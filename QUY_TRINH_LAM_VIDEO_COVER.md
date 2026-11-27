# QUY TRÌNH LÀM VIDEO COVER — BẢN ĐỂ DUYỆT

> Viết lại từ file «Workflow làm nhạc cover youtube.docx», đối chiếu với những gì tool **đang làm thật** (ngày 29/10/2026).
> Ký hiệu: ✅ đã có và đã chạy · 🟡 có code nhưng chưa chạy ổn · ❌ chưa làm · 👤 bạn tự làm/tự code
>
> Bạn đọc từng bước — chỗ nào sai hoặc muốn khác, ghi chú ngay dưới bước đó.

---

## PHẦN 1 — NHẠC GỐC + LỜI (tab ① Tải nhạc gốc)

**Bước 1. Tìm & tải nhạc gốc** ✅
- Gõ mỗi dòng 1 bài «Tên bài – Ca sĩ» (hoặc dán link bài nhaccuatui) → bấm **🔎 Tìm & tải**.
- Tool mở cửa sổ trình duyệt riêng → tìm trên nhaccuatui → chọn bản đúng nhất (tránh remix/slowed/karaoke) → **Download → High quality**.
- File lưu ở: `media\<tên project> (#số)\nhac_goc\` — mỗi project 1 thư mục riêng.
- Tool lưu luôn **link bài** + **lời bài hát** (file .txt cạnh file nhạc).
- Cần đăng nhập nhaccuatui 1 lần (Settings → 🔑 Mở nhaccuatui để đăng nhập — bạn tự đăng nhập).

**Bước 2. Lấy lời bài hát** ✅
- Có lời trên nhaccuatui → lấy luôn.
- Không có → tool tự tìm Google «tên bài + ca sĩ + lyrics», chỉ chép lời hát (bỏ Chorus, Điệp khúc, ĐK, hợp âm, x2, tên nhạc sĩ…). Không thấy thì mở vài trang lời + AI lọc. Bài đó hiện **🌐 lời lấy trên mạng**.
- Bạn bấm **📝 Xem/sửa lời** để kiểm tra / sửa tay.

**Bước 3. Đổi tempo bài gốc** 👤 (phần bạn tự code)
- Thanh **🎚 Tempo** dưới mỗi bài (0.2× – 5×) → **⬇ Xuất file đã chỉnh tempo** → lưu ở `da_chinh_tempo\`.
- Suno chỉ nhận bản đã xuất tempo, không nhận thẳng file gốc.
- *Ghi chú của tôi: phần này và phần Suno Editor ở bước 4 do bạn tự code; tôi không viết, không kiểm tra, không sửa.*

---

## PHẦN 2 — LÀM BẢN COVER (tab ② Suno Cover)

**Bước 4. Đưa nhạc lên Suno** 👤🟡
- Tool mở suno.com/create (cửa sổ riêng, bạn đăng nhập Suno 1 lần ở Settings).
- Upload bản đã xuất tempo → Open in Editor → chỉnh tempo (22 cho lofi/R&B/jazz/blues/pop/ballad, 25 cho remix/house) → Save as New Song. *(phần bạn tự code)*
- Tình trạng: lần chạy gần nhất (bài «Tìm Em») báo **lỗi: không thấy nút «Open in Editor»**.

**Bước 5. Tạo cover** 🟡
- Từ bài trên Suno → Remix → **Cover**.
- Tool điền:
  - **Tên bài** = tên bài gốc, **không** kèm ca sĩ.
  - **Lời** = lời ở bước 2 (lời thường).
  - **Styles** = AI/tool viết theo thể loại + mô tả của project (ví dụ ballad → «emotional ballad, 68-76 BPM, piano, strings…»).
  - **Vocal Gender** = AI đoán ca sĩ gốc là nam hay nữ (sửa được ở ô «Giọng»).
  - Model **v6**, **Max Mode bật**, Duration **Auto**, **Weirdness 10%**, **Style Influence 75%**, **Audio Influence 50%**, **Variety Normal**.
- Bấm **Create** → ra **2 bản** (~20 credit).
- Nên bấm **🧪 Chạy thử** trước: tool điền form rồi dừng, không bấm Create, không tốn credit.

**Bước 6. Tải 2 bản cover về + kiểm tra lỗi** 🟡
- Tool tải cả 2 bản WAV về `ban_cover\` và tự gắn đúng bài.
- Tool tự nghe và báo **🔴 Lỗi** khi rè/nhiễu, bị cắt ngắn, mất tiếng, vỡ tiếng, im lặng. Bạn sửa bằng **✓ Nghe ổn** / **🚩 Báo lỗi**.
- Tải xong → tool **tự master** 2 bản bằng ffmpeg (EQ nhẹ, gom bass về mono, nén, chuẩn độ to -14 LUFS) → `ban_cover\mastered\…_master.wav`. File gốc giữ nguyên. Mỗi bản cover hiện **🎚 Đã master** + độ to trước → sau + trình phát bản master; nút **🎚 Master / ↻ Master lại**; khung **🎚 Master** chọn kiểu (natural / dynamic / loud) và WAV/MP3 ngay trên giao diện.
- Bản lỗi → **🔁 Tạo lại trên Suno** (file lỗi cất vào `ban_cover\_loi`, không xoá).
- Suno từ chối bài → **⛔ Suno từ chối**, tool bỏ qua làm bài tiếp; bạn tự làm rồi **⬆ Nhập file cover**.
- Captcha / hộp đồng ý điều khoản → tool kêu «bíp», **bạn tự bấm**, tool chờ rồi làm tiếp.
- *(Bước «lời có dấu _ + font nghệ thuật» trong file .docx: tool **không** làm — dùng lời thường.)*

**Bước 7. Làm các bài khác** ✅
- Lặp bước 1–6 cho từng bài. Hoặc đã có sẵn cover → khung **⬆ Nhập bài cover tôi đã làm sẵn**.

---

## PHẦN 3 — LỜI CHẠY TRÊN VIDEO + GHÉP NHẠC

**Bước 8. Tạo lời bài hát** ✅ (nút ở tab ①/②, làm ở tab ③ Lời bài hát)
- Bấm **🎤 Tạo lời bài hát** → tool điền tên bài, ca sĩ, lời cho từng bản cover.
- AI tách giọng + căn từng câu lời theo nhạc (lệch < 0.1 giây khi chạy thử).
- Bạn xem lại, sửa câu nào lệch.

**Bước 9. Mix** ✅ (tab ④)
- **Mixset**: ghép các bản cover thành 1 file nhạc dài, **mỗi bài phát đúng 1 lần** theo thứ tự bạn xếp — không còn ô Duration, độ dài video = tổng độ dài các bài. Crossfade mặc định **5 giây**.
- Bài có bản master (`ban_cover\mastered\…_master.wav`) → ghép bản master; chưa có → bản gốc. Các bài được chỉnh to đều theo preset master (natural = -14 LUFS).
- ⚠️ Tool **tự làm video ngay sau khi mix** → **căn lời xong rồi mới bấm Mix**.

---

## PHẦN 4 — HÌNH ẢNH + VIDEO (tab ⑤ Video)

Mặc định phong cách **Tả thực điện ảnh** (project mới; project cũ chưa có ảnh cũng tự chuyển).

**Bước 10. Tạo ảnh bìa + 2 bảng tham chiếu** ✅
- Tool viết prompt ảnh bìa (không chữ) theo **tên + ý tưởng + thể loại nhạc** của project
  (ví dụ «mùa thu» → lá vàng; «đêm mưa» → quán cà phê bên cửa kính mưa; Remix/Deep House → sân thượng thành phố lúc chạng vạng).
- **ChatGPT vẽ** (cửa sổ ChatGPT riêng của tool, đăng nhập 1 lần; ChatGPT lỗi / hết lượt → tự chuyển **Muse.ai** vẽ phần còn thiếu, KHÔNG xoá ảnh đã vẽ). Đổi máy ở ⚙️ Cài đặt → Máy vẽ ảnh nền.
- Thứ tự vẽ:
  1. **Ảnh 0 — ảnh bìa**: kiểu thumbnail mixtape Việt, **1 cô gái trẻ (hư cấu, ~25 tuổi), mặc gợi cảm nhưng lịch sự, bịt mặt / đeo khẩu trang / mạng che mặt (chỉ lộ mắt), nhìn thẳng camera**. Trang phục theo thể loại —
     Remix/Deep House → nữ DJ áo croptop + chân váy da, khẩu trang đen bóng; Ballad → váy dạ hội trễ vai + mạng ren đen;
     Acoustic → áo len croptop + quần short jean ôm đàn, khẩu trang vải; nhạc khác → váy body + áo khoác lửng, tai nghe. Nền mờ đèn bokeh, chừa 1 bên trống cho tiêu đề.
  2. **Ảnh 1 — bảng phân tích nhân vật**: vẽ TỪ ảnh bìa (đính kèm ảnh bìa) — mặt trước / nghiêng / sau / 3/4, cận mặt nạ + trang phục + giày, dải màu.
  3. **Ảnh 2 — bảng tham chiếu bối cảnh**: vẽ TỪ ảnh bìa — chỉ nơi chốn (không người), nhiều góc nhìn + chi tiết đạo cụ.
- Chọn «👤 Có 1 cô gái» hoặc «🏞️ Chỉ cảnh vật» (chế độ cảnh vật: 2 bảng là bảng thiết kế bối cảnh + bảng ánh sáng).
- AI viết prompt mà nhân vật không phải nữ che mặt → tự bỏ, dùng mẫu dựng sẵn.
- ⚠️ Project cũ (chỉ có 1 ảnh bìa): bấm **Chạy tiếp** → giữ ảnh bìa cũ, vẽ thêm 2 bảng + 4 clip góc quay. Muốn đổi sang cô gái che mặt → **Làm lại từ đầu**.

**Bước 10b. Thumbnail có chữ (ChatGPT)** ✅
- ChatGPT lấy ảnh bìa trên và thêm chữ kiểu mixtape: **tiêu đề 3D thật to** (ánh kim / neon), **dòng thể loại** nhỏ
  (vd «Nhạc Deep House Cover Cực Cuốn»), **danh sách bài đánh số** trong khung tối bo góc (tối đa 6 bài, chỉ khi project có từ 2 bài),
  thêm nốt nhạc + sóng âm trang trí. Lỗi → vẽ chữ bằng font thường (chỉ tiêu đề + dòng phụ).

**Bước 11. Tạo 6 clip** ✅
- **Clip 00** = ảnh bìa «sống dậy» (máy quay đẩy chậm) → làm video giới thiệu.
- **Clip 01** = cùng ảnh bìa, máy quay đứng yên, chỉ chuyển động nhẹ (gió, tóc, ánh đèn).
- **Clip 02–05** = **4 góc quay nhân vật**, dựng từ 2 bảng (giữ đúng mặt nạ, trang phục, bối cảnh):
  02 cận mặt (đẩy máy vào mắt) · 03 đi ngang góc nghiêng · 04 góc thấp lia từ dưới lên · 05 toàn cảnh xoay quanh nhân vật.

**Bước 12. Render video** ✅
- Thumbnail mở đầu → clip 00 → clip 01–05 xáo trộn nối mềm đến hết nhạc.
- Trên video: **danh sách bài bên PHẢI** — mỗi bài 2 dòng: **tên bài đầy đủ + tên ca sĩ đầy đủ** (không cắt «…»), bài đang phát tô vàng;
  **lời từng câu phía dưới** (câu trước mờ / câu đang hát to sáng / câu sau mờ — không chạy chữ kiểu karaoke), **sóng âm nhảy theo nhạc** sát đáy video (bật/tắt ở tab ③).

---

## PHẦN 5 — DUYỆT & ĐĂNG (tab ⑥) — **ĐỢT C, CHƯA LÀM**

**Bước 13. Xem trước** ❌
- Nút **▶ Xem trước video** để bạn duyệt bằng tay.

**Bước 14. Tự động tải nháp YouTube** 🟡 (nút đang nằm cuối tab ⑤, chưa chuyển sang ⑥)
- AI viết **tiêu đề + mô tả** (kèm mốc thời gian từng bài).
- Đánh dấu **«không dành cho trẻ em»** và **«có sử dụng AI»**.
- Đăng lên **kênh YouTube mới** (không phải kênh của tool thiền cũ).
- Chỉ lưu **NHÁP** — bạn tự kiểm tra rồi mới công khai.

---

## CẦN BẠN XÁC NHẬN TRƯỚC KHI LÀM ĐỢT C

1. Bước 13–14: chuyển hẳn nút nháp YouTube từ tab ⑤ sang tab ⑥ — đồng ý không?
