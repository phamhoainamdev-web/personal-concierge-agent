"""
main.py — Terminal chat loop (Day 1 + MCP client Day 2)

This is the entry point: it loads the API key from .env (SECURITY — no hardcoding),
initializes the agent, OPENS an MCP session to mcp-server-time, then runs the chat loop.
Because the MCP client uses asyncio, the whole chat loop runs inside asyncio.run(main_async()).
Each user input is handled by the agent through the Perceive -> Plan -> Act -> Observe loop.
'thoát'/'exit'/Ctrl+C -> close the MCP session cleanly, no hang.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

from agent import ConciergeAgent
from security import mask_pii


async def main_async() -> None:
    # Ensure Vietnamese can be printed/read on a Windows terminal (avoid cp1252 codepage errors).
    for stream in (sys.stdout, sys.stdin, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    # SECURITY — Secrets: read the API key only from .env via python-dotenv, never hardcode.
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key.strip() in ("", "your_key_here"):
        print("[Lỗi] Thiếu GEMINI_API_KEY. Hãy tạo file .env với dòng:")
        print("      GEMINI_API_KEY=khoa_api_cua_ban")
        sys.exit(1)

    try:
        agent = ConciergeAgent(api_key)
    except Exception as e:
        print(f"[Lỗi] Không khởi tạo được agent: {e}")
        sys.exit(1)

    # CONCEPT 4 — MCP client: open a session to mcp-server-time, keep it open for the whole chat.
    await agent.start_mcp()

    print("=" * 60)
    print("  PERSONAL CONCIERGE — trợ lý việc cần làm (chạy cục bộ)")
    print("  Gõ yêu cầu của bạn. Gõ 'thoát' hoặc 'exit' để dừng.")
    print("=" * 60)

    try:
        while True:
            try:
                # PERCEIVE: read the user's input (run input() in a thread so it doesn't block the event loop).
                user_input = (await asyncio.to_thread(input, "\nBạn> ")).strip()
            except (EOFError, KeyboardInterrupt):
                print("\nTạm biệt!")
                break

            if not user_input:
                continue
            if user_input.lower() in ("thoát", "thoat", "exit", "quit"):
                print("Tạm biệt!")
                break

            # Hand the whole turn to the agent (Plan -> Act -> Observe live inside run_turn).
            try:
                reply = await agent.run_turn(user_input)
            except Exception as e:
                # SECURITY — mask PII even in the error message in case it contains user data.
                reply = mask_pii(f"[Lỗi khi gọi Gemini] {e}")

            print(f"\nConcierge> {reply}")
    finally:
        # Close the MCP session cleanly whether we exit normally or via error/Ctrl+C.
        await agent.close()


def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\nTạm biệt!")


if __name__ == "__main__":
    main()
