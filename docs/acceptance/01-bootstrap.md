# Giai đoạn 01 — Khởi tạo source

Ngày kiểm tra: **08/10/2026**, theo múi giờ người dùng Asia/Saigon.

**Trạng thái: ĐẠT nghiệm thu kỹ thuật giai đoạn 01 — 09/10/2026.**

## Đóng gate trước giai đoạn 02

Đã chạy `docker compose -f compose.test.yaml up --build --abort-on-container-exit
--exit-code-from tests`: **4 passed, 18 deselected**, test container exited 0.
Bao gồm upgrade/downgrade/reapply và drift trên PostgreSQL thật, API dependencies,
Redis round-trip và Celery gọi FFmpeg. Stack test đã được dọn bằng `down`, không
đụng volume phát triển. Chạy lại smoke có **4 PASS**, 5 dịch vụ dev healthy.
Kết hợp 29 tests local đã đạt ở giai đoạn 01, các gate yêu cầu đã đủ bằng chứng.
Những ghi chú “chưa chạy” bên dưới là lịch sử trước thời điểm đóng gate này.

## Cập nhật khởi chạy — 09/10/2026

- Docker Desktop Linux Engine 29.8.2 và Compose 5.5.1 đã hoạt động.
- Build container thành công. Đã sửa chuỗi `tmpfs` có dấu phẩy cần được quote;
  thêm mạng `edge` cho API/web để publish port loopback trên Docker Desktop.
  PostgreSQL/Redis/worker vẫn chỉ nối mạng `internal`.
- `docker compose up -d --wait`: web, API, PostgreSQL, Redis và worker healthy;
  migration exited 0. Không xóa volume hoặc reset database.
- `python scripts/smoke.py`: 4 PASS, gồm web kết nối API/PostgreSQL/Redis.
- Enqueue `suni.probe` qua Redis và nhận kết quả worker thành công;
  FFmpeg thực tế là 5.1.9-0+deb12u1.
- Web: http://localhost:3000; API docs: http://localhost:8000/docs.
- Chưa chạy bộ 4 integration tests trên Compose test riêng, đặc biệt rollback/
  reapply migration. Vì vậy chưa đóng gate giai đoạn 01. Các kết quả ngày 08/10
  bên dưới được giữ làm lịch sử, blocker thiếu Docker đã được giải quyết.

## Sản phẩm bàn giao

- Next.js App Router/TypeScript, trang khởi tạo responsive, trạng thái API thật;
  health endpoint; lint/typecheck; unit tests; Playwright desktop/mobile.
- FastAPI factory, settings validation, health live/ready, PostgreSQL/Redis probes,
  CORS/Host checks, security headers và JSON request logs không chứa query/credentials.
- Celery JSON-only và task nội bộ kiểm tra FFmpeg, chưa có upload/transcode nghiệp vụ.
- Dockerfiles non-root; Compose dev và Compose test độc lập; migrate one-shot;
  lockfiles; CI có backend/frontend/integration/stack smoke.
- Script sinh `.env` với secret ngẫu nhiên riêng, không ghi đè; Git đã khởi tạo;
  `.env` đã kiểm tra bị ignore. Chưa commit/push hoặc triển khai lên server.

## Migration

`0001_bootstrap`, parent `None`. Không tạo bảng nghiệp vụ; Alembic quản lý
`alembic_version`. No-op là có chủ đích: schema và seed nằm ở giai đoạn 02.
Unit test xác nhận head duy nhất. Upgrade/downgrade/reapply/drift trên PostgreSQL
đã có test nhưng chưa được chạy tại môi trường này.

## Bằng chứng chạy local

Môi trường: Windows, Python 3.12.14, Node 24.19.0, pnpm 11.25.0.
Dependency đã resolve: Next.js 16.4.0, React 19.3.0, FastAPI 0.143.0,
SQLAlchemy 2.0.54; xem lockfiles cho toàn bộ phiên bản.

| Kiểm tra | Kết quả |
|---|---|
| Backend `pytest` | 18 passed; 4 integration skipped vì không có Docker |
| Script sinh env `unittest` | 1 passed: secret riêng và không ghi đè |
| Ruff backend/scripts | Passed |
| Frontend lint + TypeScript | Passed |
| Frontend Vitest | 6 passed |
| Next.js production build | Passed |
| Playwright trên standalone build | 4 passed: desktop/mobile, anchor navigation, không tràn ngang, không pageerror, health endpoint |
| Quan sát screenshot desktop/mobile | Đã xem; chữ/nút không bị cắt; bố cục mobile một cột |
| `pip-audit -r backend/requirements.lock` | No known vulnerabilities found |
| `pnpm audit --prod` | No known vulnerabilities found |
| `pnpm peers check` | No peer dependency issues found |
| Parse YAML hai Compose files | Passed; chỉ xác nhận cú pháp YAML, không thay cho Docker validation |
| Docker build/Compose smoke/PostgreSQL/Redis/Celery/FFmpeg | **CHƯA CHẠY** |

29 tests local passed, không bao gồm 4 integration skipped.
Quét dependency không thay cho code security review hoặc image scan.

## Giới hạn và warning

- Không tìm thấy Docker CLI hoặc Docker Desktop ở đường dẫn cài đặt thông thường.
  Không có bằng chứng Docker daemon/Linux containers sẵn sàng.
- Có một lần máy báo thiếu bộ nhớ trong lượt chạy bổ sung; đã chạy lại lint và
  standalone E2E thành công. Không coi lần lỗi môi trường đó là pass.
- Starlette cảnh báo TestClient dùng httpx đã deprecated. Test vẫn đạt với lock hiện tại;
  cần nâng test adapter trong lần cập nhật dependency tiếp theo.
- ESLint 9 bị đánh dấu deprecated; giữ bản 9.39.5 do peer ranges của các plugin
  trong eslint-config-next hiện chưa nhận ESLint 10. Đây là dev dependency.
- Chưa chạy CI từ remote vì chưa có repository remote. Workflow là source bàn giao.
- Các giới hạn bảo mật dev/CSP/role DB/secrets được ghi tại `docs/SECURITY.md`.

## Gate còn thiếu và lệnh nghiệm thu

Trên máy có Docker Desktop/Engine với Linux containers:

```powershell
docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests
docker compose -f compose.test.yaml down
docker compose up --build -d --wait
python scripts/smoke.py
docker compose ps
```

Yêu cầu: 4 integration tests đạt; migration exited 0; postgres/redis/api/worker/web
healthy; smoke trả đủ PASS và web xác nhận kết nối API. Nếu có lỗi phải sửa và
chạy lại trước khi ký nghiệm thu. Cập nhật hồ sơ bằng kết quả thực tế, sau đó
mới bắt đầu giai đoạn 02.
