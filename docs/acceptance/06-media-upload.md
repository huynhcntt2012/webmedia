# Giai đoạn 06 — Upload và xử lý video

**ĐẠT nghiệm thu kỹ thuật — 10/10/2026 (Asia/Saigon).**
Gate 05 đã đạt trước triển khai. Player (07) chưa bắt đầu.

## Kết quả

- Admin chọn video trong tập, upload MP4 theo chunk 4 MiB, tạm dừng/tiếp tục,
  kiểm tra SHA-256 phần đã gửi, hiển thị queued/processing/ready/failed và thumbnail.
- Offset/checksum/size/MIME/magic, idempotency key, duplicate chunk và complete;
  quota reservation có khóa DB, giới hạn file/phiên/TTL. Không dùng tên client làm path.
- PostgreSQL job durable outbox, Celery/Redis thật, Beat dispatch lại và cleanup.
  Worker chống xử lý trùng qua advisory lock; retry tối đa ba lần; checksum toàn nguồn.
- FFmpeg tạo HLS 360p/720p theo nguồn, JPEG thumbnail; output hoàn tất trước ready.
  Không mở media công khai. Endpoint thumbnail chỉ dành cho Admin sở hữu upload, no-store.
- Decoder không shell, không inherited credentials, ép MOV/MP4, không external drefs,
  protocol whitelist và seccomp chặn socket/socketpair; resource limits và timeout.
- Cancel/expiry/xóa tập thu hồi file và reservation qua maintenance. Video ready giữ
  lại qua TTL; xóa tập thu hồi các phiên liên quan. Nguồn được xóa khi xử lý xong.

## Migration

`0005_media_uploads → 0004_admin_catalogue`: upload_sessions, upload_chunks,
media_jobs, media_variants, FK/unique/check/index. Runtime được CRUD bảng media,
không thêm quyền DDL, sửa role/plan hay nhật ký. Upgrade, downgrade về 0004,
reapply và Alembic drift check chạy trên PostgreSQL `suni_test` riêng, giữ phim cũ.
Dev chỉ upgrade và giữ các volume dữ liệu có sẵn; thêm private volume `suni_media_data`.

## Kiểm thử đã chạy

| Kiểm tra | Kết quả |
|---|---|
| Backend unit `pytest backend/tests -m "not integration" -q --basetemp=./test-results/pytest-stage06` | 61 passed |
| `python -m unittest discover -s scripts -p "test_*.py"` | 2 passed |
| `ruff check backend scripts` | Passed |
| Compose integration `up --build --abort-on-container-exit --exit-code-from tests` | 114 passed, 61 unit deselected; exit 0 |
| Migration rollback/reapply + schema drift | Passed, PostgreSQL thật |
| MP4 → queued → worker → HLS 360/720 + decode segment + JPEG | Passed |
| Outbox dispatch fault injection → maintenance qua Redis/Celery thật | Passed |
| Offset/hash/duplicate, ownership, User denial, CSRF, body limit, quota, expiry, cancel, orphan cleanup, retry cap | Passed |
| Seccomp network denial trong Docker Linux | Passed |
| Frontend `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build` | Passed; 14 unit tests |
| `E2E_AUTH=1 pnpm test:e2e` trên standalone Next.js | 12 passed (42.7s), desktop/mobile; gồm upload video thật và thumbnail decode |
| `docker compose up --build -d --wait --wait-timeout 180` | Exit 0; API/web/PostgreSQL/Redis/worker healthy, Beat running |
| `python scripts/smoke.py` | 4 checks passed |
| Chuyển mã video tổng hợp trong worker dev read-only/cap-drop/resource limits | Passed; HLS + thumbnail; xóa fixture sau thử |

Log local (ignored): `test-results/stage06-integration.log`, `stage06-browser.log`,
`stage06-dev-stack.log`. Ảnh desktop/mobile ở `frontend/test-results/.../admin-video-ready.png`.
Ảnh mobile đã kiểm tra trực quan; browser kiểm tra không tràn chiều ngang.

Lần chạy đầu phát hiện CHECK dùng từ khóa SQL offset chưa quote; đã sửa model/migration
và chạy lại từ database test sạch. Test network chạy pytest PID 1 bị parent guard từ chối;
test service đã thêm init, giữ nguyên fail-closed guard. Không tính các lần lỗi là đạt.
Docker Desktop được khởi động lại trước integration. Unit tmp mặc định Windows bị lỗi
quyền truy cập; dùng basetemp trong thư mục test-results của project và chạy lại đạt.

## Giới hạn và bàn giao

- Mặc định 1 GiB, 60 phút, 3 upload hoạt động/Admin và 20 GiB reservation quota.
  Bộ thử dùng clip tổng hợp ngắn; không khẳng định hiệu năng video dài hay kiểm thử tải.
- Cancel trong lúc FFmpeg chạy không giết ngay tiến trình; chặn publication và dọn
  sau khi nhả lock. Bản ready cũ giữ đến khi xóa tập. Maintenance có thể chậm theo backlog.
- Các upload thuộc người tạo; Admin khác không có quyền xem/sửa phiên của người đó.
- Private local filesystem, chưa object storage/CDN video; sandbox mạng không phải
  sandbox filesystem đầy đủ. Hardening production, image scan, backup/load thuộc gate 12.
- Chưa Player/subtitle/progress (07), thanh toán (10), playback entitlement/device limit (11).
  VIP/Premium tiếp tục nháp, chưa giá/chưa bán; CDN poster vẫn media.sunifactory.com.
- Không tạo tài khoản Admin hoặc nội dung mẫu trong dev. Hướng dẫn dùng tại [MEDIA.md](../MEDIA.md).
