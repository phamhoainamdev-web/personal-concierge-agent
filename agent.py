"""
agent.py — Bộ não của Concierge: Gemini + Function calling + Agent Skills + MCP client

Tập trung 4 khái niệm:
 - KHÁI NIỆM 1: Vòng lặp Agent (Perceive -> Plan -> Act -> Observe) trong run_turn().
 - KHÁI NIỆM 2: Agent Skills — SKILL.md + frontmatter + progressive disclosure (Day 3).
 - KHÁI NIỆM 3: Tool use — dùng khai báo & hàm thật từ tools.py.
 - KHÁI NIỆM 4: MCP Client — tiêu thụ mcp-server-time (official) qua stdio; consume, don't build.
 - TRỤ CỘT BẢO MẬT: gọi policy_check() trước khi chạy tool, mask_pii() khi in.
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

# Model chính theo SPEC; nếu lỗi sẽ fallback sang model dự phòng.
_PRIMARY_MODEL = "gemini-2.5-flash"
_FALLBACK_MODEL = "gemini-2.5-flash-lite"

_SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")

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

# ===================== KHÁI NIỆM 4 — MCP CLIENT =====================
# consume, don't build: agent là CLIENT, tiêu thụ server chính thức mcp-server-time
# qua stdio (không cần API key). Server này cung cấp 2 tool: get_current_time, convert_time.
_MCP_SERVER_ARGS = ["-m", "mcp_server_time"]
_DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"

# Bản đồ kiểu JSON Schema (server MCP trả về) -> enum Type của google.genai.
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
    Chuyển JSON Schema (inputSchema từ MCP list_tools) sang types.Schema của Gemini.

    Chỉ xử lý tập con đủ dùng cho mcp-server-time (object/string/... , properties,
    required, items). Nhờ đó tool của MCP được GỘP CHUNG vào function declarations
    cho Gemini mà không cần khai báo tay.
    """
    if not isinstance(schema, dict):
        return types.Schema(type=types.Type.STRING)
    jtype = schema.get("type", "string")
    if isinstance(jtype, list):  # ví dụ ["string", "null"] -> lấy kiểu khác null
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
    """Gộp các phần TextContent trong kết quả call_tool của MCP thành một chuỗi."""
    parts = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


# ===================== KHÁI NIỆM 2 — AGENT SKILLS =====================
# Chuẩn Agent Skill (agentskills.io): mỗi skill là 1 THƯ MỤC chứa file SKILL.md,
# mở đầu bằng YAML frontmatter gồm `name` + `description`.
#
# PROGRESSIVE DISCLOSURE (tiết lộ dần):
#  - METADATA (name + description) rất rẻ nên LUÔN được nạp sẵn cho mọi skill.
#  - THÂN SKILL.md (hướng dẫn chi tiết) chỉ được nạp khi skill đó THỰC SỰ trúng
#    yêu cầu — chính `description` là căn cứ để quyết định trúng hay không, thay
#    cho việc gán cứng intent bằng từ khóa.

def _parse_frontmatter(path: str) -> tuple[dict, str]:
    """
    Tách file SKILL.md thành (metadata, body).

    metadata lấy từ khối YAML frontmatter giữa hai dấu '---' ở đầu file
    (ở đây chỉ cần các trường phẳng `name:` và `description:`); body là phần
    hướng dẫn còn lại.
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
    Quét skills/<tên-skill>/SKILL.md và trả về CATALOG metadata của mọi skill.

    Đây là bước 'luôn nạp sẵn' của progressive disclosure: chỉ đọc frontmatter
    (name + description), KHÔNG nạp thân skill. Kết quả: {name: {dir, description}}.
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
    Nạp THÂN hướng dẫn của một skill trong skills/<dir_name>/SKILL.md.

    Chỉ được gọi khi skill đã trúng yêu cầu (nạp theo nhu cầu / on-demand) — phần
    tốn context nhất chỉ vào context của đúng lượt cần đến nó.
    """
    path = os.path.join(_SKILLS_DIR, dir_name, "SKILL.md")
    try:
        _, body = _parse_frontmatter(path)
        return body
    except OSError:
        return ""


def _trigger_text(description: str) -> str:
    """
    Lấy phần 'khi nào DÙNG' của description, bỏ vế 'khi nào KHÔNG dùng'.

    Nhờ vậy khi chấm điểm khớp, các từ trong vế phủ định (ví dụ 'không dùng khi
    thêm việc') không vô tình kéo nhầm skill khác về.
    """
    low = description.lower()
    idx = low.find("không dùng")
    return low[:idx] if idx != -1 else low


def select_skill(user_input: str, catalog: dict[str, dict]) -> str | None:
    """
    Chọn skill cần nạp DỰA TRÊN description trong metadata (progressive disclosure).

    Chấm điểm mỗi skill theo số từ khóa (>=4 ký tự) trong phần 'khi nào dùng' của
    description mà xuất hiện trong câu người dùng. Skill điểm cao nhất (>0) thắng;
    không skill nào khớp thì trả None — thay cho việc gán cứng intent trước đây.
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
    """Đóng gói client Gemini, tool declarations và vòng lặp agent."""

    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        # KHÁI NIỆM 3: dựng function declarations cho Gemini từ tools.py.
        self.tool_decl = tools.build_tool_declarations(types)
        self.model = _PRIMARY_MODEL
        # KHÁI NIỆM 2: metadata (name+description) của mọi skill — luôn nạp sẵn.
        self.skills = discover_skills()

        # KHÁI NIỆM 4 — MCP client: các trạng thái phiên MCP (mở ở start_mcp()).
        self._mcp_stack = AsyncExitStack()
        self.mcp_session: ClientSession | None = None
        self.mcp_tool_names: set[str] = set()  # tên các tool phục vụ QUA MCP
        # Danh sách Tool mà Gemini nhìn thấy: mặc định chỉ 5 tool việc; sau khi MCP
        # kết nối sẽ GỘP THÊM Tool chứa get_current_time + convert_time.
        self.gemini_tools = [self.tool_decl]

    # ---------------- KHÁI NIỆM 4 — MCP CLIENT: vòng đời phiên ----------------
    async def start_mcp(self) -> None:
        """
        Mở phiên MCP tới mcp-server-time qua stdio và GIỮ MỞ suốt phiên chat.

        list_tools() -> chuyển get_current_time, convert_time thành function
        declarations cho Gemini và GỘP CHUNG với 5 tool việc.
        Nếu server không khởi động được: agent vẫn chạy phần việc, chỉ báo lỗi rõ.
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
                # GỘP TOOL: Gemini giờ thấy tổng 5 tool việc + các tool thời gian.
                self.gemini_tools = [self.tool_decl, types.Tool(function_declarations=time_decls)]
            self.mcp_session = session
            print(f"[MCP] Đã kết nối mcp-server-time. Tool thời gian: {', '.join(sorted(self.mcp_tool_names))}")
        except Exception as e:
            # KHÔNG treo/crash: đóng lại stack và chạy tiếp chỉ với tool việc.
            self.mcp_session = None
            self.mcp_tool_names = set()
            self.gemini_tools = [self.tool_decl]
            await self._mcp_stack.aclose()
            self._mcp_stack = AsyncExitStack()
            print(f"[MCP] Không kết nối được mcp-server-time ({e}). Agent vẫn chạy phần việc bình thường.")

    async def close(self) -> None:
        """Đóng phiên MCP sạch sẽ (gọi khi thoát chat / Ctrl+C)."""
        await self._mcp_stack.aclose()

    async def _call_mcp_tool(self, tool_name: str, args: dict) -> dict:
        """Gọi một tool thời gian QUA phiên MCP và trả kết quả về dạng dict cho Gemini."""
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
        """Gọi Gemini có fallback model + bọc try/except chống crash."""
        try:
            return self.client.models.generate_content(
                model=self.model, contents=contents, config=config
            )
        except Exception as e:
            # IN RA nguyên thông báo lỗi gốc trước khi thử fallback (đừng nuốt lỗi) để dễ debug.
            print(f"[Gemini lỗi với model '{self.model}'] {e}")
            # Thử model dự phòng đúng như SPEC nếu model chính lỗi.
            if self.model == _PRIMARY_MODEL:
                self.model = _FALLBACK_MODEL
                print(f"[Đang thử lại với model dự phòng '{self.model}'...]")
                return self.client.models.generate_content(
                    model=self.model, contents=contents, config=config
                )
            raise e

    # ============ KHÁI NIỆM 1 — VÒNG LẶP AGENT (Perceive→Plan→Act→Observe) ============
    async def run_turn(self, user_input: str) -> str:
        """Xử lý MỘT lượt chat của người dùng qua đủ 4 bước của vòng lặp agent."""

        # ---------- PERCEIVE: nhận câu người dùng nhập ----------
        # (user_input chính là tri giác đầu vào của agent ở lượt này.)

        # KHÁI NIỆM 2 (progressive disclosure): dùng description trong metadata để
        # chọn skill trúng yêu cầu, rồi mới nạp THÂN skill vào context lượt này.
        skill_name = select_skill(user_input, self.skills)
        system_instruction = _SYSTEM_INSTRUCTION
        if skill_name:
            skill_text = load_skill(self.skills[skill_name]["dir"])
            if skill_text:
                system_instruction += f"\n\n[SKILL ĐƯỢC NẠP: {skill_name}]\n{skill_text}"

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            # KHÁI NIỆM 3+4: GỘP tool việc + tool thời gian (MCP) cho Gemini thấy chung.
            tools=self.gemini_tools,
            # Tắt auto function-calling để TỰ tay chạy tool sau khi qua policy_check (BẢO MẬT).
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        contents = [types.Content(role="user", parts=[types.Part(text=user_input)])]

        # ---------- PLAN: gửi cho Gemini kèm tool để model chọn hành động ----------
        response = self._generate(contents, config)

        # Vòng lặp công cụ: model có thể yêu cầu gọi tool nhiều lần liên tiếp.
        for _ in range(5):  # giới hạn để tránh lặp vô hạn
            calls = getattr(response, "function_calls", None)
            if not calls:
                break  # Model đã có câu trả lời cuối, không cần gọi tool nữa.

            # Lưu lại lượt nói của model (chứa yêu cầu gọi tool) vào lịch sử hội thoại.
            contents.append(response.candidates[0].content)

            tool_response_parts = []
            for call in calls:
                tool_name = call.name
                args = dict(call.args or {})

                # ---------- ACT: BẢO MẬT trước, rồi mới thực thi tool ----------
                # TRỤ CỘT BẢO MẬT: policy_check() chạy TRƯỚC MỌI tool (kể cả tool MCP).
                allowed, reason = policy_check(tool_name, args)
                log_tool_call(tool_name, args, allowed)  # log đã mask_pii
                if not allowed:
                    # Tool ngoài allowlist -> trả thông báo Policy Violation cho model
                    # tự xử lý nhẹ nhàng, KHÔNG crash. (Chống MCP spoofing — Day 4.)
                    result = {"ok": False, "error": reason}
                elif tool_name in self.mcp_tool_names:
                    # KHÁI NIỆM 4: tool thời gian -> thực thi QUA phiên MCP (không chạy nội bộ).
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

            # ---------- OBSERVE: đưa kết quả tool về cho model để nó chốt câu trả lời ----------
            contents.append(types.Content(role="user", parts=tool_response_parts))
            response = self._generate(contents, config)

        final_text = response.text or "(Mình chưa rõ yêu cầu, bạn nói lại giúp nhé.)"

        # TRỤ CỘT BẢO MẬT: che PII trước khi trả về để in ra màn hình.
        return mask_pii(final_text)
