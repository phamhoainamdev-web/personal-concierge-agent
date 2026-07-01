"""
tools.py — Tool use / Function calling (Day 2)

================ KHÁI NIỆM 3 — TOOL USE / FUNCTION CALLING =================
File này định nghĩa các HÀM PYTHON THẬT thao tác dữ liệu việc-cần-làm
(đọc/ghi data/tasks.json), đồng thời KHAI BÁO chúng cho Gemini bằng
function calling (TOOL_DECLARATIONS).

Model sẽ tự quyết định gọi tool nào dựa trên câu của người dùng; còn code ở
đây mới là nơi THỰC THI tool thật và trả kết quả về cho model.
============================================================================
"""

import json
import os
from datetime import date

# Đường dẫn storage cục bộ. BẢO MẬT: dữ liệu chỉ nằm trên máy, không gửi ra ngoài.
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_TASKS_FILE = os.path.join(_DATA_DIR, "tasks.json")


# --------------------------- Helpers lưu trữ JSON ---------------------------
def _load() -> list[dict]:
    """Đọc danh sách task từ tasks.json (tạo file rỗng nếu chưa có)."""
    if not os.path.exists(_TASKS_FILE):
        return []
    try:
        with open(_TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        # File hỏng -> coi như rỗng, tránh crash.
        return []


def _save(tasks: list[dict]) -> None:
    """Ghi danh sách task xuống tasks.json (tạo thư mục data/ nếu thiếu)."""
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)


def _next_id(tasks: list[dict]) -> int:
    """Sinh id mới = id lớn nhất hiện có + 1."""
    return (max((t["id"] for t in tasks), default=0)) + 1


# ------------------------------ Các tool thật ------------------------------
def add_task(title: str, due: str = "") -> dict:
    """Thêm một việc cần làm. due là hạn (chuỗi tự do, có thể rỗng)."""
    title = (title or "").strip()
    if not title:
        return {"ok": False, "message": "Tiêu đề việc không được để trống."}
    tasks = _load()
    task = {"id": _next_id(tasks), "title": title, "due": due.strip(), "done": False}
    tasks.append(task)
    _save(tasks)
    return {"ok": True, "message": f"Đã thêm việc #{task['id']}: {task['title']}", "task": task}


def list_tasks() -> dict:
    """Liệt kê tất cả việc cần làm."""
    tasks = _load()
    return {"ok": True, "count": len(tasks), "tasks": tasks}


def complete_task(task_id: int) -> dict:
    """Đánh dấu một việc là đã hoàn thành theo id."""
    try:
        task_id = int(task_id)
    except (TypeError, ValueError):
        return {"ok": False, "message": "task_id phải là số."}
    tasks = _load()
    for t in tasks:
        if t["id"] == task_id:
            t["done"] = True
            _save(tasks)
            return {"ok": True, "message": f"Đã đánh dấu xong việc #{task_id}: {t['title']}", "task": t}
    return {"ok": False, "message": f"Không tìm thấy việc #{task_id}."}


def delete_task(task_id: int) -> dict:
    """Xóa một việc theo id."""
    try:
        task_id = int(task_id)
    except (TypeError, ValueError):
        return {"ok": False, "message": "task_id phải là số."}
    tasks = _load()
    for i, t in enumerate(tasks):
        if t["id"] == task_id:
            removed = tasks.pop(i)
            _save(tasks)
            return {"ok": True, "message": f"Đã xóa việc #{task_id}: {removed['title']}"}
    return {"ok": False, "message": f"Không tìm thấy việc #{task_id}."}


def plan_day() -> dict:
    """
    Đọc các việc CHƯA hoàn thành và trả về để model gợi ý thứ tự làm trong ngày.
    (Việc sắp xếp/giải thích sẽ do model làm khi đã nạp skill planning-day.)
    """
    tasks = _load()
    pending = [t for t in tasks if not t.get("done")]
    return {
        "ok": True,
        "today": date.today().isoformat(),
        "pending_count": len(pending),
        "pending_tasks": pending,
    }


# Bảng tra cứu: tên tool -> hàm Python thật để THỰC THI ở bước ACT.
TOOL_FUNCTIONS = {
    "add_task": add_task,
    "list_tasks": list_tasks,
    "complete_task": complete_task,
    "delete_task": delete_task,
    "plan_day": plan_day,
}


def build_tool_declarations(types):
    """
    KHÁI NIỆM 3 — Khai báo function declarations cho Gemini.

    Nhận module `google.genai.types` từ agent để dựng schema cho từng tool.
    Đây chính là phần "mô tả tool" mà model đọc để biết có thể gọi hàm nào,
    cần tham số gì.
    """
    return types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="add_task",
                description="Thêm một việc cần làm (to-do) mới vào danh sách.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "title": types.Schema(type=types.Type.STRING, description="Tên/nội dung việc cần làm."),
                        "due": types.Schema(type=types.Type.STRING, description="Hạn chót (tùy chọn), ví dụ '6/7' hoặc '6/7/2026'."),
                    },
                    required=["title"],
                ),
            ),
            types.FunctionDeclaration(
                name="list_tasks",
                description="Liệt kê toàn bộ việc cần làm hiện có.",
                parameters=types.Schema(type=types.Type.OBJECT, properties={}),
            ),
            types.FunctionDeclaration(
                name="complete_task",
                description="Đánh dấu một việc là đã hoàn thành theo id.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={"task_id": types.Schema(type=types.Type.INTEGER, description="id của việc cần đánh dấu xong.")},
                    required=["task_id"],
                ),
            ),
            types.FunctionDeclaration(
                name="delete_task",
                description="Xóa một việc khỏi danh sách theo id.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={"task_id": types.Schema(type=types.Type.INTEGER, description="id của việc cần xóa.")},
                    required=["task_id"],
                ),
            ),
            types.FunctionDeclaration(
                name="plan_day",
                description="Đọc các việc chưa làm để lập kế hoạch / gợi ý thứ tự làm trong ngày.",
                parameters=types.Schema(type=types.Type.OBJECT, properties={}),
            ),
        ]
    )
