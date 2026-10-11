# Giai đoạn 05 — Admin quản lý phim

**ĐẠT nghiệm thu kỹ thuật — 10/10/2026 (Asia/Saigon).**
Gate 04 đã đạt trước khi triển khai; chưa triển khai upload/transcoding giai đoạn 06.

## Kết quả

- `/admin`: tìm/lọc/phân trang phim; tạo/sửa/xóa phim, tập và thể loại, chọn thể loại,
  đặt trạng thái xuất bản, gói yêu cầu, URL poster/trailer; xác nhận trước thao tác xóa.
- Metadata published được cập nhật ở catalogue. Poster từ CDN do người dùng chọn:
  `media.sunifactory.com`; HTTPS/exact hostname/path allowlist, browser-only fetch.
  Trailer YouTube canonical URL, link noopener/noreferrer. Không upload file lên CDN.
- Row locks + version cho sửa/xóa; 409 khi bản cũ hoặc unique/FK conflict.
  Tập chỉ sửa/xóa qua đúng movie ID. Xóa phim cascade tập/liên kết, giữ thể loại dùng chung.
- Nhật ký actor UUID, entity UUID/type, action, changed_fields và timestamp; ghi cùng
  transaction với mutation. Runtime không được UPDATE/DELETE nhật ký.
- Mọi route Admin có RBAC, mutation có CSRF/Origin/rate limit; body 32 KiB và input
  allowlist. Không seed admin trong dev; test Admin chỉ ở Compose E2E riêng.

## Migration và database

Revision **0004_admin_catalogue → parent 0003_auth**, thêm genres/movie_genres/audit_events,
poster_url/trailer_url/version vào movies và version vào episodes. Schema/model drift
check đạt. Upgrade/rollback/reapply giữ phim cũ đã chạy trong `suni_test` riêng;
downgrade loại bỏ metadata/audit mới. Dev chỉ upgrade, không xóa/reset volume.
Runtime được CRUD phim/tập/thể loại và SELECT/INSERT audit, không sửa role/plan user,
DDL hoặc quyền owner. Runtime chung cho API/worker local được ghi rõ trong ADMIN.md.

## Kiểm thử đã chạy

| Lệnh / kiểm tra | Kết quả |
|---|---|
| `pytest backend/tests -m "not integration" -q` | 55 passed |
| `python -m unittest discover -s scripts -p "test_*.py"` | 2 passed |
| `ruff check backend scripts` | Passed |
| Compose integration up --build --abort-on-container-exit --exit-code-from tests | 107 passed, 55 unit deselected, tests exit 0 |
| Migration 0004 → 0003 → head, bảo toàn title/version khởi tạo và Alembic drift | Passed trên PostgreSQL thật |
| `pnpm lint`, `pnpm typecheck` | Passed |
| `pnpm test` | 14 passed |
| `pnpm build` (sau sửa fallback ảnh/mobile layout) | Passed, gồm kiểm tra TypeScript |
| `E2E_AUTH=1 pnpm test:e2e` | 12 passed, không skip, standalone production build desktop/mobile |
| Dev Compose up --build -d --wait | Exit 0; 5 services healthy; bootstrap/migrate exited 0 |
| `python scripts/smoke.py` | 4 PASS |
| Dev /admin, CSP poster host, anonymous admin movies/audit | 200 shell, hostname đúng, 401/401 |
| Gitignore | .env và logs bị ignore |

**190 tests passed** (55 + 2 + 107 + 14 + 12). 24 integration mới kiểm tra CRUD,
publication, audit atomicity, unique/FK conflict, version stale/concurrent, sở hữu tập,
Admin/User/anonymous trên các nhóm route, CSRF mọi phương thức ghi, URL/bounds/body,
rollback và giữ dữ liệu cũ. Bộ auth/catalogue/PostgreSQL/Redis/Celery/FFmpeg hồi quy đạt.
27 unit mới kiểm tra URL allowlist/canonicalization và validation nghiệp vụ.

Browser thực hiện tạo genre, phim nháp, từ chối host poster lạ, lưu URL hợp lệ,
thêm/sửa tập, xuất bản, đọc public detail/genre/trailer, XSS không thực thi,
poster failure fallback, xóa tập/phim/genre và đọc nhật ký trên desktop/mobile.
E2E chặn request ảnh CDN để kiểm tra fallback; không dùng kết quả này để tuyên bố
CDN thật có file hoặc hoạt động. CRUD API/database là thật, không mock PostgreSQL.

Các lượt browser đầu sai locator/chuỗi thông báo đã được sửa. Phát hiện và sửa
trường hợp ảnh lỗi trước hydration chưa hiện placeholder; ref kiểm tra ảnh complete
khi mount và E2E scroll poster vào viewport. Lượt cuối 12/12 đạt.
Form trên mobile được đưa lên trước danh sách khi đang chỉnh sửa. Đã xem ảnh desktop
editor và mobile toàn trang, đồng thời browser kiểm tra không tràn ngang.

Hai stack test đã dọn; stack dev vẫn chạy. Worker test có exit 137 khi Compose dừng
sau test hoàn tất; task Celery/FFmpeg đã pass trước đó, không ghi nhận là lỗi test.

## Giới hạn

- Domain đã cấu hình theo người dùng, chưa xác minh file thật/CDN ownership/MIME.
  Không server fetch URL, không Next image optimization; browser chịu trách nhiệm tải ảnh.
- Trailer chỉ là liên kết YouTube, không embed hoặc phát video nội bộ.
- Audit không lưu before/after hoặc chống sửa bởi DB owner; retention/backup ở 12.
- Không đổi dependencies; dùng lock đã audit ở 03. CI đã cập nhật, chưa chạy remote.
- Starlette TestClient còn cảnh báo deprecated httpx. Đây là local dev, chưa production.
- Chưa tự cấp quyền Admin cho tài khoản dev nào. Xem lệnh operator theo UUID trong
  [ADMIN.md](../ADMIN.md); không có tài khoản/mật khẩu Admin mặc định.

Gate 05 đã đạt; giai đoạn 06 chỉ bắt đầu theo yêu cầu tiếp theo.
