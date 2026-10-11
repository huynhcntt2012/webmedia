# Giai đoạn 11 — quyền nội dung và thiết bị

Mỗi request metadata, HLS master/variant/segment, phụ đề, ảnh truyện và lưu tiến độ
đều xác minh cookie HttpOnly đã ký, tài khoản/phiên còn hoạt động, trạng thái xuất
bản và quyền hiện tại trong PostgreSQL. Media nằm trong volume riêng hoặc BYTEA;
không có static mount công khai hay bearer token trên URL. Response private dùng
`Cache-Control: no-store`. Poster trên media.sunifactory.com là tài nguyên công khai.

Migration `0010_content_access` thêm `content_grants` và `content_devices`; rollback
chỉ thực hiện trên Compose test. Không thay seed hoặc giá VIP/Premium.

## Quyền hiện tại

- Mặc định Free; `users.plan_code` không tự cấp quyền trả phí.
- Admin có quyền xem nội dung Premium và tối đa 10 phiên đồng thời.
- Admin có thể cấp quyền riêng qua `POST /admin/content-grants` với `user_id`,
  `plan_code` (vip/premium), `days` (1–366), `device_limit` (1–20).
  CSRF và role Admin bắt buộc. Lấy user UUID từ trang tài khoản.
- `GET /admin/content-grants?user_id=UUID` xem lịch sử và
  `DELETE /admin/content-grants/UUID` thu hồi. Mọi thay đổi có audit.
- Premium bao gồm VIP và Free. Nếu nhiều quyền chồng lấn, chọn cấp cao nhất,
  rồi ngày hết hạn xa nhất và UUID để ổn định thứ tự. Không cộng số thiết bị.
- Subscription SePay sandbox không cấp quyền thật. Cấp quyền Admin là thao tác
  độc lập, có chủ ý; không phải đánh dấu đơn hàng thanh toán. Không tự cấp quyền
  cho bất kỳ tài khoản dev nào khi migration/seed.

## Thiết bị

Thiết bị được định nghĩa là **phiên đăng nhập trình duyệt**, không phải nhận dạng
phần cứng. Nhiều tab cùng phiên dùng chung chỗ; đăng nhập mới tạo phiên mới.
Free có 2 chỗ xem/đọc đồng thời. Lease kéo dài 5 phút từ request nội dung và được
gia hạn tối đa mỗi phút; hết hoạt động sẽ nhả chỗ. PostgreSQL advisory lock theo
user đảm bảo request đồng thời không vượt quota. Khi hạn mức giảm, các phiên được
nhận sớm nhất giữ chỗ; phiên vượt hạn mức bị chặn ở request tiếp theo.

`/devices` vẫn mở được khi đầy chỗ. Thu hồi phiên chỉ cho chủ tài khoản, yêu cầu
CSRF, vô hiệu access và refresh của phiên đó. Quyền hết hạn/thu hồi, logout hoặc
ngừng xuất bản có hiệu lực trên request tiếp theo, kể cả URL media đã sao chép.
Bytes đã gửi hoặc buffer trình duyệt không thể thu hồi. Không tuyên bố DRM hoặc
chống quay màn hình; người có quyền vẫn có thể lưu nội dung đã nhận.

Cloudflare/reverse proxy phải bypass cache cho `/api/*` và các trang tài khoản,
watch/read; không cache response có cookie. Không mở volume media bằng web server.
API không tin X-Forwarded-For do client cung cấp; triển khai hiện tại dùng giới hạn
IP chung tại Next proxy và giới hạn đăng nhập theo tài khoản, cần cân nhắc tải thực.
