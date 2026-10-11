# Giai đoạn 10 — Local hoàn tất; chưa nghiệm thu toàn bộ

Ngày 10/10/2026. Đã đọc gate 09 accepted trước khi triển khai. Người dùng xác nhận:
giữ VIP/Premium nháp, giá mẫu chỉ trong DB test; chưa có tài khoản SePay Test mode
và endpoint webhook, yêu cầu hoàn thiện local trước. Không bắt đầu giai đoạn 11.

Đã triển khai trang `/plans`, danh sách gói, tạo/lịch sử đơn theo tài khoản,
subscription thử nghiệm, webhook HMAC và API Admin xem kết quả đối soát. Giá server
snapshot; UI retry cùng idempotency key khi mất response. Migration `0009_payments`
thêm orders/events/subscriptions, FK/check/index/unique; seed thương mại không đổi.

| Kiểm tra thực chạy | Kết quả |
|---|---|
| Backend unit | 95 passed |
| Script unit | 2 passed |
| Compose integration PostgreSQL/Redis/Celery/FFmpeg thật | 146 passed, 95 unit deselected, exit 0 |
| Frontend unit | 16 passed |
| Standalone Next.js Chromium desktop/mobile | 18 passed (1.4 phút) |
| Ruff, frontend lint/typecheck/build | Passed |
| Upgrade → rollback 0008 → reapply, drift | Passed trên Compose test riêng |
| Dev Docker rebuild/upgrade/health | Healthy, 4 smoke checks passed |
| Dev billing disabled, VIP/Premium null giá và unavailable | Passed qua API local |
| /plans + CSP nonce | Passed |
| SePay Test mode gửi webhook thực tới endpoint công khai | **Chưa chạy — thiếu tài khoản/secret/endpoint** |

Tổng 277 tests local đạt. Webhook trong test được ký bởi code kiểm thử và gửi qua
API/Next proxy thật; đây là kiểm thử contract local, **không phải provider sandbox
E2E**. Không dùng SQLite/mocks thay bằng chứng PostgreSQL. Bản dev chưa bật payment,
không ghi giá mẫu, không sửa `.env`. Không thêm dependency runtime.

## Bảo mật và nhất quán

Đã kiểm tra HMAC raw bytes/timestamp, body limit, strict amount/currency/date,
duplicate JSON keys, receiver bank/account/VA, incoming, code/content, cửa sổ đơn;
idempotency và quota tạo đơn; provider ID concurrent duplicate/replay/conflict;
extra payment không cấp thêm ngày; gia hạn hai đơn đồng thời; IDOR/CSRF/RBAC;
giả redirect không xác nhận thanh toán; transaction lỗi rollback event rồi retry đạt.
Runtime không DELETE billing records hay UPDATE/DELETE subscription, không sửa plans.
Chỉ sandbox, bị chặn trên APP_ENV=production; subscription test không mở paid media.

Ảnh billing-local.png mobile đã xem, overflow desktop/mobile được kiểm thử.
Log ignored tại `test-results/stage10-{unit,integration,frontend-unit,build,browser,dev-stack}.log`.
Các stack test được xóa riêng sau khi kiểm thử; stack dev và dữ liệu dev giữ nguyên.

## Điều kiện còn thiếu để mở gate 11

Cấu hình SePay **Test mode thật**, secret riêng trong env local, tài khoản nhận thử,
endpoint HTTPS; chạy provider delivery + replay + các trường hợp sai qua hệ thống
SePay và lưu bằng chứng đã che dữ liệu nhạy cảm. Chỉ sau đó cập nhật gate 10 accepted.
Không tính 277 tests local là thay thế điều kiện này. Hướng dẫn, contract và giới hạn
được ghi tại [PAYMENTS.md](../PAYMENTS.md). Giá thương mại tiếp tục nháp theo yêu cầu.

## Ngoại lệ thứ tự do người dùng xác nhận

Sau bản ghi trên, người dùng yêu cầu triển khai 11 và 12 trước rồi quay lại kiểm tra 10. Điều này cho phép bắt đầu 11; không thay thế nghiệm thu SePay thật, không mở bán VIP/Premium.
