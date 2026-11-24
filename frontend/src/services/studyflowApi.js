import { clearCurrentSession, getAccessToken } from "./authSession.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

function isPrivateApiPath(path) {
  return path.startsWith("/api") && !path.startsWith("/api/auth");
}

function formatApiError(body, status) {
  const detail = body?.detail ?? body?.message ?? body?.error;

  if (typeof detail === "string") return detail;

  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        const path = Array.isArray(item?.loc)
          ? item.loc.filter((part) => part !== "body").join(".")
          : "";
        const message = item?.msg || item?.message || JSON.stringify(item);
        return path ? `${path}: ${message}` : message;
      })
      .join("; ");
  }

  if (detail && typeof detail === "object") {
    return detail.message || detail.msg || JSON.stringify(detail);
  }

  if (body && typeof body === "object") return JSON.stringify(body);
  return `Request failed: ${status}`;
}

async function request(path, options = {}) {
  const url = `${API_BASE_URL}${path}`;
  const headers = new Headers(options.headers || {});
  if (isPrivateApiPath(path)) {
    const token = getAccessToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }
  let response;
  try {
    response = await fetch(url, { ...options, headers });
  } catch (error) {
    throw new Error(`Cannot reach backend at ${url}. Restart dev server or open the app through the Vite URL.`);
  }
  const text = await response.text();
  let body = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = { message: text };
    }
  }

  if (!response.ok) {
    if (response.status === 401 && isPrivateApiPath(path)) {
      clearCurrentSession();
    }
    throw new Error(formatApiError(body, response.status));
  }

  return body;
}

export const authApi = {
  register(payload) {
    return request("/api/auth/register", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
  },

  login(payload) {
    const identifier = payload.identifier || payload.username || payload.email || "";
    return request("/api/auth/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...payload, identifier, username: identifier, email: identifier })
    });
  }
};

export const coursesApi = {
  getCourses() {
    return request("/api/courses");
  },

  getCourse(courseId) {
    return request(`/api/courses/${courseId}`);
  },

  getChunks(courseId) {
    return request(`/api/courses/${courseId}/chunks`);
  },

  updateCourse(courseId, payload) {
    return request(`/api/courses/${courseId}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
  },

  createCourse(payload) {
    return request("/api/courses", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
  },

  createOnboardingCourse({ course, syllabusMeta = {}, syllabusFile, sourceFiles = [] }) {
    const formData = new FormData();
    formData.append("course", JSON.stringify(course));
    formData.append("syllabusMeta", JSON.stringify(syllabusMeta));
    if (syllabusFile) formData.append("syllabus", syllabusFile);
    sourceFiles.forEach((file) => formData.append("sources", file));
    return request("/api/courses/onboarding", {
      method: "POST",
      body: formData
    });
  },

  generateTopicMap(courseId) {
    return request(`/api/courses/${courseId}/generate-topic-map`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "{}"
    });
  },

  generatePlan(courseId, payload = {}) {
    return request(`/api/courses/${courseId}/generate-plan`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
  },

  createSyllabus(courseId, payload = {}) {
    return request(`/api/courses/${courseId}/syllabus`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
  },

  uploadSyllabus(courseId, file, payload = {}) {
    const formData = new FormData();
    formData.append("file", file);
    Object.entries(payload).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        formData.append(key, typeof value === "object" ? JSON.stringify(value) : value);
      }
    });
    return request(`/api/courses/${courseId}/syllabus`, {
      method: "POST",
      body: formData
    });
  },

  getSyllabus(courseId) {
    return request(`/api/courses/${courseId}/syllabus`);
  },

  retryUploadedSyllabus(courseId) {
    return request(`/api/courses/${courseId}/syllabus/retry`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "{}"
    });
  },

  createSyllabusFromSources(courseId) {
    return request(`/api/courses/${courseId}/syllabus/from-sources`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "{}"
    });
  },

  updateCurrentLesson(courseId, payload = {}) {
    return request(`/api/courses/${courseId}/current-lesson`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
  },

  generateDiagnostic(courseId, payload = {}) {
    return request(`/api/courses/${courseId}/diagnostic-test`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
  },

  approveSyllabus(courseId, payload) {
    return request(`/api/courses/${courseId}/approve-syllabus`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
  },

  deleteCourse(courseId) {
    return request(`/api/courses/${courseId}`, {
      method: "DELETE"
    });
  }
};

export const dashboardApi = {
  getDashboard() {
    return request("/api/dashboard");
  }
};

export const tasksApi = {
  getTasks(params = {}) {
    const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value !== undefined && value !== ""));
    return request(`/api/tasks${query.toString() ? `?${query}` : ""}`);
  },

  createTask(payload) {
    return request("/api/tasks", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
  },

  updateTask(taskId, payload) {
    return request(`/api/tasks/${taskId}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
  },

  reschedule(payload = {}) {
    return request("/api/schedule/reschedule", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
  }
};

export const busyEventsApi = {
  getBusyEvents(params = {}) {
    const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value !== undefined && value !== ""));
    return request(`/api/busy-events${query.toString() ? `?${query}` : ""}`);
  },

  createBusyEvent(payload) {
    return request("/api/busy-events", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
  },

  updateBusyEvent(eventId, payload) {
    return request(`/api/busy-events/${eventId}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
  },

  deleteBusyEvent(eventId, deleteSeries = false) {
    return request(`/api/busy-events/${eventId}${deleteSeries ? "?delete_series=true" : ""}`, {
      method: "DELETE"
    });
  }
};

export const topicsApi = {
  getTopics(courseId) {
    return request(`/api/courses/${courseId}/topics`);
  },

  submitSelfAssessment(courseId, ratings) {
    return request(`/api/courses/${courseId}/self-assessment`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ratings })
    });
  }
};

export const sourcesApi = {
  getSources(courseId) {
    return request(`/api/courses/${courseId}/sources`);
  },

  updateSource(sourceId, payload) {
    return request(`/api/sources/${sourceId}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
  },

  deleteSource(sourceId) {
    return request(`/api/sources/${sourceId}`, {
      method: "DELETE"
    });
  },

  uploadFile(courseId, file) {
    const formData = new FormData();
    formData.append("file", file);
    return request(`/api/courses/${courseId}/sources`, {
      method: "POST",
      body: formData
    });
  },

  createWebsiteSource(courseId, url) {
    return request(`/api/courses/${courseId}/sources`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ url, filename: url, fileType: "web" })
    });
  },

  createTextSource(courseId, text, filename = "pasted-notes.txt") {
    return request(`/api/courses/${courseId}/sources`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ filename, fileType: "txt", text })
    });
  }
};

export const chatApi = {
  getThreads(courseId) {
    return request(`/api/courses/${courseId}/chat-threads`);
  },

  createThread(payload) {
    return request("/api/chat-threads", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
  },

  getMessages(threadId) {
    return request(`/api/chat-threads/${threadId}/messages`);
  },

  sendMessage(payload) {
    return request("/api/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
  },

  sendMessageStream(payload) {
    const url = `${API_BASE_URL}/api/chat`;
    const headers = { "content-type": "application/json" };
    const token = getAccessToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    return fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify({ ...payload, stream: true })
    });
  }
};

export const quizApi = {
  getQuizzes(courseId) {
    return request(`/api/courses/${courseId}/quizzes`);
  },

  getQuiz(quizId) {
    return request(`/api/quizzes/${quizId}`);
  },

  generateQuiz(payload) {
    return request("/api/quizzes/generate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
  },

  submitResult(payload) {
    return request("/api/quiz-results", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
  }
};

export const flashcardsApi = {
  getFlashcards(courseId) {
    return request(`/api/courses/${courseId}/flashcards`);
  },

  generateFlashcards(payload) {
    return request("/api/flashcards/generate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
  },

  createSession(payload) {
    return request("/api/flashcard-sessions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
  },

  reviewFlashcard(flashcardId, rating) {
    return request(`/api/flashcards/${flashcardId}/review`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ rating })
    });
  }
};
