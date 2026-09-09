# Phase 8 — Video clip AI (Veo/Kling)

> **Mục tiêu:** cho phép một beat dùng một đoạn video ngắn AI-sinh (thay vì ảnh
> tĩnh/slide) khi nội dung thật sự cần chuyển động.
> **Kết quả kiểm chứng được:** một video có ít nhất 1 beat dùng clip AI thật, ghép
> mượt vào timeline, thời lượng khớp với beat, cost ghi đúng vào ledger.
> **Phụ thuộc:** Phase 7 (cần pipeline đã ổn định, có test, trước khi thêm loại
> visual mới)
> **Ước lượng:** 2–3 buổi

**Phase này KHÔNG nằm trong định nghĩa "dùng được" của
[README.md](README.md).** Đó là mục tiêu $1/video với ảnh tĩnh + slide, không có
video-clip AI — xem phần "Cái gì KHÔNG nằm trong plan này". Phase 8 là mở rộng
**tùy chọn/opt-in**: `providers.video_clip.default` mặc định vẫn là `null`
(tắt), không phase nào trước đó bị chặn bởi việc phase này có làm hay không.

## Vấn đề đang có

- `s04_visual_plan.py`'s `VISUAL_TYPES` chỉ có 6 loại tĩnh (`title`, `code`,
  `diagram`, `comparison`, `ai_image`, `b_roll`) — không có loại nào sinh ra
  chuyển động thật.
- `core/providers/video_clip/veo.py` và `kling.py` hiện là stub thuần
  (`NotImplementedError`) — `VENDOR_MODULES["video_clip"]` đã trỏ tới chúng
  trong `registry.py` nhưng chưa ai gọi được.
- `s06_render.py`'s ffmpeg pipeline chỉ biết một cách dựng hình: loop một ảnh
  tĩnh suốt `beat_duration`. Không có logic nào xử lý một asset đã có sẵn thời
  lượng riêng (một clip video) cần khớp với `beat_duration` do TTS quyết định.
- Chi phí Veo/Kling (~$0.28–0.35/giây theo `pricing.yaml`) vượt xa ngân sách
  $1/video ngay cả với vài giây — không thể bật mặc định.

## Việc cần làm

### 8.1 — Thêm loại visual `ai_video_clip`

**File:** `core/stages/s04_visual_plan.py`, `prompts/en/educational/visual.md`

Thêm `ai_video_clip` vào `VISUAL_TYPES`. Cần một ngân sách riêng, tách khỏi
`max_ai_images` — ví dụ `budget.max_ai_video_clips` trong `project.yaml`
(mặc định 0, tức tắt). Threading ngân sách này qua classifier giống hệt cách
`remaining_ai_images` đã được truyền vào `visual.md` — thêm biến
`remaining_ai_video_clips`, và rule tương tự: hết ngân sách → hạ về `b_roll`.

### 8.2 — Provider Veo/Kling thật

**File:** `core/providers/video_clip/veo.py`, `core/providers/video_clip/kling.py`

Theo đúng khuôn mẫu `nano_banana.py` (retry 3 lần, delay `[1, 4, 10]` giây,
`estimate_cost` đọc `pricing.yaml`'s per-second rate, `health_check` gọi một
endpoint nhẹ). Khác biệt chính so với image: kết quả là job bất đồng bộ ở cả
Veo lẫn Kling thật (submit → poll → download) — đây là pipeline
submit/poll đầu tiên của dự án, phần khó nhất của bước này về mặt kỹ thuật.

### 8.3 — Manual provider cho video clip

**File:** `core/providers/video_clip/manual.py`

Mirror chính xác `core/providers/image/manual.py` (Phase hiện tại) —
cùng cơ chế `ManualAssetPending`, chỉ đổi `capability="video_clip"`, không cần
exception type mới. Mở rộng `core/manual_assets.py` với các hàm path
tương ứng cho clip (`.mp4` thay vì `.png`) — ví dụ `video_clip_prompt_path`,
`expected_video_clip_path`; `import_asset` cần biến thể nhận `.mp4` bytes.

### 8.4 — `s05_assets.py` bắt `ManualAssetPending` cho clip

Giống hệt cách beat `ai_image` đã bắt trong phase hiện tại — một nhánh
`vtype == "ai_video_clip"` riêng, cùng cấu trúc `try/except ManualAssetPending:
continue`, ghi vào `manual_pending.json` (dùng chung file, thêm field
`capability` để dashboard phân biệt ảnh vs clip khi hiển thị).

### 8.5 — Ghép clip vào `s06_render.py`

**File:** `core/stages/s06_render.py`

Phần khó nhất của phase này. Hiện tại mỗi beat luôn được xử lý như "loop ảnh
tĩnh cho đủ `beat_duration`". Một clip AI có thời lượng riêng (thường không
khớp `beat_duration` do TTS quyết định) — cần logic hòa giải:
- Clip ngắn hơn beat: loop hoặc freeze frame cuối cho đủ thời lượng.
- Clip dài hơn beat: cắt (trim) cho khớp, ưu tiên giữ đoạn đầu clip.
- Vẫn phải giữ đồng bộ audio/video hiện có — không được làm trôi timeline của
  các beat khác.

### 8.6 — Mô hình ngân sách

- `providers.video_clip.default` giữ nguyên `null` (tắt) theo mặc định — không
  đổi hành vi hiện tại của bất kỳ project nào.
- Bật Veo/Kling thật đòi hỏi nâng `budget.cap_usd` lên cao hơn hẳn $1 — Veo
  ≈$0.35/giây, Kling ≈$0.28/giây theo `pricing.yaml`, vài giây đã vượt ngân
  sách cả video.
- Vendor `manual/manual` luôn $0 bất kể `cap_usd`, giống hệt manual image ở
  phase hiện tại — đây vẫn là đường dùng thử miễn phí cho ai muốn có clip
  video mà không trả tiền Veo/Kling.

## Định nghĩa hoàn thành

- [ ] `ai_video_clip` xuất hiện như một lựa chọn hợp lệ trong `visual_plan.json`,
      có ngân sách riêng tách khỏi `max_ai_images`
- [ ] Ít nhất một trong hai provider Veo/Kling gọi được thật (submit → poll →
      tải file `.mp4` về đúng chỗ)
- [ ] `manual/manual` cho `video_clip` hoạt động giống hệt manual image — dashboard
      cho xem prompt, sửa tay/AI-improve, upload `.mp4`
- [ ] `s06_render.py` ghép được ít nhất một clip vào timeline, đồng bộ đúng với
      audio, không làm trôi các beat khác
- [ ] Cost clip video trong ledger đúng theo giây thực tế sinh ra, không phải giá
      ước lượng cứng

## Rủi ro

- **8.5 (ghép clip vào ffmpeg pipeline) là phần khó nhất, giống cảnh báo về
  `diagram` ở Phase 4.** Nếu tốn quá nửa buổi để làm đúng logic trim/freeze:
  cho phép giảm phạm vi xuống chỉ hỗ trợ "clip ngắn hơn hoặc bằng beat_duration,
  freeze frame cuối nếu ngắn hơn" — bỏ nhánh trim clip dài hơn, ghi lại thành
  việc riêng thay vì làm phase này trôi quá ước lượng.
- **Submit/poll bất đồng bộ là pipeline đầu tiên loại này trong dự án** — mọi
  provider khác hiện tại đều đồng bộ (một call, một response). Rủi ro
  timeout/poll vô hạn nếu API phía Veo/Kling đổi hành vi; cần timeout cứng và
  raise lỗi rõ ràng thay vì treo tiến trình `run`.
- **Chi phí thật nếu bật Veo/Kling có thể vượt xa ngân sách $1** nếu người dùng
  không tự tay nâng `cap_usd` — không có gì trong code này nên tự động nâng nó.
