# G1.1 — Làm sạch và chia tập URL theo miền

Phạm vi: tạo dataset URL có thể tái lập từ snapshot PhiUSIIL đã audit ở G0. Chưa huấn luyện
mô hình, chưa chọn ngưỡng, chưa thay đổi API đang chạy. Không có thao tác mở URL đích,
DNS hay redirect của các URL trong CSV. Script download chỉ tải archive nguồn UCI.

## Quyết định dữ liệu

- Chỉ đọc URL và label cho pipeline; bỏ qua đặc trưng HTML, thống kê và thông tin nhãn có sẵn khác.
- Nhãn PhiUSIIL 0 → y=1 PHISHING; nhãn 1 → y=0 LEGITIMATE. Đây là nhãn nguồn,
  không phải kết quả xác minh độc lập của dự án.
- Dùng chính `services/ai/url_analysis.py` hiện có, không tạo một bản parser khác.
- Giữ case path/query/fragment, Unicode theo chính sách parser. Không lowercase cả URL.
- Loại bản dư theo normalized_url; nếu cùng normalized_url có cả hai nhãn, cách ly toàn bộ nhóm.
- Nếu nhiều biểu diễn tương đương cùng nhãn, giữ biểu diễn input_url nhỏ nhất theo thứ tự Unicode,
  rồi source_record nhỏ nhất khi trùng hoàn toàn. Giữ input_url để sau này trích đặc trưng Unicode
  và độ dài giống runtime; không coi normalized_url là input thay thế trong mọi đặc trưng.
- Nhóm theo registered_domain, có private suffix; IP theo địa chỉ canonical. Subdomain khác nhau
  của cùng miền vào cùng tập. Hai tenant khác nhau trên blogspot.com được coi là hai miền riêng.
- Seed42, đích70/15/15 theo số mẫu. Nhóm lớn xếp trước; hòa thứ tự bằng SHA-256(seed:group_id).
  Greedy chọn tập có mức tăng nhỏ nhất của tổng sai số bình phương số mẫu mỗi lớp, chia cho
  mục tiêu lớp tương ứng. Không thử nhiều seed rồi chọn kết quả có metric đẹp.
- Tất cả tập phải có cả hai lớp. Không đủ nhóm thì dừng; không tách miền để ép đạt tỷ lệ.
  Lệch tỷ lệ hơn2 điểm phần trăm được cảnh báo, cần xem lại phân bố nhóm trước huấn luyện.

## Cài và chạy trên Windows

Từ thư mục gốc `E:\BE_NodeJs\phishing-detector`, dùng venv AI đã chạy được URL inspection:

```powershell
.\services\ai\.venv\Scripts\python.exe -m unittest discover -s scripts/g1/tests -v
```

Không cần pandas/scikit-learn trong G1.1. Script dùng thư viện chuẩn Python và idna/tldextract
đã cài cho AI. Nếu thiếu dependency, dùng requirements của AI đã chốt; không tự đổi version
idna/tldextract/PSL để vượt qua kiểm tra nguồn.

Tải đúng nguồn và xác minh cả checksum ZIP lẫn CSV:

```powershell
.\services\ai\.venv\Scripts\python.exe scripts/g1/download_source.py --output-dir "E:\BE_NodeJs\phishing-data\raw\phiusiil"
```

Lần đầu cần internet và tải khoảng vài chục MB. Lần sau, nếu CSV đã đúng checksum thì dùng lại.
Nguồn tải lỗi/checksum khác thì dừng và gửi thông báo lỗi; không sửa source-lock.json để bỏ qua.
Script không giải nén tùy ý đường dẫn trong ZIP. Chỉ nhận đúng một CSV, giới hạn128MiB và kiểm hash.

Chuẩn bị dữ liệu (offline, có thể mất vài phút):

```powershell
.\services\ai\.venv\Scripts\python.exe scripts/g1/prepare_urls.py prepare --input "E:\BE_NodeJs\phishing-data\raw\phiusiil\phiusiil.csv" --output "E:\BE_NodeJs\phishing-data\processed\phiusiil-url-v1"
```

Kiểm tra lại dữ liệu đã ghi:

```powershell
.\services\ai\.venv\Scripts\python.exe scripts/g1/prepare_urls.py verify --dataset "E:\BE_NodeJs\phishing-data\processed\phiusiil-url-v1"
```

Không ghi đè thư mục output đã tồn tại. Nếu chỉ muốn kiểm tra lần chạy cũ, dùng `verify`.
Khi thay thuật toán/parser/source, tạo phiên bản và thư mục mới, không thay dữ liệu của một
thí nghiệm đã công bố. Không chạy hai tiến trình ghi cùng output version.

## Các tệp được tạo ở vùng dữ liệu riêng

| Tệp | Nội dung |
|---|---|
| train.jsonl | Mẫu huấn luyện |
| validation.jsonl | Mẫu chọn mô hình, calibration và ngưỡng |
| test.jsonl | Final test; không dùng fit, tuning hay chọn seed |
| quarantine.jsonl | Số thứ tự bản ghi, nhãn nguồn hợp lệ nếu có, mã lỗi; không chứa URL thô |
| duplicates.jsonl | Bản ghi dư và sample_id/record đại diện; không chứa URL thô |
| report.json | Tổng số từng bước, lớp, nhóm, tỷ lệ, lý do cách ly và giới hạn |
| manifest.json | Hash nguồn/output/mã, runtime, PSL, seed, thuật toán và ánh xạ nhãn |

Một mẫu gồm input_url, normalized_url, sample_id=SHA256(normalized_url),
group_id=SHA256(domain:/ip:+khóa canonical), source_record (số bản ghi dữ liệu, bắt đầu1,
không phải số dòng vật lý của CSV), source_label, y, source_id, label_schema_version.
Chỉ URL được dùng để tính đặc trưng. y là mục tiêu. Không dùng sample_id/group_id/source_record,
source_label/source_id làm đặc trưng mô hình. Cột normalized_url phục vụ dedup/provenance,
không được làm mất dấu hiệu của input_url khi trích đặc trưng.

Các tệp train/validation/test vẫn chứa URL nguồn có thể nhạy cảm hoặc nguy hiểm: lưu riêng,
không đưa vào Git công khai, không mở thử. Quyền giữ dữ liệu nghiên cứu này khác với quy tắc
không lưu URL của người dùng API. Hash chỉ là định danh và kiểm toàn vẹn, không phải ẩn danh
hay chữ ký xác thực. Không gửi toàn bộ CSV/JSONL vào chat khi báo lỗi; gửi report metadata.

## Khi nào trạng thái FROZEN được ghi

Nguồn và giấy phép được rà soát ở G0, ghi lại trong lock; script không tự xác minh quyền
pháp lý hay chất lượng nhãn. Trước khi xuất thư mục cuối, pipeline kiểm SHA-256 nguồn,
version thư viện và PSL, phân lớp; chạy kiểm tra lại output: hash, tính canonical và nhóm,
nhãn, cả hai lớp mỗi tập, mẫu/miền không giao nhau, mỗi source_record được hạch toán đúng một lần.
Chỉ khi các kiểm tra cấu trúc đạt mới chuyển thư mục tạm thành thư mục cuối.
FROZEN ở đây là snapshot cục bộ cho thí nghiệm, không phải bản ghi đã đăng ký vào PostgreSQL.
Không có kiểm tra tự động nào chứng minh mọi nhãn của nguồn đều đúng hoặc không có PII.

Manifest ghi Python và Unicode runtime thực tế. Verify yêu cầu đúng runtime/mã để tránh âm
thầm xác nhận bộ dữ liệu bằng một parser khác. Nếu chuyển từ Python3.12 sang3.14, tạo snapshot
riêng và so sánh thống kê/manifest; không sửa manifest cũ để giả vờ giống môi trường.
Mã mở tất cả tệp văn bản với UTF-8 rõ ràng và ghi newline LF để tránh lỗi cp1252 trên Windows.

## Tiêu chí chuyển G1.2

- Các kiểm thử và verify đạt, không có giao nhau sample/domain group.
- Tổng input = clean + duplicate + quarantine; phân tích số bị loại theo nhãn.
- So sánh kết quả với `reference-report.json`. Nếu khác trên máy bạn, kiểm môi trường và lý do,
  không tự ép số lượng cho giống hoặc xóa ngẫu nhiên dữ liệu.
- Chốt manifest này trước khi train. Chỉ dùng train để fit scaler/vectorizer/chọn feature.
- G1.2 mới thêm đặc trưng, baseline Logistic Regression/Random Forest và báo cáo validation.

Miền không giao nhau không loại trừ hoàn toàn cùng chiến dịch trên nhiều miền. Nguồn không có
mốc thời gian tin cậy nên chưa được gọi là đánh giá theo thời gian. Loại URL ngoài phạm vi gây
selection bias; không được tính HTTP422 thành dự đoán đúng hoặc tuyên bố recall trên toàn nguồn.

## Nguồn và giấy phép

Nguồn: [PhiUSIIL Phishing URL (Website), UCI dataset967](https://archive.ics.uci.edu/dataset/967/phiusiil+phishing+url+website),
giấy phép công bố CC BY4.0. URL tải và checksum cố định ở `scripts/g1/source-lock.json`,
truy nguyên audit G0 ngày14/11/2026. Khi công bố luận văn/dữ liệu dẫn xuất, trích dẫn tác giả/DOI
đúng theo trang nguồn, nêu phép lọc, dedup, ánh xạ nhãn và split của dự án. Gói mã không tái phân phối CSV.
