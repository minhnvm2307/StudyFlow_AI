from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = ROOT / "backend" / "tests"
SCRIPT_PATH = ROOT / "scripts" / "run_eval_scorecard.py"

if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))


def _load_scorecard_module():
    spec = importlib.util.spec_from_file_location("run_eval_scorecard", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_render_scorecard_markdown_includes_metric_explanations_and_case_details():
    scorecard = _load_scorecard_module()

    environment = scorecard.EnvironmentStatus(
        database_url="postgresql://studyflow:studyflow@localhost:5432/studyflow",
        database_available=True,
        database_error=None,
        llm_available=True,
        llm_error=None,
    )
    result = scorecard.SuiteResult(
        suite="RAG online evaluation",
        pillar="rag",
        profile="online",
        status="failed",
        passed=5,
        failed=0,
        skipped=0,
        cases=[
            {
                "name": "Bayes answer quality",
                "status": "passed",
                "metrics": {
                    "faithfulness": 0.0,
                    "answer_relevance": 0.0,
                    "retrieval_recall_at_5": 1.0,
                },
                "notes": "",
                "answer": "Xin lỗi, hệ thống gặp lỗi khi truy xuất tài liệu.",
            }
        ],
        metrics={
            "faithfulness": 0.0,
            "answer_relevance": 0.0,
            "retrieval_recall_at_5": 1.0,
            "guardrail_refusal_accuracy": 1.0,
        },
        thresholds=[
            {
                "metric": "Faithfulness",
                "status": "failed",
                "value": 0.0,
                "target": 0.9,
                "operator": "gte",
            }
        ],
        artifact_paths={"log": "artifacts/eval/logs/rag-online-evaluation.log"},
        notes=["One or more eval metrics missed their thresholds."],
        description="Integration eval for retrieval, routing, refusal behavior, and live model answer quality.",
        command="python -m pytest -q backend/tests/test_rag_evaluation.py -k online_",
        return_code=0,
    )

    markdown = scorecard.render_scorecard_markdown(
        results=[result],
        baselines=scorecard.load_baselines(),
        environment=environment,
        selected_profile="online",
    )

    assert "## Metric Explanations" in markdown
    assert "Faithfulness checks whether the final answer stays supported by retrieved evidence." in markdown
    assert "RAG online eval hiện dùng dữ liệu TTHCM và chỉ chấm trên tiếng Việt." in markdown
    assert "RMSE = sqrt(Brier)" in markdown
    assert "## Suite Details" in markdown
    assert "Bayes answer quality" in markdown
    assert "Xin lỗi, hệ thống gặp lỗi khi truy xuất tài liệu." in markdown
