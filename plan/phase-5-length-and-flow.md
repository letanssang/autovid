# Phase 5 — Đủ dài & mạch lạc

> **Mục tiêu:** video chạm đúng 15–25 phút và xem liền mạch, không lặp ý, không cụt đầu cụt đuôi.
> **Kết quả kiểm chứng được:** thời lượng `output.mp4` nằm trong khoảng `target_duration_minutes`
> của `project.yaml`, và xem hết không thấy chỗ nào lặp lại điều đã nói.
> **Phụ thuộc:** Phase 2 (cần số đo thời lượng thật để biết đang thiếu bao nhiêu)
> **Ước lượng:** 2 buổi

## Vấn đề đang có (gap #9)

Cấu trúc hiện tại cứng hoàn toàn và **không liên quan gì tới thời lượng mục tiêu**:

- `s01_research.py` khai báo đúng 5 angle cố định cho mọi chủ đề
- `s02_outline.py:12` nhân đôi thành 10 section, luôn luôn
- `s03_script.py:26-27` chia đều thời lượng mục tiêu cho 10 section rồi ghi vào prompt

Prompt `script.md` có nói "~{{ target_duration_sec // 2 }} words", nhưng **không có gì kiểm tra
model có viết đủ hay không**. LLM nổi tiếng viết ngắn hơn yêu cầu. Kết quả thực tế nhiều khả năng
là video 6–8 phút trong khi bạn đặt mục tiêu 20.

Nghịch lý cần tránh: ép LLM viết dài bằng cách bảo "viết dài hơn" chỉ tạo ra văn nước.
Cách đúng là **cho nó nhiều thứ hơn để nói**, không phải bắt nói dai hơn về cùng một thứ.

## Việc cần làm

### 5.1 — Cấu trúc outline theo thời lượng mục tiêu

**File:** `core/stages/s02_outline.py`

Tính ngược từ mục tiêu thay vì cố định 10:

```
số section ≈ (phút mục tiêu × 150 từ/phút) / số từ mỗi section
```

Với ~350 từ/section (≈2.3 phút): 20 phút → ~13 section, 40 phút → ~26 section.

Nghĩa là `SECTIONS_PER_CHAPTER = 2` phải thành số tính được, và số angle cũng có thể cần
tăng cho video dài. Để LLM đề xuất angle theo chủ đề thay vì dùng 5 angle cứng — nhưng
**giữ 5 angle hiện tại làm fallback** khi LLM trả về rác.

Lưu ý: `RESEARCH_ANGLES` đang được `s02_outline.py` import từ `s01_research.py`, và ID section
sinh từ `slug(angle)`. Đổi sang angle động thì ID cũng động — kiểm lại toàn bộ chuỗi
`s02 → s03 → s04 → s05 → s06` vẫn tra cứu được nhau.

### 5.2 — Vòng lặp đo-và-sửa độ dài

**File:** `core/stages/s03_script.py`

Sau khi sinh mỗi section, đếm từ. Nếu lệch quá 25% so với mục tiêu:

- **Quá ngắn** → gọi lại với chỉ dẫn cụ thể: thêm ví dụ, thêm số liệu từ research, khai triển
  một điểm — **không** phải "viết dài hơn".
- **Quá dài** → yêu cầu cắt gọn giữ nguyên ý.
- Tối đa **2 lần thử lại** mỗi section, rồi chấp nhận và ghi cảnh báo vào `script.md`.

Chốt hàng rào cost: 13 section × tối đa 3 lần gọi = 39 request. Với route `s03_script` sang
Claude Sonnet thì đây là khoản chi lớn nhất của cả pipeline — cần đo lại ngân sách sau khi làm.

### 5.3 — Hook mở đầu và kết đóng

Video YouTube dài cần 30 giây đầu giữ chân người xem. Hiện script bắt đầu thẳng vào
section 1 của chương "Overview" — mở đầu nhạt.

**Prompt mới:** `prompts/en/educational/hook.md` và `prompts/en/educational/outro.md`.
Sinh ở `s03_script.py` như hai section đặc biệt (`id: "hook"`, `id: "outro"`), đứng ngoài
vòng lặp chương. Hook cần biết toàn bộ outline (để hứa hẹn được điều video sắp trả lời),
nên sinh **sau** các section khác dù nằm đầu.

### 5.4 — Chống lặp ý bằng knowledge spine

Spine đã có ở `s03_script.py:29-50` — hiện chỉ đưa vào **tiêu đề** các section trước.
Đủ để tránh lặp chủ đề, chưa đủ để tránh lặp *sự kiện*: hai section khác nhau vẫn có thể
cùng định nghĩa lại một thuật ngữ.

Nâng lên: sau mỗi section, rút 2–3 khái niệm/thuật ngữ đã giới thiệu, đưa vào spine cùng
tiêu đề. Prompt `script.md` đã có chỗ nhận (`{{ spine }}`), chỉ cần đổ nội dung phong phú hơn vào.

Đánh đổi: spine dài lên thì input token mỗi lần gọi tăng dần. Với 26 section cuối cùng thì
spine có thể tới vài trăm từ — vẫn rẻ, nhưng cần theo dõi trong ledger.

### 5.5 — Điều chỉnh mật độ beat

`s04_visual_plan.py:_split_beats` cắt beat theo dấu `". "`. Một section 350 từ → ~20 câu →
20 beat → mỗi beat ~7 giây. Hình đổi mỗi 7 giây với video 20 phút là **quá nhanh**, gây mệt mắt.

Gộp 2–3 câu thành một beat, nhắm 12–20 giây mỗi hình. Số beat giảm → cost visual ở Phase 4
cũng giảm theo, một mũi tên hai đích.

## Định nghĩa hoàn thành

- [ ] Thời lượng `output.mp4` nằm trong `target_duration_minutes` của `project.yaml`
- [ ] Đổi mục tiêu thành `[35, 40]`, chạy lại → video dài ra tương ứng (không phải vẫn 8 phút)
- [ ] 30 giây đầu có hook thật, không phải "Trong video này chúng ta sẽ tìm hiểu về..."
- [ ] Xem hết không gặp chỗ định nghĩa lại thuật ngữ đã giải thích
- [ ] Hình đổi trung bình mỗi 12–20 giây
- [ ] `script.md` in số từ thực tế vs mục tiêu từng section, và đánh dấu section phải thử lại

## Rủi ro

- **Đây là phase dễ đội cost nhất.** Vòng lặp thử lại có thể nhân đôi chi phí text. Đặt
  `budget.cap_usd` thấp khi thử (ví dụ $0.30) để `BudgetExceeded` bắt lỗi thay vì ví bạn.
- **Video dài hơn không tự nhiên nghĩa là tốt hơn.** Nếu ép 40 phút mà chủ đề chỉ đủ 15 phút
  nội dung, kết quả là văn nước — tệ hơn video 15 phút chặt chẽ. Cân nhắc để `s02` **từ chối**
  mục tiêu quá dài so với lượng research thu được, và báo lên gate thay vì cố nhồi.
