"""
tools.py — Tool use / Function calling (Day 2)

================ CONCEPT 3 — TOOL USE / FUNCTION CALLING =================
This file defines the REAL PYTHON FUNCTIONS that manipulate the to-do data
(read/write data/tasks.json), and also DECLARES them to Gemini via
function calling (TOOL_DECLARATIONS).

The model decides which tool to call based on the user's sentence; the code
here is where the real tool is EXECUTED and the result returned to the model.
============================================================================
"""

import json
import os
from datetime import date

# Local storage path. SECURITY: data stays on the machine and is not sent anywhere.
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_TASKS_FILE = os.path.join(_DATA_DIR, "tasks.json")


# --------------------------- JSON storage helpers ---------------------------
def _load() -> list[dict]:
    """Read the task list from tasks.json (return empty if the file doesn't exist yet)."""
    if not os.path.exists(_TASKS_FILE):
        return []
    try:
        with open(_TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        # Corrupt file -> treat as empty, avoid crashing.
        return []


def _save(tasks: list[dict]) -> None:
    """Write the task list to tasks.json (create the data/ directory if missing)."""
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)


def _next_id(tasks: list[dict]) -> int:
    """Generate a new id = current max id + 1."""
    return (max((t["id"] for t in tasks), default=0)) + 1


# ------------------------------ The real tools ------------------------------
def add_task(title: str, due: str = "") -> dict:
    """Add a to-do item. `due` is the deadline (free-form string, may be empty)."""
    title = (title or "").strip()
    if not title:
        return {"ok": False, "message": "Tiêu đề việc không được để trống."}
    tasks = _load()
    task = {"id": _next_id(tasks), "title": title, "due": due.strip(), "done": False}
    tasks.append(task)
    _save(tasks)
    return {"ok": True, "message": f"Đã thêm việc #{task['id']}: {task['title']}", "task": task}


def list_tasks() -> dict:
    """List all to-do items."""
    tasks = _load()
    return {"ok": True, "count": len(tasks), "tasks": tasks}


def complete_task(task_id: int) -> dict:
    """Mark a task as done by id."""
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
    """Delete a task by id."""
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
    Read the UNfinished tasks and return them so the model can suggest an order for the day.
    (The ordering/explanation is done by the model once the planning-day skill is loaded.)
    """
    tasks = _load()
    pending = [t for t in tasks if not t.get("done")]
    return {
        "ok": True,
        "today": date.today().isoformat(),
        "pending_count": len(pending),
        "pending_tasks": pending,
    }


# Lookup table: tool name -> the real Python function to EXECUTE in the ACT step.
TOOL_FUNCTIONS = {
    "add_task": add_task,
    "list_tasks": list_tasks,
    "complete_task": complete_task,
    "delete_task": delete_task,
    "plan_day": plan_day,
}


def build_tool_declarations(types):
    """
    CONCEPT 3 — Build the function declarations for Gemini.

    Takes the `google.genai.types` module from the agent to build a schema for each tool.
    This is the "tool description" the model reads to know which functions it can call
    and what parameters they need.

    NOTE: the description strings below are kept in Vietnamese on purpose — they are part
    of the prompt the model reads to route tool calls, so translating them could change routing.
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
