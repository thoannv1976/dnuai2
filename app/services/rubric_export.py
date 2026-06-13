"""Xuất rubric chấm điểm ra file Excel (.xlsx) và Word (.docx) để tải về."""
from __future__ import annotations

import io


def _graded_parts(rubric: dict):
    return [(k, p) for k, p in rubric["parts"].items() if p.get("graded")]


def rubric_to_xlsx(rubric: dict) -> bytes:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = openpyxl.Workbook()
    head_fill = PatternFill("solid", fgColor="EA580C")
    head_font = Font(bold=True, color="FFFFFF")
    wrap = Alignment(wrap_text=True, vertical="top")

    # Sheet 1: Tổng quan
    ws = wb.active
    ws.title = "Tổng quan"
    ws.append([f"RUBRIC ĐÁNH GIÁ NĂNG LỰC ỨNG DỤNG AI — DNU 2026 (phiên bản {rubric.get('version', '')})"])
    ws.merge_cells("A1:D1")
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([])
    hdr = ["Phần", "Nội dung đánh giá", "Trọng số", "Điểm tối đa"]
    ws.append(hdr)
    for c in ws[ws.max_row]:
        c.fill, c.font = head_fill, head_font
    for k, p in rubric["parts"].items():
        graded = p.get("graded")
        ws.append([k, p["name"], f"{p['weight']}%" if graded else "–",
                   p["max_score"] if graded else "Đạt/Không đạt"])
    ws.append(["", "TỔNG CỘNG", "100%", sum(p["max_score"] for _, p in _graded_parts(rubric))])
    ws[ws.max_row][1].font = Font(bold=True)
    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 60
    ws.column_dimensions["C"].width = 10
    ws.column_dimensions["D"].width = 14

    # Sheet 2: Tiêu chí chi tiết
    ws2 = wb.create_sheet("Tiêu chí chấm")
    cols = ["Phần", "Mã tiêu chí", "Tên tiêu chí", "Điểm tối đa", "Hướng dẫn chấm / mức chất lượng"]
    ws2.append(cols)
    for c in ws2[1]:
        c.fill, c.font = head_fill, head_font
    for k, p in _graded_parts(rubric):
        for crit in p["criteria"]:
            ws2.append([k, crit["id"], crit["name"], crit["max"], crit.get("guide", "")])
            ws2[ws2.max_row][2].alignment = wrap
            ws2[ws2.max_row][4].alignment = wrap
    ws2.column_dimensions["A"].width = 6
    ws2.column_dimensions["B"].width = 12
    ws2.column_dimensions["C"].width = 45
    ws2.column_dimensions["D"].width = 11
    ws2.column_dimensions["E"].width = 90

    # Sheet 3: Xếp loại năng lực
    ws3 = wb.create_sheet("Xếp loại năng lực")
    ws3.append(["Mức năng lực", "Điểm", "Định hướng sử dụng kết quả"])
    for c in ws3[1]:
        c.fill, c.font = head_fill, head_font
    levels = sorted(rubric["classification"], key=lambda x: -x["min"])
    for i, lv in enumerate(levels):
        hi = "100" if i == 0 else str(levels[i - 1]["min"] - 1)
        rng = f"{lv['min']}–{hi}" if i != len(levels) - 1 else f"Dưới {levels[i - 1]['min']}"
        ws3.append([lv["label"], rng, lv.get("note", "")])
        ws3[ws3.max_row][2].alignment = wrap
    ws3.column_dimensions["A"].width = 22
    ws3.column_dimensions["B"].width = 12
    ws3.column_dimensions["C"].width = 90

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def rubric_to_docx(rubric: dict) -> bytes:
    import docx
    from docx.shared import Pt

    doc = docx.Document()
    doc.add_heading("RUBRIC ĐÁNH GIÁ NĂNG LỰC ỨNG DỤNG AI", level=0)
    doc.add_paragraph("Trường Đại học Đại Nam (DNU) — Năm 2026").alignment = 1
    doc.add_paragraph(f"Phiên bản rubric: {rubric.get('version', '')} · Thang điểm 100").alignment = 1

    # Bảng tổng quan trọng số
    doc.add_heading("Cấu trúc và trọng số", level=1)
    t = doc.add_table(rows=1, cols=4)
    t.style = "Light Grid Accent 1"
    for i, h in enumerate(["Phần", "Nội dung", "Trọng số", "Điểm"]):
        t.rows[0].cells[i].text = h
    for k, p in rubric["parts"].items():
        graded = p.get("graded")
        row = t.add_row().cells
        row[0].text, row[1].text = k, p["name"]
        row[2].text = f"{p['weight']}%" if graded else "–"
        row[3].text = str(p["max_score"]) if graded else "Đạt/Không đạt"

    # Chi tiết từng phần
    for k, p in _graded_parts(rubric):
        doc.add_heading(f"Phần {k} — {p['name']} (trọng số {p['weight']}%, tối đa {p['max_score']} điểm)", level=1)
        doc.add_paragraph(p.get("description", ""))
        if p.get("products"):
            doc.add_paragraph("Sản phẩm phải nộp:").runs[0].bold = True
            for pr in p["products"]:
                doc.add_paragraph(pr, style="List Bullet")
        ct = doc.add_table(rows=1, cols=4)
        ct.style = "Light Grid Accent 1"
        for i, h in enumerate(["Mã", "Tiêu chí", "Điểm tối đa", "Hướng dẫn chấm"]):
            ct.rows[0].cells[i].text = h
        for crit in p["criteria"]:
            row = ct.add_row().cells
            row[0].text = crit["id"]
            row[1].text = crit["name"]
            row[2].text = str(crit["max"])
            row[3].text = crit.get("guide", "")
        for cell in ct.columns[3].cells:
            for para in cell.paragraphs:
                for run in para.runs:
                    run.font.size = Pt(9)

    # Xếp loại
    doc.add_heading("Xếp loại năng lực", level=1)
    lt = doc.add_table(rows=1, cols=3)
    lt.style = "Light Grid Accent 1"
    for i, h in enumerate(["Mức năng lực", "Điểm", "Định hướng sử dụng kết quả"]):
        lt.rows[0].cells[i].text = h
    levels = sorted(rubric["classification"], key=lambda x: -x["min"])
    for i, lv in enumerate(levels):
        hi = "100" if i == 0 else str(levels[i - 1]["min"] - 1)
        rng = f"{lv['min']}–{hi}" if i != len(levels) - 1 else f"Dưới {levels[i - 1]['min']}"
        row = lt.add_row().cells
        row[0].text, row[1].text, row[2].text = lv["label"], rng, lv.get("note", "")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
