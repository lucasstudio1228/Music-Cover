import { useEffect, useMemo, useRef, useState } from 'react';
import { useOpenProjectFolder, useProjectFolders } from '../../api/projects';
import {
  songAudioUrl,
  songLrcUrl, songSrtUrl,
  lyricsSrtUrl,
  useAlignAll,
  useAlignBetween,
  useAlignSong,
  useCoverSettings,
  useCoverSongs,
  useReorderSongs,
  useSaveLines,
  useShiftLines,
  useUpdateCoverSettings,
  useUpdateSong,
  type AlignStatus,
  type CoverSettings,
  type CoverSong,
  type CoverStyle,
  type LyricLine,
} from '../../api/cover';

const card = 'rounded-xl border border-white/5 bg-surface p-4';
const h2 = 'mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400';
const btn = 'rounded-lg bg-surface-2 px-3 py-1.5 text-sm text-gray-200 hover:bg-white/10 disabled:opacity-40';
const btnPrimary = 'rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-40';
const input = 'w-full rounded-lg border border-white/10 bg-surface-2 px-3 py-1.5 text-sm text-gray-100 outline-none focus:border-accent';

const STATUS: Record<AlignStatus, { label: string; cls: string }> = {
  none: { label: 'Chưa căn lời', cls: 'bg-gray-600/40 text-gray-300' },
  queued: { label: 'Đang chờ', cls: 'bg-yellow-600/30 text-yellow-300' },
  running: { label: 'AI đang căn…', cls: 'bg-blue-600/30 text-blue-300 animate-pulse' },
  done: { label: 'Đã căn', cls: 'bg-green-600/30 text-green-300' },
  edited: { label: 'Đã sửa tay', cls: 'bg-emerald-600/30 text-emerald-300' },
  failed: { label: 'Lỗi', cls: 'bg-red-600/30 text-red-300' },
};

function fmt(t: number) {
  if (!Number.isFinite(t)) return '0:00.0';
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${m}:${s.toFixed(1).padStart(4, '0')}`;
}

function parseTime(v: string): number | null {
  const s = v.trim();
  const m = s.match(/^(\d+):(\d+(?:\.\d+)?)$/);
  if (m) return Number(m[1]) * 60 + Number(m[2]);
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

const LANG_LABEL: Record<string, string> = {
  vi: '🇻🇳 Tiếng Việt (tiêu đề, mô tả, lời đều tiếng Việt)',
  en: '🇺🇸 English (everything in English)',
};
const STYLE_LABEL: Record<CoverStyle, string> = {
  ballad: 'Ballad (nhẹ nhàng, chậm)',
  remix: 'Remix (sôi động)',
  acoustic: 'Acoustic (mộc)',
  original: 'Giữ nguyên phong cách',
};
const short = (s: string) => s.split(' (')[0];

// ---------------------------------------------------------------- Cài đặt
function SettingsCard({ projectId }: { projectId: number }) {
  const { data } = useCoverSettings(projectId);
  const update = useUpdateCoverSettings(projectId);
  const [subtitle, setSubtitle] = useState('');
  useEffect(() => setSubtitle(data?.thumb_subtitle ?? ''), [data?.thumb_subtitle]);
  if (!data) return <div className={card}>Đang tải…</div>;
  const set = (patch: Partial<CoverSettings>) => update.mutate(patch);
  const eff = data.effective;
  const manual = [data.language, data.cover_style, data.thumb_subtitle.trim()].filter(Boolean).length;

  return (
    <div className={card}>
      <h2 className={h2}>Cài đặt video cover</h2>
      {eff && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg bg-accent/10 px-3 py-2 text-xs text-gray-300">
          <span>
            🤖 Tự theo thể loại project: <b className="text-gray-100">{eff.reason}</b>
            {' → '}{short(LANG_LABEL[eff.language])} · {short(STYLE_LABEL[eff.cover_style])}
          </span>
          <span className="flex-1" />
          {manual > 0 && (
            <button className={btn} disabled={update.isPending}
              title="Bỏ các lựa chọn tay — để tool tự đặt theo thể loại (tiện chạy tự động)"
              onClick={() => set({ language: '', cover_style: '', thumb_subtitle: '' })}>
              ↺ Đặt lại theo thể loại
            </button>
          )}
        </div>
      )}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <label className="space-y-1 text-sm text-gray-300">
          <span>Ngôn ngữ của video</span>
          <select className={input} value={data.language}
            onChange={(e) => set({ language: e.target.value as CoverSettings['language'] })}>
            <option value="">
              🤖 Theo dòng nhạc{eff ? ` — ${short(LANG_LABEL[eff.suggested.language])}` : ''}
            </option>
            <option value="vi">{LANG_LABEL.vi}</option>
            <option value="en">{LANG_LABEL.en}</option>
          </select>
        </label>
        <label className="space-y-1 text-sm text-gray-300">
          <span>Phong cách cover</span>
          <select className={input} value={data.cover_style}
            onChange={(e) => set({ cover_style: e.target.value as CoverSettings['cover_style'] })}>
            <option value="">
              🤖 Theo thể loại{eff ? ` — ${short(STYLE_LABEL[eff.suggested.cover_style])}` : ''}
            </option>
            {(Object.keys(STYLE_LABEL) as CoverStyle[]).map((k) => (
              <option key={k} value={k}>{STYLE_LABEL[k]}</option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-sm text-gray-300 md:col-span-2">
          <span>Dòng chữ phụ trên thumbnail (để trống = tool tự đặt theo thể loại)</span>
          <input className={input} value={subtitle}
            placeholder={eff ? `🤖 Tự đặt: ${eff.thumb_subtitle}` : 'VD: Tuyển Tập Ballad Cover Nhẹ Nhàng'}
            onChange={(e) => setSubtitle(e.target.value)}
            onBlur={() => subtitle !== data.thumb_subtitle && set({ thumb_subtitle: subtitle })} />
        </label>
        <label className="space-y-1 text-sm text-gray-300">
          <span>Độ chính xác AI căn lời</span>
          <select className={input} value={data.whisper_model}
            onChange={(e) => set({ whisper_model: e.target.value })}>
            <option value="large-v3">Cao nhất (chậm hơn) — khuyên dùng</option>
            <option value="large-v3-turbo">Nhanh, gần bằng cao nhất</option>
            <option value="medium">Trung bình</option>
            <option value="small">Nhanh nhất (kém chính xác)</option>
          </select>
        </label>
        <div className="space-y-1.5 text-sm text-gray-300">
          {([
            ['show_tracklist', 'Hiện danh sách bài (góc phải)'],
            ['show_lyrics', 'Hiện lời bài hát (3 dòng dưới)'],
            ['show_waveform', 'Hiện sóng âm nhảy theo nhạc (dưới lời)'],
          ] as const).map(([k, label]) => (
            <label key={k} className="flex items-center gap-2">
              <input type="checkbox" checked={data[k]} onChange={(e) => set({ [k]: e.target.checked })} />
              {label}
            </label>
          ))}
        </div>
      </div>
      {update.isError && <p className="mt-2 text-xs text-red-400">Không lưu được cài đặt.</p>}
    </div>
  );
}

// ---------------------------------------------------------------- Danh sách bài
/** Nút mở thư mục audio đã xong trên máy (File Explorer) để nghe. */
function OpenAudioFolderButton({ projectId }: { projectId: number }) {
  const { data } = useProjectFolders(projectId);
  const open = useOpenProjectFolder(projectId);
  if (!data?.audio) return null;
  return (
    <button className={btnPrimary} disabled={open.isPending}
      onClick={() => open.mutate('audio')}
      title={`Mở thư mục trên máy tính để nghe: ${data.audio}`}>
      📂 Mở thư mục nghe audio
    </button>
  );
}

function SongList({ projectId, songs, selected, onSelect, alignMsg, busy }: {
  projectId: number; songs: CoverSong[]; selected: number | null;
  onSelect: (id: number) => void; alignMsg: string; busy: boolean;
}) {
  const reorder = useReorderSongs(projectId);
  const alignAll = useAlignAll(projectId);
  const move = (i: number, d: number) => {
    const ids = songs.map((s) => s.id);
    const j = i + d;
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    reorder.mutate(ids);
  };
  const missing = songs.filter((s) => s.align_status === 'none' || s.align_status === 'failed').length;

  return (
    <div className={card}>
      <h2 className={h2}>Danh sách bài · thứ tự phát ({songs.length})</h2>
      {songs.length === 0 && (
        <p className="text-sm text-gray-400">
          Chưa có bài nào. Sang tab <b>① Tải nhạc gốc</b> hoặc <b>② Suno Cover</b>, bấm
          <b> ⬆ Nhập file cover</b> ở từng bài trước.
        </p>
      )}
      <ol className="space-y-1">
        {songs.map((s, i) => {
          const st = STATUS[s.align_status] ?? STATUS.none;
          return (
            <li key={s.id}
              className={`flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm ${
                selected === s.id ? 'bg-accent/20 ring-1 ring-accent' : 'hover:bg-white/5'}`}>
              <div className="flex flex-col">
                <button className="text-xs text-gray-400 hover:text-white disabled:opacity-20"
                  disabled={i === 0 || reorder.isPending} onClick={() => move(i, -1)} title="Lên">▲</button>
                <button className="text-xs text-gray-400 hover:text-white disabled:opacity-20"
                  disabled={i === songs.length - 1 || reorder.isPending} onClick={() => move(i, 1)} title="Xuống">▼</button>
              </div>
              <span className="w-6 text-right text-gray-500">{i + 1}.</span>
              <button className="min-w-0 flex-1 text-left" onClick={() => onSelect(s.id)}>
                <div className="truncate text-gray-100">{s.title}</div>
                <div className="truncate text-xs text-gray-500">
                  {s.artist || 'chưa ghi ca sĩ gốc'} · {fmt(s.duration_seconds).split('.')[0]}
                  {s.lines.length > 0 && ` · ${s.lines.length} câu`}
                  {s.quality && !s.quality.ok && s.lines.length > 0 &&
                    <span className="text-yellow-400"> · {s.quality.suspicious} câu nghi lệch</span>}
                </div>
              </button>
              <span className={`shrink-0 rounded px-2 py-0.5 text-xs ${st.cls}`}
                title={s.align_error ?? ''}>{st.label}</span>
            </li>
          );
        })}
      </ol>
      {songs.length > 0 && (
        <div className="mt-3 space-y-2 border-t border-white/5 pt-3">
          <div className="flex flex-wrap gap-2">
            <button className={btnPrimary} disabled={alignAll.isPending || missing === 0}
              onClick={() => alignAll.mutate(true)}>
              🤖 AI căn lời {missing > 0 ? `${missing} bài chưa căn` : '(đã căn hết)'}
            </button>
            <button className={btn} disabled={alignAll.isPending}
              onClick={() => {
                if (window.confirm('Căn lại TẤT CẢ bài? Những chỗ bạn đã sửa tay sẽ bị ghi đè.'))
                  alignAll.mutate(false);
              }}>Căn lại tất cả</button>
            <a className={btn} href={lyricsSrtUrl(projectId)}
              title="File phụ đề chỉ có lời bài hát, chạy theo từng câu nhạc của bản Mix mới nhất — kéo thả vào CapCut">
              ⬇ Lời cho CapCut (.srt)
            </a>
            <OpenAudioFolderButton projectId={projectId} />
          </div>
          {(busy || alignMsg) && (
            <p className={`text-xs ${busy ? 'text-blue-300' : 'text-gray-400'}`}>
              {busy && '⏳ '}{alignMsg}
            </p>
          )}
          <p className="text-xs text-gray-500">
            Mẹo: dán lời đúng của bài trước khi căn → AI chỉ cần dò thời gian, chính xác hơn nhiều.
            Mỗi bài mất khoảng 1–3 phút.
          </p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- Sửa 1 bài
function SongEditor({ projectId, song, busy }: { projectId: number; song: CoverSong; busy: boolean }) {
  const updateSong = useUpdateSong(projectId);
  const saveLines = useSaveLines(projectId);
  const shift = useShiftLines(projectId);
  const align = useAlignSong(projectId);
  const alignBetween = useAlignBetween(projectId);

  const [title, setTitle] = useState(song.title);
  const [artist, setArtist] = useState(song.artist);
  const [lyrics, setLyrics] = useState(song.lyrics_text);
  const [lines, setLines] = useState<LyricLine[]>(song.lines);
  const [pinned, setPinned] = useState<number[]>([]);
  const [selectedIdx, setSelectedIdx] = useState<number>(0);
  const [manualMode, setManualMode] = useState(false);
  const [manualIdx, setManualIdx] = useState(0);
  const [playRate, setPlayRate] = useState(1);
  const [alignErr, setAlignErr] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [now, setNow] = useState(0);
  const audio = useRef<HTMLAudioElement>(null);
  const rowRefs = useRef<(HTMLTableRowElement | null)[]>([]);
  const lastManualStampedRef = useRef<number | null>(null);

  // Đổi bài, hoặc server trả kết quả mới (AI căn xong) → nạp lại.
  useEffect(() => {
    setTitle(song.title);
    setArtist(song.artist);
    setLyrics(song.lyrics_text);
  }, [song.id, song.title, song.artist, song.lyrics_text]);
  const linesKey = JSON.stringify(song.lines);
  useEffect(() => {
    setLines(song.lines);
    setPinned([]);
    setSelectedIdx(0);
    setManualIdx(0);
    setManualMode(false);
    lastManualStampedRef.current = null;
    setAlignErr(null);
    setDirty(false);
  }, [song.id, linesKey]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (audio.current) audio.current.playbackRate = playRate;
  }, [playRate, song.id]);

  const current = useMemo(
    () => lines.findIndex((l) => now >= l.start && now < l.end), [lines, now]);
  useEffect(() => {
    const focusRow = manualMode ? manualIdx : current;
    if (focusRow >= 0 && (!audio.current?.paused || manualMode))
      rowRefs.current[focusRow]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [current, manualMode, manualIdx]);

  const seek = (t: number, play = true) => {
    const a = audio.current;
    if (!a) return;
    a.currentTime = Math.max(t - 0.5, 0);
    a.playbackRate = playRate;
    if (play) void a.play();
  };
  const seekDelta = (delta: number) => {
    const a = audio.current;
    if (!a) return;
    a.currentTime = Math.max(0, Math.min(a.duration || song.duration_seconds || 9999, a.currentTime + delta));
  };
  const edit = (i: number, patch: Partial<LyricLine>) => {
    setLines((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)));
    setAlignErr(null);
    setDirty(true);
  };
  const stampStart = (i: number) => {
    const t = Math.round((audio.current?.currentTime ?? 0) * 100) / 100;
    setLines((ls) => ls.map((l, j) => {
      if (j === i - 1 && l.end > t) {
        return { ...l, end: Math.max(Math.round((l.start + 0.25) * 100) / 100, Math.round((t - 0.05) * 100) / 100) };
      }
      if (j !== i) return l;
      const prevEnd = l.end;
      const nextStart = ls[i + 1]?.start;
      const estEnd = nextStart && nextStart > t + 0.8 && nextStart < t + 10
        ? Math.round((nextStart - 0.05) * 100) / 100
        : (prevEnd <= t + 0.3 || prevEnd > t + 12) ? Math.round((t + 3.5) * 100) / 100 : prevEnd;
      return { ...l, start: t, end: Math.max(estEnd, Math.round((t + 0.35) * 100) / 100) };
    }));
    setSelectedIdx(i);
    setAlignErr(null);
    setDirty(true);
  };
  const stampEnd = (i: number) => {
    const t = Math.round((audio.current?.currentTime ?? 0) * 100) / 100;
    edit(i, { end: Math.max(t, Math.round((lines[i].start + 0.3) * 100) / 100) });
    setSelectedIdx(i);
  };
  const startManualFrom = (idx: number, autoPlay = true) => {
    if (!lines.length) return;
    const clamped = Math.max(0, Math.min(lines.length - 1, idx));
    setSelectedIdx(clamped);
    setManualIdx(clamped);
    setManualMode(true);
    lastManualStampedRef.current = null;
    if (autoPlay && audio.current) {
      const refTime = clamped > 0 ? Math.max(0, lines[clamped - 1].end - 1.5) : Math.max(0, lines[0].start - 2);
      if (audio.current.paused) {
        audio.current.currentTime = refTime;
        audio.current.playbackRate = playRate;
        void audio.current.play();
      }
    }
  };
  const initManualLinesFromRawLyrics = () => {
    const raw = lyrics
      .split(/\r?\n/)
      .map((s) => s.replace(/\[\d{1,3}:\d{1,2}(?:[.:]\d{1,3})?\]/g, '').trim())
      .filter((s) => s && !/^\[[a-zA-Z]+:[^\]]*\]$/.test(s));
    if (!raw.length) return;
    const dur = Math.max(song.duration_seconds || 180, raw.length * 3);
    const step = dur / raw.length;
    const built: LyricLine[] = raw.map((text, idx) => ({
      text,
      start: Math.round(idx * step * 100) / 100,
      end: Math.round(Math.min(dur, (idx + 1) * step - 0.1) * 100) / 100,
    }));
    setLines(built);
    setPinned([]);
    setSelectedIdx(0);
    setManualIdx(0);
    setManualMode(true);
    setDirty(true);
    if (audio.current) {
      audio.current.currentTime = 0;
      audio.current.playbackRate = playRate;
      void audio.current.play();
    }
  };
  const manualTapNext = () => {
    if (!lines.length) return;
    const idx = Math.max(0, Math.min(lines.length - 1, manualIdx));
    const t = Math.round((audio.current?.currentTime ?? 0) * 100) / 100;
    const prevStamped = lastManualStampedRef.current;
    setLines((ls) => ls.map((l, j) => {
      if (j === idx - 1 && (prevStamped === idx - 1 || l.end > t)) {
        return {
          ...l,
          end: Math.max(Math.round((l.start + 0.25) * 100) / 100, Math.round((t - 0.05) * 100) / 100),
        };
      }
      if (j !== idx) return l;
      const nxt = ls[idx + 1]?.start;
      const defaultEnd = nxt && nxt > t + 0.8 && nxt < t + 10
        ? Math.round((nxt - 0.05) * 100) / 100
        : Math.round((t + 4.0) * 100) / 100;
      return { ...l, start: t, end: Math.max(defaultEnd, Math.round((t + 0.35) * 100) / 100) };
    }));
    lastManualStampedRef.current = idx;
    setDirty(true);
    setAlignErr(null);
    const nextIdx = Math.min(lines.length - 1, idx + 1);
    setManualIdx(nextIdx);
    setSelectedIdx(nextIdx);
  };
  const manualTapEndPrev = () => {
    if (!lines.length) return;
    const target = lastManualStampedRef.current ?? Math.max(0, manualIdx - 1);
    stampEnd(target);
  };
  const nudgeSingleLine = (idx: number, delta: number) => {
    if (idx < 0 || idx >= lines.length) return;
    setLines((ls) => ls.map((l, j) => {
      if (j !== idx) return l;
      const st = Math.max(0, Math.round((l.start + delta) * 100) / 100);
      const en = Math.max(Math.round((st + 0.25) * 100) / 100, Math.round((l.end + delta) * 100) / 100);
      return { ...l, start: st, end: en };
    }));
    setDirty(true);
  };
  const nudgeFromHere = (fromIdx: number, delta: number) => {
    if (fromIdx < 0 || fromIdx >= lines.length) return;
    setLines((ls) => ls.map((l, j) => {
      if (j < fromIdx) return l;
      const st = Math.max(0, Math.round((l.start + delta) * 100) / 100);
      const en = Math.max(Math.round((st + 0.25) * 100) / 100, Math.round((l.end + delta) * 100) / 100);
      return { ...l, start: st, end: en };
    }));
    setDirty(true);
  };
  const evenSpaceBetweenAnchors = () => {
    if (lines.length < 3) return;
    const anchors = Array.from(new Set([0, ...pinned, lines.length - 1])).sort((a, b) => a - b);
    setLines((ls) => {
      const next = ls.map((x) => ({ ...x }));
      for (let a = 0; a < anchors.length - 1; a++) {
        const leftIdx = anchors[a];
        const rightIdx = anchors[a + 1];
        if (rightIdx - leftIdx <= 1) continue;
        const spanLo = next[leftIdx].end;
        const spanHi = next[rightIdx].start;
        if (spanHi <= spanLo + 0.2) continue;
        const mids = Array.from({ length: rightIdx - leftIdx - 1 }, (_, k) => leftIdx + 1 + k);
        const weights = mids.map((k) => Math.max(1, next[k].text.trim().split(/\s+/).length));
        const totalW = weights.reduce((s, w) => s + w, 0);
        let acc = 0;
        mids.forEach((k, idx) => {
          const t0 = spanLo + ((spanHi - spanLo) * acc) / totalW;
          acc += weights[idx];
          const t1 = spanLo + ((spanHi - spanLo) * acc) / totalW;
          next[k] = {
            ...next[k],
            start: Math.round(t0 * 100) / 100,
            end: Math.round(Math.max(t0 + 0.25, t1 - 0.05) * 100) / 100,
          };
        });
      }
      return next;
    });
    setDirty(true);
  };
  const insertLineAfter = (idx: number) => {
    setLines((ls) => {
      const base = ls[idx] ?? { text: '', start: 0, end: 2 };
      const nextStart = ls[idx + 1]?.start;
      const st = Math.round(base.end * 100) / 100;
      const en = nextStart && nextStart > st + 0.4
        ? Math.round(nextStart * 100) / 100
        : Math.round((st + 2.5) * 100) / 100;
      const copy = [...ls];
      copy.splice(idx + 1, 0, { text: 'Câu hát mới…', start: st, end: en });
      return copy;
    });
    setPinned((prev) => prev.map((p) => (p > idx ? p + 1 : p)));
    setSelectedIdx(idx + 1);
    setDirty(true);
  };
  const removeLineAt = (idx: number) => {
    if (lines.length <= 1) return;
    setLines((ls) => ls.filter((_, j) => j !== idx));
    setPinned((prev) => prev.filter((p) => p !== idx).map((p) => (p > idx ? p - 1 : p)));
    setSelectedIdx((prev) => Math.max(0, Math.min(lines.length - 2, prev)));
    setManualIdx((prev) => Math.max(0, Math.min(lines.length - 2, prev)));
    setDirty(true);
  };
  const togglePin = (i: number) => {
    if (i === 0 || i === lines.length - 1) return;
    setPinned((prev) => (prev.includes(i) ? prev.filter((x) => x !== i) : [...prev, i]));
  };

  useEffect(() => {
    if (!manualMode) return;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (e.code === 'Space') {
        e.preventDefault();
        manualTapNext();
      } else if (e.key === 'e' || e.key === 'E') {
        e.preventDefault();
        manualTapEndPrev();
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        seekDelta(-2);
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        seekDelta(2);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setManualIdx((p) => Math.max(0, p - 1));
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        setManualIdx((p) => Math.min(Math.max(0, lines.length - 1), p + 1));
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  const infoDirty = title !== song.title || artist !== song.artist;
  const lyricsDirty = lyrics !== song.lyrics_text;
  const isWorking = song.align_status === 'queued' || song.align_status === 'running';

  return (
    <div className={`${card} space-y-4`}>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <label className="space-y-1 text-sm text-gray-300">
          <span>Tên bài (hiện trên video &amp; mô tả YouTube)</span>
          <input className={input} value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label className="space-y-1 text-sm text-gray-300">
          <span>Ca sĩ / tác giả gốc (không bắt buộc)</span>
          <input className={input} value={artist} onChange={(e) => setArtist(e.target.value)} />
        </label>
      </div>
      {infoDirty && (
        <button className={btnPrimary} disabled={updateSong.isPending}
          onClick={() => updateSong.mutate({ id: song.id, title, artist })}>Lưu tên bài</button>
      )}

      <audio ref={audio} src={songAudioUrl(song.id, String(song.tempo_factor ?? ''))} controls preload="metadata" className="w-full"
        onTimeUpdate={(e) => setNow(e.currentTarget.currentTime)} />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
        {/* Lời gốc */}
        <div className="space-y-2 xl:col-span-2">
          <div className="text-sm text-gray-300">
            Lời bài hát — mỗi câu 1 dòng
            <span className="text-xs text-gray-500"> ({song.lyric_line_count} dòng · có thể dán cả file .lrc)</span>
          </div>
          <textarea className={`${input} h-80 font-mono text-xs leading-5`} value={lyrics}
            placeholder={'Dán lời bài hát vào đây…\nMỗi câu hát 1 dòng.\nĐể trống thì AI tự nghe và chép lời (kém chính xác hơn).'}
            onChange={(e) => setLyrics(e.target.value)} />
          <div className="flex flex-wrap gap-2">
            <button className={btn} disabled={!lyricsDirty || updateSong.isPending}
              onClick={() => updateSong.mutate({ id: song.id, lyrics_text: lyrics })}>
              Lưu lời
            </button>
            <button className={btnPrimary} disabled={isWorking || align.isPending || updateSong.isPending}
              onClick={async () => {
                if (lines.length && !window.confirm('Căn lại bài này? Mốc thời gian hiện tại sẽ bị thay.')) return;
                if (lyricsDirty) await updateSong.mutateAsync({ id: song.id, lyrics_text: lyrics });
                align.mutate(song.id);
              }}>
              {isWorking ? '⏳ AI đang căn…' : '🤖 AI căn lời bài này'}
            </button>
          </div>
          {song.align_status === 'failed' && song.align_error && (
            <p className="text-xs text-red-400">Lỗi: {song.align_error}</p>
          )}
          {busy && !isWorking && <p className="text-xs text-gray-500">AI đang bận bài khác, bài này sẽ xếp hàng.</p>}
        </div>

        {/* Bảng mốc thời gian */}
        <div className="space-y-2 xl:col-span-3">
          <div className="flex flex-wrap items-center gap-2 text-sm text-gray-300">
            <span>Rà lời theo nhạc ({lines.length} câu)</span>
            <button
              type="button"
              onClick={() => {
                if (!lines.length) {
                  initManualLinesFromRawLyrics();
                } else if (manualMode) {
                  setManualMode(false);
                } else {
                  startManualFrom(selectedIdx, false);
                }
              }}
              className={`rounded-lg px-2.5 py-1 text-xs font-medium transition ${
                manualMode
                  ? 'border border-cyan-400 bg-cyan-500/25 text-cyan-100'
                  : 'border border-cyan-400/40 bg-cyan-950/40 text-cyan-200 hover:bg-cyan-900/50'
              }`}
              title="Bật bảng gõ nhịp thủ công theo từng câu (dùng chuột hoặc phím Space khi nghe nhạc)">
              {manualMode ? '✋ Đóng chế độ căn thủ công' : '🎹 Căn lời thủ công'}
            </button>
            <span className="flex-1" />
            <span className="text-xs text-gray-500">Cả bài lệch đều:</span>
            {[-0.5, -0.2, 0.2, 0.5].map((d) => (
              <button key={d} className={btn} disabled={!lines.length || dirty || shift.isPending}
                title={d < 0 ? 'Lời hiện SỚM hơn' : 'Lời hiện MUỘN hơn'}
                onClick={() => shift.mutate({ id: song.id, seconds: d })}>
                {d > 0 ? `+${d}` : d}s
              </button>
            ))}
            {lines.length > 0 && <a className={btn} href={songLrcUrl(song.id)} target="_blank" rel="noreferrer">⬇ .lrc</a>}
            {lines.length > 0 && <a className={btn} href={songSrtUrl(song.id)} target="_blank" rel="noreferrer"
              title="File lời của riêng bài này cho CapCut — chỉ có lời, khớp thời gian bản cover">⬇ .srt</a>}
          </div>

          {manualMode && lines.length > 0 && (
            <div className="space-y-2 rounded-xl border border-cyan-400/40 bg-cyan-950/25 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-cyan-200">
                <span>
                  🎹 <b>Chế độ căn thủ công</b> · Nhạc đang ở <b className="font-mono text-white">{fmt(now)}</b>
                  {' · '}Đang chờ chấm <b>câu #{manualIdx + 1}/{lines.length}</b>
                </span>
                <div className="flex items-center gap-1">
                  <span className="text-gray-400">Tốc độ nghe:</span>
                  {[0.75, 1, 1.25, 1.5].map((r) => (
                    <button key={r} type="button"
                      onClick={() => setPlayRate(r)}
                      className={`rounded px-1.5 py-0.5 text-[11px] ${
                        playRate === r ? 'bg-cyan-500/40 font-semibold text-white' : 'bg-white/5 text-gray-300 hover:bg-white/10'
                      }`}>
                      {r}×
                    </button>
                  ))}
                </div>
              </div>
              <div className="rounded-lg bg-black/30 px-3 py-2 text-sm">
                {manualIdx > 0 && (
                  <div className="truncate text-xs text-gray-500">
                    ↑ Câu #{manualIdx}: {lines[manualIdx - 1]?.text} ({fmt(lines[manualIdx - 1]?.start ?? 0)} → {fmt(lines[manualIdx - 1]?.end ?? 0)})
                  </div>
                )}
                <div className="mt-0.5 font-semibold text-cyan-100">
                  👉 Câu #{manualIdx + 1}: {lines[manualIdx]?.text}
                </div>
                {manualIdx + 1 < lines.length && (
                  <div className="mt-0.5 truncate text-xs text-gray-400">
                    ↓ Tiếp theo #{manualIdx + 2}: {lines[manualIdx + 1]?.text}
                  </div>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <button type="button" onClick={manualTapNext}
                  className="rounded-lg bg-cyan-500 px-3 py-1.5 text-xs font-semibold text-slate-950 hover:bg-cyan-400">
                  👇 Chấm BẮT ĐẦU câu #{manualIdx + 1} &amp; qua câu kế (Space)
                </button>
                <button type="button" onClick={manualTapEndPrev}
                  className="rounded-lg border border-cyan-400/40 bg-cyan-900/40 px-2.5 py-1.5 text-xs text-cyan-100 hover:bg-cyan-800/50"
                  title="Ngắt giờ kết thúc của câu vừa hát (tiện ngắt trước đoạn nhạc dạo)">
                  ⏹ Ngắt KẾT THÚC câu vừa hát (Phím E)
                </button>
                <button type="button" className={btn}
                  onClick={() => {
                    const a = audio.current;
                    if (!a) return;
                    if (a.paused) void a.play();
                    else a.pause();
                  }}>
                  ⏯ Phát / Dừng
                </button>
                <button type="button" className={btn} onClick={() => seekDelta(-3)} title="Tua lùi 3 giây">⏪ -3s</button>
                <button type="button" className={btn} onClick={() => seekDelta(3)} title="Tua tới 3 giây">⏩ +3s</button>
                <button type="button" className={btn}
                  disabled={manualIdx <= 0}
                  onClick={() => { const p = Math.max(0, manualIdx - 1); setManualIdx(p); setSelectedIdx(p); }}>
                  ⏮ Câu trước
                </button>
                <button type="button" className={btn}
                  disabled={manualIdx >= lines.length - 1}
                  onClick={() => { const n = Math.min(lines.length - 1, manualIdx + 1); setManualIdx(n); setSelectedIdx(n); }}>
                  ⏭ Bỏ qua câu
                </button>
              </div>
              <p className="text-[11px] text-cyan-200/70">
                Mẹo: Bấm nút <b>🎹</b> ở bất kỳ câu nào bị lệch giữa bài để nhảy tới ngay trước câu đó rồi bấm <b>Space</b> theo ca sĩ hát. Chấm xong nhớ bấm <b>Lưu mốc thời gian</b>.
              </p>
            </div>
          )}

          {lines.length === 0 ? (
            <div className="space-y-2 rounded-lg bg-surface-2 p-4 text-sm text-gray-400">
              <p>Chưa có mốc thời gian. Dán lời rồi bấm <b>🤖 AI căn lời bài này</b>, hoặc bấm <b>🎹 Căn lời thủ công</b> để tự gõ nhịp từng câu.</p>
            </div>
          ) : (
            <>
              <div className="max-h-96 overflow-y-auto rounded-lg border border-white/5">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-surface-2 text-xs text-gray-400">
                    <tr><th className="w-8 p-1">#</th><th className="w-20 p-1">Bắt đầu</th><th className="w-20 p-1">Kết thúc</th><th className="p-1 text-left">Câu hát</th><th className="w-36 p-1">Thủ công</th></tr>
                  </thead>
                  <tbody>
                    {lines.map((l, i) => {
                      const bad = l.end <= l.start || (l.end - l.start) < 0.35 || (i > 0 && l.start < lines[i - 1].start);
                      const isEdge = lines.length >= 3 && (i === 0 || i === lines.length - 1);
                      const isPinned = isEdge || pinned.includes(i);
                      const isManualTarget = manualMode && i === manualIdx;
                      const isSelected = i === selectedIdx;
                      return (
                        <tr key={i} ref={(el) => { rowRefs.current[i] = el; }}
                          onClick={() => { setSelectedIdx(i); if (manualMode) setManualIdx(i); }}
                          className={
                            isManualTarget ? 'bg-cyan-500/25 ring-1 ring-inset ring-cyan-400'
                              : i === current ? 'bg-accent/25'
                              : bad ? 'bg-red-900/30'
                              : isSelected ? 'bg-white/10'
                              : isPinned ? 'bg-amber-500/10'
                              : 'odd:bg-white/[0.02]'
                          }>
                          <td className="p-1 text-center whitespace-nowrap">
                            <button title={`Nghe từ câu #${i + 1}`} className="text-xs text-gray-400 hover:text-white"
                              onClick={(e) => { e.stopPropagation(); setSelectedIdx(i); seek(l.start); }}>
                              ▶{i + 1}
                            </button>
                          </td>
                          <td className="p-1">
                            <TimeInput value={l.start} onChange={(v) => edit(i, { start: v })} />
                          </td>
                          <td className="p-1">
                            <TimeInput value={l.end} onChange={(v) => edit(i, { end: v })} />
                          </td>
                          <td className="p-1">
                            <div className="flex items-center gap-1.5">
                              {lines.length >= 3 && (
                                <button
                                  type="button"
                                  disabled={isEdge}
                                  onClick={(e) => { e.stopPropagation(); togglePin(i); }}
                                  title={isEdge
                                    ? (i === 0 ? 'Câu đầu luôn được giữ cố định khi AI căn lại phần còn lại'
                                               : 'Câu cuối luôn được giữ cố định khi AI căn lại phần còn lại')
                                    : isPinned ? 'Bỏ ghim câu mốc này' : 'Ghim thêm câu này làm mốc cố định cho AI / chia đều'}
                                  className={`shrink-0 rounded px-1 text-[11px] ${
                                    isPinned ? 'bg-amber-500/25 text-amber-200' : 'text-gray-600 hover:text-gray-300'
                                  }`}>
                                  {i === 0 ? '📌Đầu' : i === lines.length - 1 ? '📌Cuối' : '📌'}
                                </button>
                              )}
                              <input className="w-full bg-transparent px-1 text-gray-100 outline-none focus:bg-surface-2"
                                value={l.text} onChange={(e) => edit(i, { text: e.target.value })} />
                            </div>
                          </td>
                          <td className="p-1 text-center">
                            <div className="flex items-center justify-center gap-1">
                              <button title="Đặt giờ Bắt đầu = vị trí đang nghe"
                                className="rounded bg-white/5 px-1.5 py-0.5 text-xs text-gray-200 hover:bg-white/15 hover:text-white"
                                onClick={(e) => { e.stopPropagation(); stampStart(i); }}>⏱đầu</button>
                              <button title="Đặt giờ Kết thúc = vị trí đang nghe"
                                className="rounded bg-white/5 px-1.5 py-0.5 text-xs text-gray-300 hover:bg-white/15 hover:text-white"
                                onClick={(e) => { e.stopPropagation(); stampEnd(i); }}>⏹cuối</button>
                              <button title="Bật gõ nhịp thủ công bắt đầu ngay từ câu này"
                                className="rounded bg-cyan-500/15 px-1.5 py-0.5 text-xs text-cyan-200 hover:bg-cyan-500/30"
                                onClick={(e) => { e.stopPropagation(); startManualFrom(i, true); }}>🎹</button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Thanh nút thủ công chỉnh nhanh câu đang chọn ở giữa bài */}
              {lines[selectedIdx] && (
                <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-white/10 bg-surface-2 px-2.5 py-2 text-xs text-gray-300">
                  <span className="font-medium text-white">🛠 Câu #{selectedIdx + 1}:</span>
                  <span className="text-gray-400">Riêng câu này:</span>
                  {[-0.5, -0.2, 0.2, 0.5].map((d) => (
                    <button key={`one-${d}`} type="button"
                      onClick={() => nudgeSingleLine(selectedIdx, d)}
                      className="rounded bg-white/5 px-1.5 py-0.5 text-gray-200 hover:bg-white/15">
                      {d > 0 ? `+${d}s` : `${d}s`}
                    </button>
                  ))}
                  <span className="ml-1 text-gray-400">Từ câu #{selectedIdx + 1} → cuối:</span>
                  {[-1, -0.5, -0.2, 0.2, 0.5, 1].map((d) => (
                    <button key={`tail-${d}`} type="button"
                      onClick={() => nudgeFromHere(selectedIdx, d)}
                      title={`Dịch toàn bộ các câu từ câu #${selectedIdx + 1} đến hết bài thêm ${d > 0 ? `+${d}` : d} giây`}
                      className="rounded bg-violet-500/15 px-1.5 py-0.5 text-violet-200 hover:bg-violet-500/30">
                      {d > 0 ? `+${d}s` : `${d}s`}
                    </button>
                  ))}
                  <span className="flex-1" />
                  <button type="button"
                    onClick={() => startManualFrom(selectedIdx, true)}
                    title="Tua tới ngay trước câu này và mở chế độ gõ nhịp thủ công"
                    className="rounded bg-cyan-500/20 px-2 py-0.5 text-cyan-200 hover:bg-cyan-500/35">
                    🎹 Gõ nhịp từ câu #{selectedIdx + 1}
                  </button>
                  {lines.length >= 3 && (
                    <button type="button"
                      onClick={evenSpaceBetweenAnchors}
                      title="Chia đều thủ công thời gian các câu nằm giữa các mốc 📌 (không cần chờ AI)"
                      className="rounded bg-amber-500/15 px-2 py-0.5 text-amber-200 hover:bg-amber-500/30">
                      📏 Chia đều giữa các 📌
                    </button>
                  )}
                  <button type="button"
                    onClick={() => insertLineAfter(selectedIdx)}
                    title="Chèn thêm 1 câu hát ngay bên dưới câu này"
                    className="rounded bg-emerald-500/15 px-2 py-0.5 text-emerald-200 hover:bg-emerald-500/30">
                    ➕ Thêm câu
                  </button>
                  {lines.length > 1 && (
                    <button type="button"
                      onClick={() => removeLineAt(selectedIdx)}
                      title="Xoá câu này (ví dụ câu lặp mà Suno không hát)"
                      className="rounded bg-red-500/15 px-2 py-0.5 text-red-200 hover:bg-red-500/30">
                      🗑 Xoá câu
                    </button>
                  )}
                </div>
              )}
            </>
          )}
          {lines.length > 0 && (
            <div className="space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <button className={btnPrimary} disabled={!dirty || saveLines.isPending}
                  onClick={() => saveLines.mutate({ id: song.id, lines })}>
                  {saveLines.isPending ? 'Đang lưu…' : 'Lưu mốc thời gian'}
                </button>
                {lines.length >= 3 && (
                  <button
                    className="rounded-lg border border-amber-400/40 bg-amber-500/15 px-3 py-1.5 text-sm font-medium text-amber-100 hover:bg-amber-500/25 disabled:opacity-40"
                    disabled={isWorking || alignBetween.isPending}
                    title="Giữ cố định mốc câu đầu & câu cuối bạn vừa chỉnh (cùng câu gắn 📌), dùng AI căn lại toàn bộ các câu còn lại ở giữa"
                    onClick={() => {
                      setAlignErr(null);
                      const anchors = Array.from(new Set([0, ...pinned, lines.length - 1])).sort((a, b) => a - b);
                      alignBetween.mutate(
                        { id: song.id, lines, anchor_indices: anchors },
                        {
                          onError: (e: unknown) => {
                            const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
                              || (e instanceof Error ? e.message : 'Không thể căn lại phần giữa.');
                            setAlignErr(msg);
                          },
                        },
                      );
                    }}>
                    {isWorking || alignBetween.isPending
                      ? '⏳ AI đang căn lại phần còn lại…'
                      : '🎯 Giữ câu đầu & cuối — AI căn lại phần còn lại'}
                  </button>
                )}
                {dirty && <button className={btn} onClick={() => { setLines(song.lines); setPinned([]); setDirty(false); }}>Huỷ sửa</button>}
              </div>
              {alignErr && <p className="text-xs text-red-400">{alignErr}</p>}
              <p className="text-xs text-gray-500">
                Căn lời bị lệch? Bạn chỉ cần chỉnh đúng giờ <b>📌Đầu</b> (câu đầu) và <b>📌Cuối</b> (câu cuối) bằng ô giờ hoặc nút <b>⏱đầu / ⏹cuối</b>, rồi bấm <b>🎯 Giữ câu đầu &amp; cuối — AI căn lại phần còn lại</b> (có thể bấm 📌 ở câu bất kỳ giữa bài để khóa thêm mốc).
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function TimeInput({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  const [text, setText] = useState(fmt(value));
  const [focused, setFocused] = useState(false);
  useEffect(() => {
    if (!focused) setText(fmt(value));
  }, [value, focused]);
  return (
    <input className="w-20 bg-transparent px-1 text-center font-mono text-xs text-gray-200 outline-none focus:bg-surface-2"
      value={text}
      onFocus={() => setFocused(true)}
      onChange={(e) => {
        const raw = e.target.value;
        setText(raw);
        const v = parseTime(raw);
        if (v !== null && v >= 0 && Math.abs(v - value) > 0.001) {
          onChange(Math.round(v * 100) / 100);
        }
      }}
      onBlur={() => {
        setFocused(false);
        const v = parseTime(text);
        if (v === null || v < 0) setText(fmt(value));
        else {
          const rounded = Math.round(v * 100) / 100;
          setText(fmt(rounded));
          if (Math.abs(rounded - value) > 0.001) onChange(rounded);
        }
      }} />
  );
}

// ---------------------------------------------------------------- Panel
export default function CoverPanel({ projectId }: { projectId: number }) {
  const { data, isLoading } = useCoverSongs(projectId);
  const songs = data?.songs ?? [];
  const [selected, setSelected] = useState<number | null>(null);
  useEffect(() => {
    if (songs.length && !songs.some((s) => s.id === selected)) setSelected(songs[0].id);
  }, [songs, selected]);
  const song = songs.find((s) => s.id === selected) ?? null;

  if (isLoading) return <p className="text-gray-400">Đang tải…</p>;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <SongList projectId={projectId} songs={songs} selected={selected} onSelect={setSelected}
          alignMsg={data?.align.message ?? ''} busy={!!data?.align.busy} />
        <SettingsCard projectId={projectId} />
      </div>
      {song && <SongEditor key={song.id} projectId={projectId} song={song} busy={!!data?.align.busy} />}
    </div>
  );
}
