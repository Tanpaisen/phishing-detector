# G1.9 — Khảo sát ngưỡng trên điểm validation

Trạng thái: `EXPLORATORY_THRESHOLDS_NOT_FOR_DEPLOYMENT`. Không chọn mô hình triển khai hoặc ngưỡng cảnh báo chính thức.

## Quy trình cố định

1. `collect_url_validation_scores.py` kiểm tra checksum, phiên bản mã, môi trường và manifest G1.6/G1.8. Tái huấn luyện đúng ba cấu hình G1.8 bằng TRAIN, trọng số bốn ô nguồn × nhãn, seed và phép chia miền đã cố định. Tái lập confusion matrix và các chỉ số ở 0,5 cho cả hai nguồn trước khi xuất điểm.
2. Thu điểm của **toàn bộ** 35.188 PhiUSIIL validation và 881 external reused-validation; không chỉ lấy các ca lỗi. Không xuất URL, không sửa nhãn, không tạo model artifact.
3. `analyze_url_thresholds.py` chỉ đọc gói điểm, kiểm tra checksum, số lượng, nhãn, miền không giao nhau và tái lập chỉ số 0,5. Không huấn luyện. Phân tích riêng từng cấu hình theo `protocol.json`.

Các tập external reused-validation đã được quan sát và dùng để phát triển từ các bước trước. Chọn ngưỡng và đo kết quả trên cùng validation tạo thiên lệch lạc quan; đây không phải đánh giá cuối độc lập. Cả hai lệnh không mở PhiUSIIL test hoặc external holdout.

## Quy tắc chọn điểm khảo sát

- Dự đoán dương khi `score >= threshold`. Các mẫu có cùng điểm không bị tách tùy ý.
- Với mỗi cấu hình, tập ứng viên gồm 0, mọi điểm khác nhau của hai nguồn, và `nextafter(max_score, +inf)` để biểu diễn trường hợp không cảnh báo mẫu nào.
- Mức FPR khảo sát: 0,1%, 0,5%, 1%, 2%, 5%. Mỗi nguồn phải có FP không vượt `floor(cap × số mẫu âm)` **riêng biệt**, không gộp nguồn để che khuất lỗi. Phép tính dùng phân số chính xác.
- Chọn ứng viên nhỏ nhất thỏa cả hai nguồn. Recall không tăng khi nâng ngưỡng; quy tắc này giữ recall cao nhất trong tập ứng viên khả thi, nhưng không chứng minh hiệu quả trên dữ liệu mới.
- Xuất thêm điểm tại ngưỡng cố định 0,5; 0,6; 0,7; 0,8; 0,9; 0,95; 0,99.
- Khi không cảnh báo mẫu nào, trạng thái là `NO_POSITIVE_PREDICTIONS_ON_OBSERVED_VALIDATION`, precision là null. Ngưỡng sentinel có thể lớn hơn 1 và được đánh dấu; không làm tròn để dùng trong API.

472 mẫu âm external chỉ cho phép lần lượt 0, 2, 4, 9, 23 FP ở năm mức trên. Một FP tương ứng khoảng 0,212%. Không có FP quan sát được không chứng minh FPR quần thể bằng 0 hoặc dưới 0,1%. Mẫu chung miền phụ thuộc nhau; chưa tính khoảng tin cậy hoặc chốt recall tối thiểu nghiệm thu. Nhãn nguồn là nhãn lịch sử; MODEL_SCORE chưa hiệu chuẩn xác suất.

## Kết quả chạy tham chiếu

| Scenario | FPR cap | Threshold | External FP / 472 | External recall | PhiUSIIL recall |
|---|---:|---:|---:|---:|---:|
| baseline | 1% | 0.96410372 | 4 | 33.74% | 46.77% |
| baseline | 5% | 0.90439131 | 23 | 56.23% | 72.78% |
| baseline_plus_hostname | 1% | 0.97023275 | 4 | 34.23% | 43.48% |
| baseline_plus_hostname | 5% | 0.91527192 | 23 | 52.57% | 71.91% |
| baseline_plus_path_query | 1% | 0.94820717 | 4 | 41.32% | 45.86% |
| baseline_plus_path_query | 5% | 0.88717987 | 23 | 63.33% | 77.28% |

Ở cap 1%, cả ba cấu hình chỉ giữ khoảng 34–41% recall external. Nhánh path/query có recall cao nhất tại hai điểm minh họa, nhưng kết quả này chưa đủ chọn mô hình triển khai. Nâng ngưỡng giảm cảnh báo nhầm đồng thời bỏ sót nhiều phishing; chưa giải quyết được hạn chế dữ liệu và khả năng khái quát. Ở cap 0,1%, baseline và path/query không cảnh báo mẫu nào; hostname còn recall external khoảng 18,34%.

Các ngưỡng trong bảng đã làm tròn để đọc; JSON lưu giá trị đầy đủ. Báo cáo tham chiếu chạy Python 3.12.14; máy Windows của bạn dùng môi trường đã tạo G1.8. Không sửa manifest để bỏ qua kiểm tra môi trường.

## Chạy trên Windows PowerShell

Giữ nguyên nhánh đang làm. Chạy từ `E:\BE_NodeJs\phishing-detector`. Không cần cài thêm thư viện. G1.8 phải đã có mã và kết quả trên máy.

```powershell
git apply --check "D:\download\g1-9-url-threshold-study.patch"
git apply "D:\download\g1-9-url-threshold-study.patch"
.\services\training\.venv\Scripts\python.exe -m unittest discover -s services/training/tests -v
```

Thu điểm (tái huấn luyện ba cấu hình nên mất vài phút):

```powershell
.\services\training\.venv\Scripts\python.exe services/training/collect_url_validation_scores.py `
  --dataset "E:\BE_NodeJs\phishing-data\processed\phiusiil-url-v1" `
  --external "E:\BE_NodeJs\phishing-data\external\hannousse-provisional-v1" `
  --baseline-run "E:\BE_NodeJs\phishing-models\url-baselines-v1" `
  --primary-file "D:\download\dataset_B_05_2020.csv" `
  --primary-origin mendeley-v3 `
  --experiment-run "E:\BE_NodeJs\phishing-models\multisource-experiment-v1" `
  --feature-run "E:\BE_NodeJs\phishing-models\url-feature-experiments-v1" `
  --output "E:\BE_NodeJs\phishing-models\url-validation-scores-v1" `
  --workers 2
```

Sau khi thu điểm thành công:

```powershell
.\services\training\.venv\Scripts\python.exe services/training/analyze_url_thresholds.py `
  --scores "E:\BE_NodeJs\phishing-models\url-validation-scores-v1" `
  --output "E:\BE_NodeJs\phishing-models\url-threshold-study-v1"
```

Mỗi thư mục đầu ra phải chưa tồn tại; chương trình không ghi đè. Nếu cần chạy lại, chọn tên mới cho thư mục và cập nhật đường dẫn bước sau. Lỗi checksum hoặc tái lập phải được điều tra trước khi tiếp tục.

Gửi `E:\BE_NodeJs\phishing-models\url-threshold-study-v1\report.json` để đối chiếu. Gói điểm có sample_id/group_id liên kết dữ liệu nghiên cứu: giữ ngoài Git dù không chứa URL nguyên bản. Chỉ mã, test, protocol và báo cáo tổng hợp tham chiếu thuộc commit.

## Kiểm thử và giới hạn

71 kiểm thử training thành công, gồm 13 kiểm thử mới: FP budget chính xác, điểm bằng ngưỡng, điểm trùng nhau, nguồn riêng biệt, đối chiếu vét cạn, sentinel, dữ liệu không hợp lệ, checksum, tái lập, cấm ghi đè, và luồng không đọc test/holdout hoặc mạng. Chạy tham chiếu thật tái lập đủ sáu kết quả G1.8 và xuất báo cáo ngưỡng.

Chưa đo hiệu năng API, chưa hiệu chuẩn, chưa xét nghiệm thu sản phẩm. G1.9 cung cấp bằng chứng định lượng để quyết định bước nghiên cứu kế tiếp; không tự mở tập kiểm thử cuối hoặc kích hoạt mô hình.
