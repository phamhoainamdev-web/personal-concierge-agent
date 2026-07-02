# AGENTS.md — Personal Concierge

## Stack
- Python (runs on Windows + Python 3.14), terminal app.
- Model: Google Gemini (google-genai), primary model gemini-2.5-flash, fallback gemini-2.5-flash-lite.
- MCP: consumes the official mcp-server-time (client over stdio).
- Storage: local JSON (data/tasks.json). No external DB, no network calls outside Gemini + MCP time.

## Architecture
- Agent loop: perceive -> plan -> act -> observe (agent.py).
- Task tools: add/list/complete/delete/plan (tools.py) -> read/write tasks.json.
- Agent Skills: skills/<name>/SKILL.md, loaded based on description (progressive disclosure).
- MCP client: connects to mcp-server-time to get the real date/time.
- Security: security.py (policy_check allow-list + mask_pii + audit log).

## Hard rules
- DO NOT hardcode the API key. The key is read only from .env; .env must be in .gitignore.
- Every message printed to the user MUST go through mask_pii (masks email/phone).
- Every tool call (including MCP tools) MUST go through policy_check first; tools outside the allow-list are rejected, not crashed.
- When the current date/time is needed: MUST call get_current_time (Asia/Ho_Chi_Minh); never fabricate/assume the date.
- The agent replies to the user in Vietnamese. Do not translate system_instruction and the description in SKILL.md.
- Do not add libraries outside requirements.txt unless truly necessary.

## Workflow
- Spec-driven: design in SPEC_V2.md; when changing behavior, update the spec/skill first, then let the agent implement it.
- After every change: run py_compile on the .py files + manually test a few real prompts (add a task, list tasks, plan the day).
- Review every line the agent generates before committing.
