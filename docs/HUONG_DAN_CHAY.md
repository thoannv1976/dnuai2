# Hướng dẫn chạy DNU AI-Assess

## 1. Chạy thử nghiệm trên máy (chế độ local)

Không cần Google Cloud — dữ liệu lưu SQLite + thư mục `data/`, đăng nhập giả lập, email ghi log.

```bash
pip install -r requirements.txt

# Tạo dữ liệu demo: 3 giảng viên + hội đồng + quản trị + 1 hồ sơ mẫu đầy đủ (docx thật)
python scripts/seed_demo.py

uvicorn app.main:app --reload
# → http://localhost:8000 — chọn tài khoản demo ở trang đăng nhập
```

**Tài khoản demo:** `gv001@dainam.edu.vn` (giảng viên, có hồ sơ mẫu) · `hoidong@dainam.edu.vn` (hội đồng) · `admin@dainam.edu.vn` (quản trị).

**Demo trọn luồng:** đăng nhập admin → *Khóa ngay* → *Bắt đầu chấm* (chờ vài giây) → đăng nhập hội đồng → thẩm định/điều chỉnh → *Phê duyệt* → admin *Công bố* → đăng nhập gv001 xem kết quả + gửi phản hồi.

### Chấm bằng Claude API thật

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export GRADING_MODEL=claude-opus-4-8   # mặc định
uvicorn app.main:app --reload
```

Không có API key → hệ thống tự dùng bộ chấm `mock` (điểm giả lập, phục vụ demo/giao diện). Ép kiểu bộ chấm bằng `GRADER=mock|claude`.

## 2. Kiểm thử

```bash
pip install -r requirements-dev.txt
ruff check app tests scripts
pytest -q          # 24 test: validation, logic 2 lượt + trung vị, phân quyền, e2e trọn luồng
```

## 3. Triển khai production (Google Cloud Run)

```bash
# Một lần: tạo Firestore (Native mode), bucket GCS, OAuth Client (Google Workspace)
gcloud run deploy dnu-ai-assess --source . --region asia-southeast1 \
  --min-instances 1 \
  --set-env-vars APP_MODE=gcp,GCS_BUCKET=<bucket>,ALLOWED_EMAIL_DOMAINS=dainam.edu.vn \
  --set-env-vars GOOGLE_OAUTH_CLIENT_ID=...,SMTP_HOST=...,SMTP_USER=...,MAIL_FROM=... \
  --set-secrets ANTHROPIC_API_KEY=anthropic-key:latest,SECRET_KEY=app-secret:latest,GOOGLE_OAUTH_CLIENT_SECRET=oauth-secret:latest,SMTP_PASSWORD=smtp-pass:latest,CRON_TOKEN=cron-token:latest
```

Cloud Scheduler (nhắc hạn 24h + khóa hồ sơ đúng 17h00 30/6):

```bash
gcloud scheduler jobs create http dnu-cron --schedule "*/30 * * * *" \
  --uri https://<service-url>/tasks/cron --http-method POST \
  --headers X-Cron-Token=<CRON_TOKEN> --time-zone "Asia/Ho_Chi_Minh"
```

Sau triển khai: vào **/admin/users** import danh sách giảng viên (CSV: `ma_gv,ho_ten,email,khoa,bo_mon,role`).

## 4. Biến môi trường chính

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `APP_MODE` | `local` | `local` (SQLite + tệp cục bộ) / `gcp` (Firestore + GCS + SSO) |
| `ANTHROPIC_API_KEY` | — | Khóa Claude API; không có → bộ chấm mock |
| `GRADING_MODEL` | `claude-opus-4-8` | Model chấm điểm |
| `GRADER` | tự động | Ép `mock` hoặc `claude` |
| `DEADLINE` | `2026-06-30T17:00:00+07:00` | Hạn nộp (admin sửa được trong /admin/config) |
| `ALLOWED_EMAIL_DOMAINS` | `dainam.edu.vn` | Domain email được phép đăng nhập SSO |
| `CRON_TOKEN` | dev | Token bảo vệ endpoint /tasks/cron |
| `DATA_DIR` | `./data` | Thư mục dữ liệu (chế độ local) |

## 5. Cấu trúc luồng nghiệp vụ

```
GV đăng nhập → kê khai Phần A → nộp sản phẩm + minh chứng B–G (tệp ≤200MB / liên kết)
   → bấm NỘP (email xác nhận; nộp lại được trước hạn — chỉ chấm bản cuối)
17h00 30/6: Cloud Scheduler khóa hồ sơ + kiểm tra hợp lệ (trước đó 24h tự nhắc mục thiếu)
Admin "Bắt đầu chấm": Claude chấm từng phần theo rubric — 2 lượt độc lập/tiêu chí,
   lệch >15% chấm lượt 3 lấy trung vị; thiếu minh chứng trừ ≤50%; đối chiếu Phần G;
   hồ sơ ≥85 hoặc bất thường → hàng đợi thẩm định bắt buộc
Hội đồng xem điểm AI + nhận xét → điều chỉnh (ghi vết) → PHÊ DUYỆT
Admin CÔNG BỐ → email kết quả từng GV → GV xem điểm/nhận xét, phản hồi trong 3 ngày làm việc
Báo cáo: dashboard theo khoa, phân loại 4 mức, xuất Excel, Hồ sơ năng lực (in/PDF), danh sách nòng cốt
```
