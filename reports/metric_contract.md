# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T02 - Raw QC Triage |
| Primary metric (tên đúng như evaluator in ra) |Defect Recall@B |
| Tăng tốt hay giảm tốt? | higher |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) |image |
| Công thức + numerator / denominator |Defect Recall@B = số ảnh lỗi thật trong top-B / tổng số ảnh lỗi thật trong eval split |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) |Ghép theo image_id, không sử dụng IoU |
| Candidate pool cố định |Toàn bộ ảnh thuộc eval split trong fixtures/t02_raw_qc/ |
| Review budget B / K |B = 20 ảnh |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) |Chọn threshold trên dev split; không điều chỉnh dựa trên kết quả eval |
| Eval split (không dùng để tune) |eval |
| Chỉ số lỗi xấu (miss / false alarm / false reject) |Miss: ảnh lỗi thật không nằm trong top-20. False alarm: ảnh sạch bị đưa vào top-20 |
| Slices sẽ báo cáo (≥2) |light: day / dusk / night; defect_type: blur / glare / dark / compression |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) |Báo numerator, denominator và tỷ lệ; ghi chú khi số mẫu nhỏ. Có thể bổ sung Wilson 95% CI |
| Ngày giờ chốt + người chốt |15h30 + Vũ Đức Toàn |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.



