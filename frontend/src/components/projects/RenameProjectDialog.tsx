import { useEffect, useState } from 'react';
import { useRenameProject, type RenameRefresh } from '../../api/projects';

interface Props {
  open: boolean;
  projectId: number;
  currentName: string;
  onClose: () => void;
  /** Có job cập nhật thumbnail được gửi → mở tab Video để xem tiến độ. */
  onJobStarted?: () => void;
}

const OPTIONS: { value: RenameRefresh; label: string; hint: string }[] = [
  {
    value: 'text',
    label: 'Đổi tên + cập nhật chữ trên thumbnail & intro',
    hint:
      'Giữ ảnh bìa và clip hiện có; vẽ lại chữ tiêu đề lên thumbnail.png và ghép lại ' +
      'final.mp4 để intro mang tên mới (vài phút, không tốn lượt tạo ảnh/clip).',
  },
  {
    value: 'regen',
    label: 'Đổi tên + TẠO LẠI ảnh bìa + clip intro 00',
    hint:
      'Tạo ảnh 0 mới (Muse.ai, dự phòng Gemini) và clip intro 00 mới (cùng prompt đã khoá ' +
      '→ nhân vật khớp cả bộ), rồi vẽ chữ tên mới + ghép lại video. Mất ~10–20 phút, ' +
      'tốn 1 lượt ảnh + 1 lượt clip. Đừng đóng cửa sổ trình duyệt của tool.',
  },
  {
    value: 'none',
    label: 'Chỉ đổi tên',
    hint: 'Không đụng ảnh/video. Chữ trên thumbnail/intro sẽ đổi ở lần ghép video kế tiếp.',
  },
];

export default function RenameProjectDialog({
  open,
  projectId,
  currentName,
  onClose,
  onJobStarted,
}: Props) {
  const rename = useRenameProject(projectId);
  const [name, setName] = useState(currentName);
  const [refresh, setRefresh] = useState<RenameRefresh>('text');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName(currentName);
      setRefresh('text');
      setError(null);
    }
  }, [open, currentName]);

  if (!open) return null;
  const trimmed = name.trim().replace(/\s+/g, ' ');
  const canSubmit = Boolean(trimmed) && trimmed !== currentName && !rename.isPending;

  function submit() {
    setError(null);
    rename.mutate(
      { name: trimmed, refresh },
      {
        onSuccess: (res) => {
          onClose();
          if (res.job) onJobStarted?.();
        },
        onError: (err: any) =>
          setError(err?.response?.data?.detail ?? 'Không đổi được tên project.'),
      },
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-lg rounded-xl bg-surface p-6 shadow-xl">
        <h3 className="mb-4 text-lg font-semibold text-white">✏️ Đổi tên project</h3>
        <label className="mb-1 block text-sm text-gray-300">
          Tên mới (cũng là chữ tiêu đề trên thumbnail &amp; intro video)
        </label>
        <input
          autoFocus
          value={name}
          maxLength={150}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && canSubmit) submit();
          }}
          className="mb-4 w-full rounded-lg bg-surface-2 px-3 py-2 text-white outline-none focus:ring-2 focus:ring-accent"
        />
        <div className="mb-4 space-y-2">
          {OPTIONS.map((o) => (
            <label
              key={o.value}
              className={`block cursor-pointer rounded-lg border p-3 ${
                refresh === o.value ? 'border-accent bg-accent/10' : 'border-white/10'
              }`}
            >
              <div className="flex items-center gap-2">
                <input
                  type="radio"
                  name="rename-refresh"
                  checked={refresh === o.value}
                  onChange={() => setRefresh(o.value)}
                />
                <span className="text-sm font-medium text-white">{o.label}</span>
              </div>
              <p className="mt-1 pl-6 text-xs text-gray-400">{o.hint}</p>
            </label>
          ))}
        </div>
        <p className="mb-4 text-xs text-gray-400">
          Thư mục media được đổi tên theo. Bản nháp YouTube đã đăng KHÔNG tự đổi — bấm
          «Đăng nháp YouTube» lại sau khi cập nhật xong.
        </p>
        {error && (
          <p className="mb-4 whitespace-pre-wrap rounded-lg bg-red-900/40 p-3 text-sm text-red-200">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm text-gray-300 hover:bg-surface-2"
          >
            Huỷ
          </button>
          <button
            onClick={submit}
            disabled={!canSubmit}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
          >
            {rename.isPending ? 'Đang đổi tên…' : 'Đổi tên'}
          </button>
        </div>
      </div>
    </div>
  );
}
