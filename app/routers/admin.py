"""Phân hệ quản trị: danh sách giảng viên, cấu hình, công bố, tải sản phẩm, sao lưu."""
from __future__ import annotations

import csv
import io
import time

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse

from app.auth import require_role, set_password
from app.config import ROLE_ADMIN, ROLE_COUNCIL, ROLE_LECTURER, get_settings, now_vn
from app.rubric import get_rubric
from app.security import hash_password
from app.services import audit
from app.services.ops import get_timeline, lock_all, publish_all, send_reminders

router = APIRouter(prefix="/admin")
admin_dep = Depends(require_role(ROLE_ADMIN))


def render(request: Request, template: str, user: dict, **ctx):
    return request.app.state.templates.TemplateResponse(request, template, {"user": user, "now": now_vn(), **ctx})


@router.get("")
def index(request: Request, user: dict = admin_dep):
    from app.services.ai_config import get_ai_config

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
        "graded": by_status.get("graded", 0) + by_status.get("approved", 0) + by_status.get("published", 0),
        "appeals_open": len(store.find("appeals", status="open")),
    }
    settings = get_settings()
    return render(request, "admin/index.html", user, counts=counts, timeline=get_timeline(store),
                  settings=settings, ai_cfg=get_ai_config(store))


@router.post("/lock")
def lock(request: Request, user: dict = admin_dep):
    result = lock_all(request.app.state.store, user)
    return RedirectResponse(f"/admin?locked={result['locked']}&invalid={result['invalid']}", status_code=303)


@router.post("/remind")
def remind(request: Request, user: dict = admin_dep):
    sent = send_reminders(request.app.state.store)
    audit.log(request.app.state.store, user, "send_reminders", "users", note=f"Gửi {sent} email nhắc hạn")
    return RedirectResponse(f"/admin?reminded={sent}", status_code=303)


@router.post("/publish")
def publish(request: Request, user: dict = admin_dep):
    count = publish_all(request.app.state.store, user)
    return RedirectResponse(f"/admin?published={count}", status_code=303)


# ---------- người dùng ----------

@router.get("/users")
def users_page(request: Request, user: dict = admin_dep):
    store = request.app.state.store
    users = sorted(store.all("users"), key=lambda u: (u["role"], u.get("khoa", ""), u.get("ma_gv", "")))
    return render(request, "admin/users.html", user, users=users, settings=get_settings())


@router.post("/users/import")
async def users_import(request: Request, file: UploadFile = None, csv_text: str = Form(""), user: dict = admin_dep):
    """Import CSV: ma_gv,ho_ten,email,don_vi,bo_mon,chuc_vu,role(lecturer|council|admin),password(tùy chọn).

    Tương thích ngược: chấp nhận cột "khoa" thay cho "don_vi" và "ma_dinh_danh" thay cho "ma_gv".
    Người dùng mới không kèm password sẽ nhận mật khẩu mặc định (DEFAULT_PASSWORD, mặc định DNU@2026).
    """
    store = request.app.state.store
    settings = get_settings()
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
        # chuẩn hóa khóa cột về chữ thường, bỏ khoảng trắng (hỗ trợ tiêu đề có dấu cách)
        row = {(k or "").strip().lower(): v for k, v in row.items()}
        email = (row.get("email") or "").strip().lower()
        if not email:
            continue
        role = (row.get("role") or ROLE_LECTURER).strip() or ROLE_LECTURER
        # Đơn vị: nhận cột "don_vi" (mới) hoặc "khoa" (cũ); lưu nội bộ ở khóa "khoa"
        don_vi = (row.get("don_vi") or row.get("khoa") or "").strip()
        doc = {
            "email": email, "ho_ten": (row.get("ho_ten") or "").strip(),
            "ma_gv": (row.get("ma_gv") or row.get("ma_dinh_danh") or "").strip(), "khoa": don_vi,
            "bo_mon": (row.get("bo_mon") or "").strip(), "chuc_vu": (row.get("chuc_vu") or "").strip(),
            "role": role, "active": True,
        }
        pw = (row.get("password") or "").strip()
        existing = store.find_one("users", email=email)
        if existing:
            if pw:
                doc["password_hash"] = hash_password(pw)
            store.patch("users", existing["id"], doc)
            updated += 1
        else:
            doc["password_hash"] = hash_password(pw or settings.default_password)
            store.add("users", doc)
            added += 1
    audit.log(store, user, "import_users", "users", note=f"Thêm {added}, cập nhật {updated}")
    return RedirectResponse(f"/admin/users?added={added}&updated={updated}", status_code=303)


@router.post("/users/add")
def users_add(request: Request, ho_ten: str = Form(...), email: str = Form(...), ma_gv: str = Form(""),
              khoa: str = Form(""), bo_mon: str = Form(""), chuc_vu: str = Form(""),
              role: str = Form(ROLE_LECTURER), password: str = Form(...), user: dict = admin_dep):
    store = request.app.state.store
    email = email.strip().lower()
    if role not in (ROLE_LECTURER, ROLE_COUNCIL, ROLE_ADMIN):
        raise HTTPException(400, "Vai trò không hợp lệ")
    if len(password) < 6:
        raise HTTPException(400, "Mật khẩu tối thiểu 6 ký tự")
    if store.find_one("users", email=email):
        raise HTTPException(400, "Email đã tồn tại")
    store.add("users", {
        "email": email, "ho_ten": ho_ten.strip(), "ma_gv": ma_gv.strip(),
        "khoa": khoa.strip(), "bo_mon": bo_mon.strip(), "chuc_vu": chuc_vu.strip(),
        "role": role, "active": True, "password_hash": hash_password(password),
    })
    audit.log(store, user, "add_user", f"users/{email}", note=f"role={role}")
    return RedirectResponse("/admin/users?added=1&updated=0", status_code=303)


@router.post("/users/{uid}/password")
def users_set_password(uid: str, request: Request, new_password: str = Form(...), user: dict = admin_dep):
    store = request.app.state.store
    target = store.get("users", uid)
    if not target:
        raise HTTPException(404)
    if len(new_password) < 6:
        raise HTTPException(400, "Mật khẩu tối thiểu 6 ký tự")
    set_password(store, target, new_password)
    audit.log(store, user, "reset_password", f"users/{target['email']}")
    return RedirectResponse("/admin/users?pwset=1", status_code=303)


@router.post("/users/{uid}/toggle")
def users_toggle(uid: str, request: Request, user: dict = admin_dep):
    store = request.app.state.store
    target = store.get("users", uid)
    if not target:
        raise HTTPException(404)
    new_active = not target.get("active", True)
    store.patch("users", uid, {"active": new_active})
    audit.log(store, user, "toggle_user", f"users/{target['email']}", after={"active": new_active})
    return RedirectResponse("/admin/users", status_code=303)


# ---------- cấu hình ----------

@router.get("/config")
def config_page(request: Request, user: dict = admin_dep):
    from app.services.ai_config import get_ai_config
    from app.services.ai_usage import get_stats

    store = request.app.state.store
    return render(request, "admin/config.html", user, timeline=get_timeline(store),
                  rubric=get_rubric(store), settings=get_settings(),
                  ai_cfg=get_ai_config(store), ai_stats=get_stats(store))


@router.get("/rubric.xlsx")
def rubric_xlsx(request: Request, user: dict = admin_dep):
    from fastapi.responses import Response

    from app.services.rubric_export import rubric_to_xlsx

    data = rubric_to_xlsx(get_rubric(request.app.state.store))
    return Response(
        data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=DNU-Rubric-HoiDong-{now_vn():%Y%m%d}.xlsx"},
    )


@router.get("/rubric.docx")
def rubric_docx(request: Request, user: dict = admin_dep):
    from fastapi.responses import Response

    from app.services.rubric_export import rubric_to_docx

    data = rubric_to_docx(get_rubric(request.app.state.store))
    return Response(
        data, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=DNU-Rubric-HoiDong-{now_vn():%Y%m%d}.docx"},
    )


@router.post("/config/timeline")
def config_timeline(request: Request, deadline: str = Form(...), open_at: str = Form(...), user: dict = admin_dep):
    store = request.app.state.store
    tl = get_timeline(store)
    before = {"deadline": tl["deadline"], "open_at": tl["open_at"]}
    tl.update({"deadline": deadline.strip(), "open_at": open_at.strip()})
    store.put("config", "timeline", tl)
    audit.log(store, user, "update_timeline", "config/timeline", before=before, after=tl)
    return RedirectResponse("/admin/config?saved=1", status_code=303)


# ---------- cấu hình AI (Admin nạp API key + model) ----------

@router.post("/config/ai")
def config_ai(request: Request, api_key: str = Form(""), model: str = Form(""),
              grader: str = Form("auto"), clear_key: str = Form(""), user: dict = admin_dep):
    from app.services.ai_config import set_ai_config

    store = request.app.state.store
    set_ai_config(store, api_key=api_key, model=model, grader=grader, clear_key=bool(clear_key))
    audit.log(store, user, "update_ai_config", "config/ai",
              note=f"grader={grader}, model={model or '(giữ nguyên)'}, "
                   f"{'xóa key' if clear_key else ('cập nhật key' if api_key.strip() else 'giữ key')}")
    return RedirectResponse("/admin/config?ai=1", status_code=303)


@router.post("/config/ai/test")
def config_ai_test(request: Request, user: dict = admin_dep):
    """Gọi thử Claude để kiểm tra API key + model, tự thử lại khi máy chủ quá tải (529)."""
    from app.services.ai_config import get_ai_config
    from app.services.ai_usage import record_usage
    from app.services.grading.graders import friendly_ai_error, is_transient_error

    store = request.app.state.store
    cfg = get_ai_config(store)
    if cfg["grader"] != "claude" or not cfg["has_key"]:
        return RedirectResponse("/admin/config?ai_test=Chưa+cấu+hình+API+key+Claude", status_code=303)

    import anthropic

    client = anthropic.Anthropic(api_key=cfg["api_key"], max_retries=2)
    msg, last_exc, attempts = "", None, 4
    for attempt in range(attempts):
        try:
            resp = client.messages.create(
                model=cfg["model"], max_tokens=16,
                messages=[{"role": "user", "content": "Trả lời đúng một từ: OK"}],
            )
            record_usage(store, cfg["model"], getattr(resp, "usage", None), kind="test")
            msg = "Kết nối Claude thành công ✓"
            break
        except Exception as exc:  # noqa: BLE001 — phân loại tạm thời / cấu hình
            last_exc = exc
            if not is_transient_error(exc) or attempt == attempts - 1:
                break
            time.sleep(2 * (attempt + 1))  # backoff 2s, 4s, 6s khi Claude quá tải
    if not msg:
        msg = friendly_ai_error(last_exc, cfg["model"])
    audit.log(store, user, "test_ai", "config/ai", note=msg[:200])
    from urllib.parse import quote

    return RedirectResponse(f"/admin/config?ai_test={quote(msg)}", status_code=303)


@router.get("/ai-usage")
def ai_usage_page(request: Request, user: dict = admin_dep):
    from app.services.ai_config import get_ai_config
    from app.services.ai_usage import USD_TO_VND, get_stats

    store = request.app.state.store
    return render(request, "admin/ai_usage.html", user,
                  stats=get_stats(store), ai_cfg=get_ai_config(store), usd_vnd=USD_TO_VND)


@router.post("/ai-usage/reset")
def ai_usage_reset(request: Request, user: dict = admin_dep):
    from app.services.ai_usage import reset_stats

    store = request.app.state.store
    n = reset_stats(store)
    audit.log(store, user, "reset_ai_usage", "ai_usage", note=f"Xóa {n} bản ghi")
    return RedirectResponse("/admin/ai-usage?reset=1", status_code=303)


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


# ---------- tải sản phẩm (ZIP) ----------

@router.get("/downloads")
def downloads_page(request: Request, khoa: str = "", user: dict = admin_dep):
    store = request.app.state.store
    users = {u["id"]: u for u in store.all("users")}
    rows = []
    for s in store.all("submissions"):
        u = users.get(s["user_id"])
        if not u or s.get("status") == "draft":
            continue
        if khoa and (u.get("khoa") or "") != khoa:
            continue
        n_files = sum(1 for i in store.find("submission_items", submission_id=s["id"]) if i.get("type") == "file")
        n_links = sum(1 for i in store.find("submission_items", submission_id=s["id"]) if i.get("type") == "link")
        rows.append({"sub": s, "user": u, "n_files": n_files, "n_links": n_links})
    rows.sort(key=lambda r: (r["user"].get("khoa", ""), r["user"].get("ma_gv", "")))
    khoas = sorted({u.get("khoa", "") for u in users.values() if u.get("khoa")})
    return render(request, "admin/downloads.html", user, rows=rows, khoas=khoas, khoa=khoa)


@router.get("/download/all.zip")
def download_all(request: Request, khoa: str = "", user: dict = admin_dep):
    import os

    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask

    from app.services.downloads import build_all_zip

    path, fname = build_all_zip(request.app.state.store, request.app.state.storage, khoa=khoa)
    audit.log(request.app.state.store, user, "download_all", "submissions", note=f"khoa={khoa or 'tất cả'}")
    return FileResponse(path, filename=fname, media_type="application/zip",
                        background=BackgroundTask(os.remove, path))


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
