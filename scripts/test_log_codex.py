import json
from pathlib import Path

from scripts.log_codex import clean_prompt, extract_prompt, scan_codex_sessions


def test_clean_prompt_removes_environment_context():
    raw = [
        "<environment_context><cwd>C:/repo</cwd></environment_context>",
        "# Context from my IDE setup:\n\n## My request for Codex:\nFix the bug",
    ]
    assert clean_prompt(raw) == "# Context from my IDE setup:\n\n## My request for Codex:\nFix the bug"


def test_extract_prompt_skips_empty_environment_only_payload():
    payload = {
        "content": [
            {
                "type": "input_text",
                "text": "<environment_context><cwd>C:/repo</cwd></environment_context>",
            }
        ]
    }
    assert extract_prompt(payload) == ""


def test_scan_codex_sessions_collects_repo_user_prompt(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    subprocess_dir = repo_root / ".git"
    subprocess_dir.mkdir()
    sessions_dir = tmp_path / "sessions"
    day_dir = sessions_dir / "2026" / "06" / "28"
    day_dir.mkdir(parents=True)
    transcript = day_dir / "rollout-2026-06-28T00-00-00-session.jsonl"
    transcript.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {
                            "session_id": "session-1",
                            "source": "vscode",
                            "cwd": str(repo_root),
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-27T17:21:41.404Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": "<environment_context><cwd>C:/repo</cwd></environment_context>",
                                }
                            ],
                            "internal_chat_message_metadata_passthrough": {
                                "turn_id": "turn-1"
                            },
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-27T17:22:41.404Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": "Please log this Codex prompt",
                                }
                            ],
                            "internal_chat_message_metadata_passthrough": {
                                "turn_id": "turn-2"
                            },
                        },
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    state_file = tmp_path / "codex-state.json"
    log_dir = tmp_path / "ai-log"

    entries = scan_codex_sessions(
        repo_root=repo_root,
        sessions_dir=sessions_dir,
        log_dir=log_dir,
        state_file=state_file,
    )

    assert len(entries) == 1
    assert entries[0]["prompt"] == "Please log this Codex prompt"
