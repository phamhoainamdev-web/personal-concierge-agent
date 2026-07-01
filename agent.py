"""
agent.py — The brain of Concierge: Gemini + Function calling + Agent Skills + MCP client

Focuses on 4 concepts:
 - CONCEPT 1: Agent loop (Perceive -> Plan -> Act -> Observe) in run_turn().
 - CONCEPT 2: Agent Skills — SKILL.md + frontmatter + progressive disclosure (Day 3).
 - CONCEPT 3: Tool use — uses the real declarations & functions from tools.py.
 - CONCEPT 4: MCP Client — consumes mcp-server-time (official) over stdio; consume, don't build.
 - SECURITY PILLAR: call policy_check() before running a tool, mask_pii() when printing.
"""

import json
import os
import re
import sys
from contextlib import AsyncExitStack

from google import genai
from google.genai import types

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import tools
from security import policy_check, mask_pii, log_tool_call

# Primary model per SPEC; on error we fall back to the backup model.
_PRIMARY_MODEL = "gemini-2.5-flash"
_FALLBACK_MODEL = "gemini-2.5-flash-lite"

_SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")

# NOTE: the system instruction below is intentionally kept in Vietnamese — it drives
# the agent's language and behaviour, and must not be translated.
_SYSTEM_INSTRUCTION = (
    "Bạn là 'Personal Concierge' — trợ lý cá nhân quản lý việc cần làm, trả lời bằng tiếng Việt, "
    "ngắn gọn, thân thiện. Khi người dùng muốn thêm/xem/hoàn thành/xóa việc hoặc lập kế hoạch ngày, "
    "hãy gọi đúng tool tương ứng. "
    "QUY TẮC NGÀY/GIỜ (BẮT BUỘC): Bất cứ khi nào cần biết ngày/giờ hiện tại — hỏi 'hôm nay là ngày mấy', "
    "tính hạn/deadline, 'còn mấy ngày', việc nào tới hạn/trễ, hay bất kỳ suy luận nào liên quan tới thời "
    "điểm hiện tại — bạn PHẢI tự gọi tool get_current_time với timezone 'Asia/Ho_Chi_Minh' để lấy ngày "
    "thật rồi mới tính, và dùng convert_time khi cần đổi múi giờ. TUYỆT ĐỐI KHÔNG được hỏi ngược người "
    "dùng hôm nay là ngày mấy / bây giờ là mấy giờ, và KHÔNG được tự bịa/giả định ngày giờ — luôn lấy từ "
    "get_current_time. "
    "Nếu một yêu cầu bị từ chối vì lý do chính sách, hãy giải thích nhẹ "
    "nhàng cho người dùng thay vì báo lỗi kỹ thuật."
)

# ===================== CONCEPT 4 — MCP CLIENT =====================
# consume, don't build: the agent is a CLIENT that consumes the official mcp-server-time
# over stdio (no API key needed). That server provides 2 tools: get_current_time, convert_time.
_MCP_SERVER_ARGS = ["-m", "mcp_server_time"]
_DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"

# Map JSON Schema types (returned by the MCP server) -> google.genai Type enum.
_JSON_TO_GEMINI_TYPE = {
    "string": "STRING",
    "integer": "INTEGER",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
    "object": "OBJECT",
    "array": "ARRAY",
}


def _json_schema_to_gemini(schema: dict) -> "types.Schema":
    """
    Convert a JSON Schema (the inputSchema from MCP list_tools) into a Gemini types.Schema.

    Only handles the subset needed for mcp-server-time (object/string/..., properties,
    required, items). This lets MCP tools be MERGED into Gemini's function declarations
    without hand-writing them.
    """
    if not isinstance(schema, dict):
        return types.Schema(type=types.Type.STRING)
    jtype = schema.get("type", "string")
    if isinstance(jtype, list):  # e.g. ["string", "null"] -> pick the non-null type
        jtype = next((t for t in jtype if t != "null"), "string")
    kwargs = {"type": getattr(types.Type, _JSON_TO_GEMINI_TYPE.get(jtype, "STRING"))}
    if schema.get("description"):
        kwargs["description"] = schema["description"]
    if jtype == "object":
        props = schema.get("properties", {}) or {}
        kwargs["properties"] = {k: _json_schema_to_gemini(v) for k, v in props.items()}
        if schema.get("required"):
            kwargs["required"] = list(schema["required"])
    elif jtype == "array" and schema.get("items"):
        kwargs["items"] = _json_schema_to_gemini(schema["items"])
    return types.Schema(**kwargs)


def _extract_mcp_text(result) -> str:
    """Join the TextContent parts of an MCP call_tool result into a single string."""
    parts = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


# ===================== CONCEPT 2 — AGENT SKILLS =====================
# Agent Skill standard (agentskills.io): each skill is a DIRECTORY containing a SKILL.md
# file that opens with a YAML frontmatter block of `name` + `description`.
#
# PROGRESSIVE DISCLOSURE:
#  - METADATA (name + description) is cheap, so it is ALWAYS preloaded for every skill.
#  - The SKILL.md BODY (detailed instructions) is loaded only when a skill ACTUALLY matches
#    the request — the `description` is the basis for deciding a match, instead of
#    hard-coding intent via keywords.

def _parse_frontmatter(path: str) -> tuple[dict, str]:
    """
    Split a SKILL.md file into (metadata, body).

    metadata comes from the YAML frontmatter block between the two '---' markers at the
    top of the file (only the flat `name:` and `description:` fields are needed here);
    body is the remaining instruction text.
    """
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    meta: dict[str, str] = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            raw, body = parts[1], parts[2].lstrip("\n")
            for line in raw.strip().splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    meta[key.strip()] = value.strip()
    return meta, body


def discover_skills() -> dict[str, dict]:
    """
    Scan skills/<skill-name>/SKILL.md and return the metadata CATALOG of every skill.

    This is the 'always preloaded' step of progressive disclosure: read only the
    frontmatter (name + description), do NOT load the skill body. Result: {name: {dir, description}}.
    """
    catalog: dict[str, dict] = {}
    if not os.path.isdir(_SKILLS_DIR):
        return catalog
    for entry in sorted(os.listdir(_SKILLS_DIR)):
        skill_path = os.path.join(_SKILLS_DIR, entry, "SKILL.md")
        if not os.path.isfile(skill_path):
            continue
        try:
            meta, _ = _parse_frontmatter(skill_path)
        except OSError:
            continue
        name = meta.get("name") or entry
        catalog[name] = {"dir": entry, "description": meta.get("description", "")}
    return catalog


def load_skill(dir_name: str) -> str:
    """
    Load the instruction BODY of a skill at skills/<dir_name>/SKILL.md.

    Only called once a skill has matched the request (on-demand loading) — the most
    context-heavy part enters the context only on the turn that actually needs it.
    """
    path = os.path.join(_SKILLS_DIR, dir_name, "SKILL.md")
    try:
        _, body = _parse_frontmatter(path)
        return body
    except OSError:
        return ""


def _trigger_text(description: str) -> str:
    """
    Take the 'when to USE' part of the description, dropping the 'when NOT to use' part.

    This way, when scoring matches, words in the negative clause (e.g. 'do not use when
    adding a task') don't accidentally pull in the wrong skill.
    """
    low = description.lower()
    idx = low.find("không dùng")
    return low[:idx] if idx != -1 else low


def select_skill(user_input: str, catalog: dict[str, dict]) -> str | None:
    """
    Choose which skill to load BASED ON the description in the metadata (progressive disclosure).

    Scores each skill by how many keywords (>=4 chars) from the 'when to use' part of its
    description appear in the user's sentence. The highest-scoring skill (>0) wins; if no
    skill matches, returns None — replacing the previous hard-coded intent mapping.
    """
    text = user_input.lower()
    best_name: str | None = None
    best_score = 0
    for name, info in catalog.items():
        keywords = {w for w in re.findall(r"\w+", _trigger_text(info["description"]), re.UNICODE)
                    if len(w) >= 4}
        score = sum(1 for w in keywords if w in text)
        if score > best_score:
            best_name, best_score = name, score
    return best_name


class ConciergeAgent:
    """Wraps the Gemini client, tool declarations and the agent loop."""

    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        # CONCEPT 3: build the Gemini function declarations from tools.py.
        self.tool_decl = tools.build_tool_declarations(types)
        self.model = _PRIMARY_MODEL
        # CONCEPT 2: metadata (name+description) of every skill — always preloaded.
        self.skills = discover_skills()

        # CONCEPT 4 — MCP client: MCP session state (opened in start_mcp()).
        self._mcp_stack = AsyncExitStack()
        self.mcp_session: ClientSession | None = None
        self.mcp_tool_names: set[str] = set()  # names of tools served VIA MCP
        # The list of Tools Gemini sees: by default only the 5 task tools; after MCP
        # connects we MERGE IN a Tool holding get_current_time + convert_time.
        self.gemini_tools = [self.tool_decl]

    # ---------------- CONCEPT 4 — MCP CLIENT: session lifecycle ----------------
    async def start_mcp(self) -> None:
        """
        Open an MCP session to mcp-server-time over stdio and KEEP IT OPEN for the whole chat.

        list_tools() -> turn get_current_time, convert_time into Gemini function
        declarations and MERGE them with the 5 task tools.
        If the server fails to start: the agent still runs the task part, just reports a clear error.
        """
        params = StdioServerParameters(command=sys.executable, args=_MCP_SERVER_ARGS)
        try:
            read, write = await self._mcp_stack.enter_async_context(stdio_client(params))
            session = await self._mcp_stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            listed = await session.list_tools()

            time_decls = []
            for tool in listed.tools:
                self.mcp_tool_names.add(tool.name)
                time_decls.append(
                    types.FunctionDeclaration(
                        name=tool.name,
                        description=tool.description or "",
                        parameters=_json_schema_to_gemini(tool.inputSchema),
                    )
                )
            if time_decls:
                # MERGE TOOLS: Gemini now sees the 5 task tools + the time tools.
                self.gemini_tools = [self.tool_decl, types.Tool(function_declarations=time_decls)]
            self.mcp_session = session
            print(f"[MCP] Đã kết nối mcp-server-time. Tool thời gian: {', '.join(sorted(self.mcp_tool_names))}")
        except Exception as e:
            # Do NOT hang/crash: close the stack and continue with only the task tools.
            self.mcp_session = None
            self.mcp_tool_names = set()
            self.gemini_tools = [self.tool_decl]
            await self._mcp_stack.aclose()
            self._mcp_stack = AsyncExitStack()
            print(f"[MCP] Không kết nối được mcp-server-time ({e}). Agent vẫn chạy phần việc bình thường.")

    async def close(self) -> None:
        """Close the MCP session cleanly (call on chat exit / Ctrl+C)."""
        await self._mcp_stack.aclose()

    async def _call_mcp_tool(self, tool_name: str, args: dict) -> dict:
        """Call a time tool VIA the MCP session and return the result as a dict for Gemini."""
        if not self.mcp_session:
            return {"ok": False, "error": "MCP time server không khả dụng."}
        try:
            result = await self.mcp_session.call_tool(tool_name, args)
            text = _extract_mcp_text(result)
            if getattr(result, "isError", False):
                return {"ok": False, "error": text or "MCP tool báo lỗi."}
            return {"ok": True, "result": text}
        except Exception as e:
            return {"ok": False, "error": f"Lỗi khi gọi MCP tool '{tool_name}': {e}"}

    def _generate(self, contents, config):
        """Call Gemini with model fallback + a try/except wrapper to avoid crashing."""
        try:
            return self.client.models.generate_content(
                model=self.model, contents=contents, config=config
            )
        except Exception as e:
            # PRINT the original error before trying the fallback (don't swallow it) for easier debugging.
            print(f"[Gemini lỗi với model '{self.model}'] {e}")
            # Try the backup model exactly as in the SPEC if the primary model fails.
            if self.model == _PRIMARY_MODEL:
                self.model = _FALLBACK_MODEL
                print(f"[Đang thử lại với model dự phòng '{self.model}'...]")
                return self.client.models.generate_content(
                    model=self.model, contents=contents, config=config
                )
            raise e

    # ============ CONCEPT 1 — AGENT LOOP (Perceive→Plan→Act→Observe) ============
    async def run_turn(self, user_input: str) -> str:
        """Handle ONE chat turn from the user through all 4 steps of the agent loop."""

        # ---------- PERCEIVE: receive the user's typed input ----------
        # (user_input is the agent's perceptual input for this turn.)

        # CONCEPT 2 (progressive disclosure): use the description in the metadata to
        # pick the matching skill, then load only its BODY into this turn's context.
        skill_name = select_skill(user_input, self.skills)
        system_instruction = _SYSTEM_INSTRUCTION
        if skill_name:
            skill_text = load_skill(self.skills[skill_name]["dir"])
            if skill_text:
                system_instruction += f"\n\n[SKILL ĐƯỢC NẠP: {skill_name}]\n{skill_text}"

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            # CONCEPT 3+4: MERGE task tools + time tools (MCP) so Gemini sees them together.
            tools=self.gemini_tools,
            # Disable auto function-calling so we run tools MANUALLY after policy_check (SECURITY).
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        contents = [types.Content(role="user", parts=[types.Part(text=user_input)])]

        # ---------- PLAN: send to Gemini with the tools so the model picks an action ----------
        response = self._generate(contents, config)

        # Tool loop: the model may request tool calls several times in a row.
        for _ in range(5):  # limit to avoid an infinite loop
            calls = getattr(response, "function_calls", None)
            if not calls:
                break  # The model has its final answer, no more tool calls needed.

            # Record the model's turn (containing the tool-call request) into the conversation history.
            contents.append(response.candidates[0].content)

            tool_response_parts = []
            for call in calls:
                tool_name = call.name
                args = dict(call.args or {})

                # ---------- ACT: SECURITY first, only then execute the tool ----------
                # SECURITY PILLAR: policy_check() runs BEFORE EVERY tool (including MCP tools).
                allowed, reason = policy_check(tool_name, args)
                log_tool_call(tool_name, args, allowed)  # log is already mask_pii'd
                if not allowed:
                    # Tool outside the allowlist -> return a Policy Violation message for the model
                    # to handle gently, do NOT crash. (Anti MCP-spoofing — Day 4.)
                    result = {"ok": False, "error": reason}
                elif tool_name in self.mcp_tool_names:
                    # CONCEPT 4: time tool -> execute VIA the MCP session (not run locally).
                    result = await self._call_mcp_tool(tool_name, args)
                else:
                    fn = tools.TOOL_FUNCTIONS.get(tool_name)
                    try:
                        result = fn(**args) if fn else {"ok": False, "error": "Tool không tồn tại."}
                    except Exception as e:
                        result = {"ok": False, "error": f"Lỗi khi chạy tool: {e}"}

                tool_response_parts.append(
                    types.Part.from_function_response(name=tool_name, response={"result": result})
                )

            # ---------- OBSERVE: feed the tool results back to the model so it finalizes the answer ----------
            contents.append(types.Content(role="user", parts=tool_response_parts))
            response = self._generate(contents, config)

        final_text = response.text or "(Mình chưa rõ yêu cầu, bạn nói lại giúp nhé.)"

        # SECURITY PILLAR: mask PII before returning it for printing to the screen.
        return mask_pii(final_text)
