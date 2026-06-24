# DANH MỤC BÀN GIAO — DNU AI-Assess

Bộ cài này là sản phẩm bàn giao theo Hợp đồng chuyển giao phần mềm (Phương án A), tương ứng **Phụ lục 02 – Danh mục bàn giao**.

| # | Hạng mục (theo Phụ lục 02) | Thành phần trong bộ cài |
|---|---|---|
| 1 | Mã nguồn đầy đủ + hướng dẫn build/triển khai | `app/`, `rubrics/`, `scripts/`, `Dockerfile`, `requirements*.txt`; hướng dẫn: `docs/HUONG_DAN_CAI_DAT.md`, `deploy/deploy.sh` |
| 2 | Hệ thống triển khai trên GCP của Trường | Script cài tự động `deploy/deploy.sh` (Cloud Run + Firestore + Storage + Secret Manager + Scheduler) |
| 3 | Bộ kiểm thử tự động (~56) + kết quả | `tests/` (chạy: `pytest -q`) |
| 4 | Tài liệu hướng dẫn vận hành | `docs/HUONG_DAN_SU_DUNG` (Word, có ảnh), `docs/HUONG_DAN_CHAY.md`, `docs/HUONG_DAN_CAI_DAT.md` |
| 5 | Biên bản tập huấn & nghiệm thu | Lập khi tập huấn/nghiệm thu (mẫu theo Hợp đồng) |

## Thành phần thư mục

```
DNU-AI-Assess/
├── app/                     Mã nguồn ứng dụng (FastAPI): nộp hồ sơ, chấm AI, thẩm định, báo cáo, quản trị
├── rubrics/rubric.json      Rubric chấm điểm (4 mức, theo đề bài DNU 2026)
├── deploy/deploy.sh         Cài đặt tự động lên Google Cloud (1 lệnh)
├── scripts/                 Tiện ích: seed demo, sinh tài liệu, đóng gói, import
├── tests/                   ~56 kiểm thử tự động
├── docs/                    Tài liệu: cài đặt, vận hành, sử dụng, danh mục bàn giao, CSV mẫu
├── Dockerfile               Đóng gói container cho Cloud Run
├── requirements*.txt        Thư viện (chạy / GCP / phát triển)
├── .env.example             Mẫu biến môi trường
└── VERSION                  Phiên bản phần mềm
```

## Cài đặt nhanh

Xem chi tiết tại `docs/HUONG_DAN_CAI_DAT.md`. Tóm tắt (trong Google Cloud Shell):

```bash
cd DNU-AI-Assess
export ANTHROPIC_API_KEY="sk-ant-..."
PROJECT_ID="<project-cua-truong>" ADMIN_EMAIL="admin@dainam.edu.vn" bash deploy/deploy.sh
```

## Kiểm thử & chạy thử

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -q                       # chạy bộ kiểm thử
python scripts/seed_demo.py && uvicorn app.main:app --reload   # chạy thử cục bộ
```

## Nghiệm thu (tiêu chí theo Điều 6 Hợp đồng)

- Hệ thống chạy đúng chức năng Phần A–G.
- Chấm tự động bằng AI theo rubric (2 lượt + trung vị, trừ minh chứng).
- Phân quyền 3 vai trò (giảng viên / hội đồng / quản trị).
- Xuất báo cáo (bảng điểm, Excel, hồ sơ năng lực) và tải sản phẩm (ZIP).
- Bộ kiểm thử tự động chạy đạt (`pytest -q`).
