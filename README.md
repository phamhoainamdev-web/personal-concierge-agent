# Personal Concierge Agent

A personal assistant ("Personal Concierge") that runs in the **terminal** and helps you
**manage your to-dos**: add tasks, list them, mark them done, delete them, and plan your day.
Data is stored **locally** in `data/tasks.json` — nothing is sent anywhere (Gemini is only
called to understand your request).
The agent is also an **MCP client**, consuming the official **mcp-server-time** server to know
the real date/time.

> Note: the agent chats in **Vietnamese** (that is its intended UX and what skill routing relies
> on). The example commands below are shown in Vietnamese because they are the literal inputs you
> type to the agent.

## Diagram

```
                      security: policy_check() + mask_pii() wrap EVERY call
        ┌─────────────────────────────────────────────────────────────────┐
        │                                                                   │
User ⇄ agent.py  ── task tools (add/list/complete/delete/plan) ─► data/tasks.json
        │  (Gemini + skills + MCP client)                                   │
        │                                                                   │
        └── MCP client ⇄ [stdio] ⇄ mcp-server-time (official) : get_current_time / convert_time
```
Gemini sees **7 tools** (5 task tools + 2 time tools merged together). `policy_check()` gates
every tool (including MCP tools), and `mask_pii()` masks PII before printing.

## How to run

Requirements: Python (tested on Windows + Python 3.14). The MCP time server runs out of the box
via `python -m mcp_server_time` — no API key needed.

```bash
# 1) Create & activate a virtual environment
python -m venv .venv
.venv\Scripts\activate         # Windows (PowerShell/CMD)

# 2) Install dependencies
pip install -r requirements.txt

# 3) Create the .env file and fill in the API key (do NOT hardcode it in the code)
copy .env.example .env         # Windows
#   then open .env and set: GEMINI_API_KEY=your_real_api_key

# 4) Run
python main.py
```

In the chat loop, type `thoát` or `exit` to quit.

### Quick try (type these Vietnamese inputs to the agent)
- `thêm việc nộp capstone hạn 6/7` → creates a task, saved to `data/tasks.json` (loads the `adding-tasks` skill)
- `xem việc của tôi` → lists tasks
- `lập kế hoạch hôm nay cho tôi` → loads the `planning-day` skill and suggests an order
- `hôm nay là ngày mấy?` → calls `get_current_time` **via MCP** → the real date
- `còn mấy ngày tới hạn nộp capstone?` → uses the real date (MCP) to compute
- `đánh dấu việc 1 xong` → updates the status
- Enter an email/phone number → it gets masked when printed back (e.g. `a***@gmail.com`, `09******89`)

## Course concepts demonstrated

| Concept | Where it shows up |
|---|---|
| **1. Agent system** (Perceive → Plan → Act → Observe) | `agent.py` → `ConciergeAgent.run_turn()`: comments clearly mark the 4 steps; `main.py` reads input (Perceive). |
| **2. Agent Skills** ✓ (SKILL.md standard) | `agent.py` → `discover_skills()` (metadata always available) + `select_skill()` (loads based on `description`, progressive disclosure) + `load_skill()` (loads the body on match); skills live in `skills/adding-tasks/SKILL.md`, `skills/planning-day/SKILL.md`. |
| **3. Tool use / Function calling** | `tools.py`: 5 real functions (`add_task`, `list_tasks`, `complete_task`, `delete_task`, `plan_day`) + `build_tool_declarations()` that declares them to Gemini. |
| **4. MCP** ✓ (consume an existing server) | `agent.py` → `start_mcp()` opens a stdio session to **mcp-server-time** and merges `get_current_time`/`convert_time` into the tools for Gemini; `_call_mcp_tool()` invokes them via MCP. No server is built. |
| **PILLAR — Security & privacy** ✓ | `security.py`: `policy_check()` (allowlist including the MCP tools, anti-spoofing) runs **before** every tool in the ACT step; `log_tool_call()` + `mask_pii()` mask email/phone before printing/logging. Secrets are read from `.env` via dotenv; `.gitignore` excludes `.env` and `data/`. |

## Directory structure

```
concierge/
  main.py            # async chat loop; opens/closes the MCP session
  agent.py           # Gemini + function calling + skills (SKILL.md) + MCP client
  tools.py           # task tools operating on data/tasks.json
  security.py        # security pillar (policy_check, mask_pii, log_tool_call)
  skills/
    adding-tasks/
      SKILL.md       # frontmatter name+description + instructions for adding tasks
    planning-day/
      SKILL.md       # frontmatter name+description + instructions for planning the day
  data/
    tasks.json       # local storage (auto-created if missing)
  .env               # GEMINI_API_KEY=...  (do NOT commit)
  .env.example
  .gitignore
  requirements.txt
  README.md
```

## requirements.txt
- `google-genai` (calls model `gemini-2.5-flash`, fallback `gemini-2.5-flash-lite`)
- `python-dotenv` (reads the API key from `.env`)
- `mcp` (MCP client SDK — connects to servers over stdio)
- `mcp-server-time` (the official time server, consumed via `python -m mcp_server_time`)
