# Vận hành local — giai đoạn 12

Người dùng xác nhận 11/10/2026: hoàn thiện code ở local, **không deploy**. Không cần
SSH key, không kết nối server hay thay đổi Cloudflare. Website local tiếp tục ở
http://localhost:3000; cấu hình production 8083 chỉ là artifact để dùng sau.

## Backup mã hóa trên máy này

Yêu cầu Python 3.11+ và Docker Linux engine. Chạy từ thư mục project:

```powershell
.venv/Scripts/python.exe scripts/local_ops.py init
.venv/Scripts/python.exe scripts/local_ops.py backup
.venv/Scripts/python.exe scripts/local_ops.py status
```

`init` chỉ dùng một lần, tạo `backups/local/repository` và password ngẫu nhiên,
không overwrite. Công cụ dùng image restic 0.18.0 pinned theo digest, container
không có network, không mount Docker socket, filesystem read-only ngoài repo.
Giữ bản sao password ở nơi an toàn tách khỏi repository. Nếu chuyển backup ra
ngoài máy, **chỉ copy repository**, không copy password cùng nó. Encryption không
bảo vệ nếu kẻ khác lấy được cả repo và password. Windows dùng ACL thừa kế của
tài khoản hiện tại; Linux tạo folder/file quyền 0700/0600.

Backup có downtime: dừng web/API/worker/beat, chụp PostgreSQL bằng pg_dump custom và
toàn bộ volume media, ghi manifest SHA256, lưu cùng một encrypted snapshot. Không
đưa `.env`, SSH key hoặc Redis auth/rate-limit state vào snapshot. PostgreSQL chứa
thông tin nghiệp vụ/tài khoản cần bảo vệ. Thư mục tạm plaintext chỉ tồn tại trong
quá trình chạy; nên bật BitLocker/LUKS cho ổ lưu trữ.

Khóa maintenance theo profile ngăn hai backup chạy chồng nhau. Nếu lỗi sau khi
dừng dịch vụ, finally khởi động lại và đợi health. Mật khẩu sai bị chặn trước khi
dừng dịch vụ. `state.json` chỉ ghi thời điểm/snapshot thành công sau khi restic kiểm
toàn bộ dữ liệu. Nếu tiến trình bị kill hoặc máy tắt, kiểm tra dịch vụ trước khi
xóa file lock; không tự xóa lock khi không rõ chủ sở hữu.

## Giám sát

`status` in JSON và trả exit 1 khi service thiếu/dừng/unhealthy/starting, disk còn
dưới 20% hoặc backup chưa có/quá 26 giờ; exit 0 khi đạt. Có thể dùng làm đầu vào
scheduler/monitor về sau, chưa tự tạo lịch hay gửi thông báo ra ngoài. Disk đo ổ
chứa source local; Docker Desktop có virtual disk riêng, cần theo dõi riêng khi
chọn storage thực. `beat` kiểm tra running; worker có Celery healthcheck.
Docker logs có rotation; API logs không chứa body, query hay cookie.

## Nghiệm thu cô lập và phục hồi

`scripts/check_production_runtime.py` chỉ dùng project `suni-production-check`, env
test-results/stage12.env và DB suni_test, không phục hồi vào dữ liệu dev. Nó kiểm
private ports, cookie production, billing disabled; tạo binary fixture PostgreSQL
và media; chạy chính code backup; decrypt snapshot, kiểm manifest, pg_restore vào
DB UUID mới và extract media vào container tạm không có live volume; so sánh bytes.
DB phục hồi được xóa sau test. `restore-test` cố ý chỉ nhận snapshot profile test.
Không cung cấp lệnh restore đè dữ liệu thật: việc đó cần chọn snapshot và kế hoạch
khôi phục cụ thể khi triển khai. Test còn kiểm mật khẩu sai không làm dừng ứng dụng.

```powershell
.venv/Scripts/python.exe -m unittest discover -s scripts -p 'test_*.py'
.venv/Scripts/python.exe scripts/run_stage12_checks.py
.venv/Scripts/python.exe scripts/load_check.py
```

Runner tự tạo secrets test riêng nếu chưa có, dựng rồi dọn project cố định
suni-production-check cùng volumes test. Cổng 8083 cần trống. Không sửa .env dev.
Test không dùng SQLite hay giả lập PostgreSQL/Redis/Celery.
Local load mặc định 200 GET/5 concurrent/p95<=2000ms; không đại diện tải streaming
hay VPS thực tế. Giai đoạn 10 vẫn chờ SePay Test mode thật, VIP/Premium vẫn nháp.
