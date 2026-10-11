# Giai đoạn 08 — Quản lý truyện và ảnh trang

Mở `/admin` → **Truyện tranh** hoặc `/admin/comics` bằng tài khoản Admin.
Tạo truyện (tên, slug, mô tả, trạng thái, gói), tạo chương theo số chương rồi chọn
nhiều ảnh. Có thể sửa/xóa truyện/chương, tìm truyện và phân trang danh sách.
Reader công khai thuộc giai đoạn 09, chưa triển khai ở gate này.

## Upload và sắp xếp

- Chọn tối đa 50 file/lần; frontend gửi lần lượt theo thứ tự danh sách. Tối đa 500 trang/chương.
- JPEG, PNG, WebP tĩnh, tối đa 8 MiB đầu vào, 12 triệu pixel, rộng 8192/cao 20000 pixels.
  Decoder cũng kiểm tra kích thước sau EXIF orientation. Ảnh động, SVG, malformed,
  decompression bomb bị từ chối. Server kiểm tra bytes thực, không tin tên file.
- Mỗi ảnh được decode đầy đủ, xử lý EXIF orientation, đặt nền trắng nếu alpha, vẽ lại
  trên canvas RGB sạch và encode JPEG quality 88, tối đa 4 MiB. Không giữ ảnh gốc,
  EXIF/XMP/ICC/text metadata, SVG hay đường dẫn client.
- Decoder chạy child không shell, environment không chứa secrets, seccomp không socket,
  timeout 15s, CPU 10s, address space 512 MiB, output limit. Mỗi API process tối đa hai
  child đồng thời; bận trả 429. Body giới hạn cả FastAPI và Next proxy, checksum SHA-256.
- Mỗi file có upload_key UUID. Request lặp cùng key/hash trả cùng trang; đổi bytes bị
  từ chối. Frontend giữ key khi thử lại ảnh lỗi trong cùng màn hình. Tải lại trang web
  làm mất hàng đợi chọn file; chọn lại tạo lượt upload mới, có thể tạo trang trùng ảnh.
- Lỗi một file không rollback các file trước đã thành công. Danh sách báo từng file,
  nút thử lại chỉ gửi ảnh lỗi/chưa gửi. Dừng kết thúc sau request hiện tại.
- Nút đưa lên/xuống gửi toàn bộ danh sách ID của chương. Server yêu cầu mỗi trang đúng
  một lần, cùng chương, khóa chương và kiểm tra version. Unique position được defer
  trong transaction để hoán đổi nguyên tử; xóa trang cũng đánh số lại liên tục từ 1.
- Upload/reorder/delete/edit đều tăng version chương. Tab cũ nhận 409; dùng **Tải lại
  trang chương** hoặc mở lại chương trước khi tiếp tục. Xóa truyện/chương/trang cần xác nhận.

## Quyết định lưu trữ và migration

Revision `0007_comic_admin → 0006_playback` thêm version vào comics/chapters và
comic_page_assets (JPEG BYTEA, size, source hash, idempotency key, FK cascade theo page/chapter).
Ảnh được lưu trong PostgreSQL ở giai đoạn local này để image bytes + trang + audit cùng
commit/rollback, xóa cascade thu hồi bytes mà không có filesystem orphan. Storage key
UUID ở comic_pages là metadata tương đối, không URL và không dùng để đọc filesystem.
Không gắn ảnh truyện vào CDN poster media.sunifactory.com hoặc thư mục public của Next.js.

`COMIC_QUOTA_BYTES` mặc định 2 GiB cho tổng JPEG đã lưu. PostgreSQL advisory transaction
lock tuần tự hóa cấp quota; mất/chưa đủ version không tạo page/blob/audit. Quota này
không tính WAL/index/TOAST overhead hay dung lượng DB vật lý: production phải review
storage và backup/load ở gate 12. BYTEA phù hợp baseline local có quota; chưa khẳng định
phù hợp thư viện lớn. Nếu chuyển object storage cần migration + kiểm thử nhất quán mới.
Các page metadata từ stage 02 được giữ; không có blob thì preview trả 404, không tự tải
URL ngoài. Downgrade xóa assets/version mới, chỉ thử trên Compose test riêng.

## Quyền và kiểm thử

Mọi endpoint comics/chapters/pages/images yêu cầu Admin, không có public reader. Admin
có thể cùng quản lý catalogue; kiểm tra comic/chapter/page parent ngăn nhầm tài nguyên.
Mutation dùng CSRF/Origin/Redis throttle và version; audit cùng transaction, runtime chỉ
có CRUD bảng nghiệp vụ, không có quyền sửa role/plan/audit hoặc DDL. Preview JPEG no-store,
qua proxy allowlist, không image optimizer. Không log raw file, đường dẫn hoặc secrets.

Unit: re-encode, metadata stripping, invalid/truncated/SVG/animation/bomb rejection.
Integration: PostgreSQL thật, decoder Linux thật, quota, races/idempotency, reorder atomic,
partial upload, cleanup cascade, RBAC/CSRF/parent/body limits, migration rollback/drift.
E2E: standalone Next.js desktop/mobile, CRUD, hai ảnh thật xen file lỗi, retry không nhân
đôi trang thành công, preview decode, reorder/reload và xóa.

Tham chiếu decoder: [Pillow Image](https://pillow.readthedocs.io/en/stable/reference/Image.html),
[EXIF orientation](https://pillow.readthedocs.io/en/stable/reference/ImageOps.html#PIL.ImageOps.exif_transpose).
