import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.course_api_service import _max_semester_overlap


def test_max_semester_overlap_detects_six_simultaneous_courses():
    windows = [
        {"courseId": f"course-{index}", "startDate": date(2026, 1, 1), "endDate": date(2026, 5, 30)}
        for index in range(5)
    ]
    windows.append({"courseId": "course-6", "startDate": date(2026, 3, 1), "endDate": date(2026, 4, 15)})

    max_overlap, breach_day = _max_semester_overlap(windows)

    assert max_overlap == 6
    assert breach_day == date(2026, 3, 1)


def test_max_semester_overlap_allows_five_when_windows_do_not_stack_above_limit():
    windows = [
        {"courseId": "course-1", "startDate": date(2026, 1, 1), "endDate": date(2026, 2, 15)},
        {"courseId": "course-2", "startDate": date(2026, 1, 10), "endDate": date(2026, 2, 20)},
        {"courseId": "course-3", "startDate": date(2026, 1, 20), "endDate": date(2026, 2, 25)},
        {"courseId": "course-4", "startDate": date(2026, 2, 1), "endDate": date(2026, 3, 1)},
        {"courseId": "course-5", "startDate": date(2026, 2, 5), "endDate": date(2026, 3, 5)},
    ]

    max_overlap, breach_day = _max_semester_overlap(windows)

    assert max_overlap == 5
    assert breach_day == date(2026, 2, 5)
