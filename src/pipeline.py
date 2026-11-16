"""YOUR PoC PIPELINE — this is the file your group owns.

Lab contract = 5 automated steps, run by `python -m src.main ...`:
    01 load      input + provenance check (manifest.csv)
    02 process   your algorithm / model (the research part)
    03 rank      prioritise for a fixed review budget B
    04 review    human-in-the-loop: queue -> reviewer decisions -> overrides + audit log
    05 decide    GO / HOLD / REWORK (or track equivalent) with reason_code + owner, write outputs

Required output: out/<pred_file> with the columns listed for your track in
docs/tracks/TXX.md (also in src/metrics/tracks.py::TRACKS). Then evaluate with
    python -m src.evaluate --track tXX --pred out/<pred_file>

Rules: never read fixtures/*/gt/ here (the GT guard will stop you); seed everything via ctx.rng;
no network calls; fail loudly on missing models instead of downloading.
See src/examples/random_baseline.py for a minimal end-to-end wiring example.
"""

from __future__ import annotations

import pandas as pd

from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.manifest import verify_manifest
from .common.review import load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    data = {"manifest": pd.read_csv(manifest) if manifest.exists() else None,"images": pd.read_csv(ctx.input_dir / "images.csv")
    }
    # TODO: load the tables/images your track needs, e.g.
    # data["images"] = pd.read_csv(ctx.input_dir / "images.csv")
    return data


# ---------------------------------------------------------------- 02 process
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



# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    """Default: top-B by `score`. Adapt id/score/reason columns to your track."""
    budget = int(ctx.param("budget", 20))
    if "score" not in scored.columns:
        raise ValueError("rank(): process() output needs a numeric `score` column (higher = review first), "
                         "or adapt rank() to your track")
    q = make_review_queue(scored, id_col=scored.columns[0], score_col="score", budget=budget,
                          reason_col="reason" if "reason" in scored.columns else None)
    write_review_queue(q, ctx.out("review_queue.csv"))
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    """If a reviewed queue exists (out/review_queue_reviewed.csv), apply it. Otherwise pass through.

    TODO: decide what an `edit` / `reject` means for your track and apply it
    (e.g. via common.review.apply_overrides), logging every change to ctx.audit.
    """
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    if reviewed_path.exists():
        reviewed = load_review_decisions(reviewed_path)
        ctx.stats["n_reviewed"] = len(reviewed)
        # TODO: apply overrides
    return scored


# ---------------------------------------------------------------- 05 decide

def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    return Decision(
        status="GO",
        reason_code="PILOT_RUN",
        reason="Baseline pipeline completed successfully",
        owner=ctx.config.get("owner", "G00"),
        scope=ctx.track
    )
# def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
#     # TODO: replace with your policy (thresholds frozen BEFORE looking at eval results)
#     return Decision(status="HOLD", reason_code="POLICY_NOT_IMPLEMENTED", reason="Decision policy not implemented yet",
#                     owner=ctx.config.get("owner", "TODO-owner"), scope=ctx.track)


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)
    final[spec.pred_columns + [c for c in final.columns if c not in spec.pred_columns]].to_csv(ctx.out(spec.pred_file), index=False)
    write_decision(decide(ctx, final), ctx.out("decision.json"), ctx.out("decision_log.csv"))
