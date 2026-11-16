# G1.6 — Thí nghiệm huấn luyện URL đa nguồn

## Câu hỏi nghiên cứu

Việc bổ sung cấu trúc URL từ nguồn Hannousse có giảm cảnh báo nhầm trên phần development được giữ lại, đồng thời duy trì kết quả trên validation PhiUSIIL không?

Đây là thí nghiệm nghiên cứu trên nhãn lịch sử của nguồn. Xác nhận tải trực tiếp Mendeley V3 và checksum không có nghĩa từng nhãn đã được xác minh độc lập. Không thay đổi trạng thái của dữ liệu G1.4 thành dữ liệu sản xuất đã duyệt.

## Thiết kế cố định trước khi chạy

- Giữ nguyên train/validation của PhiUSIIL; không đọc `test.jsonl`.
- Chỉ đọc `development.jsonl` của Hannousse, không đọc `holdout.jsonl`.
- Chia development theo `sha256('g16-external-v1:' + group_id) % 100 < 80`: train; phần còn lại là reused validation. Tỷ lệ 80/20 là kỳ vọng theo nhóm, không ép số dòng hay tỷ lệ nhãn.
- Cùng miền/IP group luôn cùng phía; không thử nhiều seed để tìm kết quả đẹp. Nếu một phía thiếu nhãn thì dừng.
- Toàn bộ external development đã được quan sát ở G1.5. Reused validation chỉ hỗ trợ nghiên cứu; không phải kiểm thử độc lập.
- Kiểm tra checksum, môi trường, phiên bản parser/features, nguồn tải và đúng dataset nền; đối chiếu URL/nhãn development với CSV gốc. Kiểm tra trùng sample/domain giữa các phần train/validation và giữa hai nguồn trước khi fit.
- Ngưỡng 0.5, seed 42 và 18 đặc trưng giữ nguyên G1.2; chưa tuning, calibration hoặc chọn mô hình tự động.

| Phương án | Dữ liệu fit | Trọng số |
|---|---|---|
| `phiusiil_only` | PhiUSIIL train | `class_weight=balanced` như G1.2 |
| `mixed_pooled` | PhiUSIIL train + external train | `class_weight=balanced` trên tập gộp |
| `mixed_source_class_balanced` | Cùng tập gộp | Bốn ô nguồn × nhãn có tổng trọng số bằng nhau |

Mỗi phương án chạy Logistic Regression và Random Forest. Với phương án thứ ba, đặt `class_weight=None` để không cân bằng hai lần. Mẫu thuộc ô có n dòng nhận trọng số N/(4n). StandardScaler của LR được fit trên train với cùng trọng số; không fit scaler trên validation. Cân bằng nguồn không bảo đảm tốt hơn: nguồn nhỏ có thể bị nhấn mạnh quá mức, nên phải xem kết quả riêng từng nguồn.

Đánh giá mỗi mô hình riêng trên validation PhiUSIIL và external reused validation, gồm confusion matrix, FPR, precision, recall, F1, AP, ROC AUC và nhóm HTTP/HTTPS. Không gộp hai nguồn thành một điểm tổng để chọn người thắng.

## Chạy trên máy bạn

Dùng nhánh hiện tại `feat/url-baselines-g1-2`, môi trường training hiện có. Không sửa các file G1.1–G1.5 đã được ghim hash.

```powershell
.\services\training\.venv\Scripts\python.exe -m unittest discover -s services/training/tests -v

.\services\training\.venv\Scripts\python.exe services/training/train_multisource_experiment.py --dataset "E:\BE_NodeJs\phishing-data\processed\phiusiil-url-v1" --external "E:\BE_NodeJs\phishing-data\external\hannousse-provisional-v1" --baseline-run "E:\BE_NodeJs\phishing-models\url-baselines-v1" --primary-file "D:\download\dataset_B_05_2020.csv" --primary-origin mendeley-v3 --output "E:\BE_NodeJs\phishing-models\multisource-experiment-v1" --workers 2
```

`--primary-origin` ghi lại xác nhận nguồn tải đã cung cấp. `--baseline-run` chỉ dùng để kiểm tra thông tin và hash; script không nạp pickle cũ. Tất cả mô hình được fit mới trong bộ nhớ.

Thư mục output phải chưa tồn tại. Script xuất:

- `report.json`: cấu hình, số mẫu/nhóm/nhãn và kết quả theo phương án/mô hình/nguồn.
- `external-assignments.jsonl`: sample ID, group ID, source record và vai trò, không chứa URL gốc. Giữ ngoài Git cùng dữ liệu nghiên cứu.
- `manifest.json`: hash đầu vào, mã thí nghiệm và file đầu ra.

Thí nghiệm không xuất model triển khai, không kích hoạt API và không sửa mô hình cũ. Đây là bước xác định hướng cải thiện dữ liệu, chưa phải một release. Điểm số vẫn là MODEL_SCORE chưa hiệu chỉnh xác suất.

## Kiểm thử và giới hạn

Test bao gồm chia miền ổn định theo thứ tự/nhãn, cân bằng bốn ô trọng số, truyền trọng số vào scaler/classifier, phát hiện overlap/thiếu nhãn, checksum, lỗi fit không công bố output, không ghi đè và luồng chạy offline không mở test/holdout hoặc nạp pickle.

Kết quả tham chiếu (nếu đi kèm) chạy Python 3.12.14. Bạn cần chạy trên Python 3.14.8 của mình trước khi coi là đã xác nhận trên Windows. Các file `reference-*` là bản sao metadata; manifest tham chiếu chứa tên file gốc trong output, không phải tên có tiền tố trong docs.

Sau thí nghiệm, xem đồng thời FPR và recall từng nguồn. Kể cả có cải thiện cũng không gọi đây là hiệu năng thực tế hoặc đánh giá cuối cùng. Giữ nguyên hai tập kiểm thử chưa quan sát; chưa sửa nhãn tự động từ dự đoán, chưa đưa 128 ca review chưa xác minh vào train.

## Kết quả tham chiếu thực nghiệm

External development được chia thành 3691 dòng train (2620 nhóm; 1781 legitimate, 1910 phishing) và 881 dòng reused validation (627 nhóm; 472 legitimate, 409 phishing). Không mở hai tập kiểm thử cuối cùng. Bộ test training có 37 test đều đạt.

| Phương án | Mô hình | External FPR | External recall | PhiUSIIL FPR | PhiUSIIL recall |
|---|---|---:|---:|---:|---:|
| mixed_pooled | logistic_regression | 95.34% | 98.78% | 0.025% | 97.79% |
| mixed_pooled | random_forest | 86.02% | 99.27% | 0.059% | 99.08% |
| mixed_source_class_balanced | logistic_regression | 54.03% | 86.80% | 0.465% | 57.49% |
| mixed_source_class_balanced | random_forest | 34.32% | 93.64% | 0.044% | 95.67% |
| phiusiil_only | logistic_regression | 98.94% | 99.76% | 0.035% | 98.67% |
| phiusiil_only | random_forest | 99.15% | 99.76% | 0.049% | 99.14% |

Gộp dữ liệu đơn thuần vẫn có FPR cao. Random Forest cân bằng nguồn/nhãn cải thiện external FPR từ 99.15% xuống 34.32%, nhưng external recall giảm từ 99.76% xuống 93.64%, và PhiUSIIL recall từ 99.14% xuống 95.67%. External ROC AUC tăng từ 0.5035 lên 0.9108. Đây là hướng nghiên cứu có triển vọng, chưa đạt yêu cầu cảnh báo người dùng. Logistic Regression cân bằng nguồn giảm PhiUSIIL recall xuống 57.49%, nên không thể chỉ nhìn mức giảm cảnh báo nhầm ở nguồn bổ sung.

Bước nghiên cứu tiếp theo cần xem xét độ đa dạng nguồn/đặc trưng và lỗi còn lại trên development trước khi chốt phương án. Chưa dùng holdout để cải tiến, chưa tự chọn ngưỡng triển khai. Không so sánh trực tiếp tỷ lệ G1.5 trên 4572 dòng với G1.6 trên 881 dòng như thể cùng một tập; bảng G1.6 đã chạy lại baseline trên đúng cùng 881 dòng để so sánh công bằng.
