#!/usr/bin/env python3
"""
Collect Codex local chat prompts from ~/.codex/sessions and optionally submit
them to the AI log server.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

VN_TZ = timezone(timedelta(hours=7))
ENV_CONTEXT_RE = re.compile(
    r"<environment_context>.*?</environment_context>",
    re.DOTALL | re.IGNORECASE,
)


def git(cmd: str, cwd: Path) -> str:
    try:
        return subprocess.check_output(
            cmd.split(),
            shell=False,
            text=True,
            stderr=subprocess.DEVNULL,
            cwd=str(cwd),
        ).strip()
    except Exception:
        return ""


def normalize_path(path: str) -> str:
    return path.strip().lower().replace("/", "\\").rstrip("\\")


def load_state(state_file: Path) -> dict[str, Any]:
    if not state_file.exists():
        return {"files": {}, "logged_entry_ids": []}
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"files": {}, "logged_entry_ids": []}


def save_state(state_file: Path, state: dict[str, Any]) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_prompt(texts: list[str]) -> str:
    joined = "\n".join(texts).strip()
    if not joined:
        return ""
    cleaned = ENV_CONTEXT_RE.sub("", joined).strip()
    return cleaned.strip()


def extract_prompt(payload: dict[str, Any]) -> str:
    texts = [
        part.get("text", "")
        for part in payload.get("content", [])
        if part.get("type") == "input_text" and isinstance(part.get("text"), str)
    ]
    return clean_prompt(texts)


def build_entry(
    *,
    session_id: str,
    turn_id: str,
    prompt: str,
    repo_root: Path,
    transcript_path: Path,
    timestamp: str,
) -> dict[str, Any]:
    origin = git("git remote get-url origin", repo_root)
    repo = origin.rstrip("/").split("/")[-1] if origin else repo_root.name
    if repo.endswith(".git"):
        repo = repo[:-4]
    branch = git("git rev-parse --abbrev-ref HEAD", repo_root)
    commit = git("git rev-parse --short HEAD", repo_root)
    student = git("git config user.email", repo_root) or os.environ.get(
        "USERNAME",
        os.environ.get("USER", "unknown"),
    )
    entry_hash = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:12]
    return {
        "ts": timestamp,
        "tool": "codex",
        "event": "UserPrompt",
        "entry_id": f"codex-{session_id}-{turn_id}-{entry_hash}",
        "session_id": session_id,
        "turn_id": turn_id,
        "model": "gpt-5",
        "repo": repo,
        "branch": branch,
        "commit": commit,
        "student": student,
        "prompt": prompt[:4000],
        "response_summary": "",
        "transcript_path": str(transcript_path),
    }


def _session_matches_repo(meta: dict[str, Any], repo_root_n: str) -> bool:
    cwd = normalize_path(str(meta.get("cwd", "")))
    if not cwd or not repo_root_n:
        return False
    return cwd == repo_root_n or cwd.startswith(repo_root_n + "\\") or repo_root_n.startswith(cwd + "\\")


def iter_session_files(sessions_dir: Path) -> list[Path]:
    return sorted(sessions_dir.rglob("rollout-*.jsonl"))


def scan_codex_sessions(
    *,
    repo_root: Path,
    sessions_dir: Path,
    log_dir: Path,
    state_file: Path,
) -> list[dict[str, Any]]:
    repo_root_n = normalize_path(str(repo_root))
    state = load_state(state_file)
    files_state: dict[str, Any] = state.setdefault("files", {})
    logged_entry_ids = set(state.setdefault("logged_entry_ids", []))

    log_dir.mkdir(parents=True, exist_ok=True)
    new_entries: list[dict[str, Any]] = []

    for session_file in iter_session_files(sessions_dir):
        key = str(session_file)
        file_state = files_state.setdefault(
            key,
            {"offset": 0, "session_id": "", "repo_match": None, "source": "", "cwd": ""},
        )
        try:
            current_size = session_file.stat().st_size
        except OSError:
            continue
        if current_size < int(file_state.get("offset", 0)):
            file_state["offset"] = 0

        with session_file.open("r", encoding="utf-8") as handle:
            if int(file_state.get("offset", 0)) == 0:
                first_line = handle.readline()
                if first_line:
                    try:
                        meta_entry = json.loads(first_line)
                    except json.JSONDecodeError:
                        meta_entry = {}
                    if meta_entry.get("type") == "session_meta":
                        meta = meta_entry.get("payload", {})
                        file_state["session_id"] = meta.get("session_id") or meta.get("id") or ""
                        file_state["source"] = meta.get("source", "")
                        file_state["cwd"] = meta.get("cwd", "")
                        file_state["repo_match"] = _session_matches_repo(meta, repo_root_n)
                handle.seek(0)
            else:
                handle.seek(int(file_state.get("offset", 0)))

            if not file_state.get("repo_match") or "codex" not in str(file_state.get("source", "vscode")).lower() and file_state.get("source") != "vscode":
                handle.seek(0, os.SEEK_END)
                file_state["offset"] = handle.tell()
                continue

            for raw_line in handle:
                try:
                    record = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if record.get("type") != "response_item":
                    continue
                payload = record.get("payload", {})
                if payload.get("type") != "message" or payload.get("role") != "user":
                    continue
                turn_id = (
                    payload.get("internal_chat_message_metadata_passthrough", {}).get("turn_id")
                    or ""
                )
                prompt = extract_prompt(payload)
                if not turn_id or not prompt:
                    continue
                timestamp = record.get("timestamp")
                if timestamp:
                    try:
                        timestamp = (
                            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                            .astimezone(VN_TZ)
                            .isoformat()
                        )
                    except ValueError:
                        timestamp = datetime.now(VN_TZ).isoformat()
                else:
                    timestamp = datetime.now(VN_TZ).isoformat()
                entry = build_entry(
                    session_id=str(file_state.get("session_id", "")),
                    turn_id=turn_id,
                    prompt=prompt,
                    repo_root=repo_root,
                    transcript_path=session_file,
                    timestamp=timestamp,
                )
                if entry["entry_id"] in logged_entry_ids:
                    continue
                logged_entry_ids.add(entry["entry_id"])
                new_entries.append(entry)

            file_state["offset"] = handle.tell()

    state["logged_entry_ids"] = sorted(logged_entry_ids)[-5000:]
    save_state(state_file, state)
    return new_entries


def append_entries(log_file: Path, entries: list[dict[str, Any]]) -> None:
    if not entries:
        return
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run_submit(repo_root: Path) -> None:
    subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "submit_log.py")],
        cwd=str(repo_root),
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect Codex prompts into AI log.")
    parser.add_argument("--sessions-dir", default=str(Path.home() / ".codex" / "sessions"))
    parser.add_argument("--log-dir", default=".ai-log")
    parser.add_argument("--state-file", default=".ai-log/codex-state.json")
    parser.add_argument("--interval", type=int, default=10)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args()

    repo_root = Path.cwd()
    sessions_dir = Path(args.sessions_dir)
    log_dir = Path(args.log_dir)
    state_file = Path(args.state_file)
    log_file = log_dir / "session.jsonl"

    if not sessions_dir.exists():
        print(f"[codex-log] Sessions dir not found: {sessions_dir}", file=sys.stderr)
        return 0

    while True:
        entries = scan_codex_sessions(
            repo_root=repo_root,
            sessions_dir=sessions_dir,
            log_dir=log_dir,
            state_file=state_file,
        )
        append_entries(log_file, entries)
        if entries:
            print(f"[codex-log] Logged {len(entries)} prompt(s) from Codex.", file=sys.stderr)
            if args.submit:
                run_submit(repo_root)
        elif not args.loop:
            print("[codex-log] No new Codex prompts.", file=sys.stderr)

        if not args.loop:
            return 0
        time.sleep(max(3, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
