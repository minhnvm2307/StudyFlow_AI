import re
import os
from datetime import datetime

# Regex patterns for PII
EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_REGEX = re.compile(r'(?:\+84|0)(?:3[2-9]|5[25689]|7[0|6-9]|8[1-9]|9[0-9])(?:\s?\d){7}')
CCCD_REGEX = re.compile(r'\b\d{9}\b|\b\d{12}\b')
CREDIT_CARD_REGEX = re.compile(r'\b(?:\d[ -]*?){13,16}\b')

# Harmful/toxic content keywords
HARMFUL_KEYWORDS = [
    "chế tạo bom", "bom mìn", "make bomb", "suicide", "tự tử",
    "hack", "ddos", "bẻ khóa", "vũ khí", "how to kill",
    "mua chất cấm", "ma túy", "chế chất nổ"
]

# Prompt injection keywords
PROMPT_INJECTION_KEYWORDS = [
    "bỏ qua chỉ dẫn", "bỏ qua tất cả chỉ dẫn", "ignore previous instructions",
    "hiển thị system prompt", "tiết lộ system prompt", "tiết lộ chỉ dẫn hệ thống",
    "show system prompt", "reveal system prompt", "bỏ qua các chỉ dẫn"
]

REPORT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "docs", "guardrail_report.md"))

def log_guardrail_violation(stage: str, original: str, processed: str, issues: list[str], action: str):
    """
    Logs the guardrail event to backend/docs/guardrail_report.md as a table row.
    """
    try:
        os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
        
        # Initialize file with header if it doesn't exist
        if not os.path.exists(REPORT_PATH):
            with open(REPORT_PATH, "w", encoding="utf-8") as f:
                f.write("# Guardrail Audit & Protection Report\n\n")
                f.write("This report documents the safety measures, sanitization logic, and audit trail for the StudyFlow Chatbot system.\n\n")
                f.write("## Guardrail Methodology\n")
                f.write("1. **PII Masking & Scrubbing (Regex-Based)**: Masks Emails, Phone Numbers, CCCD, and Credit Cards.\n")
                f.write("2. **Input/Output Safety Moderation (Keyword Blacklist)**: Blocks messages matching toxic/harmful keywords.\n")
                f.write("3. **Platform Limitations Guardrail**: Implements API-level limit constraints (e.g. Max 10 subjects).\n\n")
                f.write("| Timestamp | Stage | Original Text | Processed/Masked Text | Issues Found | Action Taken |\n")
                f.write("| --- | --- | --- | --- | --- | --- |\n")
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Escape markdown piping in texts to preserve table format
        esc_orig = original.replace("|", "\\|").replace("\n", " ")[:150]
        esc_proc = processed.replace("|", "\\|").replace("\n", " ")[:150]
        esc_issues = ", ".join(issues)
        
        with open(REPORT_PATH, "a", encoding="utf-8") as f:
            f.write(f"| {timestamp} | {stage} | {esc_orig} | {esc_proc} | {esc_issues} | {action} |\n")
    except Exception as e:
        # Prevent logging errors from crashing the main chat pipeline
        print(f"[Guardrail Logger Error] {e}")

def guardrail_check_input(text: str) -> tuple[str, bool, list[str]]:
    """
    Checks user input for PII and harmful content.
    Returns: (cleaned_text, is_safe, issues_list)
    """
    if not text:
        return text, True, []
        
    issues = []
    cleaned = text
    
    # Check safety
    lower_text = text.lower()
    unsafe_found = [kw for kw in HARMFUL_KEYWORDS if kw in lower_text]
    if unsafe_found:
        issues.append(f"Unsafe Content Detected ({', '.join(unsafe_found)})")
        log_guardrail_violation("INPUT", text, "[BLOCKED]", issues, "BLOCKED")
        return text, False, issues
        
    # Check prompt injection
    injection_found = [kw for kw in PROMPT_INJECTION_KEYWORDS if kw in lower_text]
    if injection_found:
        issues.append(f"Prompt Injection Detected ({', '.join(injection_found)})")
        log_guardrail_violation("INPUT", text, "[BLOCKED]", issues, "BLOCKED")
        return text, False, issues
        
    # Check and mask PII
    if EMAIL_REGEX.search(cleaned):
        cleaned = EMAIL_REGEX.sub("[EMAIL_REDACTED]", cleaned)
        issues.append("Email Pattern")
        
    if PHONE_REGEX.search(cleaned):
        cleaned = PHONE_REGEX.sub("[PHONE_REDACTED]", cleaned)
        issues.append("Phone Pattern")
        
    if CCCD_REGEX.search(cleaned):
        cleaned = CCCD_REGEX.sub("[CCCD_REDACTED]", cleaned)
        issues.append("CCCD/ID Pattern")
        
    if CREDIT_CARD_REGEX.search(cleaned):
        cleaned = CREDIT_CARD_REGEX.sub("[CARD_REDACTED]", cleaned)
        issues.append("Credit Card Pattern")
        
    if issues:
        log_guardrail_violation("INPUT", text, cleaned, issues, "MASKED")
        
    return cleaned, True, issues

def guardrail_check_output(text: str) -> tuple[str, bool, list[str]]:
    """
    Checks assistant output for PII leakage.
    Returns: (cleaned_text, is_safe, issues_list)
    """
    if not text:
        return text, True, []
        
    issues = []
    cleaned = text
    
    # We do not block output for safety keywords normally (unless it is extreme, but
    # here we focus on preventing AI from spilling/generating PII data).
    if EMAIL_REGEX.search(cleaned):
        cleaned = EMAIL_REGEX.sub("[EMAIL_REDACTED]", cleaned)
        issues.append("Email Pattern")
        
    if PHONE_REGEX.search(cleaned):
        cleaned = PHONE_REGEX.sub("[PHONE_REDACTED]", cleaned)
        issues.append("Phone Pattern")
        
    if CCCD_REGEX.search(cleaned):
        cleaned = CCCD_REGEX.sub("[CCCD_REDACTED]", cleaned)
        issues.append("CCCD/ID Pattern")
        
    if CREDIT_CARD_REGEX.search(cleaned):
        cleaned = CREDIT_CARD_REGEX.sub("[CARD_REDACTED]", cleaned)
        issues.append("Credit Card Pattern")
        
    if issues:
        log_guardrail_violation("OUTPUT", text, cleaned, issues, "MASKED")
        
    return cleaned, True, issues
