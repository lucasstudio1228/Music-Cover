# Nhật ký thay đổi dành cho AI bảo trì

File này là nguồn bàn giao kỹ thuật cho Codex, ChatGPT hoặc AI khác tiếp tục sửa tool. Mục mới được nối ở đầu phần nhật ký, không chứa khóa API hay dữ liệu đăng nhập.

## 2026-11-09 00:24 +07:00 — Khôi phục tempo mặc định 4.5×

- **Yêu cầu:** Hủy thay đổi 3× và quay lại nguyên trạng tăng tempo 4.5×.
- **Nguyên nhân:** Người dùng quyết định giữ quy trình cũ sau lượt thử một bài mẫu.
- **File đã đổi:** `backend/cover/nct_jobs.py`, `backend/batch_service.py`, `frontend/src/components/cover/SourcePanel.tsx`, `frontend/src/components/projects/ProjectFormModal.tsx`, `tests/test_nct_source.py`, `AI_CHANGELOG.md`.
- **Trước:** Bài mới tải, workflow tự động và giao diện mặc định dùng 3×.
- **Sau:** Toàn bộ mặc định và mô tả workflow trở lại 4.5×; batch vẫn dùng chung `AUTO_TEMPO_FACTOR` để tránh lệch cấu hình.
- **Tác vụ ngoài:** Đã dừng an toàn lượt Suno mẫu đang chờ người dùng xác nhận quyền sử dụng bản ghi âm; không tiếp tục Create.
- **Kiểm thử:** `python -m unittest tests.test_nct_source tests.test_source_tempo tests.test_source_tempo_edges` — 46 test đạt; `npm run build` — TypeScript và Vite build thành công.
- **Triển khai:** Đã xuất lại đầu vào 4.5× cho bài mẫu #148, xác nhận không còn job hoạt động, restart backend và kiểm tra `AUTO_TEMPO_FACTOR=4.5`.
- **Tồn đọng:** Không. Lượt Suno mẫu không được tiếp tục sau hộp xác nhận quyền sử dụng.

## 2026-11-08 23:55 Nhận bài người dùng tự làm trên Suno (link/ID)

### Yêu cầu

- Người dùng đã tự làm bài trên Suno sau khi tool treo bài "Em Là Nhất Miền Tây", nhưng tool không nhận 2 bài mới.

### Nguyên nhân xác định

- Tool chỉ nhận bài qua `wait_for_new_songs`: chụp danh sách ID TRƯỚC khi chính tool bấm Create rồi lấy ID mới xuất hiện. Bài người dùng tự tạo trước lượt đó bị coi là bài cũ, và không có đường nào khác để gắn ID thủ công vào bài nguồn.
- Bấm «↻ Làm lại trên Suno» sau khi tự làm tay lại khiến tool Create thêm một lượt mới (log 23:40–23:43), không đụng tới bài tự làm.

### Thay đổi

- `backend/routers/sources.py`: `POST /sources/{id}/suno` nhận thêm `song_links` (link hoặc ID, tối đa 4). Tool lưu thành `suno_song_ids` và xếp hàng ở chế độ CHỈ TẢI: không Create, không điền form, không tốn credit; tải xong thì nhập cover + QC như bình thường.
- `frontend/src/api/sources.ts`, `frontend/src/components/cover/SunoCoverPanel.tsx`: thêm nút «🔗 Nhận bài làm tay trên Suno» trên từng bài.

### Kiểm thử

- `py_compile` đạt cho `sources.py`. Chưa chạy được test/UI trong môi trường sửa; cần kiểm tra trên máy.

### Tồn đọng

- Nếu bài dán vào cũng "failed to generate", bài quay lại trạng thái chờ nhập thủ công như mục trước.

## 2026-11-08 23:40 Bài Suno "failed to generate" (HTTP 404) → giữ chờ nhập thủ công

### Yêu cầu

- Sửa lỗi `RuntimeError: Không tải được bản nào từ Suno … HTTP Error 404` (bài "Em Là Nhất Miền Tây", project #26).
- Nếu lyrics bị Suno chặn thì treo bài đó lại để người dùng tự nhập thủ công.

### Nguyên nhân xác định

- Ảnh debug `create_error_232413.png` cho thấy trang bài Suno báo `This song failed to generate`; asset của 2 ID không tồn tại nên trả 404.
- Nhánh tải mới `download_asset_wav` (asset liên tục) không kiểm tra trạng thái failed như nhánh Studio cũ, nên 404 rơi vào lỗi chung và UI gợi ý «Làm lại» chỉ tải lại — vô ích.

### Thay đổi

- `backend/video/suno_driver.py`: thêm `_song_generation_failed()` (chỉ đọc trang `/song/<id>`); khi `download_asset_wav` lỗi và trang báo failed → ném `SunoGenerationFailed`. Import thêm `OperationCancelled`.
- `backend/cover/suno_jobs.py`: khi cả 2 bản failed to generate → trạng thái `rejected` với thông báo "⏸ Chờ nhập thủ công", xóa ID hỏng, không tự Create lại, không biến dạng lyrics; hàng đợi đi tiếp bài sau. Trước đây: `failed` + gợi ý Create lượt mới.
- Thêm `tests/test_suno_generation_failed.py`.

### Kiểm thử

- `py_compile` đạt cho 2 file sửa. Test mới chưa chạy được trong môi trường sửa (không có đủ dependency); cần chạy `python -m pytest tests/test_suno_generation_failed.py` trên máy.
- Không restart backend; nạp thay đổi ở lần restart an toàn khi `/api/tasks/active` rỗng.

### Tồn đọng

- Bài đang lỗi chỉ cần bấm «↻ Làm lại trên Suno» một lần sau khi restart: nhánh tải sẽ nhận ra failed và chuyển sang chờ nhập thủ công, không tốn credit.

## 2026-11-08 Lyrics Suno dùng khoảng trắng tự nhiên và xử lý từ chối bản quyền

### Yêu cầu

- Ngừng đổi khoảng trắng thành dấu `_` vì có thể làm Suno đọc sai lyrics.
- Có phương án rõ ràng khi Suno báo lyrics chứa nội dung có bản quyền.
- Từ nay mọi sửa đổi phải được ghi lại để AI khác biết lộ trình trước đó.

### Nguyên nhân xác định

- Workflow đang chạy thực tế đã dùng `normalize_for_suno` và ảnh lỗi cho thấy lyrics có khoảng trắng bình thường.
- Toast `Your lyrics contain copyrighted material` là từ chối theo bộ lọc bản quyền của Suno; đổi `_`, font nghệ thuật hoặc ký tự tương tự không phải cách sửa hợp lệ và không được dùng để né bộ lọc.
- Module tương thích cũ `chatgpt_lyrics.py` vẫn còn code mở ChatGPT và đổi space thành `_`, có nguy cơ được gọi lại bởi code/AI khác.

### Thay đổi

- Thêm `AGENTS.md` bắt buộc mọi AI ghi nhật ký sau mỗi lần sửa và bảo vệ job đang chạy.
- Viết lại `backend/cover/chatgpt_lyrics.py` thành lớp tương thích cục bộ: không mở trình duyệt, không gửi lyrics lên ChatGPT, chỉ gọi bộ chuẩn hóa `normalize_for_suno`.
- `safe_suno_transform` và alias cũ `local_artistic_transform` nay trả lyrics NFC với khoảng trắng tự nhiên; dữ liệu `_` cũ được đổi về khoảng trắng.
- `backend/cover/suno_jobs.py` bỏ executor ChatGPT lyrics không còn dùng; hàm tương thích `_transform_lyrics_isolated` cũng chỉ chuẩn hóa cục bộ.
- Dọn các chú thích cũ còn mô tả bước gửi lyrics sang ChatGPT để người bảo trì sau không hiểu nhầm workflow hiện hành.
- Khi Suno báo bản quyền, trạng thái bài là `rejected`; tool không obfuscate lyrics và không tự Create lại. Người dùng cần dùng lyrics/audio tự sáng tác hoặc có quyền sử dụng, hoặc bỏ qua/nhập cover hợp lệ thủ công.
- Cập nhật test lyrics theo hành vi mới.

### Tác động dữ liệu

- Không migration phá dữ liệu. Trước mỗi lượt Create mới, `lyrics_suno_text` luôn được tính lại từ `lyrics_text`, nên cache cũ có `_` tự được thay bằng bản dùng khoảng trắng.
- Các ID Suno đã Create vẫn chỉ đi qua nhánh tải lại, không tạo lại và không tốn credit.

### Kiểm thử

- Chưa restart backend trong lúc ghi thay đổi vì project #26 đang có hàng đợi Suno hoạt động.
- `py_compile` đạt cho `chatgpt_lyrics.py` và `suno_jobs.py`.
- Nhóm test lyrics, copyright, rejected và transform: **35 passed**, 59 test không thuộc bộ lọc bị bỏ qua; có 2 cảnh báo FastAPI deprecation không liên quan.
- Backend chưa được restart để không làm gián đoạn hàng đợi hiện tại; bản sửa sẽ được nạp ở lần restart an toàn sau khi job kết thúc.

## 2026-11-08 Ổn định nhạc cụ sáng tạo tự động

- Chế độ tự động chuyển từ lựa chọn mở của AI sang profile nhạc cụ ổn định theo genre.
- Nhạc cụ phụ bị khóa ở vai trò nền sustain/legato, theo groove hiện hữu; cấm off-grid hit, stab, nốt lặp, ostinato, arpeggio và attack giống bộ gõ.
- Suno Variety đổi từ Normal sang Off để tránh v6 tự viết lại style tags.
- Signature prompt tăng lên version 8 để cache cũ được viết lại.
- Kiểm thử prompt mục tiêu: 34 test và 14 subtest đạt; kiểm thử slider đạt.

## 2026-11-08 Footage màn hình và watermark

- Footage nằm trong TV/máy chiếu được cân màu cinematic, saturation 0.40, tăng tương phản, giảm sáng, thêm grain động và vignette.
- Watermark tên kênh bắt buộc ở góc trên bên phải từ 00:00 đến hết video, dùng font đã khóa.
- Backend đã được kiểm tra health sau lần nạp thay đổi.
## 2026-11-09 00:06 +07:00 — Đổi tempo đầu vào mặc định từ 4.5× xuống 3×

- **Yêu cầu:** Các bài gốc trước khi đưa sang Suno Cover chỉ tăng tempo 3× thay vì 4.5×.
- **Nguyên nhân:** Giá trị mặc định 4.5 được khai báo riêng ở hàng đợi tải nhạc, workflow tự động và giao diện nên có nguy cơ hiển thị và xuất file không đồng nhất.
- **File đã đổi:** `backend/cover/nct_jobs.py`, `backend/batch_service.py`, `frontend/src/components/cover/SourcePanel.tsx`, `frontend/src/components/projects/ProjectFormModal.tsx`, `tests/test_nct_source.py`, `AI_CHANGELOG.md`.
- **Trước:** Bài mới tải được tự động xuất WAV 4.5×; thanh tempo và mô tả workflow mặc định 4.5×.
- **Sau:** Bài mới tải và workflow tự động xuất WAV 3×; batch dùng chung `AUTO_TEMPO_FACTOR` để tránh lệch cấu hình; giao diện mặc định và mô tả hiển thị 3×. Các file 4.5× cũ không bị xóa hàng loạt, nhưng sẽ được xuất lại 3× khi bài đi qua bước chuẩn bị tempo/resume.
- **Kiểm thử:** `python -m unittest tests.test_nct_source tests.test_source_tempo tests.test_source_tempo_edges` — 46 test đạt; `npm run build` — TypeScript và Vite build thành công.
- **Triển khai:** Đã xác nhận `/api/tasks/active` không có job, restart backend an toàn và kiểm tra lại API hoạt động trên cổng 8100.
- **Tồn đọng:** Không. Các file 4.5× lịch sử vẫn được giữ để tránh xóa dữ liệu của người dùng.

## 2026-11-09 00:57 +07:00 — Phục hồi lyrics thủ công, fallback audio đa nguồn và thumbnail A/B

- **Yêu cầu:** Khi Suno chặn lyrics phải báo popup, tiếp nhận tự động 2 bản người dùng tạo thủ công và nối automation; tải nhạc phải chuyển Zing MP3 → YouTube Music/YouTube khi link hỏng; mọi video dùng 3 thumbnail YouTube A/B cùng hệ màu/bố cục nhưng khác style.
- **Nguyên nhân:** Worker cũ kết thúc ở trạng thái `rejected` và chỉ cho nhập file/link tay; `find_best` dừng tìm ngay khi một nguồn có metadata EXACT nên không giữ URL dự phòng; pipeline video chỉ tạo và tải một `thumbnail.png`.
- **File đã đổi:** `backend/cover/audio_sources.py`, `backend/cover/suno_jobs.py`, `backend/routers/sources.py`, `backend/video/thumbnail_ai.py`, `backend/video/service.py`, `backend/video/youtube_driver.py`, `frontend/src/api/sources.ts`, `frontend/src/components/cover/SunoCoverPanel.tsx`, `tests/test_song_match.py`, `tests/test_thumbnail_ai.py`, `AI_CHANGELOG.md`.
- **Trước:** Zing có kết quả nhưng URL hỏng có thể làm hết fallback; Suno copyright chỉ báo lỗi; YouTube nhận một thumbnail.
- **Sau:** Tool luôn thu thập ứng viên từ toàn bộ nguồn và thử tối đa 18 URL; popup copyright yêu cầu xác nhận lyrics tự sáng tác/được phép rồi worker chỉ theo dõi 2 ID mới (không bấm Create), tải WAV, master, nhập project và tiếp tục hàng đợi; video tạo ba ảnh A/B cinematic/editorial/spatial, khóa chung palette/layout/font/chữ lớn, từ chối bộ ảnh trùng, và bắt buộc thiết lập `Test & compare` trước khi lưu nháp YouTube.
- **An toàn:** Không obfuscate lyrics, không tự tạo lại nội dung bị chặn và không tự tiêu credit. Luồng theo dõi thủ công chỉ mở sau xác nhận quyền sử dụng lyrics. YouTube A/B dừng rõ ràng nếu kênh chưa bật Advanced features.
- **Kiểm thử:** `py_compile` cho 6 module backend đạt; `pytest tests/test_audio_sources.py tests/test_song_match.py tests/test_thumbnail_ai.py tests/test_suno_queue.py -q` đạt **57 passed**; `npm run build` đạt. Backend được restart sau khi `/api/tasks/active` xác nhận không có job và health check cổng 8100 thành công.
- **Tồn đọng/giới hạn:** Chưa có công cụ đáng tin cậy để tự nghe và quyết định “tempo nghệ thuật tốt nhất” trong Suno Editor; chỉ có thể đo BPM tham khảo. YouTube A/B phụ thuộc quyền Advanced features và selector giao diện Studio, nên lần chạy đầu cần quan sát xác nhận selector thực tế.

## 2026-11-09 01:32 +07:00 — Không còn báo sai 0/2 sau Create HTTP 200

- **Yêu cầu:** Kiểm tra và sửa ngay lỗi hàng đợi Suno dừng ở bài “Nặng Tình Hay Nhẹ Lòng” dù Create đã được Suno nhận.
- **Nguyên nhân:** Suno trả `/api/generate/` HTTP 200 nhưng thư viện đang có `Filters (3)` và virtual scrolling. `snapshot_song_ids()` chỉ đọc các link `/song/` đang render trong DOM nên không thấy hai bài vừa tạo, chờ đủ 300 giây rồi kết luận sai `0/2` và dừng toàn hàng đợi.
- **File đã đổi:** `backend/video/suno_driver.py`, `backend/cover/suno_jobs.py`, `tests/test_suno_captcha.py`, `AI_CHANGELOG.md`.
- **Trước:** UUID bài mới chỉ được phát hiện từ danh sách giao diện; HTTP 200 chỉ được dùng như tín hiệu “request thành công”, không cung cấp ID để tải.
- **Sau:** Driver đọc thụ động response `/generate`, chỉ trích UUID ở các trường ID (không lưu body/token/cookie), hợp nhất chúng với UUID từ DOM và tiếp tục tải ngay khi đủ hai ID. Worker cũng thử xoá bộ lọc trước snapshot như lớp dự phòng, nhưng không còn phụ thuộc vào việc xoá filter thành công.
- **An toàn credit:** Lượt HTTP 200 được tiếp nhận bằng ID từ chính response, không tự bấm Create lần hai. Response chỉ được đọc trong trình duyệt đã đăng nhập; không gọi API Suno bên ngoài và không lưu dữ liệu xác thực.
- **Kiểm thử:** `python -m pytest tests/test_suno_captcha.py -q` đạt **31 passed**, gồm test hồi quy `Filters (3)` + DOM rỗng + response có hai clip. `py_compile` đạt cho hai module sửa. Bộ rộng đạt 100 test và có 5 lỗi test cũ không liên quan (chuỗi prompt kỳ vọng cũ và fake tempo stepper thiếu API trình duyệt).
- **Triển khai:** Chờ kiểm tra `/api/tasks/active`, restart backend an toàn và phục hồi lượt HTTP 200 hiện tại mà không tạo lại nếu tìm thấy hai bài trong thư viện.


## 2026-11-09 02:05 +07:00 — Create bị menu Filters nuốt; trình duyệt đóng khi chờ tải lại

- **Yêu cầu:** Kiểm tra và sửa 2 lỗi: #149 «Em Là Nhất Miền Tây» báo "Không chắc Suno đã nhận lệnh Create… Sau Create 90s không có bài mới"; #151 «Lo Người Ướt Áo» báo `TargetClosedError: Page.wait_for_timeout`.
- **Nguyên nhân #149 (và #153 cùng nguyên nhân):** `_clear_library_filters` không xoá được Filters thì để nguyên menu Filters (Radix/Base UI, dạng modal) đang mở. Cú bấm Create sau đó chỉ làm đóng menu, không tới nút → Suno không nhận lệnh, không tốn credit. Ảnh debug `create_filters_not_cleared_*` + `create_not_accepted_*` xác nhận.
- **Nguyên nhân #151:** Bản 1 đã tải; bản 2 lỗi nên chờ 60 giây để tải lại. Cốc Cốc bị đóng giữa lúc chờ → `drv._wait` ném `TargetClosedError` ra ngoài, không đi qua nhánh mở lại trình duyệt → cả bài thành failed dù đã có bản 1 và đủ 2 ID.
- **File đã đổi:** `backend/video/suno_driver.py`, `backend/cover/suno_cover.py`, `backend/cover/suno_jobs.py`, thêm `tests/test_suno_create_click.py`.
- **Trước:** Create bấm thẳng dù còn menu mở/che nút; lỗi đóng trình duyệt trong lúc chờ tải lại làm hỏng cả bài.
- **Sau:**
  - `click_create` gọi `_prepare_create_click`: đóng mọi `[role=menu]/[role=listbox]` đang hiện bằng Escape (tối đa 3 lần), còn sót thì `_dismiss_popups`; cuộn nút vào khung nhìn; kiểm tra phần tử ở tâm nút Create (`elementFromPoint`) — bị che thì đóng popup lại và ghi log, vẫn bị che thì ghi CẢNH BÁO.
  - `_clear_library_filters` đóng menu bằng `_close_open_menus` ở cả nhánh thành công và thất bại.
  - `_download_all`: lúc chờ tải lại mà trình duyệt đóng → mở lại bằng `reopen_driver` rồi tải tiếp ID còn thiếu; không mở lại được thì giữ các bản đã tải, ghi lỗi cho ID còn thiếu (kết quả "Chỉ tải được n/2 bản", bấm tải lại sau, không tốn credit). Huỷ job (`OperationCancelled`) vẫn dừng ngay.
- **An toàn:** Không bấm Create thêm lần nào, không đổi lyrics, không đổi cách tải (tải qua Studio vẫn để sau theo yêu cầu người dùng).
- **Kiểm thử:** `tests/test_suno_create_click.py` 6 test (gồm 1 test JS chạy Chromium thật với menu đè nút Create) — đạt. Toàn bộ `unittest discover`: 1013 test, failures=5, errors=3 — đúng các lỗi cũ có từ trước (tempo master, wav_downloader thiếu pytest, tempo stepper, channel look, style Deep House/Ballad), không lỗi mới.
- **Tồn đọng:** Cần restart backend (khi `/api/tasks/active` rỗng) để áp dụng. Làm lại #149 và #153 bằng «↻ Làm lại»; #151 bấm tải lại 2 bản (không tốn credit). Lỗi "Không bắt được quyền audio từ player Suno" của bản 2 thuộc bộ tải trực tiếp — chờ việc chuyển hẳn sang tải qua Studio. Chưa thử LIVE trên Suno (không bấm Create thật).

## 2026-11-09 02:20 +07:00 — Bài bị Suno gỡ vì bản quyền (trang 404) không được nhận ra

- **Yêu cầu:** Người dùng báo: sau khi Suno báo lyrics dính bản quyền, tool không hiện popup để dán lyrics khác mà mở sang trang `suno.com/song/b5befdac…` báo 404 «Page not found».
- **Nguyên nhân:** #149 Create thành công (02:08), nhưng Suno chặn lyrics: bản `bb488f2a` báo «failed to generate», bản `b5befdac` bị gỡ hẳn (trang bài 404). `_song_generation_failed` chỉ nhận chữ «failed to generate», không nhận trang 404 → coi là lỗi tải thường, mở lại trang bài thêm 3 lượt × 60 giây (~6 phút) rồi mới chuyển `rejected` và hiện popup.
- **File đã đổi:** `backend/video/suno_driver.py` (`_JS_SONG_404`, `_song_page_missing`, `_song_generation_failed`, thông báo trong `download_asset_wav`), `backend/cover/suno_jobs.py` (log/thông báo bản bị gỡ), `tests/test_suno_generation_failed.py` (+3 test).
- **Trước:** Trang 404 → tải lại vô ích nhiều lần; thông báo cuối ghi sai «Cả 1/2 bản… đều failed».
- **Sau:** Trang bài có «404» + «Page not found» → nạp lại 1 lần cho chắc → vẫn 404 thì coi bản đó đã bị Suno gỡ (`SunoGenerationFailed`), không tải lại. Không bản nào tải được → bài `rejected` với lý do chặn lyrics/bản quyền → popup «Suno từ chối lyrics vì bản quyền» hiện ngay. Thông báo ghi đúng số bản.
- **An toàn:** Không tự Create lại, không đổi/biến dạng lyrics, không chạm bộ tải asset của người khác (`suno_wav_downloader.py`).
- **Kiểm thử:** Đoạn JS nhận 404 chạy trên trang Suno thật (`/song/b5befdac…`) → đúng; test Chromium với markup 404 và trang bài thường (có chữ «404 plays») → đúng. Toàn bộ `unittest discover`: 1016 test, failures=5, errors=3 — đúng các lỗi cũ, không lỗi mới.
- **Tồn đọng:** Cần restart backend (kiểm `/api/tasks/active` rỗng — hiện đang rỗng). #149 đã ở trạng thái `rejected` nên popup hiện được ngay cả khi chưa restart.

## 2026-11-09 02:41 — Sửa «Save as New Song nhưng không xác định được bài mới» + rút ngắn thời gian điền form Cover

- **Yêu cầu:** "lại lỗi. Ngoài ra tôi yêu cầu rút ngắn tất cả delay time ở bước paste xong lyrics, style quá lâu…" (lỗi #149: đã bấm Save as New Song nhưng không nhận ra bài mới, tool chưa bấm Create).
- **Nguyên nhân:**
  - Lỗi bài mới: `save_editor_as_new_song` chỉ nhận khi xuất hiện ĐÚNG 1 ID mới. Thư viện có nhiều bài «(#149) (Edit)» (các lần chạy trước), ảnh chụp `before` có lúc thiếu bài → nhiều ID «mới» → báo lỗi dù Suno đã lưu.
  - Chậm (đo LIVE, dry-run): gõ lyrics từng dòng ~13 giây; 3 thanh trượt ~34 giây vì kéo chuột luôn trượt trên giao diện mới (5 lần × ~6 giây mỗi thanh) rồi mới dùng phím, bấm phím qua Playwright ~0,14 giây/nấc; xoá Filters mặc định của Suno (không xoá được) ~7 giây mỗi lần.
- **File đổi:** `backend/cover/suno_cover.py` (`_JS_PASTE_TEXT`, `_JS_SONG_LINKS`, `_fold_title`, `_pick_saved_song`, `save_editor_as_new_song(title_hint)`, `prepare_editor_source`, `fill_song_lyrics`, `_clear_library_filters` + `_filters_stuck_at`), `backend/video/suno_driver.py` (`set_slider`, `_keyboard_slider`, `_JS_SLIDER_KEYS`, `_focus_slider`), test mới `tests/test_suno_fast_fill.py`. Backup: `*.bak33` (trước sửa nhận bài/lyrics), `*.bak34` (suno_driver.py, suno_jobs.py trước sửa thanh trượt).
- **Trước → sau:**
  - Nhận bài Editor: nhiều ID mới → chọn bài đầu danh sách (mới nhất) có tên «<tên file> … (Edit)»; trang Create thì dò lại tối đa 6 lần trước khi báo lỗi.
  - Lyrics: dán 1 lần bằng sự kiện paste (Lexical) → đọc lại khớp từng dòng; không khớp thì gõ từng dòng như cũ. 13 giây → 0,8 giây. Lyrics không bị đổi chữ (vẫn so khớp nguyên văn).
  - Thanh trượt: phím mũi tên trước (gửi trong trang, 1 nấc/khung hình, giới hạn 2,5 giây; thiếu thì bấm phím thật), kéo chuột chỉ dự phòng; đã đúng giá trị thì bỏ qua. 34 giây → 2 giây.
  - Filters mặc định (3) không xoá được: lần đầu thử như cũ, các lần sau cùng số lượng thì bỏ qua (tiết kiệm ~7 giây). Không lưu DOM khi chưa có thư mục _debug.
- **Kiểm thử:** Chạy thật trên Suno (dry-run, KHÔNG bấm Create, không ghi DB) từ bài Editor b43485df… của #149: form điền đủ, đọc lại Weirdness=10, Style Influence=75, Variety=0, Audio Influence=50, lyrics giữ đúng dòng/đoạn. `tests/test_suno_fast_fill.py` 12 test OK. Toàn bộ `unittest discover`: 1028 test, failures=5, errors=3 — đúng các lỗi cũ, không lỗi mới.
- **Tồn đọng:** Cần restart backend để áp dụng (kiểm `/api/tasks/active` rỗng trước). Chưa chạy lượt Create thật sau bản sửa. Chờ «Preparing song for playback» ~8 giây trước Remix nằm trong hàm dùng chung với tải Studio — chưa đổi.

## 2026-11-09 02:49 — Xác nhận Editor đã mở thật sau «Open in Editor»

- **Yêu cầu:** người dùng restart và chạy lại #149 → dừng hàng đợi lúc 02:43 «Không tìm thấy ô hoặc cụm nút Tempo/BPM trong Suno Editor».
- **Nguyên nhân:** ảnh `create_no_editor_tempo_024341.png` + DOM cho thấy URL vẫn `https://suno.com/create`, panel bên phải mở bài «Rượu Mừng Hóa Người Dưng». Menu ⋯ đóng ngay trước cú bấm «Open in Editor» → chuột trúng hàng bài khác. `_editor_from_open_menu` chỉ chờ 1,8 giây rồi coi như đã vào Editor, không kiểm tra. Không liên quan tới bản sửa lúc 02:41.
- **File đổi:** `backend/cover/suno_cover.py` (`_editor_from_open_menu`, mới `_wait_editor_url`), `tests/test_suno_upload_row.py` (cập nhật 1 test, thêm 2 test). Backup: Temp/.../bak37/.
- **Trước → sau:** Trước: bấm xong là coi như đã mở Editor. Sau: chờ tối đa 8 giây phải thấy URL `/edit/<id>`; không thấy → đóng popup, nếu trang đã đổi thì quay lại trang ban đầu, trả lỗi để vòng ngoài mở lại menu (tối đa 3 lần; hàng UPLOAD hết lượt thì upload lại như cũ). Backup bak34/bak37 dời ra thư mục Temp, không để trong mã nguồn.
- **Kiểm thử:** Chạy thật (không Save, không Create): mở Editor từ hàng UPLOAD #149 → URL `/edit/c6f38f33…`, thấy nút Save as New Song. `test_suno_upload_row` + `test_suno_fast_fill` 25 test OK. Toàn bộ: 1030 test, failures=5, errors=3 — đúng các lỗi cũ.
- **Tồn đọng:** Cần restart backend lần nữa (kiểm `/api/tasks/active` rỗng — hiện rỗng). Chưa có lượt Create thật sau các bản sửa 02:41/02:49.

## 2026-11-09 03:02 — Suno từ chối lyrics: hiện ngay popup dán lyrics khác, chặn Create lại lyrics cũ

- **Yêu cầu:** "ngay khi báo lần 1 copyright đã phải nhảy popup để tôi paste lyrics khác trước khi ấn create lần 2 rồi. Sửa lại".
- **Nguyên nhân:**
  - #149 bị Suno gỡ cả 2 bản lúc 02:15 (đánh dấu `rejected`). Nút «↻ Làm lại trên Suno» chỉ hỏi xác nhận rồi Create lại ĐÚNG lyrics cũ → lúc 02:52 Suno gỡ tiếp, mất credit.
  - Popup cũ chỉ nằm trong tab ② (ở tab khác thì không thấy), và không có ô dán lyrics mới — chỉ có «Để xử lý sau» / «theo dõi 2 bản làm tay».
  - Máy chủ không chặn: API chạy 1 bài và hàng đợi đều nhận bài `rejected`.
- **File đổi:**
  - `backend/routers/sources.py`: `SourceIn.authorized_lyrics`, hàm `lyrics_key`, kiểm tra trong `update_source`, chặn trong `suno_one`.
  - `backend/cover/suno_jobs.py`: `submit` bỏ qua bài `rejected` (trừ lượt theo dõi làm tay).
  - Mới `frontend/src/components/cover/RejectedLyricsDialog.tsx`; sửa `SunoCoverPanel.tsx` (bỏ popup cũ, nút bài bị từ chối), `pages/ProjectDetailPage.tsx` (gắn popup cấp trang), `SourcePanel.tsx` (lưu lời bài bị từ chối cần xác nhận quyền), `api/sources.ts`.
  - Test mới `tests/test_suno_rejected_lyrics.py`. Backup: Temp/.../bak38/.
- **Trước → sau:**
  - Trước: bài bị từ chối vẫn bấm «Làm lại» được, Create lại lyrics cũ.
  - Sau: bài `rejected` chỉ hết khoá khi lưu lyrics KHÁC (so bỏ qua hoa/thường, dấu câu, khoảng trắng, [Verse]) kèm xác nhận tự sáng tác/được phép. API «làm 1 bài» (kể cả chạy thử) trả 409, hàng đợi không nhận bài `rejected`.
  - Popup hiện ở MỌI tab trong vòng ~2 giây sau khi bài bị từ chối: có ô dán lyrics mới, ô xác nhận quyền, nút «💾 Lưu lyrics mới & tạo lại», «Chỉ lưu lyrics», «Tôi tự làm trên Suno — theo dõi 2 bản», «Để xử lý sau». Dán lại lyrics cũ → báo «giống hệt», nút tạo lại bị khoá.
  - Trong tab ②, bài bị từ chối hiện nút «✍️ Dán lyrics khác để làm lại» (mở popup) thay cho «↻ Làm lại»; «🧪 Chạy thử» bị khoá.
  - Tool không tự sửa/biến dạng lyrics.
- **Kiểm thử:**
  - `test_suno_rejected_lyrics` 9 test OK.
  - `tsc` + `vite build` OK.
  - Xem trên giao diện thật (không bấm Lưu/Create): popup #149 hiện ở tab ①; dán lyrics cũ viết hoa/giãn dòng → cảnh báo «giống hệt», nút tạo lại khoá; lyrics khác → nút mở; «Để xử lý sau» đóng; nút trong tab ② mở lại popup; không lỗi console.
  - Toàn bộ `unittest discover`: 1039 test, failures=5, errors=3, skipped=1 — đúng các lỗi cũ, không lỗi mới.
- **Tồn đọng:** Cần restart backend để áp dụng phần chặn phía máy chủ (giao diện mới đã có hiệu lực vì `frontend/dist` đã build). Kiểm `/api/tasks/active` rỗng trước khi restart.

## 2026-11-09 08:50 — Bảng cam bản quyền sau Create: popup dán lyrics ngay, tool tự điền lại & Create

- **Yêu cầu:** "ngày khi hiện ra bảng màu cam, tool phải báo popup về tool ngay để tự nhập lyrics, sau đó create ra và tự nhận diện" (ảnh: toast cam Suno «Couldn't generate that. Your lyrics contain copyrighted material. Please change it and try again.»).
- **Nguyên nhân:**
  - LIVE 08:40, #149: Suno trả ngay 2 ID trong phản hồi /generate rồi mới hiện bảng cam. `wait_for_new_songs` thoát vì đã đủ ID.
  - Regex toast trong `_JS_GEN_STATE` không có «couldn't generate»/«copyrighted».
  - Tool chờ mù 90 giây, cả 2 ID 404, đánh dấu `rejected` và sang bài sau. Popup chỉ hiện SAU khi form Suno đã bị bỏ.
- **File đổi:**
  - `backend/video/suno_driver.py`: regex toast trong `_JS_GEN_STATE` thêm `couldn.?t generate|copyrighted material`.
  - `backend/cover/suno_cover.py`: thêm `_JS_CREATE_NOTICES`, `_JS_CLOSE_CREATE_NOTICE`, `CoverDriver.create_rejection_text()`, `CoverDriver.close_create_rejection()`.
  - `backend/cover/suno_jobs.py`:
    - Hàm/hằng mới: `_create_and_watch`, `_await_replacement_lyrics`, `awaiting_lyrics`, `provide_lyrics`, `skip_lyrics`, `_beep_human`, `LYRICS_WAIT_SEC=1800`, `MAX_LYRICS_RETRIES=5`.
    - `status()` trả thêm `awaiting_lyrics`.
    - Vòng Create trong `_process` đổi theo luồng mới.
  - `backend/routers/sources.py`: thêm `POST /api/sources/{id}/suno/replacement-lyrics` và `.../replacement-lyrics/skip`.
  - Frontend: `frontend/src/api/sources.ts` (kiểu `awaiting_lyrics`, hook `useSunoReplacementLyrics`/`useSunoSkipLyrics`); `RejectedLyricsDialog.tsx` có chế độ «đang chờ» viền cam.
  - Test mới: `tests/test_suno_copyright_toast.py`.
  - Backup: Temp/.../bak40/, bak41/.
- **Trước → sau:**
  - Trước: bảng cam bị bỏ qua, form Suno bị bỏ, bài thành `rejected` sau ~90 giây.
  - Sau, phát hiện: sau Create, tool kiểm bảng cam lúc chờ ID và mỗi giây trong 90 giây chờ trước khi tải. Gặp bảng cam thì giữ nguyên form Suno, xoá 2 ID hỏng, báo «⛔ CẦN BẠN…» và kêu bíp. Popup cam hiện ở mọi tab trong ~2 giây.
  - Sau, popup: người dùng dán lyrics mới và tick xác nhận tự sáng tác/được phép, rồi bấm «🚀 Dán vào Suno & Create lại».
  - Sau, kiểm tra ở máy chủ:
    - Không nhận lyrics trống, chưa xác nhận, hoặc giống lyrics cũ (bỏ qua hoa/thường, dấu câu, [Verse]).
    - Lyrics dài quá 5000 ký tự bị từ chối.
    - Lyrics được chuẩn hoá NFC + `normalize_for_suno` (không dấu `_`, bỏ dòng tên bài/ca sĩ) rồi lưu vào bài.
  - Sau, Create lại: worker đóng bảng cam cũ, điền lyrics mới vào ô Lyrics, bấm Create, nhận diện 2 bản mới rồi tải như thường. Bảng cam cũ còn đọng không bị tính là lỗi mới; gặp bảng cam lần nữa thì lại hỏi.
  - Sau, bỏ qua / hết giờ: chọn «Bỏ qua bài này», chờ quá 30 phút, hoặc quá 5 lần thì bài thành `rejected`, giữ dữ liệu và sang bài tiếp theo. Bấm Dừng thì dừng ngay.
  - Tool không tự sửa/biến dạng lyrics.
- **Kiểm thử:**
  - `test_suno_copyright_toast` 18 test + `test_suno_rejected_lyrics` 9 test OK.
  - `tsc` + `vite build` OK.
  - Giao diện thật, giả lập `awaiting_lyrics` qua JS trong trình duyệt (không gửi, không Create): popup cam hiện đúng chữ Suno; nút gửi chỉ bật khi đã dán lyrics + tick xác nhận.
  - Lần chạy đầu bộ test đầy đủ làm hỏng 4 test `JobTests`: FakeDriver cũ không có `create_rejection_text`, và vòng chờ 90 giây tính theo đồng hồ thật nên chạy không ngừng với driver giả.
  - Đã sửa: thêm `_toast_text(drv)` dùng `getattr` (driver cũ → ''); vòng chờ đếm theo nhịp `drv._wait(1000)`.
  - Toàn bộ `unittest discover`: 1057 test, failures=5, errors=3, skipped=1 — đúng các lỗi cũ, không lỗi mới.
- **Tồn đọng:**
  - Cần restart backend để áp dụng (kiểm `/api/tasks/active` rỗng trước).
  - Chưa chạy thật trên Suno với lyrics mới (cần lyrics tự sáng tác/được phép của người dùng).
  - Nếu bảng cam tắt quá nhanh trước khi tool kịp đọc (<1 giây), vẫn rơi về đường cũ (404 → `rejected` + popup dán lyrics).

## 2026-11-09 09:10 — Bảng cam bản quyền: chỉ báo popup, người dùng tự sửa lyrics & tự Create; trả lại nút «↻ Làm lại trên Suno»
- **Yêu cầu:** "chỉ cần nếu bị Suno báo copyright thì báo để tôi nhập thủ công là được rồi. Nút chạy lại Suno của tôi đâu ?". Người dùng cũng yêu cầu khi dán lyrics phải giữ nguyên form/font, không đưa về NFC, giữ chữ nghệ thuật. Phần này KHÔNG làm vì AGENTS.md bắt buộc lyrics gửi Suno là Unicode NFC và cấm làm biến dạng lyrics để né bộ lọc bản quyền. Sau thay đổi này tool cũng không còn tự dán lyrics vào Suno nữa.
- **Nguyên nhân:**
  - Bản 08:50 bắt dán lyrics trong tool, rồi tool tự điền vào Suno và tự Create. Như vậy là thừa so với mong muốn của người dùng.
  - Bài bị từ chối (#149) bị thay nút «↻ Làm lại trên Suno» bằng «✍️ Dán lyrics khác để làm lại».
  - Hộp thoại dán lyrics tự bật mỗi lần mở trang.
- **File đổi:**
  - `backend/cover/suno_jobs.py`
  - `backend/routers/sources.py`
  - `frontend/src/api/sources.ts`
  - `frontend/src/components/cover/RejectedLyricsDialog.tsx` (viết lại)
  - `frontend/src/components/cover/SunoCoverPanel.tsx`
  - `tests/test_suno_copyright_toast.py`
  - `tests/test_suno_rejected_lyrics.py`
  - `frontend/dist` (build lại)
- **Trước:**
  - Có bảng cam thì worker chờ lyrics từ popup trong tool, sau đó `fill_song_lyrics` và tự bấm Create lại.
  - Có endpoint `/suno/replacement-lyrics`.
  - Bài `rejected` không có nút Làm lại, và server luôn trả 409.
- **Sau:**
  - Có bảng cam thì tool bíp, hiện popup cam trong tool và đưa cửa sổ Suno lên trước. Người dùng TỰ sửa lyrics và TỰ bấm Create trên Suno.
  - `_await_manual_create` cứ ~2 giây xem có 2 song ID mới không, lấy từ danh sách Suno hoặc response /generate, bỏ qua các ID cũ.
  - Thấy 2 ID mới thì vẫn canh bảng cam thêm 90 giây (`_create_and_watch(song_ids=...)`), rồi tải về như thường.
  - Tool không điền lyrics, không bấm Create.
  - Popup có hai nút:
    - «Đã hiểu — tôi tự Create trên Suno»: ẩn popup.
    - «Bỏ qua bài này» (`POST /suno/copyright-skip`): đánh dấu `rejected`, giữ dữ liệu, sang bài tiếp.
  - Hết 30 phút chưa thấy bản mới thì đánh dấu `rejected`. Bấm Dừng thì huỷ.
  - Đã xoá `provide_lyrics`, `ReplacementLyricsIn` và endpoint replacement-lyrics. Bỏ hộp thoại dán lyrics tự bật khi mở trang.
  - Nút «↻ Làm lại trên Suno» hiện lại cho bài `rejected`:
    - Hộp xác nhận cảnh báo chỉ làm lại khi lyrics là nội dung tự sáng tác/được phép, rồi gửi `authorized_lyrics: true`.
    - Server khi đó xoá trạng thái `rejected` và cho vào hàng đợi. Nếu không có xác nhận thì vẫn trả 409.
    - Hàng đợi hàng loạt vẫn bỏ qua bài `rejected`.
  - Nhãn trạng thái đổi thành «⛔ Suno báo bản quyền».
- **Kiểm thử:**
  - `tests.test_suno_copyright_toast` + `tests.test_suno_rejected_lyrics`: 29 test OK. Test mới:
    - chờ Create thủ công không đụng Suno;
    - trạng thái chờ / bỏ qua / hết giờ / dừng;
    - truyền sẵn ID thì bỏ bước chờ;
    - bảng cam hiện lại sau lần Create tay;
    - endpoint skip và endpoint dán lyrics đã bị xoá;
    - nút Làm lại có xác nhận thì được xếp hàng.
  - `tsc --noEmit` sạch; `npm run build` OK.
  - Toàn bộ `unittest discover`: 1059 test, failures=5, errors=3, skipped=1 — đúng các lỗi cũ, không lỗi mới.
  - Trình duyệt (dữ liệu giả, không bấm gì thật):
    - Bài #149 hiện lại «↻ Làm lại trên Suno».
    - Mở trang không còn tự bật hộp thoại.
    - Popup cam hiện đúng nội dung khi giả lập `awaiting_lyrics`.
- **Tồn đọng:**
  - Cần restart backend để áp dụng (kiểm `/api/tasks/active` rỗng trước).
  - Chưa chạy thật trên Suno.
  - Nếu bảng cam cũ vẫn đọng trên màn hình khi người dùng Create lại và Suno báo lại ngay, tool có thể không nhận ra lần báo mới cho tới khi bản đó lỗi lúc tải.

## 2026-11-09 09:35 — Sau bảng cam: nhận nhầm 1 bản bị Suno từ chối làm bản người dùng tự Create
- **Yêu cầu:** "sau khi báo lời bài hát dính bản quyền, tôi đã thay bằng lyrics khác và đã create ra 2 bài hát. Nhưng không thấy tool nhận diện… nhảy sang địa chỉ https://suno.com/song/36028d8b-… (404)". Người dùng cũng nhờ theo dõi để chuẩn hoá quy trình.
- **Nguyên nhân (theo log LIVE 09:14–09:17, bài #149):**
  - Tool bấm Create, 3 giây sau thì bảng cam hiện. Lúc đó tool chụp danh sách ID làm mốc.
  - ID của 2 bản bị từ chối tới MUỘN, sau khi đã chụp mốc. Khi người dùng tự Create, tool lấy «2 ID mới bất kỳ» nên ra 36028d8b (bản bị từ chối, 404) và b187f8d7 (bản thật).
  - Kết quả: chỉ nhập được 1/2 bản, bản thật thứ 2 bị bỏ sót.
  - Lỗi «Lo Người Ướt Áo» (TargetClosedError) trong ảnh là lỗi cũ lúc 01:48, không thuộc lượt này.
- **File đổi:**
  - `backend/video/suno_driver.py`: thêm `_gen_batches`. Mỗi response POST /generate ghi lại danh sách ID của đúng lượt đó (lượt lỗi ghi danh sách rỗng). Danh sách được xoá khi tool bấm Create.
  - `backend/cover/suno_jobs.py`: `_await_manual_create` chỉ nhận ID từ các response /generate SAU số request đã gửi trước lúc chờ. Mọi ID của lượt bị từ chối, kể cả ID tới muộn, đều bị loại.
    - Dự phòng: nếu đã thấy lượt Create của người dùng mà response không có ID, sau 60 giây tool dò danh sách và vẫn loại ID của lượt bị từ chối.
    - Driver cũ không có `_gen_batches` thì vẫn dùng cách dò danh sách như trước.
  - `tests/test_suno_copyright_toast.py`: thêm test tái hiện đúng tình huống ID bị từ chối tới muộn, và test driver ghi batch cho mỗi response /generate.
- **Trước:** nhận nhầm ID bị từ chối, nên tải 404 và chỉ nhập 1/2 bản.
- **Sau:** chỉ nhận đúng 2 ID của lượt Create người dùng tự bấm.
- **Kiểm thử:** `tests.test_suno_copyright_toast` + `tests.test_suno_rejected_lyrics`: 32 test OK. Toàn bộ `unittest discover`: 1062 test, failures=5, errors=3 — đúng các lỗi cũ, không lỗi mới.
- **Tồn đọng:**
  - Cần restart backend.
  - Bản thật thứ 2 của #149 (dòng trên cùng, 3:05, trong Workspace Suno) chưa được nhập. Người dùng dán link bài đó vào nút «🔗 Nhận bài làm tay trên Suno».
  - Chưa chạy LIVE lại.

## 2026-11-09 09:50 — Master lại khi bản cover bị Suno tải đè

- Yêu cầu: theo dõi lượt chạy LIVE bài #149 «Em Là Nhất Miền Tây» sau khi người dùng tự Create (bảng cam bản quyền) và chuẩn hoá quy trình.
- Kết quả LIVE: 09:28:46 nhận đúng 2 bản afbb1ec4, d0713a3b (sửa p46 hoạt động); 09:30 tải WAV 201.0s/200.0s, nhập thành «cover 3.wav», «cover 4.wav».
- Nguyên nhân lỗi mới: «cover 3/4.wav» ghi đè file cũ, nhưng `mastered/… cover 3/4_master.wav` (23:45 hôm trước, bài khác) vẫn còn → `already_mastered` chỉ xét file tồn tại nên log «đã có bản _master — bỏ qua», bản master là bài cũ.
- File đổi: `backend/cover/mastering.py` (thêm `_master_fresh`: bản _master cũ hơn file gốc = phải master lại; dùng cho `already_mastered` và vòng ghi từng định dạng), `tests/test_master_stale.py` (mới).
- Trước: file gốc bị thay vẫn giữ bản master cũ. Sau: bản master cũ hơn file gốc bị coi là chưa master → master lại.
- Kiểm thử: `tests.test_master_stale tests.test_mastering tests.test_cover_mix_master tests.test_master_ui tests.test_suno_cover` — 104 test, 4 fail + 1 error đều là lỗi cũ có sẵn trong baseline (style/tempo của test_suno_cover).
- Tồn đọng: backend đang chạy chưa nạp code mới (không restart khi chưa được phép); cover 3/4 của #149 cần bấm «↻ Master lại» thủ công. Bài 3:05 bị sót ở lượt 09:15 cần nhận qua «🔗 Nhận bài làm tay trên Suno».

## 2026-11-09 10:35 — Chế độ Suno BÁN THỦ CÔNG

- Yêu cầu: «phần chỉnh tempo và save as new song tôi sẽ làm, tool hãy nhập tất cả lyrics, style và thông số, create tôi sẽ bấm, sau đó lại automation workflow tiếp. Yêu cầu tool phải nhận diện workflow chuẩn».
- Nguyên nhân: người dùng muốn tự kiểm soát Tempo/Save và nút Create; tool làm phần còn lại.
- File đổi:
  - `backend/cover/suno_cover.py`: thêm `read_editor_tempo` (chỉ đọc), `wait_user_editor_save` (tool upload + mở Editor, bíp báo, chờ người dùng Save as New Song; nhận ID mới trên URL Editor hoặc bài «<tên file> … (Edit)» mới trong thư viện; ghi Tempo người dùng đặt vào `last_editor_tempo`); `prepare_cover` nhận `manual_editor/alert/manual_wait_sec`.
  - `backend/cover/suno_jobs.py`: `WORKFLOW_FILE=data/suno_workflow.json`, `get_workflow/set_workflow`, `status()["semi_manual"]`; tách `_poll_user_ids`/`_sent_count` từ `_await_manual_create`; thêm `_await_semi_create` (arm theo dõi /generate, bíp báo «tự bấm Create», nhận 2 ID của đúng lượt người dùng bấm; bảng cam → popup bỏ qua, loại ID lượt bị từ chối kể cả tới muộn, chờ Create lại; hết 30 phút → bài failed). `_process` ở chế độ bán thủ công không `_pace`, không `click_create`; sau đó vẫn canh bảng cam 90 giây, tải WAV, master, sang bài sau.
  - `backend/routers/sources.py`: `GET/PUT /api/sources/suno/workflow`.
  - `frontend/src/api/sources.ts` (`useSunoWorkflow`, `SunoWorker.semi_manual`), `frontend/src/components/cover/SunoCoverPanel.tsx` (ô «✋ Bán thủ công», nội dung hộp xác nhận).
  - `tests/test_suno_semi_manual.py` (mới, 11 test).
- Trước: tool tự chỉnh Tempo, tự Save as New Song, tự bấm Create. Sau: bật «✋ Bán thủ công» → người dùng làm 2 bước đó, tool tự nhận diện rồi chạy tiếp; tắt → như cũ.
- Tool không sửa lyrics và không bấm Create ở chế độ này; lyrics điền vẫn là bản chuẩn hoá NFC bước 6.
- Kiểm thử: `tests.test_suno_semi_manual tests.test_suno_copyright_toast tests.test_suno_rejected_lyrics tests.test_master_stale` 43 test OK; `npx tsc --noEmit` sạch; `npm run build` OK. Bộ test đầy đủ: 1073 test, failures=5 errors=3 skipped=1 — đúng 8 lỗi cũ có sẵn, không lỗi mới.
- Tồn đọng: backend chưa restart (cần người dùng restart khi không có job); chưa chạy LIVE.

## 2026-11-09 10:39 — Sửa lỗi lấy nhầm mã bài Suno (trang 404 liên tục)

- **Yêu cầu:** người dùng gửi ảnh Suno 404 `suno.com/song/30c274fe-…` — "kiểm tra lỗi này, bị liên tục".
- **Nguyên nhân:** `SunoDriver._on_response` coi mọi UUID nằm cạnh khóa `metadata`/`major_model_version` là mã bài. Response generate của Suno có object top-level (mã *task*) cũng có các khóa này → mã task bị lấy như mã bài, rồi danh sách bị sắp xếp ABC nên đôi khi chọn [task, 1 clip] → 404 + mất 1 bài thật (gặp 09:15 với 36028d8b và 10:34 với 30c274fe).
- **File đổi:** `backend/video/suno_driver.py` (`_on_response`), `tests/test_suno_captcha.py` (thêm test hồi quy).
- **Trước:** batch có thể chứa mã task + chỉ 1 clip thật.
- **Sau:** ID nằm trong danh sách `clips` được ưu tiên ("strong"); chỉ khi không có clip nào mới dùng ID dự phòng ("weak"). Giữ đúng thứ tự Suno trả về, không sắp xếp lại.
- **Kiểm thử:** `tests.test_suno_captcha tests.test_suno_semi_manual tests.test_suno_copyright_toast` → 66 OK. Full suite trước đó 1073 tests: 8 lỗi có sẵn từ trước, không liên quan.
- **Tồn đọng:** cần restart backend (khi không có job) để áp dụng; người dùng tự nhận lại bài thứ 2 của #153 và bài 3:05 của #149 bằng "🔗 Nhận bài làm tay trên Suno".

## 2026-11-09 16:21 — Sửa DuplicatePromptError "Prompt gemini[1] trùng project #19"

- **Yêu cầu:** ảnh chụp lỗi ở bước chuẩn bị prompt video — "kiểm tra lỗi và khắc phục".
- **Nguyên nhân:** `cover_scene.sheet_prompts` tạo prompt ảnh 1 (bảng nhân vật) bằng câu mẫu cố định, chỉ phụ thuộc kiểu nhân vật (nữ/nam/cặp đôi), không có chi tiết riêng của bài. Project nào cùng kiểu nhân vật cũng ra prompt giống hệt #19 → `prompt_catalog.claim_prompts` chặn.
- **File đổi:** `backend/video/cover_scene.py` (`sheet_prompts`), `tests/test_cover_single.py` (test mới).
- **Trước:** prompt bảng nhân vật giống nhau giữa các project → lỗi trùng, không tạo được ảnh.
- **Sau:** prompt bảng nhân vật thêm mô tả bối cảnh riêng của bài (chỉ để định mood trang phục/ánh sáng, nền bảng vẫn trơn). Không thêm mã ID, không nới bộ kiểm tra trùng. Hồ sơ prompt đã lưu của project cũ giữ nguyên.
- **Kiểm thử:** `tests.test_cover_single` → 33 OK (có test mới: 2 bối cảnh khác nhau → prompt khác nhau, cho nữ/nam/cặp đôi).
- **Tồn đọng:** cần restart backend khi không có job; sau đó bấm lại "Chuẩn bị / kiểm tra bộ prompt". Nếu AI không viết được bối cảnh và 2 project cùng thể loại rơi vào mẫu giống nhau thì vẫn có thể trùng; khi đó đổi ý tưởng hình ảnh của project.

## 2026-11-09 17:06 — Nút «🎬 Tạo video có footage» (footage ở cuối video)

- **Yêu cầu:** người dùng quên đưa footage vào; muốn có nút cạnh chỗ upload footage để tạo video có footage, footage đặt ở CUỐI và chiếu tới hết video.
- **File đổi:** `backend/video/assembler.py` (`assemble_video_blend` thêm `footage_at_end`), `backend/video/service.py` (`step_assemble` thêm `footage_at_end`), `backend/routers/video.py` (`POST /api/projects/{id}/video/footage/render`), `frontend/src/api/video.ts` (`useRenderWithFootage`), `frontend/src/components/video/VideoPanel.tsx` (nút), `tests/test_video_footage_end.py` (mới); build lại `frontend/dist`.
- **Trước:** footage chỉ được chèn 1 lần ngay sau phần mở đầu khi bấm Ghép video; không có nút riêng.
- **Sau:** nút mới (hiện khi đã có footage, cần đủ clip) ghép lại toàn bộ final.mp4: intro → cycle lặp → fade → footage (trong khung màn chiếu, nền là clip cuối) phát tới hết video; nhạc giữ nguyên độ dài; lyrics/tên bài vẫn in đè như cũ. Footage dài hơn video thì bị cắt cho vừa. Nút «Ghép video» thường giữ hành vi cũ.
- **Kiểm thử:** `tests.test_video_footage_end` (ghép thật bằng ffmpeg: video 30s, footage 5s → footage từ 25s tới hết, giữa video không có footage; API báo lỗi khi chưa có footage) + `tests.test_video_footage tests.test_video_workflow` → OK. `npm run build` OK.
- **Tồn đọng:** cần restart backend để có API mới. Chưa thử trên project thật (người dùng tự bấm).

## 2026-11-09 17:28 — Quy trình video có footage: clip AI chạy 1 lần, footage lặp tới hết video
- **Yêu cầu:** "mỗi video chỉ chạy 1 lần, riêng video có footage sẽ được loop chạy liên tục đến khi hết video. Footage có thể nhiều clip và sẽ chạy đi chạy lại. Nhớ chỉnh màu phim, giảm saturation và để nhiễu hạt film".
- **Nguyên nhân:** trước đó mỗi project chỉ giữ 1 footage, footage chèn 1 lần (sau intro hoặc ở cuối) còn các clip AI lặp vòng tới hết nhạc.
- **File đã đổi:** `backend/video/assembler.py` (`_present_footage`, `_closed_loop`, `assemble_video_blend(footage_paths=...)`, bỏ `footage_at_end`), `backend/video/config.py` (`footage_files`), `backend/video/service.py` (status `footage_list`, `step_assemble` dùng nhiều footage), `backend/routers/video.py` (upload thêm không thay file cũ, trùng tên tự đánh số; GET/DELETE `/footage?name=`), `frontend/src/types/index.ts`, `frontend/src/api/video.ts`, `frontend/src/components/video/VideoPanel.tsx`, tests `test_video_footage_end`, `test_video_footage`, `test_video_workflow`, `test_intro_scenery_mode`.
- **Trước:** 1 footage/project, upload mới thay file cũ; clip AI lặp vòng; footage chèn 1 lần.
- **Sau:** khi có footage: intro → mỗi clip AI chạy đúng 1 lần → chuyển mờ sang footage → tất cả footage (khung màn chiếu, màu phim, saturation 0.40, hạt film, vignette) nối thành vòng lặp khép kín, lặp tới hết nhạc. Không có footage: giữ nguyên hành vi lặp cũ. Giao diện cho upload nhiều file một lúc, xem/xoá từng footage, nút "➕ Thêm footage". Nút «🎬 Tạo video có footage» và «Ghép video» đều dùng quy trình mới khi có footage.
- **Kiểm thử:** `tests.test_video_footage_end` (ghép thật bằng ffmpeg: 4 clip × 4s, 2 footage đỏ/xanh lá, nhạc 30s → video 30s, footage bắt đầu < 16s, sau đó chỉ còn đỏ/xanh lá xen kẽ lặp lại; không footage vẫn lặp cũ; upload nhiều file + xoá theo tên) + `test_video_footage test_video_workflow test_intro_scenery_mode test_cover_single` → 95 test OK. `npm run build` OK.
- **Tồn đọng:** backend (port 8100) không phản hồi lúc kiểm tra — người dùng cần bật lại để có API mới. Chưa thử trên project thật. Nếu nhạc ngắn hơn tổng thời lượng clip AI chạy 1 lần thì footage không kịp xuất hiện (có log cảnh báo).

## 2026-11-09 17:33 — Upload footage báo "timeout of 30000ms exceeded"
- **Yêu cầu:** "lỗi khi upload footage" (ảnh chụp: `Final Gia Đình.mp4: timeout of 30000ms exceeded`).
- **Nguyên nhân:** axios client dùng timeout mặc định 30s cho mọi request; file footage lớn upload lâu hơn 30s nên trình duyệt báo lỗi và không làm mới danh sách (dù server vẫn nhận xong file).
- **File đã đổi:** `frontend/src/api/video.ts` (`useUploadFootage` dùng `timeout: 0`).
- **Trước:** upload footage > 30s bị báo lỗi, giao diện vẫn hiện "Chưa có footage".
- **Sau:** upload footage không giới hạn thời gian, xong thì danh sách tự cập nhật.
- **Kiểm thử:** `npm run build` OK; xác nhận qua API status project #26 rằng file `Final Gia Đình.mp4` (4:35) đã nằm trên server.
- **Tồn đọng:** người dùng cần tải lại trang (F5) để nhận bản giao diện mới.

## 2026-11-10 01:05 — Tách «Cover Audio Tool» + thư mục nhac_mix (1 file nhạc đã mix)
- **Yêu cầu:** (1) "Phần Audio đã tốt, giữ nguyên mọi setting, tách ra thành 1 tool riêng… lưu lại hết setting để người khác có thể tải về và sử dụng được ngay. Để ở trong folder Cover nhạc luôn" — người dùng chọn phạm vi ①②③④. (2) "cả tool chính và tool vừa tách ra cần thêm 1 folder gồm 1 file nhạc đã mix ra, không cần thiết phải có video".
- **Nguyên nhân:** muốn dùng/chia sẻ riêng phần làm nhạc; và muốn lấy file mix gọn mà không cần video.
- **File đã đổi (tool chính):** `backend/cover/mix_export.py` (mới), `backend/routers/mixes.py` (`_on_success` gọi `export_mix_audio`), `backend/mix_patch.py` (`_on_patch_success` cập nhật lại file), `tests/test_mix_export.py` (mới), `.claude/launch.json` (thêm cấu hình chạy thử `audio-tool`).
- **Thư mục mới:** `Cover Audio Tool/` — bản sao mã nguồn (backend, frontend có sẵn `dist`, các module gốc, requirements, install.bat, start.bat cổng 8200), `backend/edition.py` (AUDIO_ONLY), job_manager bỏ qua mọi job video/upload (chỉ cho "suno"), mixes không auto dựng video, batch_service coi "xong" = có mix.wav (Mix Set) / có file cover (bài lẻ). Giao diện bỏ tab ⑤ Video, ⑥ Duyệt & đăng và phần Settings Thumbnail/YouTube/Máy tạo video. `data/` kèm `master_config.json`, `suno_workflow.json`, `app.db` mới (địa chỉ API + model, KHÔNG có API key, 0 project). Không chép profile trình duyệt/cookie/login. Có `HUONG_DAN.md`, `AGENTS.md`.
- **Trước:** chỉ có tool đầy đủ; file mix nằm sâu trong `outputs/<pid>/<mix>/mix.wav`.
- **Sau:** mỗi lần mix/vá mix xong, `media/.../<project>/nhac_mix/<tên project>.wav` chứa đúng 1 file (hardlink, không tốn thêm dung lượng). Đã tạo sẵn cho project #14 và #26.
- **Kiểm thử:** `tests.test_mix_export tests.test_video_footage_end tests.test_video_workflow tests.test_cover_mix_master tests.test_mixset_create tests.test_cover_singles_batch tests.test_batch_create_guard` → OK. Chạy thử Cover Audio Tool (preview, cổng 8201 vì công cụ preview báo bận 8200 — kiểm tra lại 8200 trống): API title đúng, 0 project, setting API không có key, giao diện mở bình thường; batch/mix test chạy trên mã bản sao → OK. `npm run build` bản sao OK.
- **Tồn đọng:** tool chính cần restart backend (khi không có job) để tự tạo thư mục nhac_mix cho mix mới. Bản sao chưa chạy `install.bat` trên máy sạch. Bài lẻ (không mix) chưa có thư mục nhac_mix.

## 2026-11-10 — Đẩy Cover Audio Tool lên GitHub (MasterAudio)
- **Yêu cầu:** "bỏ bản cũ, cập nhật bản mới đầy đủ trên github: https://github.com/lucasstudio1228/MasterAudio".
- **Nguyên nhân:** repo đang chứa bản MasterAudio v1.0.0 cũ (app.py, audio_engine.py…).
- **File đã đổi:** `Cover Audio Tool/backend/models.py` — giá trị mặc định AppSettings = setting tool gốc (api_base_url shopaikey /v1, model gpt-4.1, thumb_engine pil, thumb_ai_enabled False) để bản tải từ GitHub (không có app.db) vẫn có sẵn setting. Repo: xoá file cũ, thêm toàn bộ Cover Audio Tool + `README.md` (từ HUONG_DAN.md + cách tải). Commit 07d4e58 trên nhánh main (commit thường, lịch sử cũ vẫn còn).
- **Trước/Sau:** GitHub có bản cũ → có Cover Audio Tool mới.
- **Kiểm thử:** kiểm tra danh sách file trong commit không có .db, profile trình duyệt, cookie, .env, media/outputs; quét chuỗi giống API key → không có. API GitHub liệt kê đúng file mới.
- **Tồn đọng:** chưa thử tải ZIP + install.bat trên máy sạch.

## 2026-11-10 — Thêm bản cài cho Mac (Cover Audio Tool / GitHub MasterAudio)
- **Yêu cầu:** "viết thêm file và hướng dẫn để cài cho mac trên github".
- **Nguyên nhân:** chỉ có install.bat/start.bat (Windows); Suno dùng đường dẫn Chrome của Windows.
- **File đã đổi (Cover Audio Tool):** `install_mac.command`, `start_mac.command` (mới, LF, quyền chạy +x trong git), `.gitattributes` (mới: .command LF, .bat CRLF), `HUONG_DAN.md` (mục Cài đặt trên Mac), `backend/video/config.py` (thêm `import sys`; trên macOS SITE_BROWSER["suno"] = Chrome trong /Applications). Repo GitHub: thêm các file trên + README.md cập nhật, commit 7d0484e.
- **Trước/Sau:** Mac không có cách cài → có script cài (Python 3.11 + venv + torch + requirements + Chromium, cảnh báo nếu thiếu ffmpeg) và chạy (cổng 8200, tự mở trình duyệt). Windows không đổi hành vi.
- **Kiểm thử:** `bash -n` 2 script OK; import backend.video.config OK trên Windows (SITE_BROWSER suno giữ đường dẫn Windows); kiểm tra file trên GitHub: xuống dòng LF, mode 100755.
- **Tồn đọng:** chưa chạy thử trên máy Mac thật; vài thông báo lỗi trong mã vẫn ghi đường dẫn kiểu Windows (.venv\Scripts).

## 2026-11-10 — Hỗ trợ Mac chip Intel (Cover Audio Tool / GitHub MasterAudio)
- **Yêu cầu:** "tạo hệ thống để sử dụng được cho máy Mac chip intel sau đó up lên github kèm hướng dẫn sử dụng".
- **Nguyên nhân:** PyTorch ngừng bản Mac Intel sau 2.2.2 (cần numpy<2); bản mới nhất của numba/llvmlite/cryptography/contourpy/sphn không có wheel macOS x86_64 cp311; demucs 4.1.0 đòi sphn>=0.1.12 (chỉ có wheel arm64). Phát hiện thêm: requirements.txt thiếu `stable-ts` (align.py dùng), và stable-ts kéo torchaudio bản mới không khớp torch.
- **File đã đổi (Cover Audio Tool):** `constraints-mac-intel.txt` (mới: torch/torchaudio 2.2.2, numpy 1.26.4, numba 0.62.1, llvmlite 0.45.1, librosa 0.11.0, cryptography 48.0.1, contourpy 1.3.3, sphn 0.1.4, demucs 4.1.0); `install_mac.command` (tự nhận chip qua platform.machine(): Intel → cài theo constraints + --prefer-binary, demucs/sphn --no-deps + deps của demucs; chip M → torch+torchaudio 2.5.1; cuối cùng kiểm tra import torch/numpy/librosa/demucs.api/stable_whisper/fastapi); `requirements.txt` (+stable-ts>=2.19.0); `install.bat` (torch kèm torchaudio==2.5.1; đổi sang CRLF); `start.bat` (CRLF); `HUONG_DAN.md` + README trên GitHub (cách xem chip, mục Mac chip Intel, cài thủ công cho macOS cũ, bảng lỗi thường gặp). Commit f9b555d.
- **Trước/Sau:** Mac Intel cài sẽ lỗi ở torch 2.5.1 → cài được bộ thư viện tương thích. Máy mới (mọi nền tảng) thiếu stable-ts → có.
- **Kiểm thử:** `bash -n install_mac.command` OK; `pip install --dry-run --platform macosx_12_0_x86_64 --python-version 3.11 --only-binary=:all: -c constraints-mac-intel.txt` với toàn bộ requirements (trừ gói chỉ có sdist thuần Python: demucs, stable-ts, panns_inference) → giải được hết, toàn bộ là bản cài sẵn. Kiểm tra README/constraints trên GitHub raw → đúng.
- **Tồn đọng:** chưa chạy thật trên Mac Intel/Mac chip M; demucs với sphn 0.1.4 dựa vào đường lùi ffmpeg khi sphn.read lỗi (chưa thử thực tế). requirements.txt của tool chính cũng thiếu stable-ts (chưa sửa tool chính).

## 2026-11-10 — Tool chính: bổ sung stable-ts vào requirements
- **Yêu cầu:** đồng ý thêm stable-ts vào requirements.txt của tool chính ("Yes, add it").
- **Nguyên nhân:** backend/cover/align.py dùng `stable_whisper` (bước ③ căn lời) nhưng requirements.txt không liệt kê → máy cài mới thiếu; stable-ts kéo torchaudio bản mới không khớp torch 2.5.1+cu121.
- **File đã đổi:** `requirements.txt` (+`stable-ts>=2.19.0`), `install.bat` (cài `torchaudio==2.5.1` cùng torch, cả nhánh CUDA và CPU).
- **Trước/Sau:** máy mới cài thiếu AI nghe lời → có. Máy hiện tại không đổi (đã có stable-ts 2.19.1, torchaudio 2.5.1+cu121). Không restart backend.
- **Kiểm thử:** kiểm tra nội dung file; không chạy cài đặt lại.
- **Tồn đọng:** không.

## 2026-11-11 01:58 — Lyrics trên video: chỉ câu đang hát, chữ nhiều màu
- **Yêu cầu:** "Phần Lyrics chạy theo nhạc, chỉ cần hiển thị câu đang hát, không cần câu trước câu sau. Sử dụng font chữ màu sắc hơn".
- **Nguyên nhân:** overlay lyrics hiện 3 dòng (câu trước mờ / câu đang hát trắng / câu kế mờ) + hé lộ câu sắp hát trong đoạn nhạc dạo.
- **File đã đổi:** `backend/cover/overlay.py` (bỏ dòng prev/next và PREVIEW_SEC, bỏ style LyDim; thêm LYRIC_PALETTES 4 bảng màu, `_gradient_text` tô màu từng ký tự, lớp hào quang `LyGlow` (viền mờ màu), fade 180/160 ms, chữ 62px, chuẩn hoá NFC; mỗi bài trong Mix Set một bảng màu), `tests/test_cover_single.py` (+test_lyrics_show_only_current_line_in_color). Ảnh xem thử: `outputs/_xem_thu_lyrics/bai_1.png`, `bai_2.png`.
- **Trước:** 3 dòng lời, chữ trắng.
- **Sau:** 1 dòng câu đang hát, chữ gradient (vàng→cam→hồng, xanh ngọc→xanh lá→tím, …) có viền tối + glow; font vẫn Segoe UI đậm (đủ dấu tiếng Việt).
- **Kiểm thử:** `tests.test_cover_single tests.test_video_workflow tests.test_video_footage_end` → 60 OK; render thử 2 khung hình bằng ffmpeg/libass → chữ tiếng Việt hiển thị đúng, nhiều màu.
- **Tồn đọng:** backend 8100 cần restart (hiện không có job) để video mới dùng kiểu lyrics mới; video đã dựng trước đó không đổi. Cover Audio Tool không dựng video nên không cần sửa.

## 2026-11-11 09:20 — Xuất lời bài hát .srt cho CapCut

- **Yêu cầu:** "chỉ cần xuất ra file để tôi tự chèn vào capcut… như hát karaoke, không cần tên bài, chữ ngoài luồng. Chỉ cần lời bài hát theo câu nhạc".
- **Nguyên nhân:** người dùng muốn tự chèn lời trong CapCut thay vì dùng lời đốt sẵn vào video.
- **File đã đổi:** `backend/cover/lyrics_export.py` (mới), `backend/cover/mix_export.py`, `backend/routers/cover.py` (endpoint `GET /api/cover/projects/{id}/lyrics-srt`, tuỳ chọn `?mix_id=`), `frontend/src/api/cover.ts`, `frontend/src/components/cover/CoverPanel.tsx`, `frontend/src/components/mixes/MixHistoryList.tsx`, `tests/test_lyrics_export.py` (mới, chỉ tool chính), `frontend/dist`. Cover Audio Tool: các file như trên + `HUONG_DAN.md`; GitHub MasterAudio commit `d8d4876` (thêm README).
- **Trước:** thư mục `nhac_mix` chỉ có 1 file .wav; lời chỉ có dạng đốt vào video hoặc .lrc từng bài (giờ theo file bài, không theo bản mix).
- **Sau:** mỗi lần mix xong, `nhac_mix/<tên project>.srt` được tạo cạnh file .wav (không bị dọn). File chỉ có lời (NFC, khoảng trắng tự nhiên), mỗi câu 1 phụ đề, mốc theo bản mix — cùng quy tắc với lớp lyrics video (đổi bài giữa crossfade, giữ câu thêm 2s nếu chưa tới câu sau). UTF-8 BOM + CRLF để CapCut/Windows đọc đúng tiếng Việt. Project bài lẻ chưa mix dùng thẳng lời của bài (mốc 0). Nút "⬇ Lời cho CapCut (.srt)" ở tab Lời bài hát, nút "Lời .srt (CapCut)" cạnh từng bản mix.
- **Kiểm thử:** `tests.test_lyrics_export tests.test_cover_single` → 35 OK; TestClient: #26 → 200, 173 câu, không chồng thời gian; #19 (bài lẻ) → 200; #14 (bài chưa căn lời) → 404 kèm hướng dẫn; mix_id sai → 404. Gọi `export_mix_audio` cho #26 → có cả .wav và .srt. `npm run build` OK ở cả 2 tool (bản copy build qua junction tạm tới node_modules của tool chính, đã gỡ).
- **Tồn đọng:** backend 8100 cần restart (khi không có job) mới có endpoint/nút mới; project chưa căn lời (vd #14) sẽ không có .srt. Lời đốt vào video vẫn giữ nguyên — chưa tắt.

## 2026-11-11 09:55 — Suno đổi nút ⋯ đầu trang bài («More options for <tên bài>»)

- **Yêu cầu:** "Kiểm tra project Lưu Niên - Jack J97, selector đang bị lỗi hoặc có thể giao diện Suno mới cập nhật".
- **Nguyên nhân:** log `_suno.log` của #27: upload xong → "Menu ⋯ của bài chưa mở đúng" 3 lần → dừng hàng đợi. Dò trực tiếp trang `/song/<id>` (script chỉ đọc, không Create/không tải): nút ⋯ đầu trang giờ có aria-label `More options for <tên bài>`; tool chỉ tìm đúng `More options` nên bỏ qua nút này và bấm ⋯ của bài trong "Similar songs" (menu chỉ có Share/Add to queue/…/Report, không có Edit). Ngoài ra khối đầu trang giờ chung tổ tiên với "Similar songs" nên phép thử "link /song/ của bài khác" loại nhầm nút đầu trang.
- **File đã đổi:** `backend/video/suno_driver.py` (`_MARK_HEADER_MORE_JS` khớp thêm `More options for…` và tin nút có tên bài; fallback theo hàng + kiểm tra trang bài dùng tiền tố `More options`), `backend/cover/suno_cover.py` (JS tìm hàng UPLOAD khớp thêm `More options for…`), `backend/video/config.py` (`song_more_options` thêm selector tiền tố). Áp dụng y hệt cho Cover Audio Tool; GitHub MasterAudio commit `372f483`.
- **Trước:** mở menu nhầm bài gợi ý → `SunoUIChanged: Không mở được menu ⋯` → dừng hàng đợi.
- **Sau:** dò lại trên Suno thật: tool chọn đúng nút ⋯ đầu trang (cạnh Play), menu có Remix/Edit/…; rê Edit → submenu có "Open in Studio" và "Open in Editor" (selector cũ vẫn khớp).
- **Kiểm thử:** script dò Suno (3 lần, chỉ đọc); 19 module test Suno: 16 lỗi FAIL/ERROR trùng khớp 100% với khi chạy bằng mã cũ (lỗi có sẵn, không lỗi mới).
- **Tồn đọng:** backend 8100 phải restart (đang không có job) mới dùng mã mới; chưa chạy lại toàn bộ luồng #27 (bán thủ công: cần người dùng chỉnh Tempo + bấm Create). 16 test Suno lỗi sẵn từ trước chưa xử lý.

## 2026-11-12 10:35 — Remix → Cover không ăn ngay sau «Save as New Song»: thử lại tối đa 3 lần

- **Yêu cầu:** "đang lỗi. Cho chạy và Claude giám sát để có quy trình chuẩn" (project #27 Lưu Niên - Jack J97, thẻ lỗi "Đã bấm Remix → Cover nhưng Suno không chuyển sang form Create").
- **Nguyên nhân:** log `_suno.log` + ảnh `_debug/create_remix_cover_no_navigation_101746.png`: lượt 1 tool bấm ⋯ → Remix → Cover chỉ ~11 giây sau khi người dùng bấm Save as New Song; menu Remix vẫn mở, Suno không nhận cú bấm (bài vừa lưu còn đang xử lý) → tool dừng cả hàng đợi ngay. Lượt chạy lại (10:19) cùng bài đó: bấm Cover → chuyển sang `/create?remix_clip=<id>&remix_type=cover` trong 1 giây, form điền đủ lyrics/style/thanh trượt. Selector không sai, chỉ thiếu bước chờ/thử lại.
- **File đã đổi:** `backend/cover/suno_cover.py` (`_remix_cover_from_library` lặp tối đa 3 lần qua hàm mới `_remix_cover_once`; giữa các lần: Escape đóng menu, chờ 15s rồi 30s, tải lại trang bài, chờ hết "Preparing…"; mỗi lần hỏng lưu ảnh `remix_cover_no_navigation_try<N>`), `tests/test_suno_semi_manual.py` (+`RemixCoverRetryTests`: lần 2 thành công; 3 lần hỏng → báo lỗi, không tự `goto`). Cover Audio Tool và GitHub MasterAudio: cùng sửa `suno_cover.py` + mục "Quy trình chuẩn Suno Cover" trong `HUONG_DAN.md`.
- **Trước:** 1 lần bấm Cover không chuyển trang → dừng cả hàng đợi, người dùng phải bấm chạy lại.
- **Sau:** tool tự chờ và bấm lại (tổng tối đa ~2 phút); vẫn không tự điều hướng /create (tránh mất audio nguồn), vẫn không bấm Create.
- **Kiểm thử:** `tests.test_suno_semi_manual` → 12 OK; 19 module test Suno: 269 test, 16 FAIL/ERROR đều là lỗi có sẵn từ trước (không có lỗi mới). Theo dõi trực tiếp lượt chạy #27: Remix → Cover OK, form Cover đã điền, đang chờ người dùng bấm Create.
- **Tồn đọng:** backend 8100 phải restart khi KHÔNG có job mới dùng mã mới (hiện đang có job #27). Tempo trong Editor vẫn "không đọc được" lúc Save (đọc được sau ở form: 32 BPM). 16 test Suno lỗi sẵn chưa xử lý.

## 2026-11-12 11:05 — Lô sản xuất Track lẻ giữ cả 2 bản Suno

- **Yêu cầu:** "Tool hiện chỉ nhận 1 bản" → người dùng chọn «Giữ cả 2 bản».
- **Nguyên nhân:** `_cover_chain` trong `backend/batch_service.py` cố ý giữ bản đầu và đưa bản thứ 2 của mỗi bài vào thùng rác track ("mỗi dòng = đúng một bài"). Project #27 Lưu Niên: Suno tạo/tải/master đủ 2 bản nhưng `Lưu Niên - cover 2.wav` bị chuyển vào thùng rác lúc 10:25.
- **File đã đổi:** `backend/batch_service.py` (bỏ bước đưa bản 2 vào thùng rác khi project là `single`; Mix Set giữ quy tắc cũ để mix không phát một bài 2 lần; hàm mới `_first_cover_audio` để video Track lẻ luôn dùng bản 1 thay vì file có mtime mới nhất), `tests/test_cover_singles_batch.py` (+`FirstCoverAudioTests`). Cover Audio Tool + GitHub MasterAudio: cùng sửa `batch_service.py`. Dữ liệu: khôi phục `Lưu Niên - cover 2.wav` vào #27 bằng API `POST /api/projects/27/tracks/recovery/restore` (trash id 48).
- **Trước:** Track lẻ chạy theo lô chỉ còn 1 bản trong project; bản 2 nằm trong thùng rác.
- **Sau:** Track lẻ giữ đủ 2 bản (cover.wav vị trí 1, cover 2.wav vị trí 2); video, lời .srt và tên bài vẫn theo bản 1. Mix Set không đổi.
- **Kiểm thử:** `tests.test_cover_singles_batch tests.test_continue_chain tests.test_track_recovery tests.test_suno_semi_manual` → 34 OK. #27 sau khôi phục có 2 CoverSong cùng source 167.
- **Tồn đọng:** backend 8100 cần restart (hiện không có job) để dùng mã mới (cả bản sửa Remix → Cover). Job dựng video #27 đang ở trạng thái "Đã huỷ" — cần bấm chạy tiếp.

## 2026-11-12 10:45 — Chạy auto 2 kiểu (Audio + Video / Chỉ audio) + nút mở thư mục audio/video trên máy

- **Yêu cầu:** "Chạy auto có 2 kiểu, auto làm cả audio và video. Chạy auto chỉ audio. Sau khi tạo xong audio, lời bài hát sẽ có nút ấn vào thư mục trên máy tính để nghe. Video sau khi render xong cũng vậy, có nút bấm vào thư mục trên máy tính để xem final".
- **Nguyên nhân:** lô Mix Set/Track lẻ và nút 🚀 luôn chạy tới final.mp4 + nháp YouTube, không có cách dừng ở audio; tool chưa có nút mở thư mục trên máy (chỉ có nút tải file qua trình duyệt).
- **File đã đổi:**
  - `backend/batch_service.py`: `create_cover_mixset`/`create_cover_singles` nhận `audio_only` (lưu `params_json.audio_only`, project `auto_video/auto_upload = not audio_only`); hàm mới `_is_audio_only`, `set_audio_only`, `audio_folder`, `_verify_audio`; `_cover_chain` ở chế độ Chỉ audio dừng sau master (Track lẻ) hoặc sau ghép mix không dựng video (Mix Set); `_verify_product` chấm xong theo audio khi lô Chỉ audio.
  - `backend/routers/projects.py`: form `/mixset`, `/singles` nhận `audio_only`; endpoint mới `GET /api/projects/{id}/folders`, `POST /api/projects/{id}/open-folder?what=audio|video` (mở File Explorer; video chọn sẵn final.mp4).
  - `backend/routers/tasks.py`: `/api/tasks/auto-run?audio_only=` — đổi chế độ lô có sẵn, Chỉ audio thì không dựng video.
  - Frontend: `types/index.ts`, `api/projects.ts` (`useProjectFolders`, `useOpenProjectFolder`), `api/tasks.ts`, `TaskBar.tsx` (2 nút «🎧 Auto chỉ audio» / «🚀 Auto audio + video»), `ProjectFormModal.tsx` (chọn «Kiểu chạy auto»), `CoverPanel.tsx` (nút «📂 Mở thư mục nghe audio» ở tab ③ Lời bài hát), `VideoPanel.tsx` (nút «📂 Mở thư mục video final»).
  - Test mới `tests/test_audio_only_mode.py` (chỉ tool chính).
- **Trước:** auto luôn làm cả audio + video; muốn nghe/xem phải tự tìm thư mục media.
- **Sau:** chọn được Audio + Video (mặc định, như cũ) hoặc Chỉ audio khi tạo lô và ở thanh tác vụ; nút mở thư mục chỉ hiện khi đã có audio / final.mp4.
- **Kiểm thử:** `tests.test_audio_only_mode` + `tests.test_cover_singles_batch` 15 OK; 8 module project/task (gồm `test_tasks_auto`) 64 OK. `npm run build` OK (tool chính, Cover Audio Tool). Kiểm tra trên server thử cổng 8101: nút mở thư mục audio của #27 → POST open-folder 200; nút video final hiện ở #19; form tạo lô hiện lựa chọn Kiểu chạy auto; không tạo lô thật.
- **Tồn đọng:** backend 8100 phải khởi động lại (khi không có job) mới có endpoint mới — trước đó nút «Auto chỉ audio» gửi tới backend cũ sẽ bị bỏ qua tham số và chạy cả video. Cover Audio Tool (8200) cũng cần khởi động lại.

## 2026-11-12 11:40 — Tab Suno Cover: nút «🗑 Xoá bản này» cho từng bản cover + thùng rác khôi phục theo bài

- **Yêu cầu:** "phần này có nhiều bản, thêm nút chức năng xoá bản nào không sử dụng. Để ở thùng rác, có thể phục hồi" (danh sách Bài gốc → bản cover, vd Lưu Niên có 4 bản).
- **Nguyên nhân:** mỗi bài có nhiều bản Suno nhưng tab Suno Cover chỉ có «Báo lỗi»/«Tạo lại», không có cách bỏ bản không dùng; thùng rác track đã có ở backend nhưng chỉ dùng được ở phần thêm file nhạc.
- **File đã đổi:**
  - `backend/routers/tracks.py`: `/tracks/recovery` trả thêm `source_id` cho mỗi mục (hàm mới `_snapshot_source_id`); `_orphan_cover_files` bỏ qua file đang nằm trong thùng rác (trước đó 1 bản đã xoá hiện trùng 2 lần: mục thùng rác + "file cũ").
  - `frontend/src/api/tracks.ts`: kiểu `source_id`; xoá/khôi phục track làm mới luôn query `sources` và `cover-songs`.
  - `frontend/src/components/cover/SunoCoverPanel.tsx`: nút «🗑 Xoá bản này» ở mỗi bản cover (hỏi xác nhận, khoá khi bài đang chạy Suno); khối «🗑 Thùng rác (N)» dưới mỗi bài: nghe thử, «♻ Khôi phục» từng bản, «♻ Khôi phục tất cả».
  - Test: `tests/test_track_recovery.py` thêm `test_delete_one_cover_version_then_restore_it` (chỉ tool chính).
- **Trước:** không xoá được từng bản cover ở tab Suno Cover.
- **Sau:** xoá bản không dùng → vào thùng rác (file trên máy giữ nguyên), khôi phục lại đúng vị trí/bài gốc/lời. Bài đã «Loại bài» vẫn khôi phục bằng nút của bài như cũ (không hiện thùng rác riêng).
- **Kiểm thử:** `tests.test_track_recovery` + `tests.test_audio_only_mode` 9 OK. Chạy thêm 6 module cover: lỗi chỉ nằm ở `tests.test_suno_cover` (FakeDriver thiếu tham số `manual_editor` — test cũ từ trước, không liên quan thay đổi này). `npm run build` OK. Server thử 8101: project #27 hiện 4 nút «🗑 Xoá bản này»; không xoá dữ liệu thật.
- **Tồn đọng:** khởi động lại backend 8100/8200 khi rảnh để có `source_id` (trước đó khối thùng rác theo bài chưa hiện, nút xoá vẫn chạy). Cập nhật FakeDriver trong `tests/test_suno_cover.py` cho tham số `manual_editor`.

## 2026-11-16 17:20 — Mở tool bằng cửa sổ ứng dụng .exe thay vì trình duyệt localhost

- **Yêu cầu:** "Đưa giao diện về ứng dụng .exe thay vì chạy trên trình duyệt local host".
- **Nguyên nhân:** `start.bat` mở cửa sổ đen + tab trình duyệt; đóng nhầm tab/cửa sổ dễ rối.
- **File đã đổi:** mới `app_window.py` (cửa sổ pywebview/Edge WebView2, tự bật server ẩn trên cổng đọc từ `start.bat`, chờ sẵn sàng rồi nạp giao diện, đóng cửa sổ thì tắt cả cây tiến trình server; đang có việc thì hỏi lại; server mở sẵn bằng start.bat thì chỉ gắn vào, không tắt; giữ localStorage ở `data/webview`; cho phép tải file; tự cài pywebview nếu thiếu), `launcher_exe/Launcher.cs` + `build_exe.bat` (exe 29 KB build bằng csc có sẵn của Windows, tìm `.venv` cạnh exe hoặc thư mục cha), `launcher_exe/app.ico`, `make_icon.py`; `CoverNhacTool.exe`; `requirements.txt` thêm `pywebview>=6,<7` (chỉ Windows). Đã cài pywebview 6.2.1 vào `.venv` của tool chính (thêm 5 gói mới, không nâng cấp gói cũ). Tạo lối tắt Desktop «Cover Nhac Tool», «Cover Audio Tool».
- **Trước:** chạy bằng start.bat + trình duyệt. **Sau:** bấm đúp exe/lối tắt → cửa sổ ứng dụng; start.bat vẫn dùng được.
- **Kiểm thử:** bản sao thử cổng 8299 (DB trống): exe mở cửa sổ «Cover Audio Tool» phóng to, server sẵn sàng sau ~3 giây, giao diện hiện đúng, có icon; gửi lệnh đóng cửa sổ → server và tiến trình con tắt hết. Kiểm tra logic đóng: đang có việc + Huỷ → không đóng; OK → đóng; không có việc → đóng không hỏi; server mở sẵn → không hỏi, không tắt. Lối tắt Desktop trỏ đúng đường dẫn có dấu.
- **Tồn đọng:** chưa mở thử bằng dữ liệu thật (không tự bật tool thật); chưa thử nút tải file thật trong cửa sổ. Bản Mac vẫn dùng trình duyệt. Chưa đưa lên GitHub.

## 2026-11-17 — Đưa tính năng mới của bản tách (MasterAudio) sang tool chính + lời bài hát xuống dòng 8 từ/dòng

- **Yêu cầu:** "update với cả tool chính" (3 tính năng đã làm ở bản tách: tạo project không chạy auto, kéo thả bài cover có sẵn + master/đồng bộ âm lượng + file lời, danh sách bài từ Excel) + "phần lyrics đang hiện cả câu dài trên 1 dòng. Sửa chỉ để 8 từ trên 1 dòng, khoảng cách các dòng +1 (không được xít nhau quá)".
- **Nguyên nhân:** tool chính chưa có các tính năng trên; lời trên video bị thu nhỏ cỡ chữ để nhét cả câu vào 1 dòng (WrapStyle 2), file .srt cũng 1 dòng/câu.
- **File đã đổi:**
  - Mới `backend/song_list.py` (đọc .txt/.docx/.doc/.xlsx/.xlsm/.xls/.csv).
  - `backend/routers/projects.py`: `_read_mixset_lines` dùng `song_list`; mới `POST /api/projects/from-list` (tạo project + bài trạng thái «stopped», nhận cả thông số video: kênh, kiểu ảnh, chủ đề, intro, nhân vật, cảnh, thời lượng mix; `auto_video`/`auto_upload` tắt tới khi bấm chạy auto).
  - `backend/routers/sources.py`: nhập cover có `auto_master` / `auto_align`.
  - `backend/routers/cover.py`: mới `GET /api/cover/songs/{id}/srt`.
  - `backend/project_progress.py`: project chưa có bước nào xong hiện «Chưa bắt đầu».
  - `backend/cover/lyrics_export.py`: mới `wrap_lyric()` (tối đa 8 từ/dòng, chia đều); `build_srt` xuống dòng.
  - `backend/cover/overlay.py`: lời trên video chia nhiều dòng ≤ 8 từ, dòng cuối giữ vị trí cũ, các dòng xếp lên với khoảng cách `LYRIC_LINE_GAP = 1.45 × cỡ chữ`.
  - Frontend: `api/projects.ts`, `api/sources.ts`, `api/cover.ts`, `ProjectFormModal.tsx` (4 kiểu tạo; «Chỉ tạo, tôi tự chạy» / «Tạo & chạy tự động» — kiểu chạy auto audio/video và ô xác nhận credit chỉ hiện khi chạy tự động; ô kéo thả file danh sách; sửa chữ hướng dẫn trỏ đúng nút «Auto chỉ audio / Auto audio + video»), `ProjectsPage.tsx`, mới `components/cover/CoverDropPanel.tsx`, `SunoCoverPanel.tsx`, `CoverPanel.tsx` (⬇ .srt từng bài); build lại `frontend/dist`.
  - Bản dự phòng các file cũ + dist cũ: `Trash/backup_truoc_cap_nhat_20261117/`.
- **Trước:** tạo từ danh sách = chạy auto ngay; danh sách chỉ .txt/.docx; nhập cover 1 file, không tự master; lời video/srt 1 dòng dài (chữ bị thu nhỏ).
- **Sau:** như bản tách; lời video và .srt xuống dòng tối đa 8 từ/dòng, dòng cách nhau thoáng.
- **Kiểm thử:** bản sao code tool chính ở thư mục tạm, cổng 8299, DB trống: `tsc -b && vite build` OK; parser 7/7 PASS; API ALL PASS (from-list mixset/single + project có đủ thông số video, lỗi 422, `/api/tasks/active` rỗng, nhập 2 WAV + auto_master → master xong, .srt 404 rồi 200); UI: form 4 kiểu + chế độ chạy, tab Suno có ô kéo thả; render khung hình .ass bằng ffmpeg: câu 16 từ → 2 dòng 8 từ, cỡ chữ đầy đủ, khoảng cách thoáng (cả khi bật sóng âm).
- **Kết quả:** đã chép vào tool chính. Kiểm tra `/api/tasks/active` cổng 8100 rỗng trước khi chép; KHÔNG restart backend — cần tắt/mở lại tool để backend mới chạy (giao diện mới gọi `/from-list` sẽ lỗi 404 tới khi mở lại).
- **Tồn đọng:** chưa render video thật đầu-cuối với bài thật; chưa chạy AI căn lời khi nhập bài; .xls cần xlrd; .doc best-effort.

## 2026-11-17 — Đưa tool chính lên GitHub repo Music-Cover + hướng dẫn sử dụng đầy đủ

- **Yêu cầu:** "up lên github với đầy đủ hướng dẫn sử dụng cho cả 2 phiên bản. Music-Cover cho tool tổng (tool chính)".
- **Nguyên nhân:** repo Music-Cover còn trống / chưa có bản mới của tool chính và chưa có hướng dẫn.
- **File đã đổi:** toàn bộ mã nguồn tool chính (backend, frontend + `frontend/dist`, `app_window.py`, `launcher_exe/`, `audio_tempo_master_tool`, `docs/`, `tests/`); mới `README.md`, `HUONG_DAN.md`, `update.bat`, `patch/apply_update.ps1`, `patch/removed_files.txt`, `.gitattributes`; sửa `.gitignore` (gắn `/` đầu tên thư mục để không bỏ sót `frontend/src/components/projects`, chỉ cho phép 2 file json trong `data/`), `install.bat` (tạo `CoverNhacTool.exe` + lối tắt Desktop), `launcher_exe/setup_app.ps1` (tên mặc định CoverNhacTool / "Cover Nhac Tool"). Bỏ các tài liệu cũ trùng lặp (`HUONG_DAN_CAI_DAT.md`, `QUY_TRINH_LAM_VIDEO_COVER.md`, `VIDEO_MODULE.md`) khỏi repo, gộp vào README + HUONG_DAN.
- **Không đưa lên:** `.venv`, profile trình duyệt, `data/app.db`, `.env`, đăng nhập, API key, nhạc/video, file `.exe`.
- **Trước:** chưa có bản trên GitHub, chưa có cách cập nhật không mất dữ liệu. **Sau:** tải ZIP → `install.bat` → lối tắt Desktop; `update.bat` tải bản mới từ Music-Cover, giữ dữ liệu.
- **Kiểm thử:** bản xuất từ git chạy cổng 8298 với data trống: `/api/tasks/active` và `/` trả 200; `setup_app.ps1` tạo được exe + lối tắt thử (đã xoá lối tắt thử); `apply_update.ps1` trên bản cài giả: giữ nguyên `app.db`, `master_config.json`, `media`, thêm `suno_workflow.json` còn thiếu, chép mã + dist mới. Quét chuỗi bí mật (sk-, AIza, ghp_, khoá riêng, token): sạch.
- **Sửa thêm:** `apply_update.ps1` bỏ qua bước sao lưu nếu thiếu thư mục `backend`/`frontend` (trước đó báo lỗi robocopy 16).
- **Tồn đọng:** chưa thử `install.bat` từ đầu trên máy mới hoàn toàn.

## 2026-11-18 — Dán lời cho bài bị loại «thiếu lời» thì tool nhận lại bài

- **Yêu cầu:** "khi dán lời là phải nhận bài, đây hiện đang không pass" (ảnh: bài «Bỏ qua · thiếu lời» vẫn bị loại sau khi bấm Lưu lời).
- **Nguyên nhân:** `PUT /api/sources/{id}` chỉ lưu chữ lời; trạng thái `skipped_no_lyrics` và dòng báo lỗi giữ nguyên nên bài vẫn bị loại khỏi Suno Cover.
- **File đã đổi:** `backend/routers/sources.py` (`update_source`). Bản cũ cất ở `Trash/backup_truoc_dan_loi_20261118/` (máy).
- **Trước:** dán lời xong bài vẫn «Bỏ qua · thiếu lời». **Sau:** lời không trống → bài đã có file gốc chuyển «Đã tải» + tự xuất WAV tempo 4.5× chạy nền; bài chưa có file → tự xếp hàng tải bài gốc (giữ nguyên lời vừa dán). Lời trống thì vẫn để loại. Không bấm gì trên Suno.
- **Kiểm thử:** bản sao code + DB tạm (không mở trình duyệt): bài có file → `done`, hết lỗi, tempo 4.5× có file; bài chưa có file → được xếp tải, lời giữ nguyên; lời trống → vẫn `skipped_no_lyrics`. ALL PASS cho cả bản chính và bản 8200.
- **Tồn đọng:** lô Mix Set đã chạy qua bước bỏ bài thì không tự thêm lại bài vào lô đó — bấm chạy Suno cho bài sau khi nhận lại.
