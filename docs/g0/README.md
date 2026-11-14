# G0 — Baseline thiết kế kỹ thuật

Ngày: 2026-11-14. Dựa trên đặc tả1.1 và nhánh feat/url-inspection tại commit
`7f08bdb5b98f9d0575b0ce58ec0fba4177f9d60b`.

Gói này hoàn thiện **thiết kế G0**: không triển khai endpoint scan, mô hình AI, frontend,
migration vào database đang chạy hay hệ thống quản trị. Không sửa hành vi URL inspect hiện có.

## Đọc theo thứ tự

1. [Dữ liệu, nhãn và nghiên cứu](01-data-and-research.md).
2. [ERD và chính sách dữ liệu](02-database-design.md), [từ điển dữ liệu](data-dictionary.md).
3. [API và chính sách kết quả](03-api-and-policy.md).
4. [Ma trận nghiệm thu](04-test-matrix.md), [báo cáo kiểm tra](validation-report.json).

Nguồn máy đọc được: `docs/g0/source-audit.json`, `database/design/g0-schema.sql`,
`packages/contracts/*.openapi.json`, `packages/contracts/examples.json`.

## Kết quả và việc còn lại

| Hạng mục | G0 | Giai đoạn tiếp |
|---|---|---|
| Cấu trúc/quy ước | Chốt dưới đây | Áp dụng khi tạo module |
| Dữ liệu | Audit nguồn, chọn có điều kiện, định nghĩa nhãn và split | Làm sạch, kiểm duyệt, freeze manifest |
| PostgreSQL | ERD/DDL đích24bảng; kiểm cô lập | Migration từng nhóm trên PostgreSQL17 thật |
| API | OpenAPI public/internal; đánh dấu implemented/planned | Implement và test integration từng luồng |
| Cảnh báo/quyền | Quy tắc, state, test matrix | Implement policy, auth, ownership, consent |
| AI | Thiết kế thí nghiệm và promotion gate | Train baseline, chọn ngưỡng, đo laptop |

Audit phát hiện 27 nội dung SMS trùng nguyên văn giữa train/test công bố. Vì vậy không dùng
nguyên split nguồn. 793 URL PhiUSIIL bị parser hiện tại từ chối, đều thuộc nhãn phishing
của nguồn; cần báo coverage theo nhãn để không che selection bias. Chi tiết/hashes ở audit.
Không gọi nhãn spam của nguồn SMS là nhãn lừa đảo đã xác minh.

## Cấu trúc và quy ước

- `apps/web`: React + TypeScript, responsive, QR trình duyệt; tạo khi vào frontend.
- `apps/api`: Node + Express + TypeScript, nghiệp vụ và DB; giữ cấu trúc đang có.
- `services/ai`: FastAPI, chuẩn hóa/feature/inference; giữ bộ chuẩn hóa đã test.
- `services/training`: worker riêng khi triển khai, không train trong request FastAPI.
- `packages/contracts`: OpenAPI/examples; generator tại scripts/g0 là nguồn chỉnh sửa.
- `database`: thiết kế hiện tại; migration phiên bản hóa tạo ở bước triển khai.
- `docs/g0`: quyết định thiết kế, audit và nghiệm thu; raw dataset/artifact để ngoài Git.

TypeScript giữ strict typing; Python có type hints ở biên module; SQL snake_case; JSON
snake_case theo API hiện có. Thời gian UTC ISO8601, ID UUID; seed42 cho thí nghiệm ban đầu.
Không ép đổi runtime Python hiện tại trước khi thử compatibility thư viện train; ghi phiên
bản thực tế vào manifest. Lock dependency theo từng service; không commit .env, .venv,
node_modules, dữ liệu raw, model binary hoặc log chứa input. `.env.example` chỉ placeholder.
Commit nhỏ theo mục đích; test đúng phần đổi; API breaking change phải tăng version hợp đồng.

## Kiểm tra gói trên Windows PowerShell

Tại thư mục gốc dự án:

```powershell
npm.cmd ci --prefix scripts/g0
npm.cmd test --prefix scripts/g0
py -3.14 -m venv ..\phishing-g0-venv
.\..\phishing-g0-venv\Scripts\python.exe -m pip install -r scripts/g0/requirements-validation.txt
.\..\phishing-g0-venv\Scripts\python.exe scripts/g0/validate_contracts.py
```

Môi trường kiểm tra dùng ở phiên soạn gói là Python3.12 và Node24; không khẳng định đã
chạy các lệnh Windows trên Python3.14 của bạn. Có thể dùng thư mục venv ngoài repo để tránh
commit nhầm. Không chạy DDL này vào database hiện tại; script Node tự tạo DB trong bộ nhớ.
PGlite trong báo cáo dùng PostgreSQL18.6/WASM, không thay thế kiểm tra PostgreSQL17.

## Thứ tự G1

1. Tạo pipeline nhập/làm sạch URL, thống kê rejected/quarantine; freeze split theo domain.
2. Recompute đặc trưng từ bộ chuẩn hóa hiện có, train baseline URL và đánh giá validation.
3. So sánh mô hình/ablation/calibration, chốt ngưỡng dựa mục tiêu recall và FPR; lưu manifest.
4. Triển khai registry/migration tối thiểu, inference và policy/API scan; kiểm lỗi và ownership.
5. Làm SMS sau khi xử lý trùng lặp/conflict/PII và xác nhận phạm vi nhãn; mở rộng UI/QR.

Các giá trị threshold, mục tiêu recall/FPR chốt trước đánh giá finaltest, không đặt sau khi
nhìn test. G0 đủ để bắt đầu các bước này; chưa đủ để tuyên bố hệ thống phát hiện phishing đạt nghiệm thu.
