# SPEC_V2.md — Bản nâng cấp gộp (thay cho SPEC_MCP.md)

> Đọc CÙNG SPEC.md (giữ nguyên mọi thứ trong đó). File này gộp 2 nâng cấp:
>   A) Refactor Agent Skills về đúng chuẩn agentskills.io (Day 3)
>   B) Agent làm MCP CLIENT, TIÊU THỤ một MCP server có sẵn, chính thức (Day 2)
> QUAN TRỌNG: KHÔNG tự xây MCP server. Xoá file SPEC_MCP.md cũ nếu còn, chỉ dùng file này.
> Giữ nguyên: 4 lệnh việc, mask_pii, policy_check, model gemini-2.5-flash (fallback gemini-2.5-flash-lite).
> Chạy trên Windows + Python 3.14, trong terminal.

======================================================================
## PHẦN A — Refactor Agent Skills về đúng chuẩn (Day 3)
======================================================================

Hiện tại skills/ là file .md phẳng (add_task.md, plan_day.md) nạp bằng gán cứng theo intent.
Sửa về đúng chuẩn "Skill" của agentskills.io:

A1. Cấu trúc thư mục mới (mỗi skill = 1 thư mục con chứa SKILL.md):
```
skills/
  adding-tasks/
    SKILL.md
  planning-day/
    SKILL.md
```
- Tên skill: kebab-case, dạng gerund (adding-tasks, planning-day).

A2. Mỗi SKILL.md bắt đầu bằng YAML frontmatter (đây là "thuật toán định tuyến"):
```markdown
---
name: planning-day
description: |
  Lập kế hoạch và sắp xếp thứ tự việc trong ngày cho người dùng.
  Dùng khi người dùng muốn: lên kế hoạch hôm nay, xem việc ưu tiên, việc nào tới hạn.
  KHÔNG dùng để thêm việc mới hay xoá việc.
---
(thân: hướng dẫn chi tiết cách agent lập kế hoạch...)
```
- description phải nêu: LÀM GÌ + KHI NÀO dùng + KHI NÀO KHÔNG dùng.

A3. Sửa hàm nạp skill trong agent.py theo progressive disclosure:
- Luôn có sẵn trong context: metadata (name + description) của mọi skill.
- Đọc description để QUYẾT ĐỊNH nạp skill nào cho lượt hiện tại (thay cho gán cứng theo intent).
- Chỉ nạp THÂN SKILL.md khi skill đó trúng.
- Comment: `# KHÁI NIỆM: Agent Skills — SKILL.md + frontmatter + progressive disclosure (Day 3)`.

======================================================================
## PHẦN B — MCP Client tiêu thụ server CÓ SẴN (Day 2)
======================================================================

Theo tài liệu Day 2 "consumption over creation": KHÔNG tự xây server. Agent kết nối tới
server chính thức **mcp-server-time** (không cần API key → hợp track Concierge).

B1. Thư viện: thêm vào requirements.txt: `mcp`, `mcp-server-time`.
   (Đã verify: mcp 1.28.1, mcp-server-time 2026.6.4, chạy được.)

B2. API MCP (đã verify, dùng đúng như sau):
```python
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server_time"])
# async with stdio_client(params) as (r, w):
#   async with ClientSession(r, w) as session:
#       await session.initialize()
#       tools = await session.list_tools()          # -> get_current_time, convert_time
#       res = await session.call_tool("get_current_time", {"timezone": "Asia/Ho_Chi_Minh"})
```

B3. Sửa agent.py thành MCP client (KHÔNG bỏ 5 tool việc):
- Giữ 5 tool việc (add/list/complete/delete/plan) dạng function calling — đây là phần "Agent system".
- Khi khởi động: mở thêm phiên MCP tới mcp-server-time, GIỮ MỞ suốt phiên chat.
- list_tools() từ time server -> chuyển get_current_time, convert_time thành function
  declarations cho Gemini, GỘP CHUNG với 5 tool việc (Gemini thấy tổng 7 tool).
- Khi Gemini gọi tool:
  - Tool việc -> chạy như cũ (sau policy_check).
  - Tool thời gian -> (1) policy_check trước; (2) await session.call_tool(...) gọi QUA MCP;
    (3) đưa kết quả về Gemini để chốt câu trả lời.
- Comment: `# KHÁI NIỆM: MCP Client — tiêu thụ mcp-server-time (official) qua stdio; consume, don't build`.

B4. Sửa security.py:
- Mở rộng allowlist của policy_check cho phép thêm: get_current_time, convert_time (5 tool việc vẫn giữ).
- Tool ngoài allowlist vẫn bị chặn, không crash. (Chống MCP spoofing — Day 4.)
- (Tùy chọn cộng điểm) ghi log mỗi lần gọi tool (tên + thời điểm), PII trong log phải mask_pii.

B5. Dùng time server cho có ý nghĩa (không làm cảnh):
- Trong planning-day và khi hỏi hạn/deadline, agent gọi get_current_time
  (timezone mặc định "Asia/Ho_Chi_Minh") để biết hôm nay, rồi tính việc nào tới hạn/trễ.

======================================================================
## PHẦN C — Async, giữ nguyên, acceptance criteria
======================================================================

C1. Async: MCP client dùng asyncio -> vòng lặp chat chạy trong asyncio.run(main_async()).
   Tool việc là hàm sync, gọi trực tiếp. Gọi Gemini dùng client.aio... (hoặc sync cũng được).
   'thoát'/'exit'/Ctrl+C -> đóng phiên MCP sạch, không treo.

C2. GIỮ NGUYÊN: tools.py + tasks.json; mask_pii bọc mọi câu in cho người dùng; hành vi 4 lệnh việc.

C3. Acceptance criteria (chạy đúng hết):
- python main.py mở vòng chat; 4 lệnh việc chạy đúng; PII bị che; tool lạ bị chặn.
- Skill trúng đúng: "lập kế hoạch hôm nay" -> nạp planning-day; "thêm việc..." -> nạp adding-tasks.
- "hôm nay là ngày mấy?" -> đúng ngày thật (qua MCP).
- "còn mấy ngày tới hạn nộp capstone?" -> tính đúng theo ngày thật.
- time server không khởi động được -> agent vẫn chạy phần việc, báo lỗi rõ, không treo.

C4. Cập nhật README.md:
- Sơ đồ: User -> agent (task tools + MCP client + skills) ⇄ [stdio] ⇄ mcp-server-time (official);
  security (policy_check + mask_pii) bọc ngoài.
- Bảng khái niệm: Agent system ✓, Agent Skills ✓ (chuẩn SKILL.md), MCP ✓ (consume server có sẵn),
  Security ✓. Ghi 1 dòng chỉ file/đoạn code cho mỗi khái niệm.

C5. Sau khi build: in danh sách file đã tạo/sửa + chỉ rõ dòng khởi động MCP client, dòng gộp tool,
   và hàm nạp skill theo description.
