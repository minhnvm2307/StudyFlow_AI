import asyncio
import os
import asyncpg

async def main():
    dsn = os.getenv("DATABASE_URL", "postgresql://studyflow:studyflow@localhost:5432/studyflow")
    conn = await asyncpg.connect(dsn)
    try:
        with open("state_dump.txt", "w", encoding="utf-8") as f:
            subject_id = "course_20378ad8cc"
            subj = await conn.fetchrow("SELECT id, name, exam_date, mode FROM subjects WHERE id=$1", subject_id)
            if not subj:
                f.write(f"Subject {subject_id} not found!\n")
                return

            f.write(f"SUBJECT:\n  ID: {subj['id']}, Name: {subj['name']}, Exam: {subj['exam_date']}, Mode: {subj['mode']}\n")

            f.write(f"\nTOPICS:\n")
            topics = await conn.fetch(
                """SELECT t.id, t.title, t.learning_state, t.is_learned, t.practice_allowed, sl.starts_on AS lesson_starts_on
                   FROM topics t
                   LEFT JOIN syllabus_lessons sl ON sl.id=t.lesson_id
                   WHERE t.subject_id=$1 ORDER BY t.order_idx""",
                subject_id
            )
            for t in topics:
                f.write(f"  Topic ID: {t['id']}\n")
                f.write(f"    Title: {t['title']}\n")
                f.write(f"    State: {t['learning_state']}, Learned: {t['is_learned']}\n")
                f.write(f"    Starts: {t['lesson_starts_on']}, Practice: {t['practice_allowed']}\n")

            f.write(f"\nTASKS:\n")
            tasks = await conn.fetch(
                "SELECT id, type, title, scheduled_date, status, reason, lesson_id FROM study_tasks WHERE subject_id=$1 ORDER BY scheduled_date",
                subject_id
            )
            for r in tasks:
                f.write(f"  Task ID: {r['id']}\n")
                f.write(f"    Title: {r['title']}\n")
                f.write(f"    Type: {r['type']}, Date: {r['scheduled_date']}, Status: {r['status']}\n")
                f.write(f"    Reason: {r['reason']}\n")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
