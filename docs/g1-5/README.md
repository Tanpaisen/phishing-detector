# G1.5 — Đánh giá trên external development

## Phạm vi và nguồn dữ liệu

Người dùng xác nhận `dataset_B_05_2020.csv` tải trực tiếp từ trang Mendeley V3. File khớp byte với nguồn G1.4 đã ghim: SHA256 `21093e2902e5441c86a6daf95e86e7c332046e477fdf109a579d7bd81e586d6c`.

Đây là xác nhận nguồn tải của người dùng cộng kiểm tra tính toàn vẹn file, không phải phần mềm tự xác thực nguồn tải hoặc xác minh độc lập từng nhãn. Nhãn là chú thích lịch sử của nguồn, không mô tả chắc chắn trạng thái website hiện nay.

Giữ nguyên manifest G1.4 có trạng thái provisional để bảo toàn lịch sử. Lần chạy này ghi `provenance-record.json` riêng, chỉ cho phép đánh giá chẩn đoán trên **development**. Không tự chuyển trạng thái dữ liệu thành nguồn huấn luyện đã duyệt.

Script nạp hai mô hình từ chính lần huấn luyện G1.2 của bạn, kiểm tra checksum, schema, runtime và metadata trước khi nạp. Chỉ dùng các file joblib do bạn tự huấn luyện: checksum không khiến một pickle từ nguồn lạ trở nên đáng tin cậy.

Không huấn luyện lại, không đổi ngưỡng 0.5, không hiệu chỉnh xác suất, không kích hoạt model. Script đánh giá không mở train/validation/test JSONL của PhiUSIIL hoặc external holdout. Script audit riêng đọc train để đếm cấu trúc và đọc CSV nguồn để đối chiếu các dòng development; không chấm điểm holdout.

## Kết quả chạy tham chiếu

4572 dòng development, gồm 2253 legitimate và 2319 phishing theo nhãn nguồn:

| Mô hình | TN | FP | FN | TP | FPR | Recall | ROC AUC |
|---|---:|---:|---:|---:|---:|---:|---:|
| Logistic Regression | 14 | 2239 | 13 | 2306 | 99.38% | 99.44% | 0.6623 |
| Random Forest | 12 | 2241 | 7 | 2312 | 99.47% | 99.70% | 0.5109 |

FPR trên validation PhiUSIIL trước đó chỉ khoảng 0.035% và 0.049%. Đây là so sánh mô tả hai nguồn, không phải thí nghiệm chứng minh nguyên nhân. Recall cao của tập bổ sung không đủ để chấp nhận mô hình: cả hai gần như gán phishing cho mọi URL. Random Forest còn có khả năng xếp hạng rất yếu trên nguồn này.

Audit đối chiếu đủ 4572 dòng development với URL/nhãn trong CSV gốc, đều khớp. Trong train PhiUSIIL, cả 94395 dòng legitimate đều HTTPS và có đường dẫn rỗng. Trong external development, chỉ 148/2253 dòng legitimate có đường dẫn rỗng; 1278 dòng dùng HTTP. Điều này củng cố nghi ngờ mô hình học đặc điểm riêng của nguồn dữ liệu. Chưa chứng minh toàn bộ nguyên nhân, nhưng chỉ chỉnh ngưỡng không giải quyết được vấn đề tổng quát hóa đã quan sát.

Không cắt đường dẫn, bỏ dấu slash hoặc đổi HTTP thành HTTPS để làm đẹp kết quả: việc đó làm biến đổi đầu vào. Chưa đưa các model này vào API cảnh báo.

Các báo cáo `reference-*` đến từ môi trường tham chiếu Python 3.12.14, không phải xác nhận đã chạy trên Windows Python 3.14.8 của bạn. Manifest tham chiếu mô tả tên file gốc trong thư mục output, không dùng để kiểm tra các tên file có tiền tố `reference-` trong docs.

## Chạy trên Windows

Chạy từ thư mục gốc dự án, trên nhánh hiện tại `feat/url-baselines-g1-2`. Dùng lại môi trường training, không thêm dependency.

```powershell
.\services\training\.venv\Scripts\python.exe -m unittest discover -s services/training/tests -v
```

Bộ test hiện có 29 trường hợp. Test tạo mô hình nhỏ từ dữ liệu giả nên có log `Fitting`; lệnh đánh giá dữ liệu thật dưới đây không gọi fit.

```powershell
.\services\training\.venv\Scripts\python.exe services/training/evaluate_external_development.py --external "E:\BE_NodeJs\phishing-data\external\hannousse-provisional-v1" --baseline-run "E:\BE_NodeJs\phishing-models\url-baselines-v1" --primary-file "D:\download\dataset_B_05_2020.csv" --primary-origin mendeley-v3 --output "E:\BE_NodeJs\phishing-models\external-development-eval-v1" --workers 2
```

`--primary-origin mendeley-v3` ghi lại xác nhận nguồn tải bạn đã cung cấp. Không sửa runtime hoặc checksum để vượt qua lỗi; nếu không khớp cần kiểm tra lại đúng môi trường/lần chạy G1.2 và G1.4.

Tái lập audit cấu trúc:

```powershell
.\services\training\.venv\Scripts\python.exe services/training/audit_url_structure.py --dataset "E:\BE_NodeJs\phishing-data\processed\phiusiil-url-v1" --external "E:\BE_NodeJs\phishing-data\external\hannousse-provisional-v1" --primary-file "D:\download\dataset_B_05_2020.csv" --output "E:\BE_NodeJs\phishing-models\url-structure-audit-v1"
```

Output phải là thư mục mới. Không xóa lần chạy cũ chỉ để chạy lại; dùng tên phiên bản khác nếu cần. Báo cáo chỉ chứa số liệu tổng hợp, không xuất URL gốc. Dữ liệu và model giữ ngoài repository.

## Bước tiếp theo

Thiết kế lại dữ liệu huấn luyện đa nguồn và cách kiểm định, dựa trên chẩn đoán này. External development đã được quan sát, không còn là test độc lập. Giữ nguyên external holdout và PhiUSIIL test chưa chấm điểm; không dùng chúng để chọn đặc trưng, ngưỡng hay mô hình. Gói review 128 trường hợp vẫn cần bằng chứng rà soát, không tự chuyển sang đã xác minh.
