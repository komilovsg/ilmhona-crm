"""Pure parsing rules of the import (docs/IMPORT.md): dates, lesson times, names, scores."""

from datetime import date, time

from app.importer import parse as p

JS = "Mon May 04 2026 12:00:00 GMT+0500 (Таджикистан)"


def test_js_date_strings_are_read_with_their_offset() -> None:
    assert p.parse_date(JS) == date(2026, 5, 4)
    # 23:30 at +00:00 is already the next day in Dushanbe (+05:00)
    assert p.parse_date("Mon May 04 2026 23:30:00 GMT+0000 (UTC)") == date(2026, 5, 5)


def test_empty_garbage_and_out_of_range_dates_are_none() -> None:
    assert p.parse_date("") is None and p.parse_date("9") is None and p.parse_date(None) is None
    assert p.parse_date("Sun Dec 31 1899 07:05:12 GMT+0435 (x)") is None  # before 2020
    assert p.parse_date("Mon May 04 2040 12:00:00 GMT+0500 (x)") is None  # after 2035 (#8)


def test_lesson_times_are_shifted_by_11_25() -> None:
    assert p.parse_clock("Sun Dec 31 1899 07:05:12 GMT+0435 (x)") == time(18, 30)
    assert p.parse_clock("Sun Dec 31 1899 05:35:12 GMT+0435 (x)") == time(17, 0)
    assert p.parse_clock("Sun Dec 31 1899 08:35:12 GMT+0435 (x)") == time(20, 0)


def test_sat_dec_30_1899_and_other_dates_are_not_lesson_times() -> None:
    assert p.parse_clock("Sat Dec 30 1899 17:10:12 GMT+0435 (x)") is None
    assert p.parse_clock(JS) is None and p.parse_clock("") is None


def test_lesson_window_rules() -> None:
    assert p.lesson_window_ok(time(18, 30), time(20, 0))
    assert not p.lesson_window_ok(time(6, 0), time(8, 0))  # before 07:00
    assert not p.lesson_window_ok(time(21, 0), time(22, 30))  # after 22:00
    assert not p.lesson_window_ok(time(10, 0), time(10, 20))  # shorter than 30 min
    assert not p.lesson_window_ok(time(8, 0), time(13, 0))  # longer than 240 min
    assert not p.lesson_window_ok(None, time(9, 0))


def test_latin_and_cyrillic_spellings_are_one_instructor() -> None:
    assert p.translit_key("Aziz Testov") == p.translit_key("Азиз Тестов")
    assert p.translit_key("Zarifkhon Olimov") == p.translit_key("Зарифхон Олимов")
    assert p.translit_key("Testov Aziz") == p.translit_key("Aziz  Testov")  # order, spaces
    assert p.translit_key("Aziz Testov") != p.translit_key("Aziz Testova")


def test_logins_are_made_from_the_name() -> None:
    assert p.slug("Aziz Testov") == "aziz.testov"
    assert p.slug("Азиз Тестов") == "aziz.testov"
    assert p.slug("") == ""


def test_phone_forms() -> None:
    assert p.phone_of("931234567") == ("+992931234567", "931234567")
    assert p.phone_of("992931234567")[0] == "+992931234567"
    assert p.phone_of("#ERROR!") == (None, "#ERROR!")
    assert p.phone_of("") == (None, "")
    assert p.phone9("+992 93 123 45 67") == p.phone9("931234567") == "931234567"
    assert p.phone9("1234") is None


def test_score_strings_are_rescaled_to_0_40() -> None:
    assert p.parse_score("score:20|20|60") == (20, 20, 60)
    assert p.parse_score("score: 5|8|9") == (5, 8, 9)
    assert (
        p.parse_score("Нет") is None
        and p.parse_score("") is None
        and p.parse_score("20|20") is None
    )
    assert p.rescale(20, p.OLD_HOMEWORK_MAX) == 40 and p.rescale(60, p.OLD_FINAL_MAX) == 40
    assert p.rescale(0, p.OLD_FINAL_MAX) == 0
    assert p.rescale(30, p.OLD_FINAL_MAX) == 20 and p.rescale(10, p.OLD_HOMEWORK_MAX) == 20
    assert p.rescale(25, p.OLD_HOMEWORK_MAX) == 40  # never above the new maximum


def test_refs_keep_the_old_id_and_tell_apart_people_with_the_same_id() -> None:
    a, b = (
        p.make_ref("STUDENTS", "S-005", "p:932222222"),
        p.make_ref("STUDENTS", "S-005", "p:933333333"),
    )
    assert (
        a != b
        and a.startswith("STUDENTS:S-005~")
        and a == p.make_ref("STUDENTS", "S-005", "p:932222222")
    )
    assert p.make_ref("COHORTS", "G-001") == "COHORTS:G-001"


def test_numbers() -> None:
    assert p.to_int("15") == 15 and p.to_int("15.0") == 15 and p.to_int("1 выше") is None
    assert str(p.to_decimal("350,50")) == "350.50" and p.to_decimal("") is None
