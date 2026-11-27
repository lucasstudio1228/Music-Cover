import { useState } from 'react';
import type {
  CastMode, FootageSceneMode, IntroMode, MixSetCreate, Project, ProjectCreate, ProjectKind,
} from '../../types';
import { useBatchStyles } from '../../api/projects';
import { useChannelMappings, useChannelLooks, type ChannelMapping } from '../../api/youtube';
import MusicLineSelect from '../shared/MusicLineSelect';

interface Props {
  open: boolean;
  initial?: Project;
  saving?: boolean;
  /** Đang gửi yêu cầu tạo lô (AI sinh ý tưởng có thể mất vài giây). */
  batchSaving?: boolean;
  batchError?: string | null;
  /** Project tạo tay luôn dừng ở trạng thái sẵn sàng; Mix Set dùng endpoint tự động riêng. */
  /** ownCovers = project «từ bài cover có sẵn» → mở thẳng chỗ kéo thả file cover. */
  onSubmit: (data: ProjectCreate, opts: { autoRun: boolean; ownCovers?: boolean }) => void;
  /** Bỏ qua → không hiện chế độ Mix Set (vd khi đang sửa project).
   *  autoRun=false → «Chỉ tạo, tôi tự chạy»: tạo sẵn project + bài, không chạy gì. */
  onSubmitBatch?: (data: MixSetCreate, opts: { autoRun: boolean }) => void;
  onClose: () => void;
}

/** File danh sách bài nhận được (Word, Excel, chữ thường, CSV). */
const LIST_EXTS = ['.txt', '.docx', '.doc', '.xlsx', '.xlsm', '.xls', '.csv'];
const LIST_ACCEPT = LIST_EXTS.join(',');

const norm = (s: string) => s.trim().toLowerCase();
const genreNorm = (s: string) => {
  const value = norm(s).replace(/[-_]+/g, ' ').replace(/\s+/g, ' ');
  if (['mix việt', 'mix viet', 'viet mix'].includes(value)) return 'vietmix';
  if (['rnb', 'rhythm and blues'].includes(value)) return 'r&b';
  if (value === 'lo fi') return 'lofi';
  return value;
};
const CUSTOM = '__custom__';

/** Catalog thể loại chuẩn của tool Cover. Lưu vào music_style — đầu vào
 *  profile BPM/groove/harmony/arrangement, prompt ảnh/clip và gợi ý kênh. */
const COVER_GENRES = [
  'Ballad', 'Pop', 'R&B', 'Rock', 'Acoustic', 'Jazz', 'Blues', 'Lofi',
  'House', 'Deep House', 'Future House', 'Tropical House',
  'Vietmix', 'Dance Remix',
];

/** Chọn thể loại: danh sách cố định + thể loại trong ánh xạ kênh + «Khác (tự nhập)». */
function GenrePicker({
  value,
  onChange,
  extra,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  extra: string[];
  className: string;
}) {
  const known = new Set(COVER_GENRES.map(genreNorm));
  const fromChannels = [...new Set(extra.filter((v) => v.trim() && !known.has(genreNorm(v))))];
  const listed = new Set([...known, ...fromChannels.map(genreNorm)]);
  const [custom, setCustom] = useState(Boolean(value) && !listed.has(genreNorm(value)));
  const match = [...COVER_GENRES, ...fromChannels].find((g) => genreNorm(g) === genreNorm(value));
  return (
    <>
      <select
        className={className}
        value={custom ? CUSTOM : (match ?? '')}
        onChange={(e) => {
          if (e.target.value === CUSTOM) {
            setCustom(true);
            onChange('');
          } else {
            setCustom(false);
            onChange(e.target.value);
          }
        }}
      >
        <option value="">— chọn thể loại —</option>
        {COVER_GENRES.map((g) => (
          <option key={g} value={g}>{g}</option>
        ))}
        {fromChannels.length > 0 && (
          <optgroup label="Từ kênh đã cấu hình">
            {fromChannels.map((v) => (
              <option key={v} value={v}>{v}</option>
            ))}
          </optgroup>
        )}
        <option value={CUSTOM}>Khác (tự nhập)…</option>
      </select>
      {custom && (
        <input
          className={`${className} mt-2`}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="vd: Bolero, EDM, Acoustic, Indie…"
          autoFocus
        />
      )}
    </>
  );
}

/** Kênh tự chọn cho project chưa chọn kênh — giống backend (match_channel):
 *  cùng dòng nhạc + cùng thể loại → cùng dòng nhạc, kênh chưa ghi thể loại → cùng
 *  dòng nhạc → kênh chưa ghi dòng nhạc + cùng thể loại. Chưa chọn dòng nhạc → chỉ
 *  theo thể loại. Nhiều kênh cùng khớp → kênh thêm sau thắng. */
function autoPickChannel(
  list: ChannelMapping[],
  instrument: string,
  style: string,
  line: string
): ChannelMapping | undefined {
  const rows = [...list].sort((a, b) => b.id - a.id);
  const sty = norm(style);
  const ln = norm(line);
  if (instrument.trim()) {
    // Project cũ (tool thiền) có nhạc cụ: khớp nhạc cụ + thể loại như trước.
    return sty
      ? rows.find((m) => norm(m.music_style) === sty && norm(m.instrument) === norm(instrument))
      : undefined;
  }
  if (ln) {
    const same = rows.filter((m) => norm(m.music_line ?? '') === ln);
    return (
      (sty ? same.find((m) => norm(m.music_style) === sty) : undefined) ??
      same.find((m) => !norm(m.music_style)) ??
      same[0] ??
      (sty
        ? rows.find((m) => !norm(m.music_line ?? '') && norm(m.music_style) === sty)
        : undefined)
    );
  }
  return sty ? rows.find((m) => norm(m.music_style) === sty) : undefined;
}

export default function ProjectFormModal({
  open,
  initial,
  saving,
  batchSaving,
  batchError,
  onSubmit,
  onSubmitBatch,
  onClose,
}: Props) {
  const [name, setName] = useState(initial?.name ?? '');
  const [description, setDescription] = useState(initial?.description ?? '');
  // Nhạc cụ + thể loại của project đơn lẻ (chung state với chế độ hàng loạt).

  // ── Tạo từ danh sách: '' = tạo tay 1 project; 'mixset' = cả danh sách → 1
  //    project Mix Set; 'single' = mỗi bài → 1 project Track lẻ ──
  const [listMode, setListMode] = useState<'' | ProjectKind>('');
  // «📂 Project từ bài cover có sẵn»: tạo 1 project rồi mở chỗ kéo thả file cover.
  const [ownMode, setOwnMode] = useState(false);
  // Tạo từ danh sách: true = tạo & chạy tự động; false = chỉ tạo, tôi tự chạy.
  const [runAuto, setRunAuto] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const batchMode = listMode !== '';
  const singles = listMode === 'single';
  const listLabel = singles ? 'Track lẻ' : 'Mix Set';
  // Nhóm (thư mục media/Mix Set | media/Track lẻ) của project tạo tay / đang sửa.
  const [kind, setKind] = useState<ProjectKind>(initial?.kind ?? 'mixset');
  const [songFile, setSongFile] = useState<File | null>(null);
  const [songLineCount, setSongLineCount] = useState<number | null>(null);
  const [songFileError, setSongFileError] = useState('');
  const [instrument] = useState(initial?.instrument ?? '');
  const [musicStyle, setMusicStyle] = useState(initial?.music_style ?? '');
  // Dòng nhạc (VN / US-UK / Chinese…) — cùng thể loại để tự chọn kênh đăng nháp.
  const [musicLine, setMusicLine] = useState(initial?.music_line ?? '');
  // "channel" = theo phong cách riêng của kênh (mỗi kênh 1 phong cách, tự xoay vòng).
  // Mặc định Tả thực điện ảnh (ảnh bìa → intro → video loop cùng bối cảnh).
  const [videoStyle, setVideoStyle] = useState('real');
  const [theme, setTheme] = useState('');
  // Mix Set: AI tự chọn thêm 1 nhạc cụ nổi bật cho từng bài Suno (mặc định bật).
  const [creativeInstrument, setCreativeInstrument] = useState(
    initial?.creative_instrument ?? true
  );
  const [confirmed, setConfirmed] = useState(false);
  // Chạy auto: false = cả audio + video (mặc định), true = chỉ audio.
  const [audioOnly, setAudioOnly] = useState(false);
  // Kênh YouTube đăng nháp: '' = tự chọn theo nhạc cụ; id = kênh người dùng chọn
  // (kênh nào cũng nhận nhạc cụ / thể loại nào — không cần khớp ánh xạ).
  const [channelId, setChannelId] = useState(
    initial?.channel_id ? String(initial.channel_id) : ''
  );
  // Intro 00:00: ảnh thumbnail động (mặc định) | chữ font có sẵn (tuỳ chọn).
  const [introMode, setIntroMode] = useState<IntroMode>(initial?.intro_mode ?? 'thumbnail');
  // Nội dung video: nhân vật + linh thú/thú nuôi (mặc định) | chỉ cảnh vật.
  const [castMode, setCastMode] = useState<CastMode>(initial?.cast_mode ?? 'character_pet');
  const [footageSceneMode, setFootageSceneMode] = useState<FootageSceneMode>(
    initial?.footage_scene_mode ?? 'auto'
  );

  const { data: mappings } = useChannelMappings();
  const { data: styleData } = useBatchStyles();
  const { data: looks } = useChannelLooks();

  if (!open) return null;

  const isEdit = Boolean(initial);
  const canBatch = !isEdit && Boolean(onSubmitBatch);
  const styleList = styleData?.styles ?? [];
  const totalCredits = (songLineCount ?? 0) * 2;
  const channelStyles = [...new Set((mappings ?? []).map((m) => m.music_style))];
  const channelLines = (mappings ?? []).map((m) => m.music_line ?? '');
  const instrumentChanged = isEdit && instrument.trim() !== (initial?.instrument ?? '');
  const introChanged = isEdit && introMode !== (initial?.intro_mode ?? 'thumbnail');
  const castChanged = isEdit && castMode !== (initial?.cast_mode ?? 'character_pet');
  const footageChanged = isEdit && footageSceneMode !== (initial?.footage_scene_mode ?? 'auto');
  const creativeChanged = isEdit && creativeInstrument !== (initial?.creative_instrument ?? true);
  const kindChanged = isEdit && kind !== (initial?.kind ?? 'mixset');
  const scenery = castMode === 'scenery';

  // Kênh người dùng chọn thắng tất cả; chưa chọn → tự chọn theo dòng nhạc +
  // thể loại (so khớp không phân biệt hoa/thường).
  const chosenChannel = (mappings ?? []).find((m) => String(m.id) === channelId);
  const autoChannel = autoPickChannel(mappings ?? [], instrument, musicStyle, musicLine);
  // Tự chọn khớp theo gì — để giải thích cho người dùng.
  const autoWhy = autoChannel
    ? [
        norm(autoChannel.music_line ?? '') && norm(autoChannel.music_line ?? '') === norm(musicLine)
          ? 'dòng nhạc'
          : '',
        norm(autoChannel.music_style) && norm(autoChannel.music_style) === norm(musicStyle)
          ? 'thể loại'
          : '',
      ].filter(Boolean).join(' + ')
    : '';
  const matchedChannel = chosenChannel ?? (channelId ? undefined : autoChannel);
  const chosenIdOrNull = chosenChannel ? chosenChannel.id : null;
  const channelChanged = isEdit && chosenIdOrNull !== (initial?.channel_id ?? null);

  const channelLook = (looks ?? []).find((l) => l.key === matchedChannel?.visual_look);
  const lookStyleKeys = new Set((channelLook?.styles ?? []).map((s) => s.key));

  /** Ô chọn style ảnh: mặc định theo phong cách kênh; vẫn cho chọn cố định. */
  function styleSelect(note: string) {
    return (
      <div>
        <label className={labelCls}>Style ảnh {note}</label>
        <select
          className={inputCls}
          value={videoStyle}
          onChange={(e) => setVideoStyle(e.target.value)}
        >
          <option value="channel">🎯 Theo phong cách kênh</option>
          {styleList.map((s) => (
            <option key={s.key} value={s.key}>
              {s.icon} {s.label}
              {lookStyleKeys.has(s.key) ? ' — hợp phong cách kênh' : ''}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-gray-500">
          {videoStyle === 'channel'
            ? channelLook
              ? <>Kênh này dùng phong cách <b>{channelLook.icon} {channelLook.label}</b>:{' '}
                  ảnh xoay vòng {channelLook.styles.map((s) => `${s.icon} ${s.label}`).join(' / ')},{' '}
                  kiểu chữ thumbnail, màu &amp; chuyển cảnh riêng — mỗi video tự đổi bố cục/font.</>
              : <>Chưa chọn kênh → dùng phong cách mặc định. Mỗi kênh có phong cách riêng
                  ở ⚙️ Settings → YouTube/GPMLogin.</>
            : lookStyleKeys.size > 0 && !lookStyleKeys.has(videoStyle)
              ? <span className="text-amber-300/80">⚠️ Style này không thuộc phong cách của
                  kênh — video có thể trông giống kênh khác.</span>
              : <>Giữ cố định style này; thumbnail vẫn tự đổi bố cục/font mỗi video.</>}
        </p>
      </div>
    );
  }

  /** Chọn kênh đăng nháp. Nhạc cụ/thể loại gợi ý của kênh chỉ điền vào ô ĐANG
   *  TRỐNG — không bao giờ ghi đè lựa chọn của người dùng. */
  function pickChannel(value: string) {
    setChannelId(value);
    const m = (mappings ?? []).find((x) => String(x.id) === value);
    if (!m) return;
    if (!musicStyle.trim() && m.music_style.trim()) setMusicStyle(m.music_style);
    if (!musicLine.trim() && (m.music_line ?? '').trim()) setMusicLine(m.music_line);
  }

  /** Bộ công cụ video dùng chung cho Track lẻ, Mix Set và project tạo tay. */
  function modeSelects(note: string) {
    return (
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={labelCls}>Nội dung video {note}</label>
          <select
            className={inputCls}
            value={castMode}
            onChange={(e) => setCastMode(e.target.value as CastMode)}
          >
            <option value="character_pet">👤 Nhân vật + linh thú/thú nuôi (mặc định)</option>
            <option value="scenery">🏞️ Chỉ cảnh vật (không nhân vật)</option>
          </select>
        </div>
        <div>
          <label className={labelCls}>Intro mở đầu (00:00) {note}</label>
          <select
            className={inputCls}
            value={introMode}
            onChange={(e) => setIntroMode(e.target.value as IntroMode)}
          >
            <option value="thumbnail">🖼️ Thumbnail động (mặc định)</option>
            <option value="font">🔤 Chữ font có sẵn</option>
          </select>
        </div>
        <p className="col-span-2 -mt-1 text-xs text-gray-500">
          {scenery
            ? <>🏞️ Chỉ cảnh vật: không nhân vật chính, không linh thú / con vật — ảnh và{' '}
                clip chỉ có <b>khung cảnh theo «Ý tưởng của bạn»</b> nhưng là <b>cảnh động</b>,
                không phải ảnh tĩnh (nước chảy, mây trôi, gió lùa cây cỏ, mưa / tuyết / cánh hoa
                rơi, máy quay chuyển động bình thường). </>
            : <>👤 Nhân vật chính + linh thú / thú nuôi đồng bộ xuyên suốt, bám theo «Ý tưởng
                của bạn». </>}
          {introMode === 'thumbnail'
            ? <>🖼️ Video mở đầu từ 00:00 bằng <b>chính ảnh thumbnail</b> (chữ do AI thiết kế),
                đẩy máy chậm rồi hoà tan vào clip đầu.</>
            : <>🔤 Intro dùng chữ font có sẵn đè lên clip đầu (kiểu cũ).</>}
        </p>
        <div className="col-span-2">
          <label className={labelCls}>Cách lồng footage đời thật {note}</label>
          <select
            className={inputCls}
            value={footageSceneMode}
            onChange={(e) => setFootageSceneMode(e.target.value as FootageSceneMode)}
          >
            <option value="auto">🤖 Tự chọn theo nội dung video</option>
            <option value="character_screen">👤 Nhân vật xem TV / máy chiếu</option>
            <option value="screen_only">📺 Chỉ TV / màn chiếu, không nhân vật</option>
          </select>
          <p className="mt-1 text-xs text-gray-500">
            Khi bạn upload footage ở tab Video, tool chỉ lồng footage một lần theo bố cục này.
          </p>
        </div>
        {castChanged && (
          <p className="col-span-2 -mt-1 text-xs text-amber-300/80">
            ⚠️ Đổi nội dung video khi project đã có ảnh: cần «Làm lại từ đầu» ở phần Video
            để vẽ lại bộ ảnh + cảnh clip theo lựa chọn mới.
          </p>
        )}
        {footageChanged && (
          <p className="col-span-2 -mt-1 text-xs text-amber-300/80">
            ⚠️ Đổi bố cục footage áp dụng ở lần dựng video tiếp theo.
          </p>
        )}
      </div>
    );
  }

  const lookLabel = (key?: string) => {
    const l = (looks ?? []).find((x) => x.key === key);
    return l ? `${l.icon} ${l.label}` : '';
  };

  /** Ô chọn kênh YouTube đăng nháp (dùng cho project lẻ và cả lô). */
  function channelSelect(note: string) {
    const list = mappings ?? [];
    return (
      <div>
        <label className={labelCls}>Kênh YouTube đăng nháp {note}</label>
        <select
          className={inputCls}
          value={channelId}
          onChange={(e) => pickChannel(e.target.value)}
        >
          <option value="">🤖 Tự chọn kênh theo dòng nhạc + thể loại</option>
          {list.map((m) => {
            const hint = [m.music_line ?? '', m.music_style].filter((v) => v.trim()).join(' · ');
            const look = lookLabel(m.visual_look);
            return (
              <option key={m.id} value={m.id}>
                {m.channel_name || `(kênh #${m.id} chưa đặt tên)`}
                {look ? ` — ${look}` : ''}
                {hint ? ` (gợi ý: ${hint})` : ''}
              </option>
            );
          })}
        </select>
        {list.length === 0 ? (
          <p className="mt-1 text-xs text-amber-300/80">
            ⚠️ Chưa có kênh nào. Thêm kênh (tên kênh → profile GPMLogin) ở ⚙️ Settings →
            YouTube/GPMLogin; Suno / Mix / Video vẫn chạy, bước đăng nháp sẽ chờ bạn chọn kênh.
          </p>
        ) : chosenChannel ? (
          <p className="mt-1 text-xs text-green-300/80">
            ✅ Lưu nháp lên kênh «{chosenChannel.channel_name || `#${chosenChannel.id}`}» —
            dòng nhạc / thể loại nào cũng được.
          </p>
        ) : autoChannel ? (
          <p className="mt-1 text-xs text-gray-500">
            Tự chọn → kênh «{autoChannel.channel_name || `#${autoChannel.id}`}»
            {autoWhy ? ` (khớp ${autoWhy} của kênh)` : ''}. Chọn kênh khác ở trên nếu muốn.
          </p>
        ) : (
          <p className="mt-1 text-xs text-gray-500">
            Chưa có kênh nào khớp dòng nhạc / thể loại này → tool sẽ dừng ở bước đăng
            nháp. <b>Chọn hẳn 1 kênh</b> ở trên để chắc chắn — kênh nào cũng nhận dòng
            nhạc / thể loại nào.
          </p>
        )}
      </div>
    );
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (batchMode) {
      if (!batchReady || !onSubmitBatch) return;
      onSubmitBatch({
        kind: listMode,
        name: singles ? '' : name.trim(),
        song_file: songFile!,
        music_style: musicStyle.trim(),
        music_line: musicLine.trim(),
        channel_id: chosenIdOrNull,
        video_style: videoStyle,
        theme: theme.trim(),
        creative_instrument: creativeInstrument,
        intro_mode: introMode,
        cast_mode: castMode,
        footage_scene_mode: footageSceneMode,
        audio_only: audioOnly,
      }, { autoRun: runAuto });
      return;
    }
    if (!name.trim() || (!isEdit && !ownMode && !musicStyle.trim())) return;
    const data: ProjectCreate = { name: name.trim(), description };
    // Sửa project: chỉ gửi nhạc cụ/thể loại khi đổi (giữ chữ ký hồ sơ prompt cũ).
    if (!isEdit || instrumentChanged) data.instrument = instrument.trim();
    if (!isEdit || musicStyle.trim() !== (initial?.music_style ?? ''))
      data.music_style = musicStyle.trim();
    if (!isEdit || musicLine.trim() !== (initial?.music_line ?? ''))
      data.music_line = musicLine.trim();
    if (!isEdit) data.video_style = videoStyle;
    if (!isEdit || channelChanged) data.channel_id = chosenIdOrNull;
    if (!isEdit || introChanged) data.intro_mode = introMode;
    if (!isEdit || castChanged) data.cast_mode = castMode;
    if (!isEdit || footageChanged) data.footage_scene_mode = footageSceneMode;
    if (!isEdit || creativeChanged) data.creative_instrument = creativeInstrument;
    if (!isEdit || kindChanged) data.kind = kind;
    onSubmit(data, { autoRun: false, ownCovers: ownMode });
  }

  const inputCls =
    'w-full rounded-lg border border-white/10 bg-background px-3 py-2 text-sm text-white outline-none focus:border-accent';
  const labelCls = 'mb-1 block text-xs font-medium text-gray-400';

  const batchReady = Boolean(
    (singles || name.trim()) && musicStyle.trim() && songFile && !songFileError && (confirmed || !runAuto)
  );

  async function chooseSongFile(file: File | null) {
    setSongFile(file);
    setSongLineCount(null);
    setSongFileError('');
    if (!file) return;
    const lower = file.name.toLowerCase();
    if (!LIST_EXTS.some((ext) => lower.endsWith(ext))) {
      setSongFileError('Chỉ nhận file Word (.docx, .doc), Excel (.xlsx, .xls), .txt hoặc .csv.');
      return;
    }
    if (lower.endsWith('.txt')) {
      const lines = (await file.text()).split(/\r?\n/).map((v) => v.trim()).filter(Boolean);
      const invalid = lines.find((v) => !/\s[-–—]\s/.test(v));
      if (!lines.length) setSongFileError('File TXT chưa có bài hát.');
      else if (invalid) setSongFileError(`Dòng sai định dạng: “${invalid}”`);
      else if (lines.length > 50) setSongFileError(`Tối đa 50 bài (file có ${lines.length} dòng).`);
      else setSongLineCount(lines.length);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <form
        onSubmit={submit}
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl bg-surface p-6 shadow-xl"
      >
        <h3 className="mb-4 text-lg font-semibold text-white">
          {isEdit ? 'Edit Project' : 'New Project'}
        </h3>

        {canBatch && (
          <div className="mb-4 space-y-1.5 rounded-lg border border-white/10 bg-background px-3 py-2 text-sm text-gray-200">
            {([
              ['', '✍️ Tạo 1 project thủ công (trống)'],
              ['own', '📂 Project từ bài cover có sẵn — kéo thả file cover, tự master + ghép lời'],
              ['mixset', '🎼 Mix Set — cả danh sách bài ghép thành 1 video dài'],
              ['single', '🎵 Track lẻ — mỗi bài trong danh sách thành 1 project, ảnh bìa + video riêng'],
            ] as const).map(([value, label]) => (
              <label key={value} className="flex items-start gap-2">
                <input
                  type="radio"
                  name="create-mode"
                  className="mt-1"
                  checked={value === 'own' ? ownMode : !ownMode && listMode === value}
                  onChange={() => {
                    setOwnMode(value === 'own');
                    setListMode(value === 'own' ? '' : value);
                    setConfirmed(false);
                  }}
                />
                <span>{label}</span>
              </label>
            ))}
          </div>
        )}

        {!batchMode ? (
          <>
            <label className={labelCls}>Name *</label>
            <input
              className={`${inputCls} mb-4`}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="vd: Tuyển tập Ballad Việt hay nhất"
              autoFocus
            />

            <label className={labelCls}>Description</label>
            <textarea
              className={`${inputCls} mb-4`}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="Không khí, bối cảnh, câu chuyện — AI bám vào đây khi viết prompt"
            />

            <div className="mb-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className={labelCls}>Dòng nhạc</label>
                  <MusicLineSelect
                    value={musicLine}
                    onChange={setMusicLine}
                    extra={channelLines}
                    className={inputCls}
                    emptyLabel="— chưa chọn —"
                    title="Dòng nhạc của bài"
                  />
                </div>
                <div>
                  <label className={labelCls}>Thể loại nhạc {isEdit || ownMode ? '' : '*'}</label>
                  <GenrePicker
                    value={musicStyle}
                    onChange={setMusicStyle}
                    extra={channelStyles}
                    className={inputCls}
                  />
                </div>
              </div>
              <p className="mt-1 text-xs text-gray-500">
                Thể loại quyết định không khí ảnh nền và cảnh động. Dòng nhạc + thể loại giúp
                tool tự chọn kênh đăng nháp khi bạn chưa chọn kênh.
              </p>
            </div>
            <div className="mb-4">
              <label className={labelCls}>Nhóm (thư mục lưu)</label>
              <select
                className={inputCls}
                value={kind}
                onChange={(e) => setKind(e.target.value as ProjectKind)}
              >
                <option value="mixset">🎼 Mix Set (nhiều bài ghép 1 video)</option>
                <option value="single">🎵 Track lẻ (1 bài 1 video)</option>
              </select>
              <p className="mt-1 text-xs text-gray-500">
                {isEdit
                  ? <>Project tạo trước bản cập nhật này vẫn nằm thẳng trong <b>media/</b>; đổi
                      nhóm thì thư mục được chuyển vào <b>media/{kind === 'single' ? 'Track lẻ' : 'Mix Set'}/</b>.</>
                  : <>File của project sẽ nằm trong <b>media/{kind === 'single' ? 'Track lẻ' : 'Mix Set'}/</b>.</>}
                {kindChanged && (
                  <span className="text-amber-300/80">
                    {' '}Khi lưu, thư mục của project được chuyển sang nhóm mới (cần project
                    đang rảnh, đóng các file của project đang mở).
                  </span>
                )}
              </p>
            </div>
            <div className="mb-4">{channelSelect('')}</div>
            {!isEdit && <div className="mb-4">{styleSelect('')}</div>}
            <div className="mb-4">{modeSelects('')}</div>
            <label className="mb-4 flex items-start gap-2 rounded-lg border border-purple-500/30 bg-purple-500/10 px-3 py-2 text-xs text-gray-200">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={creativeInstrument}
                onChange={(e) => setCreativeInstrument(e.target.checked)}
              />
              <span>
                <b>Thêm nhạc cụ sáng tạo</b> — mặc định bật để AI tự chọn nhạc cụ phù hợp
                cho từng bài. Bỏ tick để không thêm; vẫn chỉnh riêng từng bài ở tab Suno Cover.
              </span>
            </label>
            {!isEdit && ownMode && (
              <p className="mb-4 rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-100">
                Tạo xong, tool mở tab <b>② Suno Cover</b> ở ô <b>📂 Kéo thả bài cover có sẵn</b>:
                kéo các file nhạc cover (và file lời .txt/.lrc nếu có) vào. Tool tự <b>master +
                đồng bộ âm lượng</b> từng bài và <b>AI căn lời</b> để xuất file lời <b>.srt</b>.
                Không tải bài gốc, không dùng Suno. Thể loại để trống cũng được.
              </p>
            )}
            {!isEdit && !ownMode && (
              <p className="mb-4 rounded-lg border border-cyan-500/25 bg-cyan-500/10 px-3 py-2 text-xs text-cyan-100">
                Project thủ công chỉ được tạo và chuẩn bị đầy đủ công cụ. Bạn chủ động chạy từng
                bước; khi cần vẫn có thể bấm <b>Auto chỉ audio</b> / <b>Auto audio + video</b> ở thanh dưới cùng.
              </p>
            )}
          </>
        ) : (
          <div className="mb-4 space-y-3">
            <div className="space-y-1.5 rounded-lg border border-white/10 bg-background px-3 py-2 text-sm text-gray-200">
              <label className="flex items-start gap-2">
                <input
                  type="radio"
                  name="run-mode"
                  className="mt-1"
                  checked={!runAuto}
                  onChange={() => { setRunAuto(false); setConfirmed(false); }}
                />
                <span>
                  ✍️ <b>Chỉ tạo, tôi tự chạy</b>
                  <span className="block text-xs text-gray-500">
                    Tạo sẵn project và danh sách bài, <b>chưa chạy gì, chưa tốn credit</b>. Bạn
                    tự bấm từng bước, hoặc bấm <b>Auto chỉ audio</b> / <b>Auto audio + video</b> ở thanh dưới cùng khi muốn.
                  </span>
                </span>
              </label>
              {/* 2026-11-25: «chỉ audio» là lựa chọn hiện thẳng, không giấu sau
                  «Tạo & chạy tự động» nữa. */}
              {([
                [true, '🎧', 'Tạo & chạy auto chỉ audio', singles
                  ? 'Tạo xong tool tự làm Cover → master → AI căn lời (.srt) từng bài rồi dừng. Không dựng video (dùng credit Suno).'
                  : 'Tạo xong tool tự làm Cover → master → AI căn lời → ghép mix (.wav + .srt) rồi dừng. Không dựng video (dùng credit Suno).'],
                [false, '🚀', 'Tạo & chạy auto audio + video', singles
                  ? 'Cover → master → dựng video → lưu nháp YouTube (dùng credit Suno).'
                  : 'Cover → master → ghép mix → dựng video → lưu nháp YouTube (dùng credit Suno).'],
              ] as const).map(([onlyAudio, icon, label, hint]) => (
                <label key={label} className="flex items-start gap-2">
                  <input
                    type="radio"
                    name="run-mode"
                    className="mt-1"
                    checked={runAuto && audioOnly === onlyAudio}
                    onChange={() => { setRunAuto(true); setAudioOnly(onlyAudio); setConfirmed(false); }}
                  />
                  <span>
                    {icon} <b>{label}</b>
                    <span className="block text-xs text-gray-500">{hint}</span>
                  </span>
                </label>
              ))}
            </div>
            {singles ? (
              <p className="rounded-lg border border-white/10 bg-background px-3 py-2 text-xs text-gray-400">
                Mỗi dòng trong file thành <b>một project Track lẻ riêng</b> (tên project = dòng
                đó), lưu trong thư mục <b>media/Track lẻ/</b>. Mỗi bài có <b>ảnh bìa + video
                riêng</b> do AI vẽ theo tên bài
                {videoStyle === 'channel' ? '; style ảnh tự xoay vòng giữa các bài' : ''}. Khi
                chạy, tool làm lần lượt từng bài: tải bài gốc → tempo 4.5× → Suno Cover → master → dựng
                video → lưu nháp YouTube. Bài nào lỗi thì bỏ qua, làm tiếp bài sau.
              </p>
            ) : (
              <p className="rounded-lg border border-white/10 bg-background px-3 py-2 text-xs text-gray-400">
                Tạo đúng <b>một project Mix Set</b> (thư mục <b>media/Mix Set/</b>). Mỗi dòng
                trong file là một bài theo dạng <b>Tên bài - Ca sĩ</b> hoặc <b>Ca sĩ - Tên
                bài</b>. Khi chạy, tool lần lượt tải bài gốc → tempo 4.5× → Suno Cover → master → ghép
                mix → dựng video → lưu nháp YouTube.
              </p>
            )}

            {!singles && (
              <div>
                <label className={labelCls}>Tên Mix Set *</label>
                <input
                  className={inputCls}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="vd: Ballad nhạc Việt mùa Thu"
                />
              </div>
            )}

            <div>
              <label className={labelCls}>Danh sách bài hát (Word, Excel hoặc .txt) *</label>
              <label
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(false);
                  void chooseSongFile(e.dataTransfer.files?.[0] ?? null);
                }}
                className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-3 py-4 text-center text-xs ${
                  dragOver ? 'border-accent bg-accent/10 text-white' : 'border-white/15 bg-background text-gray-400'
                }`}
              >
                <span className="text-2xl">📄</span>
                {songFile
                  ? <span className="mt-1 text-sm text-white">{songFile.name}</span>
                  : <span className="mt-1">Kéo thả file danh sách vào đây, hoặc bấm để chọn file</span>}
                <span className="mt-0.5 text-gray-500">.docx · .doc · .xlsx · .xls · .txt · .csv</span>
                <input
                  type="file"
                  accept={LIST_ACCEPT}
                  className="hidden"
                  onChange={(e) => void chooseSongFile(e.target.files?.[0] ?? null)}
                />
              </label>
              <p className="mt-1 text-xs text-gray-500">
                Word / .txt: mỗi dòng 1 bài <b>Tên bài - Ca sĩ</b>. Excel: mỗi hàng 1 bài — cột
                Tên bài và cột Ca sĩ (hoặc 1 cột ghi sẵn «Tên bài - Ca sĩ»); hàng tiêu đề và
                cột STT tự bỏ qua. Tối đa 50 bài.
                {songLineCount != null ? ` Đã đọc ${songLineCount} bài.` : ''}
              </p>
              {songFileError && <p className="mt-1 text-xs text-red-300">{songFileError}</p>}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={labelCls}>Dòng nhạc</label>
                <MusicLineSelect
                  value={musicLine}
                  onChange={setMusicLine}
                  extra={channelLines}
                  className={inputCls}
                  emptyLabel="— chưa chọn —"
                  title={`Dòng nhạc của ${listLabel}`}
                />
              </div>
              <div>
                <label className={labelCls}>Thể loại nhạc *</label>
                <GenrePicker
                  value={musicStyle}
                  onChange={setMusicStyle}
                  extra={channelStyles}
                  className={inputCls}
                />
              </div>
            </div>

            {channelSelect(`(${listLabel})`)}

            {styleSelect(`(${listLabel})`)}

            {modeSelects(`(${listLabel})`)}

            <div>
              <label className={labelCls}>
                {singles
                  ? 'Chủ đề chung (tuỳ chọn — để trống thì AI vẽ theo tên từng bài)'
                  : 'Chủ đề (tuỳ chọn — để trống thì AI tự chọn 1 mạch chung)'}
              </label>
              <input
                className={inputCls}
                value={theme}
                onChange={(e) => setTheme(e.target.value)}
                placeholder="vd: tình đầu tuổi học trò, mưa đêm, chia tay…"
              />
            </div>

            <div>
              <label className="flex items-start gap-2 text-sm text-gray-200">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={creativeInstrument}
                  onChange={(e) => setCreativeInstrument(e.target.checked)}
                />
                <span>
                  Tự động chọn thêm nhạc cụ để bài hát sáng tạo hơn
                  <span className="mt-0.5 block text-xs text-gray-500">
                    AI chọn 1 nhạc cụ hợp thể loại (vd sáo, saxophone, guitar điện…) cho từng bài
                    khi làm cover trên Suno. Vẫn đổi riêng từng bài được ở tab ② Suno Cover.
                  </span>
                </span>
              </label>
            </div>

            {runAuto && <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2.5">
              <p className="text-sm font-medium text-amber-200">
                ⚠️ Đây là quy trình LIVE, sẽ dùng credit Suno cho từng bài
                {songLineCount != null ? ` (khoảng ${totalCredits} bản cover đầu ra)` : ''}.
              </p>
              <p className="mt-1 text-xs text-amber-200/80">
                Tool xử lý tuần tự và <b>không</b> tự mua thêm credit. Khi thiếu đăng nhập,
                credit hoặc thao tác xác nhận, {listLabel} dừng an toàn để bạn tiếp tục. YouTube
                chỉ được <b>lưu nháp</b>, không đăng công khai.
              </p>
              <label className="mt-2 flex items-center gap-2 text-xs text-amber-100">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                />
                Tôi hiểu và xác nhận chạy {singles
                  ? `${songLineCount ?? 'các'} Track lẻ này`
                  : 'Mix Set này'}.
              </label>
            </div>}

            {batchError && (
              <p role="alert" className="text-sm text-red-300">
                {batchError}
              </p>
            )}
          </div>
        )}

        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm text-gray-300 hover:bg-surface-2"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={
              batchMode
                ? batchSaving || !batchReady
                : saving || !name.trim() || (!isEdit && !ownMode && !musicStyle.trim())
            }
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
          >
            {batchMode
              ? batchSaving
                ? `Đang tạo ${listLabel}…`
                : !runAuto
                  ? singles ? '🎵 Tạo Track lẻ (chưa chạy)' : '🎼 Tạo Mix Set (chưa chạy)'
                  : singles
                    ? `🎵 Tạo & chạy ${songLineCount ?? ''} Track lẻ${audioOnly ? ' (chỉ audio)' : ''}`
                    : `🎼 Tạo & chạy Mix Set${audioOnly ? ' (chỉ audio)' : ''}`
              : isEdit
                ? 'Save Changes'
                : ownMode ? '📂 Tạo & mở chỗ kéo thả' : 'Create Project'}
          </button>
        </div>
      </form>
    </div>
  );
}
