from pathlib import Path
import xml.etree.ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[2]
DIAGRAM_DIR = REPO_ROOT / "docs" / "diagram"
DRAWIO_PATH = DIAGRAM_DIR / "studyflow-architecture.drawio"
PNG_EXPORTS = [
    "system-overview.png",
    "runtime-container-view.png",
    "backend-internal-architecture.png",
    "document-and-rag-flow.png",
    "scheduling-and-practice-feedback-loop.png",
]


def _page_root(page_name: str) -> ET.Element:
    tree = ET.parse(DRAWIO_PATH)
    root = tree.getroot()
    for diagram in root.findall("diagram"):
        if diagram.attrib.get("name") == page_name:
            return diagram.find("mxGraphModel/root")
    raise AssertionError(f"missing diagram page: {page_name}")


def _labeled_edge_count(page_name: str) -> int:
    page_root = _page_root(page_name)
    count = 0
    for edge in page_root.findall("mxCell[@edge='1']"):
        if (edge.attrib.get("value") or "").strip():
            count += 1
    return count


def test_architecture_diagram_artifacts_exist():
    assert DIAGRAM_DIR.exists()
    assert (DIAGRAM_DIR / "README.md").exists()
    assert DRAWIO_PATH.exists()
    for export_name in PNG_EXPORTS:
        assert (DIAGRAM_DIR / export_name).exists()


def test_architecture_drawio_has_expected_pages():
    tree = ET.parse(DRAWIO_PATH)
    root = tree.getroot()
    page_names = [diagram.attrib.get("name") for diagram in root.findall("diagram")]

    assert page_names == [
        "System Overview",
        "Runtime / Container View",
        "Backend Internal Architecture",
        "Document and RAG Flow",
        "Scheduling and Practice Feedback Loop",
    ]


def test_root_readme_points_to_docs_diagram_set():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    expected_links = [
        "docs/diagram/README.md",
        "docs/diagram/studyflow-architecture.drawio",
        "docs/diagram/README.md#system-overview",
        "docs/diagram/README.md#runtime-container-view",
        "docs/diagram/README.md#backend-internal-architecture",
        "docs/diagram/README.md#document-and-rag-flow",
        "docs/diagram/README.md#scheduling-and-practice-feedback-loop",
    ]

    for link in expected_links:
        assert link in readme


def test_dense_pages_keep_edge_labels_sparse():
    assert _labeled_edge_count("Runtime / Container View") <= 6
    assert _labeled_edge_count("Document and RAG Flow") <= 6
    assert _labeled_edge_count("Scheduling and Practice Feedback Loop") <= 6
