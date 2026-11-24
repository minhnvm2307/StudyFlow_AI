from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().lower())
    return cleaned.strip("-") or "suite"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def repair_mojibake(value: str) -> str:
    if not value or not any(marker in value for marker in ("Ã", "Â", "Ä", "á»", "áº")):
        return value
    try:
        repaired = value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    return repaired if repaired != value else value


def normalize_artifact_payload(payload: Any) -> Any:
    if isinstance(payload, str):
        return repair_mojibake(payload)
    if isinstance(payload, list):
        return [normalize_artifact_payload(item) for item in payload]
    if isinstance(payload, dict):
        return {
            normalize_artifact_payload(key): normalize_artifact_payload(value)
            for key, value in payload.items()
        }
    return payload


def write_json(path: Path, payload: Any) -> Path:
    ensure_dir(path.parent)
    normalized_payload = normalize_artifact_payload(payload)
    path.write_text(json.dumps(normalized_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def configure_langsmith_passthrough() -> None:
    if os.getenv("LANGSMITH_API_KEY"):
        os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY", "")
    if os.getenv("LANGSMITH_ENDPOINT"):
        os.environ["LANGCHAIN_ENDPOINT"] = os.getenv("LANGSMITH_ENDPOINT", "")
    if os.getenv("LANGSMITH_PROJECT"):
        os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGSMITH_PROJECT", "StudyFlow")
    if os.getenv("LANGSMITH_TRACING", "").lower() == "true":
        os.environ["LANGCHAIN_TRACING_V2"] = "true"


def get_case_dir() -> Path | None:
    raw = os.getenv("EVAL_CASE_DIR", "").strip()
    if not raw:
        return None
    return ensure_dir(Path(raw))


def get_guardrail_report_path(default_name: str = "guardrail_report.md") -> Path:
    raw = os.getenv("EVAL_GUARDRAIL_REPORT", "").strip()
    if raw:
        path = Path(raw)
    else:
        path = Path.cwd() / "artifacts" / "eval" / default_name
    ensure_dir(path.parent)
    return path


def record_case_result(case_name: str, payload: dict[str, Any]) -> Path | None:
    case_dir = get_case_dir()
    if case_dir is None:
        return None
    path = case_dir / f"{slugify(case_name)}.json"
    return write_json(path, payload)


def read_case_results(case_dir: Path | None) -> list[dict[str, Any]]:
    if case_dir is None or not case_dir.exists():
        return []
    results: list[dict[str, Any]] = []
    for path in sorted(case_dir.glob("*.json")):
        data = read_json(path, default={}) or {}
        if isinstance(data, dict):
            results.append(data)
    return results


def aggregate_case_statuses(cases: list[dict[str, Any]]) -> tuple[int, int, int]:
    passed = sum(1 for case in cases if str(case.get("status", "")).lower() == "passed")
    failed = sum(1 for case in cases if str(case.get("status", "")).lower() == "failed")
    skipped = sum(1 for case in cases if str(case.get("status", "")).lower() == "skipped")
    return passed, failed, skipped


def compare_metric(value: float | int | None, rule: dict[str, Any]) -> dict[str, Any]:
    operator = str(rule.get("operator") or "gte").lower()
    target = rule.get("target")
    tolerance = float(rule.get("tolerance") or 0.0)
    label = str(rule.get("label") or rule.get("metric") or "metric")

    if value is None:
        return {
            "metric": label,
            "status": "missing",
            "value": None,
            "target": target,
            "operator": operator,
            "tolerance": tolerance,
            "reason": "Metric value is missing.",
        }

    lhs = float(value)
    rhs = float(target)
    passed = False
    if operator == "gte":
        passed = lhs + tolerance >= rhs
    elif operator == "gt":
        passed = lhs > rhs - tolerance
    elif operator == "lte":
        passed = lhs - tolerance <= rhs
    elif operator == "lt":
        passed = lhs < rhs + tolerance
    elif operator == "eq":
        passed = abs(lhs - rhs) <= tolerance
    else:
        return {
            "metric": label,
            "status": "invalid",
            "value": lhs,
            "target": rhs,
            "operator": operator,
            "tolerance": tolerance,
            "reason": f"Unsupported operator '{operator}'.",
        }

    return {
        "metric": label,
        "status": "passed" if passed else "failed",
        "value": lhs,
        "target": rhs,
        "operator": operator,
        "tolerance": tolerance,
    }


def evaluate_thresholds(
    metrics: dict[str, Any],
    rules: dict[str, dict[str, Any]],
    *,
    strict: bool = False,
) -> list[dict[str, Any]]:
    evaluations: list[dict[str, Any]] = []
    for metric_key, rule in rules.items():
        result = compare_metric(metrics.get(metric_key), rule)
        result["metricKey"] = metric_key
        if result["status"] == "missing" and not strict:
            result["status"] = "skipped"
        evaluations.append(result)
    return evaluations
