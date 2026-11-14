# G1.2 — Baseline URL lexical

Gói này tạo bộ trích đặc trưng dùng chung và so sánh Logistic Regression/Random Forest
trên dataset G1.1. Chưa tích hợp model vào FastAPI, chưa calibrate, chưa chọn policy cảnh báo,
chưa chạy suy luận final test. Giữ nguyên parser và script G1.1 để không làm hỏng checksum
của manifest dữ liệu đã đóng băng. Không có thay đổi database/API đang phục vụ.

## Cấu trúc

- `packages/python-core/src/phishing_core/url_features.py`: định nghĩa/thứ tự/dtype18đặc trưng.
- `services/training/train_url_baselines.py`: kiểm dataset, trích đặc trưng, fit và báo cáo.
- `services/training/requirements.txt`: dependency ML được pin riêng.
- `services/training/tests`: kiểm đặc trưng, leakage, scaler, serialization và lỗi.

Package shared không sao chép parser. Extractor nhận callback inspect_url từ
`services/ai/url_analysis.py`; training và inference tương lai phải dùng cùng cặp này.
Script thêm đường dẫn package trong repository vào sys.path để chạy ngay từ checkout;
`pyproject.toml` sẵn cho đóng gói/install khi triển khai service. Callback là dependency tin cậy,
không phải hàm do request người dùng cung cấp. Bộ parser hiện tại vẫn là nguồn chuẩn duy nhất.

## Đặc trưng E1

Schema `url-lexical-v1`, float64, thứ tự cố định:

| Đặc trưng | Quy tắc |
|---|---|
| url_length | Số code point của input sau bỏ ASCII space ngoài cùng, theo inspect |
| hostname_length | Độ dài hostname ASCII đã chuẩn hóa |
| subdomain_count | Số thành phần subdomain theo PSL/private suffix của inspect |
| digit_count | Số chữ số ASCII0–9 trong toàn input, gồm port/path/query/fragment |
| is_ip | Host là địa chỉ IP được parser chấp nhận |
| is_https | Scheme chuẩn hóa bằng https |
| path_length, query_length, fragment_length | Độ dài từng phần, không tính dấu phân cách ?, #; không percent-decode |
| hyphen_count, dot_count, slash_count | Đếm -, ., / trong toàn input |
| equals_count, ampersand_count | Đếm =, & trong toàn input |
| percent_escape_count | Số chuỗi percent-encoded hợp lệ dạng %HH |
| has_query, has_fragment | Có dấu ?/#, kể cả nội dung sau dấu rỗng |
| has_explicit_port | Input có port rõ ràng, kể cả port mặc định |

Dùng `input_url` để giữ biểu diễn người dùng, không lấy normalized_url thay toàn bộ input.
Mẫu sai phải lỗi; không tự điền vector0. Không dùng y/source_label/source_id/sample_id/group_id,
chuỗi tên miền, nhãn G0, chỉ số từ HTML hay blacklist làm đặc trưng. Không DNS/tải website đích.
Unicode/confusable/brand similarity là nhóm thí nghiệm sau; không quảng cáo E1 đã có chúng.

## Thiết kế thí nghiệm đã cố định trước khi chạy

| Mô hình | Cấu hình |
|---|---|
| Logistic Regression | StandardScaler fit trên train; C=1, lbfgs, max_iter=2000, class_weight=balanced, seed42 |
| Random Forest | 100 cây, max_depth16, min_samples_leaf2, max_features=sqrt, class_weight=balanced, seed42 |

Chạy toàn bộ train164210 và validation35188, không subsample để lấy kết quả nhanh. Không grid
search, không đổi seed dựa kết quả. Candidate ưu tiên Average Precision trên validation;
đồng hạng thì FPR ở0,5 thấp hơn, tiếp nữa chọn LR. Đây là tiêu chí so sánh baseline, không phải
promotion gate cho triển khai thật. Chưa có cam kết recall/FPR mục tiêu của sản phẩm.

Báo accuracy, precision, recall, F1, FPR, Average Precision, ROC AUC, confusion matrix.
Lớp dương là y=1 PHISHING. Các metric phân lớp dùng ngưỡng0,5 cố định. AP/ROC AUC dùng score
liên tục. `predict_proba` của hai model được lưu là MODEL_SCORE chưa hiệu chỉnh, không hiển thị
như phần trăm độ tin cậy đã calibrate; class_weight cũng ảnh hưởng cách diễn giải điểm.
Scalers không fit trên validation. Tập test chỉ xuất hiện dưới dạng metadata checksum trong
manifest nguồn; script G1.2 không mở/hash/parse test.jsonl. Kiểm G1.1 trước đó là kiểm cấu trúc,
không phải dùng kết quả dự đoán final test để lựa chọn model.

## Chạy trên Windows PowerShell

Tại thư mục gốc `E:\BE_NodeJs\phishing-detector`:

```powershell
py -3.14 -m venv services/training/.venv
.\services\training\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r services/training/requirements.txt
.\services\training\.venv\Scripts\python.exe -m unittest discover -s services/training/tests -v
```

Venv training tách khỏi venv AI. Dùng đúng Python3.14 patch version đã tạo dataset trên máy
bạn; manifest kiểm cả Python/Unicode/IDNA/PSL. Không dùng bản dataset đã tạo bằng Python3.12
trong báo cáo tham chiếu để thay dataset3.14 của bạn. Không sửa manifest để bỏ qua mismatch.
Nếu pip báo không có wheel, giữ nguyên lỗi để kiểm tra kiến trúc/phiên bản, không tự nâng
hàng loạt dependency. Các phiên bản là lựa chọn tái lập của thí nghiệm, không tuyên bố mới nhất.

Huấn luyện và đánh giá validation:

```powershell
.\services\training\.venv\Scripts\python.exe services/training/train_url_baselines.py --dataset "E:\BE_NodeJs\phishing-data\processed\phiusiil-url-v1" --output "E:\BE_NodeJs\phishing-models\url-baselines-v1" --workers 2
```

Mỗi25000mẫu có dòng tiến độ. Thời gian phụ thuộc laptop; không suy ra từ thời gian chạy của
máy tham chiếu. Nếu máy cần dành tài nguyên cho việc khác, có thể đặt workers1 trước khi chạy.
workers cho phép1–4, hạn chế cả BLAS và RF. Không chạy hai tiến trình vào cùng thư mục output.
Không ghi đè output đã tồn tại; dùng thư mục run mới khi thực sự làm thí nghiệm mới.

Kết quả nằm ngoài Git:

| Tệp | Nội dung |
|---|---|
| logistic_regression.joblib | Pipeline scaler + LR cùng feature schema |
| random_forest.joblib | RF cùng feature schema |
| feature-schema.json | Thứ tự/kiểu/quy tắc vector |
| report.json | Metric validation, tham số, thời gian batch, môi trường, candidate và giới hạn |
| manifest.json | Hash model/report/code/dataset, preprocessing và runtime |

Không commit model binary hoặc dữ liệu raw. Có thể gửi report.json khi cần đối chiếu; nó
không có input URL, dự đoán từng mẫu hay token. Chỉ load joblib do chính pipeline tin cậy tạo;
joblib/pickle có thể thực thi mã. Inference tương lai phải kiểm manifest/runtime/feature schema,
không nhận model do khách upload rồi deserialize. Candidate chưa được tự đăng ký hay kích hoạt.

## Ý nghĩa và giới hạn kết quả

- Metric hiện tại thuộc validation đã dùng chọn candidate, không phải ước lượng cuối độc lập.
- Dataset gốc và bộ lọc vẫn có selection bias:793 URL bị từ chối đều thuộc phishing nguồn.
- Chia theo miền không bảo đảm chiến dịch/timestamp độc lập hoặc khả năng tổng quát trên URL mới ở Việt Nam.
- Accuracy/AP cao không chứng minh chống phishing thật; cần ablation, dữ liệu bổ sung và false-positive review.
- Thời gian fit/predict của batch không phải latency API, p50/p95 hay peakRAM trên laptop.
- Không có confidence interval trong gói baseline này; tránh diễn giải chênh lệch rất nhỏ là vượt trội chắc chắn.

Bước tiếp theo: xem kết quả validation trên máy bạn, kiểm lỗi và nhóm đặc trưng, thiết kế
calibration/ngưỡng/promotion gate bằng dữ liệu validation phù hợp. Chỉ mở final test sau khi
chốt toàn bộ lựa chọn và ghi lại manifest; không dùng final test lặp lại để tiếp tục tối ưu.

Tài liệu tham khảo chính thức: [cài scikit-learn](https://scikit-learn.org/stable/install.html),
[tránh rò rỉ dữ liệu](https://scikit-learn.org/stable/common_pitfalls.html),
[lưu mô hình](https://scikit-learn.org/stable/model_persistence.html).

## Kết quả chạy tham chiếu

Môi trường Python3.12.14/Linux, sklearn1.8.0; toàn bộ train/validation của G1.1.
Bản dependency binary dành cho Windows64-bit/Python3.14 tải thành công; đây không phải
khẳng định đã cài/chạy trên laptop. Chi tiết ở reference-report.json và validation-report.json.

| Model | Recall | FPR | Average Precision | FP | FN |
|---|---:|---:|---:|---:|---:|
| Logistic Regression | 98,6698% | 0,0346% | 0,997532 | 7 | 199 |
| Random Forest | 99,1377% | 0,0494% | 0,998135 | 10 | 129 |

RF có AP cao hơn nên là candidate theo quy tắc đã chốt. LR có ít false positive hơn ở ngưỡng0,5;
không thể nói RF tốt hơn mọi mặt. Chênh lệch AP nhỏ và chưa có kiểm định độ bất định.
Kết quả cao cần được kiểm bằng ablation/nguồn bổ sung ở bước tiếp, không tự biến thành
cam kết phát hiện phishing thực tế. Tập test chưa được mở bởi mã huấn luyện.
