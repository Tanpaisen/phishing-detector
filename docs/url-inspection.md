# Bước 1: kiểm tra và chuẩn hóa URL

Đây là API hỗ trợ phát triển trên localhost, chưa phải chức năng scan hoàn chỉnh.
Chưa có model, điểm phishing, kết luận rủi ro, scan_id hoặc lưu database.
Các API health cũ và readiness `503 MODEL_NOT_LOADED` vẫn giữ nguyên.

## Phạm vi đã làm

- Python là nơi duy nhất chuẩn hóa URL; Node chỉ kiểm tra body và chuyển tiếp.
- HTTP/HTTPS tuyệt đối, tối đa 4.096 Unicode code point, kiểm tra control character
  trước khi gọi parser; không chấp nhận userinfo, backslash hoặc percent-encoding hỏng.
- IDNA UTS #46 non-transitional, giữ tên miền ASCII/Unicode; đây chưa phải phát hiện homograph.
- PSL đóng gói trong tldextract 5.3.0, gồm private suffix như github.io;
  tắt tải mạng và cache, trả SHA-256 snapshot cùng phiên bản thư viện.
- IPv4/IPv6 công khai dạng chuẩn; từ chối IP nội bộ/đặc biệt, dạng IPv4 rút gọn,
  hostname không có miền đăng ký được nhận diện trong snapshot PSL.
- Chỉ lowercase scheme/hostname, bỏ một dấu chấm cuối hostname, chuẩn hóa port số;
  giữ path/query/fragment và dấu ?/# rỗng. Không giải mã percent-encoding, không sắp query.
- Không gọi DNS/HTTP tới URL, không mở redirect, không đọc website và không lưu input.
- Node giới hạn body 128 KiB và 60 yêu cầu/phút/IP trong bộ nhớ, timeout 8 giây,
  xác thực nội bộ, request ID và Cache-Control: no-store.

PSL cho biết ranh giới tên miền theo snapshot, không xác minh đăng ký thực tế hoặc
website đang tồn tại. URL được chấp nhận chỉ nghĩa là thuộc phạm vi kiểm tra cú pháp.
Đáp ứng vẫn trả URL đầy đủ cho bên gọi: không chia sẻ ảnh kết quả có token/OTP.
Lỗi không phản chiếu input. Access log không chứa body; không đưa URL vào query API.

## Cập nhật trên Windows

Nếu nhận file `url-inspection.patch` thay vì nhánh GitHub, tại thư mục gốc dự án
chạy `git apply --check DUONG_DAN_PATCH` rồi `git apply DUONG_DAN_PATCH` khi kiểm tra
không báo lỗi. Không chạy các lệnh lấy nhánh bên dưới cho đến khi nhánh đã được đưa lên GitHub.
Sau khi áp dụng patch, tiếp tục các bước cài thư viện và chạy test trong hai terminal.

Giữ nguyên hai `.env` hiện có (không bị Git ghi đè). Dừng hai server trước khi cập nhật.

```powershell
Set-Location E:\BE_NodeJs\phishing-detector
git fetch origin
git switch --track origin/feat/url-inspection
```

Nếu nhánh đã tồn tại, dùng `git switch feat/url-inspection` rồi `git pull --ff-only`.
Nếu Git báo thay đổi local xung đột, giữ nguyên file và xử lý trước khi chuyển nhánh;
không dùng reset --hard hoặc clean để ép chuyển.

Terminal Python:

```powershell
Set-Location E:\BE_NodeJs\phishing-detector\services\ai
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Terminal Node:

```powershell
Set-Location E:\BE_NodeJs\phishing-detector\apps\api
npm.cmd ci
npm.cmd run build
npm.cmd test
npm.cmd run dev
```

Terminal thứ ba:

```powershell
$body = @{ url = "https://LOGIN.Example.co.uk/Login?A=1#Section" } | ConvertTo-Json
Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:3001/api/v1/url/inspect" `
  -ContentType "application/json; charset=utf-8" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) | ConvertTo-Json -Depth 8
```

Kết quả mong đợi: stage=URL_INSPECTION, model_loaded=false,
hostname_ascii=login.example.co.uk, registered_domain=example.co.uk,
subdomain=login. Path /Login, query A=1 và fragment Section giữ nguyên.
Không có risk_level hoặc model_score. Đây là POST; mở URL API trong thanh địa chỉ
trình duyệt sẽ gửi GET và không chạy chức năng này.

## Hợp đồng API

POST `/api/v1/url/inspect` → POST `/internal/v1/url/inspect`.
Body chính xác một trường `url` dạng string. Node gửi X-Service-Token nội bộ;
frontend không được nhận hoặc gửi khóa này. Python health và inspect đều cần khóa.

200: schema_version=1.0, stage, model_loaded=false, preprocessing_version,
resources (PSL checksum/phiên bản thư viện), url (normalized_url, hostname_ascii,
hostname_unicode, hostname_input (trước IDNA), registered_domain nullable, public_suffix, subdomain, port nullable,
scheme, is_ip, is_private_suffix), features (đếm ký tự/nhãn và cờ cấu trúc), limitations.
Node thêm request_id. Không ghi những đặc trưng ban đầu này là bộ feature cuối cùng.

Lỗi Node: `{request_id, error: {code, message}}`.
400 JSON hỏng; 413 body quá lớn; 415 content type; 422 URL/body ngoài phạm vi;
429 vượt giới hạn; 503 dịch vụ chưa cấu hình/hỏng/sai hợp đồng; 504 timeout.
Python validation cũng trả lỗi đã bỏ input. Unauthorized nội bộ trả 401,
Node chuyển lỗi phụ thuộc đó thành 503 thay vì tiết lộ chi tiết xác thực.

## Kiểm thử và giới hạn

Python unittest kiểm tra các nhóm: chuẩn hóa, IDNA, PSL/private suffix,
IP công khai, đầu vào sai/nội bộ, không gọi mạng ngay lần nạp PSL đầu tiên,
xác thực, readiness và loại dữ liệu nhạy cảm khỏi lỗi.
Node test chạy HTTP server thật với upstream giả để kiểm tra giới hạn, mã lỗi,
forward token, timeout, sai hợp đồng và không rò input. Không cần PostgreSQL cho các test này.

Smoke test Node → FastAPI thật được mô tả bằng lệnh PowerShell ở trên.
Đây chưa phải hoàn thành T01–T24 của đặc tả 1.1: chưa có session/scan, model, feedback,
triển khai release hoặc kiểm thử toàn hệ thống. Rate limit trong bộ nhớ phù hợp local,
chưa dùng để triển khai nhiều tiến trình. Chưa bật CORS vì chưa có frontend.

Bước kế tiếp: chốt dataset/nhãn và bộ đặc trưng URL cho baseline, dùng lại preprocessing,
lưu manifest tài nguyên; chỉ thêm API scan khi có model và hợp đồng kết quả phù hợp.

### Kết quả kiểm tra trên môi trường phát triển

- Node.js 24.22.1: npm ci từ package-lock hiện có, TypeScript build thành công.
- Node HTTP gateway test: pass (bao gồm body/schema, forwarding, timeout, lỗi và rate limit).
- Python 3.12: 11 test methods pass, gồm nhiều subcase; đã chạy lại với requirements-dev.txt
  của repository (FastAPI 0.162.5, Pydantic 2.14.3, IDNA 3.20, tldextract 5.3.0).
- Smoke test Node → FastAPI thật: URL hợp lệ, ba đầu vào bị từ chối và AI ngừng hoạt động đều đúng.
- Không kết nối PostgreSQL trong lượt kiểm tra này: inspect không đọc/ghi database.
- Chưa kiểm chứng trên Windows/Python 3.14 của người dùng; chạy các lệnh trên để xác nhận tại máy.
- Có cảnh báo deprecation của Starlette về httpx trong test client; test vẫn pass.

### Bổ sung sau rà soát

- Phân biệt Unicode trong toàn URL với Unicode riêng hostname; đường dẫn tiếng Việt
  không tự trở thành dấu hiệu tên miền Unicode.
- Giữ hostname_input trước ánh xạ IDNA và cờ ký tự format vô hình để không mất dấu hiệu
  tiền xử lý; chưa gán mức rủi ro cho các cờ này. Khi dựng UI, hiển thị hostname_ascii
  bên cạnh và escape ký tự vô hình, không dùng hostname_input làm liên kết bấm.
- Manifest có Python/Unicode version vì chuẩn hóa phụ thuộc dữ liệu của runtime.
- Node từ chối cả trường ngoài hợp đồng trong object lồng nhau, không chuyển tiếp
  trường debug hoặc bí mật vô tình xuất hiện từ Python.
- Charset/content encoding không hỗ trợ trả 415; lỗi parse trả 400, không trả 500 chung.
