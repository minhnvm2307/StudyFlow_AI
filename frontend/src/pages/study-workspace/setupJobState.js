function firstNonEmptyString(...values) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

export function buildCourseSetupFailureState(progress, syllabusData, sourceItems) {
  const failedSource = sourceItems.find((source) => source.status === "failed");
  const detail = firstNonEmptyString(
    progress?.detail,
    syllabusData?.syllabus?.parsedJson?.error,
    failedSource?.errorMessage
  );

  return {
    type: "course-setup",
    status: "error",
    title: "Chưa trích xuất xong tài liệu",
    subtitle: detail
      ? "Hệ thống gặp lỗi trong quá trình phân tích syllabus hoặc tài liệu."
      : "Một tệp xử lý lỗi. Hãy thử lại trong panel tài liệu.",
    error: detail || "Kiểm tra syllabus hoặc giáo trình bị lỗi rồi tải lại tệp.",
    progress: 100,
    syllabus: progress?.syllabus || { status: "failed", percent: 100, message: "Thất bại" },
    practice: progress?.practice || { status: "failed", percent: 0, message: "Thất bại" },
    schedule: progress?.schedule || { status: "failed", percent: 0, message: "Thất bại" },
  };
}
