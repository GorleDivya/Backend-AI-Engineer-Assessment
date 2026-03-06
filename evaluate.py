from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from schemas import Extraction


ROOT = Path(__file__).resolve().parent

EVAL_FIELDS = [
    "product_line",
    "origin_port_code",
    "origin_port_name",
    "destination_port_code",
    "destination_port_name",
    "incoterm",
    "cargo_weight_kg",
    "cargo_cbm",
    "is_dangerous",
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def norm_str(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    return str(v).strip().lower()


def norm_float(v: Any) -> Any:
    if v is None:
        return None
    try:
        return round(float(v), 2)
    except Exception:
        return None


def eq_field(field: str, pred: Any, truth: Any) -> bool:
    if field in {"cargo_weight_kg", "cargo_cbm"}:
        return norm_float(pred) == norm_float(truth)
    if isinstance(truth, bool) or field == "is_dangerous":
        return bool(pred) == bool(truth)
    return norm_str(pred) == norm_str(truth)


@dataclass
class Metrics:
    correct: int
    total: int

    @property
    def accuracy(self) -> float:
        return 0.0 if self.total == 0 else self.correct / self.total


def main() -> None:
    gt_path = ROOT / "ground_truth.json"
    pred_path = ROOT / "output.json"

    gt_rows = load_json(gt_path)
    pred_rows = load_json(pred_path)

    gt_by_id = {r["id"]: r for r in gt_rows}
    pred_by_id = {r["id"]: r for r in pred_rows}

    missing = [i for i in gt_by_id.keys() if i not in pred_by_id]
    if missing:
        raise SystemExit(f"output.json missing {len(missing)} ids (e.g. {missing[:3]})")

    # Validate predictions via Pydantic (will also normalize/round).
    validated_pred_by_id: dict[str, dict[str, Any]] = {}
    for _id, row in pred_by_id.items():
        ex = Extraction.model_validate(row)
        validated_pred_by_id[_id] = ex.model_dump()

    per_field: dict[str, Metrics] = {f: Metrics(correct=0, total=0) for f in EVAL_FIELDS}
    overall_correct = 0
    overall_total = 0

    for _id, gt in gt_by_id.items():
        pred = validated_pred_by_id.get(_id, {})
        for f in EVAL_FIELDS:
            per_field[f].total += 1
            overall_total += 1
            ok = eq_field(f, pred.get(f), gt.get(f))
            if ok:
                per_field[f].correct += 1
                overall_correct += 1

    print("Field accuracies:")
    for f in EVAL_FIELDS:
        m = per_field[f]
        print(f"- {f}: {m.correct}/{m.total} = {m.accuracy:.2%}")
    print(f"\nOverall accuracy: {overall_correct}/{overall_total} = {overall_correct/overall_total:.2%}")


if __name__ == "__main__":
    main()

