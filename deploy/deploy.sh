#!/usr/bin/env bash
# =============================================================================
# DNU AI-Assess — Cài đặt tự động lên Google Cloud (Cloud Run + Firestore + GCS)
# =============================================================================
# Chạy MỘT lệnh để dựng toàn bộ hệ thống trên tài khoản Google Cloud của Nhà trường.
# Yêu cầu: chạy trong Google Cloud Shell (đã có gcloud, gsutil) hoặc máy đã cài
# Google Cloud SDK và đã `gcloud auth login`.
#
# Cách dùng:
#   1) Sửa các biến ở phần CẤU HÌNH bên dưới (tối thiểu: PROJECT_ID, ADMIN_EMAIL).
#   2) Đặt khóa Claude API:  export ANTHROPIC_API_KEY="sk-ant-..."
#   3) Chạy:  bash deploy/deploy.sh
# Script idempotent: chạy lại nhiều lần không gây lỗi (bỏ qua tài nguyên đã có).
# =============================================================================
set -euo pipefail

# ----------------------------- CẤU HÌNH ---------------------------------------
PROJECT_ID="${PROJECT_ID:-}"                       # BẮT BUỘC: mã dự án GCP của Trường
REGION="${REGION:-asia-southeast1}"               # Vùng triển khai (Singapore)
SERVICE="${SERVICE:-dnu-ai-assess}"               # Tên dịch vụ Cloud Run
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@dainam.edu.vn}" # Email tài khoản quản trị đầu tiên
GRADING_MODEL="${GRADING_MODEL:-claude-opus-4-8}" # Model AI dùng để chấm
BUCKET="${BUCKET:-${PROJECT_ID}-dnu-ai-assess}"   # Bucket lưu sản phẩm/minh chứng
ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"        # Khóa Claude API (có thể nạp sau trong app)
DEADLINE="${DEADLINE:-2026-06-30T17:00:00+07:00}" # Hạn nộp (admin sửa được trong app)
# -----------------------------------------------------------------------------

c_green="\033[0;32m"; c_yellow="\033[1;33m"; c_red="\033[0;31m"; c_off="\033[0m"
say()  { echo -e "${c_green}==>${c_off} $*"; }
warn() { echo -e "${c_yellow}[!]${c_off} $*"; }
die()  { echo -e "${c_red}[LỖI]${c_off} $*" >&2; exit 1; }

[ -n "$PROJECT_ID" ] || die "Chưa đặt PROJECT_ID. Ví dụ: PROJECT_ID=dnuai2 bash deploy/deploy.sh"
command -v gcloud >/dev/null || die "Không tìm thấy gcloud. Hãy chạy trong Google Cloud Shell."
command -v gsutil >/dev/null || die "Không tìm thấy gsutil."
# Chạy từ thư mục gốc dự án (có Dockerfile)
cd "$(dirname "$0")/.."
[ -f Dockerfile ] || die "Không thấy Dockerfile — hãy chạy script từ thư mục gốc bộ cài."

rand() { openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | xxd -p | tr -d '\n'; }

say "Dự án: $PROJECT_ID | Vùng: $REGION | Dịch vụ: $SERVICE | Bucket: $BUCKET"
gcloud config set project "$PROJECT_ID" >/dev/null
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# 1) Bật các API cần thiết --------------------------------------------------
say "Bật các API (Cloud Run, Build, Firestore, Storage, Secret Manager, Scheduler)..."
gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  firestore.googleapis.com storage.googleapis.com secretmanager.googleapis.com \
  cloudscheduler.googleapis.com --quiet

# 2) Firestore (Native mode) ------------------------------------------------
if gcloud firestore databases describe --database='(default)' >/dev/null 2>&1; then
  say "Firestore đã tồn tại — bỏ qua."
else
  say "Tạo Firestore (Native mode) tại $REGION..."
  gcloud firestore databases create --location="$REGION" --quiet \
    || warn "Không tạo được Firestore tự động — hãy tạo thủ công (Native mode) rồi chạy lại."
fi

# 3) Bucket Cloud Storage ----------------------------------------------------
if gsutil ls -b "gs://${BUCKET}" >/dev/null 2>&1; then
  say "Bucket gs://${BUCKET} đã tồn tại — bỏ qua."
else
  say "Tạo bucket gs://${BUCKET}..."
  gsutil mb -l "$REGION" "gs://${BUCKET}"
fi

# 4) Secrets ----------------------------------------------------------------
ensure_secret() { # tên_secret  giá_trị
  local name="$1" value="$2"
  if gcloud secrets describe "$name" >/dev/null 2>&1; then
    say "Secret $name đã tồn tại — giữ nguyên."
  else
    say "Tạo secret $name..."
    printf '%s' "$value" | gcloud secrets create "$name" --data-file=- --quiet
  fi
}
SECRET_KEY_VAL="$(rand)"
CRON_TOKEN_VAL="$(rand)"
ADMIN_PW_VAL="${ADMIN_PASSWORD:-DNU-$(head -c 6 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 8)@2026}"
ensure_secret dnu-secret-key "$SECRET_KEY_VAL"
ensure_secret dnu-cron-token "$CRON_TOKEN_VAL"
ensure_secret dnu-admin-password "$ADMIN_PW_VAL"
if [ -n "$ANTHROPIC_API_KEY" ]; then
  # luôn cập nhật phiên bản mới cho API key nếu được cung cấp
  if gcloud secrets describe dnu-anthropic-key >/dev/null 2>&1; then
    printf '%s' "$ANTHROPIC_API_KEY" | gcloud secrets versions add dnu-anthropic-key --data-file=- --quiet
  else
    printf '%s' "$ANTHROPIC_API_KEY" | gcloud secrets create dnu-anthropic-key --data-file=- --quiet
  fi
else
  # tạo placeholder để --set-secrets không lỗi; admin nạp key trong app sau
  ensure_secret dnu-anthropic-key ""
  warn "Chưa cung cấp ANTHROPIC_API_KEY — sẽ nạp trong app tại Cấu hình AI sau khi cài."
fi

# Lấy giá trị cron token thực tế (để tạo Scheduler) + mật khẩu admin để in ra
CRON_TOKEN_VAL="$(gcloud secrets versions access latest --secret=dnu-cron-token)"
ADMIN_PW_SHOWN="$(gcloud secrets versions access latest --secret=dnu-admin-password)"

# 5) Cấp quyền cho service account chạy Cloud Run ---------------------------
say "Cấp quyền cho service account $RUNTIME_SA..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA}" --role="roles/datastore.user" --quiet >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA}" --role="roles/secretmanager.secretAccessor" --quiet >/dev/null
gsutil iam ch "serviceAccount:${RUNTIME_SA}:roles/storage.objectAdmin" "gs://${BUCKET}" >/dev/null

# 6) Triển khai Cloud Run từ mã nguồn ---------------------------------------
say "Triển khai Cloud Run (build container + deploy, mất 3–7 phút)..."
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --min-instances 1 --max-instances 10 --memory 1Gi --cpu 1 --timeout 600 \
  --set-env-vars "APP_MODE=gcp,GCS_BUCKET=${BUCKET},GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GRADING_MODEL=${GRADING_MODEL},ADMIN_EMAILS=${ADMIN_EMAIL},DEADLINE=${DEADLINE}" \
  --set-secrets "SECRET_KEY=dnu-secret-key:latest,CRON_TOKEN=dnu-cron-token:latest,ADMIN_PASSWORD=dnu-admin-password:latest,ANTHROPIC_API_KEY=dnu-anthropic-key:latest" \
  --quiet

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"

# 7) Cloud Scheduler: nhắc hạn 24h + khóa hồ sơ đúng hạn --------------------
say "Cấu hình Cloud Scheduler (chạy mỗi 30 phút)..."
SCHED_ARGS=(--schedule="*/30 * * * *" --uri="${URL}/tasks/cron" --http-method=POST
  --headers="X-Cron-Token=${CRON_TOKEN_VAL}" --time-zone="Asia/Ho_Chi_Minh" --location="$REGION" --quiet)
if gcloud scheduler jobs describe dnu-cron --location="$REGION" >/dev/null 2>&1; then
  gcloud scheduler jobs update http dnu-cron "${SCHED_ARGS[@]}" >/dev/null || warn "Không cập nhật được Scheduler."
else
  gcloud scheduler jobs create http dnu-cron "${SCHED_ARGS[@]}" >/dev/null || warn "Không tạo được Scheduler (có thể tạo sau)."
fi

# 8) Hoàn tất ---------------------------------------------------------------
echo
say "CÀI ĐẶT HOÀN TẤT."
echo    "------------------------------------------------------------------"
echo -e "  Địa chỉ hệ thống : ${c_green}${URL}${c_off}"
echo    "  Tài khoản quản trị: ${ADMIN_EMAIL}"
echo -e "  Mật khẩu quản trị : ${c_yellow}${ADMIN_PW_SHOWN}${c_off}  (đổi ngay sau khi đăng nhập)"
echo    "------------------------------------------------------------------"
echo    "Bước tiếp theo:"
echo    "  1. Mở ${URL} và đăng nhập bằng tài khoản quản trị ở trên."
echo    "  2. Vào 'Cấu hình AI' nạp/kiểm tra Claude API key (nếu chưa đặt khi cài)."
echo    "  3. Vào 'Người dùng' → Import danh sách giảng viên (CSV mẫu trong docs/)."
echo    "  4. Kiểm tra mốc thời gian trong 'Cấu hình' (hạn nộp hiện tại: ${DEADLINE})."
