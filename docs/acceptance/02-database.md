# Giai đoạn 02 — Database, migration và seed

**Trạng thái: ĐẠT nghiệm thu kỹ thuật — 09/10/2026 (Asia/Saigon).**

Giai đoạn 01 đã đóng gate trước khi triển khai: 4 integration tests thật đạt,
stack smoke đạt, bằng chứng nằm trong hồ sơ `01-bootstrap.md`.

## Phạm vi đã hoàn tất

- 7 SQLAlchemy typed models: plans, users, movies, episodes, comics, chapters,
  comic_pages; relationships, UUID, UTC-capable timestamptz, foreign keys, unique,
  check constraints và indexes. Xem sơ đồ/chi tiết ở `docs/DATABASE.md`.
- Revision `0002_domain` nối `0001_bootstrap`; frozen PostgreSQL DDL không import
  model hiện tại. Có timestamp triggers cho mọi bảng; upgrade/rollback/reapply đã
  chạy trên PostgreSQL thật, Alembic drift kiểm tra cả server defaults.
- Transaction helper commit/rollback/close; seed một statement atomic, chạy lặp
  và đồng thời an toàn, giữ nguyên dữ liệu kinh doanh đã chỉnh.
- Theo lựa chọn người dùng: Free active/giá 0; VIP/Premium inactive, chưa giá,
  chưa thời hạn/giới hạn thiết bị, không được bán. Không seed admin/user/mật khẩu.
- Tách role bootstrap, migrator và runtime; API/worker không còn dùng superuser.
  Runtime chỉ đọc catalogue/plans, không đọc users/alembic_version hoặc sửa schema,
  không ghi dữ liệu, tạo bảng tạm hay chuyển sang role migrator.
- Bootstrap nâng cấp được volume giai đoạn 01, chuyển ownership version table;
  script bổ sung secret giữ nguyên cấu hình cũ; PostgreSQL log đã bỏ failing row/SQL.

## Kiểm thử đã chạy

| Lệnh / kiểm tra | Kết quả |
|---|---|
| `pytest -m "not integration"` trong backend | **21 passed**, integration không thuộc lượt unit này |
| `python -m unittest discover -s scripts -p "test_*.py"` | **2 passed**: sinh secret và nâng `.env` không ghi đè |
| `ruff check backend scripts --target-version py312` | Passed |
| `docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests` | **43 passed**, 21 unit deselected; test container exited 0 |
| Migration 0002 → 0001 → head; head → base → head | Passed trên database test riêng |
| Seed hai lần / 8 lần đồng thời / giữ giá đã chỉnh | Passed |
| FK, unique email/episode/chapter/page/storage key, plan CHECK, cascade, unsafe path | Passed |
| Reorder trang trong transaction có deferred uniqueness; timestamp raw SQL | Passed |
| Transaction lỗi rollback toàn bộ ghi; runtime permission denial; migrator non-superuser | Passed |
| PostgreSQL cấu hình log không in failing row/SQL/parameters | Passed |
| Docker dev `up --build -d --wait` | Exit 0; db-bootstrap/migrate exited 0; 5 dịch vụ healthy |
| `python scripts/smoke.py` | **4 PASS**, gồm web → API → PostgreSQL/Redis |
| Task Celery sau nâng cấp dev | `status: ok`, FFmpeg 5.1.9-0+deb12u1 |
| Query bằng credential của API | current_user = suni_runtime; đúng 3 gói với trạng thái đã chọn |
| `.env` và log local bị gitignore | Đã xác nhận |

Tổng lượt kiểm thử liên quan cuối cùng: **66 tests passed** (21 unit backend,
2 script tests, 43 integration). Lượt integration đầu có 41 bài đạt; sau khi bổ sung
kiểm tra log/database và page constraints, lượt cuối có 43 bài đạt.

Database integration là `suni_test` trên tmpfs, project `suni-integration-test`.
Fixtures mô phỏng baseline do bootstrap owner sở hữu để kiểm chứng nâng cấp cũ.
Chỉ database test bị downgrade; volume dev được giữ nguyên. Stack test đã dọn bằng
`docker compose -f compose.test.yaml down`; stack dev vẫn chạy.

## Nghiệm thu và giới hạn

- Migration, seed, unit/integration, bảo mật role và stack smoke đều đạt.
- Không thay đổi giao diện hoặc triển khai giai đoạn 03; frontend E2E không chạy lại
  ở giai đoạn này vì source giao diện không đổi. Web health và kết nối thực đã kiểm tra.
- Không đổi dependency; lockfiles giữ nguyên bộ đã audit ở giai đoạn 01.
- Cảnh báo deprecated httpx của Starlette TestClient vẫn còn; tests vẫn đạt.
- CI workflow đã cập nhật nhưng chưa chạy trên remote; không có repository remote.
- Đây là môi trường local dev; chưa phải production, chưa có auth/media/payment.
- Các giới hạn của prefix hash/email check/plan_code và quyền lợi chưa cấu hình
  được mô tả ở `docs/DATABASE.md`; không dùng chúng thay cho validation/entitlement
  của các giai đoạn sau.

Giai đoạn 03 có thể bắt đầu theo yêu cầu tiếp theo; chưa triển khai trong lần này.
