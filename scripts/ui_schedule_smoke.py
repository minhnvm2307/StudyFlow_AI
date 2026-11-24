from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


BACKEND = "http://127.0.0.1:4000"
FRONTEND = "http://127.0.0.1:5173"
SCREENSHOT = Path("artifacts/schedule-ui-proof.png")


def main() -> None:
    user_id = f"user-ui-schedule-{uuid.uuid4().hex[:8]}"
    with sync_playwright() as p:
        api = p.request.new_context(base_url=BACKEND)
        health = api.get("/api/health")
        assert health.ok, health.text()
        auth = api.post(
            "/api/auth/register",
            headers={"content-type": "application/json"},
            data=json.dumps({
                "email": f"{user_id}@local.studyflow",
                "username": user_id,
                "password": "pass_123",
            }),
        )
        assert auth.ok, auth.text()
        auth_payload = auth.json()
        auth_headers = {
            "content-type": "application/json",
            "Authorization": f"Bearer {auth_payload['accessToken']}",
        }

        course_payload = {
            "name": "UI Schedule Smoke Course",
            "mode": "continuous",
            "priority": "high",
            "dailyGoalMinutes": 45,
            "availability": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        }
        created = api.post(
            "/api/courses",
            headers=auth_headers,
            data=json.dumps(course_payload),
        )
        assert created.ok, created.text()
        course = created.json()
        course_id = course["id"]

        tasks_response = api.get(f"/api/tasks?courseId={course_id}", headers={"Authorization": f"Bearer {auth_payload['accessToken']}"})
        assert tasks_response.ok, tasks_response.text()
        tasks = tasks_response.json()
        if not tasks:
            plan = api.post(
                f"/api/courses/{course_id}/generate-plan",
                headers=auth_headers,
                data="{}",
            )
            assert plan.ok, plan.text()
            tasks = api.get(
                f"/api/tasks?courseId={course_id}",
                headers={"Authorization": f"Bearer {auth_payload['accessToken']}"},
            ).json()
        assert tasks, "Expected generated tasks for schedule UI smoke course"

        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        session_json = json.dumps({
            "user": auth_payload["user"],
            "accessToken": auth_payload["accessToken"],
            "expiresAt": int(time.time() * 1000) + (int(auth_payload["expiresIn"]) * 1000),
        })
        context.add_init_script(
            f"window.localStorage.setItem('studyflow.currentUser', {json.dumps(session_json)})"
        )
        page = context.new_page()
        console_errors: list[str] = []
        api_requests: list[str] = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("request", lambda request: api_requests.append(request.url) if "/api/" in request.url else None)
        page.goto(f"{FRONTEND}/schedule", wait_until="networkidle")
        expect(page.locator(".calendar-event").first).to_be_visible(timeout=15000)
        expect(page.get_by_text("UI Schedule Smoke Course").first).to_be_visible(timeout=15000)
        assert any("/api/tasks" in url for url in api_requests), "Expected /schedule UI to request /api/tasks"

        SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SCREENSHOT), full_page=True)
        event_count = page.locator(".calendar-event").count()
        title_texts = page.locator(".calendar-event strong").all_inner_texts()
        print(json.dumps({
            "userId": user_id,
            "courseId": course_id,
            "apiTaskCount": len(tasks),
            "visibleEventCount": event_count,
            "visibleTitles": title_texts[:8],
            "usedTasksApi": any("/api/tasks" in url for url in api_requests),
            "usedWeeklyPlanApi": any("/api/plan/weekly" in url for url in api_requests),
            "screenshot": str(SCREENSHOT.resolve()),
            "consoleErrors": console_errors[:5],
        }, ensure_ascii=False, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
