# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Điền đầy đủ, cụ thể, không viết chung chung. Mọi con số phải lấy từ file do script sinh ra
> (`reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`) — không gõ tay, không làm tròn mất đơn vị.
> 3–5 trang (hoặc README + report.md tương đương).

## 00 · Header

| Mục                        | Giá trị                                                                                                                                                  |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Group ID                   | G\_\_                                                                                                                                                    |
| Challenge                  | T** · ********\_\_\_\_**********                                                                                                                         |
| Thành viên (5–6) + vai trò | 1. \_**\_ (Lead/Integrator) · 2. \_\_** (Data & fixtures) · 3. \_**\_ (Core algorithm) · 4. \_\_** (QA/metric) · 5. \_**\_ (Review + report) · 6. \_\_** |
| Git URL                    | \_\_\_\_                                                                                                                                                 |
| Tag `demo-180m` (commit)   | \_\_\_\_                                                                                                                                                 |
| Tag `final-24h` (commit)   | \_\_\_\_                                                                                                                                                 |
| Deadline (giờ VN)          | \_\_\_\_                                                                                                                                                 |

## 01 · Problem statement

- Ai bị ảnh hưởng / ai chịu hậu quả khi hệ thống sai? \_\_\_\_
- Điểm nghẽn cụ thể: \_\_\_\_
- Đầu vào → đầu ra: \_\_\_\_
- Tiêu chí GO / HOLD / REWORK (chốt trước khi chạy eval): \_\_\_\_
- Giả định của nhóm (cần DPO/legal/domain owner xác nhận): \_\_\_\_

## 02 · Data & provenance

| Split          | N   | Nguồn / link | License | Synthetic? |
| -------------- | --- | ------------ | ------- | ---------- |
| dev            |     |              |         |            |
| eval / heldout |     |              |         |            |

- Schema & class mapping: \_\_\_\_
- Seed: 42 · Cách chia split (theo scene/group/segment?): \_\_\_\_
- `manifest.csv` verified (sha256): có / không — lệnh: `python -m tools.verify_manifests`
- Dữ liệu thật dùng (nếu có) và cách xây GT cho nó: \_\_\_\_

## 03 · Research & design

- 2–3 references (URL + ngày xem) và **vì sao** chọn kỹ thuật: \_\_\_\_
- Sơ đồ data flow (input → process → rank/QC → review → decision → report): \_\_\_\_
- Thành phần offline (model/weights + checksum + license nếu có): \_\_\_\_
- Trade-offs đã cân nhắc: \_\_\_\_

## 04 · Baseline vs PoC

- Baseline (mô tả, version/config, commit): \_\_\_\_
- PoC (mô tả, version/config, commit): \_\_\_\_
- Cùng budget / cùng heldout / cùng seed: xác nhận \_\_\_\_

**Bảng 1 · Baseline vs PoC & hard slices** — dán output của
`python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json`:

| Metric (unit)        | Baseline | PoC      | Δ & chú thích           |
| -------------------- | -------- | -------- | ----------------------- |
| Primary: **\_\_**    | \_\_\_\_ | \_\_\_\_ | \_\_\_\_; higher/lower? |
| Hard-slice: **\_\_** | \_\_\_\_ | \_\_\_\_ | \_**\_; N=**            |
| Review@B / miss / FP | \_\_\_\_ | \_\_\_\_ | \_**\_; B=**            |
| Runtime / 100 items  | \_\_\_\_ | \_\_\_\_ | \_**\_; CPU=**          |

## 05 · Evaluation protocol

- Công thức primary metric, đơn vị đánh giá, TP/FP/FN, denominator: \_\_\_\_ (xem `reports/metric_contract.md`)
- Threshold / budget B / K và lúc chốt: \_\_\_\_
- Độ bất định (CI/bootstrap/variance) khi N nhỏ: \_\_\_\_
- Lệnh evaluate chính xác: `python -m src.evaluate --track t__ --pred ... --out ...`

## 06 · Result slices

| Slice | N   | Baseline | PoC | Ghi chú |
| ----- | --- | -------- | --- | ------- |
|       |     |          |     |         |
|       |     |          |     |         |

- Failure case 1 (ảnh/metadata + root cause): \_\_\_\_
- Failure case 2: \_\_\_\_
- Latency / compute (máy, CPU, ms/item): \_\_\_\_

## 07 · Human & decision

- Review queue (file, B, cách ưu tiên): \_\_\_\_
- Cách override + audit log (`out/audit_log.jsonl`): \_\_\_\_
- Decision policy + `reason_code` + owner: \_\_\_\_
- Khi nào HOLD/REWORK thay vì tự động release: \_\_\_\_

## 08 · Reproduce & tests

```bash
make setup          # hoặc: python -m venv .venv && pip install -r requirements.txt
python -m src.main --input fixtures/<track> --config configs/lab.yaml --output out/ --offline --seed 42
python -m src.evaluate --track t__ --pred out/<file> --out reports/metrics_poc.json
pytest -q
```

- Output của `pytest -q`: \_\_\_\_
- Máy / CPU / OS / Python: \_**\_ · git sha: \_\_**

## 09 · Limitations & ethics

- Rủi ro pháp lý / PII / license: \_\_\_\_
- Điều chưa biết; false alarms; nếu scale 10× thì sao: \_\_\_\_
- Không tuyên bố "đạt GDPR / luật Việt Nam" từ checklist tự động; giả định cần DPO/legal xác nhận: \_\_\_\_
- Kế hoạch cải tiến: \_\_\_\_

## 10 · Team contribution

**Bảng 2 · Individual contribution evidence** (đối chiếu với `git shortlog -sne --all` và `reports/team_contributions.csv`)

| Học viên         | Git author/email | Module / vai trò      | Commit SHA / diff chứng minh | Trình bày? |
| ---------------- | ---------------- | --------------------- | ---------------------------- | ---------- |
| Vũ Đức Toàn      |                  | Integration / CLI     |                              |            |
| Ngô Trí Anh      |                  | Data + GT             |                              |            |
| Hoàng Vũ         |                  | Core algorithm        |                              |            |
| Nguyễn Thanh Sơn |                  | Metric + tests        |                              |            |
| Hữu Thủy         |                  | Review queue + report |                              |            |
| Mạnh Hùng        |                  | Review queue + report |                              |            |

## 11 · References

| URL | Ngày xem | 1–2 dòng ý nghĩa (không chép nguyên văn) |
| --- | -------- | ---------------------------------------- |
|     |          |                                          |

---

**Bảng 3 · Checklist chốt khi nộp**

- [x] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật.
- [x] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [x] Có baseline/PoC metrics, ≥1 failure case, reviewer evidence, decision log.
- [x] Có license/source provenance, data splits, seed, offline environment, GT/eval N.
- [x] Mỗi thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên.
