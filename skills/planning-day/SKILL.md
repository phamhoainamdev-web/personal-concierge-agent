---
name: planning-day
description: Hướng dẫn lập kế hoạch và sắp xếp thứ tự công việc cho cả ngày qua tool plan_day. Dùng khi người dùng muốn lập kế hoạch, sắp xếp việc trong ngày, hỏi hôm nay làm gì trước, ưu tiên công việc thế nào. KHÔNG dùng khi người dùng chỉ muốn thêm một việc mới, xem danh sách, hoặc hoàn thành/xóa một việc lẻ.
---

# Skill: Lập kế hoạch ngày (planning-day)

Khi người dùng muốn lập kế hoạch / sắp xếp công việc trong ngày:

1. **BẮT BUỘC ĐẦU TIÊN — lấy ngày hiện tại thật:** luôn gọi tool `get_current_time`
   với `timezone = "Asia/Ho_Chi_Minh"` TRƯỚC KHI đánh giá bất kỳ deadline nào, để biết
   chính xác hôm nay là ngày mấy. TUYỆT ĐỐI KHÔNG được suy đoán, giả định hay bịa ngày
   hôm nay; mọi kết luận về "tới hạn / còn mấy ngày / đã trễ" phải dựa trên ngày thật này.
2. Gọi tool `plan_day()` để lấy danh sách việc CHƯA hoàn thành.
3. So sánh trường `due` của từng việc với NGÀY HÔM NAY (lấy ở bước 1) để xác định
   việc nào đã trễ, việc nào tới hạn hôm nay, việc nào còn hạn — và còn bao nhiêu ngày.
   Không hiển thị/khẳng định một ngày hạn nào mà bạn chưa đối chiếu với ngày thật ở bước 1.
4. Dựa trên kết quả, đề xuất một THỨ TỰ làm việc hợp lý trong ngày:
   - Ưu tiên việc đã trễ hoặc có hạn (`due`) gần nhất so với hôm nay.
   - Việc quan trọng / mất nhiều thời gian nên làm sớm khi còn tỉnh táo.
   - Gom các việc nhỏ/nhanh lại với nhau.
5. Trình bày kế hoạch dạng danh sách đánh số, mỗi dòng kèm lý do ngắn gọn
   (nêu rõ còn mấy ngày tới hạn hoặc đã trễ mấy ngày, tính theo ngày thật).
6. Nếu không có việc nào chưa làm, chúc mừng người dùng đã hoàn thành hết và gợi ý nghỉ ngơi.

Giữ giọng văn ngắn gọn, thực tế, bằng tiếng Việt.

## Quy trình lập kế hoạch trong ngày
1. LUÔN gọi get_current_time (Asia/Ho_Chi_Minh) trước để biết hôm nay là ngày nào.
2. Đọc danh sách việc, phân loại theo thứ tự ưu tiên:
   a. Việc ĐÃ QUÁ HẠN (due < hôm nay) — làm trước, cảnh báo rõ.
   b. Việc TỚI HẠN HÔM NAY.
   c. Việc có hạn gần (trong 3 ngày tới), sắp theo hạn tăng dần.
   d. Việc KHÔNG có hạn — xếp cuối, gợi ý xen kẽ khi rảnh.
3. Với mỗi việc, ghi rõ "còn mấy ngày tới hạn" tính từ ngày thật.
4. Không bịa ngày. Nếu thiếu thông tin hạn, nói rõ là chưa có hạn.
5. Kết thúc bằng 1 câu gợi ý nên bắt đầu từ việc nào.
