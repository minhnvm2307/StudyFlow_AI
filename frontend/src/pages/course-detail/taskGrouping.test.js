import test from "node:test";
import assert from "node:assert/strict";

import { buildTaskDisplayTitle, buildTasksByTopic, formatTaskSchedule } from "./taskGrouping.js";

test("buildTasksByTopic routes partial-topic tasks to every scoped subtopic they cover", () => {
  const topics = [
    { id: "topic-parent", lessonId: "lesson-2" },
    { id: "topic-2-1", lessonId: "lesson-2" },
    { id: "topic-2-2", lessonId: "lesson-3" },
    { id: "topic-2-3", lessonId: "lesson-4" },
  ];
  const tasks = [
    {
      id: "task-2",
      topicId: "topic-parent",
      lessonId: "lesson-2",
      scope: "partial_topic",
      scopeItems: [{ id: "topic-2-1", title: "2.1. Co so hinh thanh tu tuong Ho Chi Minh" }],
      title: "Review: Chuong 2",
    },
    {
      id: "task-3",
      topicId: "topic-parent",
      lessonId: "lesson-3",
      scope: "partial_topic",
      scopeItems: [
        { id: "topic-2-1", title: "2.1. Co so hinh thanh tu tuong Ho Chi Minh" },
        { id: "topic-2-2", title: "2.2. Qua trinh hinh thanh va phat trien tu tuong Ho Chi Minh" },
      ],
      title: "Review: Chuong 2",
    },
    {
      id: "task-4",
      topicId: "topic-parent",
      lessonId: "lesson-4",
      scope: "partial_topic",
      scopeItems: [
        { id: "topic-2-1", title: "2.1. Co so hinh thanh tu tuong Ho Chi Minh" },
        { id: "topic-2-2", title: "2.2. Qua trinh hinh thanh va phat trien tu tuong Ho Chi Minh" },
        { id: "topic-2-3", title: "2.3. Gia tri tu tuong Ho Chi Minh" },
      ],
      title: "Review: Chuong 2",
    },
  ];

  const grouped = buildTasksByTopic(tasks, topics);

  assert.deepEqual(grouped["topic-2-1"]?.map((task) => task.id), ["task-2", "task-3", "task-4"]);
  assert.deepEqual(grouped["topic-2-2"]?.map((task) => task.id), ["task-3", "task-4"]);
  assert.deepEqual(grouped["topic-2-3"]?.map((task) => task.id), ["task-4"]);
  assert.equal(grouped["topic-parent"], undefined);
});

test("buildTasksByTopic keeps chapter-level partial reviews visible on the parent topic too", () => {
  const topics = [
    { id: "topic-parent", lessonId: "lesson-5" },
    { id: "topic-3-1", lessonId: "lesson-5" },
    { id: "topic-3-2", lessonId: "lesson-6" },
    { id: "topic-3-3", lessonId: "lesson-7" },
  ];
  const tasks = [
    {
      id: "task-parent-review",
      topicId: "topic-parent",
      parentTopicId: "topic-parent",
      lessonId: "lesson-7",
      scope: "partial_topic",
      scopeItems: [
        { id: "topic-3-1", title: "3.1. Tu tuong Ho Chi Minh ve doc lap dan toc" },
        { id: "topic-3-2", title: "3.2. Tu tuong Ho Chi Minh ve chu nghia xa hoi" },
        { id: "topic-3-3", title: "3.3. Moi quan he giua doc lap dan toc va chu nghia xa hoi" },
      ],
      title: "Review: Chuong 3",
    },
  ];

  const grouped = buildTasksByTopic(tasks, topics);

  assert.deepEqual(grouped["topic-parent"]?.map((task) => task.id), ["task-parent-review"]);
  assert.deepEqual(grouped["topic-3-1"]?.map((task) => task.id), ["task-parent-review"]);
  assert.deepEqual(grouped["topic-3-2"]?.map((task) => task.id), ["task-parent-review"]);
  assert.deepEqual(grouped["topic-3-3"]?.map((task) => task.id), ["task-parent-review"]);
});

test("buildTasksByTopic fans out whole-topic reviews to child subtopics when scopeItems are present", () => {
  const topics = [
    { id: "topic-parent", lessonId: "lesson-1" },
    { id: "topic-1-1", lessonId: "lesson-1" },
    { id: "topic-1-2", lessonId: "lesson-1" },
    { id: "topic-1-3", lessonId: "lesson-1" },
    { id: "topic-1-4", lessonId: "lesson-1" },
  ];
  const tasks = [
    {
      id: "task-topic-review",
      topicId: "topic-parent",
      parentTopicId: "topic-parent",
      lessonId: "lesson-1",
      scope: "topic",
      scopeItems: [
        { id: "topic-1-1", title: "1. Khai niem tu tuong Ho Chi Minh" },
        { id: "topic-1-2", title: "2. Doi tuong nghien cuu" },
        { id: "topic-1-3", title: "3. Phuong phap nghien cuu" },
        { id: "topic-1-4", title: "4. Y nghia hoc tap" },
      ],
      title: "Review: Chuong 1",
    },
  ];

  const grouped = buildTasksByTopic(tasks, topics);

  assert.deepEqual(grouped["topic-parent"]?.map((task) => task.id), ["task-topic-review"]);
  assert.deepEqual(grouped["topic-1-1"]?.map((task) => task.id), ["task-topic-review"]);
  assert.deepEqual(grouped["topic-1-2"]?.map((task) => task.id), ["task-topic-review"]);
  assert.deepEqual(grouped["topic-1-3"]?.map((task) => task.id), ["task-topic-review"]);
  assert.deepEqual(grouped["topic-1-4"]?.map((task) => task.id), ["task-topic-review"]);
});

test("buildTaskDisplayTitle prefers the scoped subtopic title for partial-topic tasks", () => {
  const task = {
    title: "Review: Chuong 2",
    scope: "partial_topic",
    scopeItems: [{ id: "topic-2-2", title: "2.2. Qua trinh hinh thanh va phat trien tu tuong Ho Chi Minh" }],
  };

  assert.equal(
    buildTaskDisplayTitle(task, "topic-2-2"),
    "Review: 2.2. Qua trinh hinh thanh va phat trien tu tuong Ho Chi Minh"
  );
});

test("formatTaskSchedule renders a Vietnamese date and time range", () => {
  const label = formatTaskSchedule({
    startAt: "2026-06-30T11:30:00+07:00",
    endAt: "2026-06-30T12:15:00+07:00",
  });

  assert.match(label, /30\/06\/2026/);
  assert.match(label, /11:30/);
  assert.match(label, /12:15/);
});
