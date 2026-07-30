"""Lightweight rule-based evaluator for interaction-threshold model outputs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

from common import DEFAULT_EVALUATIONS_ROOT, DEFAULT_EXECUTION_OUTPUT_ROOT, relative_to_repo

RUN_SUMMARY_COLUMNS = [
    "coefficient",
    "condition_name",
    "model_id",
    "run_id",
    "status",
    "detected_true_interaction",
    "detected_wrong_interaction",
    "false_positive_interaction",
    "mentions_interaction",
    "mentions_x4",
    "mentions_x5",
    "conclusion_says_no_interaction",
    "notes",
    "output_file",
]

AGGREGATE_COLUMNS = [
    "coefficient",
    "n_runs",
    "n_success",
    "n_detected_true_interaction",
    "detection_rate",
    "n_false_positive_interaction",
    "false_positive_rate",
]

VARIABLE_PATTERN = re.compile(r"\bx(?:[1-9]|1[0-9]|20)\b")
INTERACTION_KEYWORD_PATTERN = re.compile(
    r"\binteraction(?:s| term| terms| effect| effects)?\b|\binteract(?:ion|s|ed)?\b"
)
BROAD_INTERACTION_PATTERN = re.compile(
    r"\binteraction(?:s| term| terms| effect| effects)?\b"
    r"|\binteract(?:ion|s|ed)?\b"
    r"|\bnonlinear(?:ity|ities)?\b"
    r"|\bproduct term(?:s)?\b"
    r"|\bcross[- ]product(?: term(?:s)?)?\b"
    r"|\bmultiplicative\b"
)
TRUE_PAIR_OPERATOR_PATTERN = re.compile(r"\bx4\s*[*]\s*x5\b|\bx5\s*[*]\s*x4\b|\bx4x5\b|\bx5x4\b")
TRUE_PAIR_PHRASE_PATTERN = re.compile(
    r"\binteraction(?: term| effect| effects)?\b[^.:\n;]{0,80}\bx4\b[^.:\n;]{0,40}\bx5\b"
    r"|\binteraction(?: term| effect| effects)?\b[^.:\n;]{0,80}\bx5\b[^.:\n;]{0,40}\bx4\b"
    r"|\bx4\b[^.:\n;]{0,30}\binteract(?:ion|s|ed)?\b[^.:\n;]{0,30}\bx5\b"
    r"|\bx5\b[^.:\n;]{0,30}\binteract(?:ion|s|ed)?\b[^.:\n;]{0,30}\bx4\b"
)
NEGATIVE_INTERACTION_PATTERNS = [
    re.compile(r"\bno\b[^.:\n;]{0,80}\binteraction"),
    re.compile(r"\bno\b[^.:\n;]{0,80}\binteract"),
    re.compile(r"\bno significant\b[^.:\n;]{0,80}\binteraction"),
    re.compile(r"\bno compelling evidence\b[^.:\n;]{0,80}\binteraction"),
    re.compile(r"\bno evidence\b[^.:\n;]{0,80}\binteraction"),
    re.compile(r"\black of\b[^.:\n;]{0,80}\binteraction"),
    re.compile(r"\black of significant\b[^.:\n;]{0,80}\binteraction"),
    re.compile(r"\bdid not detect\b[^.:\n;]{0,80}\binteraction"),
    re.compile(r"\bfailed to detect\b[^.:\n;]{0,80}\binteraction"),
    re.compile(r"\bwithout\b[^.:\n;]{0,80}\binteraction"),
    re.compile(r"\binteraction(?: term| effect| effects)?\b[^.:\n;]{0,80}\bnot\b[^.:\n;]{0,40}\bsignificant"),
    re.compile(r"\babsence of\b[^.:\n;]{0,80}\binteraction"),
    re.compile(r"\binteraction(?: term| terms| effect| effects)?\b[^.:\n;]{0,80}\bdid not\b[^.:\n;]{0,40}\bimprov"),
    re.compile(r"\binteractions?\b[^.:\n;]{0,80}\bdo not\b[^.:\n;]{0,40}\bimprov"),
    re.compile(r"\binteractions?\b[^.:\n;]{0,80}\bunchanged\b"),
    re.compile(r"\binteractions?\b[^.:\n;]{0,80}\bp\s*[>≥]\s*0"),
]
POSITIVE_INTERACTION_PATTERNS = [
    re.compile(r"\binteraction(?: term| terms| effect| effects)?\b[^.:\n;]{0,30}\b(?:was|were|is|are)\b[^.:\n;]{0,20}\bsignificant\b"),
    re.compile(r"\bsignificant\b[^.:\n;]{0,20}\binteraction(?: term| terms| effect| effects)?\b[^.:\n;]{0,20}\b(?:was|were|is|are|detected|found|identified|present)\b"),
    re.compile(r"\binteraction(?: term| terms| effect| effects)?\b[^.:\n;]{0,30}\b(?:detected|found|identified|observed|present|exists?|retained)\b"),
    re.compile(r"\b(?:detected|found|identified|observed)\b[^.:\n;]{0,30}\binteraction(?: term| terms| effect| effects)?\b"),
    re.compile(r"\bevidence for\b[^.:\n;]{0,30}\binteraction(?: term| terms| effect| effects)?\b"),
    re.compile(r"\binteraction(?: term| terms| effect| effects)?\b[^.:\n;]{0,30}\bincluded in the final model\b"),
    re.compile(r"\binteraction(?: term| terms| effect| effects)?\b[^.:\n;]{0,30}\bimprov(?:e|ed|es)\b[^.:\n;]{0,20}\bmodel fit\b"),
    re.compile(r"\bimportant\b[^.:\n;]{0,20}\binteraction(?: term| terms| effect| effects)?\b"),
    re.compile(r"\binteraction(?: term| terms| effect| effects)?\b[^.:\n;]{0,20}\bimportant\b"),
    re.compile(r"\bpredict(?:ive|or|ors|s)?\b[^.:\n;]{0,20}\binteraction(?: term| terms| effect| effects)?\b"),
    re.compile(r"\binteraction(?: term| terms| effect| effects)?\b[^.:\n;]{0,20}\bpredict(?:ive|or|ors|s)?\b"),
]
METHODOLOGICAL_INTERACTION_PATTERNS = [
    re.compile(r"\btested\b[^.:\n;]{0,50}\binteraction"),
    re.compile(r"\binteraction\b[^.:\n;]{0,50}\btested\b"),
    re.compile(r"\bchecked\b[^.:\n;]{0,50}\binteraction"),
    re.compile(r"\binteraction\b[^.:\n;]{0,50}\bchecked\b"),
    re.compile(r"\bconsidered\b[^.:\n;]{0,50}\binteraction"),
    re.compile(r"\binteraction\b[^.:\n;]{0,50}\bconsidered\b"),
    re.compile(r"\blooked for\b[^.:\n;]{0,50}\binteraction"),
    re.compile(r"\binteraction\b[^.:\n;]{0,50}\blooked for\b"),
    re.compile(r"\bsearched for\b[^.:\n;]{0,50}\binteraction"),
    re.compile(r"\binteraction\b[^.:\n;]{0,50}\bsearched for\b"),
    re.compile(r"\bprobe(?:d|s|ing)?\b[^.:\n;]{0,50}\binteraction"),
    re.compile(r"\binteraction\b[^.:\n;]{0,50}\bprobe(?:d|s|ing)?\b"),
    re.compile(r"\bassess(?:ed|ment)?\b[^.:\n;]{0,50}\binteraction"),
    re.compile(r"\binteraction\b[^.:\n;]{0,50}\bassess(?:ed|ment)?\b"),
    re.compile(r"\bevaluat(?:ed|ing)\b[^.:\n;]{0,50}\binteraction"),
    re.compile(r"\binteraction\b[^.:\n;]{0,50}\bevaluat(?:ed|ing)\b"),
    re.compile(r"\badded\b[^.:\n;]{0,50}\binteraction"),
    re.compile(r"\binteraction\b[^.:\n;]{0,50}\badded\b"),
    re.compile(r"\bincluding\b[^.:\n;]{0,50}\binteraction"),
    re.compile(r"\binteraction\b[^.:\n;]{0,50}\bincluding\b"),
    re.compile(r"\bpossible\b[^.:\n;]{0,30}\binteraction"),
    re.compile(r"\bpotential\b[^.:\n;]{0,30}\binteraction"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate interaction-threshold outputs with lightweight rule-based "
            "heuristics. This script does not call any external API."
        )
    )
    parser.add_argument(
        "--outputs-root",
        type=Path,
        default=DEFAULT_EXECUTION_OUTPUT_ROOT,
        help="Directory containing model output JSON files.",
    )
    parser.add_argument(
        "--evaluations-root",
        type=Path,
        default=DEFAULT_EVALUATIONS_ROOT,
        help="Directory where evaluation CSV summaries will be written.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_text(text: str) -> str:
    normalized = text.lower()
    for old, new in {
        "×": "*",
        "∗": "*",
        "·": "*",
        "⋅": "*",
        "−": "-",
        "–": "-",
        "—": "-",
    }.items():
        normalized = normalized.replace(old, new)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\r\n?", "\n", normalized)
    return normalized


def split_segments(text: str) -> list[str]:
    segments = re.split(r"(?<=[\.\!\?\;\:])\s+|\n+", text)
    return [segment.strip() for segment in segments if segment.strip()]


def segment_mentions_interaction(segment: str) -> bool:
    return bool(INTERACTION_KEYWORD_PATTERN.search(segment) or TRUE_PAIR_OPERATOR_PATTERN.search(segment))


def segment_has_broad_interaction_mention(segment: str) -> bool:
    return bool(BROAD_INTERACTION_PATTERN.search(segment) or TRUE_PAIR_OPERATOR_PATTERN.search(segment))


def segment_is_negative(segment: str) -> bool:
    return any(pattern.search(segment) for pattern in NEGATIVE_INTERACTION_PATTERNS)


def segment_mentions_true_pair(segment: str) -> bool:
    return bool(TRUE_PAIR_OPERATOR_PATTERN.search(segment) or TRUE_PAIR_PHRASE_PATTERN.search(segment))


def segment_is_methodological(segment: str) -> bool:
    return any(pattern.search(segment) for pattern in METHODOLOGICAL_INTERACTION_PATTERNS)


def segment_has_positive_interaction_claim(segment: str) -> bool:
    if segment_is_negative(segment):
        return False
    return any(pattern.search(segment) for pattern in POSITIVE_INTERACTION_PATTERNS)


def extract_variables(segment: str) -> list[str]:
    return sorted(set(VARIABLE_PATTERN.findall(segment)))


def evaluate_content(content: str, coefficient: float) -> dict:
    normalized = normalize_text(content)
    segments = split_segments(normalized)

    mentions_x4 = bool(re.search(r"\bx4\b", normalized))
    mentions_x5 = bool(re.search(r"\bx5\b", normalized))
    mentions_interaction = bool(BROAD_INTERACTION_PATTERN.search(normalized) or TRUE_PAIR_OPERATOR_PATTERN.search(normalized))
    conclusion_says_no_interaction = any(
        segment_has_broad_interaction_mention(segment) and segment_is_negative(segment)
        for segment in segments
    )

    true_detection_evidence: list[str] = []
    wrong_detection_evidence: list[str] = []
    generic_positive_claims: list[str] = []

    for segment in segments:
        if not segment_has_broad_interaction_mention(segment):
            continue

        variables = extract_variables(segment)
        negative = segment_is_negative(segment)
        positive = segment_has_positive_interaction_claim(segment)
        mentions_true_pair = segment_mentions_true_pair(segment) or set(variables) == {"x4", "x5"}

        if positive and mentions_true_pair and not negative:
            true_detection_evidence.append(segment)
            continue

        if positive and not negative:
            variable_set = set(variables)
            if len(variable_set) >= 2 and variable_set != {"x4", "x5"}:
                wrong_detection_evidence.append(segment)
            elif not mentions_true_pair and not segment_is_methodological(segment):
                generic_positive_claims.append(segment)

    detected_true_interaction = bool(true_detection_evidence)
    detected_wrong_interaction = bool(wrong_detection_evidence)
    explicit_positive_interaction_claim = (
        detected_true_interaction
        or detected_wrong_interaction
        or bool(generic_positive_claims)
    )

    if conclusion_says_no_interaction and not explicit_positive_interaction_claim:
        detected_true_interaction = False
        detected_wrong_interaction = False
        false_positive_interaction = False
    else:
        false_positive_interaction = coefficient == 0.0 and explicit_positive_interaction_claim

    notes: list[str] = []
    if detected_true_interaction:
        notes.append("explicit X4*X5 interaction claim matched")
    if detected_wrong_interaction:
        notes.append("explicit non-X4/X5 interaction claim matched")
    if generic_positive_claims:
        notes.append("explicit positive interaction claim without explicit variable pair")
    if conclusion_says_no_interaction:
        notes.append("explicit no-interaction statement found")
    if mentions_interaction and not (
        detected_true_interaction
        or detected_wrong_interaction
        or conclusion_says_no_interaction
    ):
        notes.append("broad interaction/nonlinearity mention without explicit detection claim")
    if mentions_x4 and mentions_x5 and not detected_true_interaction and not conclusion_says_no_interaction:
        notes.append("X4 and X5 mentioned separately without explicit true interaction claim")

    return {
        "detected_true_interaction": detected_true_interaction,
        "detected_wrong_interaction": detected_wrong_interaction,
        "false_positive_interaction": false_positive_interaction,
        "mentions_interaction": mentions_interaction,
        "mentions_x4": mentions_x4,
        "mentions_x5": mentions_x5,
        "conclusion_says_no_interaction": conclusion_says_no_interaction,
        "notes": "; ".join(notes),
    }


def evaluate_output_file(path: Path) -> dict:
    payload = load_json(path)
    coefficient = float(payload.get("coefficient", 0.0))
    content = payload.get("response", {}).get("content", "")
    status = payload.get("status", "unknown")

    result = {
        "coefficient": coefficient,
        "condition_name": payload.get("condition_name", ""),
        "model_id": payload.get("model_id", ""),
        "run_id": payload.get("run_id", ""),
        "status": status,
        "detected_true_interaction": False,
        "detected_wrong_interaction": False,
        "false_positive_interaction": False,
        "mentions_interaction": False,
        "mentions_x4": False,
        "mentions_x5": False,
        "conclusion_says_no_interaction": False,
        "notes": "",
        "output_file": relative_to_repo(path),
    }

    if status != "success":
        result["notes"] = payload.get("error", "non-success output")
        return result

    result.update(evaluate_content(content, coefficient))
    return result


def build_aggregate(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=AGGREGATE_COLUMNS)

    aggregate_rows = []
    for coefficient, group in frame.groupby("coefficient", sort=True):
        n_runs = len(group)
        n_success = int((group["status"] == "success").sum())
        n_detected_true_interaction = int(group["detected_true_interaction"].sum())
        n_false_positive_interaction = int(group["false_positive_interaction"].sum())
        detection_rate = (
            n_detected_true_interaction / n_success if n_success else 0.0
        )
        false_positive_rate = (
            n_false_positive_interaction / n_success if n_success else 0.0
        )
        aggregate_rows.append(
            {
                "coefficient": coefficient,
                "n_runs": n_runs,
                "n_success": n_success,
                "n_detected_true_interaction": n_detected_true_interaction,
                "detection_rate": detection_rate,
                "n_false_positive_interaction": n_false_positive_interaction,
                "false_positive_rate": false_positive_rate,
            }
        )
    return pd.DataFrame(aggregate_rows, columns=AGGREGATE_COLUMNS).sort_values("coefficient")


def write_empty_outputs(evaluations_root: Path) -> None:
    evaluations_root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=RUN_SUMMARY_COLUMNS).to_csv(
        evaluations_root / "per_run_summary.csv",
        index=False,
    )
    pd.DataFrame(columns=AGGREGATE_COLUMNS).to_csv(
        evaluations_root / "aggregate_by_coefficient.csv",
        index=False,
    )


def main() -> None:
    args = parse_args()
    output_files = sorted(args.outputs_root.rglob("*.json"))

    if not output_files:
        write_empty_outputs(args.evaluations_root)
        print(
            "No output JSON files were found. Wrote empty evaluation CSVs to "
            f"{args.evaluations_root.as_posix()}."
        )
        return

    rows = [evaluate_output_file(path) for path in output_files]
    run_frame = pd.DataFrame(rows, columns=RUN_SUMMARY_COLUMNS).sort_values(
        ["coefficient", "model_id", "run_id"]
    )
    aggregate_frame = build_aggregate(rows)

    args.evaluations_root.mkdir(parents=True, exist_ok=True)
    run_path = args.evaluations_root / "per_run_summary.csv"
    aggregate_path = args.evaluations_root / "aggregate_by_coefficient.csv"
    run_frame.to_csv(run_path, index=False)
    aggregate_frame.to_csv(aggregate_path, index=False)

    print(f"Wrote per-run summary: {run_path.as_posix()}")
    print(f"Wrote aggregate summary: {aggregate_path.as_posix()}")
    print(f"Evaluated {len(run_frame)} output files.")


if __name__ == "__main__":
    main()
