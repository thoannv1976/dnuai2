"""Nghiệp vụ vận hành: khóa hồ sơ, nhắc hạn, tổng hợp điểm, phê duyệt, công bố."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.config import GRADED_PARTS, ROLE_LECTURER, get_settings, now_vn, parse_dt
from app.rubric import get_rubric
from app.services import audit
from app.services.classify import classify
from app.services.emailer import email_reminder, email_result
from app.services.validation import completeness


# ---------- mốc thời gian ----------

def get_timeline(store) -> dict:
    doc = store.get("config", "timeline")
    if not doc:
        s = get_settings()
        doc = {"id": "timeline", "deadline": s.default_deadline, "open_at": s.default_open_at,
               "reminder_sent": False, "locked_done": False}
        store.put("config", "timeline", doc)
    return doc


def deadline_passed(store, at: datetime | None = None) -> bool:
    tl = get_timeline(store)
    return (at or now_vn()) >= parse_dt(tl["deadline"])


# ---------- Bước 1: khóa hồ sơ + kiểm tra hợp lệ ----------

def lock_all(store, actor: dict | None = None) -> dict:
    counts = {"locked": 0, "invalid": 0}
    for sub in store.all("submissions"):
        if sub.get("status") in ("locked", "grading", "graded", "approved", "published"):
            continue
        summary = completeness(store, sub)
        store.patch("submissions", sub["id"], {
            "status": "locked", "locked_at": now_vn().isoformat(),
            "valid": summary["valid"], "validation": summary,
        })
        counts["locked"] += 1
        if not summary["valid"]:
            counts["invalid"] += 1
    tl = get_timeline(store)
    tl["locked_done"] = True
    store.put("config", "timeline", tl)
    audit.log(store, actor, "lock_all", "submissions", note=f"Khóa {counts['locked']} hồ sơ, {counts['invalid']} không hợp lệ")
    return counts


# ---------- Nhắc hạn 24 giờ ----------

def send_reminders(store) -> int:
    sent = 0
    for user in store.find("users", role=ROLE_LECTURER):
        sub = store.find_one("submissions", user_id=user["id"])
        if not sub:
            warnings = ["Chưa bắt đầu hồ sơ trên hệ thống"]
        else:
            if sub.get("status") not in ("draft", "submitted"):
                continue
            summary = completeness(store, sub)
            warnings = list(summary["warnings"])
            if not summary["A"]["ok"]:
                warnings.insert(0, "Phần A (thông tin chung) chưa đầy đủ: " + ", ".join(summary["A"]["missing"]))
            if sub.get("status") != "submitted":
                warnings.append("Hồ sơ chưa bấm Nộp")
        if warnings:
            email_reminder(store, user, warnings)
            sent += 1
    tl = get_timeline(store)
    tl["reminder_sent"] = True
    store.put("config", "timeline", tl)
    return sent


# ---------- Tổng hợp điểm & phê duyệt & công bố ----------

def part_totals_final(store, submission_id: str) -> dict[str, float]:
    rubric = get_rubric(store)
    scores = store.find("scores", submission_id=submission_id)
    totals: dict[str, float] = {}
    for part in GRADED_PARTS:
        part_max = rubric["parts"][part]["max_score"]
        ssum = sum(s.get("final_score") or 0 for s in scores if s["part"] == part)
        totals[part] = round(min(ssum, part_max), 2)
    return totals


def approve_submission(store, submission_id: str, reviewer: dict) -> dict:
    rubric = get_rubric(store)
    totals = part_totals_final(store, submission_id)
    total = round(sum(totals.values()), 2)
    level = classify(total, rubric)
    review = store.get("reviews", submission_id) or {"submission_id": submission_id}
    before = {"status": review.get("status"), "total_final": review.get("total_final")}
    review.update({
        "status": "approved", "approved_at": now_vn().isoformat(),
        "total_final": total, "part_totals": totals,
        "classification": level["key"], "classification_label": level["label"],
        "reviewer": reviewer["email"],
    })
    store.put("reviews", submission_id, review)
    store.patch("submissions", submission_id, {"status": "approved", "final_total": total,
                                               "classification": level["key"]})
    audit.log(store, reviewer, "approve", f"submissions/{submission_id}",
              before=before, after={"status": "approved", "total_final": total, "classification": level["key"]})
    return review


def publish_all(store, actor: dict) -> int:
    count = 0
    for review in store.find("reviews", status="approved"):
        sid = review["submission_id"]
        sub = store.get("submissions", sid)
        if not sub or sub.get("status") == "published":
            continue
        published_at = now_vn().isoformat()
        store.patch("submissions", sid, {"status": "published", "published_at": published_at})
        store.patch("reviews", sid, {"status": "published", "published_at": published_at})
        user = store.get("users", sub["user_id"])
        if user:
            detail = [f"  Phần {p}: {v:g}/{get_rubric(store)['parts'][p]['max_score']}"
                      for p, v in (review.get("part_totals") or {}).items()]
            email_result(store, user, review["total_final"], review.get("classification_label", ""), detail)
        count += 1
    audit.log(store, actor, "publish", "submissions", note=f"Công bố {count} hồ sơ")
    return count


# ---------- Phản hồi trong 3 ngày làm việc ----------

def working_days_since(start: datetime, end: datetime) -> int:
    days = 0
    d = start
    while d.date() < end.date():
        d += timedelta(days=1)
        if d.weekday() < 5:  # thứ 2..thứ 6
            days += 1
    return days


def appeal_window_open(published_at: str, at: datetime | None = None) -> bool:
    return working_days_since(parse_dt(published_at), at or now_vn()) <= 3
