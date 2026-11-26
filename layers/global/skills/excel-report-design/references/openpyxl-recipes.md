# openpyxl recipes for report design

Working code for the standard in SKILL.md. Copy the helpers into the build script.

Contents: [Palette](#palette) · [Sheet setup](#sheet-setup) · [Title block](#title-block) ·
[KPI cards](#kpi-cards) · [Section headers](#section-headers) · [Tables](#tables) ·
[Data bars & in-cell bars](#data-bars--in-cell-bars) · [Charts](#charts) ·
[Number formats](#number-formats) · [Print setup](#print-setup) · [Verify](#verify)

## Palette

Pick one accent and keep the gray ramp fixed. Swap `ACCENT` per project or brand.

```python
ACCENT      = "1F4E79"   # deep blue — headline, KPI borders, section bands, primary series
ACCENT_SOFT = "DCE6F1"   # 15% tint — band fills, alternating emphasis if truly needed
GRAY_900    = "1A1A1A"   # title
GRAY_700    = "404040"   # body
GRAY_500    = "808080"   # labels, context lines, takeaways
GRAY_200    = "E0E0E0"   # rules, table separators
RED         = "C00000"   # problems ONLY
WHITE       = "FFFFFF"
FONT        = "Arial"    # or Aptos / Inter if the target machine has it
```

## Sheet setup

Do this first on every sheet — it is what turns a spreadsheet into a document.

```python
from openpyxl.styles import PatternFill

def prepare_sheet(ws, last_col="H", last_row=200, margin_width=2):
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = margin_width          # left margin
    white = PatternFill("solid", fgColor=WHITE)
    for row in ws[f"A1:{last_col}{last_row}"]:              # kill the grid entirely
        for cell in row:
            cell.fill = white
```

Column widths: set them explicitly. Label column 34–40, numeric columns 12–14, annotation
column 60–70. Never rely on autofit.

## Title block

```python
from openpyxl.styles import Font, Alignment

def title_block(ws, title, context, headline, col="B", last_col="H"):
    ws.row_dimensions[1].height = 6
    ws[f"{col}2"] = title
    ws[f"{col}2"].font = Font(name=FONT, size=20, bold=True, color=GRAY_900)
    ws.row_dimensions[2].height = 30

    ws[f"{col}3"] = context          # "AMR071 · bản đồ BE · 24/08/2026 14:30–16:56 · 8 lần chạy"
    ws[f"{col}3"].font = Font(name=FONT, size=9, color=GRAY_500)

    ws.merge_cells(f"{col}4:{last_col}4")
    ws[f"{col}4"] = headline         # the one sentence the reader should remember
    ws[f"{col}4"].font = Font(name=FONT, size=12, bold=True, color=ACCENT)
    ws[f"{col}4"].alignment = Alignment(vertical="center", wrap_text=False)
    ws.row_dimensions[4].height = 24
    ws.row_dimensions[5].height = 8
```

## KPI cards

Each card spans 2 columns × 4 rows. Write only the top-left anchor of a merged range.

```python
from openpyxl.styles import Border, Side
from openpyxl.utils import get_column_letter

def kpi_card(ws, start_col, row, label, value, qualifier, fmt=None, alert=False):
    """start_col is a 1-based index. Occupies rows `row`..`row+3`, 2 columns wide."""
    c1, c2 = get_column_letter(start_col), get_column_letter(start_col + 1)
    color = RED if alert else ACCENT

    ws.merge_cells(f"{c1}{row}:{c2}{row}")                    # label
    ws[f"{c1}{row}"] = label
    ws[f"{c1}{row}"].font = Font(name=FONT, size=9, color=GRAY_500)
    ws[f"{c1}{row}"].alignment = Alignment(horizontal="center", vertical="center")
    ws[f"{c1}{row}"].border = Border(top=Side(style="thick", color=color))

    ws.merge_cells(f"{c1}{row+1}:{c2}{row+2}")                # the number
    ws[f"{c1}{row+1}"] = value
    ws[f"{c1}{row+1}"].font = Font(name=FONT, size=28, bold=True, color=color)
    ws[f"{c1}{row+1}"].alignment = Alignment(horizontal="center", vertical="center")
    if fmt:
        ws[f"{c1}{row+1}"].number_format = fmt

    ws.merge_cells(f"{c1}{row+3}:{c2}{row+3}")                # qualifier
    ws[f"{c1}{row+3}"] = qualifier
    ws[f"{c1}{row+3}"].font = Font(name=FONT, size=9, color=GRAY_500)
    ws[f"{c1}{row+3}"].alignment = Alignment(horizontal="center", vertical="top")

    for r in (row, row+1, row+2, row+3):
        ws.row_dimensions[r].height = 30 if r in (row+1, row+2) else 16
```

Leave one empty spacer column between cards. Use `alert=True` for a card the reader must not
miss — at most one per report.

## Section headers

A left accent rule reads lighter than a filled band and does not fight the KPI cards.

```python
def section_header(ws, row, number, text, col="B", last_col="H"):
    ws.merge_cells(f"{col}{row}:{last_col}{row}")
    cell = ws[f"{col}{row}"]
    cell.value = f"{number} · {text}"
    cell.font = Font(name=FONT, size=12, bold=True, color=ACCENT)
    cell.alignment = Alignment(vertical="center")
    cell.border = Border(bottom=Side(style="medium", color=ACCENT))
    ws.row_dimensions[row].height = 24

def takeaway(ws, row, text, col="B", last_col="H"):
    ws.merge_cells(f"{col}{row}:{last_col}{row}")
    ws[f"{col}{row}"] = text
    ws[f"{col}{row}"].font = Font(name=FONT, size=10, italic=True, color=GRAY_500)
    ws[f"{col}{row}"].alignment = Alignment(vertical="center", wrap_text=True)
```

## Tables

No boxes. A heavier rule under the header, a hairline under each row.

```python
def style_table(ws, first_row, last_row, first_col, last_col, numeric_cols=()):
    hair   = Border(bottom=Side(style="thin", color=GRAY_200))
    header = Border(bottom=Side(style="medium", color=GRAY_700))
    for c in range(first_col, last_col + 1):
        cell = ws.cell(row=first_row, column=c)
        cell.font = Font(name=FONT, size=10, bold=True, color=GRAY_700)
        cell.border = header
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[first_row].height = 22

    for r in range(first_row + 1, last_row + 1):
        ws.row_dimensions[r].height = 20
        for c in range(first_col, last_col + 1):
            cell = ws.cell(row=r, column=c)
            cell.font = Font(name=FONT, size=10, color=GRAY_700)
            cell.border = hair
            cell.alignment = Alignment(
                horizontal="right" if c in numeric_cols else "left",
                vertical="center",
            )
```

Freeze below the header: `ws.freeze_panes = ws.cell(row=first_row + 1, column=first_col)`.

## Data bars & in-cell bars

Data bars turn a column of percentages into something the eye compares without reading.

```python
from openpyxl.formatting.rule import DataBarRule

ws.conditional_formatting.add(
    "D12:D26",
    DataBarRule(start_type="num", start_value=0,
                end_type="num", end_value=1,          # fractions for a % column
                color=ACCENT, showValue=True),
)
```

openpyxl has **no sparkline API**. When a per-row trend matters, either use a data bar, write a
text bar with `=REPT("▮", ROUND(D12*20,0))` in a helper column, or generate one small matplotlib
strip image per row (expensive — usually not worth it).

## Charts

**Native openpyxl charts** — use when the data may be edited later and the chart must follow.

```python
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.drawing.line import LineProperties
from openpyxl.chart.shapes import GraphicalProperties

chart = BarChart()
chart.type = "bar"                      # horizontal bars
chart.grouping = "percentStacked"
chart.overlap = 100
chart.title = "Đứng yên chiếm 55% chu kỳ"     # the finding, not the subject
chart.height, chart.width = 7, 16              # cm
chart.legend.position = "b"
chart.y_axis.majorGridlines = None             # no gridlines
chart.x_axis.majorGridlines = None

data = Reference(ws, min_col=3, max_col=4, min_row=11, max_row=19)
cats = Reference(ws, min_col=2, min_row=12, max_row=19)
chart.add_data(data, titles_from_data=True)
chart.set_categories(cats)

chart.series[0].graphicalProperties = GraphicalProperties(solidFill=ACCENT)
chart.series[1].graphicalProperties = GraphicalProperties(solidFill=GRAY_200)
for s in chart.series:
    s.graphicalProperties.line = LineProperties(noFill=True)   # no bar outlines
chart.dataLabels = DataLabelList(); chart.dataLabels.showVal = True

ws.add_chart(chart, "B30")
```

**matplotlib images** — use for a fixed-period report (a trial summary, a monthly review) where
the numbers will not change. Control over typography, annotation, and spacing is far better, and
the result looks materially more designed than a native Excel chart.

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from openpyxl.drawing.image import Image as XLImage

fig, ax = plt.subplots(figsize=(7.5, 3.2), dpi=200)
ax.barh(labels, values, color=f"#{ACCENT}", height=0.6)
ax.invert_yaxis()                                   # largest at top
for spine in ("top", "right", "left"):
    ax.spines[spine].set_visible(False)
ax.tick_params(left=False)
ax.set_xlabel("")
for i, v in enumerate(values):                      # direct labels, no axis clutter
    ax.text(v, i, f" {v:.1f}", va="center", fontsize=9, color=f"#{GRAY_700}")
ax.set_title("Bước 4 chiếm 74% thời gian chu kỳ", loc="left",
             fontsize=12, fontweight="bold", color=f"#{GRAY_900}", pad=12)
fig.tight_layout()
fig.savefig("chart.png", transparent=True)
plt.close(fig)

ws.add_image(XLImage("chart.png"), "B30")
```

Keep the PNG file alive on disk until `wb.save()` runs — openpyxl reads it at save time.
For non-Latin text, set a font that has the glyphs:
`matplotlib.rcParams["font.family"] = "DejaVu Sans"`.

## Number formats

```python
'0.0" giây"'      # 270.3 giây          — unit inside the format, so drop the Unit column
'0.000" m/s"'     # 0.176 m/s
'0.0%'            # store 0.548 → renders 54.8%
'#,##0'           # 1,234
'0.0"%"'          # only if the value is already 54.8 rather than 0.548
'#,##0;[Red]-#,##0;–'   # zeros as en-dash, negatives red
'0.0" s"" (""'    # avoid — escaping gets fragile; keep formats simple
```

Apply per column, not per cell, and keep decimals consistent down the column.

## Print setup

```python
ws.page_setup.orientation = "landscape"
ws.page_setup.fitToWidth = 1
ws.page_setup.fitToHeight = 0
ws.sheet_properties.pageSetUpPr.fitToPage = True
ws.print_area = "A1:H60"
ws.oddFooter.right.text = "&A · &D · Trang &P/&N"
ws.oddFooter.right.size = 8
ws.sheet_properties.tabColor = ACCENT        # overview sheet only
```

## Verify

`recalc.py` from the xlsx skill proves the formulas evaluate. It says nothing about layout, so
also render the result and look at it:

```bash
soffice --headless --convert-to pdf output.xlsx --outdir /tmp/preview
pdftoppm -png -r 110 -f 1 -l 1 /tmp/preview/output.pdf /tmp/preview/page
```

Then view `/tmp/preview/page-1.png` and run the SKILL.md checklist against what is actually on
screen. Merged-cell overflow, clipped titles, charts landing on top of tables, and a headline
that wraps out of view are all invisible in code and obvious in the render.
