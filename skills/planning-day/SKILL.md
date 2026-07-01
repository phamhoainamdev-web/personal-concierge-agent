---
name: planning-day
description: Hướng dẫn lập kế hoạch và sắp xếp thứ tự công việc cho cả ngày qua tool plan_day. Dùng khi người dùng muốn lập kế hoạch, sắp xếp việc trong ngày, hỏi hôm nay làm gì trước, ưu tiên công việc thế nào. KHÔNG dùng khi người dùng chỉ muốn thêm một việc mới, xem danh sách, hoặc hoàn thành/xóa một việc lẻ.
---

# Skill: Lập kế hoạch ngày (planning-day)

Khi người dùng muốn lập kế hoạch / sắp xếp công việc trong ngày:

1. Gọi tool `plan_day()` để lấy danh sách việc CHƯA hoàn thành cùng ngày hôm nay.
2. Dựa trên kết quả, đề xuất một THỨ TỰ làm việc hợp lý trong ngày:
   - Ưu tiên việc có hạn (`due`) gần nhất hoặc đã tới hạn.
   - Việc quan trọng / mất nhiều thời gian nên làm sớm khi còn tỉnh táo.
   - Gom các việc nhỏ/nhanh lại với nhau.
3. Trình bày kế hoạch dạng danh sách đánh số, mỗi dòng kèm lý do ngắn gọn.
4. Nếu không có việc nào chưa làm, chúc mừng người dùng đã hoàn thành hết và gợi ý nghỉ ngơi.

Giữ giọng văn ngắn gọn, thực tế, bằng tiếng Việt.
