
"""T02 Raw QC Triage pipeline.

Stages:
1. Load metadata and verify provenance.
2. Extract image-quality features and calculate suspicion scores.
3. Rank the top-B images for human review.
4. Apply human review decisions and write audit events.
5. Produce a GO / HOLD / REWORK decision.

The pipeline never reads ground-truth files.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.manifest import verify_manifest
from .common.image_ops import to_gray, laplacian_variance
from .common.review import (
    load_review_decisions,
    make_review_queue,
    write_review_queue,
)
from .common.contact_sheet import render_contact_sheet
from .metrics.tracks import get_track


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def _log(ctx, actor: str, action: str, item_id: str, after=None):
    """Write an audit event when an AuditLog is available."""
    if ctx.audit is not None:
        ctx.audit.log(
            actor=actor,
            action=action,
            item_id=str(item_id),
            after=after,
        )


def _image_path(input_dir: Path, relative_path: str) -> Path:
    """Resolve an image path safely inside the input directory."""
    root = input_dir.resolve()
    path = (root / relative_path).resolve()

    if not path.is_relative_to(root):
        raise ValueError(f"Image path escapes input directory: {relative_path}")

    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")

    return path


def _risk_from_dev(values, dev_values, low_is_risk=False):
    """Convert a feature into a 0..1 risk score using dev distribution only."""
    reference = np.sort(np.asarray(dev_values, dtype=float))
    current = np.asarray(values, dtype=float)

    if len(reference) == 0:
        raise ValueError("Cannot calibrate risk without dev images")

    percentile = np.searchsorted(
        reference, current, side="right"
    ) / len(reference)

    if low_is_risk:
        return 1.0 - percentile

    return percentile


# ---------------------------------------------------------
# 01 LOAD
# ---------------------------------------------------------

def load(ctx: RunContext) -> dict:
    """Verify manifest and load image metadata."""

    input_dir = ctx.input_dir

    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    manifest_path = input_dir / "manifest.csv"
    images_path = input_dir / "images.csv"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")

    if not images_path.exists():
        raise FileNotFoundError(f"Missing images.csv: {images_path}")

    problems = verify_manifest(manifest_path)

    if problems:
        _log(
            ctx,
            actor="pipeline",
            action="provenance_problems",
            item_id=str(manifest_path),
            after=problems[:20],
        )

        if ctx.config.get("strict_provenance", True):
            raise ValueError(
                f"Manifest verification failed: {len(problems)} problem(s). "
                f"First problems: {problems[:3]}"
            )

    images = pd.read_csv(images_path)

    required = {
        "image_id",
        "path",
        "camera_id",
        "light",
        "split",
    }

    missing = required - set(images.columns)

    if missing:
        raise ValueError(
            f"images.csv missing columns: {sorted(missing)}"
        )

    if images.empty:
        raise ValueError("images.csv contains no images")

    if images["image_id"].duplicated().any():
        raise ValueError("Duplicate image_id found in images.csv")

    images["image_id"] = images["image_id"].astype(str)
    images["path"] = images["path"].astype(str)
    images["split"] = images["split"].astype(str).str.lower()

    if not images["split"].isin(["dev", "eval"]).all():
        raise ValueError("Unexpected split value; expected dev/eval")

    ctx.stats["manifest_verified"] = not problems
    ctx.stats["n_manifest_problems"] = len(problems)
    ctx.stats["n_images_loaded"] = len(images)

    _log(
        ctx,
        actor="pipeline",
        action="load_images_metadata",
        item_id="images.csv",
        after={"n_images": len(images)},
    )

    return {
        "manifest": pd.read_csv(manifest_path),
        "images": images,
    }


# ---------------------------------------------------------
# 02 PROCESS
# ---------------------------------------------------------

def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    """Extract image-quality features and calculate suspicion scores.

    Higher score means more suspicious.

    Feature weights are fixed before evaluation:
    - Blur risk: 45%
    - Darkness risk: 30%
    - Glare risk: 25%

    Risk percentiles are calibrated using dev images only.
    """

    if ctx.track != "t02":
        raise ValueError(
            f"This pipeline implements T02 only, not {ctx.track}"
        )

    images = data["images"].copy()
    records = []

    for row in images.itertuples(index=False):
        image_path = _image_path(ctx.input_dir, row.path)

        with Image.open(image_path) as source:
            rgb = np.asarray(source.convert("RGB"))

        gray = to_gray(rgb)

        # Blur feature: low Laplacian variance means less sharp.
        sharpness = float(laplacian_variance(gray))

        # Brightness and glare features.
        gray_float = np.asarray(gray, dtype=np.float32)
        brightness_mean = float(gray_float.mean())
        brightness_std = float(gray_float.std())

        frac_dark = float(np.mean(gray_float < 30))
        frac_saturated = float(np.mean(gray_float > 245))

        records.append({
            "image_id": str(row.image_id),
            "path": str(row.path),
            "camera_id": str(row.camera_id),
            "light": str(row.light),
            "split": str(row.split),
            "sharpness": sharpness,
            "brightness_mean": brightness_mean,
            "brightness_std": brightness_std,
            "frac_dark": frac_dark,
            "frac_saturated": frac_saturated,
            "evidence_path": str(image_path),
        })

    features = pd.DataFrame(records)

    dev = features[features["split"] == "dev"]

    if dev.empty:
        raise ValueError("No dev images available for calibration")

    # All calibration distributions come from dev, never eval.
    blur_risk = _risk_from_dev(
        features["sharpness"],
        dev["sharpness"],
        low_is_risk=True,
    )

    dark_risk = _risk_from_dev(
        features["frac_dark"],
        dev["frac_dark"],
        low_is_risk=False,
    )

    glare_risk = _risk_from_dev(
        features["frac_saturated"],
        dev["frac_saturated"],
        low_is_risk=False,
    )

    # Fixed weighted combination.
    features["score"] = (
        0.45 * blur_risk
        + 0.30 * dark_risk
        + 0.25 * glare_risk
    )

    # Identify the dominant signal for human review.
    risk_matrix = np.column_stack([
        blur_risk,
        dark_risk,
        glare_risk,
    ])

    risk_names = np.array([
        "BLUR_SUSPECT",
        "DARK_IMAGE",
        "GLARE_SUSPECT",
    ])

    features["reason"] = risk_names[
        np.argmax(risk_matrix, axis=1)
    ]

    features["suggested_action"] = np.where(
        features["score"] >= 0.65,
        "RECAPTURE",
        "KEEP",
    )

    features["slice"] = (
        "camera=" + features["camera_id"]
        + ";light=" + features["light"]
    )

    features = features.sort_values(
        ["score", "image_id"],
        ascending=[False, True],
        kind="mergesort",
    ).reset_index(drop=True)

    ctx.stats["n_dev"] = len(dev)
    ctx.stats["feature_weights"] = {
        "blur": 0.45,
        "darkness": 0.30,
        "glare": 0.25,
    }
    ctx.stats["score_threshold_for_recapture"] = 0.65
    ctx.stats["mean_score"] = float(features["score"].mean())

    _log(
        ctx,
        actor="pipeline",
        action="process_images",
        item_id="T02",
        after={
            "n_images": len(features),
            "n_dev": len(dev),
            "features": [
                "sharpness",
                "brightness_mean",
                "brightness_std",
                "frac_dark",
                "frac_saturated",
            ],
        },
    )

    return features


# ---------------------------------------------------------
# 03 RANK
# ---------------------------------------------------------

def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    """Create the top-B review queue and an offline contact sheet."""

    budget = int(ctx.param("budget", 20))

    if budget <= 0:
        raise ValueError("Review budget must be positive")

    queue = make_review_queue(
        scored,
        id_col="image_id",
        score_col="score",
        budget=budget,
        reason_col="reason",
        action_col="suggested_action",
        slice_col="slice",
        evidence_col="evidence_path",
        ascending=False,
    )

    write_review_queue(
        queue,
        ctx.out("review_queue.csv"),
    )

    render_contact_sheet(
        queue,
        ctx.out("contact_sheet.html"),
        image_col="evidence_path",
        fields=(
            "rank",
            "item_id",
            "score",
            "reason",
            "suggested_action",
            "slice",
        ),
        title="T02 - Raw QC Human Review",
    )

    ctx.stats["review_budget"] = budget
    ctx.stats["n_review_queue"] = len(queue)

    _log(
        ctx,
        actor="pipeline",
        action="create_review_queue",
        item_id="review_queue.csv",
        after={"budget": budget, "n_items": len(queue)},
    )

    return queue


# ---------------------------------------------------------
# 04 REVIEW
# ---------------------------------------------------------

def review(
    ctx: RunContext,
    scored: pd.DataFrame,
    queue: pd.DataFrame,
) -> pd.DataFrame:
    """Apply human review decisions when a reviewed CSV exists.

    approve  -> KEEP
    reject   -> RECAPTURE
    escalate -> HOLD
    edit     -> update score using numeric override_value
    skip     -> no change
    """

    final = scored.copy()

    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"

    decisions = {}

    if not reviewed_path.exists():
        ctx.stats["n_reviewed"] = 0
        ctx.stats["review_complete"] = False
        ctx.stats["review_decisions"] = decisions
        return final

    reviewed = load_review_decisions(reviewed_path)

    valid_ids = set(queue["item_id"].astype(str))

    for row in reviewed.itertuples(index=False):
        item_id = str(row.item_id)
        decision = str(row.reviewer_decision).lower()
        reviewer = str(row.reviewer)
        note = str(row.review_note)

        if item_id not in valid_ids:
            raise ValueError(
                f"Reviewed image {item_id} is not in the review queue"
            )

        if item_id not in set(final["image_id"].astype(str)):
            raise ValueError(f"Unknown image_id in review: {item_id}")

        if decision == "approve":
            decisions[item_id] = "KEEP"

        elif decision == "reject":
            decisions[item_id] = "RECAPTURE"

        elif decision == "escalate":
            decisions[item_id] = "HOLD"

        elif decision == "edit":
            value = str(row.override_value).strip()

            if not value:
                raise ValueError(
                    f"Edit decision for {item_id} needs numeric override_value"
                )

            try:
                new_score = float(value)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid score override for {item_id}: {value}"
                ) from exc

            if not 0 <= new_score <= 1:
                raise ValueError(
                    f"Override score must be between 0 and 1: {item_id}"
                )

            mask = final["image_id"].astype(str) == item_id
            final.loc[mask, "score"] = new_score
            decisions[item_id] = "EDITED"

        elif decision == "skip":
            decisions[item_id] = "SKIP"

        _log(
            ctx,
            actor=reviewer,
            action=f"human_review_{decision}",
            item_id=item_id,
            after={
                "decision": decision,
                "note": note,
                "override_value": str(row.override_value),
            },
        )

    ctx.stats["n_reviewed"] = len(reviewed)
    ctx.stats["review_complete"] = len(reviewed) == len(queue)
    ctx.stats["review_decisions"] = decisions

    return final


# ---------------------------------------------------------
# 05 DECIDE
# ---------------------------------------------------------

def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    """Produce an auditable release/recapture decision."""

    owner = str(ctx.config.get("owner", "")).strip()

    if not owner or "TODO" in owner.upper():
        raise ValueError(
            "Please replace the TODO owner in configs/lab.yaml "
            "with the actual reviewer name/role."
        )

    decisions = ctx.stats.get("review_decisions", {})
    values = list(decisions.values())

    evidence = [
        str(ctx.output_dir / "ranked_review.csv"),
        str(ctx.output_dir / "review_queue.csv"),
        str(ctx.output_dir / "contact_sheet.html"),
        str(ctx.output_dir / "audit_log.jsonl"),
    ]

    metrics = {
        "n_images": int(len(final)),
        "n_reviewed": int(ctx.stats.get("n_reviewed", 0)),
        "review_budget": int(ctx.param("budget", 20)),
        "mean_score": float(final["score"].mean()),
    }

    if "RECAPTURE" in values:
        return Decision(
            status="REWORK",
            reason_code="HUMAN_RECAPTURE_REQUIRED",
            reason="Human review identified one or more images requiring recapture.",
            owner=owner,
            scope="T02",
            evidence=evidence,
            metrics=metrics,
        )

    if "HOLD" in values:
        return Decision(
            status="HOLD",
            reason_code="HUMAN_ESCALATION",
            reason="One or more images were escalated for further review.",
            owner=owner,
            scope="T02",
            evidence=evidence,
            metrics=metrics,
        )

    budget = int(ctx.param("budget", 20))

    if (
        ctx.stats.get("review_complete", False)
        and len(values) == min(budget, len(final))
        and all(v in {"KEEP", "EDITED"} for v in values)
    ):
        return Decision(
            status="GO",
            reason_code="HUMAN_REVIEW_APPROVED",
            reason="All images in the review queue were approved by the reviewer.",
            owner=owner,
            scope="T02",
            evidence=evidence,
            metrics=metrics,
        )

    return Decision(
        status="HOLD",
        reason_code="REVIEW_PENDING",
        reason="Human review is incomplete; further review is required.",
        owner=owner,
        scope="T02",
        evidence=evidence,
        metrics=metrics,
    )

    dark_risk = _risk_from_dev(
        features["frac_dark"],
        dev["frac_dark"],
        low_is_risk=False,
    )

    glare_risk = _risk_from_dev(
        features["frac_saturated"],
        dev["frac_saturated"],
        low_is_risk=False,
    )

    # Fixed weighted combination.
    features["score"] = (
        0.45 * blur_risk
        + 0.30 * dark_risk
        + 0.25 * glare_risk
    )

    # Identify the dominant signal for human review.
    risk_matrix = np.column_stack([
        blur_risk,
        dark_risk,
        glare_risk,
    ])

    risk_names = np.array([
        "BLUR_SUSPECT",
        "DARK_IMAGE",
        "GLARE_SUSPECT",
    ])

    features["reason"] = risk_names[
        np.argmax(risk_matrix, axis=1)
    ]

    features["suggested_action"] = np.where(
        features["score"] >= 0.65,
        "RECAPTURE",
        "KEEP",
    )

    features["slice"] = (
        "camera=" + features["camera_id"]
        + ";light=" + features["light"]
    )

    features = features.sort_values(
        ["score", "image_id"],
        ascending=[False, True],
        kind="mergesort",
    ).reset_index(drop=True)

    ctx.stats["n_dev"] = len(dev)
    ctx.stats["feature_weights"] = {
        "blur": 0.45,
        "darkness": 0.30,
        "glare": 0.25,
    }
    ctx.stats["score_threshold_for_recapture"] = 0.65
    ctx.stats["mean_score"] = float(features["score"].mean())

    _log(
        ctx,
        actor="pipeline",
        action="process_images",
        item_id="T02",
        after={
            "n_images": len(features),
            "n_dev": len(dev),
            "features": [
                "sharpness",
                "brightness_mean",
                "brightness_std",
                "frac_dark",
                "frac_saturated",
            ],
        },
    )

    return features



# ---------------------------------------------------------
# RUN
# ---------------------------------------------------------

def run(ctx: RunContext) -> None:
    """Execute the complete T02 pipeline."""

    spec = get_track(ctx.track)

    if ctx.track != "t02":
        raise ValueError("src.pipeline.py currently supports T02 only")

    data = load(ctx)

    scored = process(ctx, data)

    ctx.stats["n_items"] = len(scored)

    queue = rank(ctx, scored)

    final = review(ctx, scored, queue)

    # Required output columns: image_id, score.
    output_columns = (
        spec.pred_columns
        + [
            col for col in final.columns
            if col not in spec.pred_columns
        ]
    )

    final[output_columns].to_csv(
        ctx.out(spec.pred_file),
        index=False,
    )

    decision = decide(ctx, final)

    write_decision(
        decision,
        ctx.out("decision.json"),
        ctx.out("decision_log.csv"),
    )

    print("T02 pipeline completed.")
    print(f"Images processed : {len(final)}")
    print(f"Review queue     : {len(queue)}")
    print(f"Prediction file  : {ctx.out(spec.pred_file)}")
    print(f"Decision         : {decision.status}")
