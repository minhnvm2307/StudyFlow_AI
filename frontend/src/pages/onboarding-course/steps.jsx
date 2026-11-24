import { BookOpenCheck, CalendarDays, Check, FileText, Plus, Trash2, Upload } from "lucide-react";
import { ModeCard } from "./components.jsx";
import { modes, priorities, weekdayLabels, weekdays } from "./constants.js";

export function StepOne({ form, update, errors }) {
  return (
    <>
      <div className="form-intro">
        <BookOpenCheck size={26} />
        <div>
          <h2>Bạn đang học môn gì?</h2>
          <p>Nhập thông tin cơ bản để StudyFlow hiểu môn học và chọn cách hỗ trợ phù hợp.</p>
        </div>
      </div>

      <label className="field">
        <span>Tên môn học</span>
        <input value={form.name} onChange={(event) => update({ name: event.target.value })} placeholder="Ví dụ: Đại số tuyến tính" />
        {errors.name ? <small className="field-error">{errors.name}</small> : null}
      </label>

      <div className="field">
        <span>Chế độ học</span>
        <div className="mode-grid">
          {modes.map((item) => (
            <ModeCard key={item.id} mode={item} selected={form.mode === item.id} onSelect={() => update({ mode: item.id })} />
          ))}
        </div>
        {errors.mode ? <small className="field-error">{errors.mode}</small> : null}
      </div>

      <div className="field">
        <span>Mức độ ưu tiên</span>
        <div className="priority-pills">
          {priorities.map((item) => (
            <button type="button" key={item.id} className={form.priority === item.id ? "active" : ""} onClick={() => update({ priority: item.id })}>
              {item.label}
            </button>
          ))}
        </div>
        {errors.priority ? <small className="field-error">{errors.priority}</small> : null}
      </div>
    </>
  );
}

export function StepTwo({ form, update, addAvailabilityWindow, addClassMeeting, removeAvailabilityWindow, removeClassMeeting, toggleAvailabilityDay, updateAvailabilityWindow, updateClassMeeting, errors }) {
  const windowsByDay = weekdays.reduce((acc, day) => {
    acc[day.key] = form.availabilityWindows
      .map((window, index) => ({ ...window, index }))
      .filter((window) => window.day === day.key);
    return acc;
  }, {});

  return (
    <>
      <div className="form-intro">
        <CalendarDays size={26} />
        <div>
          <h2>Mục tiêu và lịch trống</h2>
          <p>Đặt deadline học kỳ, mục tiêu điểm và các khung giờ đủ dài để StudyFlow tự chia phiên học phù hợp.</p>
        </div>
      </div>

      <section className="onboarding-section">
        <div className="section-heading">
          <span>Deadline học kỳ</span>
          <p>Thông tin mốc thời gian cố định, tách riêng khỏi phần chọn lịch tự học.</p>
        </div>
        <div className="onboarding-form-grid responsive-cols">
          <label className="field">
            <span>Ngày bắt đầu kỳ học</span>
            <input type="date" value={form.semesterStartDate} onChange={(event) => update({ semesterStartDate: event.target.value })} />
          </label>
          <label className="field">
            <span>Ngày kết thúc kỳ học</span>
            <input type="date" value={form.semesterEndDate} onChange={(event) => update({ semesterEndDate: event.target.value })} />
          </label>
          <label className="field">
            <span>Ngày thi</span>
            <input type="date" value={form.examDate} onChange={(event) => update({ examDate: event.target.value })} />
            {errors.examDate ? <small className="field-error">{errors.examDate}</small> : null}
          </label>
        </div>
        {errors.semesterDates ? <small className="field-error">{errors.semesterDates}</small> : null}
      </section>

      <section className="onboarding-section">
        <div className="section-heading">
          <span>Buổi học trên trường</span>
          <p>Thêm lịch lớp cố định nếu bạn muốn hệ thống tính tiến độ theo syllabus và lịch học thật.</p>
        </div>
        <div className="weekly-slot-editor">
          {form.classMeetings.map((meeting, index) => (
            <div className="weekly-slot-row active" key={`class-${index}`}>
              <select className="day-toggle" value={meeting.day} onChange={(event) => updateClassMeeting(index, { day: event.target.value })}>
                {weekdays.map((day) => <option key={day.key} value={day.key}>{day.label}</option>)}
              </select>
              <div className="slot-stack">
                <div className="slot-range">
                  <input type="time" value={meeting.start} onChange={(event) => updateClassMeeting(index, { start: event.target.value })} />
                  <span>đến</span>
                  <input type="time" value={meeting.end} onChange={(event) => updateClassMeeting(index, { end: event.target.value })} />
                  <button type="button" className="slot-icon-button" onClick={() => removeClassMeeting(index)} aria-label={`Xóa buổi học ${index + 1}`}>
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            </div>
          ))}
          <button type="button" className="slot-add-button" onClick={() => addClassMeeting("Mon")}>
            <Plus size={16} /> Thêm buổi học
          </button>
        </div>
        {errors.classMeetings ? <small className="field-error">{errors.classMeetings}</small> : null}
      </section>

      <section className="onboarding-section availability-section">
        <div className="section-heading">
          <span>Lịch tự học</span>
          <p>Chọn mục tiêu và thời lượng trước, rồi thêm các khung giờ rảnh đủ dài cho mỗi phiên.</p>
        </div>
        <div className="onboarding-form-grid study-settings-grid">
          <label className="field">
            <span>Target điểm</span>
            <input type="number" min="1" max="100" value={form.targetScore} onChange={(event) => update({ targetScore: event.target.value })} placeholder="85" />
            {errors.targetScore ? <small className="field-error">{errors.targetScore}</small> : null}
          </label>
          <label className="field">
            <span>Thời lượng mỗi phiên</span>
            <div className="input-with-unit">
              <input type="number" min="15" max="120" step="5" value={form.sessionMinutes} onChange={(event) => update({ sessionMinutes: event.target.value })} />
              <span>phút</span>
            </div>
            {errors.sessionMinutes ? <small className="field-error">{errors.sessionMinutes}</small> : null}
          </label>
        </div>

        <div className="field compact-field">
          <span>Khung giờ rảnh trong tuần</span>
          <div className="weekly-slot-editor">
            {weekdays.map((day) => {
              const dayWindows = windowsByDay[day.key];
              const isEnabled = dayWindows.length > 0;
              return (
                <div className={`weekly-slot-row ${isEnabled ? "active" : ""}`} key={day.key}>
                  <button type="button" className="day-toggle" onClick={() => toggleAvailabilityDay(day.key)} aria-pressed={isEnabled}>
                    {day.label}
                  </button>
                  <div className="slot-stack">
                    {isEnabled ? dayWindows.map((window) => (
                      <div className="slot-range" key={`${window.day}-${window.index}`}>
                        <input type="time" value={window.start} onChange={(event) => updateAvailabilityWindow(window.index, { start: event.target.value })} />
                        <span>đến</span>
                        <input type="time" value={window.end} onChange={(event) => updateAvailabilityWindow(window.index, { end: event.target.value })} />
                        <button type="button" className="slot-icon-button" onClick={() => removeAvailabilityWindow(window.index)} aria-label={`Xóa khung giờ ${day.label}`}>
                          <Trash2 size={16} />
                        </button>
                      </div>
                    )) : <span className="slot-empty">Chưa chọn</span>}
                  </div>
                  <button type="button" className="slot-add-button" onClick={() => addAvailabilityWindow(day.key)}>
                    <Plus size={16} /> Thêm
                  </button>
                </div>
              );
            })}
          </div>
          {errors.availabilityWindows ? <small className="field-error">{errors.availabilityWindows}</small> : null}
        </div>
      </section>

    </>
  );
}

export function StepDocuments({ form, update, errors, files, setFiles, syllabusFile, setSyllabusFile }) {
  return (
    <>
      <div className="form-intro">
        <Upload size={26} />
        <div>
          <h2>Tài liệu</h2>
          <p>Upload tài liệu học và syllabus trên cùng một trang để StudyFlow tạo topic, timeline và lịch học.</p>
        </div>
      </div>

      <div className="document-upload-stack">
        <div className="document-upload-pane">
          <h3>Tài liệu học</h3>
          <label className="source-dropzone">
            <Upload size={24} />
            <strong>Upload tài liệu</strong>
            <span>PDF, DOCX, PPTX hoặc TXT. Có thể chọn nhiều file.</span>
            <input type="file" multiple onChange={(event) => setFiles(Array.from(event.target.files || []))} />
            {files.length ? (
              <div className="dropzone-files">
                {files.map((file) => <span key={`${file.name}-${file.size}`}><FileText size={14} />{file.name}</span>)}
              </div>
            ) : null}
          </label>
          {errors.sources ? <small className="field-error">{errors.sources}</small> : null}
        </div>

        <div className="document-upload-pane">
          <h3>Syllabus</h3>
          <label className="source-dropzone">
            <Upload size={24} />
            <strong>Upload syllabus</strong>
            <span>PDF, DOCX, PPTX, TXT hoặc MD. Chọn đúng 1 file syllabus.</span>
            <input type="file" accept=".pdf,.docx,.pptx,.txt,.md" onChange={(event) => setSyllabusFile(event.target.files?.[0] || null)} />
            {syllabusFile ? (
              <div className="dropzone-files single-file">
                <span><FileText size={14} />{syllabusFile.name}</span>
              </div>
            ) : null}
          </label>
          {errors.syllabusText ? <small className="field-error">{errors.syllabusText}</small> : null}
          <label className="skip-source-check"><input type="checkbox" checked={form.wantsDiagnostic} onChange={(event) => update({ wantsDiagnostic: event.target.checked })} /><span>Đề xuất một bài kiểm tra đánh giá ngắn cho các chủ đề đã học.</span></label>
        </div>
      </div>
    </>
  );
}

export function StepFour({ form, sourceCount, skippedSources }) {
  const mode = modes.find((item) => item.id === form.mode)?.title;
  const priority = priorities.find((item) => item.id === form.priority)?.label;
  const availabilitySummary = formatAvailabilityWindows(form.availabilityWindows);

  return (
    <>
      <div className="form-intro">
        <Check size={26} />
        <div>
          <h2>Xác nhận kế hoạch</h2>
          <p>StudyFlow sẽ tạo môn học, topic map và lịch học đầu tiên từ thông tin này.</p>
        </div>
      </div>

      <div className="confirm-grid">
        <div><span>Môn học</span><strong>{form.name}</strong></div>
        <div><span>Chế độ</span><strong>{mode}</strong></div>
        <div><span>Ngày thi</span><strong>{form.examDate || "Chưa đặt"}</strong></div>
        <div><span>Target</span><strong>{form.targetScore || "Chưa đặt"}</strong></div>
        <div><span>Ưu tiên</span><strong>{priority}</strong></div>
        <div><span>Tài liệu</span><strong>{skippedSources ? "Bỏ qua tạm thời" : `${sourceCount} nguồn`}</strong></div>
        <div><span>Lịch trống</span><strong>{availabilitySummary}</strong></div>
        <div><span>Thời lượng</span><strong>{form.sessionMinutes} phút/phiên</strong></div>
      </div>
    </>
  );
}

function formatAvailabilityWindows(windows = []) {
  if (!windows.length) return "Chưa chọn";
  return weekdays
    .map((day) => {
      const ranges = windows
        .filter((window) => window.day === day.key)
        .sort((a, b) => a.start.localeCompare(b.start))
        .map((window) => `${window.start}-${window.end}`);
      return ranges.length ? `${weekdayLabels[day.key]} ${ranges.join(", ")}` : null;
    })
    .filter(Boolean)
    .join("; ");
}
