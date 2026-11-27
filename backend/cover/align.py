"""
cover/align.py — AI căn thời gian lời bài hát theo từng câu.

Quy trình cho 1 bài:
  1. Tách giọng hát khỏi nhạc nền bằng Demucs (htdemucs, GPU) → vocals 16 kHz
     mono, lưu cache (tách 1 lần, căn lại bao nhiêu lần cũng được).
  2a. CÓ lời: stable-ts "align" — ép Whisper khớp ĐÚNG lời người dùng đưa vào
      giọng hát → mốc bắt đầu/kết thúc từng câu (giữ nguyên chữ của người dùng).
  2b. KHÔNG có lời: Whisper nghe và chép lời (transcribe) → câu + mốc thời gian
      (người dùng nên rà lại chính tả).

Model Whisper + Demucs được giữ trong RAM/GPU giữa các bài của cùng 1 lượt
chạy (nạp model mất ~10–30 s), giải phóng bằng release_models().
"""
from __future__ import annotations

import threading
import difflib
import re
import unicodedata
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from .lyrics import normalize_lines

WHISPER_SR = 16000
CACHE_ROOT = Path(__file__).parent.parent.parent / "data" / "cover_cache"

_lock = threading.Lock()
_whisper = {"name": None, "model": None}
_demucs = {"sep": None}

Log = Optional[Callable[[str], None]]


def _say(log: Log, msg: str) -> None:
    if log:
        try:
            log(msg)
        except Exception:
            pass


def _device() -> str:
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def release_models() -> None:
    """Giải phóng Whisper + Demucs khỏi GPU (gọi khi xong 1 lượt căn lời)."""
    with _lock:
        _whisper["name"] = None
        _whisper["model"] = None
        _demucs["sep"] = None
    try:
        import gc
        import torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def vocals_cache_path(track_id: int, audio_path: str) -> Path:
    p = Path(audio_path)
    try:
        stamp = int(p.stat().st_mtime)
    except OSError:
        stamp = 0
    return CACHE_ROOT / f"track{track_id}_{stamp}_vocals16k.wav"


def _load_mono16k(path: str) -> np.ndarray:
    import soundfile as sf
    try:
        audio, sr = sf.read(path, dtype="float32", always_2d=True)
    except Exception:
        # MP3/M4A… → giải mã bằng ffmpeg
        import subprocess
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1",
                            "-ar", str(WHISPER_SR), "-f", "f32le", "-"],
                           capture_output=True, check=True)
        return np.frombuffer(r.stdout, dtype=np.float32).copy()
    mono = audio.mean(axis=1)
    if sr != WHISPER_SR:
        import librosa
        mono = librosa.resample(mono, orig_sr=sr, target_sr=WHISPER_SR,
                                res_type="soxr_hq")
    return np.ascontiguousarray(mono, dtype=np.float32)


def separate_vocals(track_id: int, audio_path: str, log: Log = None) -> str:
    """Tách giọng hát → WAV 16 kHz mono trong cache. Có rồi thì dùng lại."""
    import soundfile as sf
    out = vocals_cache_path(track_id, audio_path)
    if out.exists() and out.stat().st_size > 1000:
        _say(log, "Dùng lại giọng hát đã tách trước đó.")
        return str(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        if _demucs["sep"] is None:
            _say(log, "Nạp AI tách giọng (Demucs)…")
            import demucs.api
            _demucs["sep"] = demucs.api.Separator(
                model="htdemucs", device=_device(), shifts=1, overlap=0.25)
        sep = _demucs["sep"]
    _say(log, "Tách giọng hát khỏi nhạc nền…")
    _, stems = sep.separate_audio_file(audio_path)
    voc = stems["vocals"].cpu().numpy()          # (channels, samples)
    mono = voc.mean(axis=0).astype(np.float32)
    if sep.samplerate != WHISPER_SR:
        import librosa
        mono = librosa.resample(mono, orig_sr=sep.samplerate, target_sr=WHISPER_SR,
                                res_type="soxr_hq")
    peak = float(np.max(np.abs(mono))) if mono.size else 0.0
    if peak > 0:
        mono = mono * (0.95 / peak)
    sf.write(str(out), mono, WHISPER_SR, subtype="FLOAT")
    return str(out)


def _get_whisper(name: str, log: Log):
    with _lock:
        if _whisper["model"] is None or _whisper["name"] != name:
            _say(log, f"Nạp AI nghe lời (Whisper {name}) — lần đầu có thể tải model "
                      f"vài GB, vui lòng đợi…")
            import stable_whisper
            _whisper["model"] = None
            _whisper["model"] = stable_whisper.load_model(name, device=_device())
            _whisper["name"] = name
        return _whisper["model"]


def _segments(result) -> list[dict]:
    segs = []
    for s in getattr(result, "segments", None) or []:
        text = str(getattr(s, "text", "") or "").strip()
        if text:
            segs.append({"text": text, "start": float(s.start), "end": float(s.end)})
    return segs


def _fold_text(text: str) -> str:
    value = unicodedata.normalize("NFKD", (text or "").casefold()).replace("đ", "d")
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _line_similarity(left: str, right: str) -> float:
    a, b = _fold_text(left), _fold_text(right)
    if not a or not b:
        return 0.0
    sequence = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
    aset, bset = set(a.split()), set(b.split())
    overlap = len(aset & bset) / max(1, min(len(aset), len(bset)))
    containment = 1.0 if a in b or b in a else 0.0
    return max(sequence, overlap * 0.92, containment)


_VIETNAMESE_RE = re.compile(r"[ăâđêôơưĂÂĐÊÔƠƯ\u1ea0-\u1ef9]")


def _lyrics_language(configured: str, lines: list[str]) -> str:
    """Ưu tiên ngôn ngữ thể hiện ngay trong lyrics.

    ``music_line=US-UK`` mô tả dòng nhạc, không đồng nghĩa ca sĩ hát tiếng Anh.
    Nếu lời có ký tự tiếng Việt đặc trưng thì Whisper phải nghe/căn ở ``vi``;
    nếu không nhận diện chắc chắn được thì giữ lựa chọn đã cấu hình.
    """
    text = " ".join(lines)
    return "vi" if _VIETNAMESE_RE.search(text) else configured


def _vocal_regions(audio: np.ndarray, sample_rate: int = WHISPER_SR) -> list[tuple[float, float]]:
    """Tìm các vùng có năng lượng giọng rõ trong stem vocal đã tách.

    Đây không phải transcript: nó chỉ giúp phát hiện một lượt hát sau mà ASR
    bỏ sót hoàn toàn. Các khoảng ngắn dưới 3 giây bị loại để tránh tiếng nhạc
    rò từ Demucs kích hoạt lời giả.
    """
    if audio is None or len(audio) < sample_rate:
        return []
    frame = max(1, int(sample_rate * 0.25))
    count = int(np.ceil(len(audio) / frame))
    padded = np.pad(np.asarray(audio, dtype=np.float32),
                    (0, count * frame - len(audio)))
    rms = np.sqrt(np.mean(padded.reshape(count, frame) ** 2, axis=1) + 1e-12)
    threshold = max(0.004, float(rms.max(initial=0.0)) * 0.04)
    active = rms >= threshold

    # Lấp các nhịp nghỉ ngắn giữa hai câu hát (tối đa 1.5 giây).
    max_gap = max(1, round(1.5 / 0.25))
    i = 0
    while i < count:
        if active[i]:
            i += 1
            continue
        j = i
        while j < count and not active[j]:
            j += 1
        if i > 0 and j < count and j - i <= max_gap:
            active[i:j] = True
        i = j

    regions: list[tuple[float, float]] = []
    i = 0
    while i < count:
        if not active[i]:
            i += 1
            continue
        j = i + 1
        while j < count and active[j]:
            j += 1
        start, end = i * 0.25, min(j * 0.25, len(audio) / sample_rate)
        if end - start >= 3.0:
            regions.append((start, end))
        i = j
    return regions


def expand_repeated_lyrics(lines: list[str], heard_segments: list[dict],
                           min_similarity: float = 0.43,
                           vocal_regions: list[tuple[float, float]] | None = None) -> list[str]:
    """Dùng transcript toàn bài làm mỏ neo để mở rộng lyrics bị viết một lượt.

    Ví dụ lyrics chỉ có Verse→Chorus nhưng audio hát Chorus lần hai, chuỗi mỏ
    neo sẽ đi 0..N-1 rồi quay về chỉ số Chorus; kết quả chứa thêm đúng phần đó.
    Chữ hiển thị luôn lấy từ lyrics đã kiểm tra, không lấy chính tả của Whisper.
    """
    clean = [line.strip() for line in lines if line and line.strip()]
    if len(clean) < 2 or not heard_segments:
        return clean
    n = len(clean)
    anchors: list[tuple[int, float, float]] = []
    unmatched: list[tuple[float, float, str]] = []
    previous: int | None = None
    for segment in heard_segments:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        scores = [_line_similarity(text, line) for line in clean]
        best_score = max(scores, default=0.0)
        if best_score < min_similarity:
            start = float(segment.get("start") or 0.0)
            end = float(segment.get("end") or start)
            unmatched.append((start, end, text))
            continue
        choices = [i for i, score in enumerate(scores) if score >= best_score - 0.06]
        if previous is None:
            idx = min(choices)
        else:
            # Khi hai câu giống nhau ở nhiều verse/chorus, ưu tiên lần xuất hiện
            # kế tiếp theo thứ tự bài; vẫn cho phép quay lại khi chorus lặp.
            def distance(i: int) -> int:
                if i > previous:
                    return i - previous
                return (n - previous) + i
            idx = min(choices, key=lambda i: (distance(i), -scores[i]))
        start = float(segment.get("start") or 0.0)
        end = float(segment.get("end") or start)
        # Whisper đôi khi chia một câu thành hai segment kề nhau.
        if anchors and anchors[-1][0] == idx and start - anchors[-1][2] < 2.5:
            anchors[-1] = (idx, anchors[-1][1], max(end, anchors[-1][2]))
        else:
            anchors.append((idx, start, end))
        previous = idx

    if not anchors:
        return clean
    # Lyrics đã xác minh phải luôn xuất hiện ít nhất một lượt đầy đủ. Transcript
    # chỉ được phép THÊM lần hát lặp, tuyệt đối không làm rơi câu gốc.
    indices: list[int] = list(range(n))
    repeat_at: int | None = None
    for pos in range(1, len(anchors)):
        prev_idx, prev_start, _ = anchors[pos - 1]
        idx, start, _ = anchors[pos]
        large_backward = prev_idx - idx >= max(3, n // 3)
        reached_end = prev_idx >= n - 3
        if idx < prev_idx and (reached_end or large_backward) and start - prev_start >= 1.0:
            repeat_at = pos
            break
    if repeat_at is not None:
        repeated: list[int] = [anchors[repeat_at][0]]
        for idx, _start, _end in anchors[repeat_at + 1:]:
            prev = repeated[-1]
            if idx == prev:
                continue
            if idx > prev:
                repeated.extend(range(prev + 1, idx + 1))
            else:
                # Có thể bài hát lặp chorus thêm một lần nữa.
                repeated.append(idx)
        # Một lần lặp thường hát tới hết chorus/outro; ASR có thể bỏ sót câu cuối.
        if repeated:
            repeated.extend(range(repeated[-1] + 1, n))
        indices.extend(repeated)

    expanded = [clean[i] for i in indices]
    # Transcript dài gần gấp nhiều lần nhưng mỏ neo quá thưa: fallback an toàn
    # cho trường hợp cả bài được hát lại nguyên chu kỳ.
    heard_words = sum(len(_fold_text(str(s.get("text") or "")).split())
                      for s in heard_segments)
    lyric_words = sum(len(_fold_text(line).split()) for line in clean)
    ratio = heard_words / max(1, lyric_words)
    repeats = min(4, max(1, round(ratio)))
    if len(expanded) <= len(clean) and ratio >= 1.55 and repeats > 1:
        expanded = clean * repeats

    # Một số bản mix khiến Whisper nghe đúng lượt đầu nhưng nhận sai hoàn toàn
    # điệp khúc cuối (thường thành một câu quảng cáo/hallucination). Nếu đã đi
    # tới cuối lyrics và sau đó còn hẳn một vùng vocal dài, dùng thời lượng để
    # suy ra số câu cuối được hát lại. stable-ts ở bước kế tiếp vẫn phải ép căn
    # từng câu vào audio thật, nên đây chỉ là mở rộng ứng viên chứ không tự đặt
    # timestamp giả.
    if len(expanded) <= len(clean) and anchors and anchors[-1][0] >= n - 3:
        first_start = anchors[0][1]
        last_end = anchors[-1][2]
        late = [(start, end, text) for start, end, text in unmatched
                if start >= last_end + 5.0]
        energy_late = [(start, end) for start, end in (vocal_regions or [])
                       if start >= last_end + 5.0]
        if late or energy_late:
            late_start = min([start for start, _end, _text in late]
                             + [start for start, _end in energy_late])
            late_end = max([end for _start, end, _text in late]
                           + [end for _start, end in energy_late])
            late_span = late_end - late_start
            base_span = max(last_end - first_start, 1.0)
            late_words = sum(len(_fold_text(text).split()) for _, _, text in late)
            if late_span >= 12.0 and (late_words >= 6 or energy_late):
                tail_count = round(n * min(late_span / base_span, 1.0))
                tail_count = max(2, min(n, tail_count))
                expanded = clean + clean[n - tail_count:]
    return expanded or clean


def align_lines(vocals_path: str, lines: list[str], language: str,
                model_name: str = "large-v3", log: Log = None) -> list[dict]:
    """Khớp lời có sẵn vào giọng hát → [{text,start,end}] (giây, từ đầu bài)."""
    if not lines:
        raise ValueError("Chưa có lời bài hát để căn.")
    audio = _load_mono16k(vocals_path)
    model = _get_whisper(model_name, log)
    detected_language = _lyrics_language(language, lines)
    vocal_regions = _vocal_regions(audio)
    if detected_language != language:
        _say(log, "Lyrics là tiếng Việt — dùng nhận diện tiếng Việt dù dòng nhạc "
                  "của project là US-UK.")
    expanded = list(lines)
    try:
        _say(log, "Nghe toàn bộ phần vocal để phát hiện verse/điệp khúc hát lặp…")
        heard = model.transcribe(audio, language=detected_language, vad=True,
                                 regroup=True, verbose=None)
        expanded = expand_repeated_lyrics(lines, _segments(heard),
                                          vocal_regions=vocal_regions)
        if len(expanded) > len(lines):
            _say(log, f"Phát hiện đoạn hát lặp: mở rộng {len(lines)} thành "
                      f"{len(expanded)} câu hiển thị.")
    except Exception as exc:  # Whisper detect lỗi vẫn căn được lời gốc như trước.
        _say(log, f"Không dò được đoạn lặp ({type(exc).__name__}) — căn theo lyrics gốc.")
        expanded = list(lines)
    _say(log, f"Căn {len(expanded)} câu hát theo giọng ca sĩ…")
    result = model.align(audio, "\n".join(expanded), language=detected_language,
                         original_split=True)
    if result is None:
        raise RuntimeError("AI không khớp được lời với giọng hát (lời có thể "
                           "không đúng bài, hoặc bài không có giọng rõ).")
    segs = _segments(result)
    if len(segs) == len(expanded):
        # Giữ NGUYÊN chữ người dùng (đúng chính tả, đúng dấu) — chỉ lấy thời gian.
        out = []
        original_count = len(lines)
        for index, (text, segment) in enumerate(zip(expanded, segs)):
            start, end = segment["start"], segment["end"]
            # Ứng viên điệp khúc đoán dư mà forced-align không tìm thấy thường
            # có duration bằng 0; bỏ nó thay vì cho renderer hiện sai câu.
            if index >= original_count and end - start < 0.3:
                continue
            # stable-ts có thể kéo end của câu trước qua cả nhạc dạo tới câu
            # lặp kế tiếp. Cắt ở biên vùng vocal để lời biến mất khi hết hát.
            for region_start, region_end in vocal_regions:
                if region_start - 0.5 <= start <= region_end + 0.5:
                    end = min(end, region_end)
                    break
            out.append({"text": text, "start": start, "end": end})
    else:
        _say(log, f"Lưu ý: AI chia {len(segs)} đoạn khác {len(expanded)} câu cần căn — "
                  "hãy rà lại ở màn hình sửa lời.")
        out = segs
    return normalize_lines(out)


def transcribe(vocals_path: str, language: str, model_name: str = "large-v3",
               log: Log = None) -> list[dict]:
    """Không có lời → AI tự nghe và chép lời theo câu."""
    audio = _load_mono16k(vocals_path)
    model = _get_whisper(model_name, log)
    _say(log, "AI đang nghe và chép lời…")
    result = model.transcribe(audio, language=language, vad=True,
                              regroup=True, verbose=None)
    return normalize_lines(_segments(result))


def quality_report(lines: list[dict]) -> dict:
    """Đánh giá nhanh kết quả căn: câu quá ngắn (<0.4 s) thường là căn hỏng."""
    if not lines:
        return {"lines": 0, "suspicious": 0, "ok": False}
    bad = sum(1 for l in lines if (l["end"] - l["start"]) < 0.4)
    return {"lines": len(lines), "suspicious": bad,
            "ok": bad <= max(1, len(lines) // 10)}


def _distribute_lines_in_span(texts: list[str], span_start: float, span_end: float,
                              vocal_regions: list[tuple[float, float]] | None = None
                              ) -> list[dict]:
    """Dự phòng khi Whisper không trả đủ số câu trên đoạn hẹp: chia tỷ lệ theo số từ
    trên các vùng có giọng hát (hoặc đều trên cả khoảng nếu không tách được vùng)."""
    if not texts:
        return []
    total_span = max(span_end - span_start, 0.05 * len(texts))
    weights = [max(1, len(t.split())) for t in texts]
    total_w = sum(weights)
    regions = []
    for r0, r1 in (vocal_regions or []):
        a0, a1 = max(r0, span_start), min(r1, span_end)
        if a1 - a0 >= 0.4:
            regions.append((a0, a1))
    voiced_len = sum(r1 - r0 for r0, r1 in regions)
    use_regions = len(regions) > 0 and voiced_len >= min(total_span * 0.35, 2.0)

    def map_pos(frac: float) -> float:
        if not use_regions:
            return span_start + frac * total_span
        target = frac * voiced_len
        acc = 0.0
        for r0, r1 in regions:
            seg_len = r1 - r0
            if acc + seg_len >= target - 1e-6:
                return r0 + min(seg_len, max(0.0, target - acc))
            acc += seg_len
        return regions[-1][1]

    out: list[dict] = []
    acc_w = 0
    for text, w in zip(texts, weights):
        f0 = acc_w / total_w
        acc_w += w
        f1 = acc_w / total_w
        t0 = map_pos(f0)
        t1 = max(map_pos(f1), t0 + 0.15)
        out.append({"text": text, "start": round(t0, 3), "end": round(min(t1, span_end), 3)})
    return out


def _repair_collapsed_runs(
    placed: list[dict],
    span_lo: float,
    span_hi: float,
    vocal_regions: list[tuple[float, float]] | None = None,
) -> list[dict]:
    """Sửa cụm câu bị Whisper gom chụm (< 0.4s/câu hoặc chồng sát nhau) ngay cạnh
    khoảng trống có giọng hát (thường xảy ra ở các câu ngay sau đoạn nhạc dạo giữa)."""
    if len(placed) < 2:
        return placed
    out = [dict(x) for x in placed]
    m = len(out)

    def _is_collapsed(idx: int) -> bool:
        dur = float(out[idx]["end"]) - float(out[idx]["start"])
        if dur < 0.4:
            return True
        if idx + 1 < m and float(out[idx + 1]["start"]) - float(out[idx]["start"]) < 0.35:
            return True
        if idx > 0 and float(out[idx]["start"]) - float(out[idx - 1]["start"]) < 0.35:
            return True
        return False

    i = 0
    while i < m:
        if not _is_collapsed(i):
            i += 1
            continue
        j = i
        while j + 1 < m and _is_collapsed(j + 1):
            j += 1
        avail_lo = float(out[i - 1]["end"]) if i > 0 else span_lo
        avail_hi = float(out[j + 1]["start"]) if j + 1 < m else span_hi
        count = j - i + 1
        if avail_hi - avail_lo >= max(1.2, 0.7 * count):
            repaired = _distribute_lines_in_span(
                [out[k]["text"] for k in range(i, j + 1)],
                avail_lo,
                avail_hi,
                vocal_regions,
            )
            for offset, row in enumerate(repaired):
                out[i + offset] = row
        i = j + 1
    return out


def align_between_anchors(track_id: int, audio_path: str, lines: list[dict],
                          anchor_indices: list[int] | None = None,
                          language: str = "vi", model_name: str = "large-v3",
                          log: Log = None) -> list[dict]:
    """Giữ cố định các câu mốc (mặc định: câu đầu 0 và câu cuối N-1), dùng AI căn
    lại tất cả các câu nằm giữa trên đúng khoảng thời gian vocal của đoạn đó."""
    if len(lines) < 3:
        raise ValueError("Cần ít nhất 3 câu lời để căn lại phần giữa.")
    cleaned: list[dict] = []
    for idx, item in enumerate(lines):
        text = str(item.get("text") or "").strip()
        if not text:
            raise ValueError(f"Câu số {idx + 1} đang trống — hãy điền chữ hoặc xoá dòng trống.")
        start = float(item.get("start") or 0.0)
        end = float(item.get("end") or (start + 2.0))
        if start < 0:
            start = 0.0
        if end <= start:
            end = start + 2.0
        cleaned.append({"text": text, "start": round(start, 3), "end": round(end, 3)})

    n = len(cleaned)
    anchors = sorted({0, n - 1, *(i for i in (anchor_indices or []) if 0 <= i < n)})
    for prev_i, next_i in zip(anchors, anchors[1:]):
        if cleaned[next_i]["start"] <= cleaned[prev_i]["start"] + 0.2:
            raise ValueError(
                f"Mốc Bắt đầu của câu #{next_i + 1} ({cleaned[next_i]['start']:.1f}s) phải lớn hơn "
                f"câu #{prev_i + 1} ({cleaned[prev_i]['start']:.1f}s).")

    vocals = separate_vocals(track_id, audio_path, log)
    audio = _load_mono16k(vocals)
    total_dur = len(audio) / WHISPER_SR if len(audio) else 0.0
    detected_language = _lyrics_language(language, [x["text"] for x in cleaned])
    all_vocal_regions = _vocal_regions(audio)
    model = _get_whisper(model_name, log)

    out = [dict(x) for x in cleaned]
    for prev_i, next_i in zip(anchors, anchors[1:]):
        if next_i - prev_i <= 1:
            if out[prev_i]["end"] > out[next_i]["start"]:
                out[prev_i]["end"] = round(max(out[prev_i]["start"] + 0.15,
                                               out[next_i]["start"]), 3)
            continue

        left = out[prev_i]
        right = out[next_i]
        mid_indices = list(range(prev_i + 1, next_i))
        mid_texts = [out[k]["text"] for k in mid_indices]
        left_dur = left["end"] - left["start"]
        joint_left = left_dur < 0.4 or left_dur > 15.0 or left["end"] >= right["start"] - 0.3

        _say(log, f"AI đang căn lại {len(mid_texts)} câu giữa câu #{prev_i + 1} "
                  f"({left['start']:.1f}s) và câu #{next_i + 1} ({right['start']:.1f}s)…")

        if not joint_left:
            win_start = left["end"]
            win_end = right["start"]
            s0 = max(0, min(len(audio), int(round(win_start * WHISPER_SR))))
            s1 = max(s0, min(len(audio), int(round(win_end * WHISPER_SR))))
            segs: list[dict] = []
            if s1 - s0 >= int(0.4 * WHISPER_SR):
                res = model.align(audio[s0:s1], "\n".join(mid_texts),
                                  language=detected_language, original_split=True)
                segs = _segments(res) if res is not None else []
            if len(segs) == len(mid_texts):
                placed = []
                for text, seg in zip(mid_texts, segs):
                    st = win_start + float(seg["start"])
                    en = win_start + float(seg["end"])
                    for r0, r1 in all_vocal_regions:
                        if r0 - 0.5 <= st <= r1 + 0.5:
                            en = min(en, r1)
                            break
                    placed.append({"text": text, "start": st, "end": max(en, st + 0.15)})
            else:
                placed = _distribute_lines_in_span(
                    mid_texts, win_start, win_end, all_vocal_regions)
            span_lo, span_hi = win_start, win_end
        else:
            # Người dùng mới chấm giờ Bắt đầu của câu đầu mà chưa chỉnh giờ Kết thúc:
            # căn chung [câu đầu + phần giữa] trên [left.start .. right.start], giữ cố định left.start.
            win_start = left["start"]
            win_end = right["start"]
            s0 = max(0, min(len(audio), int(round(win_start * WHISPER_SR))))
            s1 = max(s0, min(len(audio), int(round(win_end * WHISPER_SR))))
            joint_texts = [left["text"], *mid_texts]
            segs = []
            if s1 - s0 >= int(0.6 * WHISPER_SR):
                res = model.align(audio[s0:s1], "\n".join(joint_texts),
                                  language=detected_language, original_split=True)
                segs = _segments(res) if res is not None else []
            if len(segs) == len(joint_texts):
                left_end = win_start + float(segs[0]["end"])
                left_end = min(max(left_end, left["start"] + 0.4), win_end - 0.2)
                out[prev_i]["end"] = round(left_end, 3)
                placed = []
                for text, seg in zip(mid_texts, segs[1:]):
                    st = max(left_end, win_start + float(seg["start"]))
                    en = win_start + float(seg["end"])
                    for r0, r1 in all_vocal_regions:
                        if r0 - 0.5 <= st <= r1 + 0.5:
                            en = min(en, r1)
                            break
                    placed.append({"text": text, "start": st, "end": max(en, st + 0.15)})
                span_lo, span_hi = left_end, win_end
            else:
                est_left_end = min(left["start"] + 2.5,
                                   left["start"] + (win_end - win_start) / (len(mid_texts) + 1))
                out[prev_i]["end"] = round(max(est_left_end, left["start"] + 0.3), 3)
                span_lo, span_hi = out[prev_i]["end"], win_end
                placed = _distribute_lines_in_span(
                    mid_texts, span_lo, span_hi, all_vocal_regions)

        placed = _repair_collapsed_runs(placed, span_lo, span_hi, all_vocal_regions)

        # Khử chồng lấn cục bộ trong đoạn giữa nhưng TUYỆT ĐỐI giữ nguyên mốc câu neo.
        min_step = min(0.25, max(0.05, (span_hi - span_lo) / max(len(placed) * 3, 1)))
        starts: list[float] = []
        cursor = span_lo
        for idx_in_mid, row in enumerate(placed):
            max_start = span_hi - min_step * (len(placed) - idx_in_mid)
            st = min(max(float(row["start"]), cursor), max_start)
            starts.append(st)
            cursor = st + min_step
        for idx_in_mid, row in enumerate(placed):
            st = starts[idx_in_mid]
            nxt_limit = starts[idx_in_mid + 1] if idx_in_mid + 1 < len(placed) else span_hi
            en = min(max(float(row["end"]), st + min_step), max(nxt_limit, st + min_step), span_hi)
            out[mid_indices[idx_in_mid]] = {
                "text": row["text"], "start": round(st, 3), "end": round(en, 3),
            }

    if total_dur > 0 and out[-1]["end"] > total_dur:
        out[-1]["end"] = round(max(total_dur, out[-1]["start"] + 0.3), 3)
    return out


def process_song(track_id: int, audio_path: str, lyrics: list[str], language: str,
                 model_name: str = "large-v3", log: Log = None) -> list[dict]:
    """Trọn quy trình 1 bài: tách giọng → căn (có lời) hoặc chép lời (không lời)."""
    vocals = separate_vocals(track_id, audio_path, log)
    if lyrics:
        return align_lines(vocals, lyrics, language, model_name, log)
    return transcribe(vocals, language, model_name, log)


def expand_source_lyrics_from_audio(audio_path: str | Path, lyrics_text: str,
                                    model_name: str = "large-v3",
                                    log: Log = None) -> str:
    """Khôi phục đoạn ĐK/khổ hát lặp bị trang lời nhạc viết lược 1 lượt.

    Nhiều bài Bolero/Ballad dài 4–5 phút hát lặp lại ĐK + khổ cuối sau nhạc dạo
    giữa, nhưng lời trên NCT/Zing chỉ chép 1 lượt (~180–200 từ cho bài 280s) làm
    Suno Cover thiếu chữ để hát và biến phần còn lại thành nhạc solo.
    Hàm chỉ chạy khi bài gốc >= 140s mà mật độ chữ < 1.02 từ/giây; chữ trả về
    luôn lấy nguyên văn từ ``lyrics_text`` đã xác minh, không lấy chính tả ASR.
    """
    from .lyrics import clean_lyrics
    path = Path(audio_path)
    if not path.is_file():
        return lyrics_text
    try:
        import soundfile as sf
        duration = float(sf.info(str(path)).duration)
    except Exception:
        return lyrics_text
    if duration < 140.0:
        return lyrics_text
    lines = clean_lyrics(lyrics_text)
    if len(lines) < 4:
        return lyrics_text
    words = sum(len(line.split()) for line in lines)
    if words / duration >= 1.02:
        return lyrics_text

    _say(log, f"Lời bài hát có {words} từ / {duration:.0f}s — đang đối chiếu bài gốc "
              "để khôi phục đoạn hát lặp sau nhạc dạo…")
    try:
        audio = _load_mono16k(str(path))
        lang = _lyrics_language("vi", lines)
        model = _get_whisper(model_name, log)
        heard = model.transcribe(audio, language=lang, vad=True,
                                 regroup=True, verbose=None)
        expanded = expand_repeated_lyrics(
            lines, _segments(heard), vocal_regions=_vocal_regions(audio))
        if len(expanded) > len(lines):
            _say(log, f"Đã khôi phục đoạn hát lặp từ bài gốc: {len(lines)} → "
                      f"{len(expanded)} câu ({sum(len(x.split()) for x in expanded)} từ).")
            return "\n".join(expanded)
    except Exception as exc:
        _say(log, f"Không dò được đoạn lặp từ bài gốc ({type(exc).__name__}) — giữ nguyên lời.")
    finally:
        try:
            from . import jobs as align_jobs
            if not align_jobs.any_busy():
                release_models()
        except Exception:
            pass
    return lyrics_text
