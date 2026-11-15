# G1.4 — Rà soát lỗi và chuẩn bị nguồn đánh giá bổ sung

Gói này có hai công cụ: tạo hồ sơ rà soát lỗi G1.3 và chuẩn bị một cohort URL nguồn khác.
Không đổi nhãn/bộ chia G1.1, không fit model, không chỉnh threshold, không suy luận final test.
Tiếp tục trên nhánh làm việc hiện có; không tạo nhánh mới. Không sửa các tệp đã được ghi hash
trong manifest G1.1/G1.2/G1.3. Dùng venv training đang chạy được G1.3; không thêm dependency.

## 1. Trạng thái nguồn bổ sung — cần đọc trước

Nguồn dự kiến: **Web page phishing detection**, Abdelhakim Hannousse và Salima Yahiouche,
Mendeley Data V3, DOI [10.17632/c2gw7fy2j4.3](https://data.mendeley.com/datasets/c2gw7fy2j4/3).
Trang tác giả công bố11.430URL cân bằng hai lớp, thu thập tháng5/2020 và giấy phép CC BY4.0.
Dự án chỉ lấy URL và status, không dùng các đặc trưng HTML/DNS/statistics đã tính sẵn.

Đường tải trực tiếp Mendeley trả HTTP403 trong môi trường chuẩn bị. Bản đang audit là bản sao
ở repository mnnsolanki/webpage-phishing-detection, cố định commit/hash trong source-lock.json.
Repository đó dẫn nguồn Mendeley, nhưng chưa xác minh nội dung bản sao khớp bản gốc.
Không dùng số hàng/nhãn giống nhau để khẳng định hai bản giống nhau.

Vì vậy trạng thái luôn là **PROVISIONAL_NOT_APPROVED_FOR_EVALUATION**. Hash xác định snapshot,
không chứng minh nguồn gốc hay nhãn đúng. Gói không có lệnh chấm điểm model trên nguồn này,
không tự chuyển thành dữ liệu đã duyệt hoặc dữ liệu huấn luyện. Giấy phép ghi trong lock là
công bố của nguồn gốc, không phải kết luận đã xác minh mọi tệp của bên sao chép.

Nguồn lịch sử này không chứng minh website đang hoạt động hoặc giữ nguyên trạng thái hôm nay.
Chủ thể/chiến dịch hoặc nguồn thu thập ban đầu vẫn có thể trùng với PhiUSIIL. Phải phân biệt
“nguồn công bố khác” với “hoàn toàn độc lập về chiến dịch, thời gian và nguồn gốc”.

## 2. Kiểm thử

Chạy từ thư mục gốc dự án:

```powershell
.\services\training\.venv\Scripts\python.exe -m unittest discover -s scripts/g1_4/tests -v
```

Mong đợi11kiểm thử mới đạt. Bộ18kiểm thử training cũ nằm ở services/training/tests và không
bị thay đổi. Tất cả đọc/ghi văn bản dùng UTF-8; không tự mở URL đích hay phân giải DNS.

## 3. Tạo hồ sơ rà soát lỗi G1.3

```powershell
.\services\training\.venv\Scripts\python.exe scripts/g1_4/review_errors.py export --dataset "E:\BE_NodeJs\phishing-data\processed\phiusiil-url-v1" --diagnostics "E:\BE_NodeJs\phishing-models\url-diagnostics-v1" --output "E:\BE_NodeJs\phishing-data\review\g13-errors-v1"
```

Script kiểm manifest/hash và đối chiếu mã mẫu, nhãn, số bản ghi của lỗi với validation.
Các dòng cùng sample_id được gộp, giữ kết quả của cả hai model. Với dữ liệu tham chiếu:
217dòng thành128mẫu duy nhất (15mẫu FP,113mẫu FN), tất cả chưa kiểm duyệt. Đây không phải
mọi lỗi của hai model vì G1.3 giới hạn100FN/model. Không chọn lại mẫu để lấy số đẹp.

| Tệp hồ sơ | Công dụng |
|---|---|
| cases.jsonl | URL hiển thị dạng hxxp/hxxps và [.] để tránh bấm nhầm; nhãn nguồn và lỗi model |
| decisions-template.jsonl | Một quyết định UNREVIEWED cho mỗi mẫu |
| summary.json | Số dòng, số mẫu và trạng thái |
| manifest.json | Hash tệp, dataset và chẩn đoán nguồn |

URL đã làm mất tính liên kết vẫn chứa dữ liệu nguồn: giữ cả hồ sơ ở vùng riêng, không đưa
lên Git/chat công khai. Dùng trình soạn thảo văn bản; không nhập JSONL vào bảng tính tự xử lý
công thức. Công cụ không mở website. Trước mắt ưu tiên15mẫu FP và ghi bằng chứng lịch sử
hoặc nguồn độc lập; không suy ra “lành tính” chỉ từ HTTPS hay “phishing” chỉ từ hình thức URL.

Sao chép template trước khi chỉnh, không sửa tệp trong manifest gốc:

```powershell
Copy-Item "E:\BE_NodeJs\phishing-data\review\g13-errors-v1\decisions-template.jsonl" "E:\BE_NodeJs\phishing-data\review\g13-decisions-v1.jsonl"
```

Mỗi dòng giữ sample_id; các trường cho phép:

| status | proposed_y | Điều kiện |
|---|---|---|
| UNREVIEWED | null | Giữ nguyên các trường trống như template |
| CONFIRM_SOURCE | 0 hoặc1, bằng nhãn nguồn | Người duyệt, ngày có múi giờ, lý do, tham chiếu bằng chứng |
| CORRECT_SOURCE | 0 hoặc1, khác nhãn nguồn | Người duyệt, ngày có múi giờ, lý do, tham chiếu bằng chứng |
| INSUFFICIENT_EVIDENCE | null | Người duyệt, ngày, lý do thiếu căn cứ; không ép gán nhãn |

Quy ước0=legitimate,1=phishing. reviewer là mã/tên người thực sự rà soát; reviewed_at là
ISO8601 có múi giờ. evidence_refs là danh sách mã/tệp/nguồn bằng chứng để kiểm lại, không
phải danh sách được script tự tải hoặc tự xác minh. reason ít nhất10ký tự. Không điền dữ liệu
minh họa để làm báo cáo “đã duyệt”. Giữ UNREVIEWED cho mọi mẫu chưa làm.

```powershell
.\services\training\.venv\Scripts\python.exe scripts/g1_4/review_errors.py validate --packet "E:\BE_NodeJs\phishing-data\review\g13-errors-v1" --decisions "E:\BE_NodeJs\phishing-data\review\g13-decisions-v1.jsonl" --output "E:\BE_NodeJs\phishing-data\review\g13-review-check-v1"
```

Lệnh tạo snapshot quyết định, summary, proposed-label-changes và manifest. Kiểm cấu trúc
thành công không xác thực danh tính người duyệt, sự thật của bằng chứng hoặc quyền quản trị.
Ngay cả CORRECT_SOURCE hợp lệ cũng chỉ là đề xuất: eligible_for_training=false; không sửa
frozen labels và không đưa validation trở lại train. Quản trị/phê duyệt DB vẫn là bước sau.

## 4. Tải và chuẩn bị bản sao nguồn bổ sung

```powershell
.\services\training\.venv\Scripts\python.exe scripts/g1_4/external_urls.py download --output "E:\BE_NodeJs\phishing-data\raw\hannousse-mirror-v1"
```

Chỉ tải URL bản sao đã pin, giới hạn16MiB và kiểm SHA256. Không tải URL chứa trong CSV.
Lỗi mạng/checksum phải dừng, không sửa lock để ép thông qua.

```powershell
.\services\training\.venv\Scripts\python.exe scripts/g1_4/external_urls.py prepare --source "E:\BE_NodeJs\phishing-data\raw\hannousse-mirror-v1\hannousse.csv" --dataset "E:\BE_NodeJs\phishing-data\processed\phiusiil-url-v1" --base-source "E:\BE_NodeJs\phishing-data\raw\phiusiil\phiusiil.csv" --output "E:\BE_NodeJs\phishing-data\external\hannousse-provisional-v1"
```

Bước lập chỉ mục loại trừ có thể mất vài phút. Nó đọc **cột URL của CSV PhiUSIIL gốc đã
kiểm checksum**, dựng toàn bộ nhóm miền/IP nguồn cũ. Không mở test.jsonl, không chạy model
và không thống kê metric dự đoán test. Cách này loại trùng với cả train/validation/test mà
không sử dụng nhãn/kết quả test để điều chỉnh mô hình. Chỉ mục là tập bao phủ rộng hơn bộ
clean, vì bao gồm mọi URL nguồn cũ parser chấp nhận, kể cả bản trùng.

Pipeline nguồn mới:

1. Kiểm hash/schema/nhãn; dùng parser hiện có, không sửa URL để ép hợp lệ.
2. Cách ly toàn bộ nhóm normalized_url có nhãn mâu thuẫn.
3. Loại URL canonical hoặc miền đăng ký/IP từng có trong nguồn PhiUSIIL.
4. Bỏ bản dư cùng canonical URL và nhãn; giữ input gốc nhỏ nhất theo thứ tự Unicode rồi record.
5. Chia theo group_id: SHA256("external-url-role-v1:"+group_id) modulo100 <50 vào development,
   phần còn lại holdout. Đây là phân chia xác định, không dùng nhãn/điểm mô hình để chọn nhóm.
   Tỷ lệ chỉ xấp xỉ50/50; cả hai phần phải có đủ hai lớp, nếu không thì dừng.
6. Ghi số bị loại theo lý do/nhãn, tổng hạch toán và độ bao phủ nhóm cần kiểm tra.

Không có train mới ở đây. Development dành cho phân tích/phát triển sau khi duyệt nguồn;
holdout dự trữ cho đánh giá đã chốt phương pháp. Chỉ thống kê cấu trúc/lớp lúc chuẩn bị,
không chấm điểm holdout. Không gộp holdout vào development sau khi xem kết quả model.
Nhóm URL “dài” trong báo cáo là >=34ký tự, mốc đã lấy từ train G1.3, không phải định nghĩa
URL dài phổ quát. Bản sao vẫn provisional dù mọi kiểm tra cấu trúc đều đạt.

Các tệp development.jsonl, holdout.jsonl chứa URL gốc/chuẩn hóa và nhãn nguồn; lưu riêng.
exclusions/duplicates chỉ ghi định danh và lý do. report.json là metadata có thể gửi đối chiếu.
Tất cả lệnh yêu cầu output mới, không ghi đè để giữ dấu vết phiên bản.

## 5. Đối chiếu với nguồn gốc

Khi tải được **dataset_B_05_2020.csv** từ trang Mendeley V3 đã dẫn ở trên, chạy:

```powershell
.\services\training\.venv\Scripts\python.exe scripts/g1_4/external_urls.py compare-primary --primary "D:\download\dataset_B_05_2020.csv" --mirror "E:\BE_NodeJs\phishing-data\raw\hannousse-mirror-v1\hannousse.csv" --output "E:\BE_NodeJs\phishing-data\external\hannousse-primary-comparison-v1"
```

So sánh multiset cặp URL/nhãn, giữ số lần trùng, bỏ qua thứ tự hàng và87đặc trưng không dùng.
Khớp nội dung không tự chứng minh tệp được lấy từ Mendeley: phải ghi nguồn và quá trình nhận
bản gốc. Không tự nâng trạng thái bộ dữ liệu. Nếu khác, không sửa CSV/hash hiện tại; ghi phiên
bản mới và phân tích khác biệt. Không yêu cầu đăng nhập/tài khoản từ pipeline này.

## 6. Việc đã làm và còn lại

Đã có mã nhập nguồn, lọc trùng, chia vai trò, xuất hồ sơ lỗi, kiểm quyết định và kiểm thử.
Đã chạy với nguồn bản sao và G1.1/G1.3 tham chiếu trong môi trường Linux/Python3.12.
Chưa có kết quả chạy Windows của gói này, chưa đối chiếu nguồn gốc, chưa kiểm duyệt thủ công,
chưa đánh giá model trên nguồn bổ sung, chưa calibration hoặc chọn ngưỡng triển khai.
Vì vậy hoàn thành **công cụ/chuẩn bị G1.4** không có nghĩa dữ liệu đánh giá đã được phê duyệt.

## 7. Số liệu tham chiếu sau lọc

| Bước | Số hàng |
|---|---:|
| Bản sao đầu vào | 11430 |
| URL parser từ chối | 11 |
| Trùng canonical URL nguồn PhiUSIIL | 44 |
| Còn lại trùng miền nguồn PhiUSIIL | 2089 |
| Bản dư cùng URL/nhãn trong phần còn lại | 1 |
| Giữ lại | 9285 |

Không có nhóm nhãn mâu thuẫn trong snapshot này. Development4572mẫu (2253legitimate,
2319phishing), holdout4713mẫu (2265legitimate,2448phishing); nhóm miền không giao nhau.
Các số dưới đây là độ bao phủ theo nhãn nguồn, chưa phải nhãn đã xác minh độc lập:

| Nhóm | Development | Holdout dự trữ |
|---|---:|---:|
| HTTP legitimate | 1278 | 1194 |
| HTTPS phishing | 619 | 758 |
| Legitimate có độ dài >=34 | 1335 | 1335 |

Các nhóm có thể chồng lặp nên không cộng thành tổng. Loại trùng với nguồn cũ cũng tạo
selection bias; xem lý do bị loại theo nhãn ở reference-external-report.json. Không có
metric model trên cohort này. Đây là cohort tạm thời, không phải dữ liệu đánh giá đã được phê duyệt.
