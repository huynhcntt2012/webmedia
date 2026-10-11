# Giai đoạn 09 — Comic Reader

Mở **Truyện** trên thanh điều hướng hoặc `/comics`, tìm theo tên, mở truyện rồi chọn
chương. Danh mục/chương chỉ công bố metadata truyện published; mỗi trang danh sách
tối đa 20 mục. Nội dung ảnh yêu cầu đăng nhập. Free mở cho tài khoản hoạt động;
Admin đọc truyện published ở mọi gói. VIP/Premium vẫn nháp, không cấp quyền dựa trên
plan_code tự gán; subscription và chính sách thiết bị thuộc giai đoạn 10/11.

## Cách đọc

- **Cuộn dọc**: vùng đọc riêng, ảnh giữ tỷ lệ/kích thước trước khi tải để khôi phục
  vị trí không bị nhảy bố cục. Ảnh ngoài trang hiện tại dùng native lazy loading.
- **Lật trang**: chỉ render một ảnh, dùng Trang trước/Trang sau, chọn số trang hoặc
  phím ←/→ khi focus vùng đọc. Phím mũi tên không chiếm điều khiển input/select/button.
- Lưu vị trí tự động mỗi 5 giây khi có thay đổi, khi chuyển trang/chế độ, khi ẩn tab;
  nút **Lưu vị trí** giúp xác nhận trước khi rời trang. Đóng tab đột ngột có thể mất
  phần chưa lưu. Trạng thái lưu lỗi cho phép thử lại; xung đột 409 yêu cầu tải lại.
- Mở lại chương khôi phục trang, phần cuộn trong ảnh và chế độ của riêng tài khoản.
  Đổi thứ tự vẫn theo đúng ID trang. Xóa trang đã lưu chuyển về trang đầu còn ảnh,
  offset 0; giữ version để tránh tab cũ ghi đè. Chương trống có thông báo riêng.

## Migration và quyền

`0008_reader` thêm reading_progress: khóa chính user_id + chapter_id, FK cascade
user/chapter, page_id FK SET NULL, offset_milli 0..1000, mode vertical/paged,
version > 0 và updated_at. Chế độ là preference theo chương, không có bảng preference
giả. Downgrade xóa bookmark, giữ truyện/chương/ảnh; chỉ thử trên Compose test riêng.

API reader metadata/ảnh/progress luôn xác thực session đang hoạt động và truyện
published, kiểm tra gói, chapter/page parent. Ảnh lấy từ BYTEA đã chuẩn hóa ở gate 08,
không đường dẫn lưu trữ/URL nguồn; no-store, nosniff, qua Next proxy allowlist.
Client không gửi user_id. PUT có CSRF/Origin/rate limit, body 8 KiB, strict bounds,
version bookmark và chapter_version. Khóa chapter tuần tự hóa với upload/reorder/delete;
PostgreSQL conditional insert/update bảo đảm một writer thắng mỗi version.

Reader kiểm tra lại session/publication/version mỗi 60 giây; server chặn request ảnh
mới ngay khi thu hồi quyền. Lỗi ảnh/quyền đưa về màn hình tải lại. Ảnh đã tải vào trình
duyệt không thể thu hồi byte hay ngăn chụp màn hình; đây không phải DRM. Không CDN
cache private images. Không sử dụng Next image optimizer cho ảnh có cookie.

## Kiểm thử

Backend unit kiểm tra dữ liệu bookmark không tin cậy. Integration PostgreSQL thật
kiểm tra ảnh decoder thật, publication, quyền paid/session/logout, IDOR, CSRF/body,
hai writer, hai tài khoản, reorder/delete fallback, rollback/reapply/drift.
Frontend unit kiểm tra tính phần cuộn và giới hạn trang; E2E standalone desktop/mobile
đọc ảnh thật, cuộn/resume, mode/keyboard, reload, thu hồi publication và không tràn ngang.
Mobile dùng Chromium mô phỏng, chưa khẳng định Safari thật hoặc tải thư viện lớn.
