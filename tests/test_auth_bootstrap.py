"""Test bootstrap quản trị viên (ADMIN_EMAILS) và kiểu đăng nhập (AUTH_MODE)."""
import os

from fastapi.testclient import TestClient

from app.config import reset_settings


def _fresh_app():
    reset_settings()
    from app.main import create_app

    return create_app()


def test_admin_emails_bootstrap_creates_and_promotes(store):
    store.wipe()
    # gv001 đã tồn tại với vai trò lecturer → phải được nâng quyền; email mới → tạo admin
    store.put("users", "u-x", {"id": "u-x", "email": "gv001@dainam.edu.vn", "ho_ten": "An",
                               "role": "lecturer", "active": True})
    os.environ["ADMIN_EMAILS"] = "hoanganh.goldenlight@gmail.com, gv001@dainam.edu.vn"
    try:
        app = _fresh_app()
        st = app.state.store
        created = st.find_one("users", email="hoanganh.goldenlight@gmail.com")
        assert created and created["role"] == "admin"
        promoted = st.find_one("users", email="gv001@dainam.edu.vn")
        assert promoted["role"] == "admin"

        # Đăng nhập dev bằng tài khoản bootstrap → vào được trang quản trị
        with TestClient(app) as c:
            resp = c.post("/login/dev", data={"email": "hoanganh.goldenlight@gmail.com"},
                          follow_redirects=False)
            assert resp.status_code == 303
            assert c.get("/admin", follow_redirects=False).status_code == 200
    finally:
        os.environ.pop("ADMIN_EMAILS", None)
        reset_settings()


def test_auth_mode_google_disables_dev_login(store):
    store.wipe()
    os.environ["AUTH_MODE"] = "google"
    try:
        app = _fresh_app()
        with TestClient(app) as c:
            # login/dev bị tắt khi AUTH_MODE=google
            resp = c.post("/login/dev", data={"email": "x@dainam.edu.vn"}, follow_redirects=False)
            assert resp.status_code == 404
            # trang đăng nhập hiện nút SSO
            assert "Đăng nhập bằng email DNU" in c.get("/login").text
    finally:
        os.environ.pop("AUTH_MODE", None)
        reset_settings()
