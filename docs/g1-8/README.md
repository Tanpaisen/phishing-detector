# G1.8 — Thí nghiệm đặc trưng URL theo nhóm

## Câu hỏi và phạm vi

Sau G1.7, cần kiểm tra liệu biểu diễn hostname hoặc path/query chi tiết hơn có giảm cảnh báo nhầm mà không làm tăng bỏ sót quá mức hay không. Các giả thuyết được gợi ý bởi validation đã quan sát, không phải bằng chứng về nguyên nhân gây lỗi. Đây là nghiên cứu trên nhãn lịch sử; chưa xác minh độc lập nhãn của 845 ca review.

`protocol.json` được chốt trước lần chạy G1.8. Không tìm thêm seed, ngưỡng, siêu tham số hoặc tổ hợp A+B sau khi thấy kết quả. Nếu cần thí nghiệm khác phải ghi thành phiên bản/thí nghiệm mới và công bố cả kết quả bất lợi.

| Phương án | Đặc trưng | Số cột |
|---|---|---:|
| baseline | 18 đặc trưng G1.2 | 18 |
| baseline_plus_hostname | baseline + nhóm A | 23 |
| baseline_plus_path_query | baseline + nhóm B | 23 |

Mọi phương án dùng Random Forest của G1.6: 100 cây, max_depth=16, min_samples_leaf=2, max_features=sqrt, seed=42, class_weight=None; trọng số bốn ô nguồn × nhãn có tổng N/4 mỗi ô, chỉ tính trên train. Ngưỡng cố định 0.5. Với 18 hoặc 23 cột, số đặc trưng xét ở mỗi split là 4; script ghi nhận giá trị thực tế từ cây đã fit.

Không dùng source ID, nhãn, group ID, URL dạng chuỗi hay thống kê suy ra từ validation làm cột mô hình. Không thay dữ liệu, thêm nhãn từ review hoặc cập nhật API.

## Định nghĩa nhóm A — hostname

Tên miền dùng ASCII IDNA và PSL của inspector đã đóng băng. Với IP, cả 5 đặc trưng mới bằng 0; cột is_ip cũ vẫn giữ nguyên.

1. `has_www_subdomain`: nhãn đầu của phần subdomain theo PSL có đúng là www không. Không chỉ kiểm tra hostname bắt đầu bằng www, vì www có thể thuộc registered domain.
2. `non_www_subdomain_depth`: số nhãn subdomain không rỗng sau khi bỏ đúng một nhãn www ở đầu, nếu có. Không bỏ www ở giữa.
3. `max_hostname_label_length`: độ dài lớn nhất trong các nhãn hostname ASCII không rỗng.
4. `hostname_digit_ratio`: số chữ số ASCII 0–9 chia độ dài hostname ASCII, bao gồm dấu chấm trong mẫu số.
5. `hostname_hyphen_ratio`: số dấu '-' chia cùng mẫu số.

Punycode có thể ảnh hưởng tỷ lệ ký tự; đây không phải bộ xác minh giả mạo thương hiệu. Không bỏ www khỏi URL gốc, không biến đổi miền để tạo mẫu mới.

## Định nghĩa nhóm B — path/query

Dùng path/query từ chuỗi đầu vào gốc sau khi bỏ khoảng trắng ASCII ngoài cùng theo quy ước cũ. Không giải mã percent, không chuẩn hóa Unicode, không đưa fragment vào các cột mới.

1. `path_segment_count`: số đoạn path không rỗng khi tách bằng '/'.
2. `path_max_segment_length`: độ dài lớn nhất của một đoạn, tính theo Unicode code point; không có đoạn thì 0.
3. `query_field_count`: số phần không rỗng khi tách query bằng '&'; tính cả flag, khóa lặp và trường có giá trị rỗng. Dấu ';' không phân cách trường.
4. `path_percent_encoded_ratio`: 3 × số chuỗi %HH hợp lệ / độ dài path gốc.
5. `query_percent_encoded_ratio`: tương tự cho query.

Thành phần rỗng cho tỷ lệ 0. `%2F` không tạo đoạn path mới, `%26` không tạo trường query mới. Ví dụ `/a//b%2Fc/` có 2 đoạn không rỗng; `x=%26&flag&x=2&&` có 3 trường. Không tự sửa URL để làm đẹp phân loại.

## Kiểm soát thí nghiệm

- Giữ nguyên train/validation PhiUSIIL và assignment external train/reused validation G1.6.
- Kiểm tra checksum, môi trường, code G1.6, fingerprint/group và trùng miền/sample trước fit.
- Tái lập baseline trước hai phương án mới: confusion matrix phải khớp chính xác trên cả hai nguồn, chỉ số khác sai số tối đa tuyệt đối 1e-8. Không khớp thì không chạy tiếp hoặc công bố kết quả.
- Không mở test.jsonl, holdout.jsonl, cases.jsonl hoặc decisions để fit. CSV primary chỉ dùng đối chiếu development, không chấm điểm holdout.
- Báo cáo riêng hai nguồn: FPR, recall, precision, AP, ROC AUC, confusion matrix và nhóm cấu trúc.
- `paired_changes_vs_baseline` đếm FP/FN được sửa và FP/FN mới phát sinh trên đúng cùng các hàng validation. Đây vẫn là bất đồng với nhãn nguồn, không phải xác minh độc lập website.
- Không tự chọn winner, không xuất/kích hoạt model và không gọi score là xác suất đã hiệu chỉnh.

## Chạy trên Windows

Giữ nhánh hiện tại `feat/url-baselines-g1-2`. Không sửa các module cũ được ghim hash; bản vá chỉ thêm file.

```powershell
.\services\training\.venv\Scripts\python.exe -m unittest discover -s services/training/tests -v

.\services\training\.venv\Scripts\python.exe services/training/train_url_feature_experiments.py --dataset "E:\BE_NodeJs\phishing-data\processed\phiusiil-url-v1" --external "E:\BE_NodeJs\phishing-data\external\hannousse-provisional-v1" --baseline-run "E:\BE_NodeJs\phishing-models\url-baselines-v1" --primary-file "D:\download\dataset_B_05_2020.csv" --primary-origin mendeley-v3 --experiment-run "E:\BE_NodeJs\phishing-models\multisource-experiment-v1" --output "E:\BE_NodeJs\phishing-models\url-feature-experiments-v1" --workers 2
```

Output phải chưa tồn tại. Dùng môi trường training đã chạy G1.6, không cần thêm dependency. `--primary-origin` ghi nhận xác nhận nguồn tải đã cung cấp. Model G1.2 không bị nạp pickle hoặc thay đổi; baseline-run dùng kiểm tra thông tin liên quan.

Kết quả nằm trong `report.json`, `protocol.json`, `manifest.json`. Không xuất URL gốc hoặc mô hình. Báo cáo tham chiếu chạy Python 3.12.14; cần chạy trên Python 3.14.8 của bạn để xác nhận Windows. Manifest tham chiếu chứa tên file output gốc, không phải tên có tiền tố reference trong docs.

## Giới hạn kết luận

Validation đã được xem nhiều lần và giả thuyết xuất phát từ các lỗi đó, nên không coi đây là test khách quan. Chỉ một seed, chưa có khoảng bất định. Mọi cải thiện cần đọc cùng mức tăng/giảm recall và theo từng nguồn. Không suy rộng FPR trên tập cân bằng này thành rủi ro ngoài thực tế. Hai tập cuối cùng tiếp tục giữ nguyên, chưa dùng để chọn đặc trưng, ngưỡng hay mô hình.

## Kết quả tham chiếu — 21/11/2026

58 test training đều đạt. Lần chạy thật tái lập đúng baseline G1.6 trước khi thử hai nhóm mới. Cả ba mô hình xét 4 đặc trưng tại mỗi split.

| Phương án | External FP | External FN | External FPR | External recall | PhiUSIIL FP | PhiUSIIL FN |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 162 | 26 | 34.32% | 93.64% | 9 | 648 |
| baseline_plus_hostname | 167 | 20 | 35.38% | 95.11% | 2 | 306 |
| baseline_plus_path_query | 174 | 22 | 36.86% | 94.62% | 10 | 636 |

Cả hai nhóm mới đều không đạt mục tiêu giảm cảnh báo nhầm external tại ngưỡng cố định 0.5 trong lần chạy này. Nhóm A tăng recall external nhưng FP tăng 5; nhóm B FP tăng 12. Không kết luận khác biệt nhỏ là có ý nghĩa thống kê, vì chưa có khoảng bất định/đa seed.

Nhóm A trên external sửa được 31 FP nhưng phát sinh 36 FP mới; sửa 16 FN và phát sinh 10 FN mới. Trên PhiUSIIL, nhóm A giảm FN từ 648 xuống 306 và FP từ 9 xuống 2. Vì vậy không thể mô tả bằng một điểm tổng hoặc khẳng định tốt hơn trên mọi nguồn.

ROC AUC external: baseline 0.9108, nhóm A 0.9189, nhóm B 0.9204. Khả năng xếp hạng và hành vi tại ngưỡng 0.5 là hai khía cạnh khác nhau; AUC tăng không làm tỷ lệ cảnh báo nhầm hiện tại trở nên chấp nhận được. Không tự chỉnh ngưỡng sau khi thấy các số này trong cùng thí nghiệm.

Kết luận của G1.8 là kết quả thí nghiệm, không phải release. Giữ toàn bộ kết quả và nhãn cũ; chưa ghép A+B hoặc kích hoạt model. Nếu nghiên cứu ngưỡng tiếp theo, cần chốt trước mục tiêu FPR/recall và cách chọn ngưỡng trên dữ liệu phát triển, tuyệt đối không chọn bằng test/holdout.
