#!/usr/bin/env bash
# Đóng gói bộ cài bàn giao DNU AI-Assess thành 1 file .zip (kèm mã nguồn, tài liệu,
# script cài đặt). Chạy: bash scripts/build_bundle.sh
set -euo pipefail
cd "$(dirname "$0")/.."

VER="$(head -1 VERSION | tr ' ' '-' )"
OUT_DIR="dist"
STAGE="${OUT_DIR}/DNU-AI-Assess"
ZIP="${OUT_DIR}/DNU-AI-Assess-banbangiao.zip"

rm -rf "$STAGE" "$ZIP"
mkdir -p "$STAGE"

# Sao chép các thành phần cần bàn giao (loại trừ tệp tạm/dữ liệu/môi trường)
for item in app rubrics scripts deploy docs tests \
            Dockerfile requirements.txt requirements-gcp.txt requirements-dev.txt \
            .env.example .gitignore README.md VERSION .github; do
  [ -e "$item" ] && cp -r "$item" "$STAGE/" || true
done

# Dọn rác trong bản sao
find "$STAGE" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$STAGE" -type d -name '.pytest_cache' -prune -exec rm -rf {} + 2>/dev/null || true
find "$STAGE" -type d -name '.ruff_cache' -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf "$STAGE/data" 2>/dev/null || true

( cd "$OUT_DIR" && zip -rq "$(basename "$ZIP")" "DNU-AI-Assess" )
rm -rf "$STAGE"
echo "Đã tạo bộ cài: $ZIP ($VER)"
ls -lh "$ZIP" | awk '{print $5, $9}'
