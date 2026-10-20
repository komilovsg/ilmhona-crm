from app.core.errors import VALIDATION_FAILED, errors

ROOM_NAME_TAKEN = errors.define("room_name_taken", 409, "Room name already used in the branch")
COURSE_NAME_TAKEN = errors.define("course_name_taken", 409, "Course name already used")
ROOM_IN_USE = errors.define("room_in_use", 409, "Room has cohorts or lessons")
COURSE_IN_USE = errors.define("course_in_use", 409, "Course has cohorts")
COHORT_IN_USE = errors.define("cohort_in_use", 409, "Cohort has enrollments")
STUDENT_IN_USE = errors.define("student_in_use", 409, "Student has enrollments")
# params: cohort (code of the cohort that holds the room), date, start, end
ROOM_BUSY = errors.define("room_busy", 409, "Room is busy at that time (#7)")
ALREADY_ENROLLED = errors.define("already_enrolled", 409, "Student is already in the cohort (#4)")
COHORT_FULL = errors.define("cohort_full", 409, "Cohort is full")
COHORT_CLOSED = errors.define("cohort_closed", 409, "Cohort is finished or cancelled")
LESSON_CANCELLED = errors.define("lesson_cancelled", 409, "Lesson is cancelled")
COHORT_NOT_CANCELLED = errors.define("cohort_not_cancelled", 409, "Cohort is not cancelled")
INSTRUCTOR_INVALID = errors.define(
    "instructor_invalid", 422, "Instructor must be an active instructor of the cohort's branch"
)
ROOM_BRANCH_MISMATCH = errors.define("room_branch_mismatch", 422, "Room is in another branch")

errors.on_constraint("room_branch_name_key", ROOM_NAME_TAKEN)
errors.on_constraint("course_name_key", COURSE_NAME_TAKEN)
errors.on_constraint("lesson_room_no_overlap", ROOM_BUSY)
errors.on_constraint("enrollment_cohort_student_key", ALREADY_ENROLLED)
errors.on_constraint("cohort_room_branch_fkey", ROOM_BRANCH_MISMATCH)
# Pydantic rejects these first; the database is the last line when something bypasses the API.
for _check in (
    "room_capacity_check",
    "course_price_check",
    "course_duration_check",
    "cohort_dates_order_check",
    "cohort_dates_range_check",
    "cohort_weekdays_check",
    "cohort_time_range_check",
    "cohort_duration_check",
    "cohort_capacity_check",
    "cohort_price_check",
    "lesson_date_check",
    "lesson_same_day_check",
    "lesson_dates_range_check",
    "lesson_time_range_check",
    "lesson_duration_check",
):
    errors.on_constraint(_check, VALIDATION_FAILED)
