# G1.3 — Phân tích đặc trưng và lỗi của baseline URL

Gói này bổ sung chẩn đoán, không thay thế model G1.2, không chỉnh ngưỡng0,5, không mở
final test và không kích hoạt model trong API. Dùng lại môi trường training G1.2.

## Phạm vi đã triển khai

1. Kiểm checksum/runtime/mã/manifest để xác nhận dataset và baseline đúng phiên bản.
2. Trích đặc trưng train/validation bằng đúng module shared; không đọc test.jsonl.
3. Huấn luyện lại LR và RF với cấu hình G1.2, chỉ fit trên train. Full model phải tái lập
   confusion matrix và Average Precision của baseline (sai số tuyệt đối AP tối đa1e-8).
4. Tính permutation importance trên validation theo AP:18đặc trưng đơn và2nhóm, mỗi nhóm3lần.
5. Chạy ablation: đầy đủ; bỏ HTTPS; bỏ nhóm độ dài; bỏ cả HTTPS và nhóm độ dài. Tổng8lần fit.
6. Phân tích FP/FN theo HTTPS, IP và bốn khoảng độ dài có mốc phân vị lấy từ train.
7. Xuất báo cáo tổng hợp và danh sách mẫu lỗi để rà soát riêng tại máy người dùng.

Không load joblib/pickle, không thay hoặc ghi đè model cũ. Baseline-run chỉ cung cấp báo cáo
và manifest để đối chiếu. Model chẩn đoán được fit lại và không lưu thành model ứng dụng.

## Cách diễn giải

Permutation: hoán đổi hàng của cột đặc trưng rồi đo AP giảm bao nhiêu, giữ nguyên model.
Với nhóm nhiều cột, dùng cùng một hoán vị cho mọi cột trong nhóm. Đây là mức phụ thuộc của
model trên tập đang xét, không phải xác minh nguyên nhân phishing hay SHAP từng mẫu.
`shuffle_std` mô tả biến thiên giữa3hoán vị, không phải khoảng tin cậy thống kê.
AP drop âm có thể xảy ra; không ép thành0. Đặc trưng tương quan có thể che ảnh hưởng của nhau;
hoán vị cũng có thể tạo tổ hợp đặc trưng không giống URL thực tế.

Ablation: loại cột khỏi cả train và validation rồi fit model mới, giữ các tham số còn lại.
Nhóm độ dài gồm url_length, hostname_length, path_length, query_length, fragment_length.
Các biến đếm dấu/chữ số còn lại vẫn có thể tương quan với độ dài. Vì vậy bỏ nhóm độ dài
không đồng nghĩa loại hết mọi thông tin có liên quan tới độ dài.

Metrics của ablation vẫn dùng ngưỡng0,5 cố định; model mới có phân bố score khác. Cần xem
cả AP liên tục và confusion matrix, không quy toàn bộ thay đổi recall cho chất lượng xếp hạng.
Không tự chọn cấu hình mới chỉ vì ít FP hơn hoặc AP tốt hơn trong báo cáo khám phá này.

Nguồn phương pháp: [scikit-learn — Permutation feature importance](https://scikit-learn.org/stable/modules/permutation_importance.html).

## Chạy trên Windows

Sau khi áp dụng patch, tại `E:\BE_NodeJs\phishing-detector`:

```powershell
.\services\training\.venv\Scripts\python.exe -m unittest discover -s services/training/tests -v
```

Mong đợi18kiểm thử đạt (11kiểm thử G1.2 +7kiểm thử mới). Không cần cài thêm thư viện.

```powershell
.\services\training\.venv\Scripts\python.exe services/training/diagnose_url_baselines.py --dataset "E:\BE_NodeJs\phishing-data\processed\phiusiil-url-v1" --baseline-run "E:\BE_NodeJs\phishing-models\url-baselines-v1" --output "E:\BE_NodeJs\phishing-models\url-diagnostics-v1" --workers 2
```

Có tiến độ trích đặc trưng mỗi25000mẫu và thông báo từng lần fit. Giữ cùng venv training
đã tạo baseline. Nếu runtime/checksum/reproduction khác thì dừng; không sửa manifest cũ để
bỏ qua kiểm tra. Không ghi đè output đã tồn tại. Không chạy hai tiến trình cùng output.

Kết quả thành công có `status: DIAGNOSTICS_ONLY`, `final_test_opened: false`.
Mở báo cáo bằng PowerShell:

```powershell
Get-Content "E:\BE_NodeJs\phishing-models\url-diagnostics-v1\report.json" -Raw -Encoding UTF8
```

| Tệp | Nội dung |
|---|---|
| report.json | Metrics8cấu hình, permutation, các nhóm lỗi, runtime và giới hạn |
| error-review.jsonl | Mã mẫu, mã nhóm, source_record, nhãn nguồn, score và loại lỗi; không có URL thô |
| manifest.json | Hash báo cáo, mã chẩn đoán, manifest nguồn và baseline |

Dữ liệu ở ngoài repository. Có thể gửi report.json để đối chiếu. Không đưa CSV/URL/mẫu lỗi
vào Git công khai. sample_id/group_id là hash định danh, không phải bảo đảm ẩn danh.

## Rà soát lỗi thủ công

Chỉ lấy lỗi của full models, tối đa100FP và100FN cho mỗi model. Ưu tiên FP có score cao,
FN có score thấp; cùng điểm thì sắp theo sample_id. Đây là danh sách để điều tra, không phải
mẫu ngẫu nhiên đại diện toàn bộ lỗi. Cùng một mẫu có thể xuất hiện ở hai model.
Các lỗi ngoài danh sách vẫn được tính đầy đủ trong confusion matrix và các bảng nhóm.

source_record là số bản ghi dữ liệu CSV gốc, bắt đầu1, không phải số dòng vật lý (CSV có thể
chứa nội dung xuống dòng). Đối chiếu sample_id với validation.jsonl trong vùng dữ liệu riêng;
không mở website đích chỉ để xem lỗi. Nguồn chưa chắc gán nhãn đúng cho mọi mẫu. Ghi nhận
quyết định và bằng chứng riêng; không tự đổi nhãn hoặc đưa mẫu validation đã sửa vào train.
Gói này tạo danh sách UNREVIEWED; chưa thực hiện kiểm duyệt thủ công từng mẫu.

Các nhóm độ dài dùng `searchsorted(edges, length, side='right')`: nhóm0 nhỏ hơn mốc1,
nhóm1 từ mốc1 tới nhỏ hơn mốc2, nhóm2 từ mốc2 tới nhỏ hơn mốc3, nhóm3 từ mốc3 trở lên.
Nếu thiếu một lớp trong nhóm, metric có mẫu số bằng0 là null, không được hiểu là FPR0.
Số nhóm miền ở các lát cắt không cộng được thành tổng vì một miền có thể xuất hiện ở nhiều lát.

## Kết quả tham chiếu

Chạy đầy đủ trên train164210 / validation35188, Python3.12.14, cùng cấu hình G1.2.
Hai full models tái lập confusion matrix G1.2. Các số dưới đây thuộc validation, chưa phải test cuối.

| RF | Average Precision | Recall ở0,5 | FP | FN |
|---|---:|---:|---:|---:|
| Full18đặc trưng | 0,998135 | 99,14% | 10 | 129 |
| Bỏ HTTPS | 0,996375 | 92,53% | 49 | 1117 |
| Bỏ nhóm độ dài | 0,997038 | 99,03% | 4 | 145 |
| Bỏ HTTPS và độ dài | 0,870633 | 73,46% | 738 | 3970 |

AP giảm ít nhưng recall giảm đáng kể khi RF bỏ HTTPS: ngưỡng0,5 cũng tác động, không chỉ
khả năng xếp hạng. Không kết luận một mô hình tốt hơn mọi mặt từ một metric.

Phân bố validation đáng chú ý:

- HTTPS:20228mẫu legitimate và7608mẫu phishing theo nhãn nguồn.
- HTTP:0mẫu legitimate và7352mẫu phishing. Vì không có negative HTTP nên không đo được
  FPR cho HTTP trên tập này, dù không có FP được quan sát.
- IP:0mẫu legitimate và34mẫu phishing; cũng không đủ để đánh giá false positive với IP hợp lệ.
- Cả129FN và10FP của RF đều thuộc HTTPS.9/10FP nằm ở khoảng độ dài cao nhất.

Permutation full RF: AP giảm trung bình khoảng0,1120 khi đảo is_https và0,2310 khi đảo
đồng thời HTTPS+nhóm độ dài. Đây là bằng chứng model phụ thuộc vào các tín hiệu này trên
snapshot, không chứng minh các tín hiệu đó không hữu ích hay model chắc chắn thất bại ngoài nguồn.

Danh sách rà soát có217dòng:7FP+100FN của LR,10FP+100FN của RF; không phải217mẫu duy nhất,
không phải toàn bộ lỗi, và chưa được kiểm duyệt. Không đóng gói danh sách này trong patch.

## Quyết định sau chẩn đoán

Tiếp tục giữ model là candidate. Trước khi chốt ngưỡng cho triển khai, cần tập kiểm tra bổ sung
có nguồn/nhãn hợp lệ, bao phủ HTTP lành tính, HTTPS phishing, URL dài hợp lệ và miền mới.
Không tự thêm URL giả rồi coi nhãn tự gán là bằng chứng thực nghiệm. Tập bổ sung phải kiểm
chồng lặp/domain/campaign và tách vai trò development/evaluation rõ ràng.

Có thể tiếp tục thiết kế calibration và policy trên phần development, nhưng calibration không
sửa được thiếu bao phủ dữ liệu. Validation đã dùng chọn model và phân tích nhiều lần nên
không phải đánh giá độc lập. Chốt lựa chọn, ngưỡng và quy trình trước khi mở final test một lần;
không dùng test để tối ưu tiếp. Chưa có thay đổi phạm vi SMS/QR hoặc database trong G1.3.
