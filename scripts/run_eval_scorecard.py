from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = ROOT / "backend" / "tests"
if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))

from evals.helpers import (  # noqa: E402
    aggregate_case_statuses,
    ensure_dir,
    evaluate_thresholds,
    read_case_results,
    read_json,
    slugify,
    write_json,
)


load_dotenv()

DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "eval"
BASELINES_PATH = TESTS_ROOT / "evals" / "baselines.json"
DEFAULT_DATABASE_URL = "postgresql://studyflow:studyflow@localhost:5432/studyflow"


@dataclass(frozen=True)
class EnvironmentStatus:
    database_url: str
    database_available: bool
    database_error: str | None
    llm_available: bool
    llm_error: str | None


@dataclass(frozen=True)
class ProfileSpec:
    name: str
    description: str


@dataclass(frozen=True)
class SuiteSpec:
    name: str
    pillar: str
    profile: str
    kind: str
    description: str
    command: list[str] = field(default_factory=list)
    requires_db: bool = False
    requires_llm: bool = False


@dataclass
class SuiteResult:
    suite: str
    pillar: str
    profile: str
    status: str
    passed: int
    failed: int
    skipped: int
    cases: list[dict[str, Any]]
    metrics: dict[str, Any]
    thresholds: list[dict[str, Any]]
    artifact_paths: dict[str, str]
    notes: list[str]
    description: str
    command: str
    return_code: int | None = None


PROFILES = {
    "ci": ProfileSpec(name="ci", description="Fast deterministic pull-request gate."),
    "online": ProfileSpec(name="online", description="Live-model RAG and routing evaluation."),
    "weekly": ProfileSpec(name="weekly", description="Synthetic cohort regression evaluation."),
    "all": ProfileSpec(name="all", description="Run ci, online, and weekly profiles together."),
}

METRIC_EXPLANATIONS = {
    "faithfulness": "Faithfulness checks whether the final answer stays supported by retrieved evidence.",
    "answer_relevance": "Answer Relevance checks whether the response directly answers the user's question.",
    "retrieval_recall_at_5": "Retrieval Recall@5 checks whether the top retrieved chunks contain the facts needed to answer the question.",
    "guardrail_refusal_accuracy": "Guardrail refusal accuracy checks whether unsafe or out-of-scope prompts are refused correctly.",
    "rmse": "RMSE measures the average size of prediction error for mastery estimates; lower is better.",
    "brier": "Brier score measures probability calibration error for mastery predictions; lower is better.",
    "calibration_gap": "Calibration gap measures the mismatch between predicted confidence and observed outcomes; lower is better.",
    "auc": "AUC measures how well the mastery model ranks stronger versus weaker outcomes; higher is better.",
    "over_budget_warning_rate": "Over-budget warning rate measures how often the scheduler warns that planned study time exceeds constraints; lower is better.",
    "coverage_warning_count": "Coverage warning regression checks whether new scheduler runs introduced unexpected coverage warnings.",
}


def _repair_mojibake(value: str) -> str:
    if not value:
        return value
    suspicious_markers = ("Ã", "Â", "â€", "â€“", "á»", "Æ°")
    if not any(marker in value for marker in suspicious_markers):
        return value
    try:
        return value.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def load_baselines() -> dict[str, Any]:
    return read_json(BASELINES_PATH, default={}) or {}


def parse_summary_counts(output: str) -> tuple[int, int, int]:
    passed = sum(int(match.group(1)) for match in re.finditer(r"(\d+)\s+passed", output))
    failed = sum(int(match.group(1)) for match in re.finditer(r"(\d+)\s+failed", output))
    skipped = sum(int(match.group(1)) for match in re.finditer(r"(\d+)\s+skipped", output))
    return passed, failed, skipped


def detect_environment() -> EnvironmentStatus:
    database_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    parsed = urlparse(database_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    database_available = False
    database_error = None
    try:
        with socket.create_connection((host, port), timeout=2.0):
            database_available = True
    except OSError as exc:
        database_error = f"Cannot reach database at {host}:{port} ({exc})"

    llm_keys = [
        os.getenv("OPENAI_API_KEY", "").strip(),
        os.getenv("CUSTOM_API_KEY", "").strip(),
        os.getenv("OPENROUTER_API_KEY", "").strip(),
        os.getenv("NVIDIA_API_KEY", "").strip(),
    ]
    llm_available = any(llm_keys)
    llm_error = None if llm_available else "No LLM API credentials are configured for online eval."
    return EnvironmentStatus(
        database_url=database_url,
        database_available=database_available,
        database_error=database_error,
        llm_available=llm_available,
        llm_error=llm_error,
    )


def threshold_rules_for(baselines: dict[str, Any], pillar: str, profile: str) -> dict[str, dict[str, Any]]:
    rules = {}
    pillar_metrics = ((baselines.get(pillar) or {}).get("metrics") or {})
    for metric_key, rule in pillar_metrics.items():
        run_modes = rule.get("runModes") or []
        if not run_modes or profile in run_modes:
            rules[metric_key] = rule
    return rules


def aggregate_case_metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, list[float]] = {}
    for case in cases:
        metrics = case.get("metrics") or {}
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                totals.setdefault(key, []).append(float(value))
    aggregated = {}
    for key, values in totals.items():
        if values:
            aggregated[key] = round(sum(values) / len(values), 4)
    return aggregated


def build_suite_result(
    *,
    spec: SuiteSpec,
    status: str,
    passed: int,
    failed: int,
    skipped: int,
    cases: list[dict[str, Any]],
    metrics: dict[str, Any],
    thresholds: list[dict[str, Any]],
    artifact_paths: dict[str, str],
    notes: list[str],
    command: list[str],
    return_code: int | None,
) -> SuiteResult:
    return SuiteResult(
        suite=spec.name,
        pillar=spec.pillar,
        profile=spec.profile,
        status=status,
        passed=passed,
        failed=failed,
        skipped=skipped,
        cases=cases,
        metrics=metrics,
        thresholds=thresholds,
        artifact_paths=artifact_paths,
        notes=notes,
        description=spec.description,
        command=" ".join(command),
        return_code=return_code,
    )


def write_suite_json(result: SuiteResult, suites_dir: Path) -> Path:
    path = suites_dir / f"{slugify(result.suite)}.json"
    write_json(path, asdict(result))
    return path


def run_pytest_suite(
    spec: SuiteSpec,
    *,
    baselines: dict[str, Any],
    environment: EnvironmentStatus,
    output_dir: Path,
    suites_dir: Path,
    logs_dir: Path,
    online_root: Path,
    strict_thresholds: bool,
) -> SuiteResult:
    suite_slug = slugify(spec.name)
    log_path = logs_dir / f"{suite_slug}.log"
    run_dir: Path | None = None
    case_dir: Path | None = None
    guardrail_report: Path | None = None
    notes: list[str] = []

    if spec.requires_db and not environment.database_available:
        notes.append(environment.database_error or "Database is unavailable.")
        log_path.write_text("\n".join(notes) + "\n", encoding="utf-8")
        result = build_suite_result(
            spec=spec,
            status="failed",
            passed=0,
            failed=1,
            skipped=0,
            cases=[],
            metrics={},
            thresholds=[],
            artifact_paths={"log": str(log_path.relative_to(ROOT))},
            notes=notes,
            command=spec.command,
            return_code=None,
        )
        write_suite_json(result, suites_dir)
        return result

    if spec.requires_llm and not environment.llm_available:
        notes.append(environment.llm_error or "LLM credentials are unavailable.")
        log_path.write_text("\n".join(notes) + "\n", encoding="utf-8")
        result = build_suite_result(
            spec=spec,
            status="skipped",
            passed=0,
            failed=0,
            skipped=1,
            cases=[],
            metrics={},
            thresholds=[],
            artifact_paths={"log": str(log_path.relative_to(ROOT))},
            notes=notes,
            command=spec.command,
            return_code=None,
        )
        write_suite_json(result, suites_dir)
        return result

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["EVAL_ARTIFACT_DIR"] = str(output_dir)
    env["EVAL_PROFILE"] = spec.profile
    if spec.profile == "online":
        run_dir = ensure_dir(online_root / suite_slug)
        case_dir = ensure_dir(run_dir / "cases")
        guardrail_report = run_dir / "guardrail_report.md"
        env["EVAL_CASE_DIR"] = str(case_dir)
        env["EVAL_GUARDRAIL_REPORT"] = str(guardrail_report)

    completed = subprocess.run(
        spec.command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    combined_output = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
    log_path.write_text(combined_output, encoding="utf-8")

    cases = read_case_results(case_dir)
    if cases:
        passed, failed, skipped = aggregate_case_statuses(cases)
    else:
        passed, failed, skipped = parse_summary_counts(combined_output)

    metrics = aggregate_case_metrics(cases)
    threshold_rules = threshold_rules_for(baselines, spec.pillar, spec.profile)
    thresholds = evaluate_thresholds(metrics, threshold_rules, strict=strict_thresholds) if threshold_rules else []
    status = "passed" if completed.returncode == 0 else "failed"
    if any(item["status"] == "failed" for item in thresholds):
        status = "failed"
        notes.append("One or more eval metrics missed their thresholds.")
    if completed.returncode != 0 and not combined_output.strip():
        notes.append("Command failed without pytest summary output.")

    artifact_paths = {
        "log": str(log_path.relative_to(ROOT)),
    }
    if guardrail_report is not None:
        artifact_paths["guardrailReport"] = str(guardrail_report.relative_to(ROOT))
    if case_dir is not None and cases:
        artifact_paths["caseDir"] = str(case_dir.relative_to(ROOT))

    result = build_suite_result(
        spec=spec,
        status=status,
        passed=passed,
        failed=failed,
        skipped=skipped,
        cases=cases,
        metrics=metrics,
        thresholds=thresholds,
        artifact_paths=artifact_paths,
        notes=notes,
        command=spec.command,
        return_code=completed.returncode,
    )
    write_suite_json(result, suites_dir)
    return result


def run_seeded_weekly_eval(
    *,
    baselines: dict[str, Any],
    environment: EnvironmentStatus,
    output_dir: Path,
    suites_dir: Path,
    logs_dir: Path,
    weekly_root: Path,
    strict_thresholds: bool,
    seed_prefix: str,
    users: int,
    history_days: int,
) -> list[SuiteResult]:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = ensure_dir(weekly_root / run_id)
    log_path = logs_dir / "synthetic-cohort-evaluation.log"
    command = [
        sys.executable,
        "scripts/seed_synthetic_eval.py",
        "--reset",
        "--prefix",
        seed_prefix,
        "--users",
        str(users),
        "--history-days",
        str(history_days),
        "--output-dir",
        str(run_dir),
    ]

    if not environment.database_available:
        note = environment.database_error or "Database is unavailable."
        log_path.write_text(note + "\n", encoding="utf-8")
        results = []
        for spec in [
            SuiteSpec(
                name="Mastery weekly evaluation",
                pillar="mastery",
                profile="weekly",
                kind="weekly",
                description="Synthetic cohort regression for mastery calibration metrics.",
            ),
            SuiteSpec(
                name="Scheduler weekly evaluation",
                pillar="scheduler",
                profile="weekly",
                kind="weekly",
                description="Synthetic cohort regression for scheduler warning metrics.",
            ),
        ]:
            result = build_suite_result(
                spec=spec,
                status="failed",
                passed=0,
                failed=1,
                skipped=0,
                cases=[],
                metrics={},
                thresholds=[],
                artifact_paths={"log": str(log_path.relative_to(ROOT))},
                notes=[note],
                command=command,
                return_code=None,
            )
            write_suite_json(result, suites_dir)
            results.append(result)
        return results

    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=os.environ.copy(),
    )
    combined_output = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
    log_path.write_text(combined_output, encoding="utf-8")
    summary = read_json(run_dir / "synthetic_cohort.json", default={}) or {}

    mastery_metrics = {
        "rmse": ((summary.get("offlineMetrics") or {}).get("rmse")),
        "brier": ((summary.get("offlineMetrics") or {}).get("brier")),
        "calibration_gap": ((summary.get("offlineMetrics") or {}).get("calibrationGap")),
        "auc": ((summary.get("offlineMetrics") or {}).get("auc")),
    }
    scheduler_metrics = {
        "over_budget_warning_rate": ((summary.get("schedulerMetrics") or {}).get("overBudgetWarningRate")),
        "coverage_warning_count": ((summary.get("schedulerMetrics") or {}).get("coverageWarningCount")),
    }

    common_artifacts = {
        "log": str(log_path.relative_to(ROOT)),
        "runDir": str(run_dir.relative_to(ROOT)),
        "cohortJson": str((run_dir / "synthetic_cohort.json").relative_to(ROOT)),
        "cohortMarkdown": str((run_dir / "synthetic_cohort.md").relative_to(ROOT)),
    }
    notes = []
    if completed.returncode != 0:
        notes.append("Synthetic cohort seeding returned a non-zero exit code.")

    specs_and_metrics = [
        (
            SuiteSpec(
                name="Mastery weekly evaluation",
                pillar="mastery",
                profile="weekly",
                kind="weekly",
                description="Synthetic cohort regression for mastery calibration metrics.",
            ),
            mastery_metrics,
        ),
        (
            SuiteSpec(
                name="Scheduler weekly evaluation",
                pillar="scheduler",
                profile="weekly",
                kind="weekly",
                description="Synthetic cohort regression for scheduler warning metrics.",
            ),
            scheduler_metrics,
        ),
    ]

    results: list[SuiteResult] = []
    for spec, metrics in specs_and_metrics:
        threshold_rules = threshold_rules_for(baselines, spec.pillar, spec.profile)
        thresholds = evaluate_thresholds(metrics, threshold_rules, strict=strict_thresholds) if threshold_rules else []
        status = "passed" if completed.returncode == 0 else "failed"
        if any(item["status"] == "failed" for item in thresholds):
            status = "failed"
        result = build_suite_result(
            spec=spec,
            status=status,
            passed=1 if status == "passed" else 0,
            failed=1 if status == "failed" else 0,
            skipped=0,
            cases=[{"name": "synthetic-cohort", "status": status, "metrics": metrics}],
            metrics=metrics,
            thresholds=thresholds,
            artifact_paths=common_artifacts,
            notes=list(notes),
            command=command,
            return_code=completed.returncode,
        )
        write_suite_json(result, suites_dir)
        results.append(result)
    return results


def render_scorecard_markdown(
    *,
    results: list[SuiteResult],
    baselines: dict[str, Any],
    environment: EnvironmentStatus,
    selected_profile: str,
) -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    lines = [
        "# StudyFlow Eval Scorecard",
        "",
        f"Generated at: `{generated_at}`",
        f"Profile: `{selected_profile}`",
        "",
        "## Environment",
        "",
        f"- Database reachable: `{environment.database_available}`",
        f"- LLM credentials present: `{environment.llm_available}`",
        "",
    ]

    for profile in ["ci", "online", "weekly"]:
        profile_results = [result for result in results if result.profile == profile]
        if not profile_results:
            continue
        lines.extend(
            [
                f"## {profile.upper()}",
                "",
                "| Suite | Pillar | Status | Passed | Failed | Skipped | Log |",
                "| --- | --- | --- | ---: | ---: | ---: | --- |",
            ]
        )
        for result in profile_results:
            lines.append(
                f"| {result.suite} | {result.pillar} | {result.status.upper()} | "
                f"{result.passed} | {result.failed} | {result.skipped} | `{result.artifact_paths.get('log', '')}` |"
            )
        lines.append("")

    lines.extend(
        [
            "## Metric Targets",
            "",
            "| Pillar | Metric | Target | Run Modes | Tolerance |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for pillar, payload in baselines.items():
        for metric_key, rule in (payload.get("metrics") or {}).items():
            lines.append(
                f"| {pillar} | {rule.get('label', metric_key)} | {rule.get('operator')} {rule.get('target')} | "
                f"{', '.join(rule.get('runModes') or [])} | {rule.get('tolerance', 0.0)} |"
            )

    lines.append("")
    lines.append("## Metric Explanations")
    lines.append("")
    lines.append("- RAG online eval hiện dùng dữ liệu TTHCM và chỉ chấm trên tiếng Việt.")
    lines.append("- Với weekly mastery hiện tại, `RMSE = sqrt(Brier)` nên đây là hai cách nhìn trên cùng tín hiệu lỗi dự đoán xác suất.")
    lines.append("- Baseline weekly mastery là synthetic-regression gate nội bộ, không phải ngưỡng học thuật tuyệt đối.")
    lines.append("")
    for pillar, payload in baselines.items():
        lines.append(f"### {pillar.upper()}")
        lines.append("")
        for metric_key, rule in (payload.get("metrics") or {}).items():
            label = str(rule.get("label", metric_key))
            explanation = METRIC_EXPLANATIONS.get(metric_key, "No explanation is configured for this metric yet.")
            target = f"{rule.get('operator')} {rule.get('target')}"
            tolerance = rule.get("tolerance", 0.0)
            run_modes = ", ".join(rule.get("runModes") or [])
            lines.append(f"- `{label}`: {explanation} Target: `{target}`. Tolerance: `{tolerance}`. Run modes: `{run_modes}`.")
        lines.append("")

    lines.append("## Threshold Checks")
    lines.append("")
    lines.append("| Suite | Metric | Status | Value | Target |")
    lines.append("| --- | --- | --- | ---: | ---: |")
    for result in results:
        for threshold in result.thresholds:
            value = threshold.get("value")
            target = threshold.get("target")
            lines.append(
                f"| {result.suite} | {threshold.get('metric')} | {str(threshold.get('status')).upper()} | "
                f"{value if value is not None else 'n/a'} | {target if target is not None else 'n/a'} |"
            )
    lines.append("")

    lines.append("## Suite Details")
    lines.append("")
    for result in results:
        lines.append(f"### {result.suite}")
        lines.append("")
        lines.append(f"- Status: `{result.status.upper()}`")
        lines.append(f"- Profile: `{result.profile}`")
        lines.append(f"- Pillar: `{result.pillar}`")
        lines.append(f"- Description: {result.description}")
        lines.append(f"- Command: `{result.command}`")
        if result.artifact_paths:
            artifact_summary = ", ".join(
                f"`{name}` -> `{path}`" for name, path in sorted(result.artifact_paths.items())
            )
            lines.append(f"- Artifacts: {artifact_summary}")
        if result.metrics:
            metric_summary = ", ".join(
                f"`{key}`={value}" for key, value in sorted(result.metrics.items())
            )
            lines.append(f"- Aggregated metrics: {metric_summary}")
        if result.notes:
            lines.append(f"- Notes: {' | '.join(result.notes)}")
        lines.append("")

        if result.cases:
            lines.append("| Case | Status | Metrics | Notes |")
            lines.append("| --- | --- | --- | --- |")
            for case in result.cases:
                case_metrics = case.get("metrics") or {}
                metric_summary = ", ".join(
                    f"{key}={value}" for key, value in sorted(case_metrics.items())
                ) or "n/a"
                note_parts = []
                if case.get("notes"):
                    note_parts.append(_repair_mojibake(str(case.get("notes"))))
                if case.get("answer"):
                    cleaned_answer = _repair_mojibake(str(case.get("answer"))).replace(chr(10), " ")
                    note_parts.append(f"Answer: {cleaned_answer[:240]}")
                lines.append(
                    f"| {_repair_mojibake(str(case.get('name', 'case')))} | {str(case.get('status', '')).upper()} | "
                    f"{metric_summary} | {' | '.join(note_parts) if note_parts else 'n/a'} |"
                )
            lines.append("")
    return "\n".join(lines)


def build_suite_specs() -> dict[str, list[SuiteSpec]]:
    base_pytest = [sys.executable, "-m", "pytest", "-q"]
    return {
        "ci": [
            SuiteSpec(
                name="Course overlap guard",
                pillar="scheduler",
                profile="ci",
                kind="pytest",
                command=[*base_pytest, "backend/tests/test_course_overlap_limit.py"],
                description="Regression coverage for semester overlap limits.",
            ),
            SuiteSpec(
                name="Mastery evaluation",
                pillar="mastery",
                profile="ci",
                kind="pytest",
                command=[*base_pytest, "backend/tests/test_mastery_evaluation.py"],
                description="Deterministic checks for mastery updates, confidence, and event logging.",
            ),
            SuiteSpec(
                name="Scheduler evaluation",
                pillar="scheduler",
                profile="ci",
                kind="pytest",
                command=[*base_pytest, "backend/tests/test_scheduler_evaluation.py"],
                description="Deterministic checks for coverage feasibility, precedence, and fallback warnings.",
            ),
            SuiteSpec(
                name="RAG deterministic evaluation",
                pillar="rag",
                profile="ci",
                kind="pytest",
                command=[*base_pytest, "backend/tests/test_rag_evaluation.py", "-k", "ci_"],
                description="Deterministic guardrail and retrieval checks with no DB or live model dependency.",
            ),
        ],
        "online": [
            SuiteSpec(
                name="RAG online evaluation",
                pillar="rag",
                profile="online",
                kind="pytest",
                command=[*base_pytest, "backend/tests/test_rag_evaluation.py", "-k", "online_"],
                description="Integration eval for retrieval, routing, refusal behavior, and live model answer quality.",
                requires_db=True,
                requires_llm=True,
            )
        ],
    }


def selected_profiles(profile: str) -> list[str]:
    return ["ci", "online", "weekly"] if profile == "all" else [profile]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run StudyFlow eval suites and generate a scorecard.")
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES.keys()),
        default="ci",
        help="Eval profile to run.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where markdown/json reports and raw suite logs are written.",
    )
    parser.add_argument("--seed-prefix", default="synthetic-eval", help="Prefix for weekly synthetic users.")
    parser.add_argument("--users", type=int, default=6, help="Number of synthetic users for weekly eval.")
    parser.add_argument("--history-days", type=int, default=28, help="Synthetic history window for weekly eval.")
    parser.add_argument(
        "--strict-thresholds",
        action="store_true",
        help="Fail when a required metric is missing instead of skipping that threshold check.",
    )
    args = parser.parse_args()

    output_dir = ensure_dir(Path(args.output_dir))
    suites_dir = ensure_dir(output_dir / "suites")
    logs_dir = ensure_dir(output_dir / "logs")
    active_profiles = selected_profiles(args.profile)
    online_root = output_dir / "online" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    weekly_root = output_dir / "weekly"
    if "online" in active_profiles:
        ensure_dir(online_root)
    if "weekly" in active_profiles:
        ensure_dir(weekly_root)

    baselines = load_baselines()
    environment = detect_environment()
    suite_specs = build_suite_specs()

    results: list[SuiteResult] = []
    for profile_name in active_profiles:
        if profile_name == "weekly":
            results.extend(
                run_seeded_weekly_eval(
                    baselines=baselines,
                    environment=environment,
                    output_dir=output_dir,
                    suites_dir=suites_dir,
                    logs_dir=logs_dir,
                    weekly_root=weekly_root,
                    strict_thresholds=args.strict_thresholds,
                    seed_prefix=args.seed_prefix,
                    users=max(1, args.users),
                    history_days=max(7, args.history_days),
                )
            )
            continue

        for spec in suite_specs.get(profile_name, []):
            results.append(
                run_pytest_suite(
                    spec,
                    baselines=baselines,
                    environment=environment,
                    output_dir=output_dir,
                    suites_dir=suites_dir,
                    logs_dir=logs_dir,
                    online_root=online_root,
                    strict_thresholds=args.strict_thresholds,
                )
            )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": args.profile,
        "environment": asdict(environment),
        "results": [asdict(result) for result in results],
        "baselines": baselines,
    }
    markdown = render_scorecard_markdown(
        results=results,
        baselines=baselines,
        environment=environment,
        selected_profile=args.profile,
    )

    write_json(output_dir / "scorecard.json", payload)
    (output_dir / "scorecard.md").write_text(markdown, encoding="utf-8")

    failing = any(result.status == "failed" for result in results)
    return 1 if failing else 0


if __name__ == "__main__":
    raise SystemExit(main())
