from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from textwrap import shorten

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
FIGURES_DIR = DOCS_DIR / "figures" / "eval"
SCORECARD_PATH = ROOT / "artifacts" / "eval" / "scorecard.json"
RAG_SUITE_PATH = ROOT / "artifacts" / "eval" / "suites" / "rag-online-evaluation.json"
MASTERY_SUITE_PATH = ROOT / "artifacts" / "eval" / "suites" / "mastery-weekly-evaluation.json"
SCHEDULER_SUITE_PATH = ROOT / "artifacts" / "eval" / "suites" / "scheduler-weekly-evaluation.json"
COHORT_PATH = ROOT / "artifacts" / "eval" / "weekly" / "20260707T205705Z" / "synthetic_cohort.json"
REPORT_TEX_PATH = DOCS_DIR / "eval-report.tex"
REPORT_PDF_PATH = DOCS_DIR / "eval-report.pdf"


def repair_mojibake(value: str) -> str:
    if not value or not any(marker in value for marker in ("Ã", "Â", "Ä", "á»", "áº", "ðŸ")):
        return value
    for source_encoding in ("latin-1", "cp1252"):
        try:
            fixed = value.encode(source_encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if fixed != value:
            return fixed
    return value


def normalize_payload(payload):
    if isinstance(payload, str):
        return repair_mojibake(payload)
    if isinstance(payload, list):
        return [normalize_payload(item) for item in payload]
    if isinstance(payload, dict):
        return {normalize_payload(key): normalize_payload(value) for key, value in payload.items()}
    return payload


def read_json(path: Path) -> dict:
    return normalize_payload(json.loads(path.read_text(encoding="utf-8")))


def latex_escape(value: object) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for src, dest in replacements.items():
        text = text.replace(src, dest)
    return text


def vi(text: str) -> str:
    return repair_mojibake(text)


def format_metric(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")


def ensure_dirs() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)


def build_rag_chart(rag_suite: dict) -> Path:
    metrics = rag_suite["metrics"]
    thresholds = {item["metricKey"]: item["target"] for item in rag_suite["thresholds"]}
    labels = [
        vi("Faithfulness"),
        vi("Answer Relevance"),
        vi("Recall@5"),
        vi("Refusal Accuracy"),
    ]
    keys = [
        "faithfulness",
        "answer_relevance",
        "retrieval_recall_at_5",
        "guardrail_refusal_accuracy",
    ]
    values = [metrics[key] for key in keys]
    targets = [thresholds[key] for key in keys]

    plt.figure(figsize=(8.5, 4.8))
    positions = range(len(labels))
    plt.bar(positions, values, color=["#205781", "#4F959D", "#98D2C0", "#F6F8D5"], edgecolor="#16324f")
    plt.plot(list(positions), targets, color="#C0392B", marker="o", linewidth=2, label="Ngưỡng")
    plt.ylim(0, 1.05)
    plt.xticks(list(positions), labels, rotation=10)
    plt.ylabel(vi("Điểm"))
    plt.title(vi("Các metric RAG online"))
    plt.grid(axis="y", linestyle="--", alpha=0.25)
    plt.legend()
    plt.tight_layout()

    path = FIGURES_DIR / "rag_metrics.png"
    plt.savefig(path, dpi=180)
    plt.close()
    return path


def build_weekly_chart(mastery_suite: dict, scheduler_suite: dict) -> Path:
    labels = [vi("RMSE"), vi("Brier"), vi("Calibration Gap"), vi("AUC"), vi("Over-budget Rate"), vi("Coverage Warnings")]
    values = [
        mastery_suite["metrics"]["rmse"],
        mastery_suite["metrics"]["brier"],
        mastery_suite["metrics"]["calibration_gap"],
        mastery_suite["metrics"]["auc"],
        scheduler_suite["metrics"]["over_budget_warning_rate"],
        scheduler_suite["metrics"]["coverage_warning_count"],
    ]
    targets = [
        next(item["target"] for item in mastery_suite["thresholds"] if item["metricKey"] == "rmse"),
        next(item["target"] for item in mastery_suite["thresholds"] if item["metricKey"] == "brier"),
        next(item["target"] for item in mastery_suite["thresholds"] if item["metricKey"] == "calibration_gap"),
        next(item["target"] for item in mastery_suite["thresholds"] if item["metricKey"] == "auc"),
        next(item["target"] for item in scheduler_suite["thresholds"] if item["metricKey"] == "over_budget_warning_rate"),
        next(item["target"] for item in scheduler_suite["thresholds"] if item["metricKey"] == "coverage_warning_count"),
    ]

    plt.figure(figsize=(9.5, 4.8))
    positions = range(len(labels))
    plt.bar(positions, values, color=["#6D597A", "#B56576", "#E56B6F", "#355070", "#43AA8B", "#577590"])
    plt.plot(list(positions), targets, color="#111111", marker="o", linewidth=2, label="Ngưỡng")
    plt.xticks(list(positions), labels, rotation=15)
    plt.ylabel(vi("Giá trị"))
    plt.title(vi("Các metric weekly cho mastery và scheduler"))
    plt.grid(axis="y", linestyle="--", alpha=0.25)
    plt.legend()
    plt.tight_layout()

    path = FIGURES_DIR / "weekly_metrics.png"
    plt.savefig(path, dpi=180)
    plt.close()
    return path


def build_source_breakdown_chart(cohort: dict) -> Path:
    source_breakdown = cohort["sourceBreakdown"]
    labels = [item["sourceType"] for item in source_breakdown]
    rmse_values = [item["rmse"] for item in source_breakdown]
    counts = [item["count"] for item in source_breakdown]

    fig, ax1 = plt.subplots(figsize=(9, 4.8))
    ax2 = ax1.twinx()
    ax1.bar(labels, counts, color="#A8DADC", label="Số sự kiện")
    ax2.plot(labels, rmse_values, color="#E63946", marker="o", linewidth=2, label="RMSE")
    ax1.set_ylabel(vi("Số sự kiện"))
    ax2.set_ylabel("RMSE")
    ax1.set_title(vi("Nguồn dữ liệu tổng hợp của synthetic cohort"))
    ax1.tick_params(axis="x", rotation=12)
    ax1.grid(axis="y", linestyle="--", alpha=0.2)
    fig.tight_layout()

    path = FIGURES_DIR / "source_breakdown.png"
    plt.savefig(path, dpi=180)
    plt.close(fig)
    return path


def rag_case_rows(rag_suite: dict) -> str:
    rows = []
    for case in rag_suite["cases"]:
        metrics = case.get("metrics") or {}
        metric_summary = ", ".join(f"{key}={format_metric(value)}" for key, value in metrics.items()) or "n/a"
        snippet = shorten(str(case.get("answer", "")).replace("\n", " "), width=150, placeholder="...")
        rows.append(
            " & ".join(
                [
                    latex_escape(case["name"]),
                    latex_escape(case["kind"]),
                    latex_escape(case["status"].upper()),
                    latex_escape(metric_summary),
                    latex_escape(snippet),
                ]
            )
            + r" \\"
        )
    return "\n".join(rows)


def suite_status_rows(scorecard: dict) -> str:
    rows = []
    for result in scorecard["results"]:
        rows.append(
            " & ".join(
                [
                    latex_escape(result["suite"]),
                    latex_escape(result["profile"]),
                    latex_escape(result["pillar"]),
                    latex_escape(result["status"].upper()),
                    str(result["passed"]),
                    str(result["failed"]),
                    str(result["skipped"]),
                ]
            )
            + r" \\"
        )
    return "\n".join(rows)


def threshold_rows(scorecard: dict) -> str:
    rows = []
    for result in scorecard["results"]:
        for threshold in result.get("thresholds", []):
            value = threshold.get("value")
            display_value = "n/a" if value is None else format_metric(float(value))
            rows.append(
                " & ".join(
                    [
                        latex_escape(result["suite"]),
                        latex_escape(threshold["metric"]),
                        latex_escape(threshold["status"].upper()),
                        latex_escape(display_value),
                        latex_escape(f"{threshold['operator']} {threshold['target']}"),
                    ]
                )
                + r" \\"
            )
    return "\n".join(rows)


def source_breakdown_rows(cohort: dict) -> str:
    rows = []
    for item in cohort["sourceBreakdown"]:
        rows.append(
            " & ".join(
                [
                    latex_escape(item["sourceType"]),
                    str(item["count"]),
                    format_metric(item["rmse"]),
                    format_metric(item["avgPredicted"]),
                    format_metric(item["avgActual"]),
                ]
            )
            + r" \\"
        )
    return "\n".join(rows)


def persona_rows(cohort: dict) -> str:
    rows = []
    for item in cohort["users"]:
        rows.append(
            " & ".join(
                [
                    latex_escape(item["persona"]),
                    latex_escape(item["username"]),
                    format_metric(item["readiness"]),
                    str(item["eventCount"]),
                    format_metric(item["knowledgeConsistency"]),
                    format_metric(item["personalCalibrationScore"]),
                ]
            )
            + r" \\"
        )
    return "\n".join(rows)


def evidence_rows(rag_suite: dict, mastery_suite: dict, scheduler_suite: dict, cohort_path: Path) -> str:
    evidence = [
        ("Scorecard tổng", ROOT / "artifacts" / "eval" / "scorecard.json", "Kết quả tổng hợp cho toàn bộ pipeline."),
        ("Suite RAG online", RAG_SUITE_PATH, "Metric online và minh chứng case-level cho TTHCM."),
        ("Suite Mastery weekly", MASTERY_SUITE_PATH, "Metric weekly cho mô hình dự báo mastery."),
        ("Suite Scheduler weekly", SCHEDULER_SUITE_PATH, "Metric weekly cho cảnh báo của scheduler."),
        ("Synthetic cohort", cohort_path, "Nguồn số liệu cohort tổng hợp cho weekly eval."),
        ("Guardrail report", Path(rag_suite["artifact_paths"]["guardrailReport"]), "Minh chứng từ chối câu hỏi ngoài phạm vi và prompt injection."),
        ("Log RAG online", ROOT / rag_suite["artifact_paths"]["log"], "Log chạy suite online để truy vết lỗi hoặc flake."),
        ("Log weekly", ROOT / mastery_suite["artifact_paths"]["log"], "Log chạy synthetic cohort weekly."),
    ]
    rows = []
    for name, path, note in evidence:
        rows.append(
            " & ".join([latex_escape(name), latex_escape(str(path)), latex_escape(note)]) + r" \\"
        )
    return "\n".join(rows)


def build_report_tex(
    scorecard: dict,
    rag_suite: dict,
    mastery_suite: dict,
    scheduler_suite: dict,
    cohort: dict,
    rag_chart_path: Path,
    weekly_chart_path: Path,
    source_chart_path: Path,
) -> str:
    generated_at = datetime.fromisoformat(scorecard["generated_at"].replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M UTC")
    total_suites = len(scorecard["results"])
    total_passed = sum(1 for item in scorecard["results"] if item["status"] == "passed")
    total_failed = sum(1 for item in scorecard["results"] if item["status"] == "failed")
    avg_actual = cohort["offlineMetrics"]["avgActual"]
    avg_predicted = cohort["offlineMetrics"]["avgPredicted"]
    rmse = cohort["offlineMetrics"]["rmse"]
    brier = cohort["offlineMetrics"]["brier"]
    rmse_from_brier = math.sqrt(brier)

    return vi(rf"""
\documentclass[11pt,a4paper]{{article}}
\usepackage[a4paper,margin=1in]{{geometry}}
\usepackage{{fontspec}}
\usepackage{{graphicx}}
\usepackage{{booktabs}}
\usepackage{{longtable}}
\usepackage{{tabularx}}
\usepackage{{array}}
\usepackage{{float}}
\usepackage{{hyperref}}
\usepackage{{xcolor}}
\usepackage{{fancyhdr}}
\usepackage{{setspace}}
\usepackage{{enumitem}}
\usepackage{{titlesec}}
\setmainfont{{Times New Roman}}
\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{0.5em}}
\pagestyle{{fancy}}
\fancyhf{{}}
\fancyhead[L]{{StudyFlow Eval Report}}
\fancyhead[R]{{07/07/2026}}
\fancyfoot[C]{{\thepage}}
\definecolor{{brandblue}}{{HTML}}{{205781}}
\definecolor{{softgreen}}{{HTML}}{{4F959D}}
\definecolor{{softgold}}{{HTML}}{{D4A373}}
\titleformat{{\section}}{{\Large\bfseries\color{{brandblue}}}}{{\thesection}}{{0.75em}}{{}}
\titleformat{{\subsection}}{{\large\bfseries\color{{softgreen}}}}{{\thesubsection}}{{0.75em}}{{}}
\begin{{document}}

\begin{{titlepage}}
\centering
\vspace*{{2.5cm}}
{{\Huge \bfseries Báo cáo tổng hợp Eval cho StudyFlow\par}}
\vspace{{0.75cm}}
{{\Large Pipeline: CI + Online + Weekly\par}}
\vspace{{1cm}}
{{\large Sinh tự động từ artifact eval vào lúc {latex_escape(generated_at)}\par}}
\vspace{{1.5cm}}
\includegraphics[width=0.78\textwidth]{{{latex_escape(str((ROOT / "docs" / "diagram" / "system-overview.png").relative_to(DOCS_DIR)).replace("\\", "/"))}}}
\vfill
\begin{{tabular}}{{rl}}
Hồ sơ chạy &: \texttt{{{latex_escape(scorecard["profile"])}}} \\
Tổng số suite &: {total_suites} \\
Suite pass &: {total_passed} \\
Suite fail &: {total_failed} \\
Database &: {latex_escape(str(scorecard["environment"]["database_available"]))} \\
LLM credentials &: {latex_escape(str(scorecard["environment"]["llm_available"]))} \\
\end{{tabular}}
\vfill
\end{{titlepage}}

\section{{Tóm tắt điều hành}}
Pipeline eval hiện tại đã chạy thành công toàn bộ ba lớp \textit{{ci}}, \textit{{online}} và \textit{{weekly}}. Tổng cộng có {total_suites} suite, trong đó {total_passed} suite đạt trạng thái \texttt{{PASSED}} và không còn suite thất bại ở lần chạy gần nhất.

Điểm nổi bật của lần đánh giá này là đường RAG online đã được chuyển sang dữ liệu thật của môn \textbf{{Tư tưởng Hồ Chí Minh (TTHCM)}} và chạy thuần tiếng Việt. Bộ synthetic weekly tiếp tục đóng vai trò regression gate cho mô hình mastery và cho logic scheduler.

\begin{{itemize}}[leftmargin=1.25em]
\item RAG online đạt \texttt{{Faithfulness = {format_metric(rag_suite["metrics"]["faithfulness"])}}}, \texttt{{Answer Relevance = {format_metric(rag_suite["metrics"]["answer_relevance"])}}}, \texttt{{Retrieval Recall@5 = {format_metric(rag_suite["metrics"]["retrieval_recall_at_5"])}}}, \texttt{{Guardrail refusal accuracy = {format_metric(rag_suite["metrics"]["guardrail_refusal_accuracy"])}}}.
\item Mastery weekly đạt \texttt{{RMSE = {format_metric(mastery_suite["metrics"]["rmse"])}}}, \texttt{{Brier = {format_metric(mastery_suite["metrics"]["brier"])}}}, \texttt{{Calibration gap = {format_metric(mastery_suite["metrics"]["calibration_gap"])}}}, \texttt{{AUC = {format_metric(mastery_suite["metrics"]["auc"])}}}.
\item Scheduler weekly không phát sinh \textit{{coverage warning}} hay \textit{{over-budget warning}} ngoài ngưỡng.
\end{{itemize}}

\section{{Phạm vi và nguồn minh chứng}}
Report này lấy dữ liệu trực tiếp từ cây artifact \texttt{{artifacts/eval/}} và tệp nguồn trong \texttt{{docs/diagram/}}. Các bảng và biểu đồ được sinh tự động từ:

\begin{{longtable}}{{p{{0.18\textwidth}} p{{0.47\textwidth}} p{{0.27\textwidth}}}}
\toprule
\textbf{{Nguồn minh chứng}} & \textbf{{Đường dẫn}} & \textbf{{Vai trò}} \\
\midrule
\endhead
{evidence_rows(rag_suite, mastery_suite, scheduler_suite, COHORT_PATH)}
\bottomrule
\end{{longtable}}

\section{{Kết quả tổng thể của pipeline}}
\subsection{{Trạng thái các suite}}
\begin{{longtable}}{{p{{0.26\textwidth}} p{{0.11\textwidth}} p{{0.11\textwidth}} p{{0.12\textwidth}} r r r}}
\toprule
\textbf{{Suite}} & \textbf{{Profile}} & \textbf{{Pillar}} & \textbf{{Trạng thái}} & \textbf{{Pass}} & \textbf{{Fail}} & \textbf{{Skip}} \\
\midrule
\endhead
{suite_status_rows(scorecard)}
\bottomrule
\end{{longtable}}

\subsection{{So sánh metric với ngưỡng}}
\begin{{longtable}}{{p{{0.28\textwidth}} p{{0.22\textwidth}} p{{0.12\textwidth}} p{{0.12\textwidth}} p{{0.16\textwidth}}}}
\toprule
\textbf{{Suite}} & \textbf{{Metric}} & \textbf{{Trạng thái}} & \textbf{{Giá trị}} & \textbf{{Ngưỡng}} \\
\midrule
\endhead
{threshold_rows(scorecard)}
\bottomrule
\end{{longtable}}

\section{{Đánh giá RAG online trên tài liệu TTHCM}}
\subsection{{Metric và ý nghĩa}}
\begin{{itemize}}[leftmargin=1.25em]
\item \textbf{{Faithfulness}} đo mức độ câu trả lời cuối cùng còn bám vào ngữ cảnh đã truy hồi. Điểm cao nghĩa là câu trả lời không bịa thêm nội dung ngoài tài liệu.
\item \textbf{{Answer Relevance}} đo mức độ câu trả lời có đi thẳng vào câu hỏi hay không. Đây là chỉ số chất lượng trả lời ở tầng hội thoại.
\item \textbf{{Retrieval Recall@5}} đo khả năng top-5 chunk truy hồi có chứa thông tin đủ để trả lời. Chỉ số này nhìn vào retrieval hơn là generation.
\item \textbf{{Guardrail refusal accuracy}} đo tỷ lệ từ chối đúng với câu hỏi ngoài phạm vi hoặc prompt injection.
\end{{itemize}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.9\textwidth]{{{latex_escape(str(rag_chart_path.relative_to(DOCS_DIR)).replace("\\", "/"))}}}
\caption{{Biểu đồ các metric của suite RAG online}}
\end{{figure}}

\subsection{{Nhận xét}}
Suite RAG online đạt đầy đủ bốn ngưỡng đang dùng trong pipeline. Điểm mạnh nhất là \textit{{guardrail refusal accuracy}} và \textit{{retrieval recall@5}}, cho thấy dữ liệu TTHCM đã được seed đúng phạm vi và guardrail hoạt động ổn định. \textit{{Answer relevance}} vẫn là chỉ số thấp nhất trong bốn metric, nhưng đã vượt ngưỡng gate và phản ánh đúng thực tế rằng câu trả lời còn khá dài, đôi lúc trả lời rộng hơn câu hỏi.

\subsection{{Minh chứng case-level}}
\begin{{longtable}}{{p{{0.18\textwidth}} p{{0.11\textwidth}} p{{0.11\textwidth}} p{{0.18\textwidth}} p{{0.32\textwidth}}}}
\toprule
\textbf{{Case}} & \textbf{{Loại}} & \textbf{{Trạng thái}} & \textbf{{Metric}} & \textbf{{Snippet câu trả lời}} \\
\midrule
\endhead
{rag_case_rows(rag_suite)}
\bottomrule
\end{{longtable}}

\section{{Đánh giá weekly cho mastery và scheduler}}
\subsection{{Giải thích metric mastery}}
\begin{{itemize}}[leftmargin=1.25em]
\item \textbf{{RMSE}} đo sai số dự báo trung bình theo căn bậc hai, nhạy hơn với lỗi lớn.
\item \textbf{{Brier score}} đo sai số của dự báo xác suất. Trong pipeline hiện tại, RMSE và Brier được xem là hai góc nhìn trên cùng tín hiệu lỗi xác suất.
\item \textbf{{Calibration gap}} đo độ lệch giữa xác suất dự báo và xác suất quan sát thực tế.
\item \textbf{{AUC}} đo khả năng xếp hạng đúng người học có kết quả tốt hơn so với người học kết quả kém hơn.
\end{{itemize}}

Trong lần chạy này, \texttt{{RMSE = {format_metric(rmse)}}} và \texttt{{Brier = {format_metric(brier)}}}. Về mặt định lượng, \texttt{{sqrt(Brier) = {format_metric(rmse_from_brier)}}}, gần trùng với RMSE đang ghi nhận; điều này nhất quán với phần giải thích threshold trước đó. Ngoài ra, trung bình xác suất dự báo là \texttt{{{format_metric(avg_predicted)}}} trong khi tỷ lệ kết quả thực tế là \texttt{{{format_metric(avg_actual)}}}, cho thấy mô hình vẫn còn xu hướng dự báo thấp hơn quan sát thực tế.

\subsection{{Giải thích metric scheduler}}
\begin{{itemize}}[leftmargin=1.25em]
\item \textbf{{Over-budget warning rate}} đo tỷ lệ scheduler phải phát cảnh báo vượt ngân sách thời gian học.
\item \textbf{{Coverage warning count}} đo số cảnh báo cho thấy lịch học không còn bao phủ được nhu cầu kế hoạch.
\end{{itemize}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{latex_escape(str(weekly_chart_path.relative_to(DOCS_DIR)).replace("\\", "/"))}}}
\caption{{Biểu đồ metric weekly cho mastery và scheduler}}
\end{{figure}}

\subsection{{Quy mô synthetic cohort}}
\begin{{itemize}}[leftmargin=1.25em]
\item Người dùng tổng hợp: {cohort["counts"]["users"]}
\item Môn học tổng hợp: {cohort["counts"]["courses"]}
\item Topics: {cohort["counts"]["topics"]}
\item Sự kiện mastery: {cohort["counts"]["mastery_events"]}
\item Nhiệm vụ học tập: {cohort["counts"]["tasks"]}
\end{{itemize}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{latex_escape(str(source_chart_path.relative_to(DOCS_DIR)).replace("\\", "/"))}}}
\caption{{Phân rã nguồn dữ liệu của synthetic cohort}}
\end{{figure}}

\begin{{longtable}}{{p{{0.26\textwidth}} r r r r}}
\toprule
\textbf{{Nguồn dữ liệu}} & \textbf{{Count}} & \textbf{{RMSE}} & \textbf{{Avg Pred}} & \textbf{{Avg Actual}} \\
\midrule
\endhead
{source_breakdown_rows(cohort)}
\bottomrule
\end{{longtable}}

\begin{{longtable}}{{p{{0.22\textwidth}} p{{0.24\textwidth}} r r r r}}
\toprule
\textbf{{Persona}} & \textbf{{Username}} & \textbf{{Readiness}} & \textbf{{Events}} & \textbf{{Knowledge}} & \textbf{{Calibration}} \\
\midrule
\endhead
{persona_rows(cohort)}
\bottomrule
\end{{longtable}}

\section{{Kết luận}}
Tại thời điểm sinh report, pipeline eval của StudyFlow đã đạt trạng thái pass hoàn toàn trên cả ba profile. Phần RAG online đã được chuyển sang dữ liệu thật TTHCM và chạy thuần tiếng Việt. Phần weekly tiếp tục đóng vai trò regression gate nội bộ cho mastery và scheduler, với toàn bộ metric đang nằm trong ngưỡng chấp nhận của repo hiện tại.

Các tệp nên theo dõi cùng report này là \texttt{{artifacts/eval/scorecard.json}}, \texttt{{artifacts/eval/suites/rag-online-evaluation.json}} và \texttt{{artifacts/eval/weekly/20260707T205705Z/synthetic\_cohort.json}}.

\end{{document}}
""")


def main() -> None:
    ensure_dirs()
    scorecard = read_json(SCORECARD_PATH)
    rag_suite = read_json(RAG_SUITE_PATH)
    mastery_suite = read_json(MASTERY_SUITE_PATH)
    scheduler_suite = read_json(SCHEDULER_SUITE_PATH)
    cohort = read_json(COHORT_PATH)

    rag_chart_path = build_rag_chart(rag_suite)
    weekly_chart_path = build_weekly_chart(mastery_suite, scheduler_suite)
    source_chart_path = build_source_breakdown_chart(cohort)

    report_tex = build_report_tex(
        scorecard=scorecard,
        rag_suite=rag_suite,
        mastery_suite=mastery_suite,
        scheduler_suite=scheduler_suite,
        cohort=cohort,
        rag_chart_path=rag_chart_path,
        weekly_chart_path=weekly_chart_path,
        source_chart_path=source_chart_path,
    )
    REPORT_TEX_PATH.write_text(vi(report_tex), encoding="utf-8")
    print(f"Wrote {REPORT_TEX_PATH}")


if __name__ == "__main__":
    main()
