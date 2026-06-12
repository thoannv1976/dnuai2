"""DNU AI-Assess — ứng dụng FastAPI chính."""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import auth
from app.config import ROLE_ADMIN, ROLE_COUNCIL, get_settings, now_vn
from app.db import create_store
from app.rubric import get_rubric
from app.routers import admin, council, lecturer, reports, tasks
from app.services.ops import get_timeline
from app.storage import create_storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="DNU AI-Assess", docs_url=None, redoc_url=None)

    app.state.store = create_store(settings)
    app.state.storage = create_storage(settings)
    templates = Jinja2Templates(directory=str(settings.base_dir / "app" / "templates"))
    templates.env.globals.update(app_mode=settings.app_mode, auth_mode=settings.auth_mode)
    app.state.templates = templates

    app.mount("/static", StaticFiles(directory=str(settings.base_dir / "app" / "static")), name="static")

    app.include_router(auth.router)
    app.include_router(lecturer.router)
    app.include_router(lecturer.files_router)
    app.include_router(council.router)
    app.include_router(admin.router)
    app.include_router(reports.router)
    app.include_router(tasks.router)

    # Seed rubric + timeline lần đầu
    get_rubric(app.state.store)
    get_timeline(app.state.store)

    # SEED_DEMO=1: tự tạo tài khoản + hồ sơ demo khi khởi động (phục vụ deploy demo)
    if os.environ.get("SEED_DEMO") == "1" and not app.state.store.all("users"):
        from scripts.seed_demo import seed

        seed(app.state.store, app.state.storage)

    # ADMIN_EMAILS: bảo đảm các email này là quản trị viên (tạo mới hoặc nâng quyền)
    from app.config import ROLE_ADMIN as _ADMIN

    for email in settings.admin_emails:
        existing = app.state.store.find_one("users", email=email)
        if existing:
            if existing.get("role") != _ADMIN or not existing.get("active", True):
                app.state.store.patch("users", existing["id"], {"role": _ADMIN, "active": True})
                logging.getLogger("dnu").info("Nâng quyền quản trị: %s", email)
        else:
            app.state.store.add("users", {
                "email": email, "ho_ten": email.split("@")[0], "ma_gv": "",
                "khoa": "", "bo_mon": "", "role": _ADMIN, "active": True,
            })
            logging.getLogger("dnu").info("Tạo quản trị viên từ ADMIN_EMAILS: %s", email)

    @app.get("/")
    def root(request: Request):
        user = auth.current_user(request)
        if not user:
            return RedirectResponse("/login")
        dest = {ROLE_COUNCIL: "/council", ROLE_ADMIN: "/admin"}.get(user["role"], "/lecturer")
        return RedirectResponse(dest)

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "time": now_vn().isoformat()}

    @app.exception_handler(Exception)
    async def err_handler(request: Request, exc: Exception):
        logging.getLogger("dnu").exception("Lỗi không xử lý: %s", exc)
        return HTMLResponse("<h3>Có lỗi hệ thống. Vui lòng thử lại hoặc liên hệ quản trị viên.</h3>", status_code=500)

    return app


app = create_app()
