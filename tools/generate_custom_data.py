import os
import csv
import glob
import hashlib
import random
import cv2
import numpy as np

# Cố định seed theo quy tắc bài lab
SEED = 42
random.seed(SEED)
np.random.seed(SEED)

INPUT_DIR = "data/real/raw_clean"
OUT_IMG_DIR = "data/real/custom_t02/images"
OUT_GT_CSV = "data/real/custom_t02/ground_truth.csv"
OUT_INPUT_CSV = "data/real/custom_t02/images.csv"

os.makedirs(OUT_IMG_DIR, exist_ok=True)


def compute_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def apply_blur(img, severity=1):
    # severity 1: mờ vừa (kernel 11), severity 2: mờ nặng (kernel 21)
    ksize = 11 if severity == 1 else 21
    return cv2.GaussianBlur(img, (ksize, ksize), 0)


def apply_dark(img, severity=1):
    # severity 1: thiếu sáng vừa (gamma/scale 0.35), severity 2: tối nặng (0.18)
    factor = 0.35 if severity == 1 else 0.18
    return np.clip(img.astype(np.float32) * factor, 0, 255).astype(np.uint8)


def apply_glare(img, severity=1):
    # Tạo quầng sáng lóa trắng cục bộ (mô phỏng đèn pha hoặc nắng gắt)
    out = img.copy().astype(np.float32)
    h, w, _ = out.shape
    cx = random.randint(int(w * 0.25), int(w * 0.75))
    cy = random.randint(int(h * 0.25), int(h * 0.75))
    radius = int(min(h, w) * (0.18 if severity == 1 else 0.30))

    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
    mask = np.clip(1.0 - (dist / radius), 0, 1) ** 1.5
    intensity = 220 if severity == 1 else 255

    for c in range(3):
        out[:, :, c] = np.clip(out[:, :, c] + mask * intensity, 0, 255)
    return out.astype(np.uint8)


def main():
    raw_files = sorted(
        glob.glob(os.path.join(INPUT_DIR, "*.*"))
    )
    raw_files = [
        f for f in raw_files if f.lower().endswith((".png", ".jpg", ".jpeg"))
    ]

    if not raw_files:
        print(f"Không tìm thấy ảnh nào trong {INPUT_DIR}")
        return

    # Chia split 60% dev / 40% eval theo ảnh gốc (parent_id) để chống data leakage
    num_dev = int(len(raw_files) * 0.6)

    gt_rows = []
    input_rows = []

    for idx, filepath in enumerate(raw_files):
        img = cv2.imread(filepath)
        if img is None:
            continue

        parent_id = f"custom_{idx:02d}"
        split = "dev" if idx < num_dev else "eval"
        sev = random.choice([1, 2])  # Ngẫu nhiên mức độ lỗi nhẹ (1) hoặc nặng (2)

        variants = [
            ("clean", 0, img),
            ("blur", sev, apply_blur(img, sev)),
            ("dark", sev, apply_dark(img, sev)),
            ("glare", sev, apply_glare(img, sev)),
        ]

        for v_idx, (defect_type, severity, out_img) in enumerate(variants):
            file_id = f"{parent_id}_{v_idx}"
            filename = f"{file_id}.png"
            out_path = os.path.join(OUT_IMG_DIR, filename)

            # Lưu dạng PNG để giữ nguyên độ nét chuẩn của từng biến thể
            cv2.imwrite(out_path, out_img)
            sha = compute_sha256(out_path)

            is_defect = 1 if defect_type != "clean" else 0
            gt_rows.append(
                [file_id, parent_id, split, defect_type, severity, is_defect]
            )
            input_rows.append(
                [file_id, f"images/{filename}", parent_id, split, sha]
            )

    # Xuất ground_truth.csv (dùng nội bộ để nhóm tự chấm điểm)
    with open(OUT_GT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["file_id", "parent_id", "split", "defect_type", "severity", "is_defect"]
        )
        writer.writerows(gt_rows)

    # Xuất images.csv (đúng format input cho pipeline)
    with open(OUT_INPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["file_id", "path", "group_id", "split", "sha256"])
        writer.writerows(input_rows)

    print(f"Hoàn tất! Đã tạo {len(gt_rows)} ảnh từ {len(raw_files)} ảnh gốc.")
    print(f"- File ảnh: {OUT_IMG_DIR}")
    print(f"- Ground truth nội bộ: {OUT_GT_CSV}")


if __name__ == "__main__":
    main()