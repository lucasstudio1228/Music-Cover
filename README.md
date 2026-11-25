# Cover Nhạc Tool by Lucas Studio (Music-Cover)

Tool làm **trọn gói video nhạc cover cho YouTube**. Tool làm hết từ bài gốc đến bản nháp trên
YouTube: tải bài gốc + lời → làm cover trên Suno → master → căn lời → ghép mix → vẽ ảnh bìa +
clip động → dựng video có lời chạy → lưu **nháp** YouTube.

> Chỉ cần phần **âm thanh** (cover + master + mix + file lời `.srt` cho CapCut), không làm video?
> Dùng bản gọn **[Cover Music by Lucas Studio (MasterAudio)](https://github.com/lucasstudio1228/MasterAudio)**.
> Bản đó chạy cổng 8200, có cả cho Mac, và dùng song song được với tool này.

| Bước | Tab trong project | Việc làm |
|---|---|---|
| ① | **Tải nhạc gốc** | Tìm và tải bài gốc + lời (nhaccuatui), đặt tempo cho Suno |
| ② | **Suno Cover** | Tạo bản cover trên Suno (hoặc **kéo thả bản cover có sẵn**), kiểm tra lỗi, master |
| ③ | **Lời bài hát** | AI căn lời theo nhạc, tải file lời `.srt` / `.lrc` |
| ④ | **Mix** | Cân âm lượng, ghép các bài thành 1 bản mix dài |
| ⑤ | **Video** | Ảnh bìa + bảng nhân vật/bối cảnh, clip động, thumbnail có chữ, dựng `final.mp4` có lời chạy |
| ⑥ | **Duyệt & đăng** | Xem trước, AI viết tiêu đề / mô tả, lưu **nháp** YouTube (không bao giờ tự công khai) |

Cách dùng hằng ngày: xem **[HUONG_DAN.md](HUONG_DAN.md)**.

## Có gì mới

- **Mở bằng file .exe:** cài xong có lối tắt **Cover Nhac Tool** ngoài Desktop. Tool mở trong
  cửa sổ riêng, không cần trình duyệt, không có cửa sổ đen.
- **Tạo project không chạy tự động:** chọn **✍️ Chỉ tạo, tôi tự chạy** để tool chỉ tạo sẵn
  project và danh sách bài, chưa tốn credit Suno. Khi muốn chạy, bấm **🎧 Auto chỉ audio** hoặc
  **🚀 Auto audio + video**.
- **📂 Project từ bài cover có sẵn:** kéo thả file cover (và file lời) vào. Tool tự **master +
  đồng bộ âm lượng** và **AI căn lời**.
- **File danh sách bài nhận Excel:** `.xlsx`, `.xls`, `.csv`, ngoài `.docx`, `.doc`, `.txt`.
- **Lời bài hát xuống dòng:** câu dài tự chia thành nhiều dòng, **mỗi dòng tối đa 8 từ**. Áp dụng
  cho cả lời chạy trên video và file `.srt`. Trên video các dòng cách nhau thoáng.
- **Tải nhanh file `.srt` của từng bài** (tab ③).
- **`update.bat`:** cập nhật lên bản mới mà không mất dữ liệu.

---

## 1. Tải tool về

Trên trang GitHub bấm **Code → Download ZIP**, rồi giải nén vào nơi bạn muốn để tool (ví dụ
`D:\Tools\Cover nhạc`). Nếu biết dùng git thì có thể chạy
`git clone https://github.com/lucasstudio1228/Music-Cover.git`.

## 2. Cài đặt (Windows, chỉ làm 1 lần)

**Máy cần có sẵn:**

| Thành phần | Ghi chú |
|---|---|
| Windows 10 / 11 | Đã có sẵn Edge WebView2 để hiện cửa sổ tool |
| **Python 3.10 hoặc 3.11** | https://www.python.org/downloads/. Khi cài nhớ tick **"Add Python to PATH"** |
| **ffmpeg** | Mở PowerShell gõ `winget install Gyan.FFmpeg` |
| **Google Chrome** / Cốc Cốc | Để mở Suno, nhaccuatui, ChatGPT |
| Card NVIDIA *(khuyên dùng)* | AI căn lời và tách giọng chạy nhanh hơn nhiều |
| **GPMLogin** *(cho video + YouTube)* | Đăng nháp YouTube, tạo clip bằng Muse.ai / Google Flow |
| **API Key** (OpenAI hoặc tương thích) | Để AI viết Styles, tiêu đề, mô tả, prompt ảnh |

**Cài:** bấm đúp **`install.bat`** trong thư mục tool rồi chờ hiện chữ **CAI DAT XONG**. Lần
đầu mất khoảng 10–20 phút. Cài xong sẽ có:
- File **`CoverNhacTool.exe`** trong thư mục tool.
- Lối tắt **Cover Nhac Tool** (icon tai nghe) ngoài **Desktop**.

Sau đó làm phần **Cài đặt lần đầu** trong [HUONG_DAN.md](HUONG_DAN.md#cài-đặt-lần-đầu-trong-tool).
Phần đó gồm: API Key, đăng nhập Suno / nhaccuatui / ChatGPT, kết nối GPMLogin, kênh YouTube.

## 3. Mở tool

Bấm đúp **Cover Nhac Tool** ngoài Desktop. Tool mở trong **cửa sổ riêng**.

- **Đóng cửa sổ = tắt tool.** Nếu đang có việc chạy (Suno, mix, video…), tool hỏi lại trước khi
  đóng.
- Cách cũ vẫn dùng được: bấm đúp **`start.bat`**, trình duyệt sẽ mở **http://localhost:8100**.
- Tool chạy cổng **8100**, nên dùng song song được với bản gọn MasterAudio (cổng 8200).

## 4. Cập nhật lên bản mới (không mất dữ liệu)

Project, nhạc, video, setting, các đăng nhập và API key **được giữ nguyên**.

1. Chờ các việc đang chạy xong, rồi **đóng tool**. Nếu tool đang mở, `update.bat` sẽ dừng và
   nhắc bạn đóng.
2. Bấm đúp **`update.bat`** trong thư mục tool, chờ hiện chữ **CAP NHAT XONG**.
3. Mở lại tool bằng lối tắt **Cover Nhac Tool**.

`update.bat` tự làm các việc sau:
- tải bản mới từ GitHub và chép đè phần mã;
- cài thêm thư viện nếu bản mới cần;
- tạo lại `.exe` và lối tắt Desktop.

Mã cũ được cất trong `_ban_cu_truoc_cap_nhat\`. Khi tool đã chạy ổn, xoá thư mục này cũng được.

**Bản cũ chưa có `update.bat`?** Mở link
https://raw.githubusercontent.com/lucasstudio1228/Music-Cover/main/update.bat, chuột phải →
**Lưu thành (Save as)** vào thư mục tool (cạnh `start.bat`) với tên `update.bat`. Sau đó làm như
các bước trên.

## 5. Lỗi thường gặp khi cài / mở

| Hiện tượng | Cách xử lý |
|---|---|
| "Khong tim thay Python" | Cài Python 3.10/3.11 (tick *Add to PATH*), chạy lại `install.bat` |
| "Khong tim thay ffmpeg" | `winget install Gyan.FFmpeg`, rồi đóng và mở lại tool |
| Không thấy lối tắt / mất `CoverNhacTool.exe` | Chạy `update.bat` (tự tạo lại) |
| Lần đầu mở, tool hỏi cài "thư viện cửa sổ ứng dụng" | Bấm **OK** (cần mạng, khoảng 1 phút) |
| Cửa sổ báo "Không mở được tool" | Chụp màn hình gửi người hỗ trợ, kèm file `data\logs\app_server.log` |
| Cửa sổ trắng / không hiện | Dùng tạm `start.bat` (mở bằng trình duyệt) |
| `update.bat` báo "Tool dang chay" | Đóng tool rồi bấm lại `update.bat` |
| Máy không có card NVIDIA | Vẫn chạy được, chỉ có AI căn lời / tách giọng chậm hơn |

---

## Dữ liệu cá nhân: KHÔNG có trong repo

Bản tải về chỉ kèm `data\master_config.json` (thông số master) và `data\suno_workflow.json`.
Lần đầu mở tool, `data\app.db` (project, setting) sẽ tự được tạo.

**Không** kèm theo: API key, mật khẩu, cookie đăng nhập Suno / nhaccuatui / ChatGPT, profile
GPMLogin, nhạc và video của bạn. Mỗi người tự đăng nhập và nhập key của mình.

Khi chia sẻ thư mục tool cho người khác, hãy bỏ ra các mục sau (máy kia sẽ tự tạo lại khi chạy
`install.bat`):
- `.venv`, `.browser_profile*`;
- `data\` (trừ 2 file json ở trên);
- `media`, `outputs`, `stems`, `Trash`;
- `.env` và `CoverNhacTool.exe`.

Cách gọn nhất là gửi link GitHub này.

## Lưu ý về lyrics trên Suno

Lyrics gửi lên Suno được chuẩn hoá (bỏ dòng tên bài / ca sĩ, bỏ nhãn đoạn, chuẩn Unicode NFC) và
tự thay dấu cách bằng `_` để Suno hát tiếng Việt tròn vành rõ chữ; lời gốc trong project vẫn giữ
khoảng trắng tự nhiên cho bước AI căn lời, phụ đề `.srt`/`.lrc` và lời trên video. Bài bị Suno báo
bản quyền sẽ được đánh dấu `rejected` (giữ nguyên dữ liệu) và tool chuyển sang bài tiếp theo. Chỉ
dùng bản cover / lời bạn tự làm hoặc được phép sử dụng. Video chỉ được lưu **nháp** trên YouTube;
bạn tự kiểm tra rồi mới công khai.
