# Phase 2 — Giọng nói thật

> **Mục tiêu:** script biến thành file audio nghe được, và thời lượng là số đo thật.
> **Kết quả kiểm chứng được:** mở `05_assets/audio/*.mp3` bằng trình phát nhạc, nghe hết,
> và `duration_sec` trong manifest khớp với thời lượng file thật (sai số < 0.1s).
> **Phụ thuộc:** Phase 1 (cần script thật để đọc)
> **Ước lượng:** 1–2 buổi

## Tại sao là phase riêng, không gộp vào Phase 3

Vì thời lượng audio là **trục thời gian của toàn bộ video**. `s06_render.py:24` lấy
`duration_sec` để chia timeline và sinh `.srt`. Nếu con số này sai thì phụ đề lệch,
hình lệch, và bạn sẽ đi debug ffmpeg trong khi lỗi nằm ở TTS. Tách ra để sửa xong
trục thời gian trước, rồi mới ghép hình.

## Việc cần làm

### 2.1 — TTS provider thật

**File:** `core/providers/tts/edge.py` (xem [Quyết định](#quyết-định-cần-bạn-chốt))

- `synthesize(req) -> TTSResult` ghi file audio thật vào `req.out_path`.
- Áp dụng `req.rate` và `req.voice_id` (đọc từ `providers.tts.options` trong `project.yaml`,
  hiện đã có sẵn `voice` và `rate`).
- **Chunking:** một section 15–25 phút chia 10 phần vẫn có thể ra 2.000+ ký tự. Google Chirp
  giới hạn ~5.000 byte/request; Edge TTS ổn định hơn khi chia nhỏ. Cắt theo **ranh giới câu**,
  tổng hợp từng chunk rồi nối lại — cắt giữa câu sẽ nghe rõ chỗ vá.
- Nối chunk bằng ffmpeg concat (cùng codec, cùng sample rate → an toàn), không nối byte thô.

### 2.2 — Đo thời lượng thật bằng ffprobe (gap #7)

**File mới:** `core/audio.py`

```python
def probe_duration_sec(path: str) -> float:
    """ffprobe -v error -show_entries format=duration -of csv=p=0 <path>"""
```

- **Mọi** TTS adapter trả `TTSResult.duration_sec` bằng số đo từ đây, không phải ước lượng.
- `local_fake.py` giữ nguyên cách tính từ số từ (nó ghi file 0 byte, không probe được) —
  nhưng thêm comment nói rõ đó là con số giả, để không ai tin nhầm.
- Không có `ffprobe` trên PATH → báo lỗi rõ ràng ngay lúc `health_check()`, đừng để tới
  lúc render mới vỡ.

### 2.3 — Chuẩn hoá âm lượng

Mỗi chunk/section tổng hợp riêng sẽ lệch loudness nhẹ. Chạy `loudnorm` một lượt:

```
ffmpeg -i in.mp3 -af loudnorm=I=-16:TP=-1.5:LRA=11 out.mp3
```

`-16 LUFS` là mức YouTube hay dùng cho nội dung nói. Làm ở tầng adapter (sau khi nối chunk),
không phải ở `s06_render` — để mọi TTS provider đều ra cùng một mức.

### 2.4 — Cost thật cho TTS

`pricing.yaml` tính TTS theo `per_1m_chars`. `TTSResult` đã có `char_count`.
Nối vào cơ chế cost-thật đã dựng ở bước 1.5: ghi ledger theo `char_count` thật trả về,
không theo độ dài prompt ước lượng.

Với `edge/tts` và `piper/local` thì cost = 0, nhưng vẫn ghi entry vào ledger để Phase 7
đối chiếu được số ký tự đã đọc.

## Định nghĩa hoàn thành

- [ ] `05_assets/audio/<section>.mp3` mở lên nghe được, đọc đúng nội dung `script.md`
- [ ] `probe_duration_sec()` trên file đó khớp `duration_sec` trong `assets_manifest.json`
- [ ] Tổng thời lượng các section ≈ thời lượng mục tiêu (chưa cần chính xác — Phase 5 lo)
- [ ] Section dài nhất (>2.000 ký tự) tổng hợp không lỗi, chỗ nối chunk nghe không rõ mối
- [ ] Âm lượng các section đồng đều khi nghe liên tiếp
- [ ] `budget_ledger.json` có entry `tts` với `char_count` thật

## Quyết định cần bạn chốt

**Giọng đọc nào?** Master plan §13.2 để ngỏ câu này và yêu cầu A/B trước khi chốt.
Đề xuất: làm `edge` trước để thông ống, rồi nghe thử cả hai trên **cùng một đoạn script thật**
trước khi quyết định.

| Provider | Cost | Ưu | Nhược |
|---|---|---|---|
| `edge/tts` | $0 | Không cần key, chất lượng bất ngờ tốt | API không chính thức, có thể đứt bất kỳ lúc nào |
| `google/chirp3-hd` | $0 tới 1M ký tự/tháng, sau đó $30/1M | Chính thức, ổn định, giọng rất tự nhiên | Cần GCP project + credential |
| `piper/local` | $0 | Chạy offline hoàn toàn, không giới hạn | Chất lượng thấp hơn rõ rệt |
| `elevenlabs` | $180/1M ký tự | Hay nhất | ~$0.63 cho video 3.500 từ → **vượt 60% ngân sách $1**. Loại. |

Ước tính: script 3.500 từ ≈ 21.000 ký tự → Chirp 3 HD hết ~$0.63 nếu đã quá free tier,
nhưng $0 nếu bạn làm dưới ~47 video/tháng. Với dùng cá nhân thì Chirp thực tế là miễn phí.

**Khuyến nghị:** làm `edge` trong phase này (thông ống, không cần setup),
mở issue A/B với `google/chirp3-hd` để chốt ở Phase 7.

## Rủi ro

- **Edge TTS là API không chính thức.** Nếu Microsoft chặn, `providers.tts.fallback` trong
  `project.yaml` đã có sẵn chỗ khai báo — nhưng fallback chain hiện **chưa được
  `registry.resolve()` dùng tới** (`fallback_chain()` có mà không ai gọi). Nếu chọn `edge`,
  thêm việc "hiện thực hoá fallback chain" vào phase này. Nếu chọn `chirp` thì để Phase 7.
- **Thời lượng thật sẽ khác xa ước lượng 150 từ/phút.** Chuẩn bị tinh thần video ra ngắn hơn
  hoặc dài hơn mong đợi đáng kể — đó chính là dữ liệu đầu vào cho Phase 5.
