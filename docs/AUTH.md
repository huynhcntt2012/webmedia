# Giai đoạn 03 — Tài khoản và phiên đăng nhập

Mở http://localhost:3000/register để tạo tài khoản, sau đó /login và /account.
Email được chuẩn hóa lowercase; mật khẩu 12–128 ký tự, lưu bằng Argon2id.
Tài khoản mới luôn có role User và gói Free. VIP/Premium vẫn nháp.
Không có tài khoản hoặc mật khẩu quản trị mặc định.

## API và trình duyệt

Trình duyệt gọi proxy cùng origin `/api/*`; FastAPI nhận các path dưới đây.
Proxy chỉ chuyển tiếp danh sách route/method cố định, giới hạn body 8 KiB.

| Method/path | Hành vi |
|---|---|
| GET /auth/csrf | Cấp token CSRF có chữ ký và cookie HttpOnly |
| POST /auth/register | Tạo User/Free; trả 202 giống nhau khi email đã tồn tại |
| POST /auth/login | Xác thực, tạo session; lỗi chung 401 |
| GET /auth/me | Chỉ trả hồ sơ của người đang đăng nhập |
| POST /auth/refresh | Đổi refresh token, cấp access cookie mới |
| POST /auth/logout | Thu hồi phiên hiện tại, xóa cookies |
| POST /auth/logout-all | Thu hồi mọi phiên của chính người đăng nhập |
| GET /admin/check | Chỉ Admin được phép, User nhận 403 |

Mọi POST cần Origin khớp PUBLIC_ORIGIN và header X-CSRF-Token khớp cookie,
có chữ ký hợp lệ, tuổi tối đa một giờ. Local dùng đúng `localhost:3000`;
truy cập bằng `127.0.0.1:3000` không cùng origin đã cấu hình.

Access JWT HS256 có hạn 5 phút, kiểm tra issuer/audience/type/signature/expiry.
Refresh là chuỗi ngẫu nhiên, database chỉ giữ SHA-256; phiên hết hạn tuyệt đối
sau 30 ngày. Refresh khóa hàng session, xoay token nguyên tử và giữ dấu token đã
dùng; phát hiện dùng lại thu hồi toàn bộ phiên, kể cả access vừa cấp.
Mỗi request xác thực đọc trạng thái user/session/role hiện tại từ database.

Cookies host-only, HttpOnly, SameSite=Lax; production thêm Secure và prefix
`__Host-`. Local HTTP không bật Secure. Token không lưu localStorage.
Web Locks tuần tự hóa refresh và CSRF mutations giữa tab; trình duyệt không hỗ
trợ Web Locks có thể cần đăng nhập lại nếu hai tab refresh cùng lúc (fail closed).

Redis giới hạn mặc định 60 auth mutations/IP/phút và 10 login/account/phút;
CSRF GET giới hạn 120/IP/phút. Key định danh được HMAC; Redis lỗi trả 503.
Không tin X-Forwarded-For do client gửi. Qua proxy Next.js, nhiều người dùng
chia sẻ IP proxy và chung quota IP: phù hợp local, cần trusted gateway trước production.
CSP script dùng nonce từng request, không có unsafe-inline; inline style còn được phép.

## Cấp quyền Admin bằng thao tác vận hành

Đăng ký tài khoản, lấy UUID từ trang /account. Người vận hành xác minh chủ tài
khoản rồi chạy (thay USER_UUID bằng UUID thật):

```powershell
docker compose run --rm --no-deps migrate python -m app.admin_cli USER_UUID
```

Lệnh dùng migrator, chỉ cập nhật tài khoản active đã tồn tại. Runtime không có
quyền sửa role/plan/is_active. Trang /admin đã có CRUD phim/tập/thể loại và nhật ký
từ giai đoạn 05; xem [ADMIN.md](ADMIN.md).

## Kiểm thử trình duyệt với database riêng

```powershell
docker compose -f compose.e2e.yaml up --build -d --wait
cd frontend
pnpm build
$env:E2E_AUTH = '1'
pnpm test:e2e
Remove-Item Env:E2E_AUTH
cd ..
docker compose -f compose.e2e.yaml down
```

Playwright chạy standalone build tại localhost:3100; API test ở loopback:18000.
Không mount volume dev; database test dùng tmpfs. Không bật E2E_AUTH thì hai
test luồng đăng nhập thật bị skip, không được dùng lượt đó để nghiệm thu auth.

Chưa có xác minh email, reset mật khẩu, MFA, trang quản lý session hoặc job dọn
session/token hết hạn. Phải bổ sung retention và đánh giá tải Argon2 trước production.
Email chưa xác minh không được xem là bằng chứng sở hữu để thanh toán/khôi phục.
