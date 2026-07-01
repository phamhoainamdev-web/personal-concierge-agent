"""
main.py — Vòng lặp chat trong terminal (Day 1 + MCP client Day 2)

Đây là điểm khởi chạy: nạp API key từ .env (BẢO MẬT — không hardcode), khởi tạo
agent, MỞ phiên MCP tới mcp-server-time rồi chạy vòng lặp chat. Vì MCP client dùng
asyncio nên toàn bộ vòng chat chạy trong asyncio.run(main_async()). Mỗi lượt người
dùng nhập sẽ được agent xử lý qua vòng lặp Perceive -> Plan -> Act -> Observe.
'thoát'/'exit'/Ctrl+C -> đóng phiên MCP sạch, không treo.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

from agent import ConciergeAgent
from security import mask_pii


async def main_async() -> None:
    # Đảm bảo in/đọc tiếng Việt được trên terminal Windows (tránh lỗi codepage cp1252).
    for stream in (sys.stdout, sys.stdin, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    # BẢO MẬT — Secrets: chỉ đọc API key từ .env qua python-dotenv, KHÔNG hardcode.
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

    # KHÁI NIỆM 4 — MCP client: mở phiên tới mcp-server-time, giữ mở suốt phiên chat.
    await agent.start_mcp()

    print("=" * 60)
    print("  PERSONAL CONCIERGE — trợ lý việc cần làm (chạy cục bộ)")
    print("  Gõ yêu cầu của bạn. Gõ 'thoát' hoặc 'exit' để dừng.")
    print("=" * 60)

    try:
        while True:
            try:
                # PERCEIVE: nhận câu người dùng (chạy input() trong thread để không chặn event loop).
                user_input = (await asyncio.to_thread(input, "\nBạn> ")).strip()
            except (EOFError, KeyboardInterrupt):
                print("\nTạm biệt!")
                break

            if not user_input:
                continue
            if user_input.lower() in ("thoát", "thoat", "exit", "quit"):
                print("Tạm biệt!")
                break

            # Giao cho agent xử lý cả lượt (Plan -> Act -> Observe nằm trong run_turn).
            try:
                reply = await agent.run_turn(user_input)
            except Exception as e:
                # BẢO MẬT — che PII cả trong thông báo lỗi phòng khi chứa dữ liệu người dùng.
                reply = mask_pii(f"[Lỗi khi gọi Gemini] {e}")

            print(f"\nConcierge> {reply}")
    finally:
        # Đóng phiên MCP sạch dù thoát bình thường hay do lỗi/Ctrl+C.
        await agent.close()


def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\nTạm biệt!")


if __name__ == "__main__":
    main()
