# Giai đoạn 12 — Hoàn tất code và nghiệm thu local

Ngày 11/10/2026. Gate 11 đã accepted. Người dùng xác nhận không cần deploy, yêu
cầu hoàn thiện code local trước. Không tiếp tục SSH, không thay đổi Cloudflare hay
server thật. Nghiệm thu production trên Internet được tách khỏi phạm vi hiện tại.
Giai đoạn 10 vẫn chờ SePay Test mode thật, VIP/Premium giữ nháp.

Migration **NO-OP**: công cụ vận hành không thay schema; head 0010_content_access.

## Code đã hoàn thiện

- Compose production override: port web loopback 8083, API/DB/Redis private,
  cookie Secure, billing disabled, giới hạn tài nguyên và rotation log.
- Env generator tạo secrets độc lập, không overwrite và không in secrets.
- local_ops.py: repository restic mã hóa, lock backup, dừng writer để chụp DB/media
  cùng trạng thái, SHA256 manifest, kiểm tra toàn bộ dữ liệu backup, khởi động lại
  dịch vụ trong finally và đợi health. Docker restic pinned digest, không network.
- Restore-test chỉ vào DB mới và container media tạm trong project test, không ghi
  đè dev. Password sai bị chặn trước downtime; manifest/path/tampering kiểm tra.
- Status JSON/exit code: dịch vụ, disk free và tuổi backup; load check có giới hạn.
- Runner một lệnh dựng/dọn môi trường test; CI job operations; template Cloudflare
  và hướng dẫn để dùng sau. Không tự tạo scheduler hoặc gửi thông báo ra ngoài.

## Kiểm tra thực chạy

| Kiểm tra | Kết quả |
|---|---|
| Script unit | 7 passed: secrets/no-overwrite, target local, monitor, manifest/path/tamper |
| Ruff backend/scripts | Passed |
| Shell wrapper Linux | bash -n passed |
| Docker production override runtime riêng | PostgreSQL/Redis/API/web/worker healthy |
| Private ports, Secure/HttpOnly cookie, billing disabled | Passed |
| Encrypted backup bằng restic và full repository data check | Passed |
| Decrypt + manifest + pg_restore DB UUID mới | Passed: schema và binary fixture |
| Media tar extract container riêng, so sánh bytes | Passed |
| Mật khẩu sai, ứng dụng vẫn healthy | Passed |
| Monitor trên stack test sau backup | status ok, findings [] |
| Load catalogue local | 200 requests / concurrency 5 / errors 0 / p95 47ms |
| Dev smoke sau thay đổi | 4 checks passed |

Log ignored: stage12-encrypted-restore.log, stage12-local-acceptance.log,
stage12-script-unit-final.log, stage12-load-final.json trong test-results/.
Các integration dùng Docker/PostgreSQL/Redis/Celery thật. Không dùng SQLite/mocks
làm bằng chứng runtime. Runner chỉ down -v project test cố định; dữ liệu dev giữ
nguyên. Frontend/API nghiệp vụ không đổi trong lượt này nên không chạy lại browser
suite đã đạt giai đoạn 11. CI Linux đã cấu hình, chưa tuyên bố job GitHub đã chạy.

## Phạm vi để sau theo yêu cầu

Chưa nghiệm thu deploy/HTTPS/Cloudflare thực, storage backup off-host, cảnh báo
ngoài server và tải streaming/VPS. Backup local không thay thế bản sao off-host;
phải giữ password riêng khi chuyển repository ra ngoài. Local backup staging có
plaintext tạm thời; cần bảo vệ ổ đĩa và ACL. Thiết bị xem là phiên trình duyệt,
không phải DRM. Hướng dẫn ở [LOCAL-OPERATIONS.md](../LOCAL-OPERATIONS.md).
