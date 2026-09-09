# Phase 1 — Nội dung thật

> **Mục tiêu:** LLM thật và search thật viết ra research + outline + script, đọc được bằng mắt người.
> **Kết quả kiểm chứng được:** mở `projects/<x>/03_script/script.md` và đọc thấy một kịch bản
> thật về đúng chủ đề, có trích nguồn, không phải placeholder.
> **Phụ thuộc:** không
> **Ước lượng:** 2 buổi

## Tại sao phase này đi đầu

Ba stage đầu là toàn bộ phần "nội dung" của video. Nếu script dở thì TTS xịn, visual đẹp,
render mượt đều vô nghĩa. Và đây cũng là chỗ duy nhất bạn có thể đánh giá chất lượng
**trước khi tiêu tiền** cho TTS/ảnh ở phase sau.

## Việc cần làm

### 1.1 — Đọc được `.env` (gap #1, chặn mọi thứ)

**File mới:** `core/env.py`
**Sửa:** `pyproject.toml`, `cli/main.py`, `dashboard/server.py`

```python
# core/env.py — hình dung
def require_key(var_name: str, provider_id: str) -> str:
    """Trả về giá trị biến môi trường, hoặc báo lỗi nói rõ cần sửa file nào."""
```

Yêu cầu về thông báo lỗi: khi thiếu key phải nói **cả ba** thứ — thiếu biến nào,
provider nào đang cần, và sửa ở đâu:

```
Thiếu GEMINI_API_KEY (cần bởi provider 'gemini/gemini-3.1-flash-lite',
đang được chọn ở projects/<x>/project.yaml → providers.text.default).
Thêm vào .env ở thư mục gốc repo.
```

Thêm `python-dotenv>=1.0` vào `dependencies`. Load `.env` **một lần** ở entrypoint
(`cli/main.py` và `dashboard/server.py`), không load rải rác trong từng adapter.

### 1.2 — Text provider thật đầu tiên

**File:** `core/providers/text/gemini.py` (xem mục [Quyết định](#quyết-định-cần-bạn-chốt))

Ba method cần hiện thực hoá:

**`generate(req) -> TextResult`**
- Gọi API bằng `httpx` (đã là dependency sẵn — không thêm vendor SDK, giữ cài đặt gọn).
- Map `req.system` → system instruction, `req.max_output_tokens`, `req.temperature`.
- Điền `input_tokens`/`output_tokens` từ trường usage trong response — **không ước lượng**,
  Phase 7 cần số này để đối chiếu cost thật (gap #2).
- Retry có backoff cho 429/5xx: 3 lần, 1s → 4s → 10s. Timeout 120s.
- Lỗi 4xx khác thì fail ngay kèm body lỗi — đừng nuốt lỗi thành text rỗng, stage sau
  sẽ sinh ra script trống mà không ai biết tại sao.

**`estimate_cost(req) -> Money`**
- Đọc `core/providers/pricing.yaml`, tra theo `self.id`.
- Ước lượng input token ≈ `len(prompt) / 4`, output token = `req.max_output_tokens`.
- Cố ý ước lượng cao — đây là hàng rào chặn trước khi gọi, thà dừng nhầm còn hơn tiêu lố.

**`health_check() -> HealthStatus`**
- Có key không? Gọi thử một request cực nhỏ được không? Trả `detail` nói rõ hỏng ở đâu.

### 1.3 — Research provider thật đầu tiên

**File:** `core/providers/research/gemini_grounding.py` hoặc `tavily.py`

- Trả `ResearchResult(sources=[ResearchSource(url, title, snippet, confidence)])`.
- `confidence`: quy ước rõ ràng — ví dụ domain học thuật/chính phủ 0.9, báo lớn 0.7,
  blog 0.4. Viết quy ước này thành comment trong file, vì `s01_research.py` in nó ra
  `research.md` cho người duyệt đọc.
- Nếu search không trả về gì cho một angle: trả list rỗng, **không raise**. `s01` phải
  vẫn ghi được `research.md` với angle đó đánh dấu không có nguồn.

### 1.4 — Artifact đọc được ở mọi gate (gap #3)

Ba gate hiện chỉ có JSON. Thêm bản `.md` song song, **không thay thế** JSON
(JSON là input của stage sau, `.md` là cho mắt người):

| Stage | Thêm file | Nội dung |
|---|---|---|
| `s02_outline.py` | `02_outline/outline.md` | Cây chương → section, kèm số section và thời lượng dự kiến mỗi section |
| `s03_script.py` | `03_script/script.md` | Từng section: tiêu đề, số từ, thời lượng mục tiêu, rồi tới lời thoại |
| `s04_visual_plan.py` | `04_visual_plan/visual_plan.md` | Bảng: beat → loại visual → 60 ký tự đầu của lời thoại |

`script.md` nên in **số từ thực tế** cạnh **số từ mục tiêu** ngay từ Phase 1 — đó là
cách bạn nhìn thấy vấn đề độ dài (gap #9) sớm, dù mãi Phase 5 mới sửa.

### 1.5 — Ghi cost thật vào ledger (gap #2, phần text)

**Sửa:** `core/providers/registry.py`, `core/budget.py`

Hiện `_MeteredAdapter._metered_call` ghi ước lượng trước khi gọi. Cần:
- Vẫn dùng `estimate_cost` để **chặn trước** (giữ nguyên logic hiện tại).
- Sau khi có kết quả, nếu result có `input_tokens`/`output_tokens` thì tính lại cost thật
  và ghi **con số thật** vào ledger.
- Thêm trường `estimated_usd` bên cạnh `cost_usd` trong entry của ledger, để Phase 7
  đối chiếu được ước lượng lệch bao nhiêu so với thật.

## Định nghĩa hoàn thành

- [ ] `autovid new "how photosynthesis works"` rồi chạy `01→03` với provider thật, không crash
- [ ] `01_research/research.md` có nguồn thật, click link mở ra được
- [ ] `02_outline/outline.md` và `03_script/script.md` đọc được, đúng chủ đề
- [ ] `budget_ledger.json` có số > 0 và số đó là token thật, không phải ước lượng
- [ ] Xoá `.env` đi chạy lại → báo lỗi rõ ràng, không phải `KeyError`
- [ ] Đặt `budget.cap_usd: 0.01` → pipeline dừng giữa chừng với `BudgetExceeded`, không tiêu lố
- [ ] `ruff check .` sạch

## Quyết định cần bạn chốt

**1. Provider text nào?**

| Lựa chọn | Cost/video ước tính¹ | Ghi chú |
|---|---|---|
| `gemini/gemini-3.1-flash-lite` cho tất cả | ~$0.02 | Rẻ nhất, đủ cho outline; script có thể nhạt |
| `gemini-3.1-flash-lite` + route `s03_script` sang `anthropic/claude-sonnet-5` | ~$0.15 | **Khuyến nghị.** Chỗ cần văn hay chỉ có script |
| `anthropic/claude-sonnet-5` cho tất cả | ~$0.40 | Ăn gần nửa ngân sách $1 chỉ cho chữ |

¹ Ước lượng thô cho script ~3.500 từ. Số thật sẽ có sau khi làm xong 1.5.

`project.yaml` đã hỗ trợ sẵn cách 2 mà không cần sửa code:
```yaml
providers:
  text:
    default: gemini/gemini-3.1-flash-lite
    routes: { s03_script: anthropic/claude-sonnet-5 }
```

**2. Provider research nào?** — `gemini/grounding` nếu bạn đã có Gemini key (đỡ đăng ký
thêm dịch vụ, và pricing.yaml ghi free tới 5k query/tháng). `tavily` nếu muốn kết quả
search sạch hơn và chấp nhận thêm một key nữa.

**3. Bạn thực sự có key nào?** Nếu chưa có key nào cả thì Phase 1 dừng ở bước 1.1 —
nói tôi biết, tôi sẽ đảo thứ tự để làm `ollama` (chạy local, miễn phí) trước.

## Rủi ro

- **Model trả về text kèm rác** (markdown fence, lời dẫn "Here's the script:"). Prompt hiện tại
  đã yêu cầu "plain spoken narration only" nhưng model vẫn hay thêm. Cần hàm dọn output
  dùng chung — đặt ở `core/prompts.py` để mọi stage xài lại, đừng lặp ở từng stage.
- **Rate limit tier free** rất dễ chạm khi chạy 10 section liên tiếp. Backoff ở 1.2 không phải
  tuỳ chọn.
