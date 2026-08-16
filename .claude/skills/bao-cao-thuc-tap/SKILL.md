---
name: "bao-cao-thuc-tap"
description: "Use when writing, drafting, expanding, reviewing or exporting a Vietnamese internship report (báo cáo thực tập thực tế / kiến tập) for the SIU K17 format — Computer Science framing, verified data only, figure placeholders, peer-reviewed sources, Markdown draft then an editable .docx. Triggers on 'báo cáo thực tập', 'báo cáo kiến tập', 'internship report', or work on Bao_cao_*.md."
---

# Báo cáo thực tập thực tế (K17)

Write the report in Markdown, verify every fact in it, then build an editable .docx.
The formatting rules come from the faculty guideline and are non-negotiable. The five
rules below are the author's, and they override any default drafting habit.

## The five standing rules

**1. Write it as a Computer Science student.**
The author is a Khoa học Máy tính major (AI specialisation). The report must read like
engineering work, not like a business internship diary. That means: the theory in 1.1 is
CS theory that was actually applied; Chương 3 covers problem statement, data model,
architecture, algorithms (with complexity where it matters), implementation decisions and
their trade-offs, testing, and deployment; results are measured, not asserted. Name the
courses the knowledge came from when 4.3 asks for the theory-practice link.

**2. Never invent a number, a date, a name, or a result.**
Every figure in the report must trace to one of: a query run against the real database, a
test suite run, a benchmark measured on the spot, a fact read out of the source code, a
git log, or a document the company provided. Record where it came from in an HTML comment
next to it in the Markdown — comments do not print:

```markdown
<!-- nguồn: SELECT vehicle_type, COUNT(*) FROM vehicles GROUP BY vehicle_type — chạy 2026-08-16 -->
Đội xe gồm 36 phương tiện, trong đó 32 xe tải thùng và 4 xe container.
```

If a number is needed and cannot be verified, do not estimate and do not soften it into
vague prose. Leave a marker and move on:

```markdown
[[CẦN SỐ LIỆU: chi phí nhiên liệu trung bình/tháng, lấy từ sổ theo dõi phòng kế toán]]
```

It renders in the .docx as a bold bracketed note, so nothing ships unnoticed. Percentage
improvements are the most dangerous claim in this genre: a "giảm 80%" needs a measured
before and a measured after, both cited. Without both, state what was built and what was
measured, and say the baseline was not recorded.

**3. Every diagram, chart, and screenshot is a placeholder.**
Do not generate images. Write the caption and let the builder draw a bordered box:

```markdown
![Hình 2.1. Sơ đồ tổ chức Công ty Thành Trung](placeholder)
[[CHO TRONG: Hình 3.2. Kiến trúc hệ thống Fleet Fuel Management]]
```

Both render as an empty framed box with the caption underneath, sized for a hand-drawn or
later-inserted figure. Keep a running figure/table register so Danh mục hình ảnh, sơ đồ,
bảng biểu can be filled in at the end. Exception: if the author supplies a real image file,
reference its path and it gets embedded.

**4. Be dense — many figures, tables, and citations.**
Aim for at least two figures and one table per body chapter, and put real structured
content in the tables (schema fields, API endpoints, test suites and their counts,
before/after measurements, hardware/software stack). Tables built from source code or the
database are the cheapest way to add verified substance. Prose that could have been a table
usually should have been.

**5. Sources must be academic and verified online.**
Use `WebSearch` to find and confirm every reference before citing it — title, authors,
venue, year, DOI or a stable URL. Never cite from memory; a plausible-looking citation that
does not exist is the single worst thing that can appear in this report. Prefer
peer-reviewed journals and conference proceedings (IEEE, ACM, Springer, Elsevier,
INFORMS). Vendor documentation, standards, and the company's own materials may be cited,
but as a separate class from the academic sources — not as a substitute for them. Target
12–20 references, every one of them cited somewhere in the text, IEEE numbered style.

## Order of work

### 1. Gather facts

Ask for what's missing, in one batch, and mine the codebase for the rest. The minimum set:

- Đơn vị thực tập: legal name, address, year founded, ngành nghề, headcount, phòng ban
- Thời gian thực tập (từ — đến), phòng ban, người hướng dẫn tại đơn vị
- Giảng viên hướng dẫn, MSSV, ngành, khóa
- Công việc được giao, and the department's actual workflow
- Measurable results, each with its provenance
- What did **not** work — mục 3.4 requires it and markers read that section closely

When the system being reported on is in the folder, prefer measuring over asking: run the
queries, run the test suites, read the schema, check the git log for dates. Those numbers
are defensible in a viva; remembered ones are not.

### 2. Plan against the page budget

State the outline with target page counts before drafting, and get it approved.

| Phần | Số trang | Mục |
|---|---|---|
| MỞ ĐẦU | 3–6 | 1. Lý do chọn đề tài · 2. Mục tiêu nghiên cứu · 3. Phương pháp, đối tượng, phạm vi · 4. Nội dung nghiên cứu |
| CHƯƠNG 1: GIỚI THIỆU TỔNG QUAN | 5–10 | 1.1. Tổng quan cơ sở lý thuyết · 1.2. Chủ đề thực tập · 1.3. Các kết quả, mục tiêu kỳ vọng |
| CHƯƠNG 2: MÔ TẢ CƠ QUAN THỰC TẬP THỰC TẾ | 8–16 | 2.1. Thông tin cơ quan · 2.2. Lịch sử hình thành · 2.3. Cơ cấu tổ chức **(sơ đồ)** · 2.4. Chức năng, nhiệm vụ, ngành nghề · 2.5. Quy mô nhân sự, năng lực SXKD · 2.6. Nội dung khác |
| CHƯƠNG 3: NỘI DUNG THỰC TẬP THỰC TẾ | 8–16 | 3.1. Mô tả công việc được giao · 3.2. Mục tiêu, vấn đề cần giải quyết · 3.3. Quy trình, phương pháp **(sơ đồ)** · 3.4. Kết quả đạt được · 3.5. Phân tích và xử lý số liệu |
| CHƯƠNG 4: TỰ ĐÁNH GIÁ VÀ NHẬN XÉT | 5–10 | 4.1. Nhận thức của bản thân · 4.2. Học hỏi từ nơi thực tập · 4.3. Đánh giá mối liên hệ giữa lý thuyết và thực tiễn |
| KẾT LUẬN VÀ KIẾN NGHỊ | 1–2 | Tóm tắt, điểm mạnh/hạn chế, kiến nghị |

Body must clear 30 pages. The usual failure is a padded Chương 1 and a thin Chương 3 — for
a CS report it should be the other way round.

Full structure, per-section content requirements and the submission checklist are in
`reference/cau-truc-va-dinh-dang.md`. Read it rather than working from memory.

### 3. Draft in Markdown

Copy `assets/mau-draft.md`, fill the YAML block, write one chapter at a time and show each
before moving on. Use the guideline's exact section wording; subsections numbered
`1.4.3.1. Tên mục`.

### 4. Check the prose

Invoke the `human-markdown` skill and apply it, then the Vietnamese pass in
`reference/van-phong-tieng-viet.md` — the Vietnamese tells (`đóng vai trò quan trọng`,
trailing `góp phần…`, marketing register in Chương 2, `không chỉ… mà còn`) are the ones
that actually show up here. Both have grep lists; run them.

Then: does every paragraph in Chương 2–4 contain at least one checkable fact? Cut the ones
that don't.

### 5. Build the .docx

```bash
python .claude/skills/bao-cao-thuc-tap/scripts/build_report_docx.py \
    Bao_cao_thuc_tap.md -o "Bao_cao_thuc_tap_<HoTen>.docx" --pagecount
```

The .docx is the deliverable and stays editable in Word; keep the .md alongside as the
source of truth and rebuild after edits rather than editing the .docx repeatedly.

The script applies the format spec (A4, Times New Roman 13, 1.5 spacing, margins
3.5/2/2/2 cm, page number centered in the header, roman front matter, arabic restarting at
1 on MỞ ĐẦU), builds the cover from the YAML block, inserts blank signable nhận xét pages,
renders placeholder boxes and `[[CẦN SỐ LIỆU]]` markers, and emits a live TOC field.
`--pagecount` renders through LibreOffice and checks the 30-page floor.

### 6. Verify, then hand over

- Convert to PDF and look at the rendered pages — cover, the roman→arabic switch, a body
  page, and every placeholder box. Reading the XML does not catch layout problems.
- Grep the .md for `[[CẦN SỐ LIỆU` and list what's still outstanding for the author.
- Confirm every citation was verified online and every reference is cited in the text.
- Tell the author to press Ctrl+A then F9 in Word to populate the TOC.
- Walk the checklist at the end of `reference/cau-truc-va-dinh-dang.md`.

## Seed bibliography (verified 2026-08-16)

Starting points only — verify again and expand by topic. Full IEEE formatting rules are in
the reference doc.

- G. B. Dantzig and J. H. Ramser, "The truck dispatching problem," *Management Science*,
  vol. 6, no. 1, pp. 80–91, 1959, doi: 10.1287/mnsc.6.1.80. — the origin of the VRP.
- P. Toth and D. Vigo, Eds., *The Vehicle Routing Problem*. Philadelphia, PA: SIAM, 2002.
  — standard reference volume; later editions exist, check which one is being cited.
- J. Barceló *et al.*, "Rich vehicle routing problem: A survey," *ACM Computing Surveys*,
  vol. 47, no. 2, 2014, doi: 10.1145/2666003. — confirm the author list before citing.
- M. Barrena *et al.*, "Interpretable machine learning models for predicting and explaining
  vehicle fuel consumption anomalies," *Engineering Applications of Artificial
  Intelligence*, 2022. — verify authors and volume; closest published work to the fuel
  anomaly component.
- F. Reclus and K. Drouard, "Geofencing for fleet & freight management," in *Proc. 9th Int.
  Conf. Intelligent Transport Systems Telecommunications (ITST)*, IEEE, 2009. — geofencing
  in freight; pair with a point-in-polygon/ray-casting source for the algorithm itself.

## Things that go wrong

- **Chương 2 reads like the company's marketing page.** It usually is. Convert to facts and
  cite the source.
- **A number appears with no provenance comment.** Treat that as a bug; find the source or
  turn it into a `[[CẦN SỐ LIỆU]]` marker.
- **Numbers in the body don't match phụ lục.** Check both against the source.
- **A citation was written from memory.** Search for it; if it doesn't exist, delete it.
- **TOC page numbers are stale.** They only update on F9 in Word.
- **The body is 22 pages.** Expand 3.3–3.5 with architecture, schema tables, algorithm
  descriptions, test results and screenshots in phụ lục — not with padding sentences.
