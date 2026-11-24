# G1.10 — Đo hiệu năng URL và API hiện có

Đây là bước đo hiệu năng, không phải nghiệm thu Big Data hoặc kích hoạt mô hình. Phạm vi theo đề cương ngày 24/11/2026: URL, ảnh QR chứa URL và SMS tiếng Việt do người dùng nhập/dán; chưa huấn luyện nội dung Zalo/Messenger/email. Bước này chỉ đo đường xử lý URL đã có, không thay đổi phạm vi SMS.

## Các phần được đo

| Công cụ | Đo gì | Không đo gì |
|---|---|---|
| benchmark_local.py --mode inspection | Chuẩn hóa/kiểm tra URL trong tiến trình Python | HTTP, mô hình, DB |
| benchmark_local.py --mode features | Kiểm tra URL và trích cả ba bộ đặc trưng G1.8, rồi bỏ kết quả mỗi dòng | Huấn luyện Random Forest, lưu toàn bộ ma trận |
| benchmark_api.py | HTTP client → router Node → AI inspection, kết quả phân loại theo status/contract | Suy luận phishing, truy vấn PostgreSQL, RAM/CPU server |

Mã AI hiện trả model_loaded=false; PostgreSQL không nằm trên đường /url/inspect. Không gọi thời gian inspection là thời gian phát hiện phishing. Chưa thêm Elasticsearch vì chưa có bằng chứng truy vấn DB là điểm nghẽn.

Mã nghiên cứu G1.8/G1.9 vẫn giữ nhiều mảng trong RAM. Bộ đo streaming mới chỉ kiểm tra khả năng xử lý từng dòng và bỏ kết quả; **không chứng minh bộ huấn luyện cũ đã mở rộng được đến hàng triệu dòng**. Muốn đo huấn luyện phải đo riêng worker, toàn bộ ma trận và quá trình fit.

## Cài và kiểm thử trên Windows

Giữ nhánh hiện tại. Không sửa requirements hoặc code đã được manifest G1.1–G1.9 đóng băng.

```powershell
Set-Location E:\BE_NodeJs\phishing-detector
git apply --check "D:\download\g1-10-url-performance.patch"
git apply "D:\download\g1-10-url-performance.patch"
.\services\training\.venv\Scripts\python.exe -m pip install -r scripts/g1_10/requirements.txt
.\services\training\.venv\Scripts\python.exe -m unittest discover -s scripts/g1_10/tests -v
```

Chỉ thêm psutil==7.2.2 để lấy RSS và CPU của tiến trình. Môi trường vẫn cần bộ URL/IDNA đã có. Không cài lại các phụ thuộc AI đang đóng băng.

## 1. Đo workload tăng kích thước

Tạm dừng tác vụ huấn luyện khác. Mỗi kích thước chạy trong tiến trình con mới để tránh RSS của lần trước ảnh hưởng lần sau.

```powershell
.\services\training\.venv\Scripts\python.exe scripts/g1_10/benchmark_local.py `
  --mode features --rows 10000 100000 `
  --output "E:\BE_NodeJs\phishing-models\performance-v1\synthetic-features"
```

Mặc định lặp 8 URL tổng hợp, gồm HTTP/HTTPS, query, IDNA, Unicode và URL dài. Không mở website. Dữ liệu lặp chỉ kiểm tra tải và bộ nhớ, không phải dữ liệu đánh giá độ chính xác hoặc chứng minh độ đa dạng thực tế.

Sau khi kiểm tra mức RAM và thời gian của hai lần đầu, có thể chạy riêng một triệu dòng:

```powershell
.\services\training\.venv\Scripts\python.exe scripts/g1_10/benchmark_local.py `
  --mode features --rows 1000000 `
  --output "E:\BE_NodeJs\phishing-models\performance-v1\synthetic-million"
```

Không tự coi một triệu dòng đã được kiểm chứng nếu chưa chạy lệnh này thành công. Có thể Ctrl+C nếu cần dừng; thư mục dang dở không có report tổng hợp thành công.

## 2. Đo trên URL thực trong TRAIN

```powershell
.\services\training\.venv\Scripts\python.exe scripts/g1_10/benchmark_local.py `
  --mode features --rows 10000 100000 `
  --train-jsonl "E:\BE_NodeJs\phishing-data\processed\phiusiil-url-v1\train.jsonl" `
  --output "E:\BE_NodeJs\phishing-models\performance-v1\train-features"
```

Chỉ chấp nhận tên train.jsonl. Đọc tiền tố theo thứ tự, không đọc validation/test/holdout, không lấy nhãn và không lặp lại mẫu thật nếu thiếu số dòng. Hash toàn bộ file train trước/sau chạy; đây là kiểm tra file không đổi, không thay thế kiểm định nhãn/manifest G1.1. Không đổi tên file test thành train.

Để đo riêng inspection, chạy lại với --mode inspection và thư mục output mới.

Báo cáo gồm:
- Tổng thời gian xử lý có đọc/parsing dòng dữ liệu; thông lượng tổng và thông lượng thành công tách riêng URL bị từ chối.
- p50/p95/p99 theo nearest-rank của tối đa 1.000 lần xử lý thành công đầu tiên. Đây là mẫu tiền tố, không phải phân vị đại diện cho toàn bộ dữ liệu.
- First-call đo sau import, 100 warmup tổng hợp không nằm trong pha đo chính. Không gọi first-call là thời gian khởi động toàn tiến trình.
- RSS lấy mẫu mỗi 20 ms, RSS ban đầu, RSS đỉnh quan sát và CPU seconds của chính worker. Có thể bỏ lỡ đỉnh ngắn; không bao gồm toàn bộ máy hoặc tiến trình khác.
- Cấu hình Python, hệ điều hành, số CPU, tổng RAM, hash mã.

## 3. Đo API Node → FastAPI

Chạy hai server bằng các lệnh hiện có trên máy bạn, AI tại 8000 và Node tại 3001, cấu hình token như trước. Kiểm tra health/ai hoạt động. Ghi lại máy, số worker, lệnh khởi động, có dùng reload hay không; khuyến nghị không có huấn luyện đồng thời. Không gửi token vào công cụ đo và không thay rate limit.

Đợi ít nhất 65 giây kể từ lần gọi /url/inspect trước, rồi chạy các mức sau. Thời gian chờ nhằm bắt đầu một cửa sổ rate limit mới, không phải tắt bảo vệ.

```powershell
.\services\training\.venv\Scripts\python.exe scripts/g1_10/benchmark_api.py `
  --requests 20 --concurrency 1 `
  --output "E:\BE_NodeJs\phishing-models\performance-v1\api-c1.json"

.\services\training\.venv\Scripts\python.exe scripts/g1_10/benchmark_api.py `
  --requests 20 --concurrency 4 `
  --output "E:\BE_NodeJs\phishing-models\performance-v1\api-c4.json"

.\services\training\.venv\Scripts\python.exe scripts/g1_10/benchmark_api.py `
  --requests 80 --concurrency 8 `
  --output "E:\BE_NodeJs\phishing-models\performance-v1\api-burst.json"
```

Mức cuối chủ ý quan sát rate limit. Nếu cả ba chạy trong cùng cửa sổ 60 giây, không có lượt gọi khác và bắt đầu cửa sổ mới, dự kiến 60/120 lượt được xử lý, 60 lượt bị 429. Nếu cửa sổ đổi hoặc có lượt gọi khác thì số lượng khác; báo cáo số quan sát, không ép khớp dự kiến.

API probe chỉ gửi hai URL tổng hợp tới HTTP loopback có IP literal và đúng đường /api/v1/url/inspect. Không theo redirect, không retry, không dùng proxy môi trường. Mỗi worker tái sử dụng kết nối khi có thể. Timeout là timeout socket, không phải deadline tổng cứng cho mọi pha request.

- 200 phải có stage/schema/model_loaded và normalized_url đúng với đầu vào, mới tính success.
- 429, HTTP timeout, transport timeout, lỗi HTTP và sai contract báo riêng.
- Throughput success khác attempts/second. Latency của lỗi không được trộn vào success-only latency.
- Probe closed-loop không có think time: worker chỉ gửi lượt kế sau khi lượt trước xong. Không suy ra công suất chịu tải với tốc độ đến cố định.
- 20 mẫu thành công chỉ là smoke measurement; p99 không ổn định, không dùng để khẳng định SLA. Đo dài hạn cần chiến dịch riêng với rate limit và mô hình đến phù hợp.
- RSS/CPU trong báo cáo HTTP là của **client**, không phải Node/FastAPI.

## Đọc kết quả và bước tiếp theo

Trạng thái MEASURED_WITH_NON_SUCCESS_OUTCOMES vẫn ghi được báo cáo để chẩn đoán; không có nghĩa là đạt kiểm thử tải. Nếu tất cả bị 429 hoặc lỗi, success-only latency là null, không phải 0 ms.

Không có ngưỡng nghiệm thu hiệu năng được tự đặt trong bước này. Đối chiếu báo cáo máy bạn trước khi chốt mục tiêu. Tiếp theo cần đo server RAM/CPU, worker huấn luyện thật, suy luận ứng viên trong môi trường nghiên cứu và truy vấn PostgreSQL có chỉ mục. Chỉ cân nhắc Elasticsearch khi có workload tìm kiếm rõ ràng và phép đo cho thấy cần thiết. Các cải tiến chất lượng mô hình vẫn tiếp tục riêng; benchmark không khắc phục FPR/recall của G1.9.

Các thư mục output phải mới. Nếu lệnh lỗi giữa chừng, báo cáo từng kích thước có thể còn lại nhưng chưa có report.json tổng hợp; kiểm tra lỗi rồi chạy tên thư mục khác. Không sửa hoặc xóa dữ liệu nghiên cứu cũ để chạy lại.

Gửi report.json của hai workload local và các api-*.json. Không cần gửi URL nguyên bản. Chỉ commit scripts/g1_10 và docs/g1-10; giữ báo cáo máy cá nhân ngoài repo hoặc khử thông tin trước khi đưa vào luận văn.

## Kết quả tham chiếu ngày 24/11/2026

Đo trên môi trường Linux của người triển khai, không phải laptop Windows của bạn. Hai lượt kích thước tổng hợp chạy tuần tự, mỗi lượt một tiến trình mới. Đây là số quan sát của một lượt mỗi cấu hình, không có khoảng tin cậy.

| Workload features | Số dòng | Thời gian (s) | URL/s | RSS đỉnh quan sát (MiB) |
|---|---:|---:|---:|---:|
| synthetic_cycle_8_not_accuracy_data | 10000 | 6.84 | 1461.86 | 30.18 |
| synthetic_cycle_8_not_accuracy_data | 100000 | 68.45 | 1460.87 | 31.17 |
| train_prefix | 10000 | 6.86 | 1457.42 | 31.02 |

API tham chiếu dùng router Express thật của dự án và FastAPI thật, chạy qua loopback với một AI worker và không reload. Entry Express thử nghiệm chỉ mount router inspection, không khởi tạo PostgreSQL hoặc toàn bộ server.ts. Hai lần đầu lần lượt 20/20 thành công ở concurrency 1 và 4. Lần burst concurrency 8 có 20/80 thành công, 60/80 rate-limited. Đây là phép thử nhỏ có kiểm tra hợp đồng phản hồi tối thiểu; không phải kiểm thử công suất toàn hệ thống.

Chưa chạy workload một triệu dòng trong bản tham chiếu này. Chưa đo fit mô hình, RAM server, PostgreSQL hoặc suy luận AI. 11 kiểm thử mới, 71 kiểm thử training cũ và kiểm thử gateway Node đều đạt.
