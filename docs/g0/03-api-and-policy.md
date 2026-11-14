# G0 — Hợp đồng API và chính sách kết quả

Nguồn chuẩn có thể kiểm tra bằng máy: `packages/contracts/public.openapi.json` và
`internal.openapi.json`. Sinh lại bằng `python scripts/g0/build_contracts.py`.
`x-implementation-status` phân biệt endpoint đã tồn tại với thiết kế chưa triển khai.
Các ví dụ trong `examples.json` là dữ liệu tổng hợp, không phải suy luận mô hình thật.

## Phân công

React/TypeScript gọi Node; QR giải mã ở trình duyệt và gửi URL cùng input_type=QR_URL.
Node kiểm request, quyền, hạn mức, điều phối, tổng hợp cảnh báo và quản lý PostgreSQL.
FastAPI chuẩn hóa, trích đặc trưng và suy luận; không truy cập website đích.
Training Worker huấn luyện/đánh giá ngoài luồng request; đăng ký metadata qua Node.
Worker không tự phê duyệt hay kích hoạt model. SMS có mô hình riêng, không dùng mô hình URL cho văn bản.

API inspect hiện tại vẫn trả schema_version=1.0 và model_loaded=false, chỉ kiểm cấu trúc.
API scan dự kiến trả schema_version=1.1. Hai endpoint có mục đích khác nhau; không âm thầm
đổi inspect thành kết luận phishing. Health kiểm tiến trình; ready kiểm model/release.
Ready hiện trả 503 MODEL_NOT_LOADED; 200 trong hợp đồng là hành vi sau khi có mô hình.

## Quyết định cảnh báo

Áp dụng theo thứ tự; quyết định cuối do policy đã version hóa, không do giao diện suy đoán.

| Điều kiện | Kết quả |
|---|---|
| URL khớp chính xác indicator đã xác minh, còn hiệu lực | VERIFIED_PHISHING; ghi nguồn, thời điểm, kiểu khớp |
| Ít nhất một URL component PHISHING_DETECTION có điểm vượt ngưỡng cao | HIGH_RISK; ghi rõ URL component gây cảnh báo |
| Mọi thành phần cần thiết đều thất bại và không có căn cứ độc lập | Không trả kết quả ít rủi ro; HTTP 503 hoặc 504 với mã lỗi |
| Một phần thất bại, quá giới hạn phân tích, tín hiệu mâu thuẫn hoặc điểm vùng chưa chắc chắn | NEEDS_REVIEW nếu chưa thuộc hai hàng đầu |
| Mọi thành phần cần thiết hoàn tất, dưới ngưỡng và không có tín hiệu cần xem xét | NO_SIGNIFICANT_RISK_FOUND |

Không gọi trạng thái cuối là “an toàn tuyệt đối”. Điểm cao không phải bằng chứng xác minh.
Domain giống thương hiệu, có HTTPS, IDNA hay nằm trong danh sách domain thương hiệu đều
không tự chứng minh toàn bộ URL an toàn hoặc độc hại. DOMAIN_SIGNAL không đủ để gán VERIFIED_PHISHING.
Trong policy đầu, điểm SMS SPAM_DETECTION chỉ nâng tới NEEDS_REVIEW; mức cao hơn của MESSAGE phải đến từ URL/căn cứ xác minh.
SMS SPAM_OR_SCAM phải hiển thị “dấu hiệu tin nhắn rác/đáng ngờ”, không khẳng định lừa đảo tài chính.
Nếu chỉ có mô hình SPAM_DETECTION, phải nêu giới hạn chưa phân loại riêng hành vi lừa đảo.

Score gắn task_type, predicted_label, model_version và score_type. Chỉ
CALIBRATED_PROBABILITY được trình bày như xác suất đã hiệu chỉnh và bắt buộc có calibration_version.
RAW_MARGIN/MODEL_SCORE không được chuyển thành phần trăm độ tin cậy. Điểm luôn hướng về
nhãn dương của task; predicted_label được tính theo ngưỡng phân loại của model, mức cảnh báo
được tính theo policy nên không bắt buộc trùng một-một. Ngưỡng là kết quả G1, chưa có giá trị giả định.
SHAP giải thích đóng góp vào đầu ra mô hình, không chứng minh quan hệ nhân quả hay website độc hại.
Nếu giải thích lỗi: giữ kết quả model nếu hợp lệ, explanation_status=UNAVAILABLE và nêu giới hạn.

Mỗi MESSAGE: một TEXT, tối đa 10 URL riêng biệt sau chuẩn hóa. Vượt giới hạn trả PARTIAL,
NEEDS_REVIEW hoặc mức cao hơn có căn cứ; đếm urls_detected/analyzed/failed, ghi phần chưa xét.
Coverage không phải tổng số component vì gồm cả TEXT; các tổng đếm phải được kiểm ở ứng dụng.
Không có component hoàn tất và không có căn cứ độc lập thì không dùng PARTIAL để che lỗi toàn bộ.

## Lỗi và tương thích

| HTTP | Ý nghĩa |
|---|---|
| 400 | JSON không hợp lệ hoặc hình thức request sai |
| 401 / 403 | Chưa xác thực / thiếu quyền hoặc CSRF không hợp lệ |
| 404 | Không tồn tại, sai chủ hoặc hết hạn; không tiết lộ đối tượng của người khác |
| 409 | Xung đột phiên bản, trạng thái hoặc idempotency key |
| 413 | Body vượt giới hạn |
| 422 | URL/nội dung không hỗ trợ hoặc không đạt validation; không phải kết luận ít rủi ro |
| 429 | Vượt hạn mức; có Retry-After |
| 502 | Phản hồi upstream không hợp lệ |
| 503 / 504 | Chưa sẵn sàng/dịch vụ không khả dụng / hết thời gian chờ |

Error envelope dự kiến: request_id và error.code/message, field nếu phù hợp. Không đưa raw
URL, SMS, mật khẩu, token hoặc traceback ra lỗi/log. Endpoint health legacy giữ response
đã triển khai, mô tả riêng trong OpenAPI. Không lấy HTTP 200 của health làm bằng chứng model hoạt động.

Giới hạn đầu vào URL 4096 ký tự, MESSAGE 10000 ký tự; Node còn kiểm kích thước body byte.
Cấu hình ban đầu cho scan: body 64 KiB, deadline Node 10 giây, deadline AI 8 giây;
60 request/phút/subject và giới hạn IP phụ có cấu hình cho môi trường triển khai.
Đây là giới hạn vận hành dự kiến, không phải cam kết latency hay cấu hình inspect hiện có.
Không tự retry POST ghi dữ liệu; training job có idempotency riêng. Node truyền request_id
và release đã chọn, kiểm schema/version kết quả trước khi sử dụng.

## Quyền và trạng thái

- Phiên khách sở hữu scan thông qua subject; UUID không phải quyền truy cập.
- Bootstrap tạo cookie HttpOnly, SameSite và Secure khi HTTPS; trả CSRF token, kiểm Origin
  và X-Client-Request. Endpoint thay đổi dữ liệu yêu cầu cookie + CSRF cùng lúc.
- Đăng nhập xoay session token, chống fixation; logout thu hồi server-side. Chỉ ADMIN được
  quản lý nhãn, job, model, release, báo cáo. Vai trò MEMBER không thêm luồng đăng ký trong G0.
- Token Node→AI, Worker→Node, quản trị tải model tách riêng; không đưa các token này vào React.
- If-Match mang row_version có dấu ngoặc kép; đổi nhãn/release có audit và kiểm chuyển trạng thái.
- Feedback ACCEPTED không có nghĩa verified_label. Mẫu chỉ được train khi kiểm duyệt nhãn,
  có nguồn căn cứ và quyền sử dụng; dữ liệu phản hồi chưa xác minh không vào pipeline tự học.
- Idempotency job: cùng subject/operation/key và payload trả cùng job; payload khác trả409.
- Kích hoạt/rollback chọn cả release model + policy + snapshot; warm-load trước, đổi ACTIVE
  trong transaction sau. Không ghi đè tệp model đang phục vụ. Xem 02-database-design.md.

Dataset/config/policy manifest được nhập bằng CLI quản trị Node trong giai đoạn triển khai:
validate schema/checksum/quyền sử dụng → tạo DRAFT → kiểm duyệt → FROZEN/APPROVED.
CLI này chưa được viết; không sửa DB thủ công để bỏ qua kiểm duyệt. Các đường dẫn artifact nội bộ
phải thuộc kho cho phép, không nhận URL tùy ý để worker tải, không thực thi artifact chưa tin cậy.

## Quyền riêng tư

Inspect có thể trả normalized_url cho người gọi nhưng không lưu mặc định. ScanResult không
có raw URL/SMS. Rule/explanation/JSON metadata cũng phải giảm thiểu; schema không tự bảo đảm
chuỗi tự do không chứa bí mật. Giao diện render văn bản, không đưa kết quả vào innerHTML.
Nghiên cứu yêu cầu gửi mẫu riêng và consent rõ ràng; không tái dùng input kiểm tra mặc định.
Rút đồng ý dùng session sở hữu hoặc withdrawal token, không yêu cầu phiên khách cũ còn sống.
Thời hạn, xóa và giới hạn đối với mô hình đã train xem 02-database-design.md.
