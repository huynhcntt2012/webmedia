# Suni AI Cinema — kế hoạch thực hiện tuần tự

## Quy tắc nghiệm thu

Không mở giai đoạn kế tiếp trước khi migration (upgrade/rollback), unit tests,
integration tests và kiểm tra bảo mật của giai đoạn hiện tại đạt. Mỗi giai đoạn
có hồ sơ trong `docs/acceptance/`, ghi lệnh, kết quả, giới hạn và bằng chứng.
Kiểm thử bị skip hoặc chỉ có mã test không được tính là đạt. Migration không
đổi schema phải ghi rõ lý do; không tạo bảng giả chỉ để đánh dấu tiến độ.
Migration rollback phá hủy dữ liệu chỉ chạy trên database kiểm thử riêng.

| GĐ | Phạm vi | Migration dự kiến | Kiểm thử và tiêu chí nghiệm thu |
|---|---|---|---|
| 01 | Next.js, FastAPI, PostgreSQL, Redis, Docker, Celery/FFmpeg nền | `0001_bootstrap`: baseline, chưa có bảng nghiệp vụ | Build web; kiểm tra cấu hình/host/CORS/log; PostgreSQL/Redis thật; upgrade → downgrade → upgrade; worker thực thi FFmpeg; stack healthy |
| 02 | SQLAlchemy, schema và seed Free/VIP/Premium | Users, plans, movies/episodes, comics/chapters/pages; khóa ngoại, unique, indexes; seed idempotent | Constraints, transaction rollback, seed chạy hai lần; không tạo admin/mật khẩu mặc định |
| 03 | Register/login/refresh, Admin/User | Auth sessions, refresh token family, revoked_at, user role | Argon2id; access token ngắn hạn; refresh hash + rotation/reuse detection; HttpOnly/Secure cookie, CSRF; rate limit; enumeration resistance; RBAC/IDOR và race refresh |
| 04 | Home, danh sách/tìm kiếm/chi tiết phim | Search indexes và publication fields nếu cần | Pagination có giới hạn; lọc published; tìm kiếm Unicode; empty/error/loading; responsive/a11y E2E; không lộ phim nháp |
| 05 | Admin CRUD phim/tập/poster/trailer/phân loại | Genres, movie genres, asset references, audit events | Admin-only mọi mutation; ownership/ID validation; output escaping; URL allowlist/SSRF; constraints; E2E CRUD; ghi nhật ký thay đổi |
| 06 | Resumable upload, FFmpeg queue, HLS/thumbnail | Upload sessions/chunks, media jobs/variants | Offset/hash/idempotency; size/quota/MIME/magic validation; worker resource/time limits; shell=False; FFmpeg không truy cập mạng; path traversal; retry và file cleanup; transcoding thật |
| 07 | Player/subtitle/chất lượng/progress/resume | Watch progress, subtitle tracks | Upsert theo user/episode; resume bounded; subtitle sanitization; HLS adaptive playback; network retry; không cho client tự cấp quyền media |
| 08 | CRUD truyện/chương, nhiều ảnh và thứ tự | Comic assets/page ordering | Admin-only; verify/re-encode ảnh; reject decompression bombs/SVG; reorder nguyên tử; uniqueness; batch partial failure; E2E |
| 09 | Reader cuộn dọc/lật trang/bookmark | Reading progress và reader preferences | IDOR; bounds trang; resume; mobile; keyboard; lazy-load; chương bị thu hồi quyền |
| 10 | Plans/subscriptions/SePay sandbox/webhook | Orders, payment events, subscriptions; unique provider transaction | Giá phía server; webhook xác thực theo tài liệu SePay đã kiểm chứng; exact order/account/amount/currency; replay/idempotency; concurrent duplicate; sandbox E2E; không tin redirect client |
| 11 | Quyền HLS, thiết bị, private media | Devices, playback sessions, revocation/security events | Free/VIP/Premium entitlement cả manifest/segment/key/subtitle/ảnh; TTL ngắn; quota thiết bị nguyên tử; revoke; traversal/IDOR/replay; CDN không cache sai quyền; không công khai storage |
| 12 | Cloudflare, backup/logs/load/deploy | Ops metadata nếu cần, hoặc revision no-op có lý do | HTTPS và origin restriction; proxy trust; restore drill thực; RPO/RTO; metrics/alerts; load p95/error/queue; secret rotation; non-root, image/dependency scan, rollback deploy |

## Quyết định kỹ thuật ban đầu

- Monorepo: `frontend/`, `backend/`, tài liệu nghiệm thu và Compose tại root.
- App Router + TypeScript strict; API Python 3.12, SQLAlchemy 2/Alembic;
  PostgreSQL 17, Redis 7.4, Celery và FFmpeg trong worker riêng.
- Chưa triển khai tính năng “AI”: tên sản phẩm không đồng nghĩa có nhà cung cấp
  AI, model, chi phí hoặc quyền gửi nội dung sang bên thứ ba đã được xác định.
- Chưa có nội dung phim/truyện mẫu hoặc ảnh bên ngoài. Chỉ nhập nội dung có quyền sử dụng.
- Compose hiện tại dành cho local dev; không được xem là cấu hình production.
- Trước giai đoạn 10 cần xác định tài khoản sandbox, receiver/account và cấu hình
  webhook SePay. Trước giai đoạn 12 cần domain, máy chủ, storage và Cloudflare.
- Mặc định tài khoản được cấp Free. Người dùng đã chọn seed VIP/Premium nháp:
  chưa giá/quyền lợi, inactive và không bán. Cần chốt trước khi mở thanh toán;
  không dùng giá tự đặt cho giao dịch.

## Trạng thái

- 01: đạt nghiệm thu kỹ thuật ngày 09/10/2026, gồm 4 integration tests thật.
- 02: đạt nghiệm thu kỹ thuật ngày 09/10/2026; 21 unit + 2 script + 43 integration
  tests đạt, migration/seed đã áp dụng và stack local healthy. VIP/Premium nháp.
- 03: đạt nghiệm thu kỹ thuật ngày 09/10/2026; 25 unit backend, 2 script,
  64 integration, 6 unit frontend và 8 browser tests đạt; stack local healthy.
- 04: đạt nghiệm thu kỹ thuật ngày 10/10/2026; migration NO-OP (head 0003_auth),
  28 unit backend, 2 script, 83 integration, 14 unit frontend, 10 browser tests đạt.
- 05: đạt nghiệm thu kỹ thuật ngày 10/10/2026; revision 0004_admin_catalogue;
  55 unit backend, 2 script, 107 integration, 14 unit frontend, 12 browser tests đạt.
  Admin CRUD, poster CDN media.sunifactory.com, trailer YouTube và nhật ký đã có.
- 06: đạt nghiệm thu kỹ thuật ngày 10/10/2026; revision 0005_media_uploads;
  61 unit backend, 2 script, 114 integration, 14 unit frontend, 12 browser tests đạt.
  Upload tiếp tục/checksum/quota, Celery outbox, FFmpeg HLS/thumbnail riêng tư đã có.
- 07: đạt nghiệm thu kỹ thuật ngày 10/10/2026; revision 0006_playback; 70 unit backend,
  2 script, 119 integration, 14 unit frontend, 12 browser tests đạt. HLS Player,
  WebVTT, quyền từng tài nguyên, versioned progress và tiếp tục xem đã có.
- 08: đạt nghiệm thu kỹ thuật ngày 10/10/2026; revision 0007_comic_admin; 75 unit backend,
  2 script, 125 integration, 14 unit frontend, 14 browser tests đạt. CRUD truyện/chương,
  upload ảnh chuẩn hóa riêng tư, retry idempotent và reorder nguyên tử đã có.
- 09: đạt nghiệm thu kỹ thuật ngày 10/10/2026; revision 0008_reader; 83 unit backend,
  2 script, 130 integration, 16 unit frontend, 16 browser tests đạt. Reader cuộn dọc,
  lật trang/keyboard, bookmark/mode theo tài khoản và kiểm tra quyền từng ảnh đã có.
- 10: hoàn tất tích hợp local ngày 10/10/2026, revision 0009_payments; 95 unit backend,
  2 script, 146 integration, 16 unit frontend, 18 E2E local đạt. **Chưa nghiệm thu toàn bộ**:
  còn SePay Test mode E2E thật (người dùng chưa có tài khoản/secret/endpoint). VIP/Premium
  giữ nháp, dev payment disabled; giá mẫu chỉ database test. Xem acceptance/10-payments.md.
- 11: đạt nghiệm thu kỹ thuật 11/10/2026; migration 0010_content_access; 104 backend unit, 2 script, 150 integration, 16 frontend unit, 18 browser tests đạt. Ngoại lệ thứ tự do người dùng yêu cầu; gate 10 vẫn pending.
- 12: hoàn tất code/nghiệm thu local 11/10/2026 theo phạm vi mới (không deploy).
  Migration NO-OP; 7 script unit, production Compose runtime cô lập, encrypted
  backup/restore PostgreSQL và media, monitor, load 200 requests không lỗi đạt.
  Cloudflare/HTTPS/off-host monitoring và nghiệm thu server thực để sau.
