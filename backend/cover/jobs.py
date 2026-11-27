"""
cover/jobs.py — Hàng đợi "AI căn lời" chạy nền, 1 bài 1 lúc (GPU dùng chung).

Trạng thái từng bài lưu trong CoverSong.align_status (none|queued|running|
done|failed|edited); thông báo tiến trình (đang tách giọng / đang căn…) giữ
trong RAM để giao diện hỏi định kỳ.
"""
from __future__ import annotations

from pathlib import Path
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlmodel import Session, select

from backend.database import engine
from backend.models import CoverSettings, CoverSong, Mix, Project, Track

from . import align
from .genre_defaults import project_genre, resolve
from .lyrics import clean_lyrics, dump_lines
from .lyrics_export import export_song_srt_files
from .mix_export import export_mix_audio

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cover-align")
_lock = threading.Lock()
# project_id → {"pending": int, "current": song_id|None, "message": str}
_state: dict[int, dict] = {}
_queued: set[int] = set()


def resolve_settings(s: Session, project_id: int, cfg: CoverSettings | None = None) -> dict:
    """Cài đặt cover đã ghép thể loại project (ô trống = theo thể loại)."""
    if cfg is None:
        cfg = s.exec(select(CoverSettings).where(
            CoverSettings.project_id == project_id)).first()
    p = s.get(Project, project_id)
    return resolve(cfg.model_dump() if cfg else {}, project_genre(p) if p else {})


def status(project_id: int) -> dict:
    with _lock:
        st = dict(_state.get(project_id) or {})
    return {"busy": bool(st.get("pending")), "current": st.get("current"),
            "message": st.get("message", ""), "pending": st.get("pending", 0)}


def any_busy() -> bool:
    with _lock:
        return any(bool(v.get("pending")) for v in _state.values())


def all_active() -> list[tuple[int, dict]]:
    with _lock:
        return [(pid, dict(st)) for pid, st in _state.items() if st.get("pending")]


def is_queued(song_id: int) -> bool:
    with _lock:
        return song_id in _queued


def submit(project_id: int, song_ids: list[int]) -> int:
    """Xếp các bài vào hàng đợi căn lời. Trả số bài mới được xếp."""
    added = 0
    with Session(engine) as s:
        for sid in song_ids:
            with _lock:
                if sid in _queued:
                    continue
                _queued.add(sid)
                st = _state.setdefault(project_id, {"pending": 0, "current": None,
                                                    "message": ""})
                st["pending"] += 1
            song = s.get(CoverSong, sid)
            if song:
                song.align_status = "queued"
                song.align_error = None
                s.add(song)
            _executor.submit(_run_one, project_id, sid)
            added += 1
        s.commit()
    return added


def submit_between(project_id: int, song_id: int, lines: list[dict],
                   anchor_indices: list[int] | None = None) -> bool:
    """Xếp 1 bài vào hàng đợi căn lại phần giữa theo câu đầu & câu cuối đã khóa."""
    import json
    with _lock:
        if song_id in _queued:
            return False
        _queued.add(song_id)
        st = _state.setdefault(project_id, {"pending": 0, "current": None, "message": ""})
        st["pending"] += 1
    with Session(engine) as s:
        song = s.get(CoverSong, song_id)
        if song:
            song.lyrics_json = json.dumps(lines, ensure_ascii=False)
            song.align_status = "queued"
            song.align_error = None
            s.add(song)
            s.commit()
    _executor.submit(_run_between, project_id, song_id, lines, anchor_indices)
    return True


def _export_after_align(project_id: int, audio_path: str, lyrics_json: str) -> None:
    with Session(engine) as s:
        project = s.get(Project, project_id)
        project_name = project.name if project else None
        project_kind = (getattr(project, "kind", "") if project else "") or "mixset"
        mixes_done = (s.exec(select(Mix).where(
            Mix.project_id == project_id, Mix.status == "completed")).all()
            if project_kind != "single" else [])
    export_song_srt_files(audio_path, lyrics_json)
    existing_mix = next(
        (Path(m.output_dir) / "mix.wav" for m in reversed(mixes_done)
         if m.output_dir and (Path(m.output_dir) / "mix.wav").is_file()),
        None)
    if existing_mix is not None:
        export_mix_audio(project_id, project_name, existing_mix)


def _set_msg(project_id: int, msg: str) -> None:
    with _lock:
        st = _state.get(project_id)
        if st is not None:
            st["message"] = msg


def _run_one(project_id: int, song_id: int) -> None:
    with _lock:
        _state[project_id]["current"] = song_id
    try:
        with Session(engine) as s:
            song = s.get(CoverSong, song_id)
            track = s.get(Track, song.track_id) if song else None
            if song is None or track is None:
                return
            cfg = s.exec(select(CoverSettings).where(
                CoverSettings.project_id == project_id)).first()
            language = resolve_settings(s, project_id, cfg)["language"]
            model_name = (cfg.whisper_model if cfg else "large-v3") or "large-v3"
            song.align_status = "running"
            s.add(song)
            s.commit()
            lines_in = clean_lyrics(song.lyrics_text)
            audio_path, track_id, title = track.filepath, track.id, song.title

        _set_msg(project_id, f"{title}: bắt đầu…")
        lines = align.process_song(
            track_id, audio_path, lines_in, language, model_name,
            log=lambda m: _set_msg(project_id, f"{title}: {m}"))

        with Session(engine) as s:
            song = s.get(CoverSong, song_id)
            if song is None:
                return
            lyrics_json = dump_lines(lines)
            song.lyrics_json = lyrics_json
            if not song.lyrics_text.strip() and lines:
                # Không có lời → lưu lời AI chép được để người dùng sửa.
                song.lyrics_text = "\n".join(l["text"] for l in lines)
            song.align_status = "done"
            song.align_error = None
            song.aligned_at = datetime.now(timezone.utc)
            s.add(song)
            s.commit()
        _export_after_align(project_id, audio_path, lyrics_json)
        q = align.quality_report(lines)
        _set_msg(project_id, f"{title}: xong {q['lines']} câu"
                 + ("" if q["ok"] else f" — {q['suspicious']} câu nghi lệch, nên rà lại"))
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        with Session(engine) as s:
            song = s.get(CoverSong, song_id)
            if song:
                song.align_status = "failed"
                song.align_error = f"{type(e).__name__}: {e}"[:500]
                s.add(song)
                s.commit()
        _set_msg(project_id, f"Lỗi: {e}")
    finally:
        last = False
        with _lock:
            _queued.discard(song_id)
            st = _state.get(project_id)
            if st:
                st["pending"] = max(st["pending"] - 1, 0)
                st["current"] = None
            last = not any(v.get("pending") for v in _state.values())
        if last:
            align.release_models()   # trả GPU cho bước dựng video


def _run_between(project_id: int, song_id: int, lines: list[dict],
                 anchor_indices: list[int] | None = None) -> None:
    import json
    with _lock:
        _state[project_id]["current"] = song_id
    try:
        with Session(engine) as s:
            song = s.get(CoverSong, song_id)
            track = s.get(Track, song.track_id) if song else None
            if song is None or track is None:
                return
            cfg = s.exec(select(CoverSettings).where(
                CoverSettings.project_id == project_id)).first()
            language = resolve_settings(s, project_id, cfg)["language"]
            model_name = (cfg.whisper_model if cfg else "large-v3") or "large-v3"
            song.align_status = "running"
            s.add(song)
            s.commit()
            audio_path, track_id, title = track.filepath, track.id, song.title

        _set_msg(project_id, f"{title}: giữ mốc đầu & cuối, AI đang căn lại phần giữa…")
        aligned = align.align_between_anchors(
            track_id, audio_path, lines, anchor_indices=anchor_indices,
            language=language, model_name=model_name,
            log=lambda m: _set_msg(project_id, f"{title}: {m}"))
        lyrics_json = json.dumps(aligned, ensure_ascii=False)

        with Session(engine) as s:
            song = s.get(CoverSong, song_id)
            if song is None:
                return
            song.lyrics_json = lyrics_json
            song.align_status = "edited"
            song.align_error = None
            song.aligned_at = datetime.now(timezone.utc)
            s.add(song)
            s.commit()
        _export_after_align(project_id, audio_path, lyrics_json)
        q = align.quality_report(aligned)
        _set_msg(project_id, f"{title}: đã căn lại phần giữa ({q['lines']} câu, giữ nguyên mốc đầu & cuối)")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        with Session(engine) as s:
            song = s.get(CoverSong, song_id)
            if song:
                song.align_status = "failed"
                song.align_error = f"{type(e).__name__}: {e}"[:500]
                s.add(song)
                s.commit()
        _set_msg(project_id, f"Lỗi căn lại phần giữa: {e}")
    finally:
        last = False
        with _lock:
            _queued.discard(song_id)
            st = _state.get(project_id)
            if st:
                st["pending"] = max(st["pending"] - 1, 0)
                st["current"] = None
            last = not any(v.get("pending") for v in _state.values())
        if last:
            align.release_models()
