"""Local-only load dataset (fake names) sized like the real database:
~850 students, 90 cohorts, ~1400 lessons, ~900 enrollments, ~6000 attendance marks, ~650 payments,
~60 leads, 25 campaigns, 40 instructors, 20k audit rows.

    DATABASE_URL=postgresql+asyncpg://ilm@localhost:55433/<db> uv run python -m tools.seed_load

Refuses any host but localhost and any database that already holds students.
"""

import asyncio
import random
import sys
import uuid
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, insert, select, text
from sqlalchemy.engine import make_url

from app.cohorts.status import status_for, today
from app.core.config import settings
from app.core.db import engine, sessionmaker
from app.core.security import hash_password
from app.models import (
    AppUser,
    Attendance,
    AuditLog,
    Campaign,
    Cohort,
    Course,
    Employment,
    Enrollment,
    Grade,
    InstructorPayout,
    Lead,
    Lesson,
    Payment,
    RefreshToken,
    Room,
    Student,
)

PASSWORD = "Load-test-pass-1"
FIRST = ["Азим", "Бахор", "Далер", "Зарина", "Ильхом", "Лола", "Мехр", "Нодира", "Орзу", "Рустам"]
LAST = ["Тестов", "Образцов", "Примеров", "Макетов", "Вымышленов", "Условный", "Пробников"]


def uid() -> uuid.UUID:
    return uuid.uuid4()


async def main() -> None:
    url = make_url(settings.database_url)
    if url.host not in ("localhost", "127.0.0.1"):
        sys.exit("seed_load runs on a local database only")
    rng = random.Random(7)
    now_day = today()
    pw = hash_password(PASSWORD)
    async with sessionmaker() as db:
        if (await db.execute(select(func.count()).select_from(Student))).scalar_one():
            sys.exit("database already holds students")
        roles = dict(
            (await db.execute(text("SELECT code, id FROM role WHERE code IS NOT NULL"))).all()
        )
        branches = [
            r[0] for r in (await db.execute(text("SELECT id FROM branch ORDER BY name"))).all()
        ]

        users: list[dict[str, Any]] = []

        def user(login: str, name: str, code: str, branch: Any, n: int) -> uuid.UUID:
            i = uid()
            users.append(
                {
                    "id": i,
                    "login": login,
                    "full_name": name,
                    "phone": f"+99290{n:07d}",
                    "branch_id": branch,
                    "role_id": roles[code],
                    "password_hash": pw,
                    "default_rate": Decimal("1500"),
                }
            )
            return i

        admin = user("load_admin", "Нагрузка Админов", "superadmin", None, 1)
        managers = [
            user(f"load_mgr{b}", f"Менеджер Образцов {b}", "manager", branches[b], 10 + b)
            for b in range(2)
        ]
        instructors = [
            (
                user(
                    f"load_ins{n}",
                    f"Инструктор {LAST[n % 7]} {n}",
                    "instructor",
                    branches[n % 2],
                    100 + n,
                ),
                n % 2,
            )
            for n in range(40)
        ]
        await db.execute(insert(AppUser), users)

        courses = [
            {
                "id": uid(),
                "name": f"Курс {k}",
                "direction": "IT",
                "default_price_month": Decimal(400 + 50 * k),
                "duration_months": 3,
                "format": "offline",
            }
            for k in range(8)
        ]
        await db.execute(insert(Course), courses)
        rooms = [
            {"id": uid(), "branch_id": branches[b], "name": f"Аудитория {b}-{k}", "capacity": 14}
            for b in range(2)
            for k in range(6)
        ]
        await db.execute(insert(Room), rooms)

        # 12 rooms x ~7.5 slots one after another (no overlap), 16 lessons per cohort
        base = now_day - timedelta(weeks=66)
        base -= timedelta(days=base.isoweekday() - 1)
        cohort_rows: list[dict[str, Any]] = []
        lesson_rows: list[dict[str, Any]] = []
        cohort_info: list[Any] = []
        for n in range(90):
            room = rooms[n % 12]
            start = base + timedelta(weeks=9 * (n // 12))
            end = start + timedelta(weeks=8)
            course = courses[n % 8]
            b = 0 if room["branch_id"] == branches[0] else 1
            ins = [i for i, bb in instructors if bb == b][n % 20]
            cid = uid()
            cohort_rows.append(
                {
                    "id": cid,
                    "code": f"L-{n + 1:03d}",
                    "course_id": course["id"],
                    "branch_id": room["branch_id"],
                    "instructor_id": ins,
                    "room_id": room["id"],
                    "start_date": start,
                    "end_date": end,
                    "weekdays": [1, 4],
                    "start_time": time(10),
                    "end_time": time(11, 30),
                    "capacity": 14,
                    "price_month": course["default_price_month"],
                    "instructor_rate": Decimal("1500"),
                    "status": status_for(start, end, now_day),
                }
            )
            cohort_info.append((cid, start, end, room, ins, course, b))
            d, made = start, 0
            while made < 16:
                if d.isoweekday() in (1, 4):
                    s = datetime.combine(d, time(5, 0), tzinfo=UTC)  # 10:00 in Dushanbe (UTC+5)
                    lesson_rows.append(
                        {
                            "id": uid(),
                            "cohort_id": cid,
                            "room_id": room["id"],
                            "lesson_date": d,
                            "starts_at": s,
                            "ends_at": s + timedelta(minutes=90),
                            "source": "generated",
                        }
                    )
                    made += 1
                d += timedelta(days=1)
        await db.execute(insert(Cohort), cohort_rows)
        await db.execute(insert(Lesson), lesson_rows)

        students = [
            {
                "id": uid(),
                "full_name": f"{FIRST[i % 10]} {LAST[(i * 3) % 7]} {i}",
                "gender": "female" if i % 2 else "male",
                "phone": f"+99293{i:07d}",
                "branch_id": branches[i % 2],
            }
            for i in range(850)
        ]
        await db.execute(insert(Student), students)

        by_cohort: dict[Any, list[Any]] = {}
        for ls in lesson_rows:
            by_cohort.setdefault(ls["cohort_id"], []).append(ls)
        enr_rows: list[dict[str, Any]] = []
        att_candidates: list[Any] = []
        si = 0
        for cid, start, end, _room, ins, _course, _b in cohort_info:
            for _ in range(10):
                if len(enr_rows) >= 900:
                    break
                st = students[si % 850]
                si += 1
                e = {
                    "id": uid(),
                    "cohort_id": cid,
                    "student_id": st["id"],
                    "status": "активный",
                    "enrolled_at": datetime.combine(start, time(9), tzinfo=UTC),
                }
                if end < now_day:
                    e["status"] = rng.choice(["выпускник", "выпускник", "завершил"])
                enr_rows.append(e)
                for ls in by_cohort[cid]:
                    if ls["lesson_date"] < now_day:
                        att_candidates.append((ls["id"], e["id"], ins))
        await db.execute(insert(Enrollment), enr_rows)
        rng.shuffle(att_candidates)
        att_rows = []
        for lid, eid, ins in att_candidates[:6000]:
            present = rng.random() < 0.8
            att_rows.append(
                {
                    "lesson_id": lid,
                    "enrollment_id": eid,
                    "present": present,
                    "reason": None if present else "болезнь",
                    "marked_by": ins,
                }
            )
        await db.execute(insert(Attendance), att_rows)
        await db.execute(
            insert(Grade),
            [
                {
                    "enrollment_id": e["id"],
                    "homework": rng.randint(20, 40),
                    "final": rng.randint(15, 40) if e["status"] != "активный" else None,
                }
                for e in enr_rows
                if rng.random() < 0.7
            ],
        )

        info = {c[0]: c for c in cohort_info}
        pay_rows: list[dict[str, Any]] = []
        for e in rng.sample(enr_rows, 400):
            c = info[e["cohort_id"]]
            for month_no in range(1, rng.choice([1, 2, 3]) + 1):
                paid = min(c[1] + timedelta(days=30 * (month_no - 1) + rng.randint(0, 9)), now_day)
                ok = rng.random() < 0.8
                pay_rows.append(
                    {
                        "id": uid(),
                        "enrollment_id": e["id"],
                        "month_no": month_no,
                        "amount": c[5]["default_price_month"],
                        "method": rng.choice(["alif", "payvand", "наличные"]),
                        "paid_at": paid,
                        "status": "подтверждено" if ok else "ожидает",
                        "confirmed_by": managers[0] if ok else None,
                        "confirmed_at": datetime.combine(paid, time(12), tzinfo=UTC)
                        if ok
                        else None,
                        "idempotency_key": uid(),
                    }
                )
        pay_rows = pay_rows[:650]
        await db.execute(insert(Payment), pay_rows)
        payouts = []
        for cid, start, end, _room, ins, _course, _b in cohort_info:
            if end < now_day:
                for k in range(3):
                    p = (start.replace(day=1) + timedelta(days=32 * k)).replace(day=1)
                    payouts.append(
                        {
                            "id": uid(),
                            "instructor_id": ins,
                            "cohort_id": cid,
                            "period": p,
                            "amount": Decimal("1500"),
                            "paid_at": min(p + timedelta(days=27), now_day),
                            "method": "наличные",
                        }
                    )
        await db.execute(insert(InstructorPayout), payouts)

        camps = [
            {
                "id": uid(),
                "name": f"Кампания {k}",
                "course_id": courses[k % 8]["id"],
                "branch_id": branches[k % 2],
                "platform": rng.choice(["Facebook Ads", "Instagram", "TikTok", "Telegram"]),
                "start_date": now_day - timedelta(days=200 - 7 * k),
                "budget": Decimal(500 + 40 * k),
                "status": "активна",
            }
            for k in range(25)
        ]
        await db.execute(insert(Campaign), camps)
        leads = [
            {
                "id": uid(),
                "full_name": f"{FIRST[k % 10]} {LAST[k % 7]} лид{k}",
                "raw_name": f"лид{k}",
                "phone": f"+99291{k:07d}",
                "phone_raw": f"+99291{k:07d}",
                "course_id": courses[k % 8]["id"],
                "source": rng.choice(["Facebook", "Instagram", "TikTok", "Telegram", "сайт"]),
                "campaign_id": camps[k % 25]["id"],
                "branch_id": branches[k % 2],
                "status": rng.choice(["новый", "заинтересован", "нулевой урок", "отказ"]),
            }
            for k in range(60)
        ]
        await db.execute(insert(Lead), leads)
        grads = [e for e in enr_rows if e["status"] == "выпускник"]
        await db.execute(
            insert(Employment),
            [
                {
                    "id": uid(),
                    "student_id": e["student_id"],
                    "enrollment_id": e["id"],
                    "organization": "ООО Тест",
                    "position": "разработчик",
                    "employed_at": now_day - timedelta(days=rng.randint(1, 100)),
                }
                for e in grads[:150]
            ],
        )

        actions = [
            ("student.update", "student", students),
            ("payment.confirm", "payment", pay_rows),
            ("cohort.update", "cohort", cohort_rows),
            ("lead.update", "lead", leads),
            ("student.create", "student", students),
        ]
        audit = []
        for k in range(20000):
            action, entity, pool = actions[k % 5]
            row = pool[rng.randrange(len(pool))]
            audit.append(
                {
                    "user_id": rng.choice([admin, *managers]),
                    "action": action,
                    "entity": entity,
                    "entity_id": str(row["id"]),
                    "branch_id": branches[k % 2],
                    "diff": {"full_name": ["Старое", "Новое"], "status": ["a", "b"]},
                    "label": str(row.get("full_name") or row.get("code") or row["id"]),
                    "at": datetime.now(UTC) - timedelta(minutes=k * 17),
                }
            )
        await db.execute(insert(AuditLog), audit)
        # sessions rotate their refresh token every access-token lifetime and nothing purges them:
        # a few months of 44 users leave tens of thousands of rows
        tokens = [
            {
                "user_id": users[k % len(users)]["id"],
                "family_id": uid(),
                "token_hash": uuid.uuid4().bytes + uuid.uuid4().bytes,
                "expires_at": datetime.now(UTC) + timedelta(days=30),
                "used_at": datetime.now(UTC) if k % 3 else None,
                "revoked_at": datetime.now(UTC) if k % 5 else None,
            }
            for k in range(40000)
        ]
        for i in range(0, len(tokens), 4000):
            await db.execute(insert(RefreshToken), tokens[i : i + 4000])
        await db.commit()
        for t in (
            "student",
            "cohort",
            "lesson",
            "enrollment",
            "attendance",
            "payment",
            "lead",
            "campaign",
            "app_user",
            "audit_log",
        ):
            print(t, (await db.execute(text(f"SELECT count(*) FROM {t}"))).scalar_one())
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text("ANALYZE"))
    await engine.dispose()
    print("login load_admin /", PASSWORD)


if __name__ == "__main__":
    asyncio.run(main())
