"""Chạy auto 2 kiểu (Audio + Video / Chỉ audio) + nút mở thư mục audio/video."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

from backend import batch_service
from backend.models import BatchRun, Project
from backend.routers import projects as projects_router
from backend.video import config as vconfig


class NoStartThread:
    def __init__(self, *args, **kwargs): pass
    def start(self): pass
    def is_alive(self): return False


class _Env:
    """DB sqlite tạm + MEDIA_ROOT tạm (không đụng dữ liệu thật)."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.media = self.root / "media"
        self.media.mkdir()
        self.engine = create_engine(f"sqlite:///{self.root / 'a.sqlite'}")
        SQLModel.metadata.create_all(self.engine)
        self._patches = [
            patch.object(batch_service, "engine", self.engine),
            patch.object(batch_service.threading, "Thread", NoStartThread),
            patch.object(vconfig, "MEDIA_ROOT", self.media),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()
        self.engine.dispose()
        self.tmp.cleanup()


def _drop_threads(result):
    batch_service._threads.pop(result["batch_key"], None)
    batch_service._cancel_flags.pop(result["batch_key"], None)


class AudioOnlyBatchTests(unittest.TestCase):
    def test_singles_audio_only_saved_and_video_flags_off(self):
        with _Env() as env:
            result = batch_service.create_cover_singles(
                song_lines=["Bai Mot - Ca Si"], music_style="Ballad",
                video_style="real", audio_only=True)
            _drop_threads(result)
            with Session(env.engine) as s:
                run = s.exec(select(BatchRun)).one()
                proj = s.exec(select(Project)).one()
                self.assertTrue(json.loads(run.params_json)["audio_only"])
                self.assertFalse(proj.auto_video)
                self.assertFalse(proj.auto_upload)
                pid = proj.id
            self.assertTrue(batch_service._is_audio_only(pid))

    def test_default_is_audio_plus_video(self):
        with _Env() as env:
            result = batch_service.create_cover_singles(
                song_lines=["Bai Mot - Ca Si"], music_style="Ballad", video_style="real")
            _drop_threads(result)
            with Session(env.engine) as s:
                proj = s.exec(select(Project)).one()
                self.assertTrue(proj.auto_video)
                pid = proj.id
            self.assertFalse(batch_service._is_audio_only(pid))

    def test_single_audio_only_done_when_mastered_file_exists(self):
        from backend.cover.nct_jobs import cover_dir
        from backend.models import CoverSong, SourceSong, Track
        with _Env() as env:
            result = batch_service.create_cover_singles(
                song_lines=["Bai Mot - Ca Si"], music_style="Ballad",
                video_style="real", audio_only=True)
            _drop_threads(result)
            with Session(env.engine) as s:
                proj = s.exec(select(Project)).one()
                src = s.exec(select(SourceSong)).one()
                pid, name, sid = proj.id, proj.name, src.id
            ok, _ = batch_service._verify_product(pid)
            self.assertFalse(ok)
            mastered = cover_dir(pid, name) / "mastered"
            mastered.mkdir(parents=True)
            mwav = mastered / "Bai Mot - cover_master.wav"
            mwav.write_bytes(b"x")
            # Chỉ có file trên đĩa (vd. file cũ trong thùng rác) mà SourceSong/Track
            # chưa hoàn tất trong DB thì KHÔNG được coi là đã xong.
            self.assertFalse(batch_service._verify_product(pid)[0])
            with Session(env.engine) as s:
                src = s.get(SourceSong, sid)
                src.status = "done"
                src.suno_status = "done"
                s.add(src)
                t = Track(project_id=pid, filename=mwav.name, filepath=str(mwav),
                          duration_seconds=30.0, sample_rate=48000, channels=2,
                          format="WAV", is_lossy=False)
                s.add(t)
                s.flush()
                s.add(CoverSong(project_id=pid, track_id=t.id, position=1,
                                title="Bai Mot", artist="Ca Si",
                                lyrics_text="Lời", source_id=sid,
                                align_status="done"))
                s.commit()
            ok, _ = batch_service._verify_product(pid)
            self.assertTrue(ok)      # không đòi final.mp4 / nháp YouTube
            self.assertEqual(batch_service.audio_folder(pid), mastered)

    def test_mixset_audio_only_needs_the_mix(self):
        from backend.cover.mix_export import MIX_AUDIO_DIR
        from backend.cover.nct_jobs import cover_dir
        from backend.models import CoverSong, Mix, SourceSong, Track
        with _Env() as env:
            result = batch_service.create_cover_mixset(
                name="Set Thu", song_lines=["Bai Mot - Ca Si", "Bai Hai - Ca Si"],
                music_style="Ballad", video_style="real", audio_only=True)
            _drop_threads(result)
            with Session(env.engine) as s:
                proj = s.exec(select(Project)).one()
                pid, name = proj.id, proj.name
                self.assertFalse(proj.auto_video)
                mastered = cover_dir(pid, name) / "mastered"
                mastered.mkdir(parents=True)
                for idx, src in enumerate(s.exec(select(SourceSong)).all(), 1):
                    f = mastered / f"a_{idx}_master.wav"
                    f.write_bytes(b"x")
                    src.status = "done"
                    src.suno_status = "done"
                    s.add(src)
                    t = Track(project_id=pid, filename=f.name, filepath=str(f),
                              duration_seconds=25.0, sample_rate=48000, channels=2,
                              format="WAV", is_lossy=False)
                    s.add(t)
                    s.flush()
                    s.add(CoverSong(project_id=pid, track_id=t.id, position=idx,
                                    title=f"Bài {idx}", artist="Ca Si",
                                    lyrics_text="Lời", source_id=src.id,
                                    align_status="done"))
                s.commit()
            ok, detail = batch_service._verify_product(pid)
            self.assertFalse(ok)
            self.assertIn("mix", detail)
            mix_dir = vconfig.project_dir(pid, name) / MIX_AUDIO_DIR
            mix_dir.mkdir(parents=True)
            (mix_dir / "Set Thu.wav").write_bytes(b"x")
            out_dir = env.root / "outputs" / str(pid) / "mix_done"
            out_dir.mkdir(parents=True)
            (out_dir / "mix.wav").write_bytes(b"mix")
            with Session(env.engine) as s:
                s.add(Mix(project_id=pid, title="Mix", status="completed",
                          output_dir=str(out_dir)))
                s.commit()
            self.assertTrue(batch_service._verify_product(pid)[0])
            self.assertEqual(batch_service.audio_folder(pid), mix_dir)

    def test_set_audio_only_switches_mode_back_to_video(self):
        with _Env() as env:
            result = batch_service.create_cover_singles(
                song_lines=["Bai Mot - Ca Si"], music_style="Ballad",
                video_style="real", audio_only=True)
            _drop_threads(result)
            batch_service.set_audio_only(result["batch_key"], False)
            with Session(env.engine) as s:
                proj = s.exec(select(Project)).one()
                self.assertTrue(proj.auto_video)
                pid = proj.id
            self.assertFalse(batch_service._is_audio_only(pid))

    def test_single_audio_only_runs_ai_align_and_exports_srt(self):
        import threading
        from backend.cover import jobs as align_jobs
        from backend.cover.nct_jobs import cover_dir
        from backend.models import CoverSong, SourceSong, Track
        from backend.routers import cover as cover_router

        with _Env() as env, patch.object(align_jobs, "engine", env.engine):
            result = batch_service.create_cover_singles(
                song_lines=["Bai Mot - Ca Si"], music_style="Ballad",
                video_style="real", audio_only=True)
            _drop_threads(result)
            with Session(env.engine) as s:
                proj = s.exec(select(Project)).one()
                src = s.exec(select(SourceSong)).one()
                pid, name, sid = proj.id, proj.name, src.id
                folder = cover_dir(pid, name)
                (folder / "mastered").mkdir(parents=True)
                wav = folder / "Bai Mot - cover.wav"
                mwav = folder / "mastered" / "Bai Mot - cover_master.wav"
                wav.write_bytes(b"wav")
                mwav.write_bytes(b"master")
                src.status = "done"
                src.suno_status = "done"
                src.lyrics_text = "Mưa rơi ngoài hiên\nĐêm khuya lặng thầm"
                s.add(src)
                t = Track(project_id=pid, filename=wav.name, filepath=str(wav),
                          duration_seconds=30.0, sample_rate=48000, channels=2,
                          format="WAV", is_lossy=False)
                s.add(t)
                s.flush()
                cs = CoverSong(project_id=pid, track_id=t.id, position=1,
                               title="Bai Mot", artist="Ca Si",
                               lyrics_text="", source_id=sid, align_status="none")
                s.add(cs)
                s.commit()
                song_id = cs.id

            # Có file master nhưng chưa AI căn lời → _verify_product phải báo chưa xong.
            ok, detail = batch_service._verify_product(pid)
            self.assertFalse(ok)
            self.assertIn("AI căn lời", detail)

            aligned_calls: list[tuple[int, list[int]]] = []

            def fake_align_submit(p_id: int, song_ids: list[int]) -> int:
                aligned_calls.append((p_id, list(song_ids)))
                with Session(env.engine) as s:
                    for cid in song_ids:
                        row = s.get(CoverSong, cid)
                        row.align_status = "done"
                        row.lyrics_json = json.dumps([
                            {"text": "Mưa rơi ngoài hiên", "start": 1.0, "end": 3.0},
                            {"text": "Đêm khuya lặng thầm", "start": 4.0, "end": 6.5},
                        ], ensure_ascii=False)
                        s.add(row)
                    s.commit()
                return len(song_ids)

            with patch.object(align_jobs, "submit", side_effect=fake_align_submit), \
                    patch.object(align_jobs, "status", return_value={"busy": False, "pending": 0, "message": ""}), \
                    patch("backend.cover.nct_jobs.submit") as nct_sub, \
                    patch("backend.cover.suno_jobs.submit") as suno_sub, \
                    patch("backend.routers.mixes.start_mix_for_project") as start_mix, \
                    patch.object(batch_service.video_job_manager, "submit") as vid_sub, \
                    patch.object(cover_router.jobs, "is_queued", return_value=False):
                batch_service._cover_chain(
                    result["batch_key"], pid, [sid], threading.Event())

            self.assertEqual(aligned_calls, [(pid, [song_id])])
            nct_sub.assert_not_called()
            suno_sub.assert_not_called()
            start_mix.assert_not_called()
            vid_sub.assert_not_called()
            self.assertTrue(batch_service._verify_product(pid)[0])
            # Lời bài gốc đã tự động chép sang CoverSong trước khi căn lời, và xuất .srt.
            with Session(env.engine) as s:
                cs = s.get(CoverSong, song_id)
                self.assertIn("Mưa rơi ngoài hiên", cs.lyrics_text)
                self.assertEqual(cs.align_status, "done")
            srt_raw = folder / "Bai Mot - cover.srt"
            srt_master = folder / "mastered" / "Bai Mot - cover_master.srt"
            self.assertTrue(srt_raw.is_file())
            self.assertTrue(srt_master.is_file())
            self.assertIn("Mưa rơi ngoài hiên", srt_master.read_text(encoding="utf-8-sig"))

    def test_mixset_audio_only_aligns_before_mix_and_exports_mix_srt(self):
        import threading
        from backend.cover import jobs as align_jobs, lyrics_export
        from backend.cover.mix_export import MIX_AUDIO_DIR, export_mix_audio
        from backend.cover.nct_jobs import cover_dir
        from backend.models import CoverSong, Mix, SourceSong, Track

        with _Env() as env, \
                patch.object(align_jobs, "engine", env.engine), \
                patch.object(lyrics_export, "DB_PATH", env.root / "a.sqlite"):
            result = batch_service.create_cover_mixset(
                name="Set Thu", song_lines=["Bai Mot - Ca Si", "Bai Hai - Ca Si"],
                music_style="Ballad", video_style="real", audio_only=True)
            _drop_threads(result)
            with Session(env.engine) as s:
                proj = s.exec(select(Project)).one()
                sources = s.exec(select(SourceSong).order_by(SourceSong.position)).all()
                pid, name = proj.id, proj.name
                folder = cover_dir(pid, name)
                folder.mkdir(parents=True)
                sids = []
                for idx, src in enumerate(sources, 1):
                    wav = folder / f"bai_{idx}.wav"
                    wav.write_bytes(b"wav")
                    src.status = "done"
                    src.suno_status = "done"
                    src.lyrics_text = f"Câu hát số {idx}"
                    s.add(src)
                    t = Track(project_id=pid, filename=wav.name, filepath=str(wav),
                              duration_seconds=20.0, sample_rate=48000, channels=2,
                              format="WAV", is_lossy=False)
                    s.add(t)
                    s.flush()
                    s.add(CoverSong(project_id=pid, track_id=t.id, position=idx,
                                    title=f"Bài {idx}", artist="Ca Si",
                                    lyrics_text=src.lyrics_text, source_id=src.id,
                                    align_status="none"))
                    sids.append(src.id)
                s.commit()

            events: list[str] = []

            def fake_align_submit(p_id: int, song_ids: list[int]) -> int:
                events.append("align")
                with Session(env.engine) as s:
                    for cid in song_ids:
                        row = s.get(CoverSong, cid)
                        row.align_status = "done"
                        row.lyrics_json = json.dumps([
                            {"text": row.lyrics_text, "start": 1.0, "end": 4.0},
                        ], ensure_ascii=False)
                        s.add(row)
                    s.commit()
                return len(song_ids)

            def fake_start_mix(p_id: int, force_video: bool = False):
                events.append(f"mix:force_video={force_video}")
                out_dir = env.root / "outputs" / str(p_id) / "mix_1"
                out_dir.mkdir(parents=True)
                mix_wav = out_dir / "mix.wav"
                mix_wav.write_bytes(b"mixwav")
                with Session(env.engine) as s:
                    songs = s.exec(select(CoverSong).where(
                        CoverSong.project_id == p_id).order_by(CoverSong.position)).all()
                    info = {
                        "audio": {"total_duration_seconds": 40.0},
                        "tracks": [
                            {"song_id": songs[0].id, "start_seconds": 0.0,
                             "end_seconds": 20.0, "src_offset_seconds": 0.0},
                            {"song_id": songs[1].id, "start_seconds": 20.0,
                             "end_seconds": 40.0, "src_offset_seconds": 0.0},
                        ],
                    }
                    (out_dir / "mix_info.json").write_text(
                        json.dumps(info, ensure_ascii=False), encoding="utf-8")
                    s.add(Mix(project_id=p_id, title="Mix 1", status="completed",
                              output_dir=str(out_dir)))
                    s.commit()
                export_mix_audio(p_id, name, mix_wav)

            with patch.object(align_jobs, "submit", side_effect=fake_align_submit), \
                    patch.object(align_jobs, "status", return_value={"busy": False, "pending": 0, "message": ""}), \
                    patch("backend.routers.mixes.start_mix_for_project", side_effect=fake_start_mix), \
                    patch.object(batch_service.time, "sleep"):
                batch_service._cover_chain(
                    result["batch_key"], pid, sids, threading.Event())

            # Căn lời BẮT BUỘC chạy trước khi ghép Mix để nhac_mix/<tên>.srt có sẵn lời.
            self.assertEqual(events, ["align", "mix:force_video=False"])
            mix_dir = vconfig.project_dir(pid, name) / MIX_AUDIO_DIR
            self.assertTrue((mix_dir / "Set Thu.wav").is_file())
            self.assertTrue((mix_dir / "Set Thu.srt").is_file())
            srt_txt = (mix_dir / "Set Thu.srt").read_text(encoding="utf-8-sig")
            self.assertIn("Câu hát số 1", srt_txt)
            self.assertIn("Câu hát số 2", srt_txt)
            self.assertTrue(batch_service._verify_product(pid)[0])

    def test_auto_worker_audio_only_aligns_manual_tracks_and_reports_active(self):
        from backend.cover import jobs as align_jobs
        from backend.models import CoverSong, Track
        from backend.routers import tasks as tasks_router

        with _Env() as env, \
                patch.object(tasks_router, "engine", env.engine), \
                patch.object(align_jobs, "engine", env.engine):
            wav = env.root / "manual_cover.wav"
            wav.write_bytes(b"wav")
            with Session(env.engine) as s:
                p = Project(name="Bai Le Thu Cong", kind="single")
                s.add(p)
                s.flush()
                pid = p.id
                s.add(Track(project_id=pid, filename=wav.name, filepath=str(wav),
                            duration_seconds=15.0, sample_rate=48000, channels=2,
                            format="WAV", is_lossy=False))
                s.commit()

            def fake_submit(p_id: int, song_ids: list[int]) -> int:
                with Session(env.engine) as s:
                    for cid in song_ids:
                        row = s.get(CoverSong, cid)
                        row.align_status = "done"
                        row.lyrics_text = "Lời AI chép tự động"
                        row.lyrics_json = json.dumps([
                            {"text": "Lời AI chép tự động", "start": 0.5, "end": 2.5},
                        ], ensure_ascii=False)
                        s.add(row)
                    s.commit()
                return len(song_ids)

            with patch.object(align_jobs, "submit", side_effect=fake_submit), \
                    patch.object(align_jobs, "status", return_value={"busy": False, "pending": 0, "message": ""}), \
                    patch.object(align_jobs, "any_busy", return_value=False):
                tasks_router._auto_worker(pid, audio_only=True)

            self.assertEqual(tasks_router._auto_state[pid]["status"], "completed")
            self.assertTrue(wav.with_suffix(".srt").is_file())
            self.assertIn("Lời AI chép tự động",
                          wav.with_suffix(".srt").read_text(encoding="utf-8-sig"))

            # Kiểm tra /api/tasks/active có hiện tác vụ cover-align khi đang căn lời.
            with patch.object(align_jobs, "all_active",
                              return_value=[(pid, {"pending": 2, "current": 1, "message": "Bài 1: đang tách giọng…"})]), \
                    Session(env.engine) as s:
                active = tasks_router.active_tasks(s)
            align_items = [t for t in active["tasks"] if t["source"] == "cover-align"]
            self.assertEqual(len(align_items), 1)
            self.assertEqual(align_items[0]["tab"], "lyrics")
            self.assertEqual(align_items[0]["detail"], "còn 2 bài")

    def test_auto_audio_only_reruns_suno_after_browser_closed_even_with_trashed_files_on_disk(self):
        """Tái hiện lỗi thực tế Project #34: xoá cover cũ vào Thùng rác (file .wav
        vẫn nằm trong ban_cover/mastered), chạy Suno bị đóng nhầm trình duyệt
        (suno_status='failed'), rồi bấm «Auto chỉ audio» → PHẢI chạy lại Suno + AI
        căn lời chứ không được tưởng nhầm đã xong vì thấy file rác trên ổ đĩa."""
        from backend.cover import jobs as align_jobs, suno_jobs
        from backend.cover.nct_jobs import cover_dir
        from backend.models import CoverSong, SourceSong, Track
        from backend.routers import tracks as tracks_router

        with _Env() as env, patch.object(align_jobs, "engine", env.engine):
            result = batch_service.create_cover_singles(
                song_lines=["Sau Tim Thiep Hong - Le Quyen"],
                music_style="Ballad", video_style="real", audio_only=True)
            _drop_threads(result)
            with Session(env.engine) as s:
                proj = s.exec(select(Project)).one()
                src = s.exec(select(SourceSong)).one()
                pid, name, sid = proj.id, proj.name, src.id
                folder = cover_dir(pid, name)
                (folder / "mastered").mkdir(parents=True)
                orig = folder.parent / "nhac_goc" / "goc.mp3"
                orig.parent.mkdir(parents=True)
                orig.write_bytes(b"mp3")
                tempo_wav = folder.parent / "da_chinh_tempo" / "tempo.wav"
                tempo_wav.parent.mkdir(parents=True)
                tempo_wav.write_bytes(b"wav")
                old_cov = folder / "Sau Tim Thiep Hong - cover.wav"
                old_master = folder / "mastered" / "Sau Tim Thiep Hong - cover_master.wav"
                old_cov.write_bytes(b"old_wav")
                old_master.write_bytes(b"old_master")

                src.status = "done"
                src.file_path = str(orig)
                src.tempo_factor = 4.5
                src.tempo_file_path = str(tempo_wav)
                src.lyrics_text = "Đoạn đường xưa anh đi"
                s.add(src)
                t_old = Track(project_id=pid, filename=old_cov.name, filepath=str(old_cov),
                              duration_seconds=240.0, sample_rate=48000, channels=2,
                              format="WAV", is_lossy=False)
                s.add(t_old)
                s.flush()
                s.add(CoverSong(project_id=pid, track_id=t_old.id, position=1,
                                title="Sau Tim Thiep Hong", artist="Le Quyen",
                                lyrics_text=src.lyrics_text, source_id=sid,
                                align_status="done"))
                s.commit()

                # Người dùng xoá bản cũ vào Thùng rác (file vẫn còn trên ổ đĩa)
                # rồi lỡ tay đóng trình duyệt Suno → suno_status = 'failed'.
                t_row = s.get(Track, t_old.id)
                tracks_router._trash_track(s, t_row)
                src = s.get(SourceSong, sid)
                src.suno_status = "failed"
                src.suno_error = "TargetClosedError: Target page, context or browser has been closed"
                s.add(src)
                s.commit()

            # File cũ vẫn còn trên ổ đĩa nhưng không còn bản cover hoạt động → PHẢI chưa xong.
            ok, why = batch_service._verify_product(pid)
            self.assertFalse(ok)
            self.assertIn("Suno Cover", why)

            suno_calls: list[list[int]] = []
            align_calls: list[list[int]] = []

            def fake_suno_submit(ids: list[int], dry_run: bool = False) -> int:
                suno_calls.append(list(ids))
                new_wav = folder / "Sau Tim Thiep Hong - cover mới.wav"
                new_wav.write_bytes(b"new_wav")
                with Session(env.engine) as s:
                    src_row = s.get(SourceSong, ids[0])
                    src_row.suno_status = "done"
                    src_row.suno_error = None
                    s.add(src_row)
                    t_new = Track(project_id=pid, filename=new_wav.name, filepath=str(new_wav),
                                  duration_seconds=245.0, sample_rate=48000, channels=2,
                                  format="WAV", is_lossy=False)
                    s.add(t_new)
                    s.flush()
                    s.add(CoverSong(project_id=pid, track_id=t_new.id, position=1,
                                    title="Sau Tim Thiep Hong", artist="Le Quyen",
                                    lyrics_text=src_row.lyrics_text, source_id=src_row.id,
                                    align_status="none"))
                    s.commit()
                return len(ids)

            def fake_align_submit(p_id: int, song_ids: list[int]) -> int:
                align_calls.append(list(song_ids))
                with Session(env.engine) as s:
                    for cid in song_ids:
                        cs = s.get(CoverSong, cid)
                        cs.align_status = "done"
                        cs.lyrics_json = json.dumps(
                            [{"text": "Đoạn đường xưa anh đi", "start": 1.0, "end": 4.0}],
                            ensure_ascii=False,
                        )
                        s.add(cs)
                    s.commit()
                return len(song_ids)

            with patch.object(suno_jobs, "submit", side_effect=fake_suno_submit), \
                    patch.object(suno_jobs, "status", return_value={"busy": False, "pending": [], "current": None, "message": ""}), \
                    patch.object(align_jobs, "submit", side_effect=fake_align_submit), \
                    patch.object(align_jobs, "status", return_value={"busy": False, "pending": 0, "message": ""}), \
                    patch("backend.cover.mastering.is_busy", return_value=False):
                batch_service._run_cover_singles(result["batch_key"])

            self.assertEqual(suno_calls, [[sid]])
            self.assertEqual(len(align_calls), 1)
            self.assertTrue(batch_service._verify_product(pid)[0])

    def test_singles_list_never_autoskips_queued_songs_and_auto_run_advances_to_next_songs(self):
        """Tái hiện lỗi 50 Track lẻ: bài 1 & 2 đã xong, bài 3..5 còn queued chưa tải
        (hoặc từng bị đồng hồ 5 phút cũ đánh dấu nhầm skipped_no_lyrics):
        1) restore_pending_lyrics_timers KHÔNG ĐƯỢC đặt hẹn giờ cho các bài queued.
        2) Bấm «Auto chỉ audio» (kể cả từ trang Projects hoặc truyền nhầm bài #2 đã xong)
           phải nhảy sang bài #3 chưa làm và chạy tiếp lần lượt hết bài #3, #4, #5."""
        from backend.cover.nct_jobs import cover_dir
        from backend.models import CoverSong, SourceSong, Track
        from backend.routers import tasks as tasks_router

        with _Env() as env, patch.object(tasks_router, "engine", env.engine):
            res = batch_service.create_cover_singles(
                song_lines=[
                    "Di vang nhat nhoa - Lan Nha",
                    "Tinh nhat phai - Dam Vinh Hung",
                    "Sa mac tinh yeu - Le Quyen",
                    "Trai tim lam lo - Thanh Ha",
                ],
                music_style="Ballad", video_style="real", audio_only=True,
            )
            _drop_threads(res)
            bkey = res["batch_key"]

            with Session(env.engine) as s:
                projs = s.exec(select(Project).order_by(Project.id)).all()
                p1, p2, p3, p4 = projs
                p3_id, p4_id = p3.id, p4.id
                # Hoàn tất bài 1 & bài 2
                for p in (p1, p2):
                    src = s.exec(select(SourceSong).where(SourceSong.project_id == p.id)).one()
                    folder = cover_dir(p.id, p.name) / "mastered"
                    folder.mkdir(parents=True)
                    wav = folder / "cover_master.wav"
                    wav.write_bytes(b"wav")
                    src.status = "done"
                    src.suno_status = "done"
                    src.lyrics_text = "Lời bài hát"
                    s.add(src)
                    t = Track(project_id=p.id, filename=wav.name, filepath=str(wav),
                              duration_seconds=30.0, sample_rate=48000, channels=2,
                              format="WAV", is_lossy=False)
                    s.add(t)
                    s.flush()
                    s.add(CoverSong(project_id=p.id, track_id=t.id, position=1,
                                    title=p.name, artist="Ca si",
                                    lyrics_text="Lời bài hát", source_id=src.id,
                                    align_status="done"))
                # Lô đang dừng (blocked) sau bài 2; bài 3 đang queued, bài 4 từng bị skip nhầm 5 phút
                src4 = s.exec(select(SourceSong).where(SourceSong.project_id == p4.id)).one()
                src4.status = "skipped_no_lyrics"
                src4.error = "Tự động bỏ qua sau 5 phút không bổ sung lyrics."
                s.add(src4)
                run = s.exec(select(BatchRun).where(BatchRun.batch_key == bkey)).one()
                run.status = "blocked"
                run.current_project_id = None
                s.add(run)
                s.commit()

            # 1) Server khởi động lại: KHÔNG được bật timer bỏ qua các bài queued chưa tải!
            with patch.object(batch_service, "_schedule_auto_skip") as sched:
                batch_service.restore_pending_lyrics_timers()
                sched.assert_not_called()

            # 2) Bấm Auto chỉ audio từ trang danh sách (project_id=None) hoặc từ bài #2 đã xong:
            #    phải trỏ ngay sang bài #3 (Sa mạc tình yêu) và khôi phục cả bài #4 về queued!
            with Session(env.engine) as s:
                picked = tasks_router._resolve_fallback_project_id(s, audio_only=True)
                self.assertEqual(picked, p3_id)
                src4_after = s.exec(select(SourceSong).where(SourceSong.project_id == p4_id)).one()
                self.assertEqual(src4_after.status, "queued")

            resumed_keys: list[str] = []
            with patch.object(batch_service, "resume_batch", side_effect=lambda k: resumed_keys.append(k)), \
                 patch.object(tasks_router, "_auto_wait_idle"):
                tasks_router._auto_worker(p3_id, audio_only=True)

            self.assertEqual(resumed_keys, [bkey])


class OpenFolderTests(unittest.TestCase):
    def _project(self, env, kind="single"):
        with Session(env.engine) as s:
            p = Project(name="Bai Mot - Ca Si", kind=kind)
            s.add(p)
            s.commit()
            return p.id, p.name

    def test_open_audio_folder_and_final_video(self):
        from backend.cover.nct_jobs import cover_dir
        with _Env() as env:
            pid, name = self._project(env)
            with Session(env.engine) as s:
                self.assertEqual(projects_router._project_folders(s, pid),
                                 {"audio": None, "video": None})
                with self.assertRaises(HTTPException) as ctx:
                    projects_router.open_project_folder(pid, "audio", s)
                self.assertEqual(ctx.exception.status_code, 404)
            folder = cover_dir(pid, name)
            folder.mkdir(parents=True)
            (folder / "Bai Mot - cover.wav").write_bytes(b"x")
            final = vconfig.final_dir(pid, name)
            final.mkdir(parents=True)
            (final / "final.mp4").write_bytes(b"x")
            with Session(env.engine) as s, \
                    patch("os.startfile", create=True) as startfile, \
                    patch("subprocess.Popen") as popen:
                res = projects_router.open_project_folder(pid, "audio", s)
                startfile.assert_called_once_with(str(folder))
                self.assertEqual(res["path"], str(folder))
                projects_router.open_project_folder(pid, "video", s)
                args = popen.call_args[0][0]
                self.assertEqual(args[:2], ["explorer", "/select,"])
                self.assertTrue(args[2].endswith("final.mp4"))
                with self.assertRaises(HTTPException):
                    projects_router.open_project_folder(pid, "evil", s)


if __name__ == "__main__":
    unittest.main()
