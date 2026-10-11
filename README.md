# Suni AI Cinema

Next.js + FastAPI + PostgreSQL + Redis + Celery + FFmpeg + Docker.

Dự án triển khai **tuần tự 12 giai đoạn**. Giai đoạn 01–09 đã nghiệm thu kỹ thuật.
Đã có HLS Player/phụ đề/tiếp tục xem, Admin quản lý truyện/chương/upload ảnh và Comic Reader.
83 unit backend + 2 script + 130 integration + 16 unit frontend + 16 browser tests đạt.
Giai đoạn 10 đã hoàn tất tích hợp local: tổng 277 tests đạt (95 backend unit, 2 script,
146 integration, 16 frontend unit, 18 E2E). **Chưa nghiệm thu sandbox SePay thật**;
payment dev vẫn tắt, VIP/Premium vẫn nháp. Xem [thanh toán](docs/PAYMENTS.md).
Xem [Player](docs/PLAYER.md), [Truyện tranh](docs/COMICS.md) và [nghiệm thu 08](docs/acceptance/08-comics.md).
Không có tài khoản mặc định hoặc phim giả trong database dev; phim hư cấu chỉ ở test.

## Chạy local bằng Docker

Yêu cầu: Docker Engine/Desktop có Compose v2 và Linux containers; Python 3.12+
để tạo cấu hình. Node 24/pnpm chỉ cần nếu phát triển frontend ngoài Docker.

```powershell
python scripts/init_env.py
docker compose up --build -d --wait
docker compose ps
```

Nếu đã có `.env` từ giai đoạn 01, chạy `python scripts/upgrade_env_stage02.py`
thay cho `init_env.py` để thêm hai secret database mới mà giữ nguyên cấu hình cũ.

- Web: [localhost:3000](http://localhost:3000)
- Thư viện: [localhost:3000/movies](http://localhost:3000/movies)
- Quản trị: [localhost:3000/admin](http://localhost:3000/admin) (cần quyền Admin)
- [Đăng ký](http://localhost:3000/register) / [Đăng nhập](http://localhost:3000/login)
- API docs (development): [localhost:8000/docs](http://localhost:8000/docs)
- API readiness: [localhost:8000/health/ready](http://localhost:8000/health/ready)

`db-bootstrap` và `migrate` là one-shot services, trạng thái exited 0 là bình thường. API và worker
chỉ khởi động sau migration thành công. PostgreSQL và Redis không mở port host.
Lần đầu build cần mạng để tải packages/images. DB/cache/worker nằm trong mạng internal;
API/web có thêm mạng edge để publish port loopback.
`.env` chứa secret local và không được commit. Mật khẩu do script tạo là hex nên
an toàn trong URL; nếu tự sửa phải URL-encode ký tự đặc biệt.

```powershell
docker compose logs --tail 100 api worker
docker compose stop
```

Không dùng `down -v` với stack phát triển: lệnh đó xóa dữ liệu.

## Kiểm thử dự án

Python:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements-test.lock
# Chạy từ backend để import package app
cd backend
../.venv/Scripts/python -m ruff check .
../.venv/Scripts/python -m pytest -m "not integration"
cd ..
.venv/Scripts/python -m unittest discover -s scripts -p "test_*.py"
```

Trên Linux/macOS dùng `.venv/bin/python` thay cho `.venv/Scripts/python`.
Frontend:

```powershell
cd frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm exec playwright install chromium
pnpm test:e2e
cd ..
```

Integration dùng PostgreSQL/Redis **thật**, queue **thật**, FFmpeg **thật**;
DB kiểm thử độc lập, không tác động volume phát triển:

```powershell
docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests
docker compose -f compose.test.yaml down
```

Test bao gồm migration upgrade → downgrade → upgrade, drift check, API readiness,
Redis round-trip, Celery task gọi FFmpeg, constraints/FK/cascade, seed đồng thời,
transaction rollback và quyền runtime/migrator. Không có Docker thì phải ghi **chưa chạy**,
không thay thế bằng SQLite rồi đánh dấu integration đạt.

Stack smoke sau integration:

```powershell
docker compose up --build -d --wait
python scripts/smoke.py
```

Kiểm tra dependency:

```powershell
.venv/Scripts/python -m pip_audit -r backend/requirements.lock
cd frontend
pnpm audit --prod
```

## Phát triển không có Docker

Unit tests và build web chạy được mà không có database. API runtime cần
`APP_SECRET`, `DATABASE_URL` (PostgreSQL + psycopg), `REDIS_URL` có password.
Không commit cấu hình và không đặt secret vào biến `NEXT_PUBLIC_*`.

```powershell
cd frontend
# Không cấu hình API_INTERNAL_URL: trang hiện trung thực trạng thái chưa kết nối
pnpm dev
```

Muốn nối API khi chạy ngoài Docker, đặt `API_INTERNAL_URL=http://localhost:8000`
ở môi trường server Next.js. API dev chạy từ `backend/`:
`python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log`.
URL database/Redis trong Compose chỉ phân giải được trong mạng Docker.

## Cấu trúc và tài liệu

- `frontend/`: App Router, TypeScript strict, unit tests và Playwright desktop/mobile.
- `backend/`: API, models, migration baseline/domain, seed, worker, unit/integration tests.
- `compose.yaml`: stack dev. `compose.test.yaml`: stack integration độc lập.
- [Lộ trình 12 giai đoạn](docs/ROADMAP.md)
- [Bảo mật và giới hạn](docs/SECURITY.md)
- [Nghiệm thu giai đoạn 01](docs/acceptance/01-bootstrap.md)
- [Thiết kế database và hướng dẫn nâng cấp](docs/DATABASE.md)
- [Nghiệm thu giai đoạn 02](docs/acceptance/02-database.md)
- [Auth, cấp quyền Admin và browser tests với backend thật](docs/AUTH.md)
- [Nghiệm thu giai đoạn 03](docs/acceptance/03-auth.md)
- [Catalogue, API và quyết định migration no-op](docs/CATALOGUE.md)
- [Nghiệm thu giai đoạn 04](docs/acceptance/04-catalogue.md)
- [Admin, CDN poster và hướng dẫn quản lý phim](docs/ADMIN.md)
- [Nghiệm thu giai đoạn 05](docs/acceptance/05-admin-catalogue.md)
- [Upload video, giới hạn và vận hành hàng đợi](docs/MEDIA.md)
- [Nghiệm thu giai đoạn 06](docs/acceptance/06-media-upload.md)
- [Player, phụ đề và tiếp tục xem](docs/PLAYER.md)
- [Nghiệm thu giai đoạn 07](docs/acceptance/07-player.md)
- [Quản lý truyện/chương và ảnh](docs/COMICS.md)
- [Nghiệm thu giai đoạn 08](docs/acceptance/08-comics.md)
- [Comic Reader và lưu vị trí](docs/READER.md)
- [Nghiệm thu giai đoạn 09](docs/acceptance/09-reader.md)
- [Tích hợp thanh toán local và cấu hình SePay Test mode](docs/PAYMENTS.md)
- [Kết quả local giai đoạn 10 và điều kiện nghiệm thu còn thiếu](docs/acceptance/10-payments.md)
- [Quyền nội dung và giới hạn thiết bị](docs/CONTENT-SECURITY.md)
- [Nghiệm thu giai đoạn 11](docs/acceptance/11-content-security.md)
- [Backup mã hóa, giám sát và kiểm thử local](docs/LOCAL-OPERATIONS.md)
- [Cấu hình production để dùng sau](docs/PRODUCTION.md)
- [Nghiệm thu local giai đoạn 12](docs/acceptance/12-production.md)

Free được seed mặc định; VIP/Premium ở trạng thái nháp, chưa định giá và chưa bán.
Catalogue chỉ hiển thị phim published. Tạo phim ở Admin; poster dùng URL HTTPS từ
`media.sunifactory.com`, trailer dùng YouTube. Chọn **Video** trong từng tập để upload MP4.
HLS/thumbnail lưu private volume; Player kiểm tra quyền từng tài nguyên.
Quản lý truyện ở `/admin/comics`; xuất bản truyện để hiển thị tại `/comics`.
Người đọc cần đăng nhập để mở ảnh chương và lưu vị trí.
Không tự tạo Admin trong dev; xem lệnh cấp quyền cho UUID tài khoản ở `docs/ADMIN.md`.

Lock Python được tạo từ dependency closure đã cài cho Windows/Linux bằng
`python scripts/lock_python.py` trong venv chứa `backend[test]`. Khi cập nhật
dependency phải chạy lại test/audit và Docker integration trước khi chấp nhận lock mới.
