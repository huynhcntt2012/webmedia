# Giai đoạn 09 — Đạt nghiệm thu kỹ thuật 10/10/2026

Gate 08 đã đạt trước khi bắt đầu. Đã có thư viện truyện published, tìm kiếm/phân
trang, danh sách chương, Reader cuộn dọc/lật trang, keyboard, lazy images và bookmark
theo tài khoản. Lưu mode theo chương; reorder giữ ID ảnh, xóa ảnh có fallback an toàn.

Migration `0008_reader` thêm reading_progress, FK/check constraints/version. Upgrade,
downgrade về 0007 rồi reapply và Alembic drift chạy trong Compose test độc lập;
giữ truyện khi rollback. Dev chỉ upgrade, không rollback hay xóa volume.

| Kiểm tra | Kết quả |
|---|---|
| Backend unit | 83 passed, 130 integration deselected |
| Script unit | 2 passed |
| PostgreSQL/Redis/Celery/FFmpeg/decoder integration thật | 130 passed, 83 unit deselected, exit 0 |
| Frontend unit | 16 passed |
| Frontend lint/typecheck/build; Ruff | Passed |
| Standalone Next.js Chromium desktop/mobile | 16 passed (1.4 phút), bản CSS cuối |
| Runtime dev upgrade/build và health | Healthy; 4 smoke checks passed |
| Local /comics và /api/comics, private cache policy | 200, no-store; HTML có CSP nonce |
| Runtime đọc schema reading_progress | Passed |

Tổng 247 tests đạt. Log ignored `test-results/stage09-{unit,integration,build,browser,dev-stack}.log`;
ảnh comic-reader.png desktop/mobile đã xem, kiểm tra overflow tự động đạt.
E2E đã phát hiện trang tĩnh không nhận CSP nonce: chuyển trang Reader sang dynamic,
giữ CSP chặt. Test sửa chờ navigation trước khi ghi URL và chọn alert ứng dụng
thay vì route announcer Next.js. Lần cuối chạy lại toàn bộ đạt. Integration sửa
expectation logout theo contract 204 hiện có; không thay behavior auth.

## Bảo mật và giới hạn

Metadata truyện chỉ published; ảnh/bookmark luôn yêu cầu session hoạt động, parent
chapter/page đúng và quyền đọc. Tests kiểm tra logout/inactive user/ẩn truyện/paid
denial, IDOR, CSRF/body/bounds, hai user độc lập, concurrent single winner, stale
chapter version, reorder/delete và rollback. Client không chỉ định user_id.
Ảnh no-store, không optimizer/CDN public; `.env` và log kiểm thử được Git ignore.
Không thêm dependency ở gate 09; audit dependency được ghi ở gate 08.

Đóng tab đột ngột có thể mất phần chưa lưu trong chu kỳ 5 giây; có nút Lưu vị trí.
Quyền được kiểm tra mỗi request mới; UI kiểm tra lại mỗi 60 giây. Không thu hồi byte
đã tải hay chống chụp màn hình. Mobile E2E là Chromium, chưa Safari thật. Compose
chỉ local; payment, thiết bị, CDN, tải lớn/backup/production theo gate 10–12.
Xem [READER.md](../READER.md). Giai đoạn 10 chưa bắt đầu.
