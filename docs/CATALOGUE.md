# Giai đoạn 04 — Thư viện phim

**Bổ sung ở giai đoạn 05:** Admin đã quản lý phim/tập/thể loại và URL poster/trailer;
API public thêm poster_url, trailer_url và genres. Poster tải trực tiếp ở browser
từ CDN được phép, có placeholder khi lỗi; trailer mở bằng liên kết YouTube.
Xem [ADMIN.md](ADMIN.md). Phần dưới ghi thiết kế/nghiệm thu giai đoạn 04.

Các trang `/`, `/movies` và `/movies/{slug}` đọc dữ liệu PostgreSQL qua FastAPI.
Home giới thiệu phim mới nhất và tối đa 8 thẻ phim. Thư viện có tìm tên phim,
sắp xếp mới thêm hoặc tên A–Z, phân trang và liên kết chi tiết. Trang chi tiết
hiển thị tên, năm, mô tả và gói yêu cầu; chưa có player hoặc URL media.

Không seed phim vào database dev. Khi chưa có nội dung xuất bản, web hiển thị
trạng thái trống. Artwork CSS trang chủ là trang trí; thẻ phim ghi rõ chưa có
poster. Quản lý phim/poster/trailer thuộc giai đoạn 05, phát video giai đoạn 07.

## Quyết định migration: NO-OP

Giữ Alembic head `0003_auth`. Schema 0002 đã có `movies.status`, slug unique,
title, synopsis, release_year, required_plan_code và index status/created_at.
Không thêm cột, quyền DB hoặc revision rỗng. Bộ test vẫn chạy upgrade/downgrade/
reapply và Alembic drift trên PostgreSQL riêng. Không rollback database dev.

Tìm kiếm substring hiện dùng PostgreSQL normalize NFC + ILIKE, có hỗ trợ hoa/thường
và tiếng Việt dạng composed/decomposed; còn phân biệt dấu. Escape `%`, `_`, `\`
để tìm literal; câu truy vấn bind parameters. Không nối input thành SQL.
Chưa có fuzzy/accent-insensitive search. Substring không dùng được B-tree hiện có;
cần đo dữ liệu thực rồi cân nhắc trigram index trước khi catalogue lớn/production.

## API public

| Endpoint | Tham số / kết quả |
|---|---|
| GET /movies | q tối đa 100 ký tự, page 1–1000, page_size 1–48 (mặc định 24), sort newest/title |
| GET /movies/{slug} | Slug ASCII theo schema, tối đa 200 ký tự; 404 khi không công khai |

List trả items/total/page/page_size. Item chỉ có slug/title/synopsis/release_year/
required_plan_code. Danh sách, tổng kết quả, tìm kiếm và detail đều chỉ trả published;
draft/archived/missing có cùng 404. Metadata phim yêu cầu VIP/Premium là công khai,
không đồng nghĩa được xem video. Episode chưa có publication flag nên chưa công khai.

Sắp xếp có UUID làm khóa phụ để ổn định thứ tự khi trùng ngày/tên. Offset pagination
có thể dịch chuyển khi nội dung được thêm/xóa giữa các lần tải; không cam kết snapshot.
Database có statement timeout 3 giây, SSR fetch timeout 4 giây; lỗi database trả 503
chung. No-store giúp lần tải mới thấy trạng thái xuất bản hiện tại. Trình duyệt đã
nhận nội dung trước đó không thể bị xóa từ xa bằng cơ chế này.

Frontend fetch URL nội bộ chỉ ở server, không nhận upstream URL từ người dùng.
Search dùng GET, giữ q/sort khi chuyển trang, giới hạn đầu vào cả hai lớp. React
render mô tả như text, không dùng dangerouslySetInnerHTML. Có labels, skip link,
focus ring, bố cục mobile, loading skeleton, thông báo lỗi và kết quả trống.

## Kiểm thử

Chạy backend/integration theo README. Compose E2E tự seed 28 phim hư cấu published
và hai phim ẩn trong database `suni_test` riêng. Script từ chối chạy ngoài APP_ENV=test
và database tên suni_test; stack dev không gọi script này.

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

Lượt E2E không có E2E_AUTH kiểm tra trạng thái backend unavailable; các bài cần
backend thật bị skip và không thay thế nghiệm thu full-stack.
