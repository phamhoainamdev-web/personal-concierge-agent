---
name: adding-tasks
description: Hướng dẫn thêm một hoặc nhiều việc cần làm vào danh sách qua tool add_task. Dùng khi người dùng muốn thêm việc, tạo việc, nhắc tôi, ghi chú một đầu việc mới (có thể kèm hạn chót). KHÔNG dùng khi người dùng chỉ muốn xem danh sách, hoàn thành/xóa việc, hoặc lập kế hoạch sắp xếp cả ngày.
---

# Skill: Thêm việc (adding-tasks)

Khi người dùng muốn thêm một việc cần làm:

- Gọi tool `add_task(title, due)`.
- `title` là nội dung việc, rút gọn cho rõ ràng (bỏ các từ thừa như "thêm việc", "nhắc tôi").
- `due` là hạn chót nếu người dùng có nhắc (ví dụ "hạn 6/7" -> due = "6/7"); nếu không có thì để trống.
- Sau khi thêm xong, xác nhận ngắn gọn với người dùng: đã thêm việc gì, hạn khi nào (nếu có).
- Nếu người dùng liệt kê nhiều việc trong một câu, hãy gọi `add_task` nhiều lần, mỗi việc một lần.
