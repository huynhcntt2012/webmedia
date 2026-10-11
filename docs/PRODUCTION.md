# Giai đoạn 12 — triển khai và vận hành

Phạm vi hiện tại (người dùng xác nhận 11/10/2026): hoàn thiện code và kiểm thử
**local**, không deploy hoặc kết nối SSH. Hướng dẫn local ở [LOCAL-OPERATIONS.md](LOCAL-OPERATIONS.md).
Domain dự kiến cinema.sunifactory.com và cổng 8083 chỉ lưu để dùng sau.

## Cấu hình

`compose.production.yaml` là override bắt buộc đi cùng `compose.yaml`, Docker
Compose >= 2.24.4. Backend chạy APP_ENV=production, cookie Secure, origin HTTPS,
OpenAPI tắt, billing disabled. API không publish port; web chỉ bind loopback 8083.
PostgreSQL/Redis giữ network nội bộ. App non-root/read-only/cap-drop và worker
giới hạn CPU/memory/pids được kế thừa. Tất cả service có bounded Docker logs.

Trên server, trong thư mục release riêng không chứa secrets dev:

```sh
python3 scripts/init_production_env.py
docker compose --env-file .env.production -p suni-production -f compose.yaml -f compose.production.yaml config --quiet
docker compose --env-file .env.production -p suni-production -f compose.yaml -f compose.production.yaml up --build -d --wait --wait-timeout 180
```

Env mới tạo bằng exclusive write, mode 0600, secrets độc lập. Không chạy config
không có `--quiet` vì có thể in secrets. Không copy `.env` local/testdata vào server.
Trước lần nâng cấp: backup, ghi image IDs/digests hiện tại, build tag release riêng,
migrate một lần, đợi health, smoke qua HTTPS. Rollback application về image đã ghi
chỉ khi schema tương thích; không tự downgrade database production. Lưu bản release
cũ đến khi nghiệm thu xong. Chính sách pin image/digest cần chốt trên server thực.

## Cloudflare và cổng 8083

Nếu cloudflared chạy trực tiếp trên server: public hostname trỏ tới
`http://127.0.0.1:8083`. Tunnel cần outbound 7844 TCP/UDP, không cần NAT inbound.
Nếu dùng reverse proxy trên cùng server: HTTPS 443 chuyển tới loopback 8083;
Cloudflare SSL Full (strict), chứng chỉ origin hợp lệ, HTTP chuyển HTTPS. Nếu proxy
ở máy khác, cần thay bind có kiểm soát và firewall chỉ cho IP proxy, không tự mở
8083 toàn mạng. Người dùng chưa xác nhận phương án nào đang dùng.

Không trỏ DNS public tới IP LAN 192.168.1.98. Không dùng URL công khai :8083 làm
origin đăng nhập. Bypass cache `/api/*`, `/watch/*`, `/read/*`, `/account`, `/devices`,
`/plans`, `/login`, `/register`; tôn trọng no-store/cookie và không cache HTML nonce.
HLS đang phục vụ qua ứng dụng có xác thực, không đưa media volume vào static CDN.
Trước phát video thương mại qua Cloudflare cần kiểm tra điều khoản/dịch vụ media
phù hợp với tài khoản thực; chưa nghiệm thu lưu lượng video Internet.

## Backup và khôi phục

`scripts/local_ops.py` chạy backup mã hóa và giám sát trên Windows/Linux qua Docker.
Script Linux `scripts/backup-production.sh DIRECTORY` là wrapper cùng code, dùng
profile production; repository phải được init trước. Xem [quy trình, bảo vệ khóa và
kiểm thử khôi phục](LOCAL-OPERATIONS.md). Bản hiện tại dùng repository local; khi
triển khai thật cần storage off-host, lịch/retention và giám sát tuổi bản sao off-host.
Không tự gửi dữ liệu hoặc khóa sang dịch vụ ngoài.

Phục hồi tự động chỉ dành cho test: DB UUID mới và container media mới, không
restore đè production. Khi triển khai thật cần kế hoạch snapshot, bootstrap roles,
restore bằng migrator, áp grants, kiểm tra auth/HLS/reader và job outbox trước mở
traffic. Redis không được phục hồi để tránh mang trạng thái auth/throttle cũ trở lại.

## Giám sát và tải

API log JSON request_id/route-template/status/duration; không log body, querystring,
cookies/credentials. Xem Docker log bounded; readiness kiểm PostgreSQL/Redis,
worker health ping Celery. Production cần monitor ngoài host: HTTPS availability,
5xx, p95, disk<20%, RAM/OOM, worker down và backup age>26h; chưa có kênh cảnh báo.
Không public Docker socket hoặc metrics chứa credentials.

`python scripts/load_check.py --origin http://127.0.0.1:3000` thực hiện 200 GET,
5 concurrent, p95 <= 2000ms, không lỗi. Đây là baseline local catalogue, không phải
chứng nhận công suất streaming/VPS. Phải đo lại server thực và HLS có quyền trước
khi chọn số người đồng thời. IP rate limit backend hiện dùng IP Next proxy chung;
cần gateway trust chain có xác thực trước khi dùng forwarded client IP.

Migration stage 12: **NO-OP**, không thay schema; head `0010_content_access`.
Gate production vẫn pending HTTPS/Cloudflare/off-host monitoring và load VPS; không thuộc phạm vi local hiện tại.

Tài liệu đối chiếu:
- [Docker Compose merge/override](https://docs.docker.com/reference/compose-file/merge/)
- [Cloudflare Tunnel firewall](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-with-firewall/)
- [PostgreSQL pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html)
- [Restic backup](https://restic.readthedocs.io/en/stable/040_backup.html)
