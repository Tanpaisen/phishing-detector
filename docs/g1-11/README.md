# G1.11 — So sánh LightGBM và Random Forest trên cùng bộ đặc trưng

Trạng thái đầu ra: `EXPLORATORY_MODEL_COMPARISON_ONLY`. Bước này quay lại chất lượng phát hiện URL sau khi G1.10 đã đo luồng inspection. Không kích hoạt mô hình, không chỉnh API và không mở tập đánh giá cuối.

## Giả thuyết và protocol

G1.9 cho thấy nhánh path/query của Random Forest đạt recall external khoảng 41,32% tại mức FPR quan sát không quá 1% trên từng nguồn. G1.11 kiểm tra một cấu hình LightGBM CPU với cùng 23 đặc trưng đó, cùng các hàng TRAIN, thứ tự, nhãn và trọng số.

`protocol.json` được viết trước lần chạy tham chiếu. Chỉ chạy một cấu hình, không tìm kiếm siêu tham số, không thử nhiều seed rồi chọn kết quả đẹp. Bộ đặc trưng path/query được lựa chọn dựa trên validation đã quan sát ở G1.9, vì vậy phép so sánh vẫn mang tính phát triển và có nguy cơ lạc quan.

| Nội dung | Quy định |
|---|---|
| Đặc trưng | baseline_plus_path_query: 18 đặc trưng cũ + 5 path/query, tổng 23 |
| Train | PhiUSIIL train + external train theo phép chia G1.6 |
| Trọng số | Mỗi ô nguồn × nhãn có tổng trọng số N/4; không nhân thêm class weight |
| Đối chứng | Random Forest cùng cấu hình G1.8, tái lập trước khi chạy LightGBM |
| LightGBM | 4.6.0; binary GBDT; tối đa 300 vòng; learning_rate 0,05; 31 lá; min_data_in_leaf 20; L2=1 |
| Tài nguyên | CPU, 2 worker mặc định; cho phép 1–4 |
| Tái lập | seed 42; deterministic=true; force_col_wise=true; lưu hash thư viện native |
| Early stopping | Không dùng; không đưa validation vào lgb.Dataset/train |
| Chỉ số chính | Chênh lệch recall thấp nhất giữa hai nguồn tại ngưỡng riêng của mỗi mô hình, thỏa FPR quan sát ≤1% ở cả hai nguồn |
| Chỉ số phụ | Cùng phép so sánh tại cap 5%; AP, ROC-AUC, FPR/recall ở 0,5 và các lát dữ liệu |
| Chọn mô hình/ngưỡng triển khai | Chưa thực hiện; không tự tuyên bố người thắng |

300 là số vòng tối đa cấu hình. Thư viện có thể dừng nếu không còn phép chia hữu ích; số vòng thực được ghi trong báo cáo. Hai thuật toán không được coi là có độ phức tạp tương đương chỉ vì dùng cùng đặc trưng.

## Quy trình và tính toàn vẹn

1. Kiểm tra manifest, checksum, phiên bản mã và môi trường của G1.1/G1.2/G1.6/G1.8; đối chiếu file Mendeley mà bạn đã xác nhận nguồn.
2. Chỉ đọc PhiUSIIL TRAIN/validation và external development. Dùng nguyên các nhóm external train/reused-validation G1.6; không mở test.jsonl, holdout.jsonl hoặc hồ sơ review để đổi nhãn.
3. Tái lập confusion matrix và chỉ số G1.8 của RF path/query trên cả hai nguồn. Nếu không khớp, dừng trước LightGBM và không xuất báo cáo thành công.
4. Huấn luyện LightGBM chỉ bằng TRAIN. Sau huấn luyện mới predict validation. Không dùng nhãn validation cho Dataset, early stopping hoặc fit.
5. Áp dụng nguyên quy tắc ngưỡng G1.9 cho từng mô hình: score >= threshold; giữ nguyên các điểm trùng; FP budget=floor(cap × số mẫu âm) trên từng nguồn riêng. Không gộp hai nguồn để làm thấp FPR.
6. Báo cáo các ca được sửa và lỗi mới phát sinh theo số lượng tổng hợp, ở ngưỡng riêng tương ứng của mỗi mô hình. Chọn và đo ngưỡng trên cùng validation, không phải bằng chứng test độc lập.
7. Kiểm tra lại snapshot trước khi công bố report/protocol/manifest trong thư mục mới. Không xuất model hoặc URL nguyên bản.

Nguồn external reused-validation có 472 mẫu âm và 409 mẫu dương. Cap 1% cho phép tối đa 4 FP; cap 5% tối đa 23 FP. Đây là giới hạn **quan sát trên mẫu**, không bảo đảm FPR quần thể. Nhãn lịch sử chưa được xác minh từng mẫu; các mẫu cùng miền có phụ thuộc. Không báo khoảng tin cậy hoặc kết luận nhân quả về ưu thế thuật toán từ một lần chạy.

LightGBM với binary objective xuất điểm nằm trong [0,1], nhưng ở đây vẫn ghi MODEL_SCORE, không trình bày như độ tin cậy đã hiệu chuẩn. Nếu kết quả không cải thiện thì giữ nguyên và phân tích; không tự thay cấu hình sau khi xem kết quả.

## Chạy trên Windows PowerShell

Giữ nguyên nhánh hiện tại, tải patch vào D:\download. G1.8 và G1.9 cần đã được áp dụng.

```powershell
Set-Location E:\BE_NodeJs\phishing-detector

git apply --check "D:\download\g1-11-lightgbm-comparison.patch"
git apply "D:\download\g1-11-lightgbm-comparison.patch"

.\services\training\.venv\Scripts\python.exe -m pip install --no-deps -r docs/g1-11/requirements.txt
.\services\training\.venv\Scripts\python.exe -c "import lightgbm; print(lightgbm.__version__)"
.\services\training\.venv\Scripts\python.exe -m unittest discover -s services/training/tests -v
```

Chỉ thêm LightGBM==4.6.0, không nâng NumPy/SciPy/scikit-learn đã đóng băng. Đã kiểm tra có wheel win_amd64 phù hợp để pip lựa chọn với Python 3.14; khả năng import và chạy native trên máy bạn vẫn phải kiểm tra bằng lệnh trên. Nếu báo lỗi DLL, gửi lỗi; không tự đổi phiên bản hoặc chỉnh manifest.

Sau khi kiểm thử đạt, tạm dừng benchmark hoặc tác vụ huấn luyện khác để giảm cạnh tranh tài nguyên, rồi chạy:

```powershell
.\services\training\.venv\Scripts\python.exe services/training/compare_url_lightgbm.py `
  --dataset "E:\BE_NodeJs\phishing-data\processed\phiusiil-url-v1" `
  --external "E:\BE_NodeJs\phishing-data\external\hannousse-provisional-v1" `
  --baseline-run "E:\BE_NodeJs\phishing-models\url-baselines-v1" `
  --primary-file "D:\download\dataset_B_05_2020.csv" `
  --primary-origin mendeley-v3 `
  --experiment-run "E:\BE_NodeJs\phishing-models\multisource-experiment-v1" `
  --feature-run "E:\BE_NodeJs\phishing-models\url-feature-experiments-v1" `
  --output "E:\BE_NodeJs\phishing-models\url-lightgbm-comparison-v1" `
  --workers 2
```

G1.6/G1.8 phải là các kết quả đã chạy trên cùng môi trường Python của bạn. Không thay bằng báo cáo tham chiếu Linux. Thư mục output phải chưa tồn tại; nếu cần chạy lại, chọn tên mới.

Gửi `E:\BE_NodeJs\phishing-models\url-lightgbm-comparison-v1\report.json` để đối chiếu. Chưa đưa mô hình vào FastAPI và chưa tạo ngưỡng sản phẩm.

## Hiệu năng và giới hạn

Báo cáo có thời gian fit + batch predict cho hai mô hình; LightGBM có thời gian fit/predict riêng. Các phép đo này không bao gồm toàn bộ chuẩn bị dữ liệu và không phải độ trễ mỗi request API. Bộ nạp G1.8 vẫn tạo các mảng trong RAM; mã mới bỏ các mảng không dùng sau khi chuẩn bị, nhưng không tuyên bố đã tối ưu toàn bộ huấn luyện cho Big Data.

CPU deterministic hỗ trợ tái lập trong điều kiện phù hợp; khác hệ điều hành, compiler hoặc binary có thể cho điểm khác. Báo cáo ghi phiên bản và hash native để truy vết. Không sửa nhãn hoặc giảm độ chặt kiểm tra RF để làm cho phép so sánh chạy qua.

Nguồn kỹ thuật: [LightGBM 4.6.0 Parameters](https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html), phần deterministic/force_col_wise, objective, num_iterations và các trọng số. Không có lời hứa LightGBM sẽ tốt hơn RF trước thực nghiệm.

## Kết quả tham chiếu

Random Forest tái lập đúng kết quả G1.8. Chạy trên Python 3.12.14/Linux; cần đối chiếu với lần chạy Windows Python 3.14.8 của bạn.

| Cap FPR quan sát ở từng nguồn | Mô hình | Recall external | Recall PhiUSIIL | FP external / 472 |
|---|---|---:|---:|---:|
| 1% | lightgbm | 39.85% | 39.64% | 4 |
| 1% | random_forest | 41.32% | 45.86% | 4 |
| 5% | lightgbm | 65.28% | 79.53% | 23 |
| 5% | random_forest | 63.33% | 77.28% | 23 |

**Không cải thiện chỉ số chính:** ở cap 1%, recall thấp nhất giữa hai nguồn của LightGBM thấp hơn RF khoảng 1,68 điểm phần trăm. Trên external, RF phát hiện 169/409, LightGBM 163/409, cả hai có 4 FP. Trên PhiUSIIL, recall giảm từ 45,86% xuống 39,64%.

Ở cap 5% (chỉ số phụ đã chốt trước), LightGBM phát hiện thêm 8 mẫu phishing external, 267 so với 259, cùng 23 FP. Trên PhiUSIIL, LightGBM có 1 FP so với RF 0 FP, vẫn dưới cap nhưng cần ghi nhận. Không chuyển sang chọn cap 5% chỉ để tuyên bố thành công.

Thời gian fit + batch predict tham chiếu: RF khoảng 4,51 giây; LightGBM khoảng 2,12 giây. Đây không phải độ trễ API và không đủ để chọn mô hình khi chỉ số chất lượng chính chưa cải thiện.

Kết luận giới hạn ở hai cấu hình đã chạy, không kết luận LightGBM nói chung kém hơn RF. Không thay thuật toán, số vòng hoặc đặc trưng sau khi xem kết quả này. Các bước cải tiến tiếp theo cần giả thuyết và protocol riêng, ưu tiên kiểm tra giới hạn dữ liệu/nhãn và đặc trưng thay vì lặp dò ngưỡng trên validation cũ.
