import { useMemo, useState } from "react";
import { navigate } from "../../router.jsx";
import { coursesApi } from "../../services/studyflowApi.js";
import { initialForm, steps, weekdayLabels, weekdays } from "./constants.js";
import { buildOnboardingSuccessPath } from "./navigation.js";

const DAY_TO_LEGACY = Object.fromEntries(weekdays.map((day) => [day.key, day.label]));

export function useOnboardingCourse() {
  const [currentStep, setCurrentStep] = useState(0);
  const [form, setForm] = useState(initialForm);
  const [files, setFiles] = useState([]);
  const [syllabusFile, setSyllabusFile] = useState(null);
  const [skippedSources, setSkippedSources] = useState(false);
  const [errors, setErrors] = useState({});
  const [submitError, setSubmitError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const sourceCount = useMemo(() => {
    return files.length + (form.websiteUrl.trim() ? 1 : 0) + (form.pastedText.trim() ? 1 : 0);
  }, [files.length, form.websiteUrl, form.pastedText]);

  const dirty = useMemo(() => {
    return Boolean(form.name.trim() || form.examDate || form.websiteUrl.trim() || form.pastedText.trim() || files.length > 0 || syllabusFile);
  }, [files.length, form, syllabusFile]);

  const update = (patch) => {
    setForm((current) => ({ ...current, ...patch }));
    setSubmitError("");
  };

  const updateAvailabilityWindow = (index, patch) => {
    setForm((current) => ({
      ...current,
      availabilityWindows: current.availabilityWindows.map((window, itemIndex) => itemIndex === index ? { ...window, ...patch } : window)
    }));
    setSubmitError("");
  };

  const addAvailabilityWindow = (day) => {
    setForm((current) => {
      const dayWindows = current.availabilityWindows.filter((window) => window.day === day).sort((a, b) => a.start.localeCompare(b.start));
      const lastEnd = dayWindows.at(-1)?.end || current.startTime || "19:00";
      const start = lastEnd;
      const end = addMinutes(start, Number(current.sessionMinutes) || 30);
      return {
        ...current,
        availabilityWindows: sortWindows([...current.availabilityWindows, { day, start, end }])
      };
    });
    setSubmitError("");
  };

  const removeAvailabilityWindow = (index) => {
    setForm((current) => ({
      ...current,
      availabilityWindows: current.availabilityWindows.filter((_, itemIndex) => itemIndex !== index)
    }));
    setSubmitError("");
  };

  const updateClassMeeting = (index, patch) => {
    setForm((current) => ({
      ...current,
      classMeetings: sortWindows(current.classMeetings.map((meeting, itemIndex) => itemIndex === index ? { ...meeting, ...patch } : meeting))
    }));
    setSubmitError("");
  };

  const addClassMeeting = (day = "Mon") => {
    setForm((current) => ({
      ...current,
      classMeetings: sortWindows([...current.classMeetings, { day, start: "08:00", end: "09:30" }])
    }));
    setSubmitError("");
  };

  const removeClassMeeting = (index) => {
    setForm((current) => ({
      ...current,
      classMeetings: current.classMeetings.filter((_, itemIndex) => itemIndex !== index)
    }));
    setSubmitError("");
  };

  const toggleAvailabilityDay = (day) => {
    setForm((current) => {
      const hasDay = current.availabilityWindows.some((window) => window.day === day);
      if (hasDay) {
        return { ...current, availabilityWindows: current.availabilityWindows.filter((window) => window.day !== day) };
      }
      const start = current.startTime || "19:00";
      return {
        ...current,
        availabilityWindows: sortWindows([...current.availabilityWindows, { day, start, end: addMinutes(start, Number(current.sessionMinutes) || 30) }])
      };
    });
    setSubmitError("");
  };

  const validateStep = (step = currentStep) => {
    const nextErrors = {};
    if (step === 0) {
      if (!form.name.trim()) nextErrors.name = "Vui lòng nhập tên môn học.";
      if (!form.mode) nextErrors.mode = "Vui lòng chọn chế độ học.";
      if (!form.priority) nextErrors.priority = "Vui lòng chọn mức ưu tiên.";
    }
    if (step === 1) {
      const targetScore = Number(form.targetScore);
      const sessionMinutes = Number(form.sessionMinutes);
      if (form.targetScore && (targetScore < 1 || targetScore > 100)) nextErrors.targetScore = "Target nên nằm trong khoảng 1-100.";
      if (!sessionMinutes || sessionMinutes < 15) nextErrors.sessionMinutes = "Mỗi phiên nên từ 15 phút trở lên.";
      const availabilityError = validateAvailabilityWindows(form.availabilityWindows, sessionMinutes);
      if (availabilityError) nextErrors.availabilityWindows = availabilityError;
      if (form.examDate && new Date(form.examDate) < new Date(new Date().toDateString())) nextErrors.examDate = "Ngày thi không nên nằm trong quá khứ.";
    }
    if (step === 1) {
      if ((form.semesterStartDate || form.semesterEndDate) && (!form.semesterStartDate || !form.semesterEndDate)) nextErrors.semesterDates = "Chọn cả ngày bắt đầu và kết thúc kỳ học.";
      if (form.semesterStartDate && form.semesterEndDate && new Date(form.semesterEndDate) < new Date(form.semesterStartDate)) nextErrors.semesterDates = "Ngày kết thúc phải sau ngày bắt đầu.";
      if (form.semesterStartDate || form.semesterEndDate) {
        if (!form.classMeetings.length) nextErrors.classMeetings = "Thêm ít nhất một buổi học trên trường.";
        const classMeetingError = validateAvailabilityWindows(form.classMeetings, 1);
        if (classMeetingError) nextErrors.classMeetings = classMeetingError;
      }
    }
    if (step === 2 && !syllabusFile) nextErrors.syllabusText = "Upload đúng 1 file syllabus.";
    if (step === 2 && files.length < 1) nextErrors.sources = "Upload ít nhất 1 file giáo trình.";
    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const handleCancel = () => {
    if (dirty && !window.confirm("Bạn có chắc muốn hủy? Thông tin đã nhập sẽ không được lưu.")) return;
    navigate("/courses");
  };

  const handleNext = () => {
    if (!validateStep()) return;
    setCurrentStep((step) => Math.min(step + 1, steps.length - 1));
  };

  const handleBack = () => {
    setErrors({});
    setCurrentStep((step) => Math.max(step - 1, 0));
  };

  const handleSubmit = async () => {
    if (!validateStep(0) || !validateStep(1) || !validateStep(2)) return;
    setIsSubmitting(true);
    setSubmitError("");

    const availabilityWindows = sortWindows(form.availabilityWindows);
    const availability = legacyAvailability(availabilityWindows);
    const preferredStartTime = availabilityWindows[0]?.start || form.startTime;

    try {
      const coursePayload = {
        name: form.name.trim(),
        mode: form.mode,
        priority: form.priority,
        targetScore: form.targetScore ? Number(form.targetScore) : undefined,
        examDate: form.examDate || undefined,
        autoGeneratePlan: false,
        availability,
        availabilityWindows,
        sessionMinutes: Number(form.sessionMinutes),
        preferredStartTime
      };

      const syllabusPayload = {
        mode: "upload",
        currentWeek: form.currentWeek ? Number(form.currentWeek) : undefined,
        currentLessonNumber: form.currentLessonNumber ? Number(form.currentLessonNumber) : undefined,
        joinPosition: Number(form.currentWeek || 1) > 1 ? "mid_semester" : "beginning"
      };
      if (form.semesterStartDate && form.semesterEndDate) {
        syllabusPayload.semesterStartDate = form.semesterStartDate;
        syllabusPayload.semesterEndDate = form.semesterEndDate;
        syllabusPayload.classMeetings = sortWindows(form.classMeetings);
        syllabusPayload.useCalendarProgress = true;
      }
      const result = await coursesApi.createOnboardingCourse({
        course: coursePayload,
        syllabusMeta: syllabusPayload,
        syllabusFile,
        sourceFiles: files
      });
      const course = result.course || result;
      const expectedSourceCount = Number(result.sourceCount || files.length || 0);
      saveSetupHint(course.id, expectedSourceCount);

      navigate(buildOnboardingSuccessPath(course.id, expectedSourceCount));
    } catch (error) {
      setSubmitError(error.message || "Không thể tạo môn học. Kiểm tra backend rồi thử lại.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return {
    currentStep,
    dirty,
    errors,
    files,
    form,
    isLastStep: currentStep === steps.length - 1,
    isSubmitting,
    setFiles,
    setSyllabusFile,
    setSkippedSources,
    skippedSources,
    sourceCount,
    submitError,
    syllabusFile,
    addAvailabilityWindow,
    addClassMeeting,
    handleBack,
    handleCancel,
    handleNext,
    handleSubmit,
    removeAvailabilityWindow,
    removeClassMeeting,
    toggleAvailabilityDay,
    update,
    updateAvailabilityWindow,
    updateClassMeeting
  };
}

function saveSetupHint(courseId, expectedSourceCount) {
  if (!courseId) return;
  try {
    window.localStorage.setItem(`studyflow.setup.${courseId}`, JSON.stringify({
      processing: true,
      expectedSourceCount,
      createdAt: Date.now()
    }));
  } catch {
    // URL params still carry the setup hint when storage is unavailable.
  }
}

function validateAvailabilityWindows(windows, sessionMinutes) {
  if (!windows.length) return "Chọn ít nhất một khung giờ rảnh.";
  const byDay = new Map();
  for (const window of windows) {
    const start = minutesFromTime(window.start);
    const end = minutesFromTime(window.end);
    if (start === null || end === null) return "Khung giờ cần đúng định dạng giờ.";
    if (end <= start) return "Giờ kết thúc phải sau giờ bắt đầu.";
    if (end - start < sessionMinutes) return "Mỗi khung giờ cần đủ dài cho một phiên học.";
    const list = byDay.get(window.day) || [];
    list.push({ start, end, label: weekdayLabels[window.day] || window.day });
    byDay.set(window.day, list);
  }
  for (const list of byDay.values()) {
    list.sort((a, b) => a.start - b.start);
    for (let index = 1; index < list.length; index += 1) {
      if (list[index].start < list[index - 1].end) return `Khung giờ ${list[index].label} đang bị chồng nhau.`;
    }
  }
  return "";
}

function sortWindows(windows) {
  const dayOrder = Object.fromEntries(weekdays.map((day, index) => [day.key, index]));
  return [...windows].sort((a, b) => (dayOrder[a.day] - dayOrder[b.day]) || a.start.localeCompare(b.start));
}

function legacyAvailability(windows) {
  return windows.reduce((days, window) => {
    const label = DAY_TO_LEGACY[window.day];
    if (label && !days.includes(label)) days.push(label);
    return days;
  }, []);
}

function minutesFromTime(value) {
  const match = /^(\d{2}):(\d{2})$/.exec(value || "");
  if (!match) return null;
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (hours > 23 || minutes > 59) return null;
  return hours * 60 + minutes;
}

function addMinutes(value, minutesToAdd) {
  const minutes = minutesFromTime(value) ?? 19 * 60;
  const next = Math.min(23 * 60 + 59, minutes + minutesToAdd);
  return `${String(Math.floor(next / 60)).padStart(2, "0")}:${String(next % 60).padStart(2, "0")}`;
}
