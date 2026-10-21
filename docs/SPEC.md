# ilmhona CRM — техническое задание

Замена ilmhona-crm.lovable.app (анализ — `docs/ANALYSIS.md`, номера багов #N оттуда).
Пользователи: суперадмин, 3–4 сотрудника, ~5 (до 40 в базе) инструкторов. Два филиала.

## Стек и инфраструктура (как ~/Developer/my-hrm, упрощённо)

- `apps/api` — FastAPI, SQLAlchemy 2 async, Alembic, Postgres (Neon free). Python 3.14, uv.
- `apps/web` — Next.js 16 (App Router), React 19, HeroUI 2, Tailwind 4. **Только русский, без i18n.**
- Деплой: web — Vercel Hobby, API — Render free (Docker), Vercel проксирует `/api/*` с общим секретом (как my-hrm).
- Без мультитенантности, RLS, RabbitMQ, on-prem. Одна компания.
- GitHub Actions: CI (lint, tests, gitleaks), keep-alive ping API каждые 10 мин, ночной зашифрованный `pg_dump` в **приватное** хранилище (не этот репозиторий), ежедневная задача статусов.
- Репозиторий публичный: секреты только в Vercel/Render/GH Secrets; реальных персональных данных в репозитории нет, фикстуры выдуманные.

Переиспользуем из my-hrm (копировать и упростить, не писать заново): auth (JWT в httpOnly cookie + CSRF), матрица прав и редактор ролей, audit log, обработка ошибок, CI, web-оболочка (layout, тема, таблицы, формы).

## Дизайн

- Палитра старой системы: primary `#00A0DC`, accent `#D65A2F`, сайдбар `#101820`, текст `#151A1E`, шрифт Inter.
- Тёмная тема (своя): фон `#0F151B`, карточки `#161E26`, рамки `#26313C`, сайдбар `#0A0F14`, текст `#E6EDF3`, вторичный `#8B98A5`, primary заливка `#00A0DC` / текст `#38BDF0`, accent `#E26A3D`. Переключатель: светлая / тёмная / системная.
- Адаптив ПК + телефон, проверка каждого экрана на 1440 и 390 px в обеих темах.
  Телефон: нижняя навигация (4–5 пунктов + «Ещё»), таблицы → карточки, фильтры в нижнем листе, формы на весь экран, `tel:` у телефонов.

## Модель данных

Все ID — генерируемые в базе (#14). Деньги — `numeric(12,2)` TJS. Время — `Asia/Dushanbe`.

| Таблица | Поля и ограничения |
|---|---|
| `branch` | name (Душанбе, Истаравшан) |
| `room` | branch_id, name, capacity; unique(branch_id, name) |
| `app_user` | login unique (citext), full_name, phone unique null, email, branch_id null (= все филиалы), role_id, is_active, password_hash, must_change_password, temp_password_expires_at |
| `role`, `role_permission` | role_permission(role_id, section, level ∈ view/change); change ⇒ delete. Системные роли: Суперадмин (всё, не редактируется), Менеджер, Инструктор |
| `course` | name unique, direction, default_price_month, duration_months, format offline/online |
| `cohort` (поток) | code `G-NNN` unique, course_id, branch_id, instructor_id → app_user, room_id, start_date, end_date (> start), weekdays smallint[], start_time, end_time (07:00–22:00, длительность 30–240 мин, #6), capacity, price_month, status набор/активный/завершён/отменён |
| `lesson` | cohort_id, date, starts_at, ends_at, room_id; генерируется из расписания, ручное добавление/перенос; **exclusion constraint** room × tstzrange (#7) |
| `student` | full_name, gender, phone, branch_id, created_at, source_lead_id |
| `lead` | full_name, phone, course_id, source, campaign_id, branch_id, call_status, status (новый/заинтересован/нулевой урок/оплатил/отказ), needs_review bool (#15), converted_student_id, created_at |
| `enrollment` | cohort_id, student_id, status активный/завершил/выпускник/отчислен, enrolled_at; **unique(cohort_id, student_id)** (#4) |
| `attendance` | lesson_id, enrollment_id, present bool, reason; PK(lesson_id, enrollment_id) |
| `grade` | enrollment_id PK, homework 0–40, final 0–40 (check). Посещ. 20 = 20 × present / проведённые уроки (#12). Итог ≥ 70 → выпускник |
| `payment` | enrollment_id NOT NULL (#5), month_no 1–N, amount > 0, method alif/payvand/наличные, paid_at, status ожидает/подтверждено, confirmed_by |
| `campaign` | course_id, branch_id, platform, start_date, end_date, budget, status |
| `employment` | student_id, enrollment_id null, organization, employed_at — единственное место (#13) |
| `instructor_rate` | cohort_id, amount_per_month |
| `instructor_payout` | instructor_id, cohort_id, period (month), amount, paid_at — прибыль считается по ним (#9) |
| `audit_log` | user, action, entity, entity_id, diff jsonb, at |

Автоматика (ежедневная задача + при изменении): статус потока по датам (#20); при закрытии потока — пересчёт статусов зачислений (#11); дата-проверки на вводе и импорте (#8).

## Права

Разделы: Дашборд, Лиды, Студенты, Потоки, Посещаемость и оценки, Оплаты, Аудитории, Выпускники и трудоустройство, Мастер-лист, Маркетинг, Инструкторы и зарплаты, Пользователи и роли, Журнал.
Уровни: нет / просмотр / изменение (⇒ удаление).
Область: `app_user.branch_id` ограничивает все данные филиалом; роль Инструктор видит только свои потоки (жёстко, на бэке).
Инструктор: свои потоки, посещаемость и оценки, свои выплаты (просмотр), без зачисления студентов (#24).
Суперадмин создаёт роли-помощники с галочками, активирует учётки: временный пароль на 7 дней, смена при первом входе.
Каждое изменение пишет `audit_log`.

## Метрики

Один модуль `metrics` на бэке; все экраны (дашборд, мастер-лист, карточки инструкторов, выпускники) берут цифры только оттуда (#3, #22). Тест сверяет дашборд со списками на одной фикстуре.
Определения: активный студент = есть активное зачисление; выпускник = зачисление со статусом «выпускник»; доход = подтверждённые оплаты; расходы ЗП = выплаты; прибыль = доход − реклама − ЗП; CAC = реклама ÷ лиды со статусом «записан»; CPL = бюджет ÷ лиды кампании; LTV/чел = доход потока ÷ записавшиеся.

## Этапы

| # | Этап | Готово, когда |
|---|---|---|
| 0 | Каркас: репо, api + web из my-hrm, тема, вход (временный пароль 7 дней), роли и права, журнал, CI, деплой, keep-alive, бэкап | вход работает на проде, суперадмин создаёт пользователя и роль с галочками |
| 1 | Учебная часть: филиалы, аудитории, курсы, потоки + расписание уроков, студенты, зачисления; кабинет инструктора «Сегодня», посещаемость с телефона, оценки | инструктор отмечает урок с телефона за < 30 с |
| 2 | Деньги: оплаты, ставки и выплаты инструкторам, зарплаты | прибыль считается по факту выплат |
| 3 | Продажи: лиды (воронка, звонки, CSV), кампании | лид → студент в один клик |
| 4 | Отчёты: дашборд, мастер-лист, выпускники, трудоустройство, Excel | все цифры из `metrics`, тест сверки зелёный |
| 5 | Импорт: 11 листов + Supabase → чистка дублей, отчёт dry-run, перенос | отчёт расхождений согласован с руководством |
| 6 | Напоминания (Telegram) — по желанию | — |
