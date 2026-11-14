# G0 — Dữ liệu, nhãn và thiết kế nghiên cứu

Ngày chốt thiết kế: 14/11/2026. Cơ sở: đặc tả 1.1 và mã nguồn nhánh
`feat/url-inspection` tại `7f08bdb`. Đây là quyết định thiết kế; chưa có kết quả huấn luyện.

## 1. Quyết định nguồn dữ liệu

| Vai trò | Nguồn | Quyết định |
|---|---|---|
| Baseline URL | PhiUSIIL từ UCI [S1] | Chọn; chỉ lấy URL và nhãn gốc, tính lại đặc trưng offline |
| Baseline tin nhắn | Vietnamese SMS Dataset của Trần Nguyễn Thái Tuấn và cộng sự [S2] | Chọn có điều kiện làm sạch; tác vụ SPAM_DETECTION với lớp dương SPAM_OR_SCAM |
| SMS phishing sample 300 mẫu [S3] | Mẫu của cùng nhóm tác giả | Không dùng làm tập kiểm thử độc lập khi chưa chứng minh không chồng lặp nguồn chính |
| Dữ liệu cập nhật mới | Phản hồi có đồng ý riêng, đã xác minh | Chỉ dùng sau khi có pipeline kiểm duyệt; không tự học |
| PhishTank, nguồn Việt Nam bổ sung | Nguồn tham khảo cho giai đoạn sau | Chưa nhập vào baseline, chưa gọi dữ liệu đó là đã xác minh |

UCI công bố PhiUSIIL gồm 235.795 mẫu, nhãn 1=legitimate và 0=phishing, có đặc trưng từ
cả URL và nội dung website, giấy phép CC BY 4.0 [S1]. Bản dự án không tải nội dung URL đích.
Nguồn SMS công bố nhãn 0=hợp lệ, 1=rác/lừa đảo và CC BY 4.0 [S2]. Nhãn gộp này không
chứng minh một tin nhắn là lừa đảo tài chính. Những tuyên bố về quy trình thu thập,
ẩn danh hoặc kết quả benchmark là tuyên bố của tác giả, không phải kết quả xác minh độc lập của dự án.

Ghi tác giả, URL nguồn, giấy phép công bố, ngày tải, hash tệp và các biến đổi trong
manifest/NOTICE. Không đưa CSV thô, URL nguy hiểm hoặc nội dung SMS vào Git công khai.
Không giả định giấy phép dataset cho phép bỏ qua quyền riêng tư hoặc tái công bố mọi nội dung.

## 2. Kiểm tra trực tiếp các tệp nguồn

Đã tải tệp từ nguồn công bố để kiểm tra offline, không mở các URL chứa trong dữ liệu.
Kết quả máy đọc đầy đủ ở `source-audit.json`; mã kiểm tra ở `scripts/g0/audit_sources.py`.
Nguồn SMS được cố định tại commit `464a028878023598e16f2f344ee36f7d5d74257f`.

### URL

| Chỉ số kiểm tra | Kết quả |
|---|---:|
| Tổng hàng | 235.795 |
| Nhãn gốc legitimate / phishing | 134.850 / 100.945 |
| Hàng trùng URL nguyên văn | 425 |
| Hàng được bộ inspect hiện tại chấp nhận | 235.002 |
| Hàng ngoài phạm vi hoặc không hợp lệ | 793 |
| URL chuẩn hóa duy nhất trong phần chấp nhận | 234.585 |
| Nhóm miền đăng ký/IP trong phần chấp nhận | 197.684 |
| URL chuẩn hóa có nhãn mâu thuẫn trong phần chấp nhận | 0 |

793 hàng bị loại trong snapshot này đều mang nhãn phishing gốc: 774 hostname ngoài
phạm vi, 10 userinfo, 5 hostname lỗi, 4 vượt độ dài. Đây là **thiên lệch cần báo cáo**:
không được loại chúng rồi tuyên bố recall end-to-end trên toàn bộ dữ liệu.
Model metrics chỉ áp dụng cho tập trong phạm vi; báo thêm coverage, số lượng và nhãn
của mẫu bị từ chối. API 422 không được xem là dự đoán an toàn hoặc đúng lớp phishing.

Chuẩn hóa dùng `inspect_url`; không lowercase toàn URL để khử trùng vì path/query có
thể phân biệt hoa thường. Thống kê `normalized_duplicate_rows` chung trong audit chỉ
là phép chẩn đoán văn bản; pipeline URL phải dùng `normalized_url` đã kiểm soát.

### SMS

| Chỉ số kiểm tra | Kết quả |
|---|---:|
| full_dataset.csv | 2.991 hàng; nhãn 0: 2.193, nhãn 1: 798 |
| train.csv / test.csv công bố | 2.394 / 597 hàng |
| Hàng trùng nguyên văn trong full | 361 |
| Hàng dư sau NFC + casefold + gộp whitespace | 393 |
| Nhóm nội dung chuẩn hóa có nhãn mâu thuẫn | 1 |
| Nội dung trùng nguyên văn giữa train và test | 27 |
| Nội dung chuẩn hóa trùng giữa train và test | 28 |
| Nhóm template trùng theo heuristic audit | 34 |
| Hàng full khớp heuristic số dạng OTP chưa che | 181 |

Các con số trên do script của dự án tính trên snapshot, không lấy từ benchmark của
tác giả. “OTP-like” là cờ kiểm tra văn bản, không chứng minh đó là mã thật/còn hiệu lực.
Không in mã hay nội dung cụ thể trong báo cáo. Không xem bước rà soát tự động là bảo đảm
đã ẩn danh hoàn toàn.

**Không dùng nguyên split train/test công bố.** Dùng full_dataset, cách ly nhóm nhãn
mâu thuẫn, khử trùng, che dữ liệu nhạy cảm và chia lại theo template group. Không gộp
thêm train.csv/test.csv vào full vì sẽ đếm lặp dữ liệu.

## 3. Schema nhãn đã chốt

| Task | Nhãn nguồn | y của dự án | predicted_label | Diễn giải được phép |
|---|---|---:|---|---|
| PHISHING_DETECTION | PhiUSIIL 0 | 1 | PHISHING | Dự đoán nguy cơ phishing, không phải bằng chứng đã xác minh |
| PHISHING_DETECTION | PhiUSIIL 1 | 0 | LEGITIMATE | Dự đoán lớp legitimate của dataset, không bảo đảm an toàn |
| SPAM_DETECTION | SMS 1 | 1 | SPAM_OR_SCAM | Nội dung thuộc nhóm rác/đáng ngờ theo nhãn gộp của nguồn |
| SPAM_DETECTION | SMS 0 | 0 | HAM | Nội dung thuộc nhóm hợp lệ theo nhãn nguồn |
| SCAM_DETECTION | Chưa có corpus riêng đã duyệt | Chưa dùng | SCAM / NON_SCAM | Chỉ bật khi có định nghĩa nhãn và dữ liệu xác minh riêng |

Manifest nhãn là `url-labels-v1` hoặc `sms-combined-labels-v1`; lưu original_label và
source_id để kiểm tra lại ánh xạ. Nhãn thiếu/khác {0,1} phải cách ly, không ép thành 0.
SMS dương chỉ nâng cảnh báo tới NEEDS_REVIEW trong policy đầu; HIGH_RISK/VERIFIED_PHISHING
của tin nhắn có thể đến từ URL bên trong, phải ghi rõ nguồn căn cứ.

## 4. Pipeline chuẩn bị dữ liệu phải triển khai ở G1

1. Tải từ URL nguồn cố định, kiểm hash, lưu raw trong vùng nghiên cứu riêng.
2. Parse CSV UTF-8 BOM an toàn; kiểm cột bắt buộc, nhãn, văn bản rỗng, giới hạn kích thước.
3. URL: dùng preprocessing chung; ghi rejected reason theo lớp; bỏ trùng canonical URL.
4. SMS: giữ bản gốc trong vùng hạn chế, tạo bản NFC, che số tài khoản/điện thoại/OTP
   theo quy tắc có phiên bản và kiểm tra thủ công; không xóa dấu tiếng Việt.
5. Cách ly toàn bộ nhóm nhãn mâu thuẫn, không giải quyết bằng đa số tự động.
6. Tạo group_id, chia tập, lưu manifest trước khi fit bất kỳ vectorizer/scaler nào.
7. Xuất báo cáo số mẫu theo từng bước, tỷ lệ lớp, tỷ lệ bị loại, kiểm không giao nhau.
8. Chỉ gán dataset status FROZEN khi mọi gate cấu trúc/nhãn/quyền riêng tư và split đạt.

Đối với SMS, dùng cùng bộ che token trong huấn luyện và suy luận; trích URL gốc trước
khi tạo biểu diễn text đã che cho classifier, chỉ giữ trong bộ nhớ. Không dùng regex
heuristic của audit như một bộ ẩn danh hoàn chỉnh hoặc bộ nhận diện scam.

## 5. Chia tập và chống rò rỉ

Tỷ lệ mục tiêu 70% train, 15% validation, 15% final test **theo số mẫu gần đúng**;
nhóm không bị tách chỉ để đạt tỷ lệ đẹp. Seed cố định 42, không thử nhiều seed để lấy điểm cao.

- URL: group theo registered_domain (PSL gồm private suffix), IP theo địa chỉ canonical.
  Khi nhiều URL cùng chiến dịch nhưng khác domain đã có bằng chứng, gộp thêm campaign_id.
- SMS: exact normalized text cùng group; tạo template bằng thay URL/số/thời gian/token
  nhạy cảm, ghép nhóm gần trùng bằng token Jaccard >=0,85 và thành phần liên thông.
  Ngưỡng này là quy tắc chống trùng của dự án, không phải kết quả ML. Lưu version,
  phân bố kích thước nhóm và rà nhóm quá lớn; không dùng label để tách một template.
- Stratify theo phân bố nhãn ở cấp nhóm khi có thể; kiểm mỗi lớp có mặt ở mọi tập.
  Nếu dữ liệu sau làm sạch quá ít hoặc mất một lớp, không chạy báo cáo đánh giá giả.
- Fit TF-IDF/scaler/chọn đặc trưng/cân bằng lớp chỉ trên train hoặc train fold.
  Validation dùng chọn mô hình, calibration và ngưỡng; final test chỉ mở sau khi đóng băng.
- URL blacklist/brand registry dùng snapshot không chứa thông tin từ tương lai trong
  đánh giá theo thời gian. Báo riêng ML thuần và hệ thống có tra cứu, tránh quy thành tích
  blacklist thành thành tích học máy.

Không coi cột `date` của SMS là thời điểm xảy ra hành vi khi chưa kiểm chứng ngữ nghĩa.
Snapshot URL không đủ timestamp đáng tin để tự tuyên bố phát hiện drift theo thời gian.

## 6. Đặc trưng và baseline

E1 URL: nhóm lexical — url_length, hostname_length, subdomain_count, digit_count,
is_ip, is_https, path_length, query_length, số dấu '-', '.', '/', '=', '&', percent-escape.
E2 bổ sung Unicode hostname, format character, Punycode và thông tin cấu trúc miền.
E3 bổ sung similarity/confusable từ danh mục thương hiệu đã xác minh, snapshot cố định.
E4 calibration/ngưỡng. E5 cập nhật theo lô đã kiểm duyệt.

Những cờ đang có trong inspect là nền tảng, chưa phải vector huấn luyện cuối cùng.
Không dùng FILENAME, nhãn, split, source_id, thời gian gán nhãn, thông tin HTML hoặc
các đặc trưng thống kê có sẵn không tái lập được ở runtime. Feature schema phải có
tên/thứ tự/dtype/quy tắc missing và version. Training và FastAPI dùng cùng module;
trước khi train chính thức sẽ đóng gói `packages/python-core`, không sao chép hai phiên bản.

Baseline URL: Logistic Regression và Random Forest trước; LightGBM là mô hình so sánh
tiếp theo. Baseline SMS: TF-IDF char n-gram (3–5) + Logistic Regression/Linear SVM.
Giới hạn n-gram và vocab bằng train; không gọi tokenizer phụ thuộc web trong inference.
Khi dùng SVM margin, score_type=RAW_MARGIN; không gọi trực tiếp margin là xác suất.

## 7. Đánh giá, chọn ngưỡng và học thích ứng

Chỉ số: precision, recall, F1, FPR, confusion matrix, average precision (ghi rõ cách
tính PR-AUC), latency; Brier/reliability curve chỉ khi có xác suất. Định nghĩa lớp dương
theo bảng nhãn. Mẫu số bằng 0 báo N/A, không tự điền 0 để làm đẹp báo cáo.

Chưa chốt số R_min/FPR_max/delta_old hoặc ngưỡng low/high. Sau baseline, chọn trade-off
trên validation, ghi policy version và quyết định trước khi chạy test. Model_score
không mặc nhiên là xác suất đã hiệu chỉnh. Confidence interval/bootstrap theo nhóm
domain/template khi đủ nhóm; báo rõ số mẫu của từng đánh giá.

E5 tối thiểu là **mô phỏng cập nhật theo lô** nếu chưa có dữ liệu theo thời gian:
giữ D0_train, D1_update, validation/promotion, old_holdout và D2_unseen tách nhau theo
group; lập manifest riêng trước thực nghiệm. D1 không chứa old_holdout/D2. So sánh model
cố định D0 với model cập nhật D0+D1 trên cùng các holdout. Không đổi tên các lô ngẫu nhiên
thành ngày thu thập. Khi có nguồn timestamp thật mới bổ sung đánh giá temporal.

Promotion set dùng quyết định release; final test nghiên cứu dùng báo cáo kết thúc,
không dùng để liên tục chọn candidate. Candidate không tốt hơn vẫn là kết quả hợp lệ.
ADWIN/Active Learning/incremental learning là mở rộng, chưa bắt buộc trong baseline.

## 8. Điều kiện chuyển G0 → G1

Đã chốt nguồn, phạm vi nhãn, cách làm sạch, chia tập, đặc trưng và quy trình đánh giá.
G0 không đồng nghĩa dữ liệu đã làm sạch, split đã FROZEN hoặc model đã huấn luyện.
Pipeline G1 phải giải quyết các lỗi audit đã thấy trước khi train, nhất là overlap SMS
và thiên lệch mẫu URL bị từ chối. Không cần người dùng tự đi tìm dataset khác ngay lúc này.

## Nguồn

- [S1 — UCI PhiUSIIL](https://archive.ics.uci.edu/dataset/967/phiusiil+phishing+url+website),
  Arvind Prasad và Shalini Chandra; truy cập 14/11/2026.
- [S2 — Vietnamese SMS dataset](https://github.com/trannguyenthaituan251209/vietnamese_sms_dataset),
  Trần Nguyễn Thái Tuấn và cộng sự; snapshot và hash trong source-audit.json.
- [Dataset card của tác giả](https://huggingface.co/datasets/trannguyenthaituan/vietnamese_sms_dataset).
- [S3 — SMS sample](https://huggingface.co/datasets/trannguyenthaituan/vietnamese_sms_phishing_sample).
- [scikit-learn: chống data leakage](https://scikit-learn.org/stable/common_pitfalls.html).

Các lựa chọn pipeline, tỷ lệ split và diễn giải sản phẩm trong tài liệu này là quyết
định của dự án; không coi điểm benchmark do tác giả dataset công bố là điểm của dự án.
