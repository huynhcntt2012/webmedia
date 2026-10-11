# Giai đoạn 05 — Quản trị phim

Mở `/admin` bằng tài khoản Admin. Người dùng thường nhận 403 ở API; không có
admin mặc định trong database dev. Cấp quyền cho tài khoản đã đăng ký bằng UUID:

```powershell
docker compose run --rm --no-deps migrate python -m app.admin_cli USER_UUID
```

## Thao tác

- Tab **Thể loại**: tạo/sửa tên và slug; không xóa thể loại còn gắn với phim.
- Tab **Phim & tập**: tìm/lọc trạng thái, tạo phim nháp, sửa thông tin, gói yêu cầu,
  poster/trailer, chọn tối đa 20 thể loại. Slug phải duy nhất, không dấu, chữ thường.
- Lưu phim trước khi thêm tập. Mỗi tập có mùa/số tập/tên/thời lượng tùy chọn;
  cặp mùa/số tập phải duy nhất trong phim. Không chuyển tập sang phim khác bằng ID.
- Chọn **Đã xuất bản** và lưu để phim xuất hiện ở thư viện. Nháp/lưu trữ bị ẩn.
- Xóa phim có xác nhận, xóa cả tập và liên kết thể loại; không xóa thể loại dùng chung.
- Tab **Nhật ký** cho biết actor UUID, loại/ID bản ghi, hành động, thời điểm và tên
  các trường được cập nhật. Không lưu mật khẩu, cookie, URL hoặc toàn bộ nội dung cũ.

Các bản ghi có `version`. PUT/DELETE phải gửi version đang xem; phiên sửa cũ nhận
409, không ghi đè thay đổi mới. Nút tải lại lấy dữ liệu mới; nội dung chưa lưu sẽ mất
khi tải lại/đóng/chuyển phim. Nhật ký và thay đổi được commit cùng transaction.

## Poster và trailer

Theo lựa chọn người dùng, poster là **URL từ CDN riêng**; không upload ảnh ở bước này.
Đã đặt `POSTER_ALLOWED_HOSTS=media.sunifactory.com` trong `.env` local và `.env.example`.
Compose truyền cùng cấu hình cho API và CSP của web. Khi đổi host cần recreate cả hai.

- Poster cần HTTPS, hostname khớp chính xác, đường dẫn ASCII đuôi jpg/jpeg/png/webp/avif.
  Ví dụ `https://media.sunifactory.com/posters/ten-phim.webp`.
- Từ chối port, userinfo, query, fragment, `%`/path traversal, wildcard và SVG.
  Không dùng signed URL chứa token trong metadata công khai.
- API không tải/resolve URL, không proxy hoặc dùng Next image optimizer. Chỉ trình
  duyệt tải ảnh, với referrer-policy no-referrer và CSP img-src theo danh sách host.
  Ảnh lỗi có placeholder. CDN phải tự phục vụ ảnh với HTTPS/MIME phù hợp.
- Trailer nhận URL `https://www.youtube.com/watch?v=VIDEO_ID` hoặc
  `https://youtu.be/VIDEO_ID` (11 ký tự ID), chuẩn hóa thành watch URL.
  Hiển thị liên kết mở tab mới với noopener/noreferrer, không autoplay/iframe.
- Để trống URL khi muốn bỏ poster/trailer. Không tự tải hoặc upload file lên CDN.
  Không xác nhận sự tồn tại của file CDN từ việc URL vượt qua validation.

## API và quyền

Tất cả `/admin/*` kiểm tra session hiện tại + role Admin; mọi POST/PUT/DELETE thêm
exact Origin, signed CSRF và rate limit Redis. Backend giới hạn body admin 32 KiB.
Frontend proxy chỉ forward các mẫu route/method cố định, không nhận upstream URL.

| API | Chức năng |
|---|---|
| GET /admin/catalogue-settings | Hostname poster cho phép |
| GET/POST /admin/movies | Danh sách (20/trang, q/status) / tạo |
| GET/PUT/DELETE /admin/movies/{uuid} | Xem / sửa đầy đủ / xóa |
| GET/POST /admin/movies/{uuid}/episodes | Danh sách 50/trang / tạo tập |
| PUT/DELETE /admin/movies/{uuid}/episodes/{uuid} | Sửa / xóa tập thuộc đúng phim |
| GET/POST /admin/genres | Danh sách 100/trang / tạo |
| PUT/DELETE /admin/genres/{uuid} | Sửa / xóa thể loại |
| GET /admin/audit-events | Nhật ký 50/trang |

page 1–1000. PUT gửi đối tượng đầy đủ + version, DELETE gửi `?version=N`.
Unique/FK/conflict trả 409; validation 422; không tồn tại 404; lỗi DB 503 đã scrub.
Metadata public bổ sung poster_url/trailer_url/genres; vẫn chỉ phim published.
Nếu cấu hình host thay đổi, API public không trả poster URL thuộc host đã bị gỡ.

## Migration và vận hành

`0004_admin_catalogue` nối `0003_auth`: genres, movie_genres, audit_events;
movies thêm poster_url/trailer_url/version, episodes thêm version. Không thay đổi
plan hoặc user role. Runtime có CRUD các bảng phim/tập/thể loại, chỉ SELECT/INSERT
audit_events; không UPDATE/DELETE nhật ký, sửa user role/plan hoặc DDL.

API thực hiện RBAC; runtime là credential dùng chung, không phải PostgreSQL role
riêng cho từng người dùng. DB grants không thay thế bảo mật API hoặc credential.
Worker vẫn dùng runtime chung trong local; production cần tách credential worker.

Downgrade mất metadata/genre/audit mới nhưng giữ phim/tập cũ; chỉ kiểm thử trong
database test. Upload/transcoding ở 06, player ở 07, entitlement ở 11.
Nhật ký hiện không có before/after snapshot hoặc cơ chế chống sửa bởi DB owner;
retention, backup và giám sát sẽ được xem xét ở 12.
