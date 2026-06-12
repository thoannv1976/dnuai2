"""Nạp rubric chấm điểm. Rubric gốc seed từ rubrics/rubric.json; bản dùng thực tế
lưu trong DB (collection config/rubric) để quản trị viên có thể hiệu chỉnh."""
from __future__ import annotations

import json
from pathlib import Path

RUBRIC_FILE = Path(__file__).resolve().parent.parent / "rubrics" / "rubric.json"


def load_rubric_seed() -> dict:
    with open(RUBRIC_FILE, encoding="utf-8") as f:
        return json.load(f)


def get_rubric(store) -> dict:
    doc = store.get("config", "rubric")
    if not doc:
        doc = {"id": "rubric", **load_rubric_seed()}
        store.put("config", "rubric", doc)
    return doc


def part_rubric(rubric: dict, part: str) -> dict:
    return rubric["parts"][part]


def criteria_map(part_def: dict) -> dict[str, dict]:
    return {c["id"]: c for c in part_def.get("criteria", [])}
