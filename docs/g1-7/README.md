# G1.7 — Tái lập và phân tích lỗi đa nguồn

G1.7 tái lập Random Forest `mixed_source_class_balanced` của G1.6, mô tả các nhóm lỗi và xuất gói review. Chưa thêm đặc trưng, điều chỉnh ngưỡng, sửa nhãn hoặc kích hoạt model.

## Quy trình

1. Kiểm tra checksum đầu vào, mã G1.6, schema, runtime và đúng dataset nền.
2. Tái tạo train/validation và assignment giống G1.6; kiểm tra sample/domain overlap.
3. Fit lại RF với cùng seed, trọng số bốn ô nguồn × nhãn, 18 đặc trưng và ngưỡng 0.5. Không nạp pickle cũ.
4. Confusion matrix phải khớp chính xác; các chỉ số khác sai số tuyệt đối tối đa 1e-8. Không khớp thì dừng và không công bố gói review.
5. Xuất tất cả FP/FN trên hai nguồn validation, không cắt bớt hoặc tự xác minh nhãn.

Không mở PhiUSIIL test hoặc external holdout JSONL. Đọc CSV primary để đối chiếu development không phải chấm điểm holdout. External reused validation đã được quan sát trước, không phải kiểm thử cuối cùng.

## Chạy trên Windows

Giữ nhánh hiện tại, không sửa các file cũ được ghim hash. Output phải là thư mục mới.

```powershell
.\services\training\.venv\Scripts\python.exe -m unittest discover -s services/training/tests -v
.\services\training\.venv\Scripts\python.exe -m unittest discover -s scripts/g1_4/tests -v

.\services\training\.venv\Scripts\python.exe services/training/diagnose_multisource_errors.py --dataset "E:\BE_NodeJs\phishing-data\processed\phiusiil-url-v1" --external "E:\BE_NodeJs\phishing-data\external\hannousse-provisional-v1" --baseline-run "E:\BE_NodeJs\phishing-models\url-baselines-v1" --primary-file "D:\download\dataset_B_05_2020.csv" --primary-origin mendeley-v3 --experiment-run "E:\BE_NodeJs\phishing-models\multisource-experiment-v1" --output "E:\BE_NodeJs\phishing-data\review\g17-multisource-v1" --workers 2
```

`--primary-origin` ghi lại xác nhận tải trực tiếp từ Mendeley V3 đã cung cấp. Checksum không xác minh độc lập từng nhãn.

## Đầu ra và cách đọc

- `report.json`: kết quả tái lập, thống kê HTTP/HTTPS, path, query, subdomain, IP và chiều dài URL.
- `review-packet/cases.jsonl`: URL defang, source label, đặc trưng hiện có, dự đoán và MODEL_SCORE của các ca sai so với nhãn nguồn.
- `review-packet/decisions-template.jsonl`: các ca đều UNREVIEWED.
- Manifest: hash các file để kiểm tra tính toàn vẹn.

Nhóm lỗi có thể chồng lặp; không cộng số ca giữa các nhóm. FPR phải đọc cùng số negative, recall cùng số positive. null là không có mẫu cho mẫu số đó, không phải tỷ lệ lỗi bằng 0. MODEL_SCORE chưa hiệu chỉnh xác suất.

URL defang vẫn chứa dữ liệu nguồn, có thể có token trong query. Giữ gói review ngoài Git. Bản vá chỉ chứa mã, test và báo cáo tổng hợp; không chứa cases/decisions hoặc model.

## Rà soát bằng chứng

Sao chép template một lần, không ghi đè bản đang làm:

```powershell
Copy-Item "E:\BE_NodeJs\phishing-data\review\g17-multisource-v1\review-packet\decisions-template.jsonl" "E:\BE_NodeJs\phishing-data\review\g17-decisions-v1.jsonl"
```

Mỗi dòng quyết định dùng sample_id để đối chiếu cases. Bắt đầu với FP/FN external ở cả HTTP và HTTPS, rồi xem FN PhiUSIIL để không bỏ qua sự đánh đổi. Phần chưa xem giữ UNREVIEWED.

- CONFIRM_SOURCE hoặc CORRECT_SOURCE: phải có reviewer, reviewed_at (ISO8601 có múi giờ), lý do, evidence_refs và proposed_y phù hợp trạng thái.
- INSUFFICIENT_EVIDENCE: đã xem nhưng thiếu bằng chứng, proposed_y phải null.
- Không lấy dự đoán mô hình, HTTPS, URL dài hoặc từ “login” làm bằng chứng nhãn.
- Nhãn nguồn là lịch sử. Trạng thái website hôm nay không tự xác minh trạng thái khi thu thập; cần chứng cứ có mốc thời gian phù hợp. Không bịa bằng chứng để điền đủ.

Không cần mở trực tiếp URL để mô tả cấu trúc. Kiểm tra bản decisions bằng validator G1.4:

```powershell
.\services\training\.venv\Scripts\python.exe scripts/g1_4/review_errors.py validate --packet "E:\BE_NodeJs\phishing-data\review\g17-multisource-v1\review-packet" --decisions "E:\BE_NodeJs\phishing-data\review\g17-decisions-v1.jsonl" --output "E:\BE_NodeJs\phishing-data\review\g17-decisions-check-v1"
```

Validator kiểm tra cấu trúc, không xác thực danh tính reviewer hoặc nội dung evidence_refs. Đề xuất sửa nhãn không sửa dataset frozen; eligible_for_training vẫn false. Không chuyển validation sang train.

## Bước tiếp theo

Phần kỹ thuật G1.7 hoàn thành khi tái lập và tạo gói thành công. Rà soát bằng chứng là phần riêng chưa hoàn tất nếu reviewed_cases=0. Dùng thống kê để đặt giả thuyết, không suy ra nguyên nhân chỉ từ tương quan. Chốt một số ít thí nghiệm đặc trưng trước khi chạy, giữ split/weight/threshold cố định để so sánh; tiếp tục báo cáo riêng từng nguồn. Không dùng hai tập cuối cùng để chọn đặc trưng/ngưỡng. Không cắt path hoặc chuyển HTTP sang HTTPS để làm đẹp kết quả.

## Kết quả tham chiếu

Bản dựng lại ngày 19/11/2026: 46 test training và 11 test G1.4 đều đạt trên Python 3.12.14. Lần chạy thật tái lập đúng G1.6. Chưa xác nhận chạy G1.7 trên Windows của bạn.

| Nguồn validation | FP | FN | Ca review |
|---|---:|---:|---:|
| PhiUSIIL | 9 | 648 | 657 |
| External reused | 162 | 26 | 188 |
| Tổng | 171 | 674 | 845 |

Tất cả 845 ca UNREVIEWED. Validator xác nhận cấu trúc template, không xác nhận nhãn.

Trên external reused validation: HTTP có FP 118/311 và FN 21/301; HTTPS có FP 44/161 và FN 5/108. Nhóm có query có FP 18/20 (mẫu số nhỏ, chưa đủ kết luận nguyên nhân). URL dài từ 34 ký tự có FP 129/302, dưới 34 có FP 33/170; mốc 34 kế thừa chẩn đoán trước, không được tìm tối ưu ở G1.7. Các nhóm chồng lặp, không cộng chúng với nhau.

Các file reference là metadata tổng hợp. Manifest tham chiếu dùng tên file trong output gốc, không phải tên có tiền tố reference trong docs. Gói review private không nằm trong patch/ZIP.
