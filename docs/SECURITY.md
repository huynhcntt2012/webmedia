# Bảo mật theo từng lớp

## Giai đoạn 01

- `.env` bị gitignore; script tạo ba secret riêng bằng `secrets.token_hex(32)`
  và từ chối ghi đè file. Không in secret ra stdout. Placeholder không dùng để chạy app.
- Pydantic từ chối secret ngắn, URL database không đúng driver, Redis không mật khẩu,
  wildcard host, origin không hợp lệ; production yêu cầu HTTPS origin.
- CORS exact origin; TrustedHost; API tắt docs trong production; response không cache;
  request ID do server cấp; log chỉ route template/method/status/duration.
  Không log query, body, Authorization, cookie hoặc chuỗi lỗi database.
- Liveness tách readiness. Readiness chỉ trả trạng thái dependency, không trả credential
  hoặc địa chỉ nội bộ. Readiness hiện chưa kiểm tra worker; worker có healthcheck riêng.
- API/web/worker chạy UID 10001, read-only root filesystem, drop capabilities,
  no-new-privileges. DB/cache không publish port; API/web chỉ bind loopback.
  DB/cache ở Docker internal network và phải có mật khẩu.
- Celery chỉ nhận JSON; không cho deserialize pickle. Không có API công khai enqueue task.
  FFmpeg probe dùng argv cố định, timeout và không dùng shell.
- Migrations chạy service riêng, API/worker phụ thuộc thành công của migration.
  Compose test có DB/tmpfs độc lập và không mount dữ liệu ứng dụng.

## Giai đoạn 02

- Tách bootstrap/migrator/runtime. API/worker không nhận secret superuser hoặc
  migrator; tại giai đoạn 02 runtime chỉ đọc 6 bảng catalogue/plans, không đọc users/alembic_version,
  không ghi, DDL, TEMP hoặc SET ROLE. Có integration kiểm tra quyền bị từ chối thật.
- Hai secret database độc lập được thêm vào `.env` bằng script append-only.
  Bootstrap chạy cả trên volume cũ, không reset database; dừng nếu có role membership lạ.
- Foreign keys, uniqueness, checks và timestamp triggers được áp dụng trong DB.
  User mới mặc định role user, plan Free. Không seed admin/user/mật khẩu.
- Paid plans chưa có giá/quyền lợi được giữ inactive và không bán. Seed không
  ghi đè cấu hình đã chỉnh; các giai đoạn thanh toán/media phải kiểm tra quyền riêng.
- PostgreSQL dùng log_error_verbosity=terse, log_min_error_statement=panic,
  log_parameter_max_length_on_error=0 và log_statement=none để tránh ghi failing
  row/SQL có thể chứa mật khẩu hoặc dữ liệu riêng tư vào log.
- Migration rollback chỉ được kiểm thử trong project test, database suni_test.
  Nâng cấp stack dev giữ volume và dữ liệu, không downgrade.

## Giai đoạn 03

- Argon2id; access JWT 5 phút; refresh lưu hash, rotation khóa hàng PostgreSQL,
  phát hiện replay thu hồi cả phiên. Kiểm tra user/session/role mỗi request.
- HttpOnly/host-only/SameSite cookies; Secure và __Host- khi production. Signed
  CSRF + exact Origin; Redis rate limit IP/account và fail closed khi Redis lỗi.
- Runtime được đọc users, INSERT cột đăng ký, đọc/tạo session/token, cập nhật
  revoked_at/consumed_at; không sửa role/plan/active, DDL hoặc DELETE users.
- Không trả password/hash/token trong JSON hoặc validation; register/login lỗi
  chung chống dò email, dummy hash cho login không tìm thấy user.
- Proxy allowlist, body tối đa 8 KiB, CSP script nonce từng request. Integration
  kiểm tra CSRF/RBAC, cookies production, replay/race, logout và Redis outage.
- Chi tiết vận hành và cấp Admin trong [AUTH.md](AUTH.md).

## Giai đoạn 04

- API catalogue read-only; lọc published ở list/count/search/detail; draft/archived
  trả 404 như nội dung không tồn tại. Response whitelist không có media/storage/user data.
- Query bind parameters, escape wildcard, q/page/page_size/sort có giới hạn;
  statement timeout và response lỗi không tiết lộ database. Không thêm runtime grants.
- SSR fetch cố định upstream; React escape mô tả, không render HTML tùy ý. E2E dùng
  nội dung script để xác nhận không thực thi. CSP nonce và auth regression vẫn đạt.
- Metadata paid plan public không phải quyền playback; quyền media vẫn ở giai đoạn 11.

## Giai đoạn 05

- Mọi API Admin đọc/ghi kiểm tra session và role; mọi mutation thêm CSRF/Origin/rate
  limit. Body 32 KiB, extra fields bị từ chối; UUID, slug, độ dài và số tập có validation.
- Row lock + version chống lost update. Tập phải thuộc đúng phim. Unique/FK xử lý
  bằng 409; nhật ký và dữ liệu commit trong một transaction, trước khi gửi response.
- Runtime được CRUD movies/episodes/genres/movie_genres và SELECT/INSERT audit_events;
  không sửa/xóa audit, sửa role/plan người dùng hoặc DDL. Credential runtime vẫn dùng
  chung API/worker local; production cần tách worker theo quyền tối thiểu.
- Poster dùng HTTPS và exact hostname media.sunifactory.com do người dùng cung cấp;
  không server fetch/DNS lookup/image optimizer. CSP chỉ thêm host được cấu hình.
  Từ chối SVG, userinfo/port/query/traversal. Trailer chỉ YouTube URL chuẩn, mở qua link.
- Nội dung vẫn render text; không dùng HTML injection. Browser kiểm tra XSS và
  placeholder khi CDN không tải được. CDN thật cần phục vụ file đúng; validation URL
  không chứng minh file tồn tại hoặc quyền sử dụng nội dung.
- Chi tiết thao tác/API/quyền và migration: [ADMIN.md](ADMIN.md).

## Giới hạn đã biết, phải xử lý trước khi production

- Đây là nền tảng local, đã có auth; chưa có upload, thanh toán hoặc entitlement.
  Không expose dev stack ra Internet.
- CSP còn inline style; script đã bỏ unsafe-inline và dùng nonce được browser test.
- Chưa xác minh email/reset mật khẩu/MFA hoặc retention job cho session/token.
  Qua Next.js các client chia sẻ IP proxy; cần trusted gateway trước production.
- Bootstrap vẫn là superuser do image PostgreSQL tạo và chỉ được dùng bởi service
  provisioning one-shot. Production phải quản lý quyền/secret provisioning riêng.
- Secrets qua environment phù hợp local dev. Production cần secret manager/Docker
  secrets và rotation; Redis TLS/ACL, network segmentation và queue credentials riêng.
- Logging API cố ý không ghi stack trace để tránh lộ secret. Giai đoạn 12 bổ sung
  error reporting đã scrub dữ liệu và retention/access policy cho log.
- Container tags theo minor/OS, chưa pin image digest. Giai đoạn 12 pin digest và
  quét CVE/FFmpeg codec; lock Python/Node đã pin dependency đã cài.
- Docker internal network cô lập DB/cache/worker. API/web có thêm bridge `edge`
  để publish port loopback trên Docker Desktop, vì vậy hai dịch vụ này có outbound.
  Production cần egress allowlist khi tích hợp payment/storage; không mở Internet
  toàn bộ worker media.
- API health timeout không hủy thread đang chạy; driver có timeout riêng. Production
  cần rate-limit health endpoints tại gateway để tránh làm cạn connection pool.
- Không thể ngăn tuyệt đối người có quyền xem chụp màn hình hoặc quay màn hình.
  Kiểm soát media giai đoạn 11 là authorization và hạn chế chia sẻ, chưa phải DRM.

## Tài liệu tham chiếu

- [FastAPI security](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)
- [Next.js installation](https://nextjs.org/docs/app/getting-started/installation)

Auth đã được kiểm thử ở giai đoạn 03. Giai đoạn 06 bổ sung Admin ownership, quota,
checksum, body limit và private volume; FFmpeg/FFprobe ép MP4, vô hiệu external data
references, seccomp chặn socket/socketpair, giới hạn tài nguyên và thời gian. Kiểm thử
kernel network denial đã chạy trong Docker Linux. Không công bố đường dẫn HLS;
thumbnail có endpoint Admin đúng người upload, no-store. Chi tiết và giới hạn
sandbox tại [MEDIA.md](MEDIA.md). Giai đoạn 07 thêm HLS/subtitle xác thực từng tài
nguyên và progress theo tài khoản. Giai đoạn 08 thêm decoder ảnh giới hạn tài nguyên,
re-encode JPEG riêng tư và mutation versioned. Giai đoạn 09 thêm Reader kiểm tra
session/publication/gói ở metadata/ảnh/bookmark, parent ID và CSRF. Free hoặc Admin
được đọc nội dung published; paid subscription/device/CDN và production theo gate
10–12. Không cấp quyền bằng plan_code chưa có subscription. Xem [READER.md](READER.md).
