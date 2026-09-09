# Phase 0 — Trạng thái hiện tại (audit)

Không phải việc cần làm — đây là điểm xuất phát. Mọi phase sau tham chiếu về đây.
Số liệu lấy từ đọc code thật, không phải từ trí nhớ.

## Cái gì đã chạy thật

| Thành phần | File | Trạng thái |
|---|---|---|
| Filesystem-as-state, gate `.approved` | `core/state.py` | ✅ thật |
| Budget ledger | `core/budget.py` | ✅ thật (nhưng ghi ước lượng, xem gap #2) |
| Provider registry, routing theo stage, vendor→module | `core/providers/registry.py` | ✅ thật |
| Contracts (dataclass request/result) | `core/providers/contracts.py` | ✅ thật |
| CLI `new/status/run/approve/ui` | `cli/main.py` | ✅ thật, có resume |
| Prompt loader theo `(locale, format, name)` | `core/prompts.py` | ✅ thật |
| Slide HTML→PNG | `core/providers/slides/html_renderer.py` | ⚠️ thật nhưng cần `playwright install` |
| Dựng MP4 bằng ffmpeg | `core/stages/s06_render.py` | ⚠️ có code thật, chưa từng chạy ra file xem được |
| Dashboard đọc trạng thái | `dashboard/server.py` | ⚠️ chỉ đọc, không có nút duyệt |
| 7 stage pipeline | `core/stages/s01…s07` | ✅ chạy hết end-to-end với `local/fake`, $0 |

## Cái gì còn rỗng (`NotImplementedError`)

Toàn bộ provider có tính tiền đều là stub:

- **text** — `gemini.py`, `claude.py`, `openai.py`, `ollama.py` (chỉ `local_fake.py` chạy)
- **research** — `tavily.py`, `exa.py`, `gemini_grounding.py` (chỉ `local_fake.py` chạy)
- **tts** — `google_chirp.py`, `elevenlabs.py`, `edge.py`, `piper.py` (chỉ `local_fake.py` chạy, và nó ghi file **rỗng 0 byte**)
- **image** — `nano_banana.py`, `imagen.py`, `flux.py`, `sdxl_local.py` (mặc định `null` = tắt)
- **video_clip** — `veo.py`, `kling.py` (cố ý để ngoài scope)
- **publish** — `youtube.py` (cố ý để ngoài scope; `local_only.py` là no-op và đúng như vậy)

Nghĩa là: **hiện tại pipeline chạy hết 7 stage nhưng không sinh ra một byte nội dung thật nào.**
`script.json` chứa text placeholder, `.mp3` là file 0 byte, `.png` là file 0 byte.

## Gap và bug đã xác định (đọc code, chưa phải giả thuyết)

### #1 — Không có chỗ nào đọc `.env`
`.env.example` liệt kê 6 biến key, nhưng `grep -rn "environ\|getenv\|dotenv" --include="*.py"`
không ra kết quả nào, và `pyproject.toml` không có `python-dotenv`.
→ Provider thật đầu tiên viết ra sẽ không có cách lấy key. **Chặn Phase 1.**

### #2 — Budget ghi ước lượng, không ghi số thật
`core/providers/registry.py:64-66` gọi `estimate_cost(req)` **trước** khi gọi API rồi
ghi luôn con số đó vào ledger. Nhưng `TextResult` đã có sẵn `input_tokens`/`output_tokens`
(`contracts.py:31-35`) — tức là số thật có sẵn mà không được dùng.
→ Điều kiện "cost < $1 đo thật" ở định nghĩa dùng được sẽ không kiểm chứng nổi. **Chặn Phase 7.**

### #3 — Gate không có gì cho người đọc
`s03_script.py` chỉ ghi `script.json`. `s02_outline.py` chỉ ghi `outline.json`.
`s04_visual_plan.py` chỉ ghi `visual_plan.json`.
Chỉ `s01_research.py` có ghi kèm `research.md`.
→ Ba trên bốn gate bắt người duyệt đọc JSON thô. **Chặn Phase 1/6.**

### #4 — Slide nào cũng chỉ nhận `title`
`s05_assets.py:62`:
```python
content={"title": beat["text"]}
```
Nhưng `templates/slides/code.html` cần biến `code`, `diagram.html` cần `svg` + `caption`,
`comparison.html` cần `left_title`/`left_items`/`right_title`/`right_items`.
→ 3 trên 4 template render ra slide gần như trống. **Chặn Phase 4.**

### #5 — Beat `b_roll` biến mất khỏi video nhưng tiếng vẫn chạy
`s05_assets.py:66` trả `asset_path: None` cho `b_roll`.
`s06_render.py:80` lọc `if b["asset_path"]` → beat đó không có hình trong danh sách concat.
Nhưng audio của cả section vẫn phát đủ.
→ **Tiếng và hình lệch nhau, lệch dồn tích lũy về cuối video.** Đây là bug nặng nhất hiện có. **Chặn Phase 3.**

### #6 — Visual type chọn bằng round-robin, không nhìn nội dung
`s04_visual_plan.py:11-13` xoay vòng `["title","diagram","code","comparison","ai_image","b_roll"]`.
Prompt phân loại bằng LLM đã viết sẵn ở `prompts/en/educational/visual.md` nhưng **chưa được gọi ở đâu cả**.
→ Video về lịch sử sẽ có slide `code`. **Chặn Phase 4.**

### #7 — Thời lượng audio là con số bịa
`core/providers/tts/local_fake.py` tính `duration_sec = words / 150 * 60`.
`s06_render.py:24` tin tuyệt đối con số đó để dựng timeline và `.srt`.
→ Với TTS thật, thời lượng thật sẽ khác. Cần đo bằng `ffprobe`. **Chặn Phase 2.**

### #8 — ffmpeg pipeline chưa từng chạy thành công
`s06_render.py:102-113` dùng concat demuxer với ảnh PNG rồi `-c:v copy` ở bước mux cuối.
Concat demuxer đòi mọi input **cùng resolution/codec**; PNG từ slide (1920×1080) và PNG từ
AI image (kích thước tùy provider) sẽ không đồng nhất. Chưa có `-r` (fps), chưa có scale filter.
→ Nhiều khả năng vỡ ngay lần đầu chạy với ảnh thật. **Chặn Phase 3.**

### #9 — Cấu trúc outline cứng, không liên quan độ dài
`s01_research.py` khai báo 5 angle cố định, `s02_outline.py:12` nhân đôi thành 10 section,
`s03_script.py:26-27` chia đều thời lượng mục tiêu cho 10 section — bất kể chủ đề, bất kể
`target_duration_minutes` là 15 hay 40.
→ Không có cơ chế nào ép LLM viết đủ dài. **Chặn Phase 5.**

### #10 — Thumbnail là file rỗng
`s07_publish.py:33` ghi `b""`. Metadata `tags` = `topic.split()` (`s07_publish.py:23`).
→ Không dán lên YouTube được. **Chặn Phase 6.**

### #11 — Không có test nào
Không có file `test_*.py` nào trong repo, dù `pytest` đã khai báo ở `[project.optional-dependencies]`.
→ **Chặn Phase 7.**

### #12 — Dashboard không duyệt được
`dashboard/server.py:64` có endpoint `POST /projects/{name}/approve/{stage}`,
nhưng `index()` render HTML không có form/nút nào gọi nó.
→ Muốn duyệt vẫn phải quay ra CLI. **Chặn Phase 6.**

## Bản đồ gap → phase

| Gap | Phase xử lý |
|---|---|
| #1 env, #3 artifact `.md` | Phase 1 |
| #7 duration thật | Phase 2 |
| #5 drift tiếng/hình, #8 ffmpeg | Phase 3 |
| #4 slide content, #6 visual classifier | Phase 4 |
| #9 độ dài | Phase 5 |
| #10 thumbnail/metadata, #12 dashboard duyệt | Phase 6 |
| #2 cost thật, #11 test | Phase 7 |
