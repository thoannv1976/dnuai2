"""Test xuất rubric ra Excel và Word."""
import io

from app.rubric import load_rubric_seed
from app.services.rubric_export import rubric_to_docx, rubric_to_xlsx
from tests.conftest import login


def test_rubric_to_xlsx_parseable():
    import openpyxl

    data = rubric_to_xlsx(load_rubric_seed())
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert {"Huong_dan", "Rubric_chi_tiet", "Bang_diem", "Phan_loai"} <= set(wb.sheetnames)
    # Sheet rubric chi tiết: đủ mã tiêu chí B–G + 4 cột mức
    rb = wb["Rubric_chi_tiet"]
    header = [c.value for c in rb[1]]
    assert "Xuất sắc (90–100%)" in header and "Chưa đạt (<50%)" in header
    crit_text = "\n".join(str(c.value) for row in rb.iter_rows() for c in row)
    for cid in ["B1", "C4", "D3", "E_BONUS", "F2", "G2"]:
        assert cid in crit_text
    # Bảng nhập điểm có công thức tổng + xếp loại
    bd_text = "\n".join(str(c.value) for row in wb["Bang_diem"].iter_rows() for c in row if c.value)
    assert "TỔNG ĐIỂM (thang 100)" in bd_text
    assert "XẾP LOẠI NĂNG LỰC" in bd_text
    assert any(str(c.value).startswith("=") for row in wb["Bang_diem"].iter_rows() for c in row if c.value)


def test_rubric_to_docx_parseable():
    import docx

    data = rubric_to_docx(load_rubric_seed())
    doc = docx.Document(io.BytesIO(data))
    full = "\n".join(p.text for p in doc.paragraphs)
    assert "RUBRIC" in full
    assert "Phần C" in full
    assert len(doc.tables) >= 6  # tổng quan + 6 phần + xếp loại


def test_admin_can_download_rubric(client):
    login(client, "admin@dainam.edu.vn")
    r1 = client.get("/admin/rubric.xlsx")
    assert r1.status_code == 200
    assert "spreadsheetml" in r1.headers["content-type"]
    assert len(r1.content) > 1000
    r2 = client.get("/admin/rubric.docx")
    assert r2.status_code == 200
    assert "wordprocessingml" in r2.headers["content-type"]
    assert len(r2.content) > 1000


def test_lecturer_cannot_download_rubric(client):
    login(client, "gv001@dainam.edu.vn")
    assert client.get("/admin/rubric.xlsx", follow_redirects=False).status_code == 403
