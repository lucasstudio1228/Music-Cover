"""AI Music Director — Intelligent Suno Cover Prompt & Lyrics Engine.

Đặt giữa bước chuẩn bị lyrics gốc và ``CoverDriver.prepare_cover(...)``:
1. Chuẩn hóa lời gốc sạch (không chứa ``_``, không chứa nhãn thô) để AI hiểu ngữ nghĩa.
2. Gửi lyrics + cấu hình thể loại / cảm xúc / giọng hát / nhạc cụ bổ sung sang OpenAI API.
3. Hậu xử lý định dạng Suno: giữ nguyên dấu cách tiếng Anh trong ``[...]`` (mỗi thẻ 1 dòng riêng)
   và thay mọi khoảng trắng ngoài ``[...]`` thành ``_`` (Unicode NFC).
4. Kiểm tra tất định 7 nhóm quy tắc (schema, giới hạn 5000/1000 ký tự, bảo toàn 100% lời gốc,
   quy tắc ``[]`` & ``_``, quy tắc solo nhạc cụ, chống mâu thuẫn Style–Exclude, thông số Suno).
5. Tự động gửi lỗi chi tiết cho ChatGPT sửa tối đa 3 lần (``MAX_REPAIR_ATTEMPTS = 3``).
6. Khi chưa cấu hình API key, cung cấp bộ dựng cục bộ chuẩn hóa đạt đầy đủ cùng bộ kiểm tra
   để workflow offline / unit test không có key vẫn hoạt động trơn tru.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import difflib
import hashlib
import json
import re
from typing import Any, Callable
import unicodedata

from .genre_catalog import canonical_genre_context, genre_profile
from .music_director_prompt import (
    MUSIC_DIRECTOR_SYSTEM_PROMPT,
    PROMPT_VERSION,
    build_director_user_prompt,
    build_repair_user_prompt,
)
from .music_line import line_profile
from .style_prompt import NO_CREATIVE_INSTRUMENT, _safe_api_error
from .suno_cover import COVER_MODEL, COVER_SLIDERS, LYRICS_LIMIT
from .suno_lyrics import (
    _clean_chars,
    _clean_line,
    _fix_punct,
    _split_label,
    strip_lyrics_header,
)

MAX_LYRICS_CHARS = LYRICS_LIMIT  # 5000
MAX_STYLE_CHARS = 1000
MAX_REPAIR_ATTEMPTS = 3
_FALLBACK_MODEL = "gpt-4o-mini"

_DISABLED_INSTRUMENT_TOKENS = {
    NO_CREATIVE_INSTRUMENT.casefold(),
    "__none__",
    "none",
    "no",
    "off",
    "không",
    "khong",
    "tắt",
    "tat",
}

# Ánh xạ nhạc cụ tiếng Việt / viết tắt sang tên tiếng Anh chuẩn + tập từ khóa đối chiếu.
_INSTRUMENT_ALIASES: dict[str, tuple[str, tuple[str, ...]]] = {
    "electric guitar": ("Electric Guitar", ("electric guitar", "lead guitar", "blues guitar", "guitar")),
    "acoustic guitar": ("Acoustic Guitar", ("acoustic guitar", "steel-string guitar")),
    "classical guitar": ("Classical Guitar", ("classical guitar", "nylon guitar", "nylon-string guitar")),
    "slide guitar": ("Slide Guitar", ("slide guitar", "lap steel", "bottleneck guitar")),
    "guitar": ("Guitar", ("guitar",)),
    "saxophone": ("Saxophone", ("saxophone", "sax", "tenor sax", "alto sax", "soprano sax")),
    "sax": ("Saxophone", ("saxophone", "sax", "tenor sax", "alto sax", "soprano sax")),
    "kèn saxophone": ("Saxophone", ("saxophone", "sax")),
    "ken saxophone": ("Saxophone", ("saxophone", "sax")),
    "trumpet": ("Trumpet", ("trumpet", "muted trumpet", "flugelhorn")),
    "kèn trumpet": ("Trumpet", ("trumpet", "muted trumpet")),
    "ken trumpet": ("Trumpet", ("trumpet", "muted trumpet")),
    "harmonica": ("Harmonica", ("harmonica", "blues harp")),
    "kèn harmonica": ("Harmonica", ("harmonica", "blues harp")),
    "piano": ("Piano", ("piano", "grand piano")),
    "violin": ("Violin", ("violin", "fiddle")),
    "đàn violin": ("Violin", ("violin", "fiddle")),
    "dan violin": ("Violin", ("violin", "fiddle")),
    "vĩ cầm": ("Violin", ("violin", "fiddle")),
    "vi cam": ("Violin", ("violin", "fiddle")),
    "cello": ("Cello", ("cello",)),
    "flute": ("Flute", ("flute", "bamboo flute")),
    "sáo": ("Bamboo Flute", ("bamboo flute", "flute")),
    "sao": ("Bamboo Flute", ("bamboo flute", "flute")),
    "sáo trúc": ("Bamboo Flute", ("bamboo flute", "flute")),
    "sao truc": ("Bamboo Flute", ("bamboo flute", "flute")),
    "bamboo flute": ("Bamboo Flute", ("bamboo flute", "flute")),
    "hammond organ": ("Hammond Organ", ("hammond organ", "hammond", "organ")),
    "organ": ("Organ", ("organ", "hammond")),
    "handpan": ("Handpan", ("handpan", "hang drum")),
    "đàn bầu": ("Dan Bau Monochord", ("dan bau", "monochord")),
    "dan bau": ("Dan Bau Monochord", ("dan bau", "monochord")),
    "đàn tranh": ("Dan Tranh Zither", ("dan tranh", "zither")),
    "dan tranh": ("Dan Tranh Zither", ("dan tranh", "zither")),
    "bass": ("Electric Bass", ("electric bass", "bass guitar", "bass")),
    "bass guitar": ("Electric Bass", ("electric bass", "bass guitar", "bass")),
    "clarinet": ("Clarinet", ("clarinet",)),
    "trombone": ("Trombone", ("trombone",)),
    "accordion": ("Accordion", ("accordion",)),
}

# Các từ khóa nhạc cụ phổ biến để phát hiện thẻ solo của nhạc cụ KHÔNG được chọn.
_KNOWN_SOLO_INSTRUMENT_WORDS: tuple[str, ...] = (
    "electric guitar",
    "acoustic guitar",
    "classical guitar",
    "slide guitar",
    "nylon guitar",
    "guitar",
    "saxophone",
    "tenor sax",
    "alto sax",
    "soprano sax",
    "sax",
    "trumpet",
    "flugelhorn",
    "trombone",
    "harmonica",
    "blues harp",
    "piano",
    "hammond organ",
    "hammond",
    "organ",
    "violin",
    "fiddle",
    "cello",
    "bamboo flute",
    "flute",
    "clarinet",
    "oboe",
    "handpan",
    "dan bau",
    "monochord",
    "dan tranh",
    "zither",
    "synth",
    "synthesizer",
    "accordion",
    "mandolin",
    "banjo",
    "ukulele",
    "horn",
    "brass",
)

# Những từ khóa rộng kiểu "horn"/"brass" sẽ chặn kèn Trumpet/Saxophone nếu lọt vào Exclude Styles.
_BROAD_FAMILY_CONFLICTS: dict[str, tuple[str, ...]] = {
    "Trumpet": ("horn", "horn solo", "horns", "brass", "brass solo"),
    "Saxophone": ("horn", "horn solo", "horns", "woodwind", "reed"),
    "Trombone": ("horn", "horn solo", "brass", "brass solo"),
    "Electric Guitar": ("guitar", "guitar solo", "guitars"),
    "Acoustic Guitar": ("guitar", "guitar solo", "guitars"),
    "Classical Guitar": ("guitar", "guitar solo", "guitars"),
    "Slide Guitar": ("guitar", "guitar solo", "guitars"),
    "Bamboo Flute": ("flute", "flute solo", "woodwind"),
    "Hammond Organ": ("organ", "organ solo"),
}

_STANDALONE_TAG_RE = re.compile(r"^\[([^\[\]\r\n]+)\]$")
_LEADING_TAG_WITH_REST_RE = re.compile(r"^\[\s*([^\[\]\r\n]+?)\s*\]\s+(.+)$")
_LRC_TIME_TAG_RE = re.compile(r"^\[\d{1,3}:\d{1,2}(?:[.:]\d{1,3})?\]")
_LRC_META_TAG_RE = re.compile(r"^\[(?:ar|ti|al|by|offset|length|re|ve):[^\]]*\]$", re.I)


class MusicDirectorError(RuntimeError):
    """Lỗi khi AI Music Director không tạo được gói dữ liệu hợp lệ cho Suno."""


class OriginalLyricsTooLongError(MusicDirectorError):
    """Lời bài hát gốc đã vượt quá giới hạn 5.000 ký tự của Suno."""


@dataclass
class MusicDirectorResult:
    lyrics: str
    style: str
    exclude_styles: str
    vocal_gender: str = ""
    sliders: dict[str, int] = field(default_factory=dict)
    max_mode: bool = True
    model: str = COVER_MODEL
    source: str = "ai"               # "ai" | "fallback:no-key"
    repair_attempts: int = 0
    raw_package: dict[str, Any] = field(default_factory=dict)

    def params_dict(self) -> dict[str, Any]:
        return {
            "vocal_gender": self.vocal_gender or None,
            "sliders": dict(self.sliders),
            "max_mode": self.max_mode,
            "model": self.model,
            "source": self.source,
            "repair_attempts": self.repair_attempts,
        }


def _fold_ascii(text: str) -> str:
    norm = unicodedata.normalize("NFKD", (text or "").casefold()).replace("đ", "d")
    stripped = "".join(ch for ch in norm if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped).strip()


def canonicalize_instrument(raw: str) -> tuple[str, tuple[str, ...]]:
    """Trả ``(English Display Name, tuple_từ_khóa_đối_chiếu)``."""
    cleaned = " ".join((raw or "").strip().split())
    low = cleaned.casefold()
    folded = _fold_ascii(cleaned)
    for candidate in (low, folded):
        if candidate in _INSTRUMENT_ALIASES:
            return _INSTRUMENT_ALIASES[candidate]
    # Nhạc cụ tùy nhập: giữ nguyên tên sạch, đối chiếu theo cụm đầy đủ + từ chính.
    display = cleaned.title() if cleaned.islower() else cleaned
    aliases: list[str] = []
    for form in (low, folded):
        if form and form not in aliases:
            aliases.append(form)
    return display, tuple(aliases)


def parse_solo_instruments(featured_instrument: str, creative_instrument: bool = True) -> list[str]:
    """Phân giải danh sách nhạc cụ solo người dùng ĐÃ CHỦ ĐỘNG CHỌN.

    - ``featured_instrument`` rỗng hoặc bằng ``NO_CREATIVE_INSTRUMENT`` / ``none`` → ``[]``
      (không chèn đoạn solo).
    - Có chỉ định 1 hoặc nhiều nhạc cụ (ngăn cách bởi dấu phẩy / ``;`` / ``+`` / ``&``)
      → danh sách tên tiếng Anh chuẩn hóa.
    """
    _ = creative_instrument  # giữ tham số tương thích ngữ cảnh Project
    raw = " ".join((featured_instrument or "").strip().split())
    if not raw or raw.casefold() in _DISABLED_INSTRUMENT_TOKENS:
        return []
    parts = [
        p.strip()
        for p in re.split(r"[,;/+&]+|\s+(?:và|and)\s+", raw, flags=re.I)
        if p.strip()
    ]
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if part.casefold() in _DISABLED_INSTRUMENT_TOKENS:
            continue
        canon, _ = canonicalize_instrument(part)
        key = canon.casefold()
        if key not in seen:
            seen.add(key)
            result.append(canon)
    return result


def director_signature(
    *,
    lyrics_text: str,
    music_style: str,
    cover_style: str = "",
    music_line: str = "",
    lyrics_lang: str = "",
    description: str = "",
    vocal_gender: str = "",
    featured_instrument: str = "",
) -> str:
    """Chữ ký cache riêng cho từng bài hát (gắn chặt với cả nội dung ``lyrics_text``)."""
    clean_lyrics = clean_raw_lyrics_for_director(lyrics_text)
    solos = parse_solo_instruments(featured_instrument)
    raw = json.dumps(
        {
            "prompt_version": PROMPT_VERSION,
            "lyrics_sha256": hashlib.sha256(clean_lyrics.encode("utf-8")).hexdigest(),
            "music_style": (music_style or "").strip().casefold(),
            "cover_style": (cover_style or "").strip().casefold(),
            "music_line": (music_line or "").strip().casefold(),
            "lyrics_lang": (lyrics_lang or "").strip().casefold(),
            "description": (description or "").strip(),
            "vocal_gender": (vocal_gender or "").strip().casefold(),
            "selected_solo_instruments": [s.casefold() for s in solos],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def clean_raw_lyrics_for_director(raw: str) -> str:
    """Làm sạch lời bài hát gốc thành văn bản tự nhiên (dấu cách thường, NFC, không nhãn thô).

    Giữ nguyên 100% chữ hát (kể cả phần hát bè trong ngoặc tròn ``(Oh oh oh)``),
    bỏ dòng tiêu đề ``Bài hát: ...``, mốc thời gian LRC ``[01:23.45]`` và nhãn đoạn thô
    như ``ĐK:``, ``[Verse 1]`` để AI phân tích ngữ nghĩa sạch và đối chiếu từ ngữ chính xác.
    """
    text = strip_lyrics_header(_clean_chars(raw or "")).strip("\n")
    lines: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if _LRC_META_TAG_RE.match(line):
            continue
        line = re.sub(r"\[\d{1,3}:\d{1,2}(?:[.:]\d{1,3})?\]", " ", line)
        line = re.sub(r"[*#]+", "", line).strip()
        line = re.sub(r"^(?:>+|[-–—•]+)\s+", "", line)
        is_label, rest = _split_label(line)
        if is_label:
            lines.append("")
            line = rest
        line = _clean_line(line)
        if not re.search(r"\w", line):
            if not line.strip() or not is_label:
                lines.append("")
            continue
        lines.append(line)

    compact: list[str] = []
    for ln in lines:
        if ln == "" and (not compact or compact[-1] == ""):
            continue
        compact.append(ln)
    while compact and compact[-1] == "":
        compact.pop()
    return unicodedata.normalize("NFC", "\n".join(compact))


def is_english_bracket_tag_content(inner: str) -> bool:
    """Kiểm tra nội dung bên trong ``[...]`` có phải thẻ chỉ dẫn tiếng Anh hợp lệ không."""
    s = (inner or "").strip()
    if not s:
        return False
    if _LRC_TIME_TAG_RE.match(f"[{s}]") or _LRC_META_TAG_RE.match(f"[{s}]"):
        return False
    # Phải có ít nhất một chữ cái Latin ASCII.
    if not re.search(r"[A-Za-z]", s):
        return False
    # Không cho phép chữ cái có dấu tiếng Việt / ký tự ngoài bảng ASCII cơ bản + dấu gạch nối chuẩn.
    for ch in s:
        if ord(ch) < 128:
            continue
        if ch in "–—’'":
            continue
        return False
    return True


def is_standalone_suno_tag_line(line: str) -> bool:
    """True nếu cả dòng là một thẻ ``[...]`` tiếng Anh độc lập (không chứa ``_``)."""
    m = _STANDALONE_TAG_RE.match((line or "").strip())
    if not m:
        return False
    inner = m.group(1)
    if "_" in inner:
        return False
    return is_english_bracket_tag_content(inner)


def _clean_sung_line_preserving_words(line: str, *, underscore: bool = True) -> str:
    """Chuẩn hóa 1 dòng lời hát ngoài ``[...]``: NFC, sạch dấu câu, đổi khoảng trắng sang ``_``."""
    cleaned = _clean_chars(line)
    cleaned = re.sub(r"[*#]+", "", cleaned)
    cleaned = re.sub(r"^\s*(?:>+|[-–—]+)(?:\s+|$)", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = _fix_punct(cleaned)
    # Bỏ khoảng trắng thừa ngay sau '(' hoặc trước ')' để tránh '(_Oh_oh_)'
    cleaned = re.sub(r"\(\s+", "(", cleaned)
    cleaned = re.sub(r"\s+\)", ")", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = unicodedata.normalize("NFC", cleaned)
    if not underscore:
        return cleaned
    return re.sub(r"_+", "_", re.sub(r"\s+", "_", cleaned)).strip("_")


def _clean_exclude_styles(raw: str) -> str:
    """Chuẩn hóa ``suno.exclude_styles`` thành chuỗi tag âm tính ngăn cách bằng dấu phẩy,
    gỡ bỏ các câu văn xuôi kiểu 'Exclude ... Avoid ...' hoặc cụm chứa từ khóa dương tính."""
    text = unicodedata.normalize("NFC", " ".join((raw or "").replace("\r", " ").replace("\n", " ").split()))
    if not text:
        return ""
    # Tách theo dấu chấm / chấm phẩy / dấu phẩy thành các mảnh tag gọn.
    raw_chunks = re.split(r"[.;,]+", text)
    tags: list[str] = []
    seen: set[str] = set()
    for chunk in raw_chunks:
        item = chunk.strip()
        item = re.sub(r"^(?:exclude|avoid|no|without|do\s+not\s+use|don't\s+use)\s+", "", item, flags=re.I).strip()
        item = re.sub(r"^(?:and|or)\s+", "", item, flags=re.I).strip()
        if not item:
            continue
        low = item.casefold()
        # Chặn các mệnh đề dài vô tình nhắc tới "vietnamese pronunciation" / "clear vocals" trong ô âm tính.
        if any(pos in low for pos in ("pronunciation", "clear vocal", "natural vocal", "original lyrics")):
            continue
        if len(item) > 65:
            continue
        if low not in seen:
            seen.add(low)
            tags.append(item)
    return ", ".join(tags)[:300].rstrip(" ,")


def postprocess_structured_lyrics(structured_lyrics: str, *, underscore: bool = True) -> str:
    """Hậu xử lý an toàn cho ``suno.lyrics`` mà KHÔNG cắt xén và KHÔNG sửa chữ hát:

    - Dòng thẻ ``[...]`` tiếng Anh: tách ra dòng riêng nếu bị dính đầu dòng lời,
      đổi mọi ``_`` bên trong ``[...]`` về dấu cách tiếng Anh chuẩn.
    - Dòng lời hát ngoài ``[...]``: chuẩn hóa Unicode NFC, dấu câu gọn và thay mọi khoảng trắng
      giữa các từ thành ``_`` (khi ``underscore=True``).
    - Giữa các đoạn tối đa 1 dòng trống; bỏ dòng trống thừa đầu/cuối.
    """
    raw = unicodedata.normalize("NFC", (structured_lyrics or "").replace("\r\n", "\n").replace("\r", "\n"))
    expanded_lines: list[str] = []
    for raw_line in raw.split("\n"):
        stripped = raw_line.strip()
        if not stripped:
            expanded_lines.append("")
            continue
        # Thẻ [...] đứng riêng một dòng (kể cả khi AI lỡ viết [Chorus_-_Soulful_Vocal]).
        m_only = _STANDALONE_TAG_RE.match(stripped)
        if m_only:
            inner_candidate = re.sub(r"[\s_]+", " ", m_only.group(1)).strip()
            inner_candidate = inner_candidate.replace("–", "-").replace("—", "-")
            if is_english_bracket_tag_content(inner_candidate):
                expanded_lines.append(f"[{inner_candidate}]")
                continue
        # Thẻ [...] đứng đầu dòng rồi dính lời hát phía sau -> tách thành 2 dòng riêng.
        m_lead = _LEADING_TAG_WITH_REST_RE.match(stripped)
        if m_lead:
            inner_candidate = re.sub(r"[\s_]+", " ", m_lead.group(1)).strip()
            inner_candidate = inner_candidate.replace("–", "-").replace("—", "-")
            if is_english_bracket_tag_content(inner_candidate):
                expanded_lines.append(f"[{inner_candidate}]")
                expanded_lines.append(m_lead.group(2).strip())
                continue
        expanded_lines.append(stripped)

    processed: list[str] = []
    for line in expanded_lines:
        if not line:
            if processed and processed[-1] != "":
                processed.append("")
            continue
        if is_standalone_suno_tag_line(line):
            processed.append(line)
            continue
        sung = _clean_sung_line_preserving_words(line, underscore=underscore)
        if not sung:
            if processed and processed[-1] != "":
                processed.append("")
            continue
        processed.append(sung)

    while processed and processed[-1] == "":
        processed.pop()
    return unicodedata.normalize("NFC", "\n".join(processed))


def reconcile_repeated_stanzas_with_original(
    structured_lyrics: str,
    clean_orig: str,
    *,
    underscore: bool = True,
) -> str:
    """Khôi phục chính xác số lần lặp khổ hát (ví dụ bài có 3–4 lần điệp khúc lặp cuối bài
    mà LLM đếm nhầm thành 2 hoặc 4 lần), trong khi VẪN CHẶN NGHIÊM NGẶT mọi trường hợp AI
    tự bịa/sửa/dịch lời lạ.

    Điều kiện chỉ kích hoạt khôi phục khổ lặp:
    1. Đã có ít nhất 1 thẻ ``[...]`` hợp lệ.
    2. Lời hiện tại chưa khớp 100% từ với ``clean_orig``.
    3. >= 92% các dòng hát mà AI xuất ra đều khớp nguyên văn với một dòng có thật trong ``clean_orig``
       (tức AI KHÔNG bịa câu mới kiểu 'Câu này AI tự ý sửa lời bài hát'), VÀ AI đã bao phủ >= 65%
       tập dòng duy nhất của ``clean_orig`` (tức AI không xóa trắng cả bài).
    Khi thỏa cả 3 điều kiện, ánh xạ các thẻ ``[...]`` (kể cả thẻ ``[...Solo...]``) của AI lên
    đúng từng dòng của ``clean_orig`` để bảo toàn 100% lời gốc ngay từ lượt đầu tiên.
    """
    if not structured_lyrics or not clean_orig:
        return structured_lyrics

    orig_raw_lines = clean_orig.split("\n")
    orig_sung = [ln.strip() for ln in orig_raw_lines if ln.strip()]
    if not orig_sung:
        return structured_lyrics

    # Nếu vốn dĩ đã khớp 100% từ gốc -> giữ nguyên tuyệt đối bản của AI.
    ai_lines_all = structured_lyrics.split("\n")
    ai_sung_only = [
        ln for ln in ai_lines_all if ln.strip() and not is_standalone_suno_tag_line(ln.strip())
    ]
    if _word_tokens("\n".join(ai_sung_only)) == _word_tokens(clean_orig):
        return structured_lyrics

    # Tách structured_lyrics thành danh sách (tags_trước_dòng, dòng_hát_AI) + tags_cuối_bài.
    ai_entries: list[tuple[list[str], str]] = []
    pending_tags: list[str] = []
    has_any_tag = False
    for raw_ln in ai_lines_all:
        s = raw_ln.strip()
        if not s:
            continue
        if is_standalone_suno_tag_line(s):
            pending_tags.append(s)
            has_any_tag = True
        else:
            ai_entries.append((pending_tags, s))
            pending_tags = []
    trailing_tags = pending_tags

    if not has_any_tag or not ai_entries:
        return structured_lyrics

    def _line_key(s: str) -> str:
        return " ".join(_word_tokens(s))

    orig_keys = [_line_key(ln) for ln in orig_sung]
    ai_keys = [_line_key(ln) for _, ln in ai_entries]
    orig_unique = set(k for k in orig_keys if k)
    if not orig_unique:
        return structured_lyrics

    # Kiểm tra nghiêm ngặt: mọi dòng AI viết phải là dòng có thật của bài gốc (không có dòng bịa lạ).
    valid_ai_lines = sum(1 for k in ai_keys if k in orig_unique)
    if valid_ai_lines / max(1, len(ai_keys)) < 0.92:
        return structured_lyrics
    covered_unique = len(orig_unique.intersection(ai_keys)) / len(orig_unique)
    if covered_unique < 0.65:
        return structured_lyrics

    # Căn gióng chuỗi dòng giữa bản gốc (chuẩn) và bản AI để gắn thẻ [...] đúng ranh giới khổ.
    matcher = difflib.SequenceMatcher(a=orig_keys, b=ai_keys, autojunk=False)
    tags_before_orig: dict[int, list[str]] = {i: [] for i in range(len(orig_sung))}
    used_ai_tag_indices: set[int] = set()

    for tag_op, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag_op == "equal":
            for offset in range(i2 - i1):
                oi = i1 + offset
                aj = j1 + offset
                if ai_entries[aj][0]:
                    tags_before_orig[oi].extend(ai_entries[aj][0])
                    used_ai_tag_indices.add(aj)
        elif tag_op in ("replace", "delete", "insert"):
            # Bảo toàn mọi thẻ Solo hoặc thẻ đoạn nằm trong vùng AI thừa/lệch vào ranh giới gần nhất.
            rescued: list[str] = []
            for aj in range(j1, j2):
                if aj not in used_ai_tag_indices and ai_entries[aj][0]:
                    for t in ai_entries[aj][0]:
                        if "solo" in t.casefold() or aj == j1:
                            rescued.append(t)
                    used_ai_tag_indices.add(aj)
            if rescued:
                target_oi = min(i1, len(orig_sung) - 1)
                tags_before_orig[target_oi].extend(rescued)

    # Đảm bảo dòng đầu tiên luôn có thẻ mở bài nếu AI có đặt thẻ đầu.
    if not tags_before_orig[0] and ai_entries[0][0]:
        tags_before_orig[0].extend(ai_entries[0][0])

    # Dựng lại văn bản kết quả từ chính xác từng dòng của clean_orig (bảo toàn ranh giới khổ gốc).
    out_lines: list[str] = []
    sung_cursor = 0
    for raw_ln in orig_raw_lines:
        if not raw_ln.strip():
            if out_lines and out_lines[-1] != "":
                out_lines.append("")
            continue
        attached = tags_before_orig.get(sung_cursor, [])
        if attached:
            if out_lines and out_lines[-1] != "":
                out_lines.append("")
            for t in attached:
                # Tránh nhân đôi hai thẻ giống hệt liền nhau
                if not out_lines or out_lines[-1] != t:
                    out_lines.append(t)
        out_lines.append(_clean_sung_line_preserving_words(raw_ln.strip(), underscore=underscore))
        sung_cursor += 1

    if trailing_tags:
        if out_lines and out_lines[-1] != "":
            out_lines.append("")
        for t in trailing_tags:
            if "solo" in t.casefold() or "outro" in t.casefold() or "end" in t.casefold():
                out_lines.append(t)

    while out_lines and out_lines[-1] == "":
        out_lines.pop()
    return unicodedata.normalize("NFC", "\n".join(out_lines))


def _word_tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFC", (text or "")).replace("_", " ")
    return [tok.casefold() for tok in re.findall(r"\w+", normalized, flags=re.UNICODE)]


def _describe_word_mismatch(expected: list[str], actual: list[str]) -> str:
    limit = min(len(expected), len(actual))
    idx = next((i for i in range(limit) if expected[i] != actual[i]), limit)
    exp_slice = " ".join(expected[max(0, idx - 3): idx + 5])
    act_slice = " ".join(actual[max(0, idx - 3): idx + 5])
    return (
        f"Lời hát không khớp 100% với lời gốc (gốc {len(expected)} từ, output {len(actual)} từ; "
        f"lệch từ vị trí #{idx + 1}: gốc «{exp_slice}» vs output «{act_slice}»)."
    )


def _contains_phrase(haystack: str, needle: str) -> bool:
    h = _fold_ascii(haystack)
    n = _fold_ascii(needle)
    if not h or not n:
        return False
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", h))


def _style_without_negations(style: str) -> str:
    """Loại bỏ các cụm phủ định 'no ... solo' / 'without ... solo' trước khi dò solo dương tính."""
    return re.sub(
        r"\b(?:no|without|avoid|free\s+of)\s+(?:[a-z0-9-]+\s+){0,4}solos?\b",
        " ",
        style or "",
        flags=re.I,
    )


def _extract_bracket_tags(lyrics: str) -> list[str]:
    tags: list[str] = []
    for line in (lyrics or "").splitlines():
        m = _STANDALONE_TAG_RE.match(line.strip())
        if m:
            tags.append(m.group(1).strip())
    return tags


def _parse_json_object(raw_text: str) -> dict[str, Any]:
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("Phản hồi từ AI đang rỗng.")
    # Gỡ markdown fence nếu custom OpenAI-compatible endpoint bọc ```json ... ```
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.I | re.S)
    if fenced:
        text = fenced.group(1).strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            obj = json.loads(text[start: end + 1])
        else:
            raise
    if not isinstance(obj, dict):
        raise ValueError("JSON trả về phải là một object ở cấp cao nhất.")
    return obj


def _coerce_optional_int(value: Any, field_name: str, lo: int, hi: int, errors: list[str]) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        errors.append(f"Thông số {field_name} phải là số nguyên {lo}..{hi}, không phải boolean.")
        return None
    if isinstance(value, (int, float)):
        iv = int(round(value))
        if abs(float(value) - iv) > 1e-6:
            errors.append(f"Thông số {field_name}={value!r} phải là số nguyên.")
            return None
        if not (lo <= iv <= hi):
            errors.append(f"Thông số {field_name}={iv} nằm ngoài khoảng hợp lệ {lo}..{hi}.")
            return None
        return iv
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        iv = int(value.strip())
        if not (lo <= iv <= hi):
            errors.append(f"Thông số {field_name}={iv} nằm ngoài khoảng hợp lệ {lo}..{hi}.")
            return None
        return iv
    errors.append(f"Thông số {field_name}={value!r} không hợp lệ (cần số nguyên {lo}..{hi} hoặc null).")
    return None


def validate_director_package(
    payload: dict[str, Any],
    *,
    original_lyrics: str,
    requested_genre: str,
    selected_solo_instruments: list[str],
    user_vocal_gender: str = "",
    underscore_formatting: bool = True,
) -> tuple[bool, list[str], dict[str, Any]]:
    """Kiểm tra tất định toàn bộ 7 nhóm quy tắc trên gói JSON của AI Music Director.

    Không tự ý cắt ngắn (truncate) ``lyrics`` hay ``style`` để lách kiểm tra.
    Trả ``(is_valid, errors, normalized_payload)``.
    """
    errors: list[str] = []
    if not isinstance(payload, dict):
        return False, ["Dữ liệu trả về không phải JSON object."], {}

    status = str(payload.get("status") or "").strip().lower()
    validation_in = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
    if status == "error":
        warns = validation_in.get("warnings") if isinstance(validation_in.get("warnings"), list) else []
        msg = "; ".join(str(w) for w in warns if w) or "AI trả status='error'."
        return False, [f"AI báo lỗi: {msg}"], payload
    if status != "success":
        errors.append(f"Trường status phải là 'success' (nhận được: {payload.get('status')!r}).")

    for section_key in ("analysis", "music_direction", "suno"):
        if not isinstance(payload.get(section_key), dict):
            errors.append(f"Thiếu object bắt buộc '{section_key}' trong JSON.")

    if errors:
        return False, errors, payload

    suno = dict(payload["suno"])
    lyrics = suno.get("lyrics")
    style = suno.get("style")
    exclude_styles = suno.get("exclude_styles")

    if not isinstance(lyrics, str) or not lyrics.strip():
        errors.append("suno.lyrics phải là chuỗi khác rỗng.")
        lyrics = ""
    if not isinstance(style, str) or not style.strip():
        errors.append("suno.style phải là chuỗi khác rỗng.")
        style = ""
    if exclude_styles is None:
        exclude_styles = ""
    elif not isinstance(exclude_styles, str):
        errors.append("suno.exclude_styles phải là chuỗi.")
        exclude_styles = str(exclude_styles)

    # Làm sạch khoảng trắng dòng đơn cho style & exclude_styles (KHÔNG cắt ngắn ký tự!).
    style_clean = unicodedata.normalize("NFC", " ".join(style.replace("\r", " ").replace("\n", " ").split()))
    exclude_clean = unicodedata.normalize(
        "NFC", " ".join(exclude_styles.replace("\r", " ").replace("\n", " ").split())
    )

    # ── 2. Giới hạn ký tự cứng (không truncate) ──
    if len(lyrics) > MAX_LYRICS_CHARS:
        errors.append(
            f"suno.lyrics dài {len(lyrics)} ký tự, vượt giới hạn tối đa {MAX_LYRICS_CHARS} ký tự của Suno "
            "(hãy rút gọn các thẻ [...] tiếng Anh, tuyệt đối không xóa lời hát gốc)."
        )
    if len(style_clean) == 0:
        errors.append("suno.style không được để trống.")
    elif len(style_clean) > MAX_STYLE_CHARS:
        errors.append(
            f"suno.style dài {len(style_clean)} ký tự, vượt giới hạn tối đa {MAX_STYLE_CHARS} ký tự của Suno."
        )

    # Chặn lỗi nhầm sang nhạc không lời ở chế độ Cover.
    style_low = style_clean.casefold()
    if any(p in style_low for p in ("instrumental only", "purely instrumental", "no vocals", "without vocals")):
        errors.append("suno.style không được yêu cầu instrumental-only / không có giọng hát trong chế độ Cover.")

    # ── 3 & 4. Quy tắc dấu [], dấu _, NFC và bảo toàn 100% lời gốc ──
    if lyrics:
        if not unicodedata.is_normalized("NFC", lyrics):
            errors.append("suno.lyrics chưa chuẩn hóa Unicode NFC.")
        if lyrics != lyrics.strip("\n") or "\n\n\n" in lyrics:
            errors.append("suno.lyrics có dòng trống thừa ở đầu/cuối hoặc nhiều hơn 1 dòng trống liên tiếp.")

        raw_lines = lyrics.split("\n")
        tag_inners: list[str] = []
        sung_lines: list[str] = []

        for line_no, ln in enumerate(raw_lines, 1):
            if ln == "":
                continue
            m_tag = _STANDALONE_TAG_RE.match(ln)
            if m_tag:
                inner = m_tag.group(1)
                if "_" in inner:
                    errors.append(
                        f"Dòng {line_no}: thẻ [{inner}] chứa dấu '_' — bên trong [...] bắt buộc giữ dấu cách tiếng Anh bình thường."
                    )
                if not is_english_bracket_tag_content(inner):
                    errors.append(
                        f"Dòng {line_no}: thẻ [{inner}] không hợp lệ — bên trong [...] phải viết bằng tiếng Anh chuẩn (ASCII)."
                    )
                tag_inners.append(inner)
                continue

            # Dòng lời hát ngoài [...]
            if "[" in ln or "]" in ln:
                errors.append(
                    f"Dòng {line_no}: thẻ [...] không được nằm chung dòng với lời hát («{ln[:80]}»)."
                )
            if underscore_formatting:
                if any(ch.isspace() for ch in ln):
                    errors.append(
                        f"Dòng {line_no}: dòng lời hát ngoài [...] vẫn còn khoảng trắng chưa đổi sang '_' («{ln[:80]}»)."
                    )
            sung_lines.append(ln)

        if not tag_inners:
            errors.append("suno.lyrics chưa có bất kỳ thẻ cấu trúc [...] hợp lệ nào.")
        if not sung_lines:
            errors.append("suno.lyrics không có dòng lời hát nào ngoài [...].")

        clean_orig = clean_raw_lyrics_for_director(original_lyrics)
        expected_words = _word_tokens(clean_orig)
        actual_words = _word_tokens("\n".join(sung_lines))
        if expected_words != actual_words:
            errors.append(_describe_word_mismatch(expected_words, actual_words))

    # ── 5. Quy tắc nhạc cụ solo bổ sung ──
    tags = _extract_bracket_tags(lyrics)
    solo_tags = [t for t in tags if re.search(r"\bsolo\b", t, flags=re.I)]
    positive_style = _style_without_negations(style_clean)
    exclude_items = [item.strip() for item in re.split(r"[,;]+", exclude_clean) if item.strip()]

    if selected_solo_instruments:
        allowed_keywords: set[str] = set()
        for inst in selected_solo_instruments:
            canon, aliases = canonicalize_instrument(inst)
            allowed_keywords.update(_fold_ascii(a) for a in aliases)
            allowed_keywords.add(_fold_ascii(canon))

            # (a) Phải có thẻ [...Solo...] khớp với nhạc cụ này
            matched_tag = any(
                any(_contains_phrase(tag, alias) for alias in (canon, *aliases))
                for tag in solo_tags
            )
            if not matched_tag:
                errors.append(
                    f"Người dùng đã chọn nhạc cụ solo '{canon}', nhưng suno.lyrics chưa có thẻ "
                    f"[{canon} Solo - ...] riêng biệt."
                )

            # (b) Style phải nhắc tới nhạc cụ đã chọn và tính chất solo (không ép 'no instrumental solo')
            if not any(_contains_phrase(style_clean, alias) for alias in (canon, *aliases)):
                errors.append(f"suno.style chưa đề cập tới nhạc cụ solo đã chọn '{canon}'.")
            if re.search(r"\bno\s+(?:instrumental\s+)?solos?\b", style_clean, flags=re.I):
                errors.append(
                    "suno.style đang chứa 'no solo / no instrumental solo' mâu thuẫn với nhạc cụ solo đã chọn."
                )
            if not re.search(r"\bsolo\b", positive_style, flags=re.I):
                errors.append(
                    f"suno.style chưa mô tả phần solo nổi bật cho nhạc cụ '{canon}'."
                )

            # (c) Exclude styles không được chặn 'solo' hoặc chặn nhạc cụ này / họ nhạc cụ bao trùm nó
            broad_conflicts = _BROAD_FAMILY_CONFLICTS.get(canon, ())
            for ex in exclude_items:
                ex_fold = _fold_ascii(ex)
                if ex_fold in ("solo", "solos", "instrumental solo", "instrumental solos"):
                    errors.append(
                        f"suno.exclude_styles chứa '{ex}' làm chặn mất đoạn solo của '{canon}'."
                    )
                    continue
                if any(_contains_phrase(ex, alias) for alias in (canon, *aliases)):
                    errors.append(
                        f"suno.exclude_styles chứa '{ex}' mâu thuẫn trực tiếp với nhạc cụ solo đã chọn '{canon}'."
                    )
                    continue
                if any(ex_fold == _fold_ascii(bc) for bc in broad_conflicts):
                    errors.append(
                        f"suno.exclude_styles chứa '{ex}' chặn họ nhạc cụ của '{canon}'."
                    )

        # (d) Không được tự bịa thẻ solo của nhạc cụ khác không nằm trong danh sách chọn
        for tag in solo_tags:
            for kw in _KNOWN_SOLO_INSTRUMENT_WORDS:
                if _contains_phrase(tag, kw):
                    # Hợp lệ nếu kw là từ con hoặc từ bao của một nhạc cụ đã chọn (vd 'guitar' trong 'electric guitar').
                    kw_fold = _fold_ascii(kw)
                    compatible = any(
                        kw_fold == ak or kw_fold in ak or ak in kw_fold
                        for ak in allowed_keywords
                    )
                    if not compatible:
                        errors.append(
                            f"Thẻ [{tag}] chứa nhạc cụ solo '{kw}' không nằm trong danh sách người dùng chọn "
                            f"({', '.join(selected_solo_instruments)})."
                        )
    else:
        # Người dùng KHÔNG chọn nhạc cụ bổ sung -> cấm tuyệt đối mọi thẻ solo và yêu cầu solo.
        if solo_tags:
            errors.append(
                f"Người dùng KHÔNG chọn nhạc cụ solo bổ sung, nhưng suno.lyrics lại chèn thẻ solo: {solo_tags!r}."
            )
        if re.search(r"\bsolo\b", positive_style, flags=re.I):
            errors.append(
                "Người dùng KHÔNG chọn nhạc cụ solo bổ sung, nhưng suno.style lại yêu cầu solo nhạc cụ."
            )

    # ── 6. Chống mâu thuẫn giữa thể loại chính và Exclude Styles ──
    genre_clean = " ".join((requested_genre or "").strip().split())
    if genre_clean and exclude_items:
        genre_fold = _fold_ascii(genre_clean)
        # Các mảnh thể loại cốt lõi (ví dụ "Blues Rock" -> {"blues rock", "blues", "rock"},
        # "Vietnamese Bolero" -> {"vietnamese bolero", "bolero"}).
        genre_parts = {genre_fold}
        for token in re.split(r"[/,&+]+|\s+", genre_fold):
            if token and token not in {"music", "song", "cover", "modern", "traditional", "vietnamese", "pop"}:
                genre_parts.add(token)
        if genre_fold == "pop":
            genre_parts.add("pop")
        for ex in exclude_items:
            ex_fold = _fold_ascii(ex)
            if ex_fold in genre_parts:
                errors.append(
                    f"suno.exclude_styles chứa '{ex}' mâu thuẫn trực tiếp với thể loại yêu cầu '{genre_clean}'."
                )

    # ── 7. Kiểm tra thông số Suno & quyền ưu tiên cài đặt người dùng ──
    weirdness = _coerce_optional_int(suno.get("weirdness"), "suno.weirdness", 0, 100, errors)
    style_influence = _coerce_optional_int(
        suno.get("style_influence"), "suno.style_influence", 0, 100, errors
    )
    audio_influence = _coerce_optional_int(
        suno.get("audio_influence"), "suno.audio_influence", 0, 100, errors
    )
    variety = _coerce_optional_int(suno.get("variety"), "suno.variety", 0, 4, errors)

    raw_gender = suno.get("vocal_gender")
    norm_gender: str | None
    if raw_gender is None or str(raw_gender).strip().lower() in ("", "auto", "null"):
        norm_gender = None
    else:
        g_low = str(raw_gender).strip().lower()
        if g_low not in ("male", "female", "duet"):
            errors.append(
                f"suno.vocal_gender={raw_gender!r} không hợp lệ (chỉ chấp nhận 'male', 'female', 'duet' hoặc null)."
            )
            norm_gender = None
        else:
            norm_gender = g_low

    explicit_gender = (user_vocal_gender or "").strip().lower()
    if explicit_gender in ("male", "female", "duet"):
        norm_gender = explicit_gender

    raw_max_mode = suno.get("max_mode")
    if raw_max_mode is not None and not isinstance(raw_max_mode, bool):
        errors.append(f"suno.max_mode={raw_max_mode!r} phải là boolean hoặc null.")
        norm_max_mode = True
    else:
        norm_max_mode = True if raw_max_mode is None else bool(raw_max_mode)

    raw_model = suno.get("model")
    if raw_model is not None and str(raw_model).strip() and str(raw_model).strip().lower() != COVER_MODEL:
        errors.append(
            f"suno.model={raw_model!r} không được hỗ trợ trong CoverDriver (chỉ chấp nhận '{COVER_MODEL}' hoặc null)."
        )
        norm_model = COVER_MODEL
    else:
        norm_model = COVER_MODEL

    normalized = dict(payload)
    normalized_suno = dict(suno)
    normalized_suno.update(
        {
            "lyrics": lyrics,
            "style": style_clean,
            "exclude_styles": exclude_clean,
            "vocal_gender": norm_gender,
            "weirdness": weirdness,
            "style_influence": style_influence,
            "audio_influence": audio_influence,
            "variety": variety,
            "duration_seconds": None,
            "max_mode": norm_max_mode,
            "personalize": None,
            "model": norm_model,
        }
    )
    normalized["suno"] = normalized_suno
    normalized["validation"] = {
        "lyrics_character_count": len(lyrics),
        "style_character_count": len(style_clean),
        "original_lyrics_preserved": not any("Lời hát không khớp" in e for e in errors),
        "solo_requirements_satisfied": not any("solo" in e.casefold() for e in errors),
        "warnings": list(validation_in.get("warnings") or []) if isinstance(validation_in, dict) else [],
    }
    return len(errors) == 0, errors, normalized


def build_local_director_package(
    *,
    original_lyrics: str,
    requested_genre: str,
    cover_style: str = "",
    music_line: str = "",
    lyrics_lang: str = "",
    description: str = "",
    vocal_gender: str = "",
    selected_solo_instruments: list[str] | None = None,
    underscore_formatting: bool = True,
) -> dict[str, Any]:
    """Bộ dựng cục bộ (chỉ dùng khi máy chưa cấu hình OpenAI API key) — vẫn tuân thủ 100%
    định dạng ``[...]`` tiếng Anh + ``_`` ngoài ``[...]``, quy tắc nhạc cụ solo và Validation Engine."""
    solos = list(selected_solo_instruments or [])
    clean_orig = clean_raw_lyrics_for_director(original_lyrics)
    line_info = line_profile(music_line)
    lang = (lyrics_lang or "").strip() or line_info["language"] or "Vietnamese"
    genre_label = " ".join((requested_genre or cover_style or "Ballad").split())
    prof = genre_profile(requested_genre, cover_style, description)

    # Tách thành các khổ tự nhiên từ lời gốc.
    paragraphs: list[list[str]] = []
    current: list[str] = []
    for ln in clean_orig.split("\n"):
        if not ln.strip():
            if current:
                paragraphs.append(current)
                current = []
        else:
            current.append(ln.strip())
    if current:
        paragraphs.append(current)
    if len(paragraphs) == 1 and len(paragraphs[0]) >= 8:
        all_lines = paragraphs[0]
        paragraphs = [all_lines[i: i + 4] for i in range(0, len(all_lines), 4)]
        if len(paragraphs) >= 2 and len(paragraphs[-1]) < 2:
            paragraphs[-2].extend(paragraphs.pop())

    # Phát hiện khổ điệp khúc nếu có khổ lặp lại.
    para_keys = ["\n".join(_word_tokens("\n".join(p))) for p in paragraphs]
    repeated_keys = {k for k in para_keys if k and para_keys.count(k) > 1}

    blocks: list[str] = []
    verse_idx = 0
    chorus_seen = 0
    solo_inserted = False
    solo_insert_after = max(0, len(paragraphs) - 2)

    for idx, para in enumerate(paragraphs):
        key = para_keys[idx]
        if idx == len(paragraphs) - 1 and len(paragraphs) >= 3:
            tag = "[Final Chorus - Emotional Climax, Full Arrangement]" if key in repeated_keys else "[Outro - Gentle Emotional Resolution]"
        elif key in repeated_keys or (len(paragraphs) >= 2 and idx == 1 and not repeated_keys):
            chorus_seen += 1
            tag = (
                "[Chorus - Expressive Lead Vocal, Memorable Hook]"
                if chorus_seen == 1
                else "[Chorus - Elevated Dynamic Lift, Full Arrangement]"
            )
        else:
            verse_idx += 1
            tag = (
                f"[Verse {verse_idx} - Intimate Expressive Vocal]"
                if verse_idx <= 2
                else "[Bridge - Dynamic Contrast, Deep Emotion]"
            )
        sung_block = "\n".join(
            _clean_sung_line_preserving_words(ln, underscore=underscore_formatting) for ln in para
        )
        blocks.append(f"{tag}\n{sung_block}")

        if solos and not solo_inserted and idx == solo_insert_after:
            for s_inst in solos:
                canon, _ = canonicalize_instrument(s_inst)
                blocks.append(f"[{canon} Solo - 8 Bars, Expressive Melodic Phrasing]")
            solo_inserted = True

    if solos and not solo_inserted:
        for s_inst in solos:
            canon, _ = canonicalize_instrument(s_inst)
            blocks.append(f"[{canon} Solo - 8 Bars, Expressive Melodic Phrasing]")

    structured = "\n\n".join(blocks)
    # Nếu bài quá dài gần chạm 5000 ký tự, rút gọn nhãn thành [Verse 1], [Chorus]...
    if len(structured) > MAX_LYRICS_CHARS:
        compact_blocks: list[str] = []
        for blk in blocks:
            first_ln, *rest = blk.split("\n")
            if "Solo" in first_ln:
                short_tag = re.sub(r"\s*-\s*.*\]$", "]", first_ln)
            else:
                short_tag = re.sub(r"\s*-\s*.*\]$", "]", first_ln)
            compact_blocks.append("\n".join([short_tag, *rest]))
        structured = "\n\n".join(compact_blocks)

    bpm_text = prof["bpm"] if prof else "76 BPM"
    groove_text = prof["groove"] if prof else "expressive organic rhythm and natural phrasing"
    music_text = prof["music"] if prof else "authentic genre instrumentation and rich harmonic voicings"
    mix_text = prof["mix"] if prof else "warm spacious vocal-forward production"

    voice_phrase = (
        "expressive male lead vocals"
        if vocal_gender == "male"
        else "expressive female lead vocals"
        if vocal_gender == "female"
        else "expressive male and female duet vocals"
        if vocal_gender == "duet"
        else "expressive natural lead vocals"
    )
    mood_hint = " ".join((description or "").split())[:140]
    solo_style_part = ""
    if solos:
        joined_solos = ", ".join(canonicalize_instrument(x)[0] for x in solos)
        solo_style_part = (
            f"featuring an expressive 8-bar {joined_solos} solo spotlight with soulful phrasing, "
        )

    style_parts = [
        f"{genre_label}",
        bpm_text,
        "4/4 time",
        groove_text,
        music_text,
        f"{solo_style_part}{voice_phrase}",
        f"sung in {lang} with clear articulate pronunciation",
        mood_hint if mood_hint else "emotional dynamic progression from intimate verse to soaring chorus",
        mix_text,
    ]
    style_text = ", ".join(p.strip(" ,") for p in style_parts if p and p.strip(" ,"))
    if len(style_text) > MAX_STYLE_CHARS:
        style_text = style_text[:MAX_STYLE_CHARS].rsplit(",", 1)[0].strip()

    # Xây dựng Exclude Styles động, không mâu thuẫn với thể loại hoặc nhạc cụ solo.
    base_excludes = [
        "instrumental only",
        "muffled vocals",
        "slurred pronunciation",
        "off-key singing",
        "muddy mix",
        "harsh clipping",
    ]
    gf = _fold_ascii(genre_label)
    if not any(x in gf for x in ("house", "edm", "remix", "vietmix", "dance")):
        base_excludes.extend(["edm festival drop", "hardstyle kick"])
    if "metal" not in gf and "rock" not in gf:
        base_excludes.append("heavy metal screaming")
    if not solos:
        base_excludes.extend(["extended instrumental break", "long intro", "long outro"])

    # Lọc an toàn để không bao giờ chứa từ khóa mâu thuẫn với nhạc cụ solo hoặc genre.
    safe_excludes: list[str] = []
    for item in base_excludes:
        if _fold_ascii(item) == gf:
            continue
        if solos and "solo" in item.casefold():
            continue
        safe_excludes.append(item)

    # Tính thông số Suno phù hợp thể loại.
    if "bolero" in gf:
        weirdness, style_inf, audio_inf = 20, 88, 52
    elif "blues" in gf or "rock" in gf:
        weirdness, style_inf, audio_inf = 35, 88, 48
    elif "r&b" in gf or "rnb" in gf or "soul" in gf:
        weirdness, style_inf, audio_inf = 35, 84, 48
    elif "jazz" in gf:
        weirdness, style_inf, audio_inf = 40, 84, 45
    elif any(x in gf for x in ("house", "remix", "vietmix", "edm")):
        weirdness, style_inf, audio_inf = 25, 85, 45
    else:
        weirdness, style_inf, audio_inf = 24, 82, 50

    bpm_num_match = re.search(r"(\d{2,3})", bpm_text)
    bpm_num = int(bpm_num_match.group(1)) if bpm_num_match else 76

    return {
        "status": "success",
        "analysis": {
            "theme": "Emotional vocal cover tailored to original lyrics",
            "mood": mood_hint or "Expressive and heartfelt",
            "emotional_progression": "Intimate opening verses building naturally toward an emotional chorus climax",
            "primary_genre": genre_label,
            "sub_genre": cover_style or "",
            "lyrical_hook": paragraphs[0][0] if paragraphs and paragraphs[0] else "",
            "arrangement_strategy": "Dynamic genre-authentic arrangement supporting clear vocal storytelling",
        },
        "music_direction": {
            "bpm": bpm_num,
            "key": "A minor",
            "time_signature": "4/4",
            "rhythmic_feel": groove_text,
            "vocal_description": voice_phrase,
            "primary_instruments": [x.strip() for x in music_text.split(",") if x.strip()],
            "selected_solo_instruments": solos,
            "solo_placement": "After chorus before final section" if solos else "",
            "solo_duration_bars": 8 if solos else None,
        },
        "suno": {
            "lyrics": structured,
            "style": style_text,
            "exclude_styles": ", ".join(safe_excludes),
            "vocal_gender": vocal_gender if vocal_gender in ("male", "female", "duet") else None,
            "weirdness": weirdness,
            "style_influence": style_inf,
            "audio_influence": audio_inf,
            "variety": COVER_SLIDERS["variety"],
            "duration_seconds": None,
            "max_mode": True,
            "personalize": None,
            "model": COVER_MODEL,
        },
        "validation": {
            "lyrics_character_count": len(structured),
            "style_character_count": len(style_text),
            "original_lyrics_preserved": True,
            "solo_requirements_satisfied": True,
            "warnings": [],
        },
    }


def _package_to_result(
    normalized_pkg: dict[str, Any],
    *,
    source: str,
    repair_attempts: int,
) -> MusicDirectorResult:
    suno = normalized_pkg["suno"]
    sliders = dict(COVER_SLIDERS)
    for key in ("weirdness", "style_influence", "variety", "audio_influence"):
        if suno.get(key) is not None:
            sliders[key] = int(suno[key])
    return MusicDirectorResult(
        lyrics=suno["lyrics"],
        style=suno["style"],
        exclude_styles=suno.get("exclude_styles") or "",
        vocal_gender=suno.get("vocal_gender") or "",
        sliders=sliders,
        max_mode=True if suno.get("max_mode") is None else bool(suno["max_mode"]),
        model=suno.get("model") or COVER_MODEL,
        source=source,
        repair_attempts=repair_attempts,
        raw_package=normalized_pkg,
    )


def _call_chat_completion(client: Any, *, model: str, messages: list[dict[str, str]]) -> str:
    """Gọi OpenAI Chat Completions (tự động thử lại không kèm response_format nếu proxy không hỗ trợ)."""
    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": 0.35,
        "max_tokens": 4096,
        "messages": messages,
    }
    try:
        resp = client.chat.completions.create(
            response_format={"type": "json_object"},
            **kwargs,
        )
    except Exception as exc:
        if "response_format" in str(exc).lower():
            resp = client.chat.completions.create(**kwargs)
        else:
            raise
    return (resp.choices[0].message.content or "").strip()


def run_music_director(
    *,
    original_lyrics: str,
    music_style: str,
    description: str = "",
    cover_style: str = "",
    vocal_gender: str = "",
    title: str = "",
    artist: str = "",
    featured_instrument: str = "",
    creative_instrument: bool = True,
    music_line: str = "",
    lyrics_lang: str = "",
    underscore_formatting: bool = True,
    api_config: Any = None,
    max_repairs: int = MAX_REPAIR_ATTEMPTS,
    log: Callable[[str], None] | None = None,
) -> MusicDirectorResult:
    """Chạy toàn bộ pipeline AI Music Director cho 1 bài hát độc lập."""

    def say(msg: str) -> None:
        if log:
            try:
                log(msg)
            except Exception:
                pass

    clean_orig = clean_raw_lyrics_for_director(original_lyrics)
    if not clean_orig.strip():
        raise MusicDirectorError("Lời bài hát gốc trống hoặc chỉ chứa nhãn trang trí.")

    # Kiểm tra sớm nếu bản thân lời gốc (chưa tính thẻ [...]) đã vượt trần 5.000 ký tự của Suno.
    bare_underscored = "\n".join(
        _clean_sung_line_preserving_words(ln, underscore=underscore_formatting) if ln.strip() else ""
        for ln in clean_orig.split("\n")
    )
    if len(clean_orig) > MAX_LYRICS_CHARS or len(bare_underscored) > MAX_LYRICS_CHARS:
        raise OriginalLyricsTooLongError(
            f"Lời bài hát gốc dài {max(len(clean_orig), len(bare_underscored))} ký tự, vượt giới hạn "
            f"{MAX_LYRICS_CHARS} ký tự của Suno — hãy rút bớt lời ở tab ① trước khi tạo Cover."
        )

    line_info = line_profile(music_line)
    resolved_lang = (lyrics_lang or "").strip() or line_info["language"] or "Vietnamese"
    requested_genre = " ".join((music_style or "").strip().split()) or (
        " ".join((cover_style or "").strip().split()) or "Vietnamese Ballad"
    )
    selected_solos = parse_solo_instruments(featured_instrument, creative_instrument=creative_instrument)
    explicit_gender = vocal_gender if vocal_gender in ("male", "female", "duet") else ""

    # Khi chưa cấu hình API key -> dùng gói cục bộ chuẩn hóa và vẫn đi qua đúng Validation Engine.
    if not api_config or not getattr(api_config, "api_key", None):
        say("AI Music Director: chưa cấu hình OpenAI API key — dùng bộ dựng cấu trúc cục bộ.")
        local_pkg = build_local_director_package(
            original_lyrics=clean_orig,
            requested_genre=requested_genre,
            cover_style=cover_style,
            music_line=music_line,
            lyrics_lang=resolved_lang,
            description=description,
            vocal_gender=explicit_gender,
            selected_solo_instruments=selected_solos,
            underscore_formatting=underscore_formatting,
        )
        local_pkg["suno"]["lyrics"] = postprocess_structured_lyrics(
            local_pkg["suno"]["lyrics"], underscore=underscore_formatting
        )
        ok, errs, norm_pkg = validate_director_package(
            local_pkg,
            original_lyrics=clean_orig,
            requested_genre=requested_genre,
            selected_solo_instruments=selected_solos,
            user_vocal_gender=explicit_gender,
            underscore_formatting=underscore_formatting,
        )
        if not ok:
            raise MusicDirectorError("Bộ dựng cục bộ không đạt kiểm tra Suno: " + "; ".join(errs))
        return _package_to_result(norm_pkg, source="fallback:no-key", repair_attempts=0)

    from openai import OpenAI

    # timeout=65s, max_retries=0 để 1 lượt proxy treo không giữ luồng suốt 4 phút;
    # vòng lặp thông minh bên dưới đã chủ động retry tối đa 3 lần kèm thông tin sửa lỗi.
    client = OpenAI(timeout=65.0, max_retries=0, **api_config.to_client_kwargs())
    model = getattr(api_config, "model", None) or _FALLBACK_MODEL
    if str(model).lower().startswith("claude"):
        model = _FALLBACK_MODEL

    orig_sung_lines = [ln for ln in clean_orig.split("\n") if ln.strip()]
    orig_word_count = len(_word_tokens(clean_orig))

    input_payload = {
        "song_title_context_only": (title or "").strip(),
        "original_artist_context_only": (artist or "").strip(),
        "original_lyrics": clean_orig,
        "original_sung_line_count": len(orig_sung_lines),
        "original_word_count": orig_word_count,
        "lyrics_language": resolved_lang,
        "requested_genre": requested_genre,
        "cover_style_hint": (cover_style or "").strip(),
        "genre_reference_profile": canonical_genre_context(music_style, cover_style, description),
        "music_line_market_hint": f"{line_info['label']} ({line_info['prompt_modifier']})",
        "mood": "",
        "target_audience": "",
        "vocal_gender": explicit_gender or "auto",
        "vocal_characteristics": "",
        "selected_solo_instruments": selected_solos,
        "solo_duration_bars": "4-8 bars" if selected_solos else None,
        "additional_instructions": (description or "").strip(),
        "underscore_formatting": bool(underscore_formatting),
        "preserve_existing_repeats_verbatim": True,
        "supported_settings": {
            "vocal_gender": True,
            "weirdness": True,
            "style_influence": True,
            "audio_influence": True,
            "variety": True,
            "duration_seconds": False,
            "max_mode": True,
            "personalize": False,
            "model": COVER_MODEL,
        },
        "limits": {
            "max_lyrics_chars": MAX_LYRICS_CHARS,
            "max_style_chars": MAX_STYLE_CHARS,
        },
    }

    solo_note = (
        f"solo {', '.join(selected_solos)} (4–8 bars)"
        if selected_solos
        else "không thêm solo nhạc cụ"
    )
    say(
        f"AI Music Director: đang phân tích bài hát với {model} "
        f"(thể loại: {requested_genre}, {solo_note})…"
    )

    last_raw_output = ""
    last_errors: list[str] = []
    total_attempts = 1 + max(0, int(max_repairs))

    for attempt_idx in range(total_attempts):
        is_repair = attempt_idx > 0
        user_msg = (
            build_director_user_prompt(input_payload)
            if not is_repair
            else build_repair_user_prompt(
                input_payload,
                last_raw_output,
                last_errors,
                attempt=attempt_idx,
                max_repairs=max_repairs,
            )
        )
        try:
            raw_output = _call_chat_completion(
                client,
                model=model,
                messages=[
                    {"role": "system", "content": MUSIC_DIRECTOR_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
            )
        except Exception as exc:
            safe_err = _safe_api_error(exc)
            last_errors = [f"Lỗi kết nối OpenAI API: {safe_err}"]
            say(f"AI Music Director: lỗi gọi API (lần {attempt_idx + 1}/{total_attempts}): {safe_err}")
            if attempt_idx + 1 >= total_attempts:
                break
            continue

        last_raw_output = raw_output
        try:
            parsed = _parse_json_object(raw_output)
        except Exception as exc:
            last_errors = [f"Phản hồi không phải JSON hợp lệ: {exc}"]
            say(
                f"AI Music Director: JSON lỗi ở lần {attempt_idx + 1}/{total_attempts} — "
                "yêu cầu AI xuất lại JSON chuẩn…"
            )
            continue

        # Hậu xử lý định dạng Suno trên suno.lyrics và suno.exclude_styles trước khi kiểm tra tất định.
        if isinstance(parsed.get("suno"), dict):
            if isinstance(parsed["suno"].get("lyrics"), str):
                formatted_lyrics = postprocess_structured_lyrics(
                    parsed["suno"]["lyrics"], underscore=underscore_formatting
                )
                parsed["suno"]["lyrics"] = reconcile_repeated_stanzas_with_original(
                    formatted_lyrics, clean_orig, underscore=underscore_formatting
                )
            if isinstance(parsed["suno"].get("exclude_styles"), str):
                parsed["suno"]["exclude_styles"] = _clean_exclude_styles(
                    parsed["suno"]["exclude_styles"]
                )

        ok, errs, normalized_pkg = validate_director_package(
            parsed,
            original_lyrics=clean_orig,
            requested_genre=requested_genre,
            selected_solo_instruments=selected_solos,
            user_vocal_gender=explicit_gender,
            underscore_formatting=underscore_formatting,
        )
        if ok:
            res = _package_to_result(
                normalized_pkg,
                source="ai",
                repair_attempts=attempt_idx,
            )
            tag_count = len(_extract_bracket_tags(res.lyrics))
            say(
                f"AI Music Director: hoàn tất ({tag_count} thẻ cấu trúc, "
                f"Lyrics {len(res.lyrics)}/{MAX_LYRICS_CHARS} ký tự, "
                f"Style {len(res.style)}/{MAX_STYLE_CHARS} ký tự"
                + (f", tự sửa {attempt_idx} lần" if attempt_idx else "")
                + ")."
            )
            return res

        last_errors = errs
        if attempt_idx + 1 < total_attempts:
            say(
                f"AI Music Director: phát hiện {len(errs)} điểm chưa đạt chuẩn Suno "
                f"({errs[0]}) — tự động yêu cầu AI sửa (lần {attempt_idx + 1}/{max_repairs})…"
            )

    joined_errors = "; ".join(last_errors[:5]) if last_errors else "không rõ nguyên nhân"
    raise MusicDirectorError(
        f"AI Music Director không tạo được dữ liệu hợp lệ sau {max_repairs} lần tự sửa: {joined_errors}"
    )
