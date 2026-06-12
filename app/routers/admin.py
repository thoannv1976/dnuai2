"""Phân hệ quản trị: danh sách giảng viên, cấu hình, vận hành chấm, công bố, sao lưu."""
from __future__ import annotations

import csv
import io
import threading

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse

from app.auth import require_role
from app.config import ROLE_ADMIN, ROLE_COUNCIL, ROLE_LECTURER, get_settings, now_vn
from app.rubric import get_rubric
from app.services import audit
from app.services.grading.engine import run_grading
from app.services.grading.graders import create_grader
from app.services.ops import get_timeline, lock_all, publish_all, send_reminders

router = APIRouter(prefix="/admin")
admin_dep = Depends(require_role(ROLE_ADMIN))


def render(request: Request, template: str, user: dict, **ctx):
    return request.app.state.templates.TemplateResponse(request, template, {"user": user, "now": now_vn(), **ctx})


def _grading_status(store) -> dict:
    return store.get("config", "grading_status") or {"running": False}


@router.get("")
def index(request: Request, user: dict = admin_dep):
    store = request.app.state.store
    subs = store.all("submissions")
    by_status: dict[str, int] = {}
    for s in subs:
        by_status[s.get("status", "?")] = by_status.get(s.get("status", "?"), 0) + 1
    users = store.all("users")
    counts = {
        "lecturers": sum(1 for u in users if u["role"] == ROLE_LECTURER),
        "council": sum(1 for u in users if u["role"] == ROLE_COUNCIL),
        "submissions": len(subs),
        "by_status": by_status,
        "appeals_open": len(store.find("appeals", status="open")),
    }
    settings = get_settings()
    return render(request, "admin/index.html", user, counts=counts, timeline=get_timeline(store),
                  grading=_grading_status(store), settings=settings)


@router.post("/lock")
def lock(request: Request, user: dict = admin_dep):
    result = lock_all(request.app.state.store, user)
    return RedirectResponse(f"/admin?locked={result['locked']}&invalid={result['invalid']}", status_code=303)


@router.post("/remind")
def remind(request: Request, user: dict = admin_dep):
    sent = send_reminders(request.app.state.store)
    audit.log(request.app.state.store, user, "send_reminders", "users", note=f"Gửi {sent} email nhắc hạn")
    return RedirectResponse(f"/admin?reminded={sent}", status_code=303)


@router.post("/grade")
def grade(request: Request, force: bool = Form(False), user: dict = admin_dep):
    store, storage = request.app.state.store, request.app.state.storage
    status = _grading_status(store)
    if status.get("running"):
        raise HTTPException(400, "Đang có phiên chấm chạy")
    settings = get_settings()
    grader = create_grader(settings)
    store.put("config", "grading_status", {
        "id": "grading_status", "running": True, "started_at": now_vn().isoformat(),
        "grader": grader.name, "model": getattr(grader, "model", ""), "stats": None,
    })
    audit.log(store, user, "start_grading", "submissions", note=f"grader={grader.name}")

    def worker():
        try:
            stats = run_grading(store, storage, grader, force=force)
        except Exception as exc:  # noqa: BLE001 — ghi nhận lỗi tổng để hiển thị
            stats = {"fatal_error": str(exc)}
        store.put("config", "grading_status", {
            "id": "grading_status", "running": False, "finished_at": now_vn().isoformat(),
            "grader": grader.name, "stats": stats,
        })

    threading.Thread(target=worker, daemon=True).start()
    return RedirectResponse("/admin?grading=started", status_code=303)


@router.post("/publish")
def publish(request: Request, user: dict = admin_dep):
    count = publish_all(request.app.state.store, user)
    return RedirectResponse(f"/admin?published={count}", status_code=303)


# ---------- người dùng ----------

@router.get("/users")
def users_page(request: Request, user: dict = admin_dep):
    store = request.app.state.store
    users = sorted(store.all("users"), key=lambda u: (u["role"], u.get("khoa", ""), u.get("ma_gv", "")))
    return render(request, "admin/users.html", user, users=users)


@router.post("/users/import")
async def users_import(request: Request, file: UploadFile = None, csv_text: str = Form(""), user: dict = admin_dep):
    """Import CSV: ma_gv,ho_ten,email,khoa,bo_mon,role(lecturer|council|admin)."""
    store = request.app.state.store
    raw = ""
    if file is not None and file.filename:
        raw = (await file.read()).decode("utf-8-sig")
    elif csv_text.strip():
        raw = csv_text
    if not raw.strip():
        raise HTTPException(400, "Chưa có dữ liệu CSV")
    reader = csv.DictReader(io.StringIO(raw.strip()))
    added, updated = 0, 0
    for row in reader:
        email = (row.get("email") or "").strip().lower()
        if not email:
            continue
        role = (row.get("role") or ROLE_LECTURER).strip() or ROLE_LECTURER
        doc = {
            "email": email, "ho_ten": (row.get("ho_ten") or "").strip(),
            "ma_gv": (row.get("ma_gv") or "").strip(), "khoa": (row.get("khoa") or "").strip(),
            "bo_mon": (row.get("bo_mon") or "").strip(), "role": role, "active": True,
        }
        existing = store.find_one("users", email=email)
        if existing:
            store.patch("users", existing["id"], doc)
            updated += 1
        else:
            store.add("users", doc)
            added += 1
    audit.log(store, user, "import_users", "users", note=f"Thêm {added}, cập nhật {updated}")
    return RedirectResponse(f"/admin/users?added={added}&updated={updated}", status_code=303)


# ---------- cấu hình ----------

@router.get("/config")
def config_page(request: Request, user: dict = admin_dep):
    store = request.app.state.store
    return render(request, "admin/config.html", user, timeline=get_timeline(store),
                  rubric=get_rubric(store), settings=get_settings())


@router.post("/config/timeline")
def config_timeline(request: Request, deadline: str = Form(...), open_at: str = Form(...), user: dict = admin_dep):
    store = request.app.state.store
    tl = get_timeline(store)
    before = {"deadline": tl["deadline"], "open_at": tl["open_at"]}
    tl.update({"deadline": deadline.strip(), "open_at": open_at.strip()})
    store.put("config", "timeline", tl)
    audit.log(store, user, "update_timeline", "config/timeline", before=before, after=tl)
    return RedirectResponse("/admin/config?saved=1", status_code=303)


@router.get("/audit")
def audit_page(request: Request, user: dict = admin_dep):
    store = request.app.state.store
    logs = sorted(store.all("audit_logs"), key=lambda x: x["ts"], reverse=True)[:300]
    return render(request, "admin/audit.html", user, logs=logs)


@router.get("/emails")
def emails_page(request: Request, user: dict = admin_dep):
    store = request.app.state.store
    emails = sorted(store.all("email_logs"), key=lambda x: x["ts"], reverse=True)[:200]
    return render(request, "admin/emails.html", user, emails=emails)


# ---------- sao lưu ----------

@router.get("/backup")
def backup(request: Request, user: dict = admin_dep):
    import json
    from fastapi.responses import Response

    store = request.app.state.store
    collections = ["users", "submissions", "submission_items", "grading_runs", "scores",
                   "reviews", "appeals", "audit_logs", "config", "email_logs"]
    data = {c: store.all(c) for c in collections}
    audit.log(store, user, "backup", "all", note="Xuất bản sao lưu JSON")
    return Response(
        json.dumps(data, ensure_ascii=False, indent=1),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=dnu-ai-assess-backup-{now_vn():%Y%m%d-%H%M}.json"},
    )
