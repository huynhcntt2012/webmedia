# Giai đoạn 03 — Đăng nhập và phân quyền

**ĐẠT nghiệm thu kỹ thuật — 09/10/2026 (Asia/Saigon).**
Gate 02 đã đạt trước khi triển khai; xem `02-database.md`.

## Kết quả

Register/login, refresh rotation/reuse detection, logout/logout-all, hồ sơ cá nhân
và Admin/User phía API; frontend /register, /login, /account, /admin. Không tạo
admin mặc định. Free mặc định; VIP/Premium vẫn nháp. Lệnh cấp Admin và flow trong
[AUTH.md](../AUTH.md). Catalogue giai đoạn 04 chưa bắt đầu.

Migration `0003_auth` thêm session/token hash; không đổi role enum đã có ở 0002.
Quyền runtime chỉ bổ sung các thao tác cần cho auth, không tự nâng role/plan.
Upgrade/rollback/reapply, bảo toàn user và Alembic drift đều chạy PostgreSQL thật
trong Compose test riêng. Stack dev chỉ upgrade, giữ volume hiện có.

## Bằng chứng kiểm thử

| Kiểm tra | Kết quả |
|---|---|
| Backend pytest -m "not integration" | 25 passed |
| Script unittest discover | 2 passed |
| Ruff backend/scripts | Passed |
| Compose integration: up --build --abort-on-container-exit --exit-code-from tests | 64 passed, 25 unit deselected, exit 0 |
| Frontend lint/typecheck | Passed |
| Frontend Vitest | 6 passed |
| Next.js production build | Passed |
| E2E_AUTH=1 Playwright, standalone build + Compose E2E backend thật | 8 passed; desktop và mobile, không skip |
| Dependency audit Python runtime và pnpm --prod | Không có lỗ hổng đã biết được báo cáo |
| Dev Compose up --build -d --wait | Exit 0, 5 services healthy; bootstrap/migrate exited 0 |
| scripts/smoke.py | 4 PASS |
| Dev proxy: login/CSP nonce, anonymous me, CSRF | 200 / nonce, 401, 200 |
| Secret/log gitignore | .env và log local bị ignore |

Integration gồm Argon2, validation không lộ password, chống mass assignment,
duplicate register response, login sai/unknown/disabled, RBAC 401/403/Admin,
role/active có hiệu lực ngay, expiry, refresh hash/rotation/replay và hai request
đồng thời; logout kể cả thiếu refresh cookie, logout-all không ảnh hưởng user khác;
CSRF/Origin, rate limit IP/account, bỏ qua IP giả, Redis outage 503, body 413,
cookie production Secure/__Host-, migration rollback/reapply và quyền DB.
Các kiểm thử PostgreSQL/Redis/Celery/FFmpeg từ giai đoạn trước tiếp tục đạt.

Browser kiểm tra đăng ký, sai mật khẩu, đăng nhập, cookie HttpOnly, không có token
localStorage, refresh khi access cookie mất, User bị chặn Admin và logout. Đã xem
ảnh trang account desktop/mobile, không thấy tràn bố cục. Tài khoản E2E chỉ nằm
trong database test tmpfs. Hai stack test đã dọn; stack local vẫn chạy.

## Giới hạn

- CI đã thêm full-stack browser job nhưng chưa chạy remote (chưa có remote repo).
- Starlette TestClient còn cảnh báo deprecated httpx; tất cả tests đạt.
- Local HTTP dùng cookie không Secure; production bật Secure, yêu cầu HTTPS.
- Chưa email verification/reset/MFA, session cleanup job; giới hạn IP qua proxy
  chia sẻ quota, cần trusted gateway và đánh giá tải trước production.
- CSP style còn unsafe-inline; script dùng nonce. Chưa tuyên bố sẵn sàng production.

Gate 03 đã đóng; giai đoạn 04 có thể bắt đầu theo yêu cầu tiếp theo.
