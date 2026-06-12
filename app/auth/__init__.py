"""Xác thực & phân quyền.

- Chế độ local: đăng nhập giả lập (chọn tài khoản demo) phục vụ phát triển/demo.
- Chế độ gcp: Google OAuth 2.0 (Google Workspace SSO), chỉ chấp nhận email thuộc
  domain DNU và đã có trong danh sách giảng viên/hội đồng/quản trị.
Phiên đăng nhập lưu trong cookie ký (itsdangerous), 12 giờ.
"""
from __future__ import annotations

import urllib.parse

import httpx
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.config import ROLE_ADMIN, ROLE_COUNCIL, ROLE_LECTURER, get_settings

SESSION_COOKIE = "dnu_session"
SESSION_MAX_AGE = 12 * 3600

router = APIRouter()


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="dnu-session")


def create_session_cookie(user: dict) -> str:
    return _serializer().dumps({"uid": user["id"], "email": user["email"], "role": user["role"]})


def read_session(request: Request) -> dict | None:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    try:
        return _serializer().loads(raw, max_age=SESSION_MAX_AGE)
    except BadSignature:
        return None


def current_user(request: Request) -> dict | None:
    sess = read_session(request)
    if not sess:
        return None
    user = request.app.state.store.get("users", sess["uid"])
    if not user or not user.get("active", True):
        return None
    return user


def require_user(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


def require_role(*roles: str):
    def dep(request: Request) -> dict:
        user = require_user(request)
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Bạn không có quyền truy cập chức năng này")
        return user

    return dep


def _login_ok(user: dict) -> RedirectResponse:
    dest = {ROLE_LECTURER: "/lecturer", ROLE_COUNCIL: "/council", ROLE_ADMIN: "/admin"}.get(user["role"], "/")
    resp = RedirectResponse(dest, status_code=303)
    resp.set_cookie(
        SESSION_COOKIE, create_session_cookie(user),
        max_age=SESSION_MAX_AGE, httponly=True, samesite="lax",
        secure=get_settings().app_mode == "gcp",
    )
    return resp


@router.get("/login")
def login_page(request: Request):
    settings = get_settings()
    demo_users = []
    if settings.auth_mode == "dev":
        demo_users = sorted(request.app.state.store.all("users"), key=lambda u: (u["role"], u.get("ma_gv", "")))
    return request.app.state.templates.TemplateResponse(
        request, "login.html",
        {"settings": settings, "demo_users": demo_users, "user": None},
    )


@router.post("/login/dev")
def login_dev(request: Request, email: str = Form(...)):
    if get_settings().auth_mode != "dev":
        raise HTTPException(404)
    user = request.app.state.store.find_one("users", email=email.strip().lower())
    if not user:
        raise HTTPException(400, "Email không có trong danh sách người dùng (chạy scripts/seed_demo.py trước)")
    return _login_ok(user)


@router.get("/auth/google")
def google_start(request: Request):
    settings = get_settings()
    if not settings.google_client_id:
        raise HTTPException(404, "Chưa cấu hình Google SSO")
    redirect_uri = str(request.url_for("google_callback"))
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "hd": settings.allowed_email_domains[0] if settings.allowed_email_domains else "",
        "prompt": "select_account",
    }
    return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params))


@router.get("/auth/google/callback", name="google_callback")
def google_callback(request: Request, code: str = ""):
    settings = get_settings()
    if not code:
        raise HTTPException(400, "Thiếu mã xác thực từ Google")
    token_resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": str(request.url_for("google_callback")),
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    if token_resp.status_code != 200:
        raise HTTPException(400, "Không đổi được mã xác thực Google")
    access_token = token_resp.json().get("access_token")
    info = httpx.get(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    ).json()
    email = (info.get("email") or "").lower()
    if not info.get("email_verified", False):
        raise HTTPException(403, "Email Google chưa được xác minh")
    # Quy tắc: đăng nhập được khi email CÓ TRONG danh sách người dùng do quản trị quản lý
    # (domain DNU chỉ là gợi ý chọn tài khoản; admin có thể thêm email ngoài domain, vd tài khoản vận hành)
    user = request.app.state.store.find_one("users", email=email)
    if not user:
        raise HTTPException(
            403,
            f"Email {email} chưa có trong danh sách người dùng của hệ thống. "
            f"Giảng viên DNU dùng email @{settings.allowed_email_domains[0] if settings.allowed_email_domains else 'dainam.edu.vn'} "
            "đã được quản trị viên import; nếu cần hỗ trợ hãy liên hệ Ban tổ chức.",
        )
    return _login_ok(user)


@router.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp
