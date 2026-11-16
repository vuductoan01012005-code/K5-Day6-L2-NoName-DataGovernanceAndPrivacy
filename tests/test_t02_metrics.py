
from pathlib import Path

import pandas as pd
import pytest

from src.metrics.tracks import TRACKS


def make_t02_data(tmp_path: Path):
    gt = pd.DataFrame([
        {"image_id": "a", "is_defect": 1, "defect_type": "blur",  "light": "night", "split": "eval"},
        {"image_id": "b", "is_defect": 0, "defect_type": "none",  "light": "night", "split": "eval"},
        {"image_id": "c", "is_defect": 1, "defect_type": "glare", "light": "day",   "split": "eval"},
        {"image_id": "d", "is_defect": 0, "defect_type": "none",  "light": "day",   "split": "eval"},
        {"image_id": "e", "is_defect": 0, "defect_type": "none",  "light": "dusk",  "split": "eval"},
        # Dev sample: must not affect evaluation.
        {"image_id": "x", "is_defect": 1, "defect_type": "blur",  "light": "day",   "split": "dev"},
    ])

    pred = pd.DataFrame([
        {"image_id": "x", "score": 1.00, "pred_defect_type": "blur"},
        {"image_id": "b", "score": 0.99, "pred_defect_type": "none"},
        {"image_id": "a", "score": 0.90, "pred_defect_type": "blur"},
        {"image_id": "c", "score": 0.80, "pred_defect_type": "glare"},
        {"image_id": "d", "score": 0.70, "pred_defect_type": "none"},
        {"image_id": "e", "score": 0.60, "pred_defect_type": "none"},
    ])

    gt_path = tmp_path / "labels.csv"
    pred_path = tmp_path / "ranked_review.csv"
    gt.to_csv(gt_path, index=False)
    pred.to_csv(pred_path, index=False)
    return gt_path, pred_path


def metric_value(result, name):
    return next(m.value for m in result.metrics if m.name == name)


def test_t02_recall_precision_and_eval_split(tmp_path):
    gt_path, pred_path = make_t02_data(tmp_path)

    result = TRACKS["t02"].evaluator(
        gt_path, pred_path, {"budget": 2, "split": "eval"}
    )

    # Top 2 in eval: b (clean), a (defect).
    assert metric_value(result, "Defect Recall@B") == pytest.approx(0.5)
    assert metric_value(result, "Precision@B") == pytest.approx(0.5)
    assert metric_value(result, "Defect-type accuracy (GT defects)") == pytest.approx(1.0)

    # The dev image x has score 1.0 but must not enter eval.
    assert "eval N=5" in result.notes[0]


def test_t02_rejects_duplicate_prediction_ids(tmp_path):
    gt_path, pred_path = make_t02_data(tmp_path)

    pred = pd.read_csv(pred_path)
    pred = pd.concat([pred, pred[pred.image_id == "a"]], ignore_index=True)
    pred.to_csv(pred_path, index=False)

    with pytest.raises(ValueError, match="duplicate"):
        TRACKS["t02"].evaluator(
            gt_path, pred_path, {"budget": 2, "split": "eval"}
        )

@pytest.mark.parametrize("columns", [
    ["score"],
    ["image_id"],
])
def test_t02_rejects_missing_required_columns(tmp_path, columns):
    gt_path, pred_path = make_t02_data(tmp_path)

    pred = pd.DataFrame([
        {"image_id": "a", "score": 0.9}
    ])[columns]
    pred.to_csv(pred_path, index=False)

    with pytest.raises(ValueError):
        TRACKS["t02"].evaluator(
            gt_path, pred_path, {"budget": 2, "split": "eval"}
        )

def test_t02_reports_false_alarm_by_light(tmp_path):
    gt_path, pred_path = make_t02_data(tmp_path)

    result = TRACKS["t02"].evaluator(
        gt_path, pred_path, {"budget": 2, "split": "eval"}
    )

    slices = result.slices.set_index("slice")

    assert slices.loc["light=night", "false_alarm_in_topB"] == pytest.approx(1.0)
    assert slices.loc["light=day", "false_alarm_in_topB"] == pytest.approx(0.0)
    assert slices.loc["light=dusk", "false_alarm_in_topB"] == pytest.approx(0.0)