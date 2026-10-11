# Giai đoạn 07 — Trình phát và tiến độ xem

Xuất bản phim có video ready, mở trang chi tiết phim rồi chọn tập để xem.
Người xem cần đăng nhập. Trang `/watch/{episode UUID}` có điều khiển phát/dừng,
seek/âm lượng/toàn màn hình của trình duyệt, chọn Auto hoặc rendition, chọn/tắt phụ đề.
Trang chủ hiển thị tối đa 20 tập đang xem dở của tài khoản hiện tại.

## Quyền truy cập

Mỗi lần đọc thông tin player, master/variant playlist, segment và phụ đề đều kiểm tra
cookie/session còn hiệu lực, tài khoản active, phim published và video ready hiện tại.
Người dùng chỉ xem phim Free; VIP/Premium vẫn nháp nên không suy quyền từ plan_code
của tài khoản. Admin được kiểm tra bản phát phim published của mọi gói. Nội dung draft
và archived không phát, kể cả bằng URL cũ. Video mới ready thay thế bản cũ cho playback;
URL bản cũ bị từ chối và tiến độ cũ không tự áp dụng lên video mới.

Media vẫn ở private volume, proxy Next.js chỉ chuyển tiếp path allowlist. Backend chỉ
nhận master.m3u8, `{height}p/index.m3u8`, `{height}p/segment_NNNNN.ts`, chặn symlink và
traversal; không nhận URL ngoài hoặc đường dẫn nguồn. Mọi response no-store, hỗ trợ một
HTTP byte range. Đây là baseline cần thiết cho Player; giới hạn thiết bị, subscription
có hạn và cơ chế CDN/token ở gate 10/11 chưa triển khai. Byte đã buffer không thu hồi được.

## Tiến độ

Migration `0006_playback` thêm watch_progress và subtitle_tracks. Progress khóa chính
(user_id, episode_id), gắn job_id của video và version tăng dần. API không nhận user_id
hay completed từ client. Upsert đầu tiên và update theo version có điều kiện, trả 409
cho request cũ/concurrent. Position nguyên millisecond giới hạn theo thời lượng worker;
completed tính khi còn không quá min(10 giây, 5% thời lượng).

Player lưu mỗi 10 giây khi đã bắt đầu xem, khi pause, seek hoặc ended; visibility hidden
cũng thử lưu. Request được tuần tự hóa/coalesce trong player. Đóng tab/kill trình duyệt
đột ngột có thể mất phần cuối chưa lưu. Khi xung đột tab/thiết bị, player báo tải lại trang
thay vì ghi đè. Xem lại video completed bắt đầu từ 0. Bản video mới reset vị trí nhưng
giữ version để đồng bộ. Continue watching loại phim ẩn, không đủ quyền, hoàn thành và
video cũ. Xóa user/episode/job cascade dữ liệu progress liên quan.

## Phụ đề

Admin tạo video chọn **Phụ đề WebVTT**, nhập/dán nội dung hoặc chọn `.vtt`, đặt mã ngôn
ngữ (vi, en, pt-BR) và tên hiển thị. Tối đa 10 ngôn ngữ/job, 128 KiB UTF-8/file, 2000 cues,
4 dòng văn bản/cue, 2000 ký tự/cue. Hỗ trợ timestamp HH:MM:SS.mmm hoặc MM:SS.mmm và
cue ID đơn giản. Không nhận HTML, CSS/STYLE/REGION, cue settings hoặc external reference.
Server chuẩn hóa thời gian, escape văn bản, kiểm tra thứ tự/thời lượng; không lưu path
client. PUT/DELETE kiểm tra version, Admin + ownership + CSRF/Origin/rate limit và audit.
Phụ đề gắn phiên bản video, không tự chuyển sang bản mới. Reader chỉ trả VTT qua cùng
authorization với HLS. Không public CDN phụ đề.

## Browser và vận hành

Hls.js được pin trong lock, chạy không Web Worker để giữ CSP chặt; chỉ thêm `media-src
'self' blob:` cho MediaSource. Có native HLS fallback. Chuyển quality native tải lại
variant và giữ currentTime. HLS loader có retry hữu hạn; lỗi fatal được thử phục hồi
tối đa hai lần rồi hiển thị nút tải lại. Mỗi phút kiểm tra session; hết hạn access được
refresh qua luồng auth có sẵn, logout/revoke bị từ chối ngay ở request media kế tiếp.
Không ghi token hoặc VTT content vào nhật ký.

Kiểm thử full stack chạy trên standalone Next.js + Compose E2E riêng, clip tổng hợp
20 giây, Chromium desktop/mobile. Không khẳng định đã kiểm thử Safari thật, video dài
hoặc hiệu năng tải lớn. API migration/rollback chỉ chạy trong Compose test, dev chỉ upgrade.

Tham chiếu triển khai: [Hls.js API](https://hlsjs.video-dev.org/api-docs/hls.js.hls),
[startLoad](https://hlsjs.video-dev.org/api-docs/hls.js.hls.startload),
[HlsConfig](https://hlsjs.video-dev.org/api-docs/hls.js.hlsconfig).
