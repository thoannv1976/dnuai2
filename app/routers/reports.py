"""Phân hệ báo cáo: dashboard tiến độ, phân loại, xuất báo cáo, hồ sơ năng lực."""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.auth import require_role
from app.config import GRADED_PARTS, ROLE_ADMIN, ROLE_COUNCIL, ROLE_LECTURER, now_vn
from app.rubric import get_rubric

router = APIRouter(prefix="/reports")
staff_dep = Depends(require_role(ROLE_COUNCIL, ROLE_ADMIN))


def render(request: Request, template: str, user: dict, **ctx):
    return request.app.state.templates.TemplateResponse(request, template, {"user": user, "now": now_vn(), **ctx})


def build_summary(store) -> dict:
    users = {u["id"]: u for u in store.all("users") if u["role"] == ROLE_LECTURER}
    subs = store.all("submissions")
    reviews = {r["submission_id"]: r for r in store.all("reviews")}
    rubric = get_rubric(store)

    by_khoa: dict[str, dict] = {}
    for u in users.values():
        k = u.get("khoa") or "(Chưa rõ khoa)"
        by_khoa.setdefault(k, {"khoa": k, "total": 0, "submitted": 0, "graded": 0, "approved": 0, "published": 0})
        by_khoa[k]["total"] += 1
    classification = {c["key"]: 0 for c in rubric["classification"]}
    class_labels = {c["key"]: c["label"] for c in rubric["classification"]}
    part_sums = {p: [] for p in GRADED_PARTS}
    core_list = []

    for s in subs:
        u = users.get(s["user_id"])
        if not u:
            continue
        k = u.get("khoa") or "(Chưa rõ khoa)"
        st = s.get("status")
        if st in ("submitted", "locked", "grading", "graded", "approved", "published"):
            by_khoa[k]["submitted"] += 1
        if st in ("graded", "approved", "published"):
            by_khoa[k]["graded"] += 1
        if st in ("approved", "published"):
            by_khoa[k]["approved"] += 1
        if st == "published":
            by_khoa[k]["published"] += 1
        r = reviews.get(s["id"])
        if r and r.get("classification"):
            classification[r["classification"]] = classification.get(r["classification"], 0) + 1
            for p, v in (r.get("part_totals") or {}).items():
                part_sums[p].append(v)
            if r["classification"] == "dan_dat":
                core_list.append({"user": u, "total": r["total_final"], "submission_id": s["id"]})

    part_avgs = {p: (round(sum(v) / len(v), 2) if v else 0) for p, v in part_sums.items()}
    core_list.sort(key=lambda x: -x["total"])
    return {
        "by_khoa": sorted(by_khoa.values(), key=lambda x: x["khoa"]),
        "classification": classification, "class_labels": class_labels,
        "part_avgs": part_avgs, "core_list": core_list,
        "lecturers": len(users),
        "submitted": sum(k["submitted"] for k in by_khoa.values()),
        "graded": sum(k["graded"] for k in by_khoa.values()),
        "published": sum(k["published"] for k in by_khoa.values()),
    }


@router.get("")
def dashboard(request: Request, user: dict = staff_dep):
    store = request.app.state.store
    return render(request, "reports/dashboard.html", user, summary=build_summary(store))


@router.get("/api/summary")
def api_summary(request: Request, user: dict = staff_dep):
    return build_summary(request.app.state.store)


@router.get("/export.xlsx")
def export_xlsx(request: Request, user: dict = staff_dep):
    import openpyxl

    store = request.app.state.store
    rubric = get_rubric(store)
    users = {u["id"]: u for u in store.all("users")}
    reviews = {r["submission_id"]: r for r in store.all("reviews")}

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Tổng hợp"
    header = ["Mã GV", "Họ tên", "Email", "Khoa", "Bộ môn", "Trạng thái"]
    header += [f"Phần {p}" for p in GRADED_PARTS] + ["Tổng điểm", "Mức năng lực"]
    ws.append(header)
    for s in sorted(store.all("submissions"), key=lambda x: -(x.get("final_total") or x.get("ai_total") or 0)):
        u = users.get(s["user_id"], {})
        r = reviews.get(s["id"]) or {}
        pt = r.get("part_totals") or {}
        ws.append([
            u.get("ma_gv", ""), u.get("ho_ten", ""), u.get("email", ""), u.get("khoa", ""), u.get("bo_mon", ""),
            s.get("status", ""), *[pt.get(p, "") for p in GRADED_PARTS],
            r.get("total_final", ""), r.get("classification_label", ""),
        ])

    ws2 = wb.create_sheet("Phân loại")
    ws2.append(["Mức năng lực", "Số lượng", "Định hướng sử dụng kết quả"])
    summary = build_summary(store)
    for c in rubric["classification"]:
        ws2.append([c["label"], summary["classification"].get(c["key"], 0), c["note"]])

    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f"attachment; filename=DNU-AI-Assess-BaoCao-{now_vn():%Y%m%d}.xlsx"},
    )


@router.get("/profile/{sid}")
def profile(sid: str, request: Request,
            user: dict = Depends(require_role(ROLE_LECTURER, ROLE_COUNCIL, ROLE_ADMIN))):
    """Hồ sơ năng lực ứng dụng AI của giảng viên — trang in được (Ctrl+P → PDF)."""
    store = request.app.state.store
    sub = store.get("submissions", sid)
    if not sub:
        raise HTTPException(404)
    if user["role"] == ROLE_LECTURER:
        if sub["user_id"] != user["id"] or sub.get("status") != "published":
            raise HTTPException(403)
    owner = store.get("users", sub["user_id"])
    review = store.get("reviews", sid)
    rubric = get_rubric(store)
    scores = store.find("scores", submission_id=sid)
    by_part: dict[str, list] = {}
    for s in sorted(scores, key=lambda x: x["criterion_id"]):
        by_part.setdefault(s["part"], []).append(s)
    level_note = ""
    if review and review.get("classification"):
        for c in rubric["classification"]:
            if c["key"] == review["classification"]:
                level_note = c["note"]
    return render(request, "reports/profile.html", user, sub=sub, owner=owner, review=review,
                  rubric=rubric, scores=by_part, parts=GRADED_PARTS, level_note=level_note)
