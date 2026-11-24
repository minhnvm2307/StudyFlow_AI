import {
  BookOpenCheck,
  CalendarDays,
  Check,
  FileText,
  HelpCircle,
  Link,
  Sparkles,
  Upload
} from "lucide-react";
import { Avatar, Button, Card } from "../../components/common.jsx";
import { navigate } from "../../router.jsx";
import { modes, priorities, steps, weekdays } from "./constants.js";

export function OnboardingTopBar({ dirty }) {
  const handleExit = () => {
    if (dirty && !window.confirm("Bạn có chắc muốn hủy? Thông tin đã nhập sẽ không được lưu.")) return;
    navigate("/courses");
  };

  return (
    <header className="onboarding-topbar">
      <button type="button" className="brand" onClick={handleExit}>
        <span className="brand-mark"><Sparkles size={18} /></span>
        <span>StudyFlow</span>
      </button>
      <div>
        <Button variant="ghost" icon={HelpCircle}>Cần trợ giúp?</Button>
        <Avatar />
      </div>
    </header>
  );
}

export function Stepper({ currentStep }) {
  return (
    <div className="onboarding-stepper">
      {steps.map((step, index) => (
        <div className={`step-item ${index === currentStep ? "active" : ""} ${index < currentStep ? "complete" : ""}`} key={step}>
          <span>{index < currentStep ? <Check size={16} /> : index + 1}</span>
          <strong>{step}</strong>
        </div>
      ))}
    </div>
  );
}

export function ModeCard({ mode, selected, onSelect }) {
  const Icon = mode.icon;
  return (
    <button type="button" className={`mode-card ${selected ? "selected" : ""}`} onClick={onSelect}>
      <span className="mode-icon"><Icon size={21} /></span>
      <span>
        <strong>{mode.title}</strong>
        <small>{mode.description}</small>
        <small>{mode.helper}</small>
      </span>
      {selected ? <Check className="mode-check" size={18} /> : null}
    </button>
  );
}

export function PreviewCard({ form, sourceCount }) {
  const mode = modes.find((item) => item.id === form.mode)?.title;
  const priority = priorities.find((item) => item.id === form.priority)?.label;

  return (
    <Card className="onboarding-preview">
      <h2>StudyFlow sẽ dùng thông tin này để</h2>
      <ul>
        {[
          "Tạo topic map ban đầu cho môn học",
          "Xếp lịch học theo mức ưu tiên và ngày thi",
          "Sinh quiz, flashcard và chatbot theo nguồn đã thêm",
          "Theo dõi mastery theo từng topic"
        ].map((item) => (
          <li key={item}><span><Check size={14} /></span>{item}</li>
        ))}
      </ul>
      <div className="setup-summary">
        <p>Tóm tắt thiết lập</p>
        <div><span>Môn học</span><strong>{form.name || "Chưa nhập"}</strong></div>
        <div><span>Chế độ</span><strong>{mode}</strong></div>
        <div><span>Ưu tiên</span><strong>{priority}</strong></div>
        <div><span>Ngày thi</span><strong>{form.examDate || "Chưa đặt"}</strong></div>
        <div><span>Nguồn</span><strong>{sourceCount} tài liệu</strong></div>
      </div>
    </Card>
  );
}
