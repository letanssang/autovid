# Phase 7 — Kiểm chứng & ổn định 🎯

> **Mục tiêu:** chứng minh AutoVid dùng được thật, không phải chạy được một lần nhờ may.
> **Kết quả kiểm chứng được:** 3 chủ đề khác nhau chạy trọn vẹn, không sửa code giữa chừng,
> mỗi video dưới $1 đo bằng số thật.
> **Phụ thuộc:** Phase 6
> **Ước lượng:** 2 buổi

## Vì sao cần phase này

Hết Phase 6 bạn có **một** video tốt. Nhưng nó được làm ra trong lúc vừa chạy vừa sửa.
Câu hỏi thật là: chủ đề tiếp theo có chạy được không, hay lại phải mở code ra vá?

Phase này biến "chạy được" thành "dùng được".

## Việc cần làm

### 7.1 — Cost thật, không phải ước lượng (gap #2)

Bước 1.5 đã dựng khung ghi cost thật. Giờ đóng vòng:

- Đối chiếu `estimated_usd` vs `cost_usd` trong ledger. Ước lượng lệch > 30% thì sửa
  `estimate_cost` — vì nó là hàng rào chặn chi tiêu, ước lượng sai làm hàng rào vô dụng.
- Thêm `autovid cost <project>`: bảng tổng theo capability và theo stage. Câu bạn thật sự
  cần trả lời là "tiền đi đâu", không phải "hết bao nhiêu".
- Với TTS/image có free tier (Chirp 1M ký tự/tháng, Gemini grounding 5k query/tháng),
  ledger đang ghi $0 — đúng, nhưng che mất mức tiêu thụ hạn mức. Ghi thêm cả lượng dùng
  (ký tự, số query) để biết bao giờ chạm trần tháng.

### 7.2 — Test (gap #11)

Chưa có file test nào, dù `pytest` đã khai báo trong `pyproject.toml`.
**Không đuổi theo độ phủ.** Chỉ test những chỗ hỏng âm thầm:

| Test | Vì sao |
|---|---|
| Gate: chưa duyệt thì `run` dừng; duyệt rồi thì đi tiếp | Cơ chế an toàn cốt lõi. Hỏng cái này là mất kiểm soát |
| Resume: chạy lại không làm lại stage đã xong | Đã từng có bug đúng chỗ này |
| Budget: vượt cap → `BudgetExceeded`, dừng thật | Hàng rào tiền |
| Timeline: số beat = số visual, tổng thời lượng = tổng audio | Bug drift ở gap #5 |
| Registry: mọi vendor trong `VENDOR_MODULES` import được và có `get_adapter` | Sai chính tả vendor sẽ nổ lúc chạy giữa chừng |
| `slug()`: ID sinh ra không có dấu cách | Đã từng có bug đúng chỗ này |
| High-stakes: có `[UNSOURCED]` thì `approve` từ chối | Cơ chế an toàn nội dung |

Dùng `local/fake` cho toàn bộ test — nhanh, offline, $0, chạy được trong CI.

### 7.3 — Chạy thật 3 chủ đề

Chọn ba chủ đề **khác thể loại nhau** để lộ ra giả định ngầm:

1. **Kỹ thuật** — "how neural networks learn" (có code, có sơ đồ)
2. **Lịch sử/nhân văn** — "the history of the silk road" (không có code, nhiều mốc thời gian)
3. **High-stakes** — đặt `high_stakes: true`, ví dụ chủ đề sức khoẻ (kiểm tra hàng rào `[UNSOURCED]`
   ở `cli/main.py:138-145` thật sự chặn)

Với mỗi chủ đề ghi lại: cost thật, thời lượng, số lần phải can thiệp tay, chỗ nào tệ nhất.
Bảng này chính là bằng chứng cho định nghĩa "dùng được".

Dự đoán chủ đề 2 sẽ lộ vấn đề: visual classifier ở Phase 4 được chỉnh trên chủ đề kỹ thuật.

### 7.4 — Fallback chain

`project.yaml` khai báo `fallback: []` cho text/research/tts, và `registry.py:87` có hàm
`fallback_chain()` — nhưng **không ai gọi nó**. Chuỗi dự phòng hiện tại chỉ là trang trí.

Hiện thực hoá trong `Registry.resolve()`: provider chính lỗi (mạng, rate limit, hết quota)
thì thử lần lượt provider dự phòng, ghi rõ vào ledger là đã fallback.

Đây là thứ biến "chạy được khi mọi API đều khoẻ" thành "chạy được vào thứ Ba". Nếu Phase 2
chọn `edge/tts` (API không chính thức) thì việc này đã làm rồi.

### 7.5 — Tài liệu

- **`README.md`** (chưa có): cài đặt, lấy key ở đâu, chạy video đầu tiên, chi phí thực đo.
- **`CLAUDE.md`**: quy ước kiến trúc cho lần sau quay lại sửa — không import vendor SDK trong
  stage code, prompt không hardcode, gate là file, format mở rộng bằng thư mục.
- Cập nhật `plan/00-current-state.md` cho khớp thực tế mới, hoặc đánh dấu đã lỗi thời.

### 7.6 — Xử lý lỗi khi đang chạy

Pipeline chạy 5–10 phút với API thật. Hỏng ở stage 6 mà mất hết công của stage 1–5 là không chấp nhận được.

- Stage lỗi → artifact các stage trước **phải còn nguyên** (kiến trúc filesystem-as-state đã
  cho sẵn điều này — cần kiểm chứng chứ không mặc định đúng).
- Thông báo lỗi phải nói được **chạy lại thế nào**: `autovid run <project> --from 06_render`.
- Ctrl-C giữa chừng không được để lại artifact viết dở khiến `has_run()` tưởng stage đã xong.
  Đây là lỗ hổng thật của `state.py:47-49` — nó chỉ đếm số file trong thư mục.

## Định nghĩa hoàn thành — cũng là định nghĩa "dùng được"

- [ ] 3 chủ đề chạy trọn vẹn, không sửa code giữa chừng
- [ ] Cả 3 đều < $1.00 theo số đo thật trong ledger
- [ ] Cả 3 đều ra video 15–25 phút xem được
- [ ] `pytest` xanh
- [ ] `ruff check .` sạch
- [ ] README đủ để người khác (hoặc chính bạn 3 tháng sau) chạy lại từ đầu
- [ ] Giết pipeline giữa chừng rồi resume → chạy tiếp đúng chỗ, không hỏng dữ liệu
- [ ] Rút phích mạng giữa chừng → lỗi rõ ràng, không phải traceback trần

## Sau phase này

AutoVid dùng được. Việc tiếp theo tuỳ nhu cầu thật, không cần plan trước:

- Format thứ 2 (kiến trúc `prompts/<locale>/<format>/` đã mở sẵn) — làm khi bạn thật sự muốn
  loại video khác, không phải để chứng minh kiến trúc.
- A/B giọng đọc theo master plan §13.2.
- Hiệu ứng Ken Burns, chuyển cảnh, nhạc nền.
- Locale thứ 2 (`prompts/vi/educational/`).
