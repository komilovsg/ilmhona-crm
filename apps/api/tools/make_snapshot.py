"""A fake old-system snapshot at the real size (for timing `python -m app.importer`):

    uv run python -m tools.make_snapshot out.json

~850 students, 90 cohorts, 900 enrollments, 650 payments, 6000 attendance rows, 60 leads,
25 campaigns, 40 instructors. Every name and phone is invented.
"""

import json
import random
import sys
from datetime import date, timedelta

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
FIRST = ["Азим", "Бахор", "Далер", "Зарина", "Ильхом", "Лола", "Мехр", "Нодира", "Орзу", "Рустам"]
LAST = ["Тестов", "Образцов", "Примеров", "Макетов", "Вымышленов", "Условный", "Пробников"]


def js(d: date) -> str:
    return (
        f"{DAYS[d.weekday()]} {MONTHS[d.month - 1]} {d.day:02d} {d.year} 12:00:00 GMT+0500 "
        "(Таджикистан)"
    )


def main(out: str) -> None:
    rng = random.Random(3)
    base = date(2025, 1, 6)
    snap: dict[str, list[dict[str, str]]] = {}
    snap["COURSES"] = [
        {
            "course_id": f"C-{k:03d}", "course_name": f"Курс{k}", "level": "0", "description": "",
            "price_per_month": str(400 + 50 * k), "duration_months": "3", "format": "Офлайн",
            "city": "Оба", "status": "Активный",
        }
        for k in range(1, 9)
    ]  # fmt: skip
    snap["INSTRUCTORS"] = [
        {
            "instructor_id": f"I-{n:03d}", "full_name": f"Инструктор{n} {LAST[n % 7]}",
            "phone": f"93{1000000 + n}", "email": "", "courses": "",
            "city": "Душанбе" if n % 2 else "Истаравшан", "salary_per_month": "1500",
            "status": "Активный",
        }
        for n in range(1, 41)
    ]  # fmt: skip
    cohorts, lessons_of = [], {}
    for n in range(90):
        slot, room = divmod(n, 12)
        start = base + timedelta(weeks=9 * slot, days=0)
        start -= timedelta(days=start.weekday())
        end = start + timedelta(weeks=8)
        city = "Душанбе" if room < 6 else "Истаравшан"
        cohorts.append(
            {
                "cohort_id": f"G-{n + 1:03d}", "course_id": f"C-{n % 8 + 1:03d}",
                "course_name": f"Курс{n % 8 + 1} 0 ({MONTHS[start.month - 1]})",
                "instructor_id": f"I-{(n % 20) * 2 + (1 if city == 'Душанбе' else 2):03d}",
                "instructor_name": "", "room": f"Аудитория {room}", "city": city,
                "start_date": js(start), "end_date": js(end), "schedule": "Пн/Чт",
                "status": "Завершён", "max_students": "20", "enrolled_count": "0",
                "telegram_link": "", "start_time": "Sun Dec 31 1899 07:05:12 GMT+0435 (Таджикистан)",
                "end_time": "Sun Dec 31 1899 08:35:12 GMT+0435 (Таджикистан)", "cost": "650",
                "duration": "2 месяца", "": "",
            }
        )  # fmt: skip
        d, ls = start, []
        while d <= end:
            if d.weekday() in (0, 3):
                ls.append(d)
            d += timedelta(days=1)
        lessons_of[f"G-{n + 1:03d}"] = ls
    snap["COHORTS"] = cohorts
    students, enrolls, pays, att = [], [], [], []
    for i in range(850):
        students.append(
            {
                "student_id": f"S-{i + 1:04d}", "lead_id": "",
                "full_name": f"{FIRST[i % 10]} {LAST[(i * 3) % 7]}{i}", "gender": "муж",
                "phone": f"93{2000000 + i}", "email": "",
                "city": "Душанбе" if i % 2 else "Истаравшан",
                "registration_date": js(base + timedelta(days=i % 300)), "status": "Активный",
                "notes": "",
            }
        )  # fmt: skip
    si = 0
    for n in range(90):
        cid = f"G-{n + 1:03d}"
        for _ in range(10):
            if len(enrolls) >= 900:
                break
            s = students[si % 850]
            si += 1
            eid = f"E-{len(enrolls) + 1:04d}"
            enrolls.append(
                {
                    "enrollment_id": eid, "student_id": s["student_id"],
                    "student_name": s["full_name"], "cohort_id": cid, "cohort_name": "",
                    "enrollment_date": js(base), "zero_lesson_date": "", "zero_lesson_attended": "",
                    "status": "Активный", "drop_reason": "", "final_score": "85",
                    "certificate_issued": "", "certificate_date": "", "employed_3m": "", "": "",
                }
            )  # fmt: skip
            for ld in lessons_of[cid][:7]:
                att.append(
                    {
                        "attendance_id": f"AT-{len(att) + 1}", "enrollment_id": eid,
                        "student_id": s["student_id"], "student_name": s["full_name"],
                        "cohort_id": cid, "lesson_date": js(ld), "lesson_number": "1",
                        "status": rng.choice(["Присутствовал", "Отсутствовал"]),
                        "instructor_note": "",
                    }
                )  # fmt: skip
    for k, e in enumerate(rng.sample(enrolls, 650)):
        pays.append(
            {
                "payment_id": f"P-{k + 1:04d}", "enrollment_id": e["enrollment_id"],
                "student_id": e["student_id"], "student_name": e["student_name"],
                "cohort_id": e["cohort_id"], "cohort_name": "", "payment_type": "Помесячно",
                "month_number": "1", "amount": "650", "payment_method": "Alif",
                "payment_date": js(base + timedelta(days=k % 200)), "screenshot_link": "",
                "verified": "Да", "verified_by": "", "notes": "",
            }
        )  # fmt: skip
    snap["STUDENTS"], snap["ENROLLMENTS"], snap["PAYMENTS"] = students, enrolls, pays
    snap["ATTENDANCE"] = att
    snap["GRADES"] = []
    snap["MARKETING"] = [
        {
            "campaign_id": f"MKT-{k:03d}", "cohort_id": f"G-{k:03d}", "course_name": "",
            "city": "Душанбе", "platform": "Facebook Ads", "start_date": js(base + timedelta(days=k)),
            "end_date": js(base + timedelta(days=k + 10)), "duration_days": "10",
            "budget_tjs": "1200", "leads_generated": "30", "cost_per_lead": "", "enrolled_students": "3",
            "cost_per_student": "", "conversion_rate": "0.10", "status": "Завершена", "notes": "",
        }
        for k in range(1, 26)
    ]  # fmt: skip
    snap["LEADS"] = [
        {
            "lead_id": f"L-{k:03d}", "timestamp": js(base + timedelta(days=k)),
            "full_name": f"Лид{k} {LAST[k % 7]}", "gender": "", "phone": f"93{3000000 + k}",
            "email": "", "Название компании": "Alpha 0", "source": "Платный", "city": "",
            "assigned_admin": "", "call_status": "Новый", "client_status": "Новый",
            "converted": "Нет", "student_id": "", "comments": "",
        }
        for k in range(1, 61)
    ]  # fmt: skip
    snap["INSTRUCTOR_PAYMENTS"] = []
    with open(out, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False)
    print({k: len(v) for k, v in snap.items()})


if __name__ == "__main__":
    main(sys.argv[1])
