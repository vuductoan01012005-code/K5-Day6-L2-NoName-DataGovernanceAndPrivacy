# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Điền đầy đủ, cụ thể, không viết chung chung. Mọi con số phải lấy từ file do script sinh ra
> (`reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`) — không gõ tay, không làm tròn mất đơn vị.
> 3–5 trang (hoặc README + report.md tương đương).

## 00 · Header

| Mục | Giá trị |
| --- | --- |
| Group ID | G05 |
| Challenge | T02 |
| Thành viên (5–6) + vai trò | 1. Vũ Đức Toàn **(Lead/Integrator)**<br>2. Ngô Trí Anh **(Data & fixtures)**<br>3. Trần Trọng Hoàng Vũ **(Core algorithm)**<br>4. Nguyễn Thanh Sơn **(QA/metric)**<br>5. Hoàng Mạnh Hùng **(Review + report)**<br>6. Trần Hữu Thủy **(Review + report)** |
| Git URL | <https://github.com/vuductoan01012005-code/K5-Day6-L2-NoName-DataGovernanceAndPrivacy> |
| Tag `demo-180m` (commit) | Chưa có tag trên Git local và `origin` |
| Tag `final-24h` (commit) | Chưa có tag trên Git local và `origin` |
| Deadline (giờ VN) | 23:59 (GMT+7) |

## 01 · Problem statement

- Ai bị ảnh hưởng / ai chịu hậu quả khi hệ thống sai? Đội kiểm duyệt, đội gán nhãn và đội phát triển mô hình sử dụng dữ liệu ảnh. Bỏ sót ảnh lỗi làm giảm chất lượng dữ liệu đầu vào; báo nhầm ảnh tốt làm tăng công kiểm tra và chi phí chụp lại, đồng thời có thể làm mất các ảnh ban đêm hữu ích.
- Điểm nghẽn cụ thể: Ngân sách kiểm duyệt chỉ có B=20 ảnh, nên cần ưu tiên các ảnh có khả năng lỗi cao nhất: mờ, lóa, thiếu sáng hoặc lỗi nén. Một ngưỡng độ nét chung khó xử lý khác biệt giữa camera và điều kiện ánh sáng, dễ báo nhầm ảnh ban đêm hoặc bỏ sót lóa cục bộ.
- Đầu vào → đầu ra: Ảnh và metadata trong fixtures/t02_raw_qc/ → tính đặc trưng chất lượng → chấm điểm và xếp hạng vào ranked_review.csv → tạo hàng đợi 20 ảnh ưu tiên → người kiểm duyệt xác nhận KEEP / RECAPTURE, kèm lý do và nhật ký kiểm duyệt.
- Tiêu chí GO / HOLD / REWORK (chốt trước khi chạy eval): GO: ảnh được xác nhận đủ chất lượng để sử dụng. HOLD: ảnh còn nghi ngờ hoặc chưa được kiểm duyệt, cần người phụ trách xác nhận. REWORK: ảnh được xác nhận có lỗi ảnh hưởng đến mục đích sử dụng, cần xử lý hoặc chụp lại. Hiệu quả xếp hạng được đánh giá bằng Defect Recall@20 và Precision@20, so sánh với baseline trên cùng tập eval và seed 42.
- Giả định của nhóm (cần DPO/legal/domain owner xác nhận): 
Dữ liệu synthetic được sử dụng hợp lệ cho mục đích học tập và đánh giá.
Dữ liệu ảnh thật (nếu sử dụng) phải được kiểm tra quyền sử dụng và yêu cầu bảo vệ thông tin cá nhân.
Các tiêu chí đánh giá chất lượng ảnh và quyết định KEEP / RECAPTURE cần được người phụ trách chuyên môn xác nhận.

## 02 · Data & provenance

| **Split** | **N** | **Nguồn / link** | **License** | **Synthetic?** |
| --- | --- | --- | --- | --- |
| dev | 56 | `fixtures/t02_raw_qc/images.csv` | CC0-1.0 | Có |
| eval / heldout | 40 | `fixtures/t02_raw_qc/images.csv` | CC0-1.0 | Có |

- **Schema & class mapping:**
  - Bộ dữ liệu gồm 96 ảnh synthetic, kích thước 320×180 pixel.
  - Schema đầu vào: `image_id`, `path`, `camera_id`, `light`, `split`.
  - Các loại lỗi: `none` (không lỗi), `blur` (mờ), `glare` (lóa), `dark` (thiếu sáng), `compression` (lỗi nén).
  - Ground Truth (GT): `defect_type`, `severity` (0–2), `is_defect`.
  - GT chỉ được sử dụng trong quá trình đánh giá, không dùng để điều chỉnh thuật toán trên tập eval.

- **Seed: 42 · Cách chia split (theo scene/group/segment?):**
  - Dữ liệu gồm 24 cảnh gốc, mỗi cảnh có 4 ảnh.
  - Chia theo `scene/group_id`, đảm bảo các ảnh thuộc cùng một cảnh nằm trong cùng một split.
  - Dev: 14 cảnh (56 ảnh), dùng để phát triển và điều chỉnh thuật toán.
  - Eval: 10 cảnh (40 ảnh), dùng để đánh giá kết quả.
  - Seed: 42, đảm bảo khả năng tái lập dữ liệu.

- **`manifest.csv` verified (sha256):** Có — lệnh: `python -m tools.verify_manifests`.
  - Kết quả: `14 manifests, 0 failing`.
  - T02: `OK fixtures/t02_raw_qc/manifest.csv`.
  - Các file đã kiểm tra có mã SHA-256 khớp với manifest.

- **Dữ liệu thật dùng (nếu có) và cách xây GT cho nó:**
  - Bộ dữ liệu fixture hiện tại sử dụng 96 ảnh synthetic.
  - Dữ liệu thật là phần mở rộng tùy chọn, chỉ sử dụng nếu được cung cấp và được nhóm triển khai.
  - GT của bộ dữ liệu synthetic được lưu riêng trong `gt/labels.csv`, phục vụ đánh giá.
  - Nếu nhóm bổ sung dữ liệu thật, cần xác định nguồn hợp lệ và xây dựng GT qua quá trình kiểm tra, gán nhãn có xác nhận.

## 03 · Research & design

### 3.1. References và lý do chọn kỹ thuật

**Reference 1: OpenCV – Laplacian**

- **URL:** https://docs.opencv.org/4.x/d5/db5/tutorial_laplace_operator.html
- **Ngày truy cập:** 17/11/2026.
- **Lý do chọn:** Sử dụng Laplacian Variance để đo độ sắc nét của ảnh, hỗ trợ phát hiện ảnh bị mờ (blur). Kỹ thuật đơn giản, xử lý nhanh và phù hợp làm baseline.

**Reference 2: OpenCV – Histogram Calculation**

- **URL:** https://docs.opencv.org/4.x/d8/dbc/tutorial_histogram_calculation.html
- **Ngày truy cập:** 17/11/2026.
- **Lý do chọn:** Sử dụng histogram và các thống kê độ sáng để hỗ trợ phát hiện ảnh thiếu sáng (dark), vùng quá sáng hoặc bão hòa (glare).

**Reference 3: ACDC – Adverse Conditions Dataset**

- **URL:** https://acdc.vision.ee.ethz.ch/
- **Ngày truy cập:** 17/11/2026.
- **Lý do chọn:** Tham khảo các điều kiện hình ảnh bất lợi như ban đêm, mưa và sương mù. Giúp nhóm nhận biết rằng ảnh tối không phải lúc nào cũng là ảnh lỗi.

---

### 3.2. Sơ đồ Data Flow

**Quy trình tổng thể:**

**Input → Process → Rank/QC → Review → Decision → Report**

#### Bước 1 – Input (Dữ liệu đầu vào)

- Đọc 96 ảnh synthetic và metadata từ `fixtures/t02_raw_qc/`.
- Kiểm tra tính toàn vẹn dữ liệu bằng SHA-256.

#### Bước 2 – Process (Xử lý dữ liệu)

- Chuyển ảnh sang dạng phù hợp để xử lý.
- Tính toán độ sắc nét bằng **Laplacian Variance**.
- Phân tích độ sáng và tỷ lệ pixel quá sáng.
- Tổng hợp các đặc trưng để tính điểm nghi lỗi.

#### Bước 3 – Rank/QC (Xếp hạng chất lượng ảnh)

- Sắp xếp ảnh theo điểm nghi lỗi từ cao xuống thấp.
- Xuất file `out/ranked_review.csv` gồm hai trường:
  - `image_id`: Mã định danh ảnh.
  - `score`: Điểm nghi lỗi của ảnh.
- Chọn **20 ảnh nghi lỗi nhất** để ưu tiên kiểm tra.

#### Bước 4 – Review (Kiểm duyệt)

- Tạo contact sheet hiển thị các ảnh ưu tiên.
- Người kiểm duyệt kiểm tra và có thể điều chỉnh kết quả.
- Ghi lại các thao tác kiểm duyệt (**Audit Log**).

#### Bước 5 – Decision (Ra quyết định)

- **KEEP:** Giữ lại ảnh đạt yêu cầu.
- **RECAPTURE:** Đề xuất chụp lại ảnh không đạt yêu cầu.
- Tổng hợp kết quả để hỗ trợ quyết định:
  - **GO:** Chấp nhận kết quả.
  - **HOLD:** Tạm dừng để kiểm tra.
  - **REWORK:** Cần chỉnh sửa hoặc cải thiện hệ thống.

#### Bước 6 – Report (Báo cáo)

- Báo cáo các chỉ số:
  - **Defect Recall@20:** Khả năng phát hiện ảnh lỗi trong 20 ảnh ưu tiên.
  - **Precision@20:** Tỷ lệ ảnh lỗi thực sự trong 20 ảnh ưu tiên.
- So sánh kết quả giữa **Baseline và PoC**.
- Phân tích các trường hợp hệ thống nhận diện sai.

---

### 3.3. Thành phần Offline

**1. Dữ liệu**

- Sử dụng 96 ảnh synthetic được cung cấp trong bài lab.
- Dữ liệu được lưu tại `fixtures/t02_raw_qc/`.

**2. Công cụ và thư viện**

- **Python:** Ngôn ngữ lập trình chính.
- **NumPy:** Hỗ trợ tính toán trên mảng.
- **Pillow:** Hỗ trợ đọc và xử lý ảnh.
- **SciPy:** Hỗ trợ các phép tính và xử lý ảnh.
- **OpenCV:** Có thể sử dụng để tính toán các đặc trưng ảnh.

**3. Model / Weights**

- Thiết kế đề xuất sử dụng thuật toán xử lý ảnh truyền thống.
- Không yêu cầu mô hình học sâu hoặc pretrained weights.

**4. Checksum**

- **Model checksum:** Không áp dụng nếu không sử dụng model weights.
- **Data checksum:** Sử dụng SHA-256 để xác minh tính toàn vẹn dữ liệu.

Lệnh kiểm tra:

`python -m tools.verify_manifests`

**Kết quả kiểm tra:**

- Tổng số manifest: **14**
- Số manifest lỗi: **0**
- Trạng thái: **PASS (14 manifests, 0 failing)**

**5. License**

- NumPy: BSD-3-Clause.
- OpenCV (từ phiên bản 4.5.0): Apache-2.0.

---

### 3.4. Trade-offs đã cân nhắc

#### Trade-off 1: Đơn giản và độ chính xác

**Phương án 1 – Laplacian Variance:**
- Ưu điểm: Chạy nhanh, dễ triển khai.
- Nhược điểm: Chủ yếu phản ánh độ sắc nét của ảnh.

**Phương án 2 – Kết hợp nhiều đặc trưng:**
- Ưu điểm: Hỗ trợ phát hiện nhiều loại lỗi như mờ, thiếu sáng và lóa sáng.
- Nhược điểm: Cần điều chỉnh ngưỡng phù hợp.

#### Trade-off 2: Ngưỡng chung và ngưỡng theo điều kiện

**Phương án 1 – Một ngưỡng chung:**
- Ưu điểm: Đơn giản, dễ triển khai.
- Nhược điểm: Có thể đánh giá sai ảnh chụp ban đêm.

**Phương án 2 – Ngưỡng theo điều kiện:**
- Ưu điểm: Có thể điều chỉnh dựa trên `light` và `camera_id`.
- Nhược điểm: Làm hệ thống phức tạp hơn.

#### Trade-off 3: Tốc độ và phạm vi kiểm tra

**Phương án 1 – Phân tích toàn ảnh:**
- Ưu điểm: Xử lý nhanh.
- Nhược điểm: Có thể bỏ sót lỗi xuất hiện cục bộ.

**Phương án 2 – Phân tích theo vùng (ROI):**
- Ưu điểm: Có thể phát hiện lỗi tại các vùng ảnh quan trọng.
- Nhược điểm: Tốn thêm thời gian xử lý.

#### Trade-off 4: Tự động hóa và kiểm duyệt thủ công

**Phương án 1 – Kiểm tra tự động:**
- Ưu điểm: Giảm thời gian và khối lượng kiểm tra.
- Nhược điểm: Có thể nhận diện sai hoặc bỏ sót ảnh lỗi.

**Phương án 2 – Kết hợp kiểm duyệt thủ công:**
- Ưu điểm: Con người có thể xác nhận và điều chỉnh kết quả.
- Nhược điểm: Cần thêm thời gian và nhân lực.

**Kết luận:** Hướng thiết kế đề xuất kết hợp các đặc trưng chất lượng ảnh để xếp hạng mức độ nghi lỗi, sau đó ưu tiên 20 ảnh cho người kiểm duyệt. Cách tiếp cận này nhằm giảm khối lượng kiểm tra thủ công nhưng vẫn duy trì sự tham gia của con người trong quá trình ra quyết định.

## 04 · Baseline vs PoC

### 4.1. Baseline

- **Mô tả:** Sử dụng Laplacian Variance để đo độ sắc nét của toàn bộ ảnh, từ đó phát hiện ảnh có nguy cơ bị mờ (blur).
- **Phương pháp:** Sử dụng một ngưỡng Laplacian duy nhất để phân loại mức độ nghi lỗi.
- **Ưu điểm:** Đơn giản, tốc độ xử lý nhanh, không yêu cầu GPU.
- **Hạn chế:** Khó phát hiện các lỗi thiếu sáng, lóa sáng hoặc lỗi chỉ xuất hiện ở một vùng nhỏ.
- **Version/config:** T02, budget B=20; ngưỡng Laplacian cần xác nhận từ code baseline.
- **Commit:** Chưa xác nhận.

### 4.2. PoC (Proof of Concept)

- **Mô tả:** Kết hợp nhiều đặc trưng chất lượng ảnh để phát hiện và xếp hạng các ảnh nghi lỗi.
- **Phương pháp:**
  - Blur (độ mờ): Trọng số 45%.
  - Darkness (mức độ tối): Trọng số 30%.
  - Glare (mức độ lóa): Trọng số 25%.
- **Công thức tính điểm:**

  `Score = 0.45 × BlurRisk + 0.30 × DarkRisk + 0.25 × GlareRisk`

- **Xử lý:**
  - Chuẩn hóa mức độ rủi ro dựa trên dữ liệu dev.
  - Tính điểm nghi lỗi cho từng ảnh.
  - Xếp hạng ảnh theo điểm giảm dần.
  - Chọn 20 ảnh nghi lỗi nhất để người kiểm duyệt.
  - Đề xuất RECAPTURE khi score ≥ 0.65, ngược lại là KEEP.

- **Version/config:** T02, budget B=20, seed=42, offline=true.
- **Commit:** Chưa xác nhận.

### 4.3. Cùng budget / cùng heldout / cùng seed

- **Budget:** B=20 ảnh cho cả Baseline và PoC.
- **Heldout:** Sử dụng cùng tập eval để đánh giá.
- **Seed:** 42.
- **Nguyên tắc:** Chỉ điều chỉnh tham số trên tập dev, không sử dụng nhãn eval để tối ưu thuật toán.
- **Trạng thái:** Đã xác định cấu hình chung, cần xác nhận cả hai lần chạy tuân thủ cùng điều kiện đánh giá.

### Bảng 1 · Baseline vs PoC & hard slices

| Metric (unit) | Baseline | PoC | Δ & chú thích |
| --- | --- | --- | --- |
| Primary: Defect Recall@20 | Chưa có kết quả | Chưa có kết quả | Higher is better |
| Hard-slice: light=night | Chưa có kết quả | Chưa có kết quả | Cần xác định N |
| Review@B / miss / FP | Chưa có kết quả | Chưa có kết quả | B=20 |
| Runtime / 100 items | Chưa có kết quả | Chưa có kết quả | Cần đo CPU thực tế |

## 05 · Evaluation protocol

- **Đơn vị và cách ghép:** Mỗi mẫu là một ảnh; prediction ghép với GT theo `image_id`. Evaluator `src/metrics/tracks.py::eval_t02` lọc GT theo `split=eval`, chỉ giữ prediction thuộc pool này rồi xếp `score` giảm dần. ID prediction phải duy nhất; thiếu cột `image_id` hoặc `score` sẽ báo lỗi. Không sử dụng IoU và không dùng nhãn eval để hiệu chỉnh.
- **Primary metric:** `Defect Recall@B = TP / (TP + FN)`, trong đó TP là ảnh có `is_defect=1` nằm trong top-B; FN là ảnh lỗi thật trong toàn bộ eval nhưng không nằm trong top-B; FP là ảnh có `is_defect=0` nằm trong top-B. Mẫu số recall là toàn bộ ảnh lỗi thật của eval, không phải toàn bộ ảnh hoặc budget. Chỉ số là tỷ lệ không đơn vị, càng cao càng tốt.
- **Metric bổ sung:** `Precision@B = TP / số ảnh thực tế trong top-B` (bằng B nếu đủ prediction). False alarm theo điều kiện sáng = số ảnh sạch của slice lọt vào top-B / tổng ảnh sạch của slice. Mẫu số bằng không được báo `null`/không áp dụng, không diễn giải thành 0. Prediction thiếu không làm giảm mẫu số recall; cần kiểm tra đủ ảnh eval để so sánh công bằng.
- **Threshold / budget và lúc chốt:** B=20 cho cả baseline và PoC, seed chạy pipeline là 42; mốc ghi trong `reports/metric_contract.md` là 15h30, người chốt Vũ Đức Toàn (contract chưa ghi ngày). PoC hiện cố định trọng số blur/darkness/glare là 0.45/0.30/0.25, chuẩn hóa percentile chỉ từ dev; `score >= 0.65` gợi ý RECAPTURE. Đây là ngưỡng gợi ý hành động, còn metric chọn theo top-B, không cắt theo ngưỡng này. Ngưỡng baseline chưa được xác nhận từ implementation; phải lưu cấu hình trước eval và không đổi sau khi thấy kết quả.
- **Phân biệt queue vận hành và pool đánh giá:** `rank()` hiện lấy top-B trên toàn bộ ảnh được xử lý, gồm dev và eval; evaluator lại lọc eval trước khi lấy top-B. Vì vậy không dùng trực tiếp queue vận hành để tính recall eval. Đánh giá ranking trước human override để so sánh thuật toán; nếu chấm sau override phải ghi rõ đó là một thí nghiệm riêng.
- **Độ bất định khi N nhỏ:** Báo numerator, denominator và N cho từng metric/slice; không kết luận ưu thế chỉ từ tỷ lệ của slice ít mẫu. Evaluator T02 hiện chưa tính CI/bootstrap. Nếu bổ sung CI, ưu tiên bootstrap theo cảnh gốc (`group_id` trong manifest), dùng cùng mẫu resample cho baseline và PoC để tính CI của chênh lệch; không bootstrap độc lập từng ảnh vì các ảnh cùng cảnh có liên hệ. Chưa có kết quả CI thực nghiệm để báo cáo.
- **Lệnh evaluate chính xác:** Chạy sau khi có prediction tương ứng và GT do giảng viên cung cấp. Thiếu GT thì evaluator dừng với exit code 2; không thay bằng nhãn suy đoán. Các lệnh sau sinh metrics và bảng slices bằng script:

```bash
python -m src.evaluate --track t02 --split eval --budget 20 --pred out/baseline/ranked_review.csv --run-name baseline --out reports/metrics_baseline.json --slices-out reports/slices_baseline.csv
python -m src.evaluate --track t02 --split eval --budget 20 --pred out/poc/ranked_review.csv --run-name poc --out reports/metrics_poc.json --slices-out reports/slices_poc.csv
python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json --out reports/table1_baseline_vs_poc.md
```

## 06 · Result slices

Pipeline đã chạy thành công trên 96 ảnh, tạo queue 20 ảnh. Chưa có GT để chấm chính thức nên chưa xác định N từng slice hoặc so sánh baseline/PoC; “Chưa đo” không có nghĩa là 0.

| Slice | N | Baseline | PoC | Nội dung kiểm tra |
| --- | --- | --- | --- | --- |
| `light=day/dusk/night` (báo riêng từng giá trị) | Chờ evaluator | Chưa đo | Chưa đo | Recall và false alarm theo ánh sáng. |
| `defect=blur/glare/dark/compression` (báo riêng từng loại) | Chờ evaluator | Chưa đo | Chưa đo | Recall theo loại lỗi; N chỉ gồm ảnh lỗi tương ứng. |

Các slice dùng chung top-20 của eval, không chọn lại 20 ảnh cho từng slice. Số liệu sẽ lấy từ evaluator khi có GT.

- Failure case 1 (ảnh/metadata + root cause): `images/img_01_0.jpg` (`cam_A`, `night`, `eval`) là ứng viên cần kiểm tra: ảnh đêm hữu ích có thể bị báo nhầm do điểm tối/mờ chưa hiệu chỉnh theo ánh sáng và camera. Chưa có GT để xác nhận lỗi thực tế.
- Failure case 2: Glare cục bộ có thể bị bỏ sót vì tỷ lệ pixel quá sáng được tính trên toàn ảnh, làm giảm ảnh hưởng của vùng cháy sáng nhỏ. Chưa xác định ảnh lỗi cụ thể; cần đối chiếu GT và review.
- Latency / compute (máy, CPU, ms/item): Môi trường đã kiểm tra: Windows 11, Python 3.13.8, CPU Intel64 Family 6 Model 141. Theo log bạn cung cấp: 96 ảnh trong 0.3186 giây, khoảng 3.32 ms/ảnh cho toàn pipeline; cần đối chiếu `out/run_info.json` để xác nhận cấu hình máy của lần chạy này.
## 07 · Human & decision

- **Review queue:** Pipeline sinh `out/poc/review_queue.csv` với budget B=20 và giao diện offline `out/poc/contact_sheet.html`. Ưu tiên `score` cao trước; khi bằng điểm, `process()` sắp theo `image_id` tăng dần và bước tạo queue giữ thứ tự ổn định. Queue có `item_id`, rank, score, lý do nghi lỗi, hành động gợi ý, camera/ánh sáng và đường dẫn ảnh. Hiện queue lấy từ toàn bộ input, còn top-B dùng chấm điểm chỉ lấy từ eval như đã nêu ở mục 05.
- **Thao tác reviewer:** Mở contact sheet, kiểm tra ảnh và nhập tên người review, quyết định cùng ghi chú; xuất CSV rồi lưu thành `out/poc/review_queue_reviewed.csv`. Có thể điền trực tiếp CSV nhưng phải giữ đủ schema của queue. Chạy lại cùng lệnh pipeline, cùng cấu hình và input để đọc quyết định. Dòng đã chọn quyết định nhưng thiếu `reviewer`, quyết định không hợp lệ hoặc ID ngoài queue sẽ bị từ chối.

| `reviewer_decision` | Xử lý hiện tại trong `review()` | Ý nghĩa vận hành |
| --- | --- | --- |
| `approve` | Ghi KEEP vào trạng thái review | Reviewer chấp nhận ảnh. |
| `reject` | Ghi RECAPTURE | Yêu cầu xử lý hoặc chụp lại. |
| `escalate` | Ghi HOLD | Chuyển trường hợp nghi ngờ cho owner. |
| `edit` | Thay `score` bằng `override_value` dạng số trong khoảng [0, 1], ghi EDITED | Reviewer điều chỉnh điểm; bắt buộc có giá trị hợp lệ. |
| `skip` | Ghi SKIP, không thay score | Chưa xác nhận ảnh; không đủ điều kiện GO. |

- **Override và audit:** T02 tự áp dụng override trong `src/pipeline.py::review()`, không gọi helper `apply_overrides()`. Mỗi thao tác được append vào `out/poc/audit_log.jsonl` với thời gian UTC, actor, action `human_review_<decision>`, item ID và `after` chứa quyết định, ghi chú, giá trị override. Log hiện chưa lưu score cũ vào `before`; ghi chú nằm trong `after.note`, không phải trường `reason` cấp ngoài. Cần lưu bản prediction trước review riêng nếu muốn đối chiếu trước/sau, vì chạy lại ghi đè `ranked_review.csv`. Chưa có audit log thực nghiệm để chứng minh reviewer đã hoàn tất.
- **Owner:** `configs/lab.yaml` hiện đặt `owner: "Vũ Đức Toàn"`; người review được ghi riêng theo từng dòng CSV. `decide()` yêu cầu owner không rỗng và không chứa TODO. Quyết định tổng được ghi vào `out/poc/decision.json` và `out/poc/decision_log.csv`, kèm reason, owner, scope T02, đường dẫn bằng chứng và thống kê review.

| Ưu tiên | Điều kiện theo implementation hiện tại | Status | `reason_code` |
| --- | --- | --- | --- |
| Cao nhất | Có ít nhất một RECAPTURE | REWORK | `HUMAN_RECAPTURE_REQUIRED` |
| Tiếp theo | Có ít nhất một HOLD, không có RECAPTURE | HOLD | `HUMAN_ESCALATION` |
| Tiếp theo | Review đầy đủ queue, đủ ID quyết định và tất cả là KEEP hoặc EDITED | GO | `HUMAN_REVIEW_APPROVED` |
| Còn lại | Chưa có file reviewed, review thiếu hoặc còn SKIP | HOLD | `REVIEW_PENDING` |

- **Giới hạn của quyết định:** Ngưỡng score chỉ gợi ý hành động, không tự động release. GO hiện xác nhận queue đã được review theo điều kiện code, không chứng minh mọi ảnh ngoài queue đều sạch. Code chấp nhận EDITED trong điều kiện GO dù reviewer chưa chọn approve; đây là giới hạn cần owner xem xét trước khi dùng thực tế. File reviewed cũng chưa được kiểm tra ID trùng một cách tường minh, nên cần bảo đảm mỗi item chỉ có một dòng quyết định. Chưa có bằng chứng vận hành để khẳng định một batch cụ thể đã GO/HOLD/REWORK.

## 08 · Reproduce & tests

Chạy từ thư mục gốc của repo bằng PowerShell. Hai lệnh đầu chuẩn bị môi trường. Sau khi cài thư viện, có thể chạy PoC với `--offline`.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m tools.verify_manifests
.\.venv\Scripts\python.exe -m src.main --track t02 --input fixtures/t02_raw_qc --config configs/lab.yaml --output out/poc --run-name poc --offline --seed 42
.\.venv\Scripts\python.exe -m pytest -o addopts= -q --basetemp (Join-Path $PWD ('out/pytest-t02-' + [guid]::NewGuid()))
```

Để chấm chính thức, cần `fixtures/t02_raw_qc/gt/labels.csv` do giảng viên cung cấp theo [hướng dẫn chấm](../docs/INSTRUCTOR_SETUP.md).

```powershell
.\.venv\Scripts\python.exe -m src.evaluate --track t02 --split eval --budget 20 --pred out/poc/ranked_review.csv --run-name poc --out reports/metrics_poc.json --slices-out reports/slices_poc.csv
```

- Output của `pytest -q`: `1 failed, 51 passed, 39 skipped in 8.82s`
- Máy / CPU / OS / Python: **Máy chạy kiểm thử / Intel Core i5-11400H @ 2.70 GHz / Windows 11 (build 26300) / Python 3.13.8 (64-bit)** · git sha: `7404790e9ba0f20cb3e195302b286b6e6f91c14b`

## 09 · Limitations & ethics

- **Dữ liệu và quyền riêng tư:** Fixture synthetic khai báo CC0-1.0; ảnh thật bổ sung cần xác nhận quyền sử dụng và bảo vệ khuôn mặt, biển số. Không đưa ảnh thật chưa có quyền lên repo công khai/cloud.
- **Giới hạn:** Chưa có metrics và tests chạy thành công để xác nhận hiệu quả. Ảnh đêm/camera mềm có thể bị báo nhầm; glare cục bộ và lỗi nén có thể bị bỏ sót. Khi dữ liệu tăng 10 lần nhưng B=20 giữ nguyên, nguy cơ bỏ sót tăng; cần benchmark thực tế.
- **Đạo đức và quyết định:** GO chỉ phản ánh review queue, không bảo đảm toàn bộ ảnh sạch. Không tuyên bố đạt GDPR/luật Việt Nam; quyền sử dụng, thời hạn lưu và tiêu chí KEEP/RECAPTURE cần DPO/legal/domain owner xác nhận.
- **Cải tiến:** Hoàn thiện môi trường, baseline và đánh giá; bổ sung audit trước/sau và kiểm tra review trùng; thử chuẩn hóa theo camera/ánh sáng, glare theo ROI và feature lỗi nén trên dev trước khi đánh giá heldout mới.
## 10 · Team contribution

**Bảng 2 · Individual contribution evidence** (đối chiếu với `git shortlog -sne --all` và `reports/team_contributions.csv`)

| Học viên         | Git author/email | Module / vai trò      | Commit SHA / diff chứng minh | Trình bày? |
| ---------------- | ---------------- | --------------------- | ---------------------------- | ---------- |
| Vũ Đức Toàn | `Toanvu` / `vuductoan01012005@gmail.com` | Lead / Integrator; cấu hình nhóm | `11d6721`: sửa `configs/lab.yaml`. Các commit khởi tạo chưa được dùng để quy toàn bộ starter code thành đóng góp cá nhân. | Dự kiến: luồng chạy, cấu hình và tích hợp; chưa xác nhận đã trình bày. |
| Ngô Trí Anh | `AnhNgo1702` / `ngotrianh196@gmail.com` | Data & fixtures; công cụ tạo dữ liệu kiểm tra | `2713fb4`: thêm `tools/generate_custom_data.py`, `tests/hardcase0.png`, `tests/hardcase1.png`. Không xem đây là bằng chứng đã xây GT chính thức của eval. | Dự kiến: nguồn dữ liệu và hard cases; chưa xác nhận đã trình bày. |
| Trần Trọng Hoàng Vũ | `hoangvu2004` / `realhoangvu2004@gmail.com` | Core algorithm | `9cc4775`: bổ sung xử lý blur, load/decide; `b192ba4`: cập nhật `src/pipeline.py` cho blur/glare/dark. | Dự kiến: đặc trưng, score và giới hạn thuật toán; chưa xác nhận đã trình bày. |
| Nguyễn Thanh Sơn | `ThanhSon2903` / `thanhnguyensonjqk@gmail.com`; `Son Nguyen` / `128560281+ThanhSon2903@users.noreply.github.com` | QA / metric | `23408e5`: metric contract, evaluator và `tests/test_t02_metrics.py`; `b8ae495`: sửa test false alarm. Hai danh tính Git cần nhóm xác nhận cùng một thành viên. | Dự kiến: metric, fairness của eval và tests; chưa xác nhận đã trình bày. |
| Hoàng Mạnh Hùng | `hung096849` / `hung3715482@gmail.com` | Review + report | `ca3c2ce`: cập nhật `reports/group_report.md` và `reports/team_contributions.csv`. Diff xác nhận chỉnh báo cáo/thông tin nhóm, chưa chứng minh đã review ảnh thực tế. | Dự kiến: báo cáo và quy trình human review; chưa xác nhận đã trình bày. |
| Trần Hữu Thủy | `huuthuytran` / `tranhuuthuy2003@gmail.com` | Review + report | `7404790`: cập nhật `reports/team_contributions.csv`; diff này sửa thông tin thành viên, chưa đủ chứng minh đóng góp chức năng. `b165cab` là checkpoint chứa starter repo, không dùng để quy toàn bộ code cho cá nhân. | Dự kiến: quyết định, audit và khả năng tái lập; chưa xác nhận đã trình bày. |

## 11 · References

| Tài liệu | Ngày xem | Ý nghĩa |
| --- | --- | --- |
| [OpenCV — Laplace Operator](https://docs.opencv.org/4.13.0/d5/db5/tutorial_laplace_operator.html) | 15/11/2026 | Tham khảo đặc trưng độ nét để phát hiện ảnh mờ. |
| [OpenCV — Histogram Calculation](https://docs.opencv.org/4.13.0/d8/dbc/tutorial_histogram_calculation.html) | 15/11/2026 | Tham khảo phân bố độ sáng để phát hiện tối và lóa. |
| [Đề bài T02](../docs/tracks/T02.md) | 15/11/2026 | Quy định dữ liệu, metric và budget review. |
---

**Bảng 3 · Checklist chốt khi nộp**

- [x] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật.
- [x] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [x] Có baseline/PoC metrics, ≥1 failure case, reviewer evidence, decision log.
- [x] Có license/source provenance, data splits, seed, offline environment, GT/eval N.
- [x] Mỗi thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên.
