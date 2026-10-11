# Giai đoạn 07 — Player, phụ đề và tiến độ xem

**ĐẠT nghiệm thu kỹ thuật — 10/10/2026 (Asia/Saigon).** Gate 06 đã đạt trước triển khai.

## Kết quả

- Trang chi tiết liệt kê tập có phân trang; `/watch/{id}` phát HLS, chọn Auto/360p/720p
  theo nguồn, bật/tắt phụ đề, native controls, retry hữu hạn và thông báo lỗi.
- Admin quản lý WebVTT theo phiên bản video, văn bản thuần và timing có giới hạn;
  ownership, version chống ghi đè, CSRF/Origin/throttle, audit, tối đa 10 tracks/video.
- Watch progress theo user/episode/job, optimistic version chống request cũ/concurrent;
  chỉ nhận vị trí trong thời lượng, completed tính phía server. Trang chủ có Tiếp tục xem.
- Session + active user + published + quyền Free/Admin kiểm tra trên metadata, playlist,
  từng segment và VTT. VIP/Premium vẫn nháp, không tự cấp quyền người dùng. URL video
  cũ mất hiệu lực khi bản mới ready; tiến độ không áp nhầm sang bản mới. Media no-store,
  path allowlist, symlink/traversal denial, một byte range; không public storage.
- Cleanup media cũng xóa subtitles/progress liên quan khi thu hồi job.

## Migration và kiểm thử

Revision **0006_playback → 0005_media_uploads** thêm subtitle_tracks/watch_progress.
Runtime CRUD hai bảng, không thêm quyền sửa role/plan/audit hay DDL. Downgrade về 0005,
reapply, bảo toàn phim và Alembic schema drift chạy trên PostgreSQL test riêng.

| Kiểm tra | Kết quả |
|---|---|
| Backend pytest non-integration, basetemp trong test-results | 70 passed |
| Script unittest | 2 passed |
| Ruff backend/scripts | Passed |
| Compose PostgreSQL/Redis/Celery/FFmpeg integration thật | 119 passed, 70 unit deselected, exit 0 |
| VTT markup/CSS/encoded markup/control/timing/size rejection | Passed |
| HLS/segment/range/VTT; logout, ẩn phim, paid denial, inactive user, source replacement | Passed |
| Progress concurrent single winner, bounds/IDOR/CSRF/completion/continue filtering | Passed |
| Frontend lint/typecheck/build và unit | Passed; 14 unit tests |
| Full stack standalone Next.js Chromium desktop/mobile | 12 passed (1.1 phút), phát clip thật 20 giây, retry segment 503, chọn quality/subtitle, cue decode, seek/pause/save/resume |
| pnpm audit --prod sau thêm hls.js 1.7.3 pin exact | No known vulnerabilities found |
| Dev compose up --build -d --wait và smoke | Stack healthy, 4 smoke checks passed |

Đã xem ảnh player desktop và kiểm tra chiều ngang bằng browser. Log ignored tại
`test-results/stage07-{integration,browser,dev-stack}.log`; ảnh `player-resume.png`
trong frontend/test-results. Lần E2E đầu phát hiện nhãn select và race hiển thị trạng
thái lưu khi seek nhanh; đã sửa, bổ sung chờ response vị trí mới, chạy lại toàn bộ đạt.
Hls.js nhận startPosition để resume ngay từ fragment phù hợp. Không tính lần lỗi là đạt.

## Giới hạn

Tiến độ lưu định kỳ 10 giây/pause/seek/end, đóng tab đột ngột có thể mất phần chưa lưu.
Native HLS có fallback nhưng Safari thật chưa được thử; E2E mobile là Chromium.
Video tổng hợp ngắn không chứng minh hiệu năng video dài hoặc tải lớn. Subtitle chỉ
nhận subset WebVTT văn bản thuần. Thông tin chi tiết tại [PLAYER.md](../PLAYER.md).
Subscription/device limits/CDN bảo vệ nâng cao theo gate 10/11; không DRM và không thu
hồi byte đã buffer. Không seed Admin/nội dung test trong dev. Giai đoạn 08 chưa triển
khai tại thời điểm nghiệm thu; người dùng đã yêu cầu tiếp tục sau khi gate này đạt.
