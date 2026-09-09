# Phase 3 — Video đầu tiên xem được 🎯

> **Mục tiêu:** một file MP4 thật chui ra khỏi ống, mở lên xem hết được, tiếng khớp hình.
> **Kết quả kiểm chứng được:** double-click `06_render/output.mp4`, xem từ đầu tới cuối,
> giọng đọc khớp với slide đang hiện, phụ đề `.srt` load vào đúng chỗ.
> **Phụ thuộc:** Phase 2 (cần audio thật và trục thời gian đúng)
> **Ước lượng:** 2 buổi

## Mốc quan trọng

Đây là lần đầu tiên AutoVid tạo ra thứ có thể gọi là video. Chấp nhận: chỉ có slide chữ,
không có ảnh AI, không hiệu ứng, nội dung có thể hơi ngắn. Mục tiêu là **thông ống**,
không phải làm đẹp.

## Việc cần làm

### 3.1 — Cài browser cho Playwright

```bash
playwright install chromium
```

`html_renderer.py:45` hiện nuốt mọi lỗi Playwright và ghi PNG rỗng 0 byte (cố ý, để scaffold
chạy offline). Sau khi cài, nó render thật.

**Cần sửa:** cách nuốt lỗi hiện tại quá im lặng — pipeline sẽ chạy "thành công" với toàn ảnh
rỗng mà không báo gì. Thêm: khi degrade, ghi lý do vào `05_assets/slide_render_status.json`
và in cảnh báo ra CLI. Người dùng phải biết mình vừa nhận về ảnh rỗng.

### 3.2 — Sửa drift tiếng/hình (gap #5 — bug nặng nhất)

**File:** `core/stages/s05_assets.py`, `core/stages/s06_render.py`

Vấn đề: beat `b_roll` trả `asset_path: None` (`s05_assets.py:66`), `s06_render.py:80` lọc bỏ
chúng khỏi danh sách concat, nhưng audio của section vẫn phát đủ độ dài.
→ Hình hết trước tiếng, và lệch dồn tích luỹ về cuối video.

Nguyên tắc sửa: **mọi beat trên timeline phải có đúng một visual.** Không có ngoại lệ,
không có `None`.

Cách làm ở phase này (đơn giản, đủ dùng): `b_roll` chưa có nguồn thật → render bằng
template `title` với chính lời thoại của beat đó. Xấu nhưng đúng thời lượng.
Phase 4 sẽ thay bằng thứ tử tế hơn.

Thêm kiểm tra bất biến ở đầu `s06_render.py`: nếu số beat trong timeline ≠ số visual
có asset, dừng ngay với thông báo rõ ràng thay vì lặng lẽ dựng ra video lệch.

### 3.3 — ffmpeg pipeline dựng được thật (gap #8)

**File:** `core/stages/s06_render.py`

Pipeline hiện tại (`_render_with_ffmpeg`, dòng 78–118) có ba chỗ sẽ vỡ với ảnh thật:

| Vấn đề | Hiện tại | Cần |
|---|---|---|
| Ảnh khác kích thước | concat demuxer đòi đồng nhất | `scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2` cho mọi input |
| Không có fps | thiếu `-r` | `-r 30` (hoặc 24 — chốt một lần rồi ghi vào config) |
| `-c:v copy` sau concat | dòng 111, copy stream đã encode | encode thật: `-c:v libx264 -preset medium -crf 23` |

Cấu trúc nên đổi: thay concat demuxer bằng **filter_complex** dựng từ danh sách ảnh +
duration. Ổn định hơn hẳn với input không đồng nhất, và mở đường cho hiệu ứng ở Phase 4.

Với video 20 phút / ~200 beat, chuỗi filter sẽ rất dài → ghi ra **filter script file**
và dùng `-filter_complex_script`, tránh chạm giới hạn độ dài dòng lệnh shell.

### 3.4 — Render có tiến trình và log được

Encode 20 phút video mất vài phút. Hiện `subprocess.run(capture_output=True)` chạy câm.

- Stream stderr của ffmpeg ra file `06_render/ffmpeg.log` (đầy đủ, để debug).
- In tiến trình gọn ra CLI (parse dòng `time=` của ffmpeg), để biết nó còn sống.
- Giữ `render_status.json` như hiện tại — nó đã đúng thiết kế.

### 3.5 — Dọn file trung gian

`_audio_concat.txt`, `_video_concat.txt`, `_narration.mp3`, `_silent.mp4` đang nằm lại
trong `06_render/` (đã ignore trong `.gitignore` nhưng vẫn chiếm đĩa).
Xoá khi render thành công, **giữ lại khi thất bại** để còn debug.

## Định nghĩa hoàn thành

- [ ] `output.mp4` mở bằng QuickTime/VLC, xem hết không lỗi
- [ ] Tiếng và hình khớp nhau **ở phút cuối cùng** (chỗ drift lộ rõ nhất)
- [ ] `subtitles.srt` load vào VLC, chữ hiện đúng lúc đang nói
- [ ] Slide chữ hiển thị đúng font, đúng theme tối, không tràn khung
- [ ] `ffmpeg.log` có nội dung, `render_status.json` báo `rendered: true`
- [ ] Chạy lại `autovid run --from 06_render` cho ra file y hệt (idempotent)

## Rủi ro

- **Đây là phase dễ trượt ước lượng nhất.** ffmpeg filter graph là thứ hay tốn nửa buổi cho
  một dấu ngoặc. Nếu quá 2 buổi: cắt bớt về phương án đơn giản nhất — chuẩn hoá **mọi** ảnh
  về đúng 1920×1080 PNG ngay từ `s05_assets`, rồi concat demuxer sẽ chạy được với code hiện có.
- **File 20 phút encode chậm.** Thêm option `--preview` chỉ render 60 giây đầu để vòng lặp
  thử-sai không phải chờ 5 phút mỗi lần. Việc này trả lại thời gian ngay trong chính phase này.

## Sau phase này bạn có gì

Một video thật, xấu, toàn slide chữ, nhưng **thật**. Từ đây mọi phase sau đều có thể
đo bằng "video có tốt lên không" thay vì đo bằng cảm giác.
