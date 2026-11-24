import React, { useState, useEffect, useRef } from "react";
import {
  Bell,
  BookOpen,
  CalendarDays,
  Check,
  ChevronDown,
  Grid3X3,
  HelpCircle,
  Home,
  LayoutGrid,
  LogOut,
  Menu,
  Plus,
  Search,
  Settings,
  Sparkles
} from "lucide-react";
import { AppLink, navigate } from "../../router.jsx";
import { clearCurrentUser, getCurrentUser } from "../../services/authSession.js";
import { tasksApi } from "../../services/studyflowApi.js";

function logout() {
  clearCurrentUser();
  navigate("/");
}

export function AppShell({ children, className = "", ambience = "default" }) {
  return <div className={`app-shell app-shell-${ambience} ${className}`}>{children}</div>;
}

export function PageContainer({ children, className = "" }) {
  return <main className={`page-container ${className}`}>{children}</main>;
}

export function Card({ children, className = "", as: Component = "section", ...props }) {
  return <Component className={`card ${className}`} {...props}>{children}</Component>;
}

export function Button({ children, variant = "secondary", size = "md", className = "", icon: Icon, onClick, type = "button", disabled = false }) {
  return (
    <button type={type} className={`btn btn-${variant} btn-${size} ${className}`} onClick={onClick} disabled={disabled}>
      {Icon ? <Icon size={16} strokeWidth={2.2} /> : null}
      <span>{children}</span>
    </button>
  );
}

export function IconButton({ label, icon: Icon, onClick, className = "" }) {
  return (
    <button type="button" className={`icon-btn ${className}`} aria-label={label} title={label} onClick={onClick}>
      <Icon size={18} strokeWidth={2.1} />
    </button>
  );
}

export function Badge({ children, tone = "neutral", className = "" }) {
  return <span className={`badge badge-${tone} ${className}`}>{children}</span>;
}

export function ProgressBar({ value, tone = "green", className = "" }) {
  return (
    <div className={`progress ${className}`} aria-label={`${value}%`}>
      <span className={`progress-fill tone-${tone}`} style={{ width: `${value}%` }} />
    </div>
  );
}

export function ProgressRing({ value, label = "Tuần này" }) {
  const angle = `${Math.round((value / 100) * 360)}deg`;
  return (
    <div className="progress-ring" style={{ "--ring-angle": angle }}>
      <div className="progress-ring-inner">
        <strong>{value}%</strong>
        <span>{label}</span>
      </div>
    </div>
  );
}

export function Avatar({ size = "md", initials = "SF" }) {
  return <div className={`avatar avatar-${size}`}>{initials}</div>;
}

export function SearchInput({ placeholder = "Tìm kiếm...", className = "", value, onChange }) {
  return (
    <label className={`search-field ${className}`}>
      <Search size={16} strokeWidth={2.1} />
      <input placeholder={placeholder} value={value} onChange={onChange} />
    </label>
  );
}

export function NotificationRing() {
  const [missedTasks, setMissedTasks] = useState([]);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);

  const fetchMissed = () => {
    tasksApi.getTasks({ status: "missed" })
      .then((items) => {
        const today = new Date();
        const currentDay = today.getDay();
        const distanceToMon = currentDay === 0 ? -6 : 1 - currentDay;
        const startOfWeek = new Date(today);
        startOfWeek.setDate(today.getDate() + distanceToMon);
        startOfWeek.setHours(0,0,0,0);
        
        const endOfWeek = new Date(startOfWeek);
        endOfWeek.setDate(startOfWeek.getDate() + 7);
        
        const currentWeekMissed = items.filter(item => {
          const taskDate = new Date(item.startAt || item.scheduledDate);
          return taskDate >= startOfWeek && taskDate < endOfWeek;
        });
        
        setMissedTasks(currentWeekMissed);
      })
      .catch(err => console.error("Error fetching missed tasks", err));
  };

  useEffect(() => {
    fetchMissed();
    const interval = setInterval(fetchMissed, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleReschedule = async () => {
    try {
      const res = await tasksApi.reschedule();
      fetchMissed();
      setDropdownOpen(false);
      if (res && res.notifications && res.notifications.length > 0) {
        alert("Thông báo dời lịch học:\n\n" + res.notifications.join("\n"));
      }
      window.location.reload();
    } catch (err) {
      alert("Không thể lập lại lịch: " + err.message);
    }
  };

  return (
    <div ref={dropdownRef} style={{ position: "relative" }}>
      <button 
        type="button"
        onClick={() => setDropdownOpen(!dropdownOpen)}
        style={{
          background: "transparent",
          border: "none",
          cursor: "pointer",
          position: "relative",
          padding: "6px",
          borderRadius: "50%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--text-main)",
          transition: "background 0.2s"
        }}
        className="hover-btn"
      >
        <Bell size={20} />
        {missedTasks.length > 0 && (
          <span style={{
            position: "absolute",
            top: "2px",
            right: "2px",
            backgroundColor: "#ef4444",
            color: "#ffffff",
            fontSize: "10px",
            fontWeight: "bold",
            borderRadius: "50%",
            width: "16px",
            height: "16px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center"
          }}>
            {missedTasks.length}
          </span>
        )}
      </button>
      
      {dropdownOpen && (
        <div style={{
          position: "absolute",
          top: "100%",
          right: 0,
          marginTop: "8px",
          width: "320px",
          backgroundColor: "#ffffff",
          borderRadius: "12px",
          boxShadow: "0 10px 25px rgba(0,0,0,0.1)",
          border: "1px solid #e2e8f0",
          zIndex: 1000,
          padding: "16px"
        }}>
          <h4 style={{ margin: "0 0 12px 0", fontSize: "15px", fontWeight: "bold", color: "#1f2937", display: "flex", alignItems: "center", gap: "6px" }}>
            <span>🔔 Thông báo trễ hạn</span>
          </h4>
          {missedTasks.length === 0 ? (
            <p style={{ margin: 0, fontSize: "13px", color: "#64748b" }}>Chúc mừng! Bạn không bỏ lỡ nhiệm vụ nào trong tuần này.</p>
          ) : (
            <>
              <p style={{ margin: "0 0 12px 0", fontSize: "13px", color: "#ef4444", fontWeight: 500 }}>
                Bạn đã trễ {missedTasks.length} nhiệm vụ học tập tuần này:
              </p>
              <div style={{ maxHeight: "180px", overflowY: "auto", marginBottom: "16px", display: "flex", flexDirection: "column", gap: "8px" }}>
                {missedTasks.map((t) => (
                  <div key={t.id} style={{ padding: "8px", backgroundColor: "#fef2f2", border: "1px solid #fee2e2", borderRadius: "6px" }}>
                    <strong style={{ fontSize: "12px", color: "#991b1b", display: "block" }}>{t.title || t.topicTitle}</strong>
                    <span style={{ fontSize: "11px", color: "#b91c1c" }}>
                      Lịch: {t.startAt ? new Date(t.startAt).toLocaleDateString("vi-VN") : "Chưa lên lịch"}
                    </span>
                  </div>
                ))}
              </div>
              <button 
                type="button"
                onClick={handleReschedule}
                style={{
                  width: "100%",
                  backgroundColor: "#ef4444",
                  color: "#ffffff",
                  border: "none",
                  padding: "8px 12px",
                  borderRadius: "6px",
                  fontWeight: "bold",
                  fontSize: "13px",
                  cursor: "pointer",
                  transition: "background 0.2s"
                }}
              >
                Lập lại lịch ngay
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

export function TopNav({ active = "dashboard", compact = false, tone = "default" }) {
  const navItems = [
    { id: "dashboard", label: "Trang chủ", to: "/dashboard", icon: Home },
    { id: "courses", label: "Môn học", to: "/courses", icon: BookOpen },
    { id: "schedule", label: "Lịch học", to: "/schedule", icon: CalendarDays }
  ];

  const user = getCurrentUser();
  const initials = user?.username ? user.username.slice(0, 2).toUpperCase() : "SF";

  return (
    <header className={`top-nav top-nav-${tone} ${compact ? "top-nav-compact" : ""}`}>
      <div className="top-nav-left">
        <AppLink to="/dashboard" className="brand">
          <span className="brand-mark"><Sparkles size={18} /></span>
          <span>StudyFlow</span>
        </AppLink>
        <nav className="nav-links" aria-label="Điều hướng chính">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <AppLink key={item.id} to={item.to} className={`nav-link ${active === item.id ? "active" : ""}`}>
                <Icon size={15} strokeWidth={2.1} />
                <span>{item.label}</span>
              </AppLink>
            );
          })}
        </nav>
      </div>
      <div className="top-nav-actions" style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        <NotificationRing />
        <IconButton icon={LogOut} label="Đăng xuất" onClick={logout} />
        <Avatar initials={initials} />
      </div>
    </header>
  );
}

export function SimpleTopBar({ title = "StudyFlow", calendar = false }) {
  const user = getCurrentUser();
  const initials = user?.username ? user.username.slice(0, 2).toUpperCase() : "SF";

  return (
    <header className="simple-topbar">
      <button type="button" className="brand simple-brand" onClick={() => navigate(calendar ? "/schedule" : "/dashboard")}>
        <span className="brand-mark">{calendar ? <CalendarDays size={18} /> : <Sparkles size={18} />}</span>
        <span>{title}</span>
      </button>
      <div className="simple-actions" style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        <NotificationRing />
        <IconButton icon={LogOut} label="Đăng xuất" onClick={logout} />
        <Avatar initials={initials} />
      </div>
    </header>
  );
}

export function SectionHeader({ eyebrow, title, subtitle, action }) {
  return (
    <div className="section-header">
      <div>
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h2>{title}</h2>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function SegmentedControl({ options, active, onChange, className = "" }) {
  return (
    <div className={`segmented ${className}`}>
      {options.map((option) => (
        <button
          key={option}
          type="button"
          className={option === active ? "active" : ""}
          onClick={() => onChange(option)}
        >
          {option}
        </button>
      ))}
    </div>
  );
}

export function Modal({ title, open, onClose, children, footer, className = "" }) {
  useEffect(() => {
    if (!open) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === "Escape") onClose?.();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;
  const handleBackdropClick = (event) => {
    if (event.target === event.currentTarget) onClose?.();
  };

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label={title} onClick={handleBackdropClick}>
      <div className={`modal ${className}`}>
        <div className="modal-header">
          <h2>{title}</h2>
          <IconButton icon={Menu} label="Đóng" onClick={onClose} />
        </div>
        <div className="modal-body">{children}</div>
        {footer ? <div className="modal-footer">{footer}</div> : null}
      </div>
    </div>
  );
}

export function SelectButton({ children }) {
  return (
    <button type="button" className="select-btn">
      <span>{children}</span>
      <ChevronDown size={15} />
    </button>
  );
}

export function CheckPill({ checked, children, tone = "green" }) {
  return (
    <span className={`check-pill ${checked ? "checked" : ""} tone-${tone}`}>
      <Check size={14} />
      {children}
    </span>
  );
}

export function AddButton({ children, onClick, className = "" }) {
  return <Button variant="primary" icon={Plus} onClick={onClick} className={className}>{children}</Button>;
}

export function ToolbarIconGroup() {
  return (
    <div className="toolbar-icon-group">
      <IconButton icon={LayoutGrid} label="Dạng lưới" className="active" />
      <IconButton icon={Menu} label="Dạng danh sách" />
    </div>
  );
}
