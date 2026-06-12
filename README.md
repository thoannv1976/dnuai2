# DNU AI-Assess

Hệ thống tiếp nhận hồ sơ và **chấm điểm tự động bằng AI** phục vụ Chương trình khảo sát, đánh giá năng lực ứng dụng AI của giảng viên **Trường Đại học Đại Nam (DNU) năm 2026**.

## Chức năng chính

- **Nộp hồ sơ trực tuyến** theo cấu trúc Phần A–G: kê khai thông tin, tải sản phẩm và minh chứng sử dụng AI, kiểm tra hợp lệ thời gian thực, nộp lại trước hạn (17h00 ngày 30/6/2026).
- **Chấm tự động bằng Claude API** theo rubric của đề bài: mỗi tiêu chí chấm 2 lượt độc lập, chênh lệch >15% chấm lượt thứ 3 và lấy trung vị; tự động đối chiếu minh chứng Phần G.
- **Thẩm định bởi Hội đồng**: điều chỉnh và phê duyệt điểm AI đề xuất, ghi vết đầy đủ (audit log), xử lý phản hồi của giảng viên.
- **Báo cáo**: dashboard tiến độ theo khoa/bộ môn, phân loại 4 mức năng lực, xuất báo cáo toàn trường và Hồ sơ năng lực AI từng giảng viên (PDF).
- **Quản trị**: danh sách giảng viên, cấu hình rubric/mốc thời gian, vận hành chấm, sao lưu.

## Công nghệ

| Thành phần | Công nghệ |
|---|---|
| Backend | Python 3.12 · FastAPI |
| Frontend | Jinja2 · TailwindCSS · Alpine.js · Chart.js (tiếng Việt, responsive) |
| Chấm AI | Claude API (`claude-opus-4-8`, structured outputs, Batches API) |
| Dữ liệu | Firestore + Google Cloud Storage (production) · SQLite + thư mục cục bộ (dev) |
| Xác thực | Google Workspace SSO (email DNU) · 3 vai trò: giảng viên / hội đồng / quản trị |
| Triển khai | Docker · Google Cloud Run · Cloud Scheduler |

## Tài liệu

- 📋 **[Kế hoạch xây dựng chi tiết](docs/KE_HOACH_XAY_DUNG.md)** — kiến trúc, mô hình dữ liệu, thiết kế engine chấm, lộ trình, rủi ro.

## Trạng thái

🟡 **Giai đoạn lập kế hoạch** — kế hoạch đã hoàn thành, chờ phê duyệt để bắt đầu Giai đoạn 0 (khung dự án). Mốc go-live: **22/6/2026**.
