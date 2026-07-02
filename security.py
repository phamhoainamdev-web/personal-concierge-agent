"""
security.py — SECURITY & PRIVACY PILLAR (Day 4)

================================ SECURITY ================================
This module emulates the "Policy Server" from the Day 4 whitepaper:
 - policy_check(): a control gate that runs BEFORE any tool is executed.
   Only tools in the allowlist are permitted to run.
 - mask_pii(): masks sensitive info (email, phone number) BEFORE printing to
   the screen or writing to a log, to avoid leaking personal data.
 - Secrets (API key) are read only from .env via python-dotenv, never hardcoded.
 - User data stays local in data/tasks.json and is not sent anywhere.
========================================================================
"""

import re

# SECURITY — Allowlist: the set of tools permitted to run.
# Any tool NOT in this set is rejected ("Policy Violation").
# Includes the 5 internal task tools + 2 time tools consumed VIA MCP (mcp-server-time).
# Explicitly allowlisting even the MCP tools is an anti MCP-spoofing layer (Day 4): even if
# the server advertises extra unknown tools, the agent only permits exactly these.
ALLOWED_TOOLS = {
    "add_task",
    "list_tasks",
    "complete_task",
    "delete_task",
    "plan_day",
    "get_current_time",
    "convert_time",
}


def policy_check(tool_name: str, args: dict) -> tuple[bool, str]:
    """
    SECURITY — Policy gate (emulates the Policy Server).

    Called in the ACT step, RIGHT BEFORE executing the tool the model chose.
    - If the tool is in the allowlist   -> (True, "OK")  : allowed to run.
    - If the tool is unknown / not allowed -> (False, "Policy Violation: ...") : rejected.

    Returns a text message so the agent can handle it gently, WITHOUT crashing the program.
    """
    if tool_name not in ALLOWED_TOOLS:
        return (
            False,
            f"Policy Violation: tool '{tool_name}' không nằm trong danh sách "
            f"cho phép ({', '.join(sorted(ALLOWED_TOOLS))}). Yêu cầu bị từ chối.",
        )

    # (Could be extended: validate args here, e.g. block odd paths, system commands...)
    if not isinstance(args, dict):
        return (False, "Policy Violation: tham số tool không hợp lệ.")

    return (True, "OK")


def log_tool_call(tool_name: str, args: dict, allowed: bool) -> None:
    """
    SECURITY — Log every tool call (name + timestamp + allowed or blocked).

    All arguments are passed through mask_pii() BEFORE printing, so emails/phone numbers
    never leak into the log.
    """
    from datetime import datetime

    status = "ALLOW" if allowed else "DENY"
    safe_args = mask_pii(", ".join(f"{k}={v}" for k, v in (args or {}).items()))
    print(f"[TOOL {datetime.now().isoformat(timespec='seconds')}] {status} {tool_name}({safe_args})")


# SECURITY — Regex patterns that identify PII to mask.
_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+\-])([A-Za-z0-9._%+\-]*)(@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})")
# Vietnamese phone numbers: 9-11 digits (may include spaces, '.', '-', or a leading +84).
_PHONE_RE = re.compile(r"(?<!\w)(\+?\d[\d\s.\-]{7,12}\d)(?!\w)")


def _mask_email(match: re.Match) -> str:
    """Keep the first char of the name, mask the rest: 'abcd@gmail.com' -> 'a***@gmail.com'."""
    first, middle, domain = match.group(1), match.group(2), match.group(3)
    return f"{first}***{domain}"


def _mask_phone(match: re.Match) -> str:
    """Keep the first 2 + last 2 digits, mask the middle: '0901234589' -> '09******89'."""
    digits = re.sub(r"\D", "", match.group(1))
    # Require >= 9 digits: VN phones have 10 (or +84 + 9), while dates like
    # '2026-07-02' only have 8 — so real dates never get masked as phones.
    if len(digits) < 9:
        return match.group(1)
    return digits[:2] + "*" * (len(digits) - 4) + digits[-2:]


def mask_pii(text: str) -> str:
    """
    SECURITY — Mask emails and phone numbers before PRINTING to screen or WRITING a log.

    Example:
        "Contact abcd@gmail.com or 0901234589"
        -> "Contact a***@gmail.com or 09******89"
    """
    if not text:
        return text
    text = _EMAIL_RE.sub(_mask_email, text)
    text = _PHONE_RE.sub(_mask_phone, text)
    return text
