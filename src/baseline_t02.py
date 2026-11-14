
"""T02 baseline: one global Laplacian threshold for image blur triage.

- Uses dev images only to estimate the global threshold.
- Does not read ground-truth labels.
- Higher score means more suspicious (lower sharpness).
"""
from pathlib import Path
import argparse

import numpy as np
import pandas as pd

from src.common.image_ops import load_rgb, to_gray, laplacian_variance
from src.common.manifest import verify_manifest


def run_baseline(input_dir: Path, output_file: Path) -> None:
    input_dir = input_dir.resolve()
    images_csv = input_dir / "images.csv"
    manifest_csv = input_dir / "manifest.csv"

    if not images_csv.exists():
        raise FileNotFoundError(f"Missing input file: {images_csv}")

    if not manifest_csv.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_csv}")

    # Verify file provenance and hashes before processing.
    problems = verify_manifest(manifest_csv)
    if problems:
        raise ValueError(
            "Manifest verification failed:\n"
            + "\n".join(str(problem) for problem in problems[:10])
        )

    images = pd.read_csv(images_csv)

    required_columns = {"image_id", "path", "split"}
    missing = required_columns - set(images.columns)
    if missing:
        raise ValueError(f"images.csv is missing columns: {sorted(missing)}")

    if images["image_id"].duplicated().any():
        raise ValueError("images.csv contains duplicate image_id values")

    # Calculate full-image sharpness for every image.
    rows = []

    for row in images.itertuples(index=False):
        relative_path = Path(str(row.path))
        image_path = input_dir / relative_path

        # Also support CSV paths that contain only the image filename.
        if not image_path.exists():
            image_path = input_dir / "images" / relative_path.name

        if not image_path.exists():
            raise FileNotFoundError(
                f"Image not found for {row.image_id}: {row.path}"
            )

        image = load_rgb(image_path)
        gray = to_gray(image)
        sharpness = float(laplacian_variance(gray))

        rows.append({
            "image_id": str(row.image_id),
            "split": str(row.split),
            "sharpness": sharpness,
        })

    features = pd.DataFrame(rows)

    # Estimate ONE global threshold using dev data only.
    dev_sharpness = features.loc[
        features["split"].str.lower() == "dev",
        "sharpness",
    ]

    if dev_sharpness.empty:
        raise ValueError("No dev images found; cannot estimate threshold.")

    # Lower 25th percentile is the baseline blur threshold.
    threshold = float(np.percentile(dev_sharpness, 25))

    # Lower sharpness => higher suspicion score.
    # Keep the continuous score so images can be ranked.
    features["score"] = threshold - features["sharpness"]

    # Stable descending order: highest suspicion first.
    predictions = (
        features.sort_values(
            ["score", "image_id"],
            ascending=[False, True],
            kind="mergesort",
        )
        [["image_id", "score"]]
        .reset_index(drop=True)
    )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(output_file, index=False)

    print("T02 baseline completed.")
    print(f"Images processed : {len(predictions)}")
    print(f"Dev images       : {len(dev_sharpness)}")
    print(f"Global threshold : {threshold:.4f}")
    print(f"Output           : {output_file.resolve()}")
    print("\nTop 20 suspicious images:")
    print(predictions.head(20).to_string(index=False))


def main():
    parser = argparse.ArgumentParser(
        description="T02 global Laplacian baseline"
    )
    parser.add_argument(
        "--input",
        default="fixtures/t02_raw_qc",
        help="T02 input directory",
    )
    parser.add_argument(
        "--output",
        default="out/baseline/ranked_review.csv",
        help="Prediction CSV output path",
    )
    args = parser.parse_args()

    run_baseline(Path(args.input), Path(args.output))


if __name__ == "__main__":
    main()
