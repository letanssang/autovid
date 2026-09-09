# Phase 4 — Hình đúng nội dung

> **Mục tiêu:** hình trên màn hình liên quan tới câu đang được đọc.
> **Kết quả kiểm chứng được:** tua ngẫu nhiên 10 điểm trong video, ít nhất 8 điểm có hình
> khớp nội dung đang nói.
> **Phụ thuộc:** Phase 3 (cần video chạy được để so sánh trước/sau)
> **Ước lượng:** 2–3 buổi

## Vấn đề đang có

Video sau Phase 3 xem được nhưng vô nghĩa về mặt hình ảnh:

- `s04_visual_plan.py:11-13` chọn loại visual bằng **round-robin** — xoay vòng
  `title → diagram → code → comparison → ai_image → b_roll` bất kể beat nói gì.
  Video về lịch sử La Mã sẽ có slide `code`.
- `s05_assets.py:62` truyền `content={"title": beat["text"]}` cho **mọi** template.
  `code.html` cần biến `code`, `diagram.html` cần `svg` + `caption`, `comparison.html` cần
  `left_title`/`left_items`/`right_title`/`right_items` → ba template này render ra slide
  gần như trống.

Prompt phân loại đã viết sẵn ở `prompts/en/educational/visual.md` từ đầu nhưng chưa được gọi.

## Việc cần làm

### 4.1 — Visual classifier bằng LLM (gap #6)

**File:** `core/stages/s04_visual_plan.py`

Thay round-robin bằng gọi text provider với `prompts/en/educational/visual.md` (đã có sẵn,
nhận `shot_text`, `previous_visual_type`, `remaining_ai_images`).

Ba ràng buộc **giữ nguyên từ heuristic hiện tại** — chúng đúng, đừng vứt đi:
- không hai beat liên tiếp cùng loại
- `ai_image` hết ngân sách → hạ xuống `b_roll`, đếm vào `downgraded_to_b_roll`
- kết quả phải xác định được, ghi đủ vào `visual_plan.json`

Ba thứ cần thêm vì giờ có LLM trong vòng lặp:
- **Validate output:** model trả về từ ngoài danh sách 6 loại → fallback về `title`, ghi log.
  Đừng tin output LLM là hợp lệ.
- **Gộp request:** 200 beat = 200 lần gọi API. Gộp ~20 beat vào một request, yêu cầu trả về
  danh sách. Giảm cost và thời gian một bậc.
- **Đừng phá gate:** `04_visual_plan` là gate có người duyệt. `visual_plan.md` (làm ở bước 1.4)
  phải in rõ **vì sao** mỗi beat chọn loại đó, để người duyệt sửa được.

### 4.2 — Sinh nội dung đúng schema cho từng template (gap #4)

**File:** `core/stages/s04_visual_plan.py` (sinh), `core/stages/s05_assets.py` (dùng)

Quyết định thiết kế: **`s04` sinh nội dung slide, `s05` chỉ render.** Lý do — `s04` là stage
có gate; người duyệt phải thấy được nội dung slide *trước khi* tốn tiền render và TTS.
Nếu để `s05` sinh thì nội dung slide lọt qua gate mà không ai duyệt.

Nghĩa là `visual_plan.json` mỗi beat mang thêm `slide_content` khớp schema template:

```json
{ "beat_id": "how-it-works-1-3", "visual_type": "comparison",
  "slide_content": { "title": "...", "left_title": "...", "left_items": ["..."],
                     "right_title": "...", "right_items": ["..."] } }
```

**Cần thêm prompt mới:** `prompts/en/educational/slide_content.md` — nhận loại visual +
lời thoại beat, trả JSON đúng schema của template đó. Đây là prompt đầu tiên trong dự án
đòi output JSON, nên cần:
- schema rõ ràng trong prompt
- hàm parse chịu được rác (fence ```json, lời dẫn) — dùng chung hàm dọn output từ bước 1.2
- parse fail → fallback về template `title` với lời thoại, ghi log, **không crash**

### 4.3 — `b_roll` tử tế

Phase 3 tạm dùng slide `title` cho `b_roll`. Giờ nâng lên. Ba hướng, chọn một:

| Hướng | Cost | Công | Ghi chú |
|---|---|---|---|
| Slide "quote" — trích một câu đắt từ lời thoại, typography lớn | $0 | thấp | **Khuyến nghị cho phase này.** Cần thêm `templates/slides/quote.html` |
| Kho ảnh nền trừu tượng có sẵn, xoay vòng theo chương | $0 | trung bình | Cần chuẩn bị ảnh, và phải để ý bản quyền |
| Ảnh AI | ~$0.017/ảnh | thấp | Ăn vào `max_ai_images`, nhưng b_roll thường là loại nhiều beat nhất |

### 4.4 — Image provider thật

**File:** `core/providers/image/nano_banana.py`

- `generate(req) -> ImageResult` với `ImageRequest` đã có sẵn ngữ nghĩa tốt:
  `intent` (`metaphor`/`hero`/`chapter_cover`/`transition`), `subject`, `maps_to`, `style_anchor`.
- **Bật batch:** `project.yaml` đã có `options.batch: true`; `estimate_cost` hiện đã tính
  $0.0168 (batch) vs $0.0336 (đơn lẻ) — gom hết ảnh của một lần chạy vào một batch request,
  tiết kiệm đúng một nửa.
- **`style_anchor` phải thật sự neo phong cách.** Hiện `s05_assets.py:56` truyền
  `style_anchor=config.get("topic")` — đó là chủ đề, không phải phong cách. Cần một mô tả
  phong cách cố định cho cả video (ví dụ "flat vector illustration, muted palette,
  dark background") để 15 ảnh trông cùng một bộ. Thêm vào `project.yaml` dưới
  `providers.image.options.style_anchor`.
- Tôn trọng `budget.max_ai_images` (mặc định 15) — hàng rào này đã có ở `s04`, đừng đi vòng.

## Định nghĩa hoàn thành

- [ ] Tua ngẫu nhiên 10 điểm, ≥8 điểm hình khớp nội dung
- [ ] Không còn slide trống — `code`/`diagram`/`comparison` đều có nội dung thật
- [ ] Video về chủ đề phi kỹ thuật (ví dụ "the history of coffee") **không** xuất hiện slide `code`
- [ ] 15 ảnh AI trong một video trông cùng một phong cách
- [ ] `visual_plan.md` đọc được ở gate, sửa tay được rồi chạy lại `--from 05_assets` là ăn theo
- [ ] Cost ảnh trong ledger ≈ `số ảnh × $0.0168`, không phải giá đơn lẻ

## Rủi ro

- **`diagram` là loại khó nhất.** `diagram.html` cần biến `svg` — tức là bắt LLM sinh SVG hợp lệ.
  Tỉ lệ hỏng cao. Nếu tốn quá nửa buổi: bỏ `diagram` khỏi danh sách loại visual ở phase này,
  ghi lại thành việc riêng. Năm loại còn lại đủ làm video tốt.
- **Chi phí phase này là phần lớn ngân sách $1.** 15 ảnh × $0.0168 = $0.25, cộng classifier
  và slide content. Chạy thử với `max_ai_images: 3` trước khi chạy full.
