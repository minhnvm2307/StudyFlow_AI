from __future__ import annotations

import contextvars
import json
import logging
import os
import re
import time
import traceback
import uuid
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from fastapi import Request, Response

from app.config import settings

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

SENSITIVE_KEY_PATTERN = re.compile(
    r"authorization|cookie|password|passwd|token|secret|api[-_]?key|custom[-_]?api[-_]?key|openai[-_]?api[-_]?key|session",
    re.I,
)

_configured = False
_backend_root = Path(__file__).resolve().parents[2]


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        event = getattr(record, "event", None)
        if isinstance(event, dict):
            entry.update(redact(event))
        if record.exc_info:
            entry["error"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "Exception",
                "message": str(record.exc_info[1]),
                "stack": "".join(traceback.format_exception(*record.exc_info)),
            }
        return json.dumps(entry, ensure_ascii=False, default=str)


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        level_str = record.levelname.upper().ljust(7)
        logger_name = record.name
        message = record.getMessage()
        
        event = getattr(record, "event", None)
        if isinstance(event, dict) and event.get("method") and event.get("path"):
            method = event.get("method")
            path = event.get("path")
            status = event.get("statusCode")
            duration = event.get("durationMs")
            user_id = event.get("userId") or "anonymous"
            return f"[{timestamp}] {level_str} {logger_name} | {method} {path} - {status} ({duration}ms) | user: {user_id}"
            
        return f"[{timestamp}] {level_str} {logger_name} | {message}"


def configure_observability() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
    formatter = JsonFormatter()
    root_logger = logging.getLogger("studyflow")
    root_logger.setLevel(level)
    root_logger.propagate = False
    root_logger.handlers.clear()

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(ConsoleFormatter())
    root_logger.addHandler(console)

    hints_logger = logging.getLogger("studyflow.debug_hints")
    hints_logger.setLevel(logging.INFO)
    hints_logger.propagate = False
    hints_logger.handlers.clear()

    if settings.LOG_TO_FILE:
        log_dir = get_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        backend_handler = _rotating_handler(log_dir / "backend.jsonl", level, formatter)
        errors_handler = _rotating_handler(log_dir / "errors.jsonl", logging.WARNING, formatter)
        hints_handler = _rotating_handler(log_dir / "debug_hints.jsonl", logging.INFO, formatter)
        root_logger.addHandler(backend_handler)
        root_logger.addHandler(errors_handler)
        hints_logger.addHandler(hints_handler)


def get_log_dir() -> Path:
    configured = Path(settings.LOG_DIR)
    return configured if configured.is_absolute() else _backend_root / configured


def logging_status() -> dict[str, Any]:
    return {
        "enabled": bool(settings.LOG_TO_FILE),
        "dir": str(get_log_dir()),
        "level": settings.LOG_LEVEL,
    }


def log_event(level: str, message: str, **meta: Any) -> None:
    logger = logging.getLogger("studyflow")
    method = getattr(logger, level.lower(), logger.info)
    method(message, extra={"event": redact(meta)})


def log_debug_hint(error: BaseException | str, request_id: str | None = None, source: str = "backend", metadata: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if not settings.LOG_DEBUG_HINTS:
        return None
    hint = classify_debug_hint(error, source=source, metadata=metadata)
    if not hint:
        return None
    hint["requestId"] = request_id or get_request_id()
    logging.getLogger("studyflow.debug_hints").info("Debug hint", extra={"event": hint})
    return hint


def classify_debug_hint(error: BaseException | str, source: str = "backend", metadata: dict[str, Any] | None = None) -> dict[str, Any] | None:
    text = str(error).lower()
    name = error.__class__.__name__.lower() if isinstance(error, BaseException) else "message"
    combined = f"{name} {text}"

    if any(marker in combined for marker in ["connection refused", "connect call failed", "could not connect", "database", "db pool not initialised"]):
        category = "database_connection"
        likely_cause = "PostgreSQL is not reachable or DATABASE_URL points at the wrong host/port."
        suggested_action = "Check the PostgreSQL container/process and verify DATABASE_URL."
    elif any(marker in combined for marker in ["credentials not configured", "api key", "unauthorized", "401"]):
        category = "llm_credentials"
        likely_cause = "LLM provider credentials are missing or invalid."
        suggested_action = "Set CUSTOM_API_KEY/provider env vars or switch TOPIC_EXTRACTION_MODE for local debugging."
    elif any(marker in combined for marker in ["timeout", "timed out", "readtimeout"]):
        category = "llm_timeout" if any(marker in combined for marker in ["llm", "openai", "completion", "topic"]) else "timeout"
        likely_cause = "An upstream operation exceeded its timeout."
        suggested_action = "Retry the action, increase the timeout, or reduce the input size."
    elif any(marker in combined for marker in ["failed to fetch", "cannot reach backend", "vite"]):
        category = "frontend_failed_fetch"
        likely_cause = "The frontend could not reach the backend API origin."
        suggested_action = "Open the app through the Vite URL and verify /api/health through the same origin."
    elif any(marker in combined for marker in ["s3_bucket_name", "s3", "boto3"]):
        category = "s3_config"
        likely_cause = "S3 upload configuration is missing or incomplete."
        suggested_action = "Set S3 env vars or use a local-only upload path during development."
    else:
        return None

    return {
        "category": category,
        "likelyCause": likely_cause,
        "suggestedAction": suggested_action,
        "source": source,
        "metadata": redact(metadata or {}),
    }


def get_request_id() -> str | None:
    return request_id_var.get()


def redact(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, BaseException):
        return {"type": value.__class__.__name__, "message": str(value)}
    if isinstance(value, bytes):
        return f"[bytes:{len(value)}]"
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            out[key_text] = "[redacted]" if SENSITIVE_KEY_PATTERN.search(key_text) else redact(item)
        return out
    return str(value)


def log_payload(value: Any, max_chars: int | None = None) -> Any:
    if not settings.LOG_BODIES or value is None:
        return None
    redacted = redact(value)
    limit = max_chars if max_chars is not None else settings.LOG_BODY_MAX_CHARS
    serialized = json.dumps(redacted, ensure_ascii=False, default=str)
    if len(serialized) <= limit:
        return redacted
    return {
        "truncated": True,
        "sizeChars": len(serialized),
        "maxChars": limit,
        "preview": serialized[:limit],
    }


class ASGIRequestLoggingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        configure_observability()
        started = time.perf_counter()
        
        from starlette.datastructures import Headers
        headers = Headers(scope=scope)
        request_id = headers.get("x-request-id") or f"req_{int(time.time() * 1000):x}_{uuid.uuid4().hex[:8]}"
        token = request_id_var.set(request_id)
        
        status_code = 500
        
        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                # Add x-request-id header
                headers_list = list(message.get("headers", []))
                headers_list.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = headers_list
            await send(message)

        # To keep log parsing robust, construct a minimal log input payload
        input_payload = {
            "query": {},
            "contentType": headers.get("content-type") or None,
            "contentLength": None
        }
        if scope.get("query_string"):
            try:
                from urllib.parse import parse_qs
                input_payload["query"] = {
                    k: v[0] if len(v) == 1 else v
                    for k, v in parse_qs(scope["query_string"].decode("utf-8")).items()
                }
            except Exception:
                pass

        try:
            await self.app(scope, receive, send_wrapper)
            # Log completed request
            duration_ms = round((time.perf_counter() - started) * 1000)
            level = "error" if status_code >= 500 else "warning" if status_code >= 400 else "info"
            
            client_host = None
            if scope.get("client"):
                client_host = scope["client"][0]
                
            meta = {
                "requestId": request_id,
                "method": scope["method"],
                "path": scope["path"],
                "statusCode": status_code,
                "durationMs": duration_ms,
                "client": client_host,
                "userAgent": headers.get("user-agent"),
                "userId": input_payload["query"].get("user_id") or input_payload["query"].get("userId"),
                "input": input_payload,
                "output": None,
            }
            log_event(level, "HTTP request completed", **meta)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000)
            client_host = None
            if scope.get("client"):
                client_host = scope["client"][0]
                
            meta = {
                "requestId": request_id,
                "method": scope["method"],
                "path": scope["path"],
                "statusCode": 500,
                "durationMs": duration_ms,
                "client": client_host,
                "userAgent": headers.get("user-agent"),
                "userId": input_payload["query"].get("user_id") or input_payload["query"].get("userId"),
                "input": input_payload,
                "output": None,
            }
            logging.getLogger("studyflow").error("Unhandled request error", exc_info=exc, extra={"event": meta})
            raise
        finally:
            request_id_var.reset(token)


def get_logs_summary() -> dict[str, Any]:
    log_dir = get_log_dir()
    files = {
        "backend": log_dir / "backend.jsonl",
        "errors": log_dir / "errors.jsonl",
        "debugHints": log_dir / "debug_hints.jsonl",
    }
    counts_by_level: dict[str, int] = {}
    latest_error_at = None
    hint_categories: dict[str, int] = {}

    backend_rows = _read_jsonl(files["backend"])
    for row in backend_rows:
        level = str(row.get("level") or "unknown")
        counts_by_level[level] = counts_by_level.get(level, 0) + 1

    error_rows = _read_jsonl(files["errors"])
    for row in error_rows:
        latest_error_at = row.get("time") or latest_error_at

    hint_rows = _read_jsonl(files["debugHints"])
    for row in hint_rows[-50:]:
        category = str(row.get("category") or "unknown")
        hint_categories[category] = hint_categories.get(category, 0) + 1

    return {
        "enabled": bool(settings.LOG_TO_FILE),
        "dir": str(log_dir),
        "level": settings.LOG_LEVEL,
        "countsByLevel": counts_by_level,
        "latestErrorAt": latest_error_at,
        "latestHintCategories": hint_categories,
        "files": {
            key: {"path": str(path), "sizeBytes": path.stat().st_size if path.exists() else 0}
            for key, path in files.items()
        },
    }


def _rotating_handler(path: Path, level: int, formatter: logging.Formatter) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        path,
        maxBytes=settings.LOG_FILE_MAX_BYTES,
        backupCount=settings.LOG_FILE_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(formatter)
    return handler


async def _safe_request_input(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    content_length = request.headers.get("content-length")
    payload: dict[str, Any] = {
        "query": dict(request.query_params),
        "contentType": content_type or None,
        "contentLength": int(content_length) if content_length and content_length.isdigit() else None,
    }
    if settings.LOG_BODIES and "application/json" in content_type.lower():
        body = await request.body()
        request._receive = _receive_again(body, request.receive)  # type: ignore[attr-defined]
        if body:
            try:
                payload["body"] = json.loads(body.decode("utf-8"))
            except Exception:
                payload["body"] = body.decode("utf-8", errors="replace")[: settings.LOG_BODY_MAX_CHARS]
    elif "multipart/form-data" in content_type.lower():
        payload["multipart"] = True
    return payload


def _receive_again(body: bytes, original_receive):
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return await original_receive()
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


def _is_json_response(response: Response) -> bool:
    return "application/json" in (response.headers.get("content-type") or "").lower()


async def _capture_response_body(response: Response) -> tuple[Response, Any]:
    chunks = [chunk async for chunk in response.body_iterator]  # type: ignore[attr-defined]
    body = b"".join(chunks)
    output = None
    if body:
        try:
            output = json.loads(body.decode("utf-8"))
        except Exception:
            output = body.decode("utf-8", errors="replace")
    headers = dict(response.headers)
    headers.pop("content-length", None)
    rebuilt = Response(
        content=body,
        status_code=response.status_code,
        headers=headers,
        media_type=response.media_type,
        background=response.background,
    )
    return rebuilt, log_payload(output)


def _log_request(request: Request, request_id: str, status_code: int, started: float, input_payload: Any, output_payload: Any, error: Exception | None = None) -> None:
    duration_ms = round((time.perf_counter() - started) * 1000)
    level = "error" if status_code >= 500 or error else "warning" if status_code >= 400 else "info"
    meta = {
        "requestId": request_id,
        "method": request.method,
        "path": request.url.path,
        "statusCode": status_code,
        "durationMs": duration_ms,
        "client": request.client.host if request.client else None,
        "userAgent": request.headers.get("user-agent"),
        "userId": _selected_user_id(request, input_payload),
        "input": log_payload(input_payload),
        "output": output_payload,
    }
    if error:
        logging.getLogger("studyflow").error("Unhandled request error", exc_info=error, extra={"event": meta})
    else:
        log_event(level, "HTTP request completed", **meta)


def _selected_user_id(request: Request, input_payload: Any) -> str | None:
    query_user_id = request.query_params.get("user_id") or request.query_params.get("userId")
    if query_user_id:
        return query_user_id
    if isinstance(input_payload, dict) and isinstance(input_payload.get("body"), dict):
        body = input_payload["body"]
        value = body.get("user_id") or body.get("userId")
        return str(value) if value is not None else None
    return None

def _log_response_hint(request: Request, request_id: str, status_code: int, output_payload: Any) -> None:
    try:
        message = json.dumps(output_payload, ensure_ascii=False, default=str)
    except Exception:
        message = str(output_payload)
    log_debug_hint(
        message,
        request_id=request_id,
        source="response",
        metadata={"path": request.url.path, "statusCode": status_code},
    )

def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows


def log_upload_metadata(request_id: str | None, filename: str, mime_type: str | None, size: int, source: str = "source_upload") -> None:
    log_event(
        "info",
        "Upload received",
        requestId=request_id or get_request_id(),
        source=source,
        file={"filename": filename, "mimeType": mime_type, "size": size},
    )
