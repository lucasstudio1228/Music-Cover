# Hướng dẫn cài đặt lần đầu — Tool Cover Nhạc

Làm 1 lần duy nhất. Tool cũ (meditation_mixer) KHÔNG bị ảnh hưởng.

## Bước 0 — Mở tool
1. Nhấp đúp `start.bat` trong thư mục `D:\Tools\Cover nhạc`.
2. Mở trình duyệt vào: http://localhost:8100
3. Vào 1 project bất kỳ (hoặc tạo project mới) → bấm nút **⚙️ Settings** ở góc trên bên phải.
   (Có chấm cam trên nút = chưa nhập API key.)

## Bước 1 — Nhập API key (để AI viết tiêu đề/mô tả YouTube)
Trong cửa sổ Settings, phần đầu tiên:
1. **API Key**: dán key của bạn.
   - Tool cũ đang dùng nhà cung cấp **shopaikey.com** → dùng lại được đúng key đó.
2. **API Base URL**:
   - Nếu dùng key shopaikey: `https://api.shopaikey.com/v1`
   - Nếu dùng key OpenAI gốc (bắt đầu bằng `sk-`): `https://api.openai.com/v1`
3. **Model**: `gpt-4.1` (giống tool cũ) hoặc `gpt-4o-mini` (rẻ hơn).
4. Bấm **🔌 Test API** → thấy báo thành công.
5. Bấm **Lưu API (OpenAI)**. Chấm cam trên nút Settings sẽ biến mất.

## Bước 2 — Đăng nhập ChatGPT (để vẽ thumbnail)
Vẫn trong Settings, kéo xuống phần thumbnail:
1. Để nguyên lựa chọn **ChatGPT web** (mặc định).
2. Bấm **🤖 Mở ChatGPT để đăng nhập** → một cửa sổ Chrome riêng của tool hiện ra.
3. Đăng nhập ChatGPT bằng **email + mật khẩu**.
   (Nút "Continue with Google" hay bị Google chặn trong cửa sổ tự động — tránh dùng.)
4. Khi đã thấy giao diện chat → quay lại tool bấm **✖ Đóng cửa sổ ChatGPT**.
5. Kiểm tra thấy dòng ✅ **Đã đăng nhập ChatGPT**.

Đây là cửa sổ Chrome RIÊNG của tool mới, không dính gì tới tool cũ.

## Bước 3 — Kết nối GPMLogin
### 3a. Trong phần mềm GPMLogin
1. Mở GPMLogin.
2. Tạo **1 profile mới** cho kênh YouTube mới (đặt tên dễ nhớ, ví dụ `Cover Nhac`).
3. Mở profile đó → đăng nhập **tài khoản Google của kênh YouTube MỚI** → vào studio.youtube.com kiểm tra đúng kênh → đóng profile.
4. Bật **Local API** trong phần cài đặt của GPMLogin (tool cũ đang dùng cổng **9495**).

### 3b. Trong tool
Settings → phần **📺 YouTube / GPMLogin**:
1. **GPMLogin Local API base URL**: `http://localhost:9495` (đã điền sẵn — giống tool cũ).
2. **Đường dẫn GPMLogin.exe**: có thể để trống.
3. Bấm **💾 Lưu cấu hình GPM**.
4. Bấm **🔌 Test kết nối / tải profiles** → danh sách profile GPM hiện ra là OK.

## Bước 4 — Ánh xạ kênh YouTube mới
Settings → bảng **Kênh YouTube — tên kênh → profile GPMLogin** → phần **➕ Thêm kênh mới**:
1. **Tên kênh \***: tên kênh mới của bạn.
2. **Profile**: chọn profile GPM vừa tạo ở Bước 3a.
3. **Ngôn ngữ**: chọn tạm `en-US` (mỗi project tự đổi theo ngôn ngữ Việt/Anh của video).
4. **#hashtag mặc định**: ví dụ `#cover #nhacviet #lofi`.
5. **Phong cách hình ảnh**: để `🎲 Tự gán` hoặc chọn kiểu bạn thích.
6. **Dòng nhạc** (Nhạc Việt, US-UK, Chinese, Japanese… hoặc tự nhập) và **thể loại gợi ý**: bỏ trống được — điền vào thì tool tự chọn đúng kênh cho project.
7. Bấm **➕ Thêm**.

Sau đó mỗi project chọn kênh này ở form **Tạo project mới** hoặc trong tab **⑤ Video**.
Nếu để **🤖 Tự chọn kênh**, tool chọn kênh theo **Dòng nhạc + Thể loại** của project: ưu tiên kênh cùng dòng nhạc (cùng cả thể loại thì càng tốt), rồi tới kênh chưa ghi dòng nhạc nhưng cùng thể loại. Dòng chữ nhỏ dưới ô chọn kênh cho biết tool sẽ chọn kênh nào.

## Bước 5 — Máy tạo video: Muse.ai / Google Flow (qua GPMLogin)
1. Trong GPMLogin: tạo profile cho Muse → mở → đăng nhập **muse.ai** → đóng.
   Muốn dùng Google Flow: tạo profile khác → mở → đăng nhập Google + vào **flow.google.com** 1 lần → đóng.
2. Trong tool: Settings → kéo xuống cuối, mục **🎬 Máy tạo video qua GPMLogin**:
   - **Máy tạo cảnh động (clip)**: chọn **Muse.ai** hoặc **Flow/Veo**.
   - **Profile GPMLogin cho Muse.ai**: chọn profile Muse.
   - **Profile GPMLogin cho Google Flow**: chọn profile Flow (để trống = Flow mở bằng Chrome riêng của tool).
   - **Máy vẽ ảnh nền**: để **Muse.ai** (dùng luôn profile Muse ở trên).
   - Bấm **💾 Lưu máy tạo video**.
3. Không thấy profile mới trong danh sách → bấm **🔄 Tải lại profiles**.

Tool dùng máy nào là theo đúng lựa chọn đã lưu ở đây.

## Bước 6 — Đăng nhập nhaccuatui (để tool tải nhạc gốc)
Chỉ cần làm 1 lần:
1. Bấm **⚙️ Settings** → mục **🎵 nhaccuatui — tải nhạc gốc** (hoặc trong project, tab **① Tải nhạc gốc**) → bấm **🔑 Mở nhaccuatui để đăng nhập**.
2. Một cửa sổ trình duyệt riêng của tool mở ra trang nhaccuatui.com → bạn **tự** bấm Đăng nhập và đăng nhập tài khoản của bạn (tool không nhập mật khẩu hộ).
3. Thấy dòng **✅ Đã đăng nhập** → bấm **Đóng cửa sổ**.

Chưa đăng nhập thì tool vẫn tìm được bài, lấy được link + lời, nhưng chưa tải được file nhạc (bài sẽ hiện **🔑 Cần đăng nhập** → đăng nhập xong bấm **↻ Thử lại**).

## Bước 7 — Đăng nhập Suno (để tool tự làm cover)
Chỉ cần làm 1 lần:
1. Bấm **⚙️ Settings** → mục **🎤 Suno — làm bản cover** (hoặc trong project, tab **② Suno Cover**) → bấm **🔑 Mở Suno để đăng nhập**.
2. Cửa sổ trình duyệt riêng của tool mở trang suno.com → bạn **tự** đăng nhập tài khoản Suno (tool không nhập mật khẩu hộ).
3. Thấy dòng **✅ Đã đăng nhập Suno** → bấm **✖ Đóng cửa sổ Suno**.

Cửa sổ này **tách riêng** với tool thiền cũ — đăng nhập ở đây không ảnh hưởng tool cũ.

## Bước 8 — Tự động master 2 bản Suno (ffmpeg)
Tải xong 2 bản cover → tool tự master ở chế độ nền (không làm chậm Suno):
- Kết quả ở `ban_cover\mastered\<tên bài>_master.wav` (WAV 24-bit 48 kHz). **File gốc giữ nguyên.**
- Nhật ký từng bài (độ to LUFS + đỉnh trước → sau, thời gian, lỗi nếu có): `ban_cover\mastered\_master.log`.
- Bài đã có bản `_master` → tự bỏ qua, không làm lại.
- Bấm **Mix** (tab ④): bài nào có bản `_master` thì tool ghép bản master (giữ độ to của preset), chưa có thì dùng bản gốc. Video làm từ bản mix nên cũng nghe bản master.

**Xem & điều khiển ngay trên giao diện (tab ② Suno Cover):**
- Dưới mỗi bản cover có dòng master: **🎚 Đã master · natural** + độ to trước → sau (LUFS) và trình phát để **nghe bản master**; hoặc **⏳ Chờ master… / 🎚 Đang master…**, **⚠ Master lỗi** (kèm lý do), **Chưa master**.
- Nút **🎚 Master** (bản chưa master — dùng được cho cả bài bạn tự nhập) / **↻ Master lại** (làm lại theo kiểu đang chọn; bản cũ chỉ bị thay khi bản mới xong). Bấm tay thì luôn chạy, kể cả khi đã tắt tự master.
- Khung **🎚 Master** bên trái: chọn **Kiểu master**, **Lưu thành** (WAV / MP3 / cả hai), bật/tắt **Tự master ngay sau khi tải 2 bản từ Suno**, nút **🎚 Master các bản chưa master** và **↻ Master lại tất cả**.

Các kiểu master:
- `natural` — mặc định, -14 LUFS (chuẩn YouTube)
- `dynamic` — -16 LUFS, ít nén, giữ độ nhấn nhá
- `loud` — -10 LUFS, to hơn (YouTube sẽ tự hạ về -14 khi phát)

Đổi kiểu chỉ áp cho lần master sau — bản đã master rồi thì bấm **↻ Master lại**. Các số chi tiết (EQ, nén…) vẫn sửa được trong `data\master_config.json` bằng Notepad; giao diện chỉ ghi 3 mục trên, không đụng số bạn đã sửa.

Máy chưa có ffmpeg → cửa sổ đen của tool báo «Không tìm thấy ffmpeg» kèm cách cài; tool vẫn tải nhạc bình thường, chỉ bỏ qua bước master. Cài xong ffmpeg → bấm **🔄 Kiểm tra lại ffmpeg** trong khung 🎚 Master (khỏi mở lại tool).

## Thứ tự làm 1 video cover (6 tab trong project)
① **Tải nhạc gốc** — gõ «Tên bài – Ca sĩ» (mỗi dòng 1 bài) → **🔎 Tìm & tải**.
   - Bài **không có lời trên nhaccuatui** → tool tự tìm Google «tên bài + ca sĩ + lyrics», chép **chỉ lời hát** (tự bỏ Chorus, Điệp khúc, ĐK, hợp âm, x2, tên nhạc sĩ…). Không thấy khung lời của Google thì tool mở vài trang lời bài hát và nhờ AI (API key ở Settings) lọc lời. Bài đó hiện **🌐 lời lấy trên mạng** → nên bấm **📝 Xem/sửa lời** liếc lại 1 lần.
   - Bài vẫn **0 câu lời** → bấm **🔎 Tìm lời trên mạng** để tìm lại, hoặc tự dán lời vào **📝 Xem/sửa lời**.
② **Suno Cover** — tool **tự làm cover trên Suno**: đính bài gốc → Cover, điền tên bài (không kèm ca sĩ), lời, giọng nam/nữ, các thông số trong bảng → bấm Create (mỗi bài ra 2 bản, ~20 credit) → tải cả 2 bản WAV về → tự nhập + kiểm tra lỗi.
   - **Lần đầu hãy bấm 🧪 Chạy thử (không bấm Create)**: tool điền form cho 1 bài rồi dừng, không tốn credit. Bạn nhìn cửa sổ Suno xem điền đúng chưa, rồi mới bấm **▶ Tạo cover trên Suno**.
   - Giọng nam/nữ: tool tự đoán theo ca sĩ gốc. Đoán sai → chọn lại ở ô **Giọng** của bài đó trước khi chạy.
   - Gặp **captcha** hoặc hộp **đồng ý điều khoản / xác nhận quyền** → tool kêu «bíp», đưa cửa sổ Suno lên trước và hiện khung đỏ trong tool. **Bạn tự bấm** trong cửa sổ Suno, tool chờ rồi làm tiếp.
   - Suno **từ chối bài gốc** (bản quyền) → bài hiện **⛔ Suno từ chối**, tool bỏ qua làm bài tiếp. Bài đó bạn tự xử lý rồi **⬆ Nhập file cover**.
   - Lỗi sau khi đã bấm Create (mất mạng, chưa tải được…) → tool nhớ 2 bản đã tạo. Bấm **⬇ Tải lại 2 bản từ Suno** — chỉ tải về, không tốn credit lại.
   - Làm tay trên Suno cũng được: tải về rồi **⬆ Nhập file cover** đúng bài.
   - Đã có sẵn bài cover + lời (không cần tải bài gốc)? Dùng khung **⬆ Nhập bài cover tôi đã làm sẵn** ở tab ②: điền tên bài, ca sĩ, chọn file cover, dán lời (hoặc mở file .txt/.lrc). Có file bài gốc thì chọn thêm để kiểm tra lỗi chính xác hơn.
   - Tool tự nghe từng bản cover và **báo 🔴 Lỗi** khi rè/nhiễu, bị cắt ngắn, mất tiếng giữa bài, vỡ tiếng hoặc im lặng. Máy báo nhầm → **✓ Nghe ổn**; bạn nghe thấy lỗi mà máy không báo → **🚩 Báo lỗi**.
   - Bản lỗi → **🔁 Tạo lại trên Suno**: file lỗi được cất vào thư mục `ban_cover\_loi` (không xoá), bài hiện **⏳ Chờ tạo lại** và **tool tự tạo lại trên Suno** (tốn ~20 credit). Bài thiếu file gốc hoặc thiếu lời thì tool báo thiếu gì — bổ sung xong bấm **↻ Làm lại trên Suno**.
③ **Lời bài hát** — bấm **🎤 Tạo lời bài hát** (ở tab ①) → tool điền lời + AI căn lời theo nhạc.
④ **Mix** — ghép các bài thành 1 file nhạc (mỗi bài phát 1 lần).
⑤ **Video** — ảnh + clip động + ghép video.
⑥ **Duyệt & đăng** — xem lại rồi lưu nháp YouTube.

## Lưu ý quan trọng
- **Không cho 2 tool dùng cùng 1 profile GPM cùng lúc** (ví dụ cả 2 tool cùng đang upload) — sẽ lỗi.
- **Tên project = tiêu đề in trên thumbnail** → đặt tên đẹp.
- Tool **tự làm video ngay sau khi mix** → hãy **căn lời xong (tab ③ Lời bài hát) rồi mới bấm mix**.
- Video chỉ được lưu **nháp** trên YouTube — bạn tự kiểm tra rồi mới công khai.
