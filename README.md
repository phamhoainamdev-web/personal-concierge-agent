# Personal Concierge Agent

Trợ lý cá nhân ("Personal Concierge") chạy trong **terminal**, giúp bạn **quản lý việc cần làm**:
thêm việc, xem danh sách, đánh dấu hoàn thành, xóa việc và lập kế hoạch trong ngày.
Dữ liệu lưu **cục bộ** trong `data/tasks.json` — không gửi đi đâu (chỉ gọi Gemini để hiểu yêu cầu).
Agent còn là **MCP client**, tiêu thụ server chính thức **mcp-server-time** để biết ngày/giờ thật.

## Sơ đồ

```
                      security: policy_check() + mask_pii() bọc ngoài MỌI lời gọi
        ┌─────────────────────────────────────────────────────────────────┐
        │                                                                   │
User ⇄ agent.py  ── task tools (add/list/complete/delete/plan) ─► data/tasks.json
        │  (Gemini + skills + MCP client)                                   │
        │                                                                   │
        └── MCP client ⇄ [stdio] ⇄ mcp-server-time (official) : get_current_time / convert_time
```
Gemini nhìn thấy **7 tool** (5 tool việc + 2 tool thời gian gộp chung). `policy_check()` gác
trước mọi tool (kể cả tool MCP), `mask_pii()` che PII trước khi in.

## Chạy thế nào

Yêu cầu: Python (đã test trên Windows + Python 3.14). MCP time server chạy sẵn qua
`python -m mcp_server_time` — không cần API key.

```bash
# 1) Tạo & kích hoạt môi trường ảo
python -m venv .venv
.venv\Scripts\activate         # Windows (PowerShell/CMD)

# 2) Cài thư viện
pip install -r requirements.txt

# 3) Tạo file .env và điền API key (KHÔNG hardcode trong code)
copy .env.example .env         # Windows
#   rồi mở .env, sửa: GEMINI_API_KEY=khoa_api_that_cua_ban

# 4) Chạy
python main.py
```

Trong vòng chat, gõ `thoát` hoặc `exit` để dừng.

### Thử nhanh
- `thêm việc nộp capstone hạn 6/7` → tạo task, lưu vào `data/tasks.json` (nạp skill `adding-tasks`)
- `xem việc của tôi` → liệt kê task
- `lập kế hoạch hôm nay cho tôi` → nạp skill `planning-day` và gợi ý thứ tự
- `hôm nay là ngày mấy?` → gọi `get_current_time` **qua MCP** → ngày thật
- `còn mấy ngày tới hạn nộp capstone?` → dùng ngày thật (MCP) để tính
- `đánh dấu việc 1 xong` → cập nhật trạng thái
- Nhập email/số điện thoại → khi in lại sẽ bị che (ví dụ `a***@gmail.com`, `09******89`)

## Khái niệm khóa học đã thể hiện

| Khái niệm | Thể hiện ở đâu |
|---|---|
| **1. Agent system** (Perceive → Plan → Act → Observe) | `agent.py` → `ConciergeAgent.run_turn()`: có comment đánh dấu rõ 4 bước; `main.py` nhận input (Perceive). |
| **2. Agent Skills** ✓ (chuẩn SKILL.md) | `agent.py` → `discover_skills()` (metadata luôn sẵn) + `select_skill()` (nạp theo `description`, progressive disclosure) + `load_skill()` (nạp thân khi trúng); skill ở `skills/adding-tasks/SKILL.md`, `skills/planning-day/SKILL.md`. |
| **3. Tool use / Function calling** | `tools.py`: 5 hàm thật (`add_task`, `list_tasks`, `complete_task`, `delete_task`, `plan_day`) + `build_tool_declarations()` khai báo cho Gemini. |
| **4. MCP** ✓ (consume server có sẵn) | `agent.py` → `start_mcp()` mở phiên stdio tới **mcp-server-time** và gộp `get_current_time`/`convert_time` vào tool cho Gemini; `_call_mcp_tool()` gọi qua MCP. Không tự xây server. |
| **TRỤ CỘT — Bảo mật & quyền riêng tư** ✓ | `security.py`: `policy_check()` (allowlist gồm cả tool MCP, chống spoofing) gọi **trước** mọi tool ở bước ACT; `log_tool_call()` + `mask_pii()` che email/SĐT trước khi in/log. Secrets đọc từ `.env` qua dotenv; `.gitignore` bỏ `.env`, `data/`. |

## Cấu trúc thư mục

```
concierge/
  main.py            # vòng lặp chat async; mở/đóng phiên MCP
  agent.py           # Gemini + function calling + skills (SKILL.md) + MCP client
  tools.py           # các tool việc thao tác data/tasks.json
  security.py        # trụ cột bảo mật (policy_check, mask_pii, log_tool_call)
  skills/
    adding-tasks/
      SKILL.md       # frontmatter name+description + hướng dẫn thêm việc
    planning-day/
      SKILL.md       # frontmatter name+description + hướng dẫn lập kế hoạch
  data/
    tasks.json       # storage cục bộ (tự tạo nếu chưa có)
  .env               # GEMINI_API_KEY=...  (KHÔNG commit)
  .env.example
  .gitignore
  requirements.txt
  README.md
```

## requirements.txt
- `google-genai` (gọi model `gemini-2.5-flash`, fallback `gemini-2.5-flash-lite`)
- `python-dotenv` (đọc API key từ `.env`)
- `mcp` (MCP client SDK — kết nối server qua stdio)
- `mcp-server-time` (server thời gian chính thức, tiêu thụ qua `python -m mcp_server_time`)
