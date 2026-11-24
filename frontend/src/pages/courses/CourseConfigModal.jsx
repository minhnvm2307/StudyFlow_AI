import { useEffect, useState } from "react";
import { CalendarDays, Loader2, Plus, SlidersHorizontal, Trash2 } from "lucide-react";
import { Button, Modal } from "../../components/common.jsx";
import { coursesApi } from "../../services/studyflowApi.js";
import { modes, priorities, weekdayLabels, weekdays } from "../onboarding-course/constants.js";
import { ModeCard } from "../onboarding-course/components.jsx";

export function CourseConfigModal({ open, courseId, onClose, onSaveSuccess }) {
  const [course, setCourse] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    name: "",
    mode: "continuous",
    priority: "medium",
    examDate: "",
    targetScore: "85",
    availabilityWindows: []
  });
  const [errors, setErrors] = useState({});
  const [generalError, setGeneralError] = useState("");
  const [rebuildPlan, setRebuildPlan] = useState(true);

  useEffect(() => {
    if (!open || !courseId) return;

    setLoading(true);
    setGeneralError("");
    setErrors({});
    coursesApi.getCourse(courseId)
      .then((data) => {
        setCourse(data);
        setForm({
          name: data.name || "",
          mode: data.mode || "continuous",
          priority: data.priority || "medium",
          examDate: data.examDate ? data.examDate.slice(0, 10) : "",
          targetScore: data.targetScore ? String(data.targetScore) : "",
          availabilityWindows: data.availabilityWindows || []
        });
      })
      .catch((err) => {
        setGeneralError(err.message || "Không thể tải thông tin môn học.");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [open, courseId]);

  const update = (patch) => {
    setForm((current) => ({ ...current, ...patch }));
    setGeneralError("");
    setErrors((errs) => ({ ...errs, ...Object.keys(patch).reduce((acc, k) => ({ ...acc, [k]: "" }), {}) }));
  };

  // Helper availability window management
  const updateAvailabilityWindow = (index, patch) => {
    update({
      availabilityWindows: form.availabilityWindows.map((w, i) => i === index ? { ...w, ...patch } : w)
    });
  };

  const addAvailabilityWindow = (day) => {
    const dayWindows = form.availabilityWindows.filter((w) => w.day === day).sort((a, b) => a.start.localeCompare(b.start));
    const lastEnd = dayWindows.at(-1)?.end || "19:00";
    const start = lastEnd;
    const end = addMinutes(start, 30);
    update({
      availabilityWindows: sortWindows([...form.availabilityWindows, { day, start, end }])
    });
  };

  const removeAvailabilityWindow = (index) => {
    update({
      availabilityWindows: form.availabilityWindows.filter((_, i) => i !== index)
    });
  };

  const toggleAvailabilityDay = (day) => {
    const hasDay = form.availabilityWindows.some((w) => w.day === day);
    if (hasDay) {
      update({
        availabilityWindows: form.availabilityWindows.filter((w) => w.day !== day)
      });
    } else {
      update({
        availabilityWindows: sortWindows([...form.availabilityWindows, { day, start: "19:00", end: "19:30" }])
      });
    }
  };

  const validate = () => {
    const nextErrors = {};
    if (!form.name.trim()) nextErrors.name = "Vui lòng nhập tên môn học.";
    
    const targetScore = Number(form.targetScore);
    if (form.targetScore && (targetScore < 1 || targetScore > 100)) {
      nextErrors.targetScore = "Target nên nằm trong khoảng 1-100.";
    }

    if (form.examDate && new Date(form.examDate) < new Date(new Date().toDateString())) {
      nextErrors.examDate = "Ngày thi không nên nằm trong quá khứ.";
    }

    const classMeetingError = validateAvailabilityWindows(form.availabilityWindows, 15);
    if (classMeetingError) {
      nextErrors.availabilityWindows = classMeetingError;
    }

    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const handleSave = async () => {
    if (!validate()) return;
    setSaving(true);
    setGeneralError("");
    try {
      const payload = {
        name: form.name.trim(),
        mode: form.mode,
        priority: form.priority,
        targetScore: form.targetScore ? Number(form.targetScore) : null,
        examDate: form.examDate || null,
        availabilityWindows: form.availabilityWindows
      };
      
      await coursesApi.updateCourse(courseId, payload);
      
      if (rebuildPlan) {
        try {
          await coursesApi.generatePlan(courseId);
        } catch (planErr) {
          console.error("Lỗi tự động lập lịch lại:", planErr);
        }
      }

      onSaveSuccess();
      onClose();
    } catch (err) {
      setGeneralError(err.message || "Không thể cập nhật cấu hình môn học.");
    } finally {
      setSaving(false);
    }
  };

  const windowsByDay = weekdays.reduce((acc, day) => {
    acc[day.key] = form.availabilityWindows
      .map((w, i) => ({ ...w, index: i }))
      .filter((w) => w.day === day.key);
    return acc;
  }, {});

  const footer = (
    <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", width: "100%" }}>
      <Button variant="secondary" onClick={onClose} disabled={saving}>Hủy</Button>
      <Button variant="primary" onClick={handleSave} disabled={saving || loading} icon={saving ? Loader2 : undefined}>
        {saving ? "Đang lưu..." : "Lưu cấu hình"}
      </Button>
    </div>
  );

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Cấu hình: ${course?.name || "Môn học"}`}
      footer={footer}
      className="course-config-modal"
    >
      {loading ? (
        <div style={{ padding: "40px 0", display: "flex", flexDirection: "column", alignItems: "center", gap: "12px", color: "#64748b" }}>
          <Loader2 className="animate-spin" size={32} />
          <span>Đang tải thông tin môn học...</span>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "20px", padding: "4px" }}>
          {generalError && (
            <div style={{ backgroundColor: "#fef2f2", border: "1px solid #fecaca", color: "#b91c1c", padding: "10px 12px", borderRadius: "6px", fontSize: "13px" }}>
              {generalError}
            </div>
          )}

          <label className="field">
            <span style={{ fontWeight: 600, fontSize: "13px", color: "#334155", marginBottom: "4px", display: "block" }}>Tên môn học</span>
            <input
              value={form.name}
              onChange={(e) => update({ name: e.target.value })}
              placeholder="Ví dụ: Đại số tuyến tính"
              style={{ width: "100%", padding: "8px 12px", borderRadius: "6px", border: "1px solid #cbd5e1" }}
            />
            {errors.name && <small className="field-error" style={{ color: "#ef4444", fontSize: "11px", marginTop: "2px", display: "block" }}>{errors.name}</small>}
          </label>

          <div className="field">
            <span style={{ fontWeight: 600, fontSize: "13px", color: "#334155", marginBottom: "4px", display: "block" }}>Chế độ học</span>
            <div className="mode-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", marginTop: "4px" }}>
              {modes.map((item) => (
                <ModeCard
                  key={item.id}
                  mode={item}
                  selected={form.mode === item.id}
                  onSelect={() => update({ mode: item.id })}
                />
              ))}
            </div>
          </div>

          <div className="field">
            <span style={{ fontWeight: 600, fontSize: "13px", color: "#334155", marginBottom: "4px", display: "block" }}>Mức độ ưu tiên</span>
            <div className="priority-pills" style={{ display: "flex", gap: "8px", marginTop: "4px" }}>
              {priorities.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  className={form.priority === item.id ? "active" : ""}
                  onClick={() => update({ priority: item.id })}
                  style={{
                    padding: "6px 16px",
                    borderRadius: "20px",
                    border: form.priority === item.id ? "1px solid #10b981" : "1px solid #cbd5e1",
                    backgroundColor: form.priority === item.id ? "#ecfdf5" : "#ffffff",
                    color: form.priority === item.id ? "#047857" : "#475569",
                    fontWeight: form.priority === item.id ? 600 : 500,
                    cursor: "pointer",
                    transition: "all 0.15s ease"
                  }}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "minmax(220px, 1fr)", gap: "16px" }}>
            <label className="field">
              <span style={{ fontWeight: 600, fontSize: "13px", color: "#334155", marginBottom: "4px", display: "block" }}>Ngày thi</span>
              <input
                type="date"
                value={form.examDate}
                onChange={(e) => update({ examDate: e.target.value })}
                style={{ width: "100%", padding: "8px 12px", borderRadius: "6px", border: "1px solid #cbd5e1" }}
              />
              {errors.examDate && <small className="field-error" style={{ color: "#ef4444", fontSize: "11px", marginTop: "2px", display: "block" }}>{errors.examDate}</small>}
            </label>
          </div>

          <div className="field">
            <span style={{ fontWeight: 700, fontSize: "15px", color: "#1e293b", marginBottom: "3px", display: "block" }}>Lịch tự học</span>
            <p style={{ margin: "0 0 12px", color: "#64748b", fontSize: "13px", lineHeight: 1.45 }}>Target điểm và khung giờ rảnh được dùng khi lập lại lịch học.</p>
            <label className="field" style={{ display: "block", maxWidth: "320px", marginBottom: "14px" }}>
              <span style={{ fontWeight: 600, fontSize: "13px", color: "#334155", marginBottom: "4px", display: "block" }}>Target điểm</span>
              <input
                type="number"
                min="1"
                max="100"
                value={form.targetScore}
                onChange={(e) => update({ targetScore: e.target.value })}
                style={{ width: "100%", minWidth: "0", padding: "8px 12px", borderRadius: "6px", border: "1px solid #cbd5e1" }}
              />
              {errors.targetScore && <small className="field-error" style={{ color: "#ef4444", fontSize: "11px", marginTop: "2px", display: "block" }}>{errors.targetScore}</small>}
            </label>
            <span style={{ fontWeight: 600, fontSize: "13px", color: "#334155", marginBottom: "4px", display: "block" }}>Khung giờ rảnh trong tuần</span>
            <div className="weekly-slot-editor" style={{ display: "flex", flexDirection: "column", gap: "8px", marginTop: "6px" }}>
              {weekdays.map((day) => {
                const dayWindows = windowsByDay[day.key] || [];
                const isEnabled = dayWindows.length > 0;
                return (
                  <div
                    className={`weekly-slot-row ${isEnabled ? "active" : ""}`}
                    key={day.key}
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: "12px",
                      padding: "8px",
                      borderRadius: "6px",
                      border: "1px solid #f1f5f9",
                      backgroundColor: isEnabled ? "#f8fafc" : "#ffffff"
                    }}
                  >
                    <button
                      type="button"
                      className="day-toggle"
                      onClick={() => toggleAvailabilityDay(day.key)}
                      style={{
                        width: "36px",
                        height: "36px",
                        borderRadius: "50%",
                        border: isEnabled ? "1px solid #3b82f6" : "1px solid #cbd5e1",
                        backgroundColor: isEnabled ? "#eff6ff" : "#ffffff",
                        color: isEnabled ? "#1d4ed8" : "#64748b",
                        fontWeight: "bold",
                        cursor: "pointer",
                        flexShrink: 0
                      }}
                    >
                      {day.label}
                    </button>
                    <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "6px" }}>
                      {isEnabled ? (
                        dayWindows.map((window) => (
                          <div className="slot-range" key={`${window.day}-${window.index}`} style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                            <input
                              type="time"
                              value={window.start}
                              onChange={(e) => updateAvailabilityWindow(window.index, { start: e.target.value })}
                              style={{ padding: "4px 8px", border: "1px solid #cbd5e1", borderRadius: "4px", fontSize: "13px" }}
                            />
                            <span style={{ fontSize: "12px", color: "#64748b" }}>đến</span>
                            <input
                              type="time"
                              value={window.end}
                              onChange={(e) => updateAvailabilityWindow(window.index, { end: e.target.value })}
                              style={{ padding: "4px 8px", border: "1px solid #cbd5e1", borderRadius: "4px", fontSize: "13px" }}
                            />
                            <button
                              type="button"
                              className="slot-icon-button"
                              onClick={() => removeAvailabilityWindow(window.index)}
                              style={{ padding: "4px", color: "#94a3b8", hover: { color: "#ef4444" }, border: "none", background: "none", cursor: "pointer" }}
                            >
                              <Trash2 size={15} />
                            </button>
                          </div>
                        ))
                      ) : (
                        <span style={{ fontSize: "13px", color: "#94a3b8", lineHeight: "36px" }}>Chưa chọn khung giờ</span>
                      )}
                    </div>
                    <button
                      type="button"
                      className="slot-add-button"
                      onClick={() => addAvailabilityWindow(day.key)}
                      style={{
                        padding: "4px 10px",
                        borderRadius: "4px",
                        border: "1px dashed #cbd5e1",
                        backgroundColor: "#ffffff",
                        fontSize: "12px",
                        color: "#475569",
                        display: "flex",
                        alignItems: "center",
                        gap: "4px",
                        cursor: "pointer",
                        alignSelf: "center"
                      }}
                    >
                      <Plus size={14} /> Thêm
                    </button>
                  </div>
                );
              })}
            </div>
            {errors.availabilityWindows && <small style={{ color: "#ef4444", fontSize: "11px", marginTop: "4px", display: "block" }}>{errors.availabilityWindows}</small>}
          </div>

          <label style={{ display: "flex", alignItems: "center", gap: "8px", padding: "10px", borderRadius: "6px", backgroundColor: "#f8fafc", cursor: "pointer", marginTop: "8px" }}>
            <input
              type="checkbox"
              checked={rebuildPlan}
              onChange={(e) => setRebuildPlan(e.target.checked)}
              style={{ width: "16px", height: "16px", cursor: "pointer" }}
            />
            <div style={{ display: "flex", flexDirection: "column" }}>
              <strong style={{ fontSize: "13px", color: "#1e293b" }}>Tự động lập lịch lại môn học sau khi lưu</strong>
              <span style={{ fontSize: "11px", color: "#64748b" }}>Cập nhật lại lịch học và sự kiện tự học trên Calendar của bạn.</span>
            </div>
          </label>
        </div>
      )}
    </Modal>
  );
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

function sortWindows(windows) {
  const dayOrder = { Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6 };
  return [...windows].sort((a, b) => (dayOrder[a.day] - dayOrder[b.day]) || a.start.localeCompare(b.start));
}

function validateAvailabilityWindows(windows, minMinutes = 15) {
  if (!windows.length) return "Chọn ít nhất một khung giờ rảnh.";
  const byDay = new Map();
  for (const window of windows) {
    const start = minutesFromTime(window.start);
    const end = minutesFromTime(window.end);
    if (start === null || end === null) return "Khung giờ cần đúng định dạng giờ.";
    if (end <= start) return "Giờ kết thúc phải sau giờ bắt đầu.";
    if (end - start < minMinutes) return `Mỗi khung giờ cần tối thiểu ${minMinutes} phút.`;
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
