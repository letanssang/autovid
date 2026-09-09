# AutoVid — Plan đi tới "dùng được"

Tài liệu này chia đường đi từ scaffold hiện tại đến lúc bạn thật sự dùng AutoVid
để làm video YouTube. Mỗi phase là một lát cắt dọc chạy được và kiểm chứng được,
không phải một lớp kiến trúc.

## Định nghĩa "dùng được"

AutoVid được coi là dùng được khi **cả 6 điều sau đồng thời đúng**:

1. `autovid new "<chủ đề bất kỳ>"` → chạy tới cuối → có `06_render/output.mp4`
   mở lên xem được, dài 15–25 phút.
2. Giọng đọc là giọng thật, nghe được hết video, không lệch tiếng/hình.
3. Hình trên màn hình khớp với nội dung đang nói (không phải slide random).
4. Có `subtitles.srt`, `thumbnail.png` thật, `metadata.json` đủ để dán lên YouTube
   (kèm chapter timestamps).
5. Tổng chi phí API trong `budget_ledger.json` < $1.00, số đo thật chứ không phải ước lượng.
6. Đã chạy trọn vẹn trên **3 chủ đề khác nhau** mà không phải sửa code giữa chừng.

Điểm 6 là điều kiện thật sự — mọi thứ trước đó chỉ là "chạy được một lần".

## Các phase

| Phase | Tên | Kết quả nhìn thấy được | Doc |
|---|---|---|---|
| 0 | Trạng thái hiện tại | Audit: cái gì thật, cái gì rỗng, bug đã biết | [00-current-state.md](00-current-state.md) |
| 1 | Nội dung thật | `research.md` + `script.md` đọc được, do LLM thật viết, có nguồn | [phase-1-real-content.md](phase-1-real-content.md) |
| 2 | Giọng nói thật | File `.mp3` nghe được, thời lượng đo thật bằng ffprobe | [phase-2-real-voice.md](phase-2-real-voice.md) |
| 3 | **Video đầu tiên** | `output.mp4` mở lên xem được từ đầu tới cuối | [phase-3-first-video.md](phase-3-first-video.md) |
| 4 | Hình đúng nội dung | Slide/ảnh khớp với câu đang đọc, không còn round-robin | [phase-4-right-visuals.md](phase-4-right-visuals.md) |
| 5 | Đủ dài & mạch lạc | Video chạm 15–25 phút, có hook, có chương, không lặp ý | [phase-5-length-and-flow.md](phase-5-length-and-flow.md) |
| 6 | Gói xuất bản + duyệt | Thumbnail, metadata, chapter; duyệt gate ngay trên dashboard | [phase-6-publish-package.md](phase-6-publish-package.md) |
| 7 | Kiểm chứng & ổn định | 3 chủ đề chạy sạch, cost < $1, có test, có README | [phase-7-harden.md](phase-7-harden.md) |

**Mốc quan trọng:** hết Phase 3 bạn có video thật đầu tiên (xấu nhưng thật).
Hết Phase 7 mới là "dùng được" theo định nghĩa trên.

## Thứ tự này được chọn như thế nào

Nguyên tắc: **đi dọc trước, đi ngang sau.** Phase 1–3 chỉ làm đủ để một video thật
chui ra khỏi ống — chấp nhận nó xấu và ngắn. Từ Phase 4 mới quay lại nâng chất
từng khâu.

Lý do: mọi giả định trong scaffold hiện tại (thời lượng audio, kích thước ảnh,
ffmpeg concat, drift tiếng/hình) chỉ lộ ra khi có dữ liệu thật chạy qua. Đánh bóng
visual classifier trước khi biết ffmpeg có ghép nổi hay không là làm việc mù.

## Ước lượng tổng

| Phase | Ước lượng |
|---|---|
| 1 | 2 buổi |
| 2 | 1–2 buổi |
| 3 | 2 buổi |
| 4 | 2–3 buổi |
| 5 | 2 buổi |
| 6 | 2 buổi |
| 7 | 2 buổi |
| **Tổng** | **13–15 buổi** (1 buổi ≈ nửa ngày làm việc tập trung) |

Tới video thật đầu tiên (hết Phase 3): **5–6 buổi**.

## Quyết định cần bạn chốt trước khi bắt đầu Phase 1

Ba câu này quyết định mọi thứ phía sau. Chi tiết trong
[phase-1-real-content.md](phase-1-real-content.md#quyết-định-cần-bạn-chốt).

1. **Bạn đang có API key nào?** (Gemini / Anthropic / OpenAI / Tavily)
2. **Ưu tiên rẻ hay ưu tiên chất lượng script?** — ảnh hưởng chọn model mặc định.
3. **Đã cài `ffmpeg` chưa?** Không có nó thì Phase 3 dừng lại (`brew install ffmpeg`).

## Cái gì KHÔNG nằm trong plan này

Cố ý để ngoài, làm sau khi đã dùng được:

- Format thứ 2 ngoài `educational` — kiến trúc đã mở sẵn (`prompts/<locale>/<format>/`),
  nhưng chưa cần chứng minh khi chưa dùng nổi format đầu tiên.
- Upload YouTube tự động (`core/providers/publish/youtube.py`) — theo master plan §6 S7,
  upload luôn là thao tác tay. Adapter để đó.
- Video clip AI (`veo`, `kling`) — quá đắt cho ngân sách $1/video.
- `notebooklm` slides, `sdxl_local`, `elevenlabs` — nhánh dự phòng, không chặn đường.
