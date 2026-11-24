function taskTargetsSubtopics(task) {
  return task?.scope === "partial_topic" || task?.isPartialTopic;
}

export function buildTasksByTopic(tasks = [], topics = []) {
  const topicById = new Map(topics.map((topic) => [topic.id, topic]));
  // Build childrenByParent once in O(topics) — all subsequent lookups are O(1)
  const childrenByParent = new Map();
  topics.forEach((topic) => {
    if (topic.parentTopicId) {
      if (!childrenByParent.has(topic.parentTopicId)) {
        childrenByParent.set(topic.parentTopicId, []);
      }
      childrenByParent.get(topic.parentTopicId).push(topic);
    }
  });

  const map = {};

  tasks.forEach((task) => {
    const scopedTopicIds = (task.scopeItems || [])
      .map((item) => item?.id)
      .filter((id) => id && topicById.has(id));

    // Use a Set for deduplication throughout to avoid O(N) .includes() calls
    const targetSet = new Set();

    if (scopedTopicIds.length) {
      if (task.parentTopicId && topicById.has(task.parentTopicId)) {
        targetSet.add(task.parentTopicId);
      }
      scopedTopicIds.forEach((id) => targetSet.add(id));
    } else {
      const mainTopicId = task.topicId || "unmapped";
      targetSet.add(mainTopicId);
      // Add all direct children of the main topic (O(children) per task, not O(topics))
      if (mainTopicId !== "unmapped") {
        const children = childrenByParent.get(mainTopicId);
        if (children) {
          children.forEach((child) => targetSet.add(child.id));
        }
      }
      if (task.parentTopicId && topicById.has(task.parentTopicId)) {
        targetSet.add(task.parentTopicId); // Set handles dedup in O(1)
      }
    }

    targetSet.forEach((id) => {
      if (!map[id]) map[id] = [];
      map[id].push(task);
    });
  });

  return map;
}

export function buildTaskDisplayTitle(task, topicId) {
  if (!taskTargetsSubtopics(task)) return task?.title || "";
  const scoped = (task.scopeItems || []).find((item) => item?.id === topicId);
  if (!scoped?.title) return task?.title || "";
  const prefix = /^([^:]+:\s*)/.exec(task.title || "")?.[1] || "";
  return `${prefix}${scoped.title}`;
}

export function formatTaskSchedule(task) {
  const startAt = task?.startAt ? new Date(task.startAt) : null;
  const endAt = task?.endAt ? new Date(task.endAt) : null;
  if (!startAt || Number.isNaN(startAt.getTime())) return "";

  const dayLabel = startAt.toLocaleDateString("vi-VN", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
  const startTime = startAt.toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
  });
  if (!endAt || Number.isNaN(endAt.getTime())) {
    return `${dayLabel} • ${startTime}`;
  }
  const endTime = endAt.toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${dayLabel} • ${startTime} - ${endTime}`;
}
