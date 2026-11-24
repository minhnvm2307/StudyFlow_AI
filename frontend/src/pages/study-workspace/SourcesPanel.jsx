import { useEffect, useState } from "react";
import { AlertCircle, CalendarDays, CheckCircle2, ChevronLeft, ChevronsLeft, ChevronsRight, FileText, Loader2, MessageSquare, Plus, Trash2, Upload, BookOpen } from "lucide-react";
import { Button, SearchInput } from "../../components/common.jsx";

function sourceLabel(source) {
  return source.originalName || source.filename || "tài liệu";
}

function sourceStatus(source) {
  const status = source.status || "parsing";
  if (["ready", "parsed"].includes(status)) return { label: "Đã sẵn sàng", tone: "ready", Icon: CheckCircle2 };
  if (status === "failed") return { label: "Bị lỗi", tone: "failed", Icon: AlertCircle };
  return { label: "Đang xử lý", tone: "loading", Icon: Loader2 };
}

function SourceItem({ source, onToggle, onDelete, deleting }) {
  const status = sourceStatus(source);
  const StatusIcon = status.Icon;
  return (
    <div className={`source-item-card source-status-${status.tone}`}>
      <div className="source-item">
        <input type="checkbox" checked={source.selected} onChange={(event) => onToggle(source.id, event.target.checked)} aria-label={sourceLabel(source)} />
        <div>
          <strong><FileText size={15} /><span className="source-name">{sourceLabel(source)}</span></strong>
          <span className="source-status-line"><StatusIcon size={13} />{source.fileType} - {status.label}</span>
          {source.status === "failed" && source.errorMessage ? <small className="source-error-text">{source.errorMessage}</small> : null}
        </div>
        <button type="button" className="source-delete-btn" onClick={() => onDelete(source)} disabled={deleting} aria-label={`Xóa ${sourceLabel(source)}`} title="Xóa tài liệu">
          <Trash2 size={16} />
        </button>
      </div>
    </div>
  );
}

function sourceIsWorking(source) {
  return ["processing", "parsing", "uploaded"].includes(source.status);
}

function SourcesTab({ sources, syllabus, setupJob, uploadingSyllabus, onToggle, onAddSource, onDeleteSource, deletingSourceId }) {
  const syllabusRecord = setupSyllabusRecord(syllabus?.syllabus, setupJob);
  const lessons = syllabus?.lessons || [];
  const showProgress = Boolean(
    syllabusRecord && (["processing", "parsing", "uploaded", "failed"].includes(syllabusRecord.status) || !lessons.length || sources.some((source) => sourceIsWorking(source) || source.status === "failed") || setupJob?.status === "loading")
  );
  return (
    <>
      {showProgress ? <SyllabusProgressCard syllabus={syllabusRecord} uploading={uploadingSyllabus || setupJob?.status === "loading" || sources.some(sourceIsWorking)} lessonCount={lessons.length} /> : null}
      <Button variant="primary" icon={Upload} className="full-btn" onClick={onAddSource}>Thêm tài liệu</Button>
      <SearchInput placeholder="Tìm tài liệu..." className="workspace-search" />
      <h3 className="panel-label">Tài liệu đã thêm</h3>
      <div className="source-list">
        {sources.length ? sources.map((source) => (
          <SourceItem key={source.id} source={source} onToggle={onToggle} onDelete={onDeleteSource} deleting={deletingSourceId === source.id} />
        )) : <p className="empty-copy">Chưa có tài liệu nào.</p>}
      </div>
    </>
  );
}

function lessonStatusLabel(status) {
  if (status === "current") return "Đang học";
  if (status === "taught") return "Đã học";
  if (status === "done") return "Hoàn thành";
  if (status === "todo" || status === "future") return "Chưa học";
  return status || "Chưa học";
}

function lessonChapter(lesson) {
  return lesson.assignedReadings?.[0] || lesson.title || "Chưa có chương";
}

function SyllabusTab({ syllabus, setupJob, onUploadSyllabus, onRetryUploadedSyllabus, onCreateSyllabusFromSources, uploadingSyllabus, syllabusError }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const lessons = syllabus?.lessons || [];
  const current = syllabus?.currentLesson;
  const currentWeek = Number(syllabus?.syllabus?.currentWeek || current?.weekNumber || current?.lessonNumber || 0);
  const syllabusRecord = setupSyllabusRecord(syllabus?.syllabus, setupJob);
  const syllabusStatus = syllabusRecord?.status;
  const hasSyllabus = syllabusRecord && syllabusStatus !== "skipped";
  const showProgress = hasSyllabus && (uploadingSyllabus || setupJob?.status === "loading" || ["processing", "parsing", "uploaded", "failed"].includes(syllabusStatus) || !lessons.length);

  const handleFileChange = (event) => setSelectedFile(event.target.files?.[0] || null);

  const submitUpload = async () => {
    const ok = await onUploadSyllabus?.(selectedFile);
    if (ok) setSelectedFile(null);
  };

  if (!hasSyllabus) {
    return (
      <div className="sidebar-syllabus">
        <SyllabusUploadBox selectedFile={selectedFile} onFileChange={handleFileChange} onUpload={submitUpload} busy={uploadingSyllabus} error={syllabusError} />
        <p className="empty-copy">Chưa có syllabus cho môn này.</p>
      </div>
    );
  }

  return (
    <div className="sidebar-syllabus">
      <SyllabusUploadBox selectedFile={selectedFile} onFileChange={handleFileChange} onUpload={submitUpload} busy={uploadingSyllabus} error={syllabusError} />
      {showProgress ? <SyllabusProgressCard syllabus={syllabusRecord} uploading={uploadingSyllabus || setupJob?.status === "loading"} lessonCount={lessons.length} onRetryUploadedSyllabus={onRetryUploadedSyllabus} onCreateSyllabusFromSources={onCreateSyllabusFromSources} /> : null}
      <h3 className="panel-label">Tuần nào học chương gì</h3>
      <div className="sidebar-syllabus-list">
        {lessons.length ? lessons.map((lesson) => {
          const lessonWeek = Number(lesson.weekNumber || lesson.lessonNumber || 0);
          const isCurrent = lesson.status === "current" || lesson.id === current?.id || (currentWeek > 0 && lessonWeek === currentWeek);

          return (
            <div className={`sidebar-syllabus-row ${isCurrent ? "active" : ""}`} key={lesson.id}>
              <CalendarDays size={16} />
              <span>
                <strong>Tuần {lesson.weekNumber || lesson.lessonNumber || "-"}: {lessonChapter(lesson)}</strong>
                <small>{lessonStatusLabel(lesson.status)} - {lesson.title}{lesson.assignedReadings?.length > 1 ? ` - ${lesson.assignedReadings.slice(1).join(", ")}` : ""}</small>
              </span>
            </div>
          );
        }) : <p className="empty-copy">Syllabus chưa có bài học.</p>}
      </div>
    </div>
  );
}

function setupSyllabusRecord(syllabusRecord, setupJob) {
  if (syllabusRecord) return syllabusRecord;
  if (setupJob?.type !== "course-setup") return null;
  const failed = setupJob.status === "error";
  return {
    status: failed ? "failed" : "processing",
    parsedJson: {
      progress: {
        stage: setupJob.progressStage || (failed ? "failed" : "uploaded"),
        message: failed ? setupJob.error : setupJob.subtitle,
        percent: failed ? 100 : Number(setupJob.progress || 10),
        detail: setupJob.progressDetail,
        updatedAt: new Date().toISOString()
      }
    }
  };
}

function SyllabusProgressCard({ syllabus, uploading, lessonCount, onRetryUploadedSyllabus, onCreateSyllabusFromSources }) {
  const status = syllabus?.status || (uploading ? "processing" : "missing");
  const progress = syllabus?.parsedJson?.progress || {};
  const isFailed = status === "failed";
  const isReady = status === "ready";
  const isLoading = uploading || ["processing", "parsing", "uploaded"].includes(status);
  const percent = Number.isFinite(Number(progress.percent)) ? Number(progress.percent) : (isReady || isFailed ? 100 : 15);
  const stage = progress.stage || (isReady ? "ready" : isFailed ? "failed" : "uploaded");
  const message = progress.message || syllabusStageMessage(stage, status, lessonCount);
  const detail = progress.detail || syllabus?.parsedJson?.error || "";
  const updatedAt = progress.updatedAt || syllabus?.updatedAt;
  const Icon = isFailed ? AlertCircle : isReady ? CheckCircle2 : Loader2;

  return (
    <div className={`syllabus-progress-card ${isFailed ? "is-error" : isLoading ? "is-loading" : "is-ready"}`}>
      <div className="syllabus-progress-head">
        <Icon size={18} />
        <span>
          <strong>{syllabusStageTitle(stage, status, lessonCount)}</strong>
          <small>{message}</small>
        </span>
      </div>
      <div className="syllabus-progress-track" aria-label={`${Math.round(percent)}%`}>
        <span style={{ width: `${Math.max(5, Math.min(100, percent))}%` }} />
      </div>
      <div className="syllabus-progress-meta">
        <small>{Math.round(percent)}%</small>
        {updatedAt ? <small>{new Date(updatedAt).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}</small> : null}
      </div>
      {detail ? <p>{detail}</p> : null}
      {isFailed ? (
        <div className="syllabus-recovery-actions">
          <Button variant="primary" className="full-btn" onClick={onCreateSyllabusFromSources} disabled={uploading}>Tạo syllabus từ giáo trình</Button>
          <Button variant="secondary" className="full-btn" onClick={onRetryUploadedSyllabus} disabled={uploading}>Thử lại syllabus đã upload</Button>
        </div>
      ) : null}
    </div>
  );
}

function syllabusStageTitle(stage, status, lessonCount) {
  if (status === "failed") return "Syllabus bị lỗi";
  if (status === "ready" && lessonCount === 0) return "Đã đọc file, chưa có bài học";
  if (status === "ready") return "Syllabus đã sẵn sàng";
  if (stage === "extracting_text") return "Đang đọc nội dung file";
  if (stage === "parsing_lessons") return "Đang tách lịch học";
  return "Đang xử lý syllabus";
}

function syllabusStageMessage(stage, status, lessonCount) {
  if (status === "failed") return "Dừng ở bước trích xuất hoặc phân tích file.";
  if (status === "ready" && lessonCount === 0) return "Không tìm thấy timeline trong syllabus vừa upload.";
  if (status === "ready") return `${lessonCount} bài học đã được tạo.`;
  if (stage === "extracting_text") return "Hệ thống đang trích text từ file upload.";
  if (stage === "parsing_lessons") return "Hệ thống đang tách tuần, bài học và readings.";
  return "File đã nhận, job sẽ tiếp tục cập nhật tại đây.";
}

function SyllabusUploadBox({ selectedFile, onFileChange, onUpload, busy, error }) {
  return (
    <div className="syllabus-upload-box">
      <label className="syllabus-upload-dropzone">
        <Upload size={18} />
        <span>
          <strong>Tải syllabus lên</strong>
          <small>{selectedFile ? selectedFile.name : "Chỉ chọn 1 file syllabus"}</small>
        </span>
        <input type="file" accept=".pdf,.docx,.pptx,.txt,.md" onChange={onFileChange} disabled={busy} />
      </label>
      <Button variant="primary" className="full-btn" onClick={onUpload} disabled={busy || !selectedFile}>{busy ? "Đang tải..." : "Tải syllabus"}</Button>
      {error ? <div className="onboarding-error">{error}</div> : null}
    </div>
  );
}

function HistoryTab({ threads, onSelect, onNewChat }) {
  return (
    <>
      <Button variant="primary" icon={Plus} className="full-btn" onClick={onNewChat}>Chat mới</Button>
      <SearchInput placeholder="Tìm cuộc trò chuyện..." className="workspace-search" />
      <div className="history-tab">
        <div className="history-head">
          <h3 className="panel-label">Lịch sử hội thoại</h3>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onNewChat}>
            Chat mới
          </button>
        </div>
        <div className="history-list">
          <div className="history-group">
            {threads.length === 0 ? (
              <p className="empty-copy">Chưa có hội thoại nào trước đó.</p>
            ) : (
              threads.map((thread) => (
                <button key={thread.id} type="button" className="history-item" onClick={() => onSelect(thread)}>
                  <MessageSquare size={16} />
                  <span>{thread.title || "Cuộc trò chuyện mới"}</span>
                </button>
              ))
            )}
          </div>
        </div>
      </div>
    </>
  );
}

export function WorkspaceSideRail({ side, label, onToggle }) {
  const Icon = side === "left" ? ChevronsRight : ChevronsLeft;
  return (
    <aside className={`workspace-side-rail ${side}`}>
      <button type="button" className="sidebar-toggle-btn" onClick={onToggle} aria-label={label} title={label}>
        <Icon size={20} />
      </button>
    </aside>
  );
}

export function WorkspaceLeftSidebar({
  sources, syllabus, setupJob, syllabusError, threads, activeThreadId,
  onSelectThread, onNewChat, onToggleSource, onAddSource, onDeleteSource,
  onUploadSyllabus, onRetryUploadedSyllabus, onCreateSyllabusFromSources, deletingSourceId, uploadingSyllabus, collapsed, onToggleCollapsed,
  chunks, tasks, activeTask, setActiveTask, selectedTopicIds, toggleTopic, topics, quizzes,
  activeTopicId, setActiveTopicId, quizInProgress = false
}) {
  const isTopicActive = !!activeTask || !!activeTopicId;
  const currentTopicId = activeTask?.topicId || activeTopicId;
  const targetTab = isTopicActive ? "Nhiệm vụ" : "Chủ đề";
  const [tab, setTab] = useState(isTopicActive ? "Nhiệm vụ" : "Chủ đề");
  const activeThread = threads.find((thread) => thread.id === activeThreadId);
  const [showTextbook, setShowTextbook] = useState(false);

  useEffect(() => {
    setTab(isTopicActive ? "Nhiệm vụ" : "Chủ đề");
  }, [isTopicActive]);

  useEffect(() => {
    setShowTextbook(false);
  }, [currentTopicId]);

  if (collapsed) {
    return <WorkspaceSideRail side="left" label="Mở panel tài liệu" onToggle={onToggleCollapsed} />;
  }

  const tabsList = [targetTab, "Tài liệu", "Syllabus"];

  return (
    <aside className="workspace-sidebar">
      <div className="workspace-tabs">
        <div className="workspace-tabs-group">
          {tabsList.map((item) => <button key={item} type="button" className={tab === item ? "active" : ""} onClick={() => setTab(item)}>{item}</button>)}
        </div>
        <button type="button" className="sidebar-toggle-btn" onClick={onToggleCollapsed} aria-label="Đóng panel tài liệu" title="Đóng panel tài liệu">
          <ChevronsLeft size={22} />
        </button>
      </div>
      <div className="workspace-sidebar-body">
        {tab === "Tài liệu" ? <SourcesTab sources={sources} syllabus={syllabus} setupJob={setupJob} uploadingSyllabus={uploadingSyllabus} onToggle={onToggleSource} onAddSource={onAddSource} onDeleteSource={onDeleteSource} deletingSourceId={deletingSourceId} /> : null}
        {tab === "Syllabus" ? <SyllabusTab syllabus={syllabus} setupJob={setupJob} onUploadSyllabus={onUploadSyllabus} onRetryUploadedSyllabus={onRetryUploadedSyllabus} onCreateSyllabusFromSources={onCreateSyllabusFromSources} uploadingSyllabus={uploadingSyllabus} syllabusError={syllabusError} /> : null}
        
        {tab === "Nhiệm vụ" && isTopicActive ? (
          <div className="active-task-tab">
            <button type="button" className="back-to-topics-btn" onClick={() => {
              setActiveTopicId(null);
              setActiveTask(null);
            }}>
              <ChevronLeft size={14} />
              Quay lại danh sách chủ đề
            </button>

            {(() => {
              const currentTopic = topics.find(t => t.id === currentTopicId);
              return (
                <>
                  <div className="active-task-header-card">
                    <CalendarDays size={18} />
                    <span>
                      <strong>Đang ôn tập chủ đề:</strong>
                      <h4>{currentTopic?.title || activeTask?.title || activeTask?.topicTitle || "Chi tiết chủ đề"}</h4>
                      {activeTask?.scheduledDate ? <small className="task-date">Ngày học: {activeTask.scheduledDate}</small> : null}
                    </span>
                  </div>

                  {activeTask ? (
                    <div className="task-completion-card" style={{
                      padding: "16px",
                      borderRadius: "10px",
                      background: activeTask.status === "done"
                        ? "linear-gradient(135deg, rgba(16, 185, 129, 0.12) 0%, rgba(16, 185, 129, 0.05) 100%)"
                        : activeTask.status === "missed"
                          ? "linear-gradient(135deg, rgba(239, 68, 68, 0.12) 0%, rgba(239, 68, 68, 0.05) 100%)"
                          : "linear-gradient(135deg, var(--surface-card) 0%, var(--surface-hover) 100%)",
                      border: activeTask.status === "done"
                        ? "1px solid rgba(16, 185, 129, 0.3)"
                        : activeTask.status === "missed"
                          ? "1px solid rgba(239, 68, 68, 0.3)"
                          : "1px solid var(--surface-line)",
                      marginBottom: "16px",
                      display: "flex",
                      flexDirection: "column",
                      gap: "10px",
                      boxShadow: "0 2px 8px rgba(0,0,0,0.02)"
                    }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                        <span style={{
                          fontSize: "13px",
                          fontWeight: "700",
                          color: activeTask.status === "done" ? "#059669" : activeTask.status === "missed" ? "#dc2626" : "var(--text-secondary)",
                          display: "flex",
                          alignItems: "center",
                          gap: "6px"
                        }}>
                          {activeTask.status === "done" ? "✅ Đã hoàn thành nhiệm vụ" : activeTask.status === "missed" ? "⚠️ Đã trễ hạn" : "✏️ Đang thực hiện"}
                        </span>
                      </div>
                      <p style={{ margin: 0, fontSize: "12px", color: "var(--text-secondary)", lineHeight: "1.4" }}>
                        {activeTask.status === "done"
                          ? "Tuyệt vời! Hệ thống đã tự động ghi nhận bạn hoàn thành bài học này sau khi làm quiz."
                          : activeTask.status === "missed"
                            ? "Nhiệm vụ này đã bị trễ hạn. Bạn hãy ôn tập lại chủ đề hoặc lập lại lịch học."
                            : "Hãy ôn tập lý thuyết, trao đổi với AI chatbot và hoàn thành Quiz hoặc Flashcard để hệ thống xác nhận hoàn thành."}
                      </p>
                    </div>
                  ) : null}

                  {currentTopic?.description && (
                    <div className="topic-description-section">
                      <h5>Giới thiệu chủ đề</h5>
                      <p>{currentTopic.description}</p>
                    </div>
                  )}

                  {currentTopic?.contentChunk && (
                    <div className="topic-content-chunk-section">
                      <h5>Tóm tắt lý thuyết</h5>
                      <p>{currentTopic.contentChunk}</p>
                    </div>
                  )}

                  {!quizInProgress && (
                    <div className="topic-full-textbook-content" style={{ marginTop: "16px" }}>
                      <button
                        type="button"
                        onClick={() => setShowTextbook(!showTextbook)}
                        style={{
                          width: "100%",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          padding: "10px 14px",
                          borderRadius: "8px",
                          background: showTextbook ? "var(--brand-green-soft)" : "#f8faf7",
                          border: "1px solid " + (showTextbook ? "var(--brand-green-strong)" : "var(--surface-line)"),
                          cursor: "pointer",
                          marginBottom: "12px",
                          transition: "all 0.15s ease",
                          color: showTextbook ? "var(--brand-green-dark)" : "var(--text-primary)",
                          fontWeight: "750",
                          fontSize: "12px",
                          textTransform: "uppercase",
                          letterSpacing: "0.03em"
                        }}
                      >
                        <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
                          <BookOpen size={14} />
                          Nội dung chi tiết tài liệu học
                        </span>
                        <span>{showTextbook ? "Thu gọn ▲" : "Mở rộng ▼"}</span>
                      </button>

                      {showTextbook && (() => {
                        const topicChunks = (chunks || []).filter(c => c.topicIds && c.topicIds.includes(currentTopicId));
                        
                        // Smart filter to narrow down textbook paragraphs to only this specific topic
                        const filteredChunks = (() => {
                          if (topicChunks.length <= 1) return topicChunks;
                          const currentTopic = topics.find(t => t.id === currentTopicId);
                          if (!currentTopic) return topicChunks;

                          const cleanString = (str) => (str || "").toLowerCase().replace(/[^a-z0-9áàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ]/g, " ").trim();
                          const topicTitleClean = cleanString(currentTopic.title);
                          if (!topicTitleClean || topicTitleClean.length < 3) return topicChunks;

                          // Match by title inclusion in chunk sections or text
                          let matched = topicChunks.filter(c => {
                            const secTitle = cleanString(c.sectionTitle || c.topicName || "");
                            const secPath = cleanString(c.sectionPath || c.chapterName || "");
                            const txt = cleanString(c.text);
                            return secTitle.includes(topicTitleClean) || topicTitleClean.includes(secTitle) || secPath.includes(topicTitleClean) || txt.includes(topicTitleClean);
                          });

                          if (matched.length > 0) return matched;

                          // Fallback: match by keywords
                          const keywords = topicTitleClean.split(/\s+/).filter(w => w.length > 2);
                          if (keywords.length > 0) {
                            matched = topicChunks.filter(c => {
                              const secTitle = cleanString(c.sectionTitle || c.topicName || "");
                              const secPath = cleanString(c.sectionPath || c.chapterName || "");
                              const txt = cleanString(c.text);
                              const matchCount = keywords.filter(kw => secTitle.includes(kw) || secPath.includes(kw) || txt.includes(kw)).length;
                              return matchCount >= Math.ceil(keywords.length * 0.5);
                            });
                            if (matched.length > 0) return matched;
                          }

                          return topicChunks;
                        })();

                        return filteredChunks.length ? (
                          <div className="textbook-reader-pane">
                            {filteredChunks.map((chunk, idx) => (
                              <p key={idx} className="textbook-paragraph">{chunk.text}</p>
                            ))}
                          </div>
                        ) : (
                          <p className="empty-copy">Không tìm thấy tài liệu văn bản cho chủ đề này.</p>
                        );
                      })()}
                    </div>
                  )}
                </>
              );
            })()}
          </div>
        ) : null}

        {tab === "Chủ đề" && !isTopicActive ? (
          <div className="topics-selector-tab">
            <h3 className="panel-label">Danh sách chủ đề học</h3>
            <p className="empty-copy" style={{ marginBottom: "12px" }}>Chọn một chủ đề dưới đây để học lý thuyết, ôn tập quiz/flashcard và thảo luận với AI.</p>
            <div className="topics-checkbox-list">
              {(topics || []).map((t) => {
                const hasQuiz = (quizzes || []).some(q => q.topicId === t.id);
                const quizStatus = hasQuiz ? "available" : "generating";
                return (
                  <div
                    key={t.id}
                    className="topic-select-row clickable-topic-card"
                    onClick={() => {
                      setActiveTopicId(t.id);
                      if (!selectedTopicIds.includes(t.id)) {
                        toggleTopic(t.id);
                      }
                    }}
                  >
                    <div className="topic-card-copy">
                      <strong className="topic-title">{t.title}</strong>
                      <span className={`quiz-status-pill ${quizStatus}`}>
                        {quizStatus === "available" ? "Quiz sẵn sàng" : "Đang tạo Quiz..."}
                      </span>
                      {t.parentTopicTitle ? <small className="topic-parent-chapter">Chương: {t.parentTopicTitle}</small> : null}
                    </div>
                    <button type="button" className="start-learn-btn">Học ngay</button>
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>
      {activeThread ? (
        <div className="selected-chat-note" style={{ margin: "0 14px 14px", flexShrink: 0 }}>
          <MessageSquare size={16} />
          <span>Đã mở: {activeThread.title}</span>
        </div>
      ) : null}
    </aside>
  );
}
