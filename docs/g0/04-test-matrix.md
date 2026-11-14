# G0 — Ma trận nghiệm thu

Đây là ma trận kỹ thuật G0 bổ sung. Mã G0-Txx không thay thế hay tuyên bố trùng chính xác
24 mã kiểm thử trong đặc tả 1.1. “Đã có” dưới đây dựa trên log người dùng đã gửi; các
kiểm thử mới chạy trong phiên này được ghi riêng tại validation-report.json.

| Mã | Tình huống và kết quả cần đạt | Trạng thái |
|---|---|---|
| G0-T01 | Health Node/DB/AI; readiness503 khi chưa có model | Health đã chạy trên máy người dùng; kiểm readiness đầy đủ ở G1 |
| G0-T02 | Chuẩn hóa scheme/hostname, giữ case path/query, encoding và dấu phân cách rỗng | Python test đã có |
| G0-T03 | IDNA tương đương; giữ hostname đầu vào; Unicode path không thành Unicode hostname | Python test đã có |
| G0-T04 | PSL/private suffix đúng, dùng snapshot offline ngay lần đầu | Python test đã có |
| G0-T05 | URL sai/unsupported/userinfo/IP đặc biệt trả lỗi rõ, không suy ra an toàn | Python validation test đã có; mở rộng biên khi triển khai |
| G0-T06 | Node chuyển token, validation, timeout/lỗi upstream/rate limit | Gateway test đã có; cần tách báo cáo từng nhánh |
| G0-T07 | Lỗi/log không lộ URL/SMS/token; inspect không lưu raw | Test lỗi Python đã có; audit log/DB toàn luồng còn chờ |
| G0-T08 | Quét URL dùng đúng model/feature/preprocessing/release | Chờ G1 |
| G0-T09 | Spam không bị báo thành lừa đảo đã xác minh; đúng task-label | Schema đã kiểm; logic/UI chờ G1 |
| G0-T10 | QR xử lý trên trình duyệt; URL theo cùng pipeline; QR không phải URL báo không hỗ trợ | Chờ frontend |
| G0-T11 | Tin nhắn nhiều URL; một URL nguy cơ cao không bị text lành tính che lấp | Chờ logic tổng hợp |
| G0-T12 | Phân tích một phần/URL vượt giới hạn không trả ít rủi ro | DB/schema đã kiểm; logic runtime chờ G1 |
| G0-T13 | AI chưa tải, timeout, tất cả component thất bại không có kết luận an toàn | Hợp đồng đã thiết kế; integration chờ G1 |
| G0-T14 | Verified indicator hết hạn/domain-only không đủ VERIFIED_PHISHING | Chờ logic evidence |
| G0-T15 | SHAP top5 + phần còn lại đúng output space; lỗi giải thích có giới hạn rõ | Chờ mô hình |
| G0-T16 | Cookie/CSRF/session rotation; GET/DELETE scan sai chủ404; admin RBAC | Chờ identity và integration |
| G0-T17 | Feedback chấp nhận không tự huấn luyện; nhãn cần reviewer và căn cứ | Một phần CHECK đã kiểm; workflow chờ G1 |
| G0-T18 | Consent riêng, rút sau hết phiên, cleanup/backup restore không tái xuất mẫu bị thu hồi | Chờ workflow/retention |
| G0-T19 | Dữ liệu không trùng group/domain/template giữa split; conflict quarantine | Audit nguồn xong; pipeline làm sạch/chia tập chờ G1 |
| G0-T20 | Threshold/calibration chỉ dùng validation; finaltest không dùng tuning | Quy trình đã chốt; thực nghiệm chờ G1 |
| G0-T21 | Job idempotency; lease cũ bị từ chối; worker lỗi không kích hoạt model | DDL/hợp đồng đã có; cạnh tranh runtime chờ G1 |
| G0-T22 | Task/model/snapshot FK đúng; chỉ một ACTIVE; rollback toàn release nguyên tử | CHECK/FK/index đã kiểm; activate runtime chờ G1 |
| G0-T23 | Học theo lô cải thiện tập mới, không suy giảm quá gate tập cũ; không học nhãn chưa xác minh | Thiết kế thí nghiệm xong; chưa có kết quả |
| G0-T24 | Đo p50/p95, RAM, CPU, cold/warm, timeout trên laptop thực | Chưa đo; không đặt trước kết quả |

## Điều kiện đóng G0 và chuyển G1

Đóng phần thiết kế khi có nguồn + định nghĩa nhãn + audit, ERD/DDL, hợp đồng máy đọc được,
chính sách cảnh báo/quyền/retention, ma trận test và báo cáo validation. Không yêu cầu mô hình
đã đạt accuracy hay latency ở G0. Các lựa chọn ngưỡng/thuật toán cuối cùng phải dựa G1.

Không được ghi “toàn bộ kiểm thử đạt” chỉ vì schema/DDL đạt. Test Python11 và Node1 là log
đã có của người dùng; không cộng thành số test chức năng mới đã chạy trong gói này.

## Kiểm tra dữ liệu G1 bắt buộc

1. Đối chiếu SHA-256 nguồn với source-audit.json; sai checksum dừng hoặc mở phiên bản dữ liệu mới.
2. Tổng accepted/rejected/quarantine = tổng input; báo cáo theo nhãn. Không bỏ âm thầm URL lỗi.
3. Chuẩn hóa cho split riêng với đặc trưng suy luận; không casefold path URL để gộp nhầm.
4. Không giao nhau ID mẫu, URL canonical/domain group hoặc SMS cluster giữa train/validation/test.
5. Chỉ fit vectorizer/scaler/feature selection trên train; freeze split manifest trước chạy thử.
6. Tập finaltest giữ kín trong chọn model/threshold; không chọn lại model sau khi nhìn finaltest.
7. Report precision/recall/F1/FPR/AP, confusion matrix, coverage, độ bất định và hạn chế nguồn.
8. Ghi seed, phiên bản mã, môi trường, checksum dữ liệu/PSL/features/model để tái lập.

## Kiểm tra migration G1 bắt buộc

Chạy trên PostgreSQL17 tạm: apply forward, kiểm constraint/index và quyền role; rollback
migration theo chiến lược đã chọn, kiểm backup/restore. Thử đồng thời activate và claimjob
bằng nhiều connection; PostgreSQL/WASM đơn luồng trong gói G0 không chứng minh concurrency.
Kiểm mapping SQL↔API, lifecycle state, ownership, consent và redaction bằng integration tests.
