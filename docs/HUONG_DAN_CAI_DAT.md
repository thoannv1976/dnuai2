# HƯỚNG DẪN CÀI ĐẶT DNU AI-ASSESS LÊN GOOGLE CLOUD

Tài liệu hướng dẫn cài đặt phần mềm **DNU AI-Assess** lên tài khoản Google Cloud (GCP) của Trường Đại học Đại Nam. Sau khi hoàn tất, hệ thống chạy trực tuyến, dữ liệu và chi phí nằm hoàn toàn trên tài khoản của Trường.

## 1. Kiến trúc & thành phần

| Thành phần | Dịch vụ Google Cloud | Vai trò |
|---|---|---|
| Ứng dụng web | **Cloud Run** | Chạy phần mềm (đóng gói container), tự co giãn theo tải |
| Cơ sở dữ liệu | **Firestore** (Native) | Hồ sơ, điểm, người dùng, nhật ký |
| Lưu tệp | **Cloud Storage** | Sản phẩm và minh chứng của giảng viên |
| Bí mật | **Secret Manager** | API key, khóa phiên, token |
| Lập lịch | **Cloud Scheduler** | Nhắc hạn 24h, khóa hồ sơ đúng hạn |
| Chấm điểm | **Claude API** (Anthropic) | Chấm tự động theo rubric |

## 2. Chuẩn bị (một lần)

1. **Tài khoản Google Cloud của Trường** với một **Project** (ví dụ `dnuai2`) và đã **bật Billing** (thanh toán). Người thực hiện cần quyền `Owner` hoặc `Editor` + `Secret Manager Admin` trên project.
2. **Khóa Claude API** (`sk-ant-...`) lấy từ https://console.anthropic.com (mục API Keys). Có thể để sau và nạp trong phần mềm.
3. **Bộ cài** (thư mục mã nguồn này) — tải lên Cloud Shell hoặc máy đã cài Google Cloud SDK.
4. **Danh sách giảng viên** dạng CSV theo mẫu `docs/mau_import_giang_vien.csv`.

> Khuyến nghị dùng **Google Cloud Shell** (bấm biểu tượng `>_` góc trên phải Console) — đã cài sẵn `gcloud`, `gsutil`, không cần cài gì trên máy cá nhân.

## 3. Cài đặt tự động (khuyến nghị — 1 lệnh)

Trong Cloud Shell, tải bộ cài lên (kéo–thả thư mục, hoặc `git clone` nếu đặt trên Git nội bộ), rồi:

```bash
cd DNU-AI-Assess                       # vào thư mục bộ cài (có Dockerfile)
export ANTHROPIC_API_KEY="sk-ant-..."  # khóa Claude API (có thể bỏ qua, nạp sau trong app)
PROJECT_ID="dnuai2" ADMIN_EMAIL="admin@dainam.edu.vn" bash deploy/deploy.sh
```

Script sẽ tự động: bật API → tạo Firestore → tạo bucket → tạo secret (khóa phiên, token, mật khẩu admin, API key) → cấp quyền → build & deploy Cloud Run → tạo Cloud Scheduler. Mất khoảng **3–7 phút**.

Kết thúc, màn hình in ra **Địa chỉ hệ thống**, **tài khoản** và **mật khẩu quản trị** — hãy lưu lại và đổi mật khẩu sau khi đăng nhập.

Biến tùy chỉnh (đặt trước lệnh nếu cần): `REGION` (mặc định `asia-southeast1`), `SERVICE` (mặc định `dnu-ai-assess`), `BUCKET`, `GRADING_MODEL`, `ADMIN_PASSWORD`, `DEADLINE`.

## 4. Cài đặt thủ công (khi cần kiểm soát từng bước)

```bash
gcloud config set project dnuai2
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  firestore.googleapis.com storage.googleapis.com secretmanager.googleapis.com cloudscheduler.googleapis.com

# Firestore (Native) + bucket
gcloud firestore databases create --location=asia-southeast1
gsutil mb -l asia-southeast1 gs://dnuai2-dnu-ai-assess

# Secrets
printf '%s' "$(openssl rand -hex 32)" | gcloud secrets create dnu-secret-key --data-file=-
printf '%s' "$(openssl rand -hex 32)" | gcloud secrets create dnu-cron-token --data-file=-
printf '%s' "DNU-Admin@2026"          | gcloud secrets create dnu-admin-password --data-file=-
printf '%s' "sk-ant-..."              | gcloud secrets create dnu-anthropic-key --data-file=-

# Cấp quyền cho service account chạy Cloud Run
NUM=$(gcloud projects describe dnuai2 --format='value(projectNumber)')
SA="${NUM}-compute@developer.gserviceaccount.com"
gcloud projects add-iam-policy-binding dnuai2 --member="serviceAccount:$SA" --role=roles/datastore.user
gcloud projects add-iam-policy-binding dnuai2 --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor
gsutil iam ch "serviceAccount:$SA:roles/storage.objectAdmin" gs://dnuai2-dnu-ai-assess

# Deploy
gcloud run deploy dnu-ai-assess --source . --region asia-southeast1 --allow-unauthenticated \
  --min-instances 1 --memory 1Gi \
  --set-env-vars APP_MODE=gcp,GCS_BUCKET=dnuai2-dnu-ai-assess,GOOGLE_CLOUD_PROJECT=dnuai2,GRADING_MODEL=claude-opus-4-8,ADMIN_EMAILS=admin@dainam.edu.vn \
  --set-secrets SECRET_KEY=dnu-secret-key:latest,CRON_TOKEN=dnu-cron-token:latest,ADMIN_PASSWORD=dnu-admin-password:latest,ANTHROPIC_API_KEY=dnu-anthropic-key:latest

# Scheduler (thay <URL> bằng địa chỉ Cloud Run, <TOKEN> bằng giá trị dnu-cron-token)
gcloud scheduler jobs create http dnu-cron --location asia-southeast1 \
  --schedule "*/30 * * * *" --uri "<URL>/tasks/cron" --http-method POST \
  --headers "X-Cron-Token=<TOKEN>" --time-zone "Asia/Ho_Chi_Minh"
```

## 5. Sau khi cài đặt

1. Mở **Địa chỉ hệ thống**, đăng nhập tài khoản **quản trị** (email + mật khẩu in ra khi cài). Vào **Đổi mật khẩu** để đặt mật khẩu mới.
2. Vào **Cấu hình AI**: nạp/kiểm tra **Claude API key** (nếu chưa đặt khi cài), bấm **Kiểm tra kết nối Claude**.
3. Vào **Người dùng → Import (CSV)**: tải danh sách giảng viên theo mẫu `docs/mau_import_giang_vien.csv` (cột `ma_gv,ho_ten,email,khoa,bo_mon,role,password`).
4. Vào **Cấu hình**: kiểm tra mốc thời gian (mở nộp, hạn nộp). Cron tự nhắc hạn 24h và khóa hồ sơ đúng hạn.
5. Kiểm tra nhanh sức khỏe hệ thống: mở `<URL>/healthz` (trả về `{"ok": true}`).

## 6. Vận hành

- **Giảng viên** nộp hồ sơ A–G (nhiều tệp/liên kết), nộp lại trước hạn.
- **Khóa hồ sơ**: tự động lúc 17h00 30/6 (Scheduler) hoặc bấm *Khóa ngay* tại trang Vận hành.
- **Chấm**: Admin/Hội đồng vào **Thẩm định**, mở từng hồ sơ và bấm *Chấm tự động hồ sơ này* (kiểm soát tiến độ & chi phí). Theo dõi token/chi phí tại **Chi phí AI**.
- **Phê duyệt & Công bố**: Hội đồng điều chỉnh + phê duyệt; Admin *Công bố* để gửi email kết quả.
- **Bảng điểm / Tải sản phẩm**: xem/tải điểm và sản phẩm toàn trường (Excel/ZIP).

## 7. Cập nhật phiên bản (redeploy)

Khi có bản cập nhật mã nguồn, chạy lại từ thư mục bộ cài:

```bash
gcloud run deploy dnu-ai-assess --source . --region asia-southeast1
```

Dữ liệu (Firestore, Storage) được giữ nguyên qua các lần deploy.

## 8. Sao lưu dữ liệu

- Trong app: **Vận hành → Tải bản sao lưu dữ liệu (JSON)**.
- Firestore: `gcloud firestore export gs://dnuai2-dnu-ai-assess/backups/$(date +%F)`.
- Tệp: dữ liệu đã nằm trên bucket `gs://dnuai2-dnu-ai-assess`.

## 9. Chi phí vận hành (Trường tự chi trả)

- **AI (Claude API)**: ~2 USD/hồ sơ (≈ 40.000–70.000đ/giảng viên/đợt), tùy độ dài tài liệu và số lần chấm lại.
- **Google Cloud**: ~2,5–5 triệu/đợt (Cloud Run + Firestore + Storage, ~2 tháng cao điểm).
- Hạ `min-instances` về 0 ngoài đợt đánh giá để gần như không phát sinh chi phí Cloud Run:
  `gcloud run services update dnu-ai-assess --region asia-southeast1 --min-instances 0`

## 10. Bảo mật

- Mọi bí mật (API key, khóa phiên, mật khẩu admin, token) lưu trong **Secret Manager**, không nằm trong mã nguồn.
- Truy cập HTTPS mặc định của Cloud Run; phân quyền 3 vai trò; nhật ký thao tác (audit log).
- Khuyến cáo: đổi mật khẩu admin sau khi cài; cấp phát mật khẩu riêng cho từng người; nhắc giảng viên đổi mật khẩu lần đầu.

## 11. Xử lý sự cố thường gặp

| Hiện tượng | Nguyên nhân & cách xử lý |
|---|---|
| Đăng nhập báo sai mật khẩu | Xem log khởi động có dòng "Khởi động... N người dùng (N có mật khẩu)"; dùng đúng mật khẩu admin in khi cài; hoặc admin đặt lại tại Người dùng |
| Bấm chấm báo lỗi API | Vào Cấu hình AI kiểm tra/nạp lại Claude API key, bấm Kiểm tra kết nối |
| Tệp >32MB tải lên thất bại | Giới hạn request Cloud Run (~32MB). Khuyến nghị nén/chia nhỏ; bản nâng cấp upload thẳng GCS (tùy chọn) gỡ giới hạn này |
| Không tạo được Firestore | Tạo thủ công Firestore (Native mode, vùng asia-southeast1) trong Console rồi chạy lại deploy |
| Xem log lỗi | `gcloud run services logs read dnu-ai-assess --region asia-southeast1 --limit 50` |

## 12. Chạy thử trên máy (không cần GCP)

Để kiểm tra trước khi đưa lên cloud:

```bash
pip install -r requirements.txt
python scripts/seed_demo.py          # tạo tài khoản + hồ sơ demo (mật khẩu demo123)
uvicorn app.main:app --reload        # mở http://localhost:8000
```

---
*Mọi vướng mắc trong thời gian bảo hành, liên hệ đơn vị cung cấp theo thông tin trong Hợp đồng.*
