# Giai đoạn 11 — Đạt nghiệm thu kỹ thuật

Chốt bản ghi ngày 11/10/2026, dựa trên các lần chạy ngày 10/10/2026.
Theo ngoại lệ thứ tự do người dùng yêu cầu, triển khai 11 trước khi quay lại
nghiệm thu SePay thật của giai đoạn 10. Gate 10 vẫn pending.

Migration `0010_content_access`: quyền Admin cấp riêng và lease phiên thiết bị.
Kiểm tra quyền trên từng tài nguyên HLS, phụ đề và ảnh truyện; không cấp quyền từ
subscription sandbox. Trang `/devices` quản lý/thu hồi phiên của chính tài khoản.
Giá/seed VIP/Premium giữ nguyên nháp. Xem [thiết kế](../CONTENT-SECURITY.md).

| Kiểm tra thực chạy | Kết quả |
|---|---|
| Backend unit | 104 passed |
| Script unit | 2 passed |
| Compose PostgreSQL/Redis/Celery/FFmpeg integration thật | 150 passed, 104 deselected |
| Frontend unit | 16 passed |
| Standalone browser desktop/mobile | 18 passed, 1.4 phút |
| Ruff, frontend lint/typecheck/build | Passed |
| Rollback/reapply và Alembic drift | Passed, database test riêng |
| Dev build/migration/health ngày 10/10 | Healthy, theo stage11-dev-stack.log |
| Ảnh UI devices mobile và kiểm tra overflow | Passed |

Tổng 290 tests đạt. Các kiểm thử mới bao gồm cấp/thu hồi/hết hạn quyền, Premium
bao gồm VIP, ba phiên tranh hai chỗ, IDOR, CSRF, phiên đã thu hồi, nhả chỗ do hết
lease và giảm hạn mức. Các kiểm thử media traversal, unpublished, logout và
subscription sandbox không cấp quyền tiếp tục đạt. Hai lỗi test đầu tiên (status
register 202 và danh sách bảng schema mới) đã sửa rồi chạy lại toàn bộ integration.

Log lưu ignored trong `test-results/stage11-*.log`; screenshot trong frontend
test-results. Không coi cơ chế này là DRM; bytes đã gửi không thể thu hồi, thiết bị
là phiên trình duyệt. Gate 12 có thể bắt đầu; triển khai Internet chưa nghiệm thu.

Kiểm tra lại ngày 11/10: Docker Desktop chưa chạy lúc đầu, nên smoke lúc đó bị
connection refused; đây là trạng thái môi trường hiện tại, không được tính là pass.
Sau khi khởi động Docker lại, stack healthy và 4 smoke checks đều passed.
