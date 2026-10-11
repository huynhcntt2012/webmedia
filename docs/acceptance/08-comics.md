# Giai đoạn 08 — Đạt nghiệm thu kỹ thuật 10/10/2026

Gate 07 đã đạt trước khi triển khai. Admin có CRUD truyện/chương, upload nhiều ảnh,
báo lỗi từng file/thử lại idempotent, preview riêng tư, sắp xếp nguyên tử và xóa cascade.

Migration `0007_comic_admin`: version comics/chapters và comic_page_assets. JPEG
chuẩn hóa lưu BYTEA để bytes, metadata và audit cùng transaction; quota local 2 GiB.
Upgrade/downgrade về 0006/reapply, bảo toàn comic và Alembic drift đã thử trên Compose
test riêng. Không rollback database dev. Quyết định và giới hạn tại [COMICS.md](../COMICS.md).

| Kiểm tra | Kết quả |
|---|---|
| Backend unit / script | 75 passed / 2 passed |
| PostgreSQL, Redis, Celery, FFmpeg và decoder Linux thật | 125 integration passed, 75 deselected |
| Frontend lint, typecheck, build, unit | Passed, 14 unit passed |
| Standalone Next.js E2E desktop/mobile | 14 passed (1.2 phút) |
| RBAC/CSRF/parent ID, checksum/body/quota, races/version/idempotency | Passed |
| Decode/re-encode, metadata stripping, SVG/animation/bomb rejection | Passed |
| Runtime dependency audit sau thêm Pillow 12.3.0 | No known vulnerabilities found |
| Local stack và smoke | Healthy; 4 checks passed; restricted image decoder passed |

Đã kiểm tra ảnh chụp mobile, preview decode và không tràn ngang. Log ignored tại
`test-results/stage08-{unit,integration,browser}.log`. Lượt E2E cuối ban đầu bị gián
đoạn do Docker Engine dừng: 8 failed/6 passed, không tính là đạt. Sau khởi động
Docker, chạy lại toàn bộ 14 tests đạt trên mã decoder cuối cùng.

Decoder child không mạng, giới hạn CPU/memory/output/time; API non-root/read-only
được kiểm tra thực tế. Ảnh chỉ qua endpoint Admin no-store. Không có public reader
ở gate này; Admin cùng quản lý catalogue. BYTEA/quota không thay kiểm thử tải/backup
production; E2E mobile là Chromium, chưa Safari thật. Không seed dữ liệu thử vào dev.

Giai đoạn 09 được người dùng yêu cầu tiếp tục sau khi gate này đạt.
