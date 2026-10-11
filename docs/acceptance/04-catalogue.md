# Giai đoạn 04 — Home, thư viện, tìm kiếm và chi tiết phim

**ĐẠT nghiệm thu kỹ thuật — 10/10/2026 (Asia/Saigon).**
Gate 03 đã đạt trước khi triển khai; xem `03-auth.md`. Các lượt kiểm thử được
chạy trong quá trình triển khai ngày 09/10; hồ sơ được hoàn tất ngày 10/10.

## Phạm vi hoàn tất

- Home phong cách thư viện streaming: hero, phim mới thêm, thẻ phim, điều hướng.
- `/movies`: tìm tên tiếng Việt, sắp xếp, phân trang, giữ truy vấn trong URL;
  trạng thái trống, lỗi, loading skeleton và tham số không hợp lệ.
- `/movies/{slug}`: tên/năm/mô tả/gói; chưa phát video. Không giả poster hoặc nút xem.
- API list/count/search/detail chỉ published, metadata whitelist; draft/archived
  và phim không tồn tại cùng 404. Không công khai episode/media/storage.
- Responsive desktop/mobile, form labels, skip link, focus ring, text escaping.
- Không thêm dữ liệu phim vào dev. E2E có fixture riêng gồm 28 published + 2 ẩn.

## Migration và bảo mật

**NO-OP:** giữ head `0003_auth`. Status, index status/created_at và các trường
catalogue đã có từ 0002; không cần schema/grants mới hoặc revision đánh dấu giả.
Migration upgrade/rollback/reapply và drift vẫn chạy qua bộ integration trên DB
test riêng. Không downgrade hoặc xóa volume dev.

Query dùng parameters, escape wildcard, NFC + ILIKE. q ≤100 ký tự, page 1–1000,
page_size 1–48, sort allowlist. Có timeout database/fetch và lỗi chung không lộ
SQL/credential. SSR không nhận URL upstream từ input. React render plain text;
browser xác nhận script trong synopsis không chạy. CSP nonce và auth regression đạt.

## Bằng chứng đã chạy

| Lệnh / kiểm tra | Kết quả |
|---|---|
| `pytest backend/tests -m "not integration" -q` | 28 passed |
| `python -m unittest discover -s scripts -p "test_*.py"` | 2 passed |
| `ruff check backend scripts` | Passed |
| `docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests` | 83 passed, 28 unit deselected, exit 0 |
| `pnpm lint`, `pnpm typecheck` | Passed |
| `pnpm test` | 14 passed |
| `pnpm build` | Production build passed |
| `pnpm test:e2e`, API không cấu hình | 6 passed, 4 bài cần backend thật skip; kiểm tra UI unavailable |
| `E2E_AUTH=1 pnpm test:e2e`, Compose E2E thật | 10 passed, không skip; standalone build desktop/mobile |
| Dev `docker compose up --build -d --wait` | Exit 0; 5 services healthy; bootstrap/migrate exited 0 |
| `python scripts/smoke.py` | 4 PASS |
| Browser đọc localhost:3000 và /movies | Empty state đúng, thư viện render thành công |
| Ảnh Home desktop, detail mobile và Home local | Đã xem, không thấy lỗi bố cục ở các ảnh này |
| `.env`, log và test-results | Bị gitignore |

19 integration tests mới kiểm tra whitelist, ẩn draft/archived, tìm kiếm Unicode
hoa/thường/NFC/NFD, escape wildcard, SQL injection string, giới hạn tham số,
phân trang ổn định, đổi published về draft và catalogue trống. 64 integration
hồi quy gồm auth, migrations, PostgreSQL/Redis/Celery/FFmpeg tiếp tục đạt.
Browser kiểm tra 24/4 kết quả phân trang, tìm tiếng Việt, detail, XSS, phim ẩn,
không kết quả, tham số sai, keyboard skip link và chiều rộng desktop/mobile.

Tổng full-stack: **137 tests passed** (28 + 2 + 83 + 14 + 10). Lượt đầu gặp trùng
tên module pytest unit/integration; đã đổi tên file unit và chạy lại đạt 83 integration.
Không dùng SQLite/mocks để thay bằng chứng tích hợp PostgreSQL.

## Giới hạn và bàn giao

- Tìm kiếm còn phân biệt dấu; chưa fuzzy. Substring có thể scan dữ liệu, cần đo
  tải/index phù hợp trước khi catalogue lớn; không tuyên bố đạt kiểm thử tải.
- Skeleton đã triển khai; chưa có bài browser cố tình làm chậm server để đo trạng thái này.
- Thư viện dev trống; poster/trailer/Admin CRUD ở 05, player ở 07. Metadata gói
  public không cấp quyền playback; entitlement ở 11. VIP/Premium vẫn nháp.
- Không đổi dependencies trong giai đoạn này; dùng bộ lock đã audit ở 03.
- CI cập nhật nhưng chưa có lượt remote; Starlette còn cảnh báo deprecated httpx.
- Hai stack test được dọn bằng compose down, giữ stack dev hoạt động. Chưa production.

Chi tiết API/migration/giới hạn: [CATALOGUE.md](../CATALOGUE.md).
Gate 04 đã đạt; chưa triển khai giai đoạn 05 trong lần này.
