"""Download a finished assignment as Word (.docx), or its tables as Excel (.xlsx).

AI deliverables are written in simple Markdown (headings, bullets, **bold**,
tables). These helpers turn that into real Office files without any AI call.
"""
import io
import re
from datetime import datetime

_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_NUMBER = re.compile(r"^\s*(?:GH[S₵¢]|GHS|USD|\$|₵)?\s*\(?-?[\d,]+(?:\.\d+)?\)?\s*(%|k|m)?\s*$", re.I)


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_blocks(text):
    """Split Markdown into ('heading', level, text) / ('bullet', level, text) / ('number', text)
    / ('table', rows) / ('para', text) blocks."""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    blocks, i = [], 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("|") and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1]):
            rows = [_cells(line)]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_cells(lines[i])); i += 1
            width = max(len(r) for r in rows)
            blocks.append(("table", [r + [""] * (width - len(r)) for r in rows]))
            continue
        if not stripped:
            i += 1; continue
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            blocks.append(("heading", len(m.group(1)), m.group(2).strip("# ").strip()))
        elif re.match(r"^[-*•]\s+", stripped):
            level = 1 if (len(line) - len(line.lstrip())) >= 2 else 0
            blocks.append(("bullet", level, re.sub(r"^[-*•]\s+", "", stripped)))
        elif re.match(r"^\d+[.)]\s+", stripped):
            blocks.append(("number", re.sub(r"^\d+[.)]\s+", "", stripped)))
        elif re.fullmatch(r"\*\*[^*]+\*\*:?", stripped):
            blocks.append(("heading", 3, stripped.strip("*:").strip()))
        elif re.fullmatch(r"[-_*]{3,}", stripped):
            pass
        else:
            blocks.append(("para", stripped))
        i += 1
    return blocks


def tables_in(text):
    return [b[1] for b in parse_blocks(text) if b[0] == "table"]


def _add_runs(paragraph, text):
    """Support **bold** and *italic* inside a line."""
    for part in re.split(r"(\*\*[^*]+\*\*|\*[^*\s][^*]*\*)", text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            paragraph.add_run(part[2:-2]).bold = True
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            paragraph.add_run(part[1:-1]).italic = True
        else:
            paragraph.add_run(part)


def to_docx(task, business_name):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"; style.font.size = Pt(11)
    for name in ("Heading 1", "Heading 2", "Heading 3"):
        doc.styles[name].font.color.rgb = RGBColor(0x0F, 0x2A, 0x55)

    small = doc.add_paragraph()
    run = small.add_run(f"{business_name} · prepared with AI Workforce")
    run.font.size = Pt(9); run.font.color.rgb = RGBColor(0x5A, 0x64, 0x78)
    doc.add_heading(task.title, level=0)
    meta = doc.add_paragraph()
    when = task.completed_at or task.created_at or datetime.now()
    r = meta.add_run(f"{when:%d %B %Y} · Draft produced by AI. Check all facts and figures before use.")
    r.italic = True; r.font.size = Pt(9); r.font.color.rgb = RGBColor(0x5A, 0x64, 0x78)

    for block in parse_blocks(task.final_output):
        kind = block[0]
        if kind == "heading":
            doc.add_heading(block[2], level=min(3, max(1, block[1])))
        elif kind == "bullet":
            _add_runs(doc.add_paragraph(style="List Bullet 2" if block[1] else "List Bullet"), block[2])
        elif kind == "number":
            _add_runs(doc.add_paragraph(style="List Number"), block[1])
        elif kind == "table":
            rows = block[1]
            table = doc.add_table(rows=len(rows), cols=len(rows[0]))
            table.style = "Light Grid Accent 1"
            for ri, row in enumerate(rows):
                for ci, value in enumerate(row):
                    cell = table.cell(ri, ci)
                    cell.text = ""
                    p = cell.paragraphs[0]
                    _add_runs(p, value)
                    if ri == 0:
                        for run in p.runs:
                            run.bold = True
                    elif _NUMBER.match(value or ""):
                        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            doc.add_paragraph()
        else:
            _add_runs(doc.add_paragraph(), block[1])

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def _to_number(value):
    """'GHS 1,200' -> 1200; '15%' -> 0.15; leaves text alone. Returns (value, number_format)."""
    raw = (value or "").replace("*", "").strip()
    if not raw or not _NUMBER.match(raw):
        return raw, None
    negative = raw.startswith("(") and raw.endswith(")") or "-" in raw
    digits = re.sub(r"[^\d.]", "", raw)
    try:
        number = float(digits)
    except ValueError:
        return raw, None
    number = -number if negative else number
    lowered = raw.lower()
    if lowered.endswith("%"):
        return number / 100, "0%" if number == int(number) else "0.0%"
    if lowered.endswith("k"):
        number *= 1000
    elif lowered.endswith("m"):
        number *= 1_000_000
    currency = "GHS " if re.match(r"^\s*(gh|₵)", lowered) else ("$" if re.match(r"^\s*(usd|\$)", lowered) else "")
    decimals = "." in digits and not digits.endswith(".00")
    fmt = ("#,##0.00" if decimals else "#,##0")
    return (int(number) if number == int(number) and not decimals else number), (f'"{currency}"{fmt}' if currency else fmt)


def to_xlsx(task, business_name):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    tables = tables_in(task.final_output)
    wb = Workbook()
    wb.remove(wb.active)
    header_fill = PatternFill("solid", fgColor="0F2A55")
    for n, rows in enumerate(tables, start=1):
        ws = wb.create_sheet(f"Table {n}")
        ws.append([f"{task.title}"]); ws["A1"].font = Font(bold=True, size=13, color="0F2A55")
        ws.append([f"{business_name} · AI Workforce draft — check figures before use"])
        ws["A2"].font = Font(italic=True, size=9, color="5A6478")
        ws.append([])
        start = 4
        for ri, row in enumerate(rows):
            for ci, value in enumerate(row, start=1):
                cell = ws.cell(row=start + ri, column=ci)
                if ri == 0:
                    cell.value = value.replace("*", "")
                    cell.font = Font(bold=True, color="FFFFFF"); cell.fill = header_fill
                    cell.alignment = Alignment(vertical="center", wrap_text=True)
                else:
                    number, fmt = _to_number(value)
                    cell.value = number
                    if fmt:
                        cell.number_format = fmt
                    if "**" in (value or ""):
                        cell.font = Font(bold=True)
        for ci in range(1, len(rows[0]) + 1):
            width = max(len(str(r[ci - 1])) for r in rows) + 2
            ws.column_dimensions[get_column_letter(ci)].width = min(max(width, 10), 60)
        ws.freeze_panes = ws.cell(row=start + 1, column=1)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
