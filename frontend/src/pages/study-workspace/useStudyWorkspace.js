import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { chatApi, coursesApi, flashcardsApi, quizApi, sourcesApi, topicsApi, tasksApi } from "../../services/studyflowApi.js";
import { getCourseId } from "./helpers.js";
import { buildCourseSetupFailureState } from "./setupJobState.js";
import { createQuizExplainPayload, sortFlashcards } from "./workspaceHelpers.js";

export function useStudyWorkspace() {
  const courseId = getCourseId();
  const setupQuery = useMemo(() => new URLSearchParams(window.location.search), []);
  const setupHint = useMemo(() => getSetupHint(courseId, setupQuery), [courseId, setupQuery]);
  const setupProcessingHint = setupHint.processing;
  const expectedSourceCount = setupHint.expectedSourceCount;

  const [course, setCourse] = useState(null), [sources, setSources] = useState([]), [threads, setThreads] = useState([]), [topics, setTopics] = useState([]);
  const [syllabus, setSyllabus] = useState(null);
  const [quizHistory, setQuizHistory] = useState([]), [flashcardHistory, setFlashcardHistory] = useState([]), [messages, setMessages] = useState([]);
  const [activeThreadId, setActiveThreadId] = useState(null), [sending, setSending] = useState(false), [output, setOutput] = useState(null);
  const [addSourceOpen, setAddSourceOpen] = useState(false), [addingSource, setAddingSource] = useState(false), [deletingSourceId, setDeletingSourceId] = useState(null), [sourceError, setSourceError] = useState("");
  const [uploadingSyllabus, setUploadingSyllabus] = useState(false), [syllabusError, setSyllabusError] = useState("");
  const [generationJob, setGenerationJob] = useState(() => {
    if (setupProcessingHint) {
      return {
        type: "course-setup",
        status: "loading",
        title: "Khởi tạo thiết lập...",
        subtitle: "Đang kết nối tới máy chủ...",
        progress: 5,
        syllabus: { status: "processing", percent: 0 },
        practice: { status: "pending", percent: 0 },
        schedule: { status: "pending", percent: 0 },
      };
    }
    return null;
  });
  const [quizSetupOpen, setQuizSetupOpen] = useState(false), [activeQuiz, setActiveQuiz] = useState(null), [quizAnswers, setQuizAnswers] = useState({}), [quizResult, setQuizResult] = useState(null);
  const [selfAssessmentOpen, setSelfAssessmentOpen] = useState(false), [selfAssessmentBusy, setSelfAssessmentBusy] = useState(false);
  const [quizBusy, setQuizBusy] = useState(false), [quizExplainBusy, setQuizExplainBusy] = useState(false), [quizQuestionIndex, setQuizQuestionIndex] = useState(0);
  const [activeFlashcards, setActiveFlashcards] = useState([]), [flashcardIndex, setFlashcardIndex] = useState(0), [flashcardRevealed, setFlashcardRevealed] = useState(false), [flashcardBusy, setFlashcardBusy] = useState(false);
  const [error, setError] = useState("");
  const [chunks, setChunks] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [activeTask, setActiveTask] = useState(null);
  const [activeTopicId, setActiveTopicId] = useState(null);
  const [selectedTopicIds, setSelectedTopicIds] = useState([]);
  const generationInFlight = useRef(false);
  const streamingTimerRef = useRef(null);

  const selectedSourceIds = useMemo(() => sources.filter((source) => source.selected).map((source) => source.id), [sources]);

  const updateSetupJob = useCallback((syllabusData, sourceItems, topicItems = [], forceLoading = false) => {
    const syllabusStatus = syllabusData?.syllabus?.status;
    const progress = syllabusData?.syllabus?.parsedJson?.progress || {};
    const sourceStatuses = sourceItems.map((source) => source.status);
    const missingSources = expectedSourceCount > 0 && sourceItems.length < expectedSourceCount;
    const waitingForTopics = setupProcessingHint && topicItems.length === 0;
    const isProcessing = forceLoading
      || missingSources
      || waitingForTopics
      || ["processing", "parsing", "uploaded"].includes(syllabusStatus)
      || sourceStatuses.some((status) => ["processing", "parsing", "uploaded"].includes(status));
    const isFailed = syllabusStatus === "failed" || sourceStatuses.some((status) => status === "failed");
    const parsedPercent = Number(progress.percent);
    const percent = Number.isFinite(parsedPercent) ? parsedPercent : (isFailed ? 100 : missingSources ? 8 : waitingForTopics ? 82 : 15);
    const readySources = sourceItems.filter((source) => ["ready", "parsed"].includes(source.status)).length;

    setGenerationJob((current) => {
      if (current && current.type !== "course-setup") return current;
      if (isFailed) {
        return buildCourseSetupFailureState(progress, syllabusData, sourceItems);
      }
      if (isProcessing) {
        return {
          type: "course-setup",
          status: "loading",
          title: setupTitle(progress.stage, missingSources, waitingForTopics),
          subtitle: progress.message || (waitingForTopics ? "Đang tạo topic map. Workspace sẽ tự cập nhật khi sẵn sàng." : `${readySources}/${Math.max(expectedSourceCount, sourceItems.length)} tài liệu sẵn sàng. Bạn có thể dùng workspace trong lúc chờ.`),
          progress: percent,
          progressStage: progress.stage || (waitingForTopics ? "generating_topics" : "uploaded"),
          progressDetail: progress.detail,
          sourceCount: sourceItems.length,
          readySourceCount: readySources,
          topicCount: topicItems.length,
          syllabus: progress.syllabus || { status: "processing", percent: percent },
          practice: progress.practice || { status: "pending", percent: 0 },
          schedule: progress.schedule || { status: "pending", percent: 0 },
        };
      }
      clearSetupHint(courseId);
      return null;
    });
  }, [courseId, expectedSourceCount, setupProcessingHint]);

  const loadWorkspace = useCallback(async () => {
    try {
      const [courseData, syllabusData, sourceItems, topicItems, threadItems, quizzes, flashcards, chunkItems, taskItems] = await Promise.all([
        coursesApi.getCourse(courseId),
        coursesApi.getSyllabus(courseId),
        sourcesApi.getSources(courseId),
        topicsApi.getTopics(courseId),
        chatApi.getThreads(courseId),
        quizApi.getQuizzes(courseId),
        flashcardsApi.getFlashcards(courseId),
        coursesApi.getChunks(courseId).catch(() => []),
        tasksApi.getTasks({ courseId }).catch(() => [])
      ]);
      setCourse(courseData);
      setSyllabus(syllabusData);
      setSources(sourceItems);
      setTopics(topicItems);
      setChunks(chunkItems);
      setTasks(taskItems);
      
      const taskId = setupQuery.get("task");
      const topicId = setupQuery.get("topic");
      if (taskId && taskItems?.length) {
        const matchingTask = taskItems.find(t => t.id === taskId);
        if (matchingTask) {
          setActiveTask(matchingTask);
          setActiveTopicId(matchingTask.topicId);
        }
      } else if (topicId && topicItems?.length) {
        const matchingTopic = topicItems.find(t => t.id === topicId);
        if (matchingTopic) {
          setActiveTopicId(matchingTopic.id);
          if (taskItems && taskItems.length) {
            const topicTask = taskItems.find(t => t.topicId === topicId && t.status !== "done" && t.status !== "skipped");
            if (topicTask) {
              setActiveTask(topicTask);
            }
          }
        }
      }

      updateSetupJob(syllabusData, sourceItems, topicItems, setupProcessingHint && topicItems.length === 0);
      setThreads(threadItems);
      setQuizHistory(quizzes);
      setFlashcardHistory(sortFlashcards(flashcards));
      setError("");
      const firstThread = threadItems[0];
      setActiveThreadId(firstThread?.id || null);
      setMessages(firstThread ? await chatApi.getMessages(firstThread.id) : []);
    } catch (err) {
      setError(err.message || "Không thể tải workspace.");
    }
  }, [courseId, expectedSourceCount, setupProcessingHint, updateSetupJob, setupQuery]);

  useEffect(() => {
    loadWorkspace();
  }, [loadWorkspace]);

  useEffect(() => {
    if (generationJob?.type !== "course-setup" || generationJob.status !== "loading") return undefined;
    const intervalId = window.setInterval(async () => {
      try {
        const [courseData, syllabusData, sourceItems, topicItems] = await Promise.all([
          coursesApi.getCourse(courseId),
          coursesApi.getSyllabus(courseId),
          sourcesApi.getSources(courseId),
          topicsApi.getTopics(courseId)
        ]);
        setCourse(courseData);
        setSyllabus(syllabusData);
        setSources(sourceItems);
        setTopics(topicItems);
        updateSetupJob(syllabusData, sourceItems, topicItems);
      } catch (err) {
        setError(err.message || "Không thể cập nhật trạng thái xử lý tài liệu.");
      }
    }, 3000);
    return () => window.clearInterval(intervalId);
  }, [courseId, generationJob, updateSetupJob]);

  const selectThread = async (thread) => {
    if (streamingTimerRef.current) {
      window.clearInterval(streamingTimerRef.current);
      streamingTimerRef.current = null;
    }
    setActiveThreadId(thread.id);
    setMessages(await chatApi.getMessages(thread.id));
  };

  const startNewChat = () => {
    if (streamingTimerRef.current) {
      window.clearInterval(streamingTimerRef.current);
      streamingTimerRef.current = null;
    }
    setActiveThreadId(null);
    setMessages([]);
  };

  const toggleSource = async (sourceId, selected) => {
    setSources((items) => items.map((source) => source.id === sourceId ? { ...source, selected } : source));
    try {
      await sourcesApi.updateSource(sourceId, { selected });
    } catch {
      setSources((items) => items.map((source) => source.id === sourceId ? { ...source, selected: !selected } : source));
    }
  };

  const deleteSource = async (source) => {
    const label = source.originalName || source.filename || "nguồn này";
    if (!window.confirm(`Xóa tài liệu "${label}"? Chat RAG sẽ không còn dùng nguồn này.`)) return;

    setDeletingSourceId(source.id);
    setSources((items) => items.filter((item) => item.id !== source.id));
    try {
      await sourcesApi.deleteSource(source.id);
      const [courseData, syllabusData, sourceItems, topicItems] = await Promise.all([coursesApi.getCourse(courseId), coursesApi.getSyllabus(courseId), sourcesApi.getSources(courseId), topicsApi.getTopics(courseId)]);
      setCourse(courseData);
      setSyllabus(syllabusData);
      setSources(sourceItems);
      setTopics(topicItems);
    } catch (err) {
      setError(err.message || "Không thể xóa tài liệu.");
      await loadWorkspace();
    } finally {
      setDeletingSourceId(null);
    }
  };

  const addSource = async ({ mode, files, url, title, text }) => {
    setSourceError("");
    setAddingSource(true);
    try {
      if (mode === "file") {
        if (!files.length) throw new Error("Chọn ít nhất một file DOCX/PDF/TXT.");
        await Promise.all(files.map((file) => sourcesApi.uploadFile(courseId, file)));
      }
      if (mode === "text") {
        if (!text.trim()) throw new Error("Nhập nội dung nguồn trước khi tạo.");
        await sourcesApi.createTextSource(courseId, text.trim(), title.trim() || "pasted-notes.txt");
      }
      if (mode === "web") {
        if (!url.trim()) throw new Error("Nhập website URL trước khi tạo.");
        await sourcesApi.createWebsiteSource(courseId, url.trim());
      }
      const [courseData, syllabusData, sourceItems, topicItems] = await Promise.all([coursesApi.getCourse(courseId), coursesApi.getSyllabus(courseId), sourcesApi.getSources(courseId), topicsApi.getTopics(courseId)]);
      setCourse(courseData);
      setSyllabus(syllabusData);
      setSources(sourceItems);
      setTopics(topicItems);
      setAddSourceOpen(false);
      return true;
    } catch (err) {
      setSourceError(err.message || "Không thể tạo nguồn.");
      return false;
    } finally {
      setAddingSource(false);
    }
  };

  const sendMessage = async (message) => {
    const quizInProgress = Boolean(activeQuiz && !quizResult);
    const tempUserMsg = {
      id: `temp-user-${Date.now()}`,
      role: "user",
      content: message,
      createdAt: new Date().toISOString()
    };
    
    const tempAssistantMsg = {
      id: "temp-assistant",
      role: "assistant",
      content: "",
      isThinking: true,
      createdAt: new Date().toISOString(),
      actions: []
    };

    setMessages((prev) => [...prev, tempUserMsg, tempAssistantMsg]);
    setSending(true);

    try {
      const response = await chatApi.sendMessage({
        courseId,
        threadId: activeThreadId,
        message,
        selectedSourceIds,
        context: quizInProgress ? {
          type: "quiz_in_progress",
          quizId: activeQuiz?.id,
          quizTitle: activeQuiz?.title,
          answeredCount: Object.keys(quizAnswers || {}).length,
          totalQuestions: activeQuiz?.questions?.length || 0
        } : undefined,
        topicIds: activeTask?.topicId 
          ? [activeTask.topicId] 
          : (activeTopicId ? [activeTopicId] : selectedTopicIds)
      });
      setActiveThreadId(response.threadId);
      const [threadItems, nextMessages] = await Promise.all([
        chatApi.getThreads(courseId),
        chatApi.getMessages(response.threadId)
      ]);
      setThreads(threadItems);
      setMessages(nextMessages);
    } catch (err) {
      setMessages((prev) => prev.filter(m => m.id !== "temp-assistant"));
      setError(err.message || "Không thể gửi tin nhắn.");
    } finally {
      setSending(false);
    }
  };

  const openQuiz = async (quiz) => {
    const fullQuiz = quiz.questions?.length ? quiz : await quizApi.getQuiz(quiz.id);
    setActiveQuiz(fullQuiz);
    setQuizAnswers({});
    setQuizResult(null);
    setQuizQuestionIndex(0);
  };

  const submitQuiz = async () => {
    if (!activeQuiz) return;
    setQuizBusy(true);
    try {
      const result = await quizApi.submitResult({ 
        quizId: activeQuiz.id, 
        answersByQuestionId: quizAnswers,
        taskId: activeTask?.id
      });
      setQuizResult(result);
      setQuizQuestionIndex(0);
      await loadWorkspace();
    } finally {
      setQuizBusy(false);
    }
  };

  const closeQuiz = () => { setActiveQuiz(null); setQuizAnswers({}); setQuizResult(null); setQuizQuestionIndex(0); };

  const nextQuizQuestion = () => setQuizQuestionIndex((index) => Math.min(index + 1, Math.max(0, (activeQuiz?.questions?.length || 1) - 1)));

  const previousQuizQuestion = () => setQuizQuestionIndex((index) => Math.max(0, index - 1));

  const explainQuizQuestion = async (question, index) => {
    if (!question || !activeQuiz) return;
    const payload = createQuizExplainPayload({ activeQuiz, question, index, quizAnswers });

    const tempUserMsg = {
      id: `temp-user-${Date.now()}`,
      role: "user",
      content: payload.message,
      createdAt: new Date().toISOString()
    };
    
    const tempAssistantMsg = {
      id: "temp-assistant",
      role: "assistant",
      content: "",
      isThinking: true,
      createdAt: new Date().toISOString(),
      actions: []
    };

    setMessages((prev) => [...prev, tempUserMsg, tempAssistantMsg]);
    setQuizExplainBusy(true);
    setSending(true);

    try {
      const response = await chatApi.sendMessage({
        courseId,
        threadId: activeThreadId,
        message: payload.message,
        selectedSourceIds,
        context: payload.context
      });
      setActiveThreadId(response.threadId);
      const [threadItems, nextMessages] = await Promise.all([chatApi.getThreads(courseId), chatApi.getMessages(response.threadId)]);
      setThreads(threadItems);
      setMessages(nextMessages);
    } catch (err) {
      setMessages((prev) => prev.filter(m => m.id !== "temp-assistant"));
      setError(err.message || "Không thể giải thích câu hỏi.");
    } finally {
      setQuizExplainBusy(false);
      setSending(false);
    }
  };

  const openFlashcards = (cards, index = 0) => {
    setActiveFlashcards(cards.length ? cards : flashcardHistory);
    setFlashcardIndex(Math.max(0, index));
    setFlashcardRevealed(false);
  };

  const closeFlashcards = () => { setActiveFlashcards([]); setFlashcardIndex(0); setFlashcardRevealed(false); };

  const nextFlashcard = () => {
    setFlashcardIndex((value) => (activeFlashcards.length ? (value + 1) % activeFlashcards.length : 0));
    setFlashcardRevealed(false);
  };

  const rateFlashcard = async (card, rating) => {
    setFlashcardBusy(true);
    try {
      const updated = await flashcardsApi.reviewFlashcard(card.id, rating);
      setActiveFlashcards((cards) => cards.map((item) => item.id === updated.id ? updated : item));
      setFlashcardHistory((cards) => cards.map((item) => item.id === updated.id ? updated : item));
      
      if (activeTask && activeTask.status !== "done" && card.topicId === activeTask.topicId) {
        try {
          await tasksApi.updateTask(activeTask.id, { status: "done" });
        } catch (taskErr) {
          console.error("Failed to update task status:", taskErr);
        }
      }
      
      await loadWorkspace();
      nextFlashcard();
    } finally {
      setFlashcardBusy(false);
    }
  };

  const generateQuiz = async ({ count = 20, difficulty = "medium", instructions = "" } = {}) => {
    if (generationInFlight.current || generationJob?.status === "loading") return;
    generationInFlight.current = true;
    const payload = { count, difficulty, instructions };
    setQuizSetupOpen(false);
    setGenerationJob({
      type: "quiz",
      status: "loading",
      title: "Đang tạo quiz",
      subtitle: `${count} câu hỏi · ${difficulty}`,
      retryPayload: payload
    });
    setQuizBusy(true);
    try {
      const quiz = await quizApi.generateQuiz({
        courseId,
        count,
        difficulty,
        query: instructions,
        instructions,
        selectedSourceIds,
        topicIds: activeTask?.topicId ? [activeTask.topicId] : selectedTopicIds
      });
      setGenerationJob(null);
      setOutput({ title: quiz.title, subtitle: `${quiz.questions.length} câu hỏi · bấm để làm ngay`, action: () => openQuiz(quiz) });
      setQuizHistory(await quizApi.getQuizzes(courseId));
      await openQuiz(quiz);
    } catch (err) {
      setGenerationJob({
        type: "quiz",
        status: "error",
        title: "Không thể tạo quiz",
        subtitle: "Kiểm tra tài liệu đang chọn rồi thử lại.",
        retryPayload: payload,
        error: err.message || "Không thể tạo quiz."
      });
    } finally {
      generationInFlight.current = false;
      setQuizBusy(false);
    }
  };

  const generateFlashcards = async () => {
    if (generationInFlight.current || generationJob?.status === "loading") return;
    generationInFlight.current = true;
    setGenerationJob({
      type: "flashcards",
      status: "loading",
      title: "Đang tạo flashcard",
      subtitle: "5 thẻ từ tài liệu đang chọn"
    });
    try {
      const cards = await flashcardsApi.generateFlashcards({
        courseId,
        count: 5,
        selectedSourceIds,
        topicIds: activeTask?.topicId ? [activeTask.topicId] : selectedTopicIds
      });
      setGenerationJob(null);
      setOutput({ title: "Flashcards mới", subtitle: `${cards.length} thẻ · bấm để ôn ngay`, action: () => openFlashcards(cards, 0) });
      const nextCards = await flashcardsApi.getFlashcards(courseId);
      setFlashcardHistory(sortFlashcards(nextCards));
      openFlashcards(cards, 0);
    } catch (err) {
      setGenerationJob({
        type: "flashcards",
        status: "error",
        title: "Không thể tạo flashcard",
        subtitle: "Kiểm tra tài liệu đang chọn rồi thử lại.",
        error: err.message || "Không thể tạo flashcard."
      });
    } finally {
      generationInFlight.current = false;
    }
  };

  const retryGenerationJob = () => {
    if (!generationJob || generationJob.status !== "error") return;
    if (generationJob.type === "quiz") generateQuiz(generationJob.retryPayload || {});
    if (generationJob.type === "flashcards") generateFlashcards();
    if (generationJob.type === "course-setup") loadWorkspace();
  };

  const uploadSyllabus = async (file) => {
    setSyllabusError("");
    if (!file) {
      setSyllabusError("Chọn đúng 1 file syllabus trước khi tải lên.");
      return false;
    }

    setUploadingSyllabus(true);
    try {
      await coursesApi.uploadSyllabus(courseId, file, {
        mode: "upload",
        currentWeek: syllabus?.syllabus?.currentWeek || 1,
        currentLessonNumber: syllabus?.currentLesson?.lessonNumber || syllabus?.currentLesson?.lesson_number || 1
      });
      const [courseData, syllabusData, topicItems] = await Promise.all([coursesApi.getCourse(courseId), coursesApi.getSyllabus(courseId), topicsApi.getTopics(courseId)]);
      setCourse(courseData);
      setSyllabus(syllabusData);
      setTopics(topicItems);
      return true;
    } catch (err) {
      setSyllabusError(err.message || "Không thể tải syllabus.");
      return false;
    } finally {
      setUploadingSyllabus(false);
    }
  };

  const retryUploadedSyllabus = async () => {
    setSyllabusError("");
    setUploadingSyllabus(true);
    try {
      const syllabusData = await coursesApi.retryUploadedSyllabus(courseId);
      const [courseData, sourceItems, topicItems, taskItems] = await Promise.all([
        coursesApi.getCourse(courseId),
        sourcesApi.getSources(courseId),
        topicsApi.getTopics(courseId),
        tasksApi.getTasks({ courseId }).catch(() => [])
      ]);
      setCourse(courseData);
      setSyllabus(syllabusData);
      setSources(sourceItems);
      setTopics(topicItems);
      setTasks(taskItems);
      updateSetupJob(syllabusData, sourceItems, topicItems, false);
      return true;
    } catch (err) {
      setSyllabusError(err.message || "Không thể thử lại syllabus đã upload.");
      return false;
    } finally {
      setUploadingSyllabus(false);
    }
  };

  const createSyllabusFromSources = async () => {
    setSyllabusError("");
    setUploadingSyllabus(true);
    try {
      const syllabusData = await coursesApi.createSyllabusFromSources(courseId);
      const [courseData, sourceItems, topicItems, taskItems] = await Promise.all([
        coursesApi.getCourse(courseId),
        sourcesApi.getSources(courseId),
        topicsApi.getTopics(courseId),
        tasksApi.getTasks({ courseId }).catch(() => [])
      ]);
      setCourse(courseData);
      setSyllabus(syllabusData);
      setSources(sourceItems);
      setTopics(topicItems);
      setTasks(taskItems);
      updateSetupJob(syllabusData, sourceItems, topicItems, false);
      return true;
    } catch (err) {
      setSyllabusError(err.message || "Không thể tạo syllabus từ giáo trình.");
      return false;
    } finally {
      setUploadingSyllabus(false);
    }
  };

  const generateDiagnostic = async () => {
    setQuizBusy(true);
    try {
      const quiz = await coursesApi.generateDiagnostic(courseId, { count: 5 });
      setOutput({ title: quiz.title, subtitle: `${quiz.questions.length} taught-lesson questions`, action: () => openQuiz(quiz) });
      setQuizHistory(await quizApi.getQuizzes(courseId));
      await openQuiz(quiz);
    } finally {
      setQuizBusy(false);
    }
  };

  const submitSelfAssessment = async (ratings) => {
    setSelfAssessmentBusy(true);
    try {
      await topicsApi.submitSelfAssessment(courseId, ratings);
      const [courseData, syllabusData, topicItems] = await Promise.all([coursesApi.getCourse(courseId), coursesApi.getSyllabus(courseId), topicsApi.getTopics(courseId)]);
      setCourse(courseData);
      setSyllabus(syllabusData);
      setTopics(topicItems);
      setSelfAssessmentOpen(false);
    } finally {
      setSelfAssessmentBusy(false);
    }
  };


  const answerQuiz = (questionId, answer) => {
    setQuizAnswers((items) => ({ ...items, [questionId]: answer }));
  };

  const toggleTopic = (topicId) => {
    setSelectedTopicIds((prev) =>
      prev.includes(topicId) ? prev.filter((id) => id !== topicId) : [...prev, topicId]
    );
  };

  const openAddSource = () => {
    setSourceError("");
    setAddSourceOpen(true);
  };

  return {
    activeFlashcards, activeQuiz, activeThreadId, addSource, addSourceOpen, addingSource,
    answerQuiz, closeFlashcards, closeQuiz, course, deletingSourceId, deleteSource,
    error, explainQuizQuestion, flashcardBusy, flashcardHistory, flashcardIndex,
    flashcardRevealed, generateDiagnostic, generateFlashcards, generateQuiz, generationJob, messages, nextFlashcard,
    nextQuizQuestion, openAddSource, openFlashcards, openQuiz, output, previousQuizQuestion,
    quizAnswers, quizBusy, quizExplainBusy, quizHistory, quizQuestionIndex, quizResult,
    createSyllabusFromSources, quizSetupOpen, rateFlashcard, retryGenerationJob, retryUploadedSyllabus, selectedSourceIds, selectThread, selfAssessmentBusy, selfAssessmentOpen, sendMessage, sending,
    setAddSourceOpen, setFlashcardRevealed, setQuizQuestionIndex, setQuizSetupOpen, setSelfAssessmentOpen,
    setupProcessingHint, sourceError, sources, startNewChat, submitQuiz, syllabus, syllabusError, threads, toggleSource, topics,
    submitSelfAssessment, uploadSyllabus, uploadingSyllabus,
    chunks, tasks, activeTask, setActiveTask, selectedTopicIds, toggleTopic,
    activeTopicId, setActiveTopicId
  };
}

function setupTitle(stage, missingSources, waitingForTopics) {
  if (missingSources) return "Đang ghi nhận tài liệu";
  if (waitingForTopics) return "Đang tạo topic map";
  if (stage === "extracting_text") return "Đang đọc syllabus";
  if (stage === "parsing_lessons") return "Đang tách lịch học";
  if (stage === "failed") return "Tài liệu bị lỗi";
  return "Đang xử lý syllabus và giáo trình";
}

function getSetupHint(courseId, setupQuery) {
  const urlProcessing = setupQuery.get("processing") === "1";
  const urlSourceCount = Number(setupQuery.get("sourceCount") || 0);
  const stored = readSetupHint(courseId);
  return {
    processing: urlProcessing || stored?.processing === true,
    expectedSourceCount: urlSourceCount || Number(stored?.expectedSourceCount || 0)
  };
}

function readSetupHint(courseId) {
  if (!courseId) return null;
  try {
    const raw = window.localStorage.getItem(`studyflow.setup.${courseId}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (Date.now() - Number(parsed.createdAt || 0) > 60 * 60 * 1000) {
      clearSetupHint(courseId);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function clearSetupHint(courseId) {
  if (!courseId) return;
  try {
    window.localStorage.removeItem(`studyflow.setup.${courseId}`);
  } catch {
    // Non-critical; stale hints expire after one hour.
  }
}
