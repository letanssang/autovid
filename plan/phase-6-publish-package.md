# Phase 6 — Gói xuất bản + duyệt trên dashboard

> **Mục tiêu:** mọi thứ cần để dán lên YouTube đều sẵn sàng, và duyệt 4 gate không phải mở terminal.
> **Kết quả kiểm chứng được:** mở dashboard, bấm duyệt qua 4 gate, rồi kéo `output.mp4` +
> `thumbnail.png` + copy `metadata.json` lên YouTube Studio là xong, không phải sửa gì bằng tay.
> **Phụ thuộc:** Phase 5 (cần video hoàn chỉnh mới đóng gói được)
> **Ước lượng:** 2 buổi

## Việc cần làm

### 6.1 — Thumbnail thật (gap #10)

**File:** `core/stages/s07_publish.py` (hiện `s07_publish.py:33` ghi `b""` — file rỗng)

Thumbnail quyết định tỉ lệ click, nên đáng làm tử tế. Hai phần:

- **Ảnh nền:** dùng lại image provider từ Phase 4 với `intent="hero"`, hoặc lấy slide `title`
  của hook. Dùng lại thì $0 và giữ đúng phong cách video.
- **Chữ đè lên:** thêm `templates/slides/thumbnail.html` (1280×720, chữ rất lớn, tương phản cao,
  đọc được ở kích thước nhỏ xíu trên điện thoại). Render bằng `html_renderer` đã có sẵn —
  không cần công cụ mới.

**Prompt mới:** `prompts/en/educational/thumbnail_text.md` — sinh 3–6 từ giật tít từ chủ đề
và outline. Chữ dài hơn 6 từ thì thumbnail không đọc nổi.

Sinh **3 phương án** và ghi cả ba ra `07_publish/thumbnail_a.png`, `_b`, `_c`, để bạn chọn.
Rẻ hơn nhiều so với chạy lại cả stage vì không ưng cái đầu tiên.

### 6.2 — Metadata dùng được thật (gap #10)

Hiện `s07_publish.py:20-25` sinh metadata thô sơ: title = chủ đề nguyên văn,
description một dòng, `tags = topic.split()[:15]` — tức "how neural networks learn"
thành tags `["how","neural","networks","learn"]`. Không dùng được.

Cần:

| Trường | Yêu cầu |
|---|---|
| `title` | Do LLM viết, ≤70 ký tự (YouTube cắt sau đó), hấp dẫn nhưng không giật gân sai sự thật |
| `description` | 2–3 đoạn: tóm tắt, **chapter timestamps**, ghi nguồn |
| `tags` | 10–15 tag thật do LLM sinh từ outline, không phải tách chuỗi |
| `chapters` | Timestamp thật từ `render_manifest.json` |

**Chapter timestamps gần như miễn phí** — `06_render/render_manifest.json` đã có `start_sec`
từng beat, `02_outline/outline.json` đã có ranh giới chương. Chỉ cần ghép và format `MM:SS`.
Đây là thứ giá trị cao nhất trong phase này so với công bỏ ra.

**Nguồn tham khảo:** `01_research/research.json` có URL của mọi nguồn. Đưa vào description —
vừa tăng uy tín, vừa đúng tinh thần "sourced" của master plan §6 S1.

**Prompt mới:** `prompts/en/educational/metadata.md`.

### 6.3 — Duyệt gate trên dashboard (gap #12)

**File:** `dashboard/server.py`

Endpoint `POST /projects/{name}/approve/{stage}` đã có (dòng 64) nhưng `index()` render HTML
không có nút nào gọi tới. Cần:

- **Trang chi tiết project** hiển thị được artifact của từng stage — ưu tiên render `.md`
  (đã làm ở bước 1.4) thay vì đổ JSON thô.
- **Nút Duyệt / Từ chối** ở mỗi gate chưa duyệt.
- **Từ chối** cần định nghĩa rõ: xoá `.approved` là chưa đủ, phải cho người dùng ghi lý do
  và chạy lại stage đó. Đề xuất: ghi `<stage>/.rejected` kèm ghi chú, `autovid run` thấy file này
  thì chạy lại stage và đưa ghi chú vào prompt.
- **Xem trước asset:** `<audio>` cho file mp3, `<img>` cho slide, `<video>` cho output.mp4.
  Thẻ HTML thuần là đủ, không cần framework.

Giữ nguyên phạm vi: đây là công cụ chạy trên `127.0.0.1` cho một người dùng. Không cần
đăng nhập, không cần WebSocket, không cần build step. Comment ở `dashboard/server.py:10-12`
nhắc HTMX/Alpine — chỉ thêm nếu thật sự thấy thiếu.

### 6.4 — Lệnh đóng gói

Thêm `autovid package <project>`: gom mọi thứ cần cho việc upload tay vào một thư mục:

```
07_publish/upload/
  video.mp4
  thumbnail.png          (bản đã chọn)
  subtitles.srt
  description.txt        (dán thẳng, đã có chapter timestamps)
  tags.txt               (dán thẳng)
```

Mục đích: lúc upload chỉ mở đúng một thư mục, không phải đi nhặt file từ 3 stage khác nhau.

## Định nghĩa hoàn thành

- [ ] `thumbnail.png` đúng 1280×720, thu nhỏ bằng ngón tay cái vẫn đọc được chữ
- [ ] `description.txt` dán vào YouTube → chapter tự động hiện thành các mốc bấm được
- [ ] Duyệt được cả 4 gate trên dashboard, không chạm terminal
- [ ] Từ chối một gate + ghi lý do → chạy lại stage đó có tính tới lý do
- [ ] `autovid package` ra một thư mục đủ để upload
- [ ] Upload thử một video lên YouTube ở chế độ **private**, xem lại thấy ổn

## Rủi ro

- **Cám dỗ làm dashboard quá to.** Đây là công cụ một người dùng chạy local — nếu bắt đầu
  nghĩ tới auth hay realtime là đã đi lạc. Giới hạn phase này ở: xem artifact + duyệt/từ chối.
- **Upload tự động vẫn nằm ngoài phạm vi.** `core/providers/publish/youtube.py` để nguyên là stub.
  Theo master plan §6 S7, bấm nút upload luôn là việc của con người. Không tự ý đổi.
