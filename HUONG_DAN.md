# Cover Nhạc Tool — Hướng dẫn sử dụng

Hướng dẫn **dùng tool hằng ngày**. Cách tải, cài, cập nhật và sửa lỗi cài đặt: xem
**[README.md](README.md)**.

## Mở và đóng tool

- **Mở:** bấm đúp **Cover Nhac Tool** ngoài Desktop (hoặc `CoverNhacTool.exe` trong thư mục
  tool). Tool hiện trong cửa sổ riêng; chờ vài giây cho tool khởi động.
- **Đóng:** bấm dấu ✕ của cửa sổ là **tắt tool**. Nếu đang có việc chạy (Suno, mix, video…),
  tool hỏi lại. Chọn **Cancel** nếu muốn tool chạy tiếp.
- Nút **⬇** tải file vẫn hiện hộp chọn nơi lưu. Link ngoài (nhaccuatui, YouTube…) mở bằng
  trình duyệt.
- Vẫn dùng được `start.bat` (trình duyệt mở http://localhost:8100). Nếu đã mở bằng `start.bat`
  rồi mới bấm `.exe`, cửa sổ chỉ hiện giao diện (tên cửa sổ có chữ *"đã mở sẵn"*). Khi đó đóng
  cửa sổ không tắt `start.bat`.

---

## Cài đặt lần đầu trong tool

Phần này chỉ làm 1 lần. Bấm nút **⚙️ Settings** ở góc trên bên phải. Nếu nút có chấm cam tức là
chưa nhập API key.

### 1. API Key (cho AI)
AI dùng key này để viết Styles cho Suno, lọc lời, viết prompt ảnh, tiêu đề và mô tả YouTube.
1. **API Key**: dán key của bạn.
2. **API Base URL**:
   - key OpenAI gốc (bắt đầu bằng `sk-`): `https://api.openai.com/v1`;
   - key của nhà cung cấp khác: điền địa chỉ họ đưa (ví dụ `https://api.shopaikey.com/v1`).
3. **Model**: ví dụ `gpt-4.1`, hoặc `gpt-4o-mini` (rẻ hơn).
4. Bấm **🔌 Test API**. Báo thành công thì bấm **Lưu API (OpenAI)**.

### 2. Đăng nhập nhaccuatui (để tải nhạc gốc)
Mục **🎵 nhaccuatui — tải nhạc gốc** → **🔑 Mở nhaccuatui để đăng nhập**. Một cửa sổ trình
duyệt riêng của tool mở ra. Bạn **tự đăng nhập** (tool không nhập mật khẩu hộ). Khi thấy
**✅ Đã đăng nhập** thì bấm **Đóng cửa sổ**.

### 3. Đăng nhập Suno (để làm cover)
Mục **🎤 Suno — làm bản cover** → **🔑 Mở Suno để đăng nhập**. Bạn tự đăng nhập. Khi thấy
**✅ Đã đăng nhập Suno** thì bấm **✖ Đóng cửa sổ Suno**.

### 4. Đăng nhập ChatGPT (để vẽ ảnh + thumbnail)
Phần thumbnail: để chọn **ChatGPT web** → bấm **🤖 Mở ChatGPT để đăng nhập**. Đăng nhập bằng
**email + mật khẩu**; nút "Continue with Google" hay bị Google chặn trong cửa sổ tự động. Khi đã
thấy giao diện chat thì bấm **✖ Đóng cửa sổ ChatGPT**.

### 5. GPMLogin (cho YouTube + clip video)
1. Trong phần mềm **GPMLogin**, làm các bước sau:
   - Tạo 1 profile cho kênh YouTube, mở profile đó, đăng nhập Google của kênh rồi đóng.
   - Bật **Local API** (cổng mặc định **9495**).
2. Trong tool, vào **📺 YouTube / GPMLogin**:
   - Kiểm tra ô `http://localhost:9495`, bấm **💾 Lưu cấu hình GPM**.
   - Bấm **🔌 Test kết nối / tải profiles**. Danh sách profile hiện ra là OK.
3. **Thêm kênh** (bảng *Kênh YouTube — tên kênh → profile GPMLogin* → **➕ Thêm kênh mới**). Điền
   các ô sau rồi bấm **➕ Thêm**:
   - tên kênh, profile GPM;
   - ngôn ngữ, #hashtag mặc định;
   - phong cách hình ảnh;
   - *(tuỳ chọn)* **Dòng nhạc** + **thể loại gợi ý**. Điền 2 ô này thì khi để **🤖 Tự chọn kênh**,
     tool sẽ tự chọn đúng kênh cho project.

### 6. Máy tạo video (Muse.ai / Google Flow)
1. Trong GPMLogin, tạo profile riêng rồi đăng nhập:
   - **muse.ai**;
   - và/hoặc Google tại **flow.google.com**.
2. Trong tool, vào **🎬 Máy tạo video qua GPMLogin** rồi bấm **💾 Lưu máy tạo video**. Các ô cần
   chọn:
   - **Máy tạo cảnh động (clip)**: Muse.ai hoặc Flow/Veo;
   - profile GPM cho từng máy;
   - **Máy vẽ ảnh nền**.
3. Không thấy profile mới thì bấm **🔄 Tải lại profiles**.

> Không cho 2 tool dùng **cùng 1 profile GPM** cùng lúc (ví dụ cả 2 tool đều đang upload), vì sẽ
> bị lỗi.

---

## Tạo project

Bấm **+ New Project**, rồi chọn 1 trong 4 kiểu:

| Kiểu | Dùng khi | Tool làm gì |
|---|---|---|
| ✍️ **Tạo 1 project thủ công (trống)** | Muốn tự làm từng bước | Chỉ tạo project trống, bạn tự bấm ① → ⑥ |
| 📂 **Project từ bài cover có sẵn** | Đã có file cover | Tạo project rồi mở ngay ô **kéo thả bài cover** (xem bên dưới). Không tải bài gốc, không dùng Suno |
| 🎼 **Mix Set** | Nhiều bài ghép thành **1 video dài** | Tạo 1 project chứa cả danh sách bài |
| 🎵 **Track lẻ** | **1 bài = 1 video** | Mỗi dòng trong danh sách thành 1 project, có ảnh bìa + video riêng |

**Tên project = tiêu đề in trên thumbnail**, nên hãy đặt tên đẹp. Form còn cho chọn:
- kênh YouTube, phong cách ảnh, chủ đề;
- kiểu intro, có cô gái hay chỉ cảnh vật, thời lượng mix.

### Mix Set / Track lẻ: chạy tự động hay tự chạy?

- **✍️ Chỉ tạo, tôi tự chạy** (mặc định): tool chỉ tạo sẵn project và danh sách bài. **Chưa tải
  bài, chưa dùng Suno, chưa tốn credit.** Sau đó bạn tự bấm từng bước trong project, hoặc bấm
  nút chạy tự động ở thanh dưới cùng khi muốn.
- **🎧 Tạo & chạy tự động**: tool làm luôn. Chọn thêm **Kiểu chạy auto**:
  - **🎬 Audio + Video**: cover → master → (ghép mix) → dựng video → lưu nháp YouTube.
  - **🎧 Chỉ audio**: cover → master → (ghép mix) rồi dừng.

  Kiểu này cần tick ô xác nhận dùng credit Suno.

### File danh sách bài

Kéo thả file vào ô **📄** trong form (hoặc bấm vào ô để chọn file). Mỗi file tối đa 50 bài.

| Loại file | Cách ghi |
|---|---|
| **Word** `.docx`, `.doc` / **chữ** `.txt` | Mỗi dòng 1 bài: **Tên bài - Ca sĩ** (hoặc **Ca sĩ - Tên bài**) |
| **Excel** `.xlsx`, `.xls` / `.csv` | Mỗi **hàng** 1 bài: cột A = Tên bài, cột B = Ca sĩ. Hoặc chỉ 1 cột ghi sẵn «Tên bài - Ca sĩ». Tool đọc **trang tính đầu tiên** và tự bỏ qua hàng tiêu đề + cột số thứ tự |

| STT | Tên bài | Ca sĩ |
|---|---|---|
| 1 | Nơi này có anh | Sơn Tùng M-TP |
| 2 | Em gái mưa | Hương Tràm |

File Office đời cũ (`.xls`, `.doc`) có thể không đọc được. Khi đó mở file bằng Excel/Word →
**Lưu thành** → chọn `.xlsx` / `.docx` rồi chọn lại.

### Thanh dưới cùng: chạy tự động

- **🎧 Auto chỉ audio**: project đang mở chạy tiếp tự động đến hết phần âm thanh.
- **🚀 Auto audio + video**: chạy tiếp tới video + nháp YouTube.
- Khi đang chạy có thêm **⏸ Tạm dừng**, **▶ Tiếp tục** và **⏹ Dừng lại**. ⏹ Dừng lại dừng tất cả
  việc, phần đã làm được giữ lại để chạy tiếp sau.
- Bấm vào một việc đang chạy để nhảy tới đúng project / tab của việc đó.

---

## 6 bước trong mỗi project

### ① Tải nhạc gốc
- Gõ mỗi dòng 1 bài «Tên bài – Ca sĩ» (hoặc dán link bài nhaccuatui), rồi bấm **🔎 Tìm & tải**.
- Tool tìm trên nhaccuatui, chọn bản đúng nhất (tránh remix/slowed/karaoke) và tải bản chất
  lượng cao. Tool lưu luôn link bài và **lời bài hát**.
- Không có lời trên nhaccuatui → tool tự tìm lời trên mạng (chỉ lấy câu hát, bỏ "Điệp khúc",
  hợp âm, "x2"…). Bài đó hiện **🌐 lời lấy trên mạng**; nên bấm **📝 Xem/sửa lời** liếc lại.
- Tool tự xuất bản đổi tempo (mặc định **4.5×**) để dùng cho Suno. Thanh **🎚 Tempo** dưới mỗi bài
  dùng để chỉnh tay.
- Thiếu đăng nhập nhaccuatui → bài hiện **🔑 Cần đăng nhập**. Đăng nhập xong bấm **↻ Thử lại**.

### ② Suno Cover
**Quy trình ✋ Bán thủ công** (mặc định, tick ở đầu tab):
1. **Tool:** upload bản tempo lên Suno, mở **Suno Editor**.
2. **Bạn:** chỉnh **Tempo** trong Editor (tool gợi ý số) → bấm **Save as New Song**.
3. **Tool:** mở bài vừa lưu → **Remix → Cover**, rồi điền form:
   - tên bài (không kèm ca sĩ), lời, Styles, giọng nam/nữ;
   - Max Mode, Weirdness 10, Style Influence 75, Audio Influence 50.
4. **Bạn:** xem lại form trong cửa sổ Suno rồi **tự bấm Create**. Mỗi bài ra 2 bản, khoảng 20
   credit.
5. **Tool:** tải 2 bản WAV về, tự nghe kiểm tra lỗi, master, rồi sang bài tiếp theo.

Các nút và tình huống khác:
- **🧪 Chạy thử (không bấm Create):** tool điền form cho 1 bài rồi dừng, không tốn credit. Nên
  chạy thử lần đầu.
- **Giọng** nam/nữ được tool đoán theo ca sĩ gốc. Đoán sai thì chọn lại ở ô **Giọng** trước khi
  chạy.
- **Captcha / hộp đồng ý điều khoản:** tool kêu «bíp» và đưa cửa sổ Suno lên trước. **Bạn tự
  bấm**, tool chờ rồi làm tiếp.
- **Kiểm tra lỗi:** tool báo **🔴 Lỗi** khi bản cover bị rè, cắt ngắn, mất tiếng hoặc im lặng.
  - Máy báo nhầm → bấm **✓ Nghe ổn**.
  - Bạn nghe thấy lỗi mà máy không báo → bấm **🚩 Báo lỗi**.
  - Muốn làm lại bản lỗi → bấm nút **🔁 Tạo lại** của bài. File lỗi được cất vào `ban_cover\_loi`,
    không bị xoá.
- **Lỗi sau khi đã bấm Create** (mất mạng…) → bấm **⬇ Tải lại 2 bản từ Suno**. Nút này chỉ tải
  về, không tốn credit lại.
- **Suno báo bản quyền:** bài được đánh dấu **⛔ Suno từ chối** (`rejected`), dữ liệu giữ nguyên,
  tool làm bài tiếp. Tool **không** sửa méo lời để né bộ lọc: lời luôn là chữ tự nhiên, không có
  dòng tên bài / ca sĩ.
- **🗑 Xoá bản này:** đưa bản cover vào thùng rác. File trên máy không bị xoá. **🗑 Thùng rác (N)**
  dưới mỗi bài cho phép nghe lại và **♻ Khôi phục**.

**🎚 Master** (khung bên trái tab ②): tải xong là tool tự master bằng ffmpeg.
- Kiểu master:
  - `natural`: −14 LUFS, chuẩn YouTube, mặc định;
  - `dynamic`: −16 LUFS, ít nén;
  - `loud`: −10 LUFS.
- **Lưu thành:** WAV / MP3 / cả hai.
- Nút **🎚 Master** / **↻ Master lại** cho từng bản, và cho tất cả.
- Bản master nằm ở `ban_cover\mastered\…_master.wav`. File gốc giữ nguyên.

#### Nhập bài cover có sẵn (kéo thả)
Dùng ô **📂 Kéo thả bài cover có sẵn** ở đầu tab ②:
1. **Kéo các file cover** (`.wav`, `.mp3`, `.flac`, `.m4a`) thả vào. Kéo nhiều bài một lúc được,
   kèm cả **file lời** `.txt` / `.lrc` cũng được.
   - Đặt tên file **Tên bài - Ca sĩ** (vd `Em gái mưa - Hương Tràm.wav`) để tool tự điền tên bài
     và ca sĩ.
   - Các bản `(1)`, `(2)` của cùng một bài được gom thành 1 bài.
   - File lời **cùng tên** tự gắn vào đúng bài.
2. Kiểm tra tên bài và ca sĩ. Mở **📝 Lời bài hát** để dán lời, hoặc kéo file lời thả thẳng vào
   dòng của bài đó.
3. Để nguyên 2 ô tick:
   - **Master + đồng bộ âm lượng**: mọi bài về **cùng một mức âm lượng**;
   - **AI căn lời ngay**.
4. Bấm **⬆ Nhập N bài**. Mỗi dòng báo ✅ khi xong.

Muốn nhập 1 bài kèm cả file bài gốc thì dùng ô **⬆ Nhập bài cover tôi đã làm sẵn** ở phía dưới.

### ③ Lời bài hát
- Bấm **🎤 Tạo lời bài hát**. Tool điền tên bài, ca sĩ, lời, rồi **AI căn từng câu theo nhạc**.
- **AI căn sai?** Bấm ▶ nghe câu đó, bấm **⏱ đây** đúng lúc câu bắt đầu (hoặc gõ lại giờ), rồi bấm
  **Lưu mốc thời gian**. Nếu cả bài lệch đều, dùng **-0.5s / -0.2s / +0.2s / +0.5s**.
- Mỗi bài có nút **⬇ .lrc** và **⬇ .srt**. Câu dài tự **xuống dòng, tối đa 8 từ/dòng**.
- Bật/tắt **sóng âm** trên video ở tab này.
- ⚠️ Mix xong là tool **tự làm video ngay**. Vì vậy hãy **căn lời xong rồi mới bấm Mix**.

### ④ Mix
- Ghép các bản cover thành 1 file nhạc dài. **Mỗi bài phát đúng 1 lần** theo thứ tự bạn xếp,
  crossfade mặc định 5 giây.
- Bài đã master thì dùng bản master, các bài được chỉnh to đều nhau.
- Mỗi bản mix trong **Mix History** có nút **Lời .srt (CapCut)**.

### ⑤ Video
1. **Ảnh:** tool viết prompt theo tên, ý tưởng và thể loại nhạc của project, rồi vẽ 3 ảnh (bằng
   ChatGPT; ChatGPT lỗi hoặc hết lượt thì tự chuyển Muse.ai):
   - **ảnh bìa** (không chữ);
   - **bảng nhân vật**;
   - **bảng bối cảnh**.

   Chọn **👤 Có 1 cô gái** hoặc **🏞️ Chỉ cảnh vật**.
2. **Thumbnail có chữ:** ChatGPT thêm tiêu đề lớn, dòng thể loại và danh sách bài (project từ 2
   bài).
3. **Clip động:**
   - **clip 00**: ảnh bìa «sống dậy», dùng làm phần giới thiệu;
   - **clip 01**: chuyển động nhẹ;
   - **clip 02–05**: 4 góc quay nhân vật.
4. **Dựng `final.mp4`:**
   - thumbnail mở đầu → clip 00 → các clip nối mềm đến hết nhạc;
   - **danh sách bài bên phải**, bài đang phát tô vàng;
   - **lời từng câu phía dưới**: câu dài xuống dòng tối đa 8 từ, các dòng cách nhau thoáng;
   - sóng âm sát đáy (nếu bật).

Các nút chính:
- **Tạo toàn bộ video**.
- **Tạo tiếp**: giữ cái đã có, làm phần còn thiếu.
- **Làm lại từ đầu**.
- **📂 Mở thư mục video final**.
- Tick **Tự động dựng video sau khi mix Audio xong** nếu muốn tool tự làm.

### ⑥ Duyệt & đăng
- **▶ Xem trước video** để tự duyệt.
- AI viết **tiêu đề + mô tả** (có mốc thời gian từng bài), đánh dấu *không dành cho trẻ em* và
  *có dùng AI*.
- Tool chỉ lưu **NHÁP** lên kênh đã chọn (qua GPMLogin) và **KHÔNG bao giờ tự công khai**. Bạn tự
  kiểm tra trên YouTube Studio rồi mới công khai.
- Tuỳ chọn tự động:
  - **Tự động đăng nháp sau khi render video xong**;
  - **Tự động tạo Short sau khi đăng nháp video dài xong**.

---

## File nằm ở đâu?

- Mỗi project có 1 thư mục trong `media\`:
  - `nhac_goc\`: bài gốc + lời;
  - `da_chinh_tempo\`: bản đổi tempo;
  - `ban_cover\`: bản cover (bản đã master nằm trong `ban_cover\mastered\`);
  - `nhac_mix\`: file mix `.wav` + lời `.srt`;
  - thư mục video: ảnh, clip, `final.mp4`.
- **Dùng file `.srt` trong CapCut:**
  - kéo file `.wav` / video vào, rồi kéo file `.srt` vào (**Văn bản → Nhập phụ đề**);
  - file `.srt` không lưu được khoảng cách dòng. Hãy chọn phụ đề → **Văn bản → Cơ bản → Khoảng
    cách dòng** → tăng thêm (vd +1) → **Áp dụng cho tất cả**.
- Project đã xoá được giữ trong **Thùng rác** vài ngày (nút ở trang Projects) để khôi phục.

## Khi có trục trặc

| Hiện tượng | Cách xử lý |
|---|---|
| Cửa sổ báo "Không mở được tool" | Chụp màn hình gửi người hỗ trợ (kèm `data\logs\app_server.log`) |
| Lỡ đóng cửa sổ khi đang chạy | Mở lại tool, vào project, bấm **🎧 Auto chỉ audio** / **🚀 Auto audio + video** để làm tiếp |
| Suno / nhaccuatui / ChatGPT đòi đăng nhập lại | **⚙️ Settings** → mở cửa sổ đăng nhập tương ứng, tự đăng nhập |
| File danh sách báo "Dòng sai định dạng" | Mỗi dòng / hàng phải là **Tên bài - Ca sĩ** (có dấu cách hai bên `-`), hoặc 2 cột Tên bài / Ca sĩ trong Excel |
| Kéo thả cover mà file lời không tự gắn | Đặt tên file lời trùng tên file nhạc, hoặc thả file lời vào dòng của bài |
| **⬇ .srt** báo "chưa có lời đã căn" | Dán lời cho bài rồi bấm **🤖 AI căn lời** ở tab ③ |
| Lời trên video lệch | Sửa mốc ở tab ③, rồi dựng lại video (tab ⑤) |
| Không thấy profile GPM | Mở GPMLogin, bật Local API, bấm **🔄 Tải lại profiles** |
| Upload YouTube lỗi | Kiểm tra profile GPM còn đăng nhập kênh, và không có tool khác đang dùng profile đó |
| Muốn lấy bản mới nhất | Đóng tool → bấm đúp `update.bat` (xem README) |
