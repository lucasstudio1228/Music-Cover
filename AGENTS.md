# Quy tắc bảo trì cho AI

## Nhật ký thay đổi bắt buộc

- Mọi lần sửa mã nguồn, cấu hình, migration, test hoặc workflow phải nối thêm một mục vào `AI_CHANGELOG.md` trong cùng lượt sửa.
- Mỗi mục phải ghi ngày giờ, yêu cầu, nguyên nhân, file đã đổi, hành vi trước và sau, kiểm thử đã chạy, kết quả và việc còn tồn đọng.
- Không ghi API key, cookie, token đăng nhập hoặc dữ liệu bí mật vào nhật ký.
- Nếu chỉ đọc/kiểm tra và không thay đổi file thì không cần thêm mục.

## An toàn workflow Suno
- Không restart backend khi đang có job; kiểm tra `/api/tasks/active` trước.