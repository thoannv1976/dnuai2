"""Cấu hình ứng dụng DNU AI-Assess.

Hai chế độ chạy (APP_MODE):
- "local": SQLite + lưu tệp cục bộ + đăng nhập giả lập + email ghi log (dev/demo)
- "gcp":   Firestore + Google Cloud Storage + Google SSO + SMTP (production)
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Ho_Chi_Minh")

ALLOWED_EXTENSIONS = {".docx", ".pdf", ".pptx", ".xlsx", ".mp4"}
MAX_FILE_SIZE = 200 * 1024 * 1024  # 200MB/tệp theo đề bài

PARTS = ["A", "B", "C", "D", "E", "F", "G"]
GRADED_PARTS = ["B", "C", "D", "E", "F", "G"]

ROLE_LECTURER = "lecturer"
ROLE_COUNCIL = "council"
ROLE_ADMIN = "admin"


class Settings:
    def __init__(self) -> None:
        self.app_mode = os.environ.get("APP_MODE", "local")
        self.base_dir = Path(__file__).resolve().parent.parent
        self.data_dir = Path(os.environ.get("DATA_DIR", self.base_dir / "data"))
        self.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
        self.cron_token = os.environ.get("CRON_TOKEN", "dev-cron-token")

        # Chấm AI
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.grading_model = os.environ.get("GRADING_MODEL", "claude-opus-4-8")
        self.grader_kind = os.environ.get("GRADER", "claude" if self.anthropic_api_key else "mock")

        # Mốc thời gian mặc định (admin có thể sửa trong DB, DB là nguồn chính)
        self.default_deadline = os.environ.get("DEADLINE", "2026-06-30T17:00:00+07:00")
        self.default_open_at = os.environ.get("OPEN_AT", "2026-06-25T00:00:00+07:00")

        # Google SSO (chế độ gcp)
        self.google_client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
        self.google_client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
        self.allowed_email_domains = [
            d.strip() for d in os.environ.get("ALLOWED_EMAIL_DOMAINS", "dainam.edu.vn").split(",") if d.strip()
        ]

        # Kiểu đăng nhập, tách khỏi kiểu hạ tầng: "dev" (chọn tài khoản, thử nghiệm)
        # hoặc "google" (SSO). Mặc định theo APP_MODE.
        self.auth_mode = os.environ.get("AUTH_MODE", "google" if self.app_mode == "gcp" else "dev")

        # Bootstrap quản trị viên: các email này được tạo/nâng quyền admin khi khởi động
        self.admin_emails = [
            e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()
        ]

        # GCP
        self.gcs_bucket = os.environ.get("GCS_BUCKET", "")
        self.firestore_project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")

        # SMTP (chế độ gcp)
        self.smtp_host = os.environ.get("SMTP_HOST", "")
        self.smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        self.smtp_user = os.environ.get("SMTP_USER", "")
        self.smtp_password = os.environ.get("SMTP_PASSWORD", "")
        self.mail_from = os.environ.get("MAIL_FROM", "ai-assess@dainam.edu.vn")

        self.data_dir.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Dùng trong test khi đổi biến môi trường."""
    global _settings
    _settings = None


def now_vn() -> datetime:
    return datetime.now(TZ)


def parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt
