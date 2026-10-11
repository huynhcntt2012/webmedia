# Giai đoạn 10 — Tích hợp thanh toán local

Người dùng xác nhận ngày 10/10/2026: giữ VIP/Premium nháp, giá mẫu chỉ trong database
kiểm thử; chưa có tài khoản SePay Test mode hoặc endpoint nhận webhook. Vì vậy local
để `PAYMENT_MODE=disabled`, không mở bán, không seed giá thương mại và không tự tạo
secret hay tunnel. Trang `/plans` hiển thị trạng thái này cùng lịch sử của tài khoản.
Phần còn thiếu để nghiệm thu đầy đủ: giao dịch do **SePay Test mode thật** gửi về.

## Phạm vi và giới hạn môi trường

Chỉ tích hợp **SePay bank webhook Test mode**, không phải Payment Gateway/IPN.
Không có chế độ Live. Cấu hình sandbox bị từ chối khi APP_ENV=production.
Orders/events/subscriptions có CHECK environment=sandbox. Subscription thử nghiệm
không cập nhật users.plan_code, không mở quyền trả phí cho HLS/Reader; policy subscription,
thiết bị và media production phải qua giai đoạn 11/12. Không tự động trừ tiền,
gia hạn thanh toán, hoàn tiền, chuyển đổi/prorate VIP↔Premium hoặc dùng redirect cấp quyền.

## Đơn hàng và subscription

- GET `/payments/plans`: Free/VIP/Premium từ database, có cờ khả dụng. Null giá là
  chưa chốt; giá/duration/device_limit hợp lệ mới tạo được đơn khi sandbox được bật.
- POST `/payments/orders`: session hoạt động + CSRF/Origin/rate limit, chỉ nhận
  plan_code và UUID idempotency_key. Giá/ngày/thiết bị, ngân hàng/account/VA lấy từ
  server và chụp vào đơn. Client không gửi giá, user_id hoặc trạng thái thanh toán.
- Một key/tài khoản trả lại đúng đơn cũ; dùng key cho gói khác trả 409. Frontend giữ
  key khi mất response, thử lại không tạo đơn mới. Reload trang mất key trong bộ nhớ;
  xem lịch sử trước khi tạo thêm. Giới hạn 5 đơn đang chờ, cửa sổ giao dịch 30 phút.
- GET `/payments/orders[/{id}]`: chỉ chủ đơn; danh sách 20 mục/trang. GET
  `/payments/subscriptions`: các kỳ còn hiệu lực hoặc chờ bắt đầu, tối đa 100 kỳ.
- Mã SUNI + 24 ký tự hex ngẫu nhiên, unique. Thanh toán đúng cấp một kỳ subscription
  duy nhất theo order_id. Cùng gói nối tiếp thời điểm kết thúc kỳ đã mua; khác gói
  độc lập. Advisory lock theo user bảo vệ gia hạn khi hai đơn thanh toán đồng thời.
- Thời điểm giao dịch phải nằm trong cửa sổ của đơn (giờ Việt Nam của provider),
  không ở tương lai quá 5 giây. Delivery đến trễ vẫn xử lý nếu giao dịch nằm đúng
  cửa sổ. UI hết hạn là hạn **tạo giao dịch**, không phải chặn retry đã ký hợp lệ.

## Webhook

POST `/payments/sepay/webhook`, hoặc Next proxy `/api/payments/sepay/webhook`.
Nhận JSON raw bytes, tối đa 16 KiB; không cần cookie/CSRF người dùng. Xác thực bằng
HMAC-SHA256 của `timestamp.raw_body`, header X-SePay-Signature dạng sha256=hex,
X-SePay-Timestamp trong ±300 giây; constant-time comparison. Không serialize lại
JSON trước xác thực. Secret riêng, tối thiểu 32 ký tự, không dùng APP_SECRET.
Nguồn: [SePay xác thực webhook](https://developer.sepay.vn/vi/sepay-webhooks/xac-thuc).

Payload integer strict; loại bỏ JSON duplicate keys, sai kiểu, ngày không tồn tại,
ngoại tệ hoặc field lạ. Contract bank webhook ghi số tiền là VND (không có currency
bắt buộc); nếu có currency phải chính xác VND. Kiểm tra incoming, bank/account/VA
đúng snapshot, số tiền bằng chính xác, code bằng mã đơn và chỉ một mã SUNI đúng trong
content. Không cộng dồn trả thiếu, không tự chấp nhận trả thừa.
Nguồn: [SePay payload/response](https://developer.sepay.vn/vi/sepay-webhooks/tich-hop-webhook).

Unique(environment, provider_transaction_id) chống retry đồng thời. Cùng ID + digest
payload đã chuẩn hóa trả success; ID cũ với nội dung đổi trả 409. Hai ID trả cùng
đơn: ID thứ hai lưu rejected/extra_payment, không tăng subscription. Event + đơn +
subscription + audit cùng PostgreSQL transaction; chỉ ACK sau commit. Không dùng
Celery cho transaction billing ngắn này; statement timeout 3 giây giới hạn chờ DB.
Lỗi DB rollback cả event để provider retry; lỗi nghiệp vụ đã lưu rejected thì ACK
200 `{"success":true}` để tránh retry vô ích, cần Admin xem và đối soát thủ công.

GET `/admin/payment-events?page=1` chỉ Admin: transaction ID, order ID, kết quả/lý do,
thời gian. Không lưu raw webhook, chữ ký, secret, nội dung chuyển khoản hoặc số dư.
Orders giữ receiver snapshot; không trả thông tin đơn cho người khác. Runtime không
có DELETE payment_orders/payment_events, không UPDATE/DELETE subscriptions, không
quyền sửa plans. Chưa có công cụ replay/override/refund bằng Admin.

## Chuẩn bị SePay sandbox thật sau này

1. Bật Test mode trên SePay, tạo tài khoản nhận tiền **thử**, cấu hình prefix SUNI
   nhận đủ suffix 24 ký tự hex. Không dùng tài khoản Live hay secret Live.
2. Tạo webhook JSON, incoming, đúng tài khoản/VA, HMAC-SHA256, bật retry. Cấu hình
   endpoint HTTPS công khai chỉ chuyển tiếp route webhook cần thiết. Chưa tự mở
   port/tunnel từ project này; Compose vẫn local-only.
3. Đặt PAYMENT_MODE=sandbox, SEPAY_BANK, SEPAY_ACCOUNT, SEPAY_SUB_ACCOUNT (rỗng khi
   không VA), SEPAY_WEBHOOK_SECRET trong `.env` local. Không gửi secret qua chat hoặc
   commit. Rebuild/recreate API để nhận config. Không in `docker compose config` đầy đủ.
4. Dùng bản sao test riêng với giá mẫu, tạo đơn bằng UI. Mô phỏng giao dịch ở SePay,
   xác minh webhook provider đến, đơn paid và chỉ một kỳ subscription. Replay ở
   dashboard, thử sai amount/account/code, hết hạn và chữ ký; lưu evidence đã che secrets.
5. Chỉ đánh dấu gate 10 accepted sau provider sandbox E2E thực tế. Giá dev vẫn nháp
   đến khi người dùng chốt; không copy giá fixture sang dev/production.

SePay Test mode và Live dùng cùng định dạng payload, nên không thể suy ra môi trường
từ body. Ranh giới ở secret/cấu hình/account và database sandbox riêng; ứng dụng
không có chế độ Live để vô tình cấp quyền thật. Tham chiếu:
[Test mode vs Live](https://developer.sepay.vn/vi/sepay-webhooks/test-mode/so-sanh-voi-live),
[tạo webhook Test mode](https://developer.sepay.vn/vi/tien-ich-khac/test-mode/tao-webhook).

## Migration và kiểm thử local

Revision `0009_payments` từ `0008_reader`: payment_orders, payment_events,
subscriptions; FK giữ hồ sơ khi xóa user (SET NULL), subscription/order RESTRICT,
unique idempotency/provider transaction/order grant, bounds và indexes. Không sửa
giá seed. Downgrade xóa dữ liệu billing mới; chỉ chạy trên Compose test độc lập.

Unit: HMAC raw bytes/time/format, strict payload, duplicate keys, fail-closed config.
Integration thật: PostgreSQL/Redis/Celery/FFmpeg toàn suite, concurrent orders/events,
quota/IDOR/CSRF, forged amount, receiver/code/date, rollback/retry, renewal và migration.
E2E standalone desktop/mobile: tạo đơn qua UI, mất response rồi retry, giả redirect,
ký webhook local qua proxy, duplicate/conflict, trạng thái và subscription.
Các webhook do test tự ký là **mô phỏng contract local**, không bằng chứng SePay đã gửi.
