# Giai đoạn 06 — Upload và xử lý video

Trong Admin, mở phim → chọn **Video** ở tập → chọn MP4 → **Bắt đầu upload**.
Có thể tạm dừng, tải lại trang rồi chọn đúng file để tiếp tục. Trình duyệt kiểm tra
SHA-256 của các chunk đã gửi trước khi gửi tiếp; không đọc cả video vào RAM.
Sau khi gửi đủ, giao diện theo dõi hàng đợi và hiển thị thumbnail cùng các độ phân giải.
Video được lưu riêng tư, chưa có Player hoặc đường dẫn HLS công khai.

## Giới hạn local

- MP4 chứa một video H.264/H.265, tối đa 4 streams, 60 phút, 4096×2160, 60 fps.
- Mặc định file tối đa 1 GiB, cấu hình `UPLOAD_MAX_BYTES` tối đa 2 GiB.
- Chunk cố định 4 MiB, chunk cuối ngắn hơn; SHA-256, offset, độ dài và magic đều kiểm tra phía server.
- Phiên hết hạn sau 24 giờ. Video ready không bị xóa theo TTL này.
- `UPLOAD_ACTIVE_LIMIT=3` giới hạn upload/queued/processing theo Admin, một tác vụ đang hoạt động mỗi tập.
- `MEDIA_QUOTA_BYTES=21474836480` (20 GiB). Mỗi phiên dự trữ kích thước nguồn + 2 GiB đầu ra;
  quota được khóa transaction khi cấp phiên. Sau ready, xóa nguồn và tính theo dung lượng đầu ra.
  Cũng kiểm tra dung lượng đĩa còn trống; không thay cho giới hạn volume ở production.
- HLS H.264/AAC, segment 4 giây, 360p/720p theo kích thước nguồn, không nâng độ phân giải;
  nguồn thấp hơn 360p tạo một rendition theo chiều cao chẵn. Thumbnail JPEG rộng 320px.
- Tối đa ba lần xử lý/phiên. Lỗi trả mã cố định, không trả stderr hoặc đường dẫn hệ thống.
- Worker concurrency 1, container tối đa 2 GiB RAM và 128 PIDs. Mỗi tiến trình codec
  có timeout, giới hạn CPU/address space/file size/FD, không shell và không kế thừa secret.

## API và tính nhất quán

Mọi route ở `/admin` yêu cầu Admin; upload/job/thumbnail còn yêu cầu đúng người tạo.
Mutation có CSRF, Origin và rate limit như Admin catalogue. API và proxy Next.js
chặn body chunk trên 4 MiB; JSON Admin vẫn giới hạn 32 KiB. Không có route nhận URL video.

1. `POST /admin/uploads`: episode_id, idempotency_key UUID, filename, total_bytes, content_type.
   Gửi lại cùng key và metadata trả cùng phiên; metadata khác trả 409.
2. `PUT /admin/uploads/{id}/chunks?offset=...`: octet-stream, header `X-Chunk-SHA256`.
   Gửi lại đúng chunk trả cùng offset đã nhận; thay dữ liệu chunk cũ bị từ chối.
3. `GET /admin/uploads/{id}`: offset, manifest checksum và trạng thái job.
4. `POST /admin/uploads/{id}/complete`: tạo một job duy nhất và commit trước khi gửi Redis.
   `dispatched=false` nghĩa job đã lưu, đang đợi gửi lại; không cần upload lại.
5. `POST .../retry` cho job failed còn lượt và TTL; `DELETE .../{id}` hủy phiên chưa ready.
6. `GET /admin/episodes/{id}/uploads` trả lịch sử của Admin hiện tại.
   `GET /admin/media-jobs/{id}/thumbnail` trả JPEG riêng tư, `Cache-Control: no-store`.

Celery Beat gửi maintenance mỗi 30 giây: dispatch queued, phục hồi processing quá 30 phút,
dọn cancelled/expired/orphan. Advisory lock theo UUID ngăn duplicate deliveries xử lý cùng
file. Worker xác minh lại từng checksum và tổng dung lượng trước FFprobe/FFmpeg. Ghi filesystem
trước commit chunk; lần gửi lại truncate về offset đã commit nếu lần trước bị gián đoạn.
Job chỉ ready sau khi playlist, segment và thumbnail hoàn tất rồi đổi tên thư mục đầu ra.

Hủy khi đang chuyển mã chặn công bố kết quả; không lập tức giết tiến trình. File được dọn khi
worker nhả lock, tối đa phụ thuộc timeout và backlog. Xóa tập/phim đặt FK upload về NULL để
maintenance thu hồi file. Bản ready cũ được giữ khi upload bản mới; xóa tập dọn mọi phiên.
429 có thể xảy ra khi gửi quá nhanh: tạm dừng rồi tiếp tục sau khi hết giới hạn.

## Lưu trữ và bảo mật

Named volume `suni_media_data` chỉ gắn vào API/worker tại `/var/lib/suni-media`.
Path từ UUID server; tên file client chỉ là metadata. Không gắn volume vào web, không
đưa media lên `media.sunifactory.com` (domain này tiếp tục chỉ dành cho poster).
Decoder ép demuxer MOV/MP4, không theo external data references, protocol whitelist
file/pipe; seccomp chặn tạo socket/socketpair ở kernel trước exec và fail closed nếu
không cài được. Đây không phải sandbox filesystem đầy đủ chống lỗ hổng native codec;
worker tách biệt, cập nhật image/FFmpeg và hardening production vẫn cần gate 12.

Migration `0005_media_uploads` thêm upload_sessions/upload_chunks/media_jobs/media_variants.
Downgrade xóa các bảng mới; chỉ thử trong Compose test riêng. Không downgrade dev.
Backup production cần bao gồm cả database và private media, được xử lý ở giai đoạn 12.

## Kiểm thử

`compose.test.yaml`: PostgreSQL/Redis/Celery/FFmpeg thật, quota/ownership/CSRF/offset/hash,
outbox fault injection và recovery qua worker thật, HLS decode, retry, cleanup, migration drift/rollback.
`compose.e2e.yaml`: trình duyệt desktop/mobile với standalone Next.js, upload MP4 thật,
poll ready và kiểm tra thumbnail đã decode. Dùng `down -v` chỉ với hai project test này
để xóa volume test; tuyệt đối không dùng với project dev có dữ liệu cần giữ.
