"""Đóng gói sản phẩm/minh chứng của giảng viên thành file ZIP để Admin tải về.

Ghi theo luồng (shutil.copyfileobj) ra tệp tạm để không nạp toàn bộ tệp lớn vào RAM.
Cấu trúc: <ĐơnVị>/<MãGV_HọTên>/Phan<X>_SanPham|MinhChung/<tên tệp>, kèm PhanA_ThongTin.txt,
LIEN_KET.txt (các liên kết), và DANH_SACH.csv ở gốc (khi tải toàn bộ).
"""
from __future__ import annotations

import csv
import io
import re
import shutil
import tempfile
import zipfile

from app.config import now_vn


def _safe(s: str | None) -> str:
    return re.sub(r"[^\w.\-]+", "_", (s or "").strip(), flags=re.UNICODE).strip("_") or "x"


def _folder_for(user: dict) -> str:
    return f"{_safe(user.get('ma_gv') or 'GV')}_{_safe(user.get('ho_ten') or '')}"


def _unique(seen: set[str], name: str) -> str:
    if name not in seen:
        seen.add(name)
        return name
    stem, dot, ext = name.rpartition(".")
    i = 2
    while True:
        cand = f"{stem}_{i}.{ext}" if dot else f"{name}_{i}"
        if cand not in seen:
            seen.add(cand)
            return cand
        i += 1


def _add_submission(zf: zipfile.ZipFile, store, storage, sub: dict, user: dict, base: str = "") -> int:
    """Thêm toàn bộ tệp + thông tin của một hồ sơ vào zip. Trả về số tệp đã thêm."""
    items = store.find("submission_items", submission_id=sub["id"])
    folder = (base + "/" if base else "") + _folder_for(user)
    pa = sub.get("part_a") or {}
    info = (
        f"Họ tên: {pa.get('ho_ten', '')}\n"
        f"Mã GV: {pa.get('ma_gv', '')}\n"
        f"Chức vụ: {user.get('chuc_vu', '')}\n"
        f"Đơn vị/Bộ môn: {pa.get('khoa_bo_mon', '')}\n"
        f"Học phần: {pa.get('hoc_phan', '')}\n"
        f"Công cụ AI: {', '.join(pa.get('cong_cu_ai') or [])}\n"
        f"Mức tự đánh giá: {pa.get('muc_thanh_thao', '')}\n"
        f"Trạng thái hồ sơ: {sub.get('status', '')}\n"
    )
    zf.writestr(f"{folder}/PhanA_ThongTin.txt", info)

    seen: set[str] = set()
    links: list[str] = []
    n_files = 0
    for it in items:
        part = it.get("part", "?")
        kind = "SanPham" if it.get("kind") == "product" else "MinhChung"
        if it.get("type") == "file":
            arc = _unique(seen, f"{folder}/Phan{part}_{kind}/{_safe(it.get('original_name'))}")
            try:
                with zf.open(arc, "w") as dest, storage.open(it["storage_path"]) as src:
                    shutil.copyfileobj(src, dest)
                n_files += 1
            except Exception as exc:  # noqa: BLE001 — tệp lỗi ghi chú lại, không dừng cả gói
                zf.writestr(arc + ".LOI.txt", f"Không đọc được tệp: {exc}")
        else:
            links.append(f"[Phần {part} · {kind}] {it.get('original_name') or ''}: {it.get('url')}")
    if links:
        zf.writestr(f"{folder}/LIEN_KET.txt", "\n".join(links))
    return n_files


def build_submission_zip(store, storage, sid: str) -> tuple[str, str] | None:
    """Đóng gói tệp của 1 giảng viên. Trả về (đường dẫn tệp tạm, tên tệp tải về)."""
    sub = store.get("submissions", sid)
    if not sub:
        return None
    user = store.get("users", sub["user_id"]) or {}
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        _add_submission(zf, store, storage, sub, user)
    tmp.close()
    return tmp.name, f"{_folder_for(user)}.zip"


def build_all_zip(store, storage, khoa: str = "") -> tuple[str, str]:
    """Đóng gói tệp của tất cả giảng viên (lọc theo khoa nếu có) + DANH_SACH.csv."""
    users = {u["id"]: u for u in store.all("users")}
    subs = [s for s in store.all("submissions") if s.get("user_id") in users]
    if khoa:
        subs = [s for s in subs if (users[s["user_id"]].get("khoa") or "") == khoa]

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    rows = [["Mã GV", "Họ tên", "Đơn vị", "Bộ môn", "Chức vụ", "Trạng thái", "Số tệp"]]
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for s in subs:
            u = users[s["user_id"]]
            n = _add_submission(zf, store, storage, s, u, base=_safe(u.get("khoa") or "KhongRoDonVi"))
            rows.append([u.get("ma_gv", ""), u.get("ho_ten", ""), u.get("khoa", ""),
                         u.get("bo_mon", ""), u.get("chuc_vu", ""), s.get("status", ""), n])
        buf = io.StringIO()
        csv.writer(buf).writerows(rows)
        zf.writestr("DANH_SACH.csv", "﻿" + buf.getvalue())  # BOM để Excel đọc đúng tiếng Việt
    tmp.close()
    khoa_tag = f"-{_safe(khoa)}" if khoa else ""
    return tmp.name, f"DNU-SanPham{khoa_tag}-{now_vn():%Y%m%d}.zip"
