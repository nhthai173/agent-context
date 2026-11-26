---
name: excel-report-design
description: "Design standard for any spreadsheet a human will READ rather than compute with — operations reports, test/trial summaries, KPI reviews, status reports, analysis handoffs, anything going to a manager or client. Use this skill whenever producing an .xlsx (or .csv-derived report) whose audience is a reader, even if the user only says 'make a report', 'summarize this data', 'export the results', or 'put this in Excel'. Layers presentation, hierarchy, and charting rules on top of the base xlsx skill. Do NOT use for financial models, calculators, data-entry templates, or raw data dumps — those follow the xlsx skill alone."
---

# Excel report design

The base `xlsx` skill covers correctness — formulas, recalc, openpyxl mechanics. Follow it.
This skill covers whether the reader will actually absorb the report and treat it as valuable.

**The failure mode this exists to prevent:** a report whose content is genuinely good but
lands flat — a grid of 15 metrics with equal visual weight, no charts, default gridlines, prose
crammed into cells. The reader has to do all the analytical work themselves, so it reads as a
data dump with notes. Correct content plus flat presentation still reads as low-value.

## The one rule everything else serves

**Say something.** A report that only presents data makes the reader find the story. A report
that states its conclusion first, then supports it, does the work for them.

Before writing a single cell, answer: *if the reader remembers exactly one sentence from this,
what should it be?* That sentence goes in row 4, in the accent color, at 12–13pt. Everything
below it is evidence.

Bad: "Báo cáo vận hành AMR — 8 lần chạy, 7 thành công."
Good: "Nút thắt không nằm ở tốc độ — 148/270 giây mỗi chu kỳ AMR đứng yên."

The first is a label. The second is a finding a manager can act on. Write the report in the
language of the source data and the audience, not English by default.

## Mandatory layout — overview sheet

Every multi-sheet report opens with an overview sheet built in this order. Detail sheets come
after and may be denser, but the overview is what gets screenshotted into a chat and pasted
into a slide, so it carries the weight.

```
Column A       spacer, width 2 — the left margin. Content starts in column B.
Row 1          spacer, height 6
Row 2          TITLE — 20pt bold, dark neutral (not the accent color)
Row 3          Context line — 9pt gray: scope, date range, sample size, source
Row 4          HEADLINE FINDING — 12pt, accent color, one sentence
Row 5          spacer
Rows 6–9       KPI CARD STRIP — 3 to 5 cards, never more
Row 10         spacer
Row 11+        Sections, each: header band → chart or table → one-line takeaway
```

A KPI card is a merged block: label (9pt gray) above, number (26–32pt bold) in the middle,
qualifier (9pt gray, e.g. "trên 8 lần chạy") below, with a 3px accent-color top border. Cards
are for the numbers that decide something — not the first five metrics in your table.

Every section ends with a takeaway line in italic gray: *what this means*. If a section has no
takeaway, it probably belongs on a detail sheet instead.

## Visualize before you tabulate

For each thing the report says, pick the form that makes the point fastest:

| The point you're making | Use |
|---|---|
| Composition — where the time/cost/volume goes | Horizontal stacked bar, 100% |
| Comparison across runs, days, machines, SKUs | Horizontal bar, sorted by value |
| Spread and outliers across repeated trials | Dot/strip plot, or bar with min–max range |
| Change over time | Line chart — but only with 6+ points |
| Step-by-step breakdown that sums to a total | Waterfall, or a sorted horizontal bar |
| One number vs. its target | Bullet chart, or a bar with a target line |
| A value inside a table row | In-cell data bar (conditional formatting) |

Never use pie charts, doughnuts, 3D, gauges, or gradient fills. Never let a report of
comparative or time-series data ship with zero charts — that is the single strongest signal of
a low-effort report.

Chart hygiene: one idea per chart · no gridlines · no legend when direct labels fit · no chart
border · sort bars by value unless the category has a natural order · start bar axes at zero ·
put the takeaway in the chart title ("Đứng yên chiếm 55% chu kỳ"), not the subject
("Phân bổ thời gian").

## Color is semantic, never decorative

One accent color plus a neutral gray ramp. That is the whole palette.

- **Accent** — the headline finding, KPI card borders, section header bands, primary chart series
- **Gray 700** — body text · **Gray 500** — labels and secondary text · **Gray 200** — rules and table separators
- **Red** — reserved *exclusively* for problems: failures, breaches, anomalies. If red appears more than 2–3 times, it has stopped meaning anything.
- **Green** — only if the report genuinely has a good/bad axis. Otherwise skip it.

Alternating yellow and green row fills across a metrics table is the classic tell of a report
that was formatted rather than designed: the color carries no information, so the eye learns to
ignore it and nothing stands out. If a fill can't be explained in a legend, remove it.

## Typography and space

- One font family throughout. Three sizes only: 20pt title / 11pt body / 9pt labels.
- Row height 20–22 for table rows, 16 for label rows. Cramped rows read as cheap.
- **Turn gridlines off** (`ws.sheet_view.showGridLines = False`) and fill the used range white. This one change does more for perceived quality than anything else — it turns a spreadsheet into a document.
- **No cell borders.** Separate table rows with a single Gray 200 bottom border, and give header rows a heavier bottom rule. Boxing every cell is visual noise.
- Blank spacer rows between sections. Whitespace is what makes the reader believe the layout was deliberate.

## Numbers

- Embed the unit in the number format, then delete the "Unit" column: `0.0" giây"`, `0.000" m/s"`, `0.0%`, `#,##0" pcs"`.
- Consistent decimals down a column. Right-align all numerics, left-align text.
- Percentages stored as fractions (`0.548` renders `54.8%`).
- Never leave a metrics column half-empty. If min/max only applies to some rows, either drop the column or replace it with a range string (`254.8 – 301.3`) or an in-cell bar.

## Prose does not go in cells

A 3-line paragraph wrapped inside a cell is the second-strongest tell of a low-effort report.

- Annotation column: **one line, ≤ 90 characters.** Trim to the insight.
- Anything longer becomes a "Nhận xét / Notes" block below the section, in merged cells across the full width, at 10pt.
- Methodology, assumptions, and data provenance get their own sheet at the end — not footnotes squeezed into column F.

## Multi-sheet reports

Sheet order runs general → specific: `Overview` → per-topic detail → `Method & data`. Tab colors:
accent for the overview, neutral for the rest. Freeze panes below every table header
(`ws.freeze_panes`).

Set up printing before delivering — most readers will see a PDF, not the workbook. Landscape,
fit to one page wide, print area set, sheet name and date in the footer. A report that breaks
across four ragged pages when printed undoes the layout work.

## Before delivering — checklist

Run through this literally. Each item corresponds to a real failure seen in practice.

1. Is there a one-sentence conclusion above the fold, in the accent color?
2. Are there 3–5 KPI cards, and are they the numbers that *decide* something?
3. Is there at least one chart, and does its title state the finding?
4. Gridlines off? Cell borders removed? Left margin column present?
5. Is every fill color explainable? Is red used only for problems?
6. Any cell containing more than one line of prose?
7. Any column that is more than half empty?
8. Does each section end with a takeaway line?
9. Print setup done — landscape, one page wide, footer?
10. Screenshot the top of the overview sheet. Would a manager, seeing only that, know what to do next?

If item 10 fails, the rest of the polish will not save it. Go back to the headline.

## Implementation

Read `references/openpyxl-recipes.md` for working code: the palette constants, KPI card builder,
section header, table styling, native charts vs. matplotlib images, data bars, number formats,
and print setup. Copy the helpers into the build script rather than reinventing them each time.
