"""
security.py — TRỤ CỘT BẢO MẬT & QUYỀN RIÊNG TƯ (Day 4)

================================ BẢO MẬT ================================
Module này mô phỏng "Policy Server" trong whitepaper Day 4:
 - policy_check(): cổng kiểm soát chạy TRƯỚC khi bất kỳ tool nào được thực thi.
   Chỉ những tool nằm trong allowlist mới được phép chạy.
 - mask_pii(): che thông tin nhạy cảm (email, số điện thoại) TRƯỚC KHI in ra
   màn hình hoặc ghi log, tránh rò rỉ dữ liệu cá nhân.
 - Secrets (API key) chỉ đọc từ .env qua python-dotenv, KHÔNG hardcode trong code.
 - Dữ liệu người dùng chỉ nằm cục bộ trong data/tasks.json, không gửi ra ngoài.
========================================================================
"""

import re

# BẢO MẬT — Allowlist: danh sách các tool được phép chạy.
# Bất kỳ tool nào KHÔNG nằm trong tập này đều bị từ chối ("Policy Violation").
# Gồm 5 tool việc nội bộ + 2 tool thời gian tiêu thụ QUA MCP (mcp-server-time).
# Việc allowlist tường minh cả tool MCP là lớp chống MCP spoofing (Day 4): dù server
# có quảng cáo thêm tool lạ, agent chỉ cho phép đúng những cái ở đây.
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
    BẢO MẬT — Cổng chính sách (mô phỏng Policy Server).

    Được gọi ở bước ACT, NGAY TRƯỚC khi thực thi tool mà model chọn.
    - Nếu tool nằm trong allowlist  -> (True, "OK")  : cho phép chạy.
    - Nếu tool lạ / ngoài allowlist  -> (False, "Policy Violation: ...") : từ chối.

    Trả về thông báo dạng văn bản để agent tự xử lý nhẹ nhàng, KHÔNG làm crash chương trình.
    """
    if tool_name not in ALLOWED_TOOLS:
        return (
            False,
            f"Policy Violation: tool '{tool_name}' không nằm trong danh sách "
            f"cho phép ({', '.join(sorted(ALLOWED_TOOLS))}). Yêu cầu bị từ chối.",
        )

    # (Có thể mở rộng: kiểm tra args ở đây, ví dụ chặn đường dẫn lạ, lệnh hệ thống...)
    if not isinstance(args, dict):
        return (False, "Policy Violation: tham số tool không hợp lệ.")

    return (True, "OK")


def log_tool_call(tool_name: str, args: dict, allowed: bool) -> None:
    """
    BẢO MẬT — Ghi log mỗi lần gọi tool (tên + thời điểm + cho phép hay bị chặn).

    Mọi tham số được đưa qua mask_pii() TRƯỚC KHI in, để email/SĐT không lọt vào log.
    """
    from datetime import datetime

    status = "ALLOW" if allowed else "DENY"
    safe_args = mask_pii(", ".join(f"{k}={v}" for k, v in (args or {}).items()))
    print(f"[TOOL {datetime.now().isoformat(timespec='seconds')}] {status} {tool_name}({safe_args})")


# BẢO MẬT — Các mẫu (regex) nhận diện PII cần che.
_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+\-])([A-Za-z0-9._%+\-]*)(@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})")
# Số điện thoại VN: 9–11 chữ số (có thể có dấu cách, '.', '-' hoặc +84 ở đầu).
_PHONE_RE = re.compile(r"(?<!\w)(\+?\d[\d\s.\-]{7,12}\d)(?!\w)")


def _mask_email(match: re.Match) -> str:
    """Giữ ký tự đầu của tên, che phần còn lại: 'abcd@gmail.com' -> 'a***@gmail.com'."""
    first, middle, domain = match.group(1), match.group(2), match.group(3)
    return f"{first}***{domain}"


def _mask_phone(match: re.Match) -> str:
    """Giữ 2 số đầu + 2 số cuối, che ở giữa: '0901234589' -> '09******89'."""
    digits = re.sub(r"\D", "", match.group(1))
    if len(digits) < 6:
        return match.group(1)
    return digits[:2] + "*" * (len(digits) - 4) + digits[-2:]


def mask_pii(text: str) -> str:
    """
    BẢO MẬT — Che email và số điện thoại trước khi IN RA màn hình hoặc GHI LOG.

    Ví dụ:
        "Liên hệ abcd@gmail.com hoặc 0901234589"
        -> "Liên hệ a***@gmail.com hoặc 09******89"
    """
    if not text:
        return text
    text = _EMAIL_RE.sub(_mask_email, text)
    text = _PHONE_RE.sub(_mask_phone, text)
    return text
