import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  ArrowRight,
  BookOpen,
  Bot,
  BrainCircuit,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Layers,
  Sparkles,
  Stars,
  Zap
} from "lucide-react";
import { navigate } from "../../router.jsx";
import { getCurrentUser } from "../../services/authSession.js";
import "./landing.css";

const FEATURES = [
  {
    id: "roadmap",
    title: "Roadmap",
    eyebrow: "Knowledge map",
    icon: Layers,
    subtitle: "Syllabus thành bản đồ topic có thứ tự học",
    description: "StudyFlow tách cấu trúc môn học từ tài liệu gốc, nối topic theo logic học và đánh dấu phần nào đang yếu để bạn không ôn dàn trải.",
    highlights: [
      { title: "Node theo chủ đề", desc: "Mỗi topic mang trạng thái mastery riêng và biết nó nối với phần nào trước sau." },
      { title: "Nhìn được nhịp học", desc: "Bạn biết nên học nền tảng nào trước khi nhảy vào bài luyện nặng." }
    ],
    metric: "36 topic"
  },
  {
    id: "schedule",
    title: "Schedule",
    eyebrow: "Time orchestration",
    icon: CalendarDays,
    subtitle: "Tự động phân phiên học vào khoảng trống thật",
    description: "Các phiên ôn được đặt vào thời gian phù hợp và có thể tái cấu trúc nếu bạn lỡ nhịp, thay vì phải chỉnh thủ công từng ngày.",
    highlights: [
      { title: "Không chồng lịch", desc: "Lịch học được xếp theo quỹ thời gian còn trống thay vì kéo thả cả tuần." },
      { title: "Tự hồi phục", desc: "Missed task được đưa lại vào flow với mức ưu tiên phù hợp." }
    ],
    metric: "48h plan"
  },
  {
    id: "workspace",
    title: "Workspace",
    eyebrow: "Guided practice",
    icon: Bot,
    subtitle: "Hỏi đáp, quiz và flashcard trong cùng một không gian",
    description: "Bạn có thể chuyển từ đọc tài liệu sang hỏi AI, rồi sinh quiz hoặc flashcard mà không đổi ngữ cảnh học.",
    highlights: [
      { title: "RAG có nguồn", desc: "Câu trả lời bám tài liệu thay vì trả lời chung chung." },
      { title: "Thực hành ngay", desc: "Từ câu trả lời có thể bẻ thẳng sang quiz, flashcard hoặc lịch ôn." }
    ],
    metric: "3 tools"
  },
  {
    id: "library",
    title: "Library",
    eyebrow: "Source intake",
    icon: BookOpen,
    subtitle: "Đưa slide, giáo trình và note vào cùng một pipeline",
    description: "Toàn bộ tài liệu của từng môn được gom về cùng một studio dữ liệu để nuôi roadmap, lịch học và practice.",
    highlights: [
      { title: "Nhập liệu nhanh", desc: "Slide, PDF, note và văn bản đều đi vào cùng một quy trình xử lý." },
      { title: "Mode học rõ", desc: "Ôn thi tăng tốc và học kỳ liên tục tạo ra kế hoạch khác nhau." }
    ],
    metric: "42 docs"
  }
];

const HERO_METRICS = [
  { value: "1", label: "Dashboard quyết định bạn nên học gì tiếp theo" },
  { value: "3", label: "Bước từ tài liệu tới roadmap, lịch học và practice" },
  { value: "24/7", label: "Nhịp hỗ trợ liên tục cho browser desktop" }
];

function FeatureScene({ featureId, metric }) {
  const screenshotMap = {
    roadmap: "/screenshots/roadmap.png",
    schedule: "/screenshots/schedule.png",
    workspace: "/screenshots/workspace.png",
    library: "/screenshots/courses.png"
  };
  
  const src = screenshotMap[featureId] || "/screenshots/dashboard.png";
  
  return (
    <div className="scene-screenshot-container" style={{ width: "100%", height: "100%", overflow: "hidden", display: "flex", alignItems: "center", justifyContent: "center", background: "#f8faf7" }}>
      <img 
        src={src} 
        alt={`Screenshot showing ${featureId} feature`} 
        style={{ 
          width: "100%", 
          height: "100%", 
          objectFit: "cover",
          objectPosition: "top center",
          borderRadius: "14px",
          boxShadow: "inset 0 0 0 1px rgba(0,0,0,0.06)"
        }} 
      />
    </div>
  );
}

export default function LandingPage() {
  const [activeTabId, setActiveTabId] = useState("roadmap");
  const [tilt, setTilt] = useState({ rotateX: -6, rotateY: 8 });
  const currentUser = getCurrentUser();
  const reduceMotion = useReducedMotion();
  const visualRef = useRef(null);

  useEffect(() => {
    if (reduceMotion) return undefined;
    const timer = setTimeout(() => {
      const currentIndex = FEATURES.findIndex((feature) => feature.id === activeTabId);
      const nextIndex = (currentIndex + 1) % FEATURES.length;
      setActiveTabId(FEATURES[nextIndex].id);
    }, 4500);
    return () => clearTimeout(timer);
  }, [activeTabId, reduceMotion]);

  const activeFeature = useMemo(
    () => FEATURES.find((feature) => feature.id === activeTabId) || FEATURES[0],
    [activeTabId]
  );

  const IconComponent = activeFeature.icon;

  const handleStart = () => {
    navigate(currentUser ? "/dashboard" : "/login");
  };

  const handleMouseMove = (event) => {
    if (reduceMotion || !visualRef.current) return;
    const rect = visualRef.current.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width;
    const y = (event.clientY - rect.top) / rect.height;
    setTilt({
      rotateX: (0.5 - y) * 14,
      rotateY: (x - 0.5) * 16
    });
  };

  return (
    <div className="landing-shell landing-shell-contrast">
      <div className="landing-noise" aria-hidden="true" />
      <div className="landing-aurora landing-aurora-left" aria-hidden="true" />
      <div className="landing-aurora landing-aurora-right" aria-hidden="true" />

      <motion.header
        className="landing-header"
        initial={reduceMotion ? false : { opacity: 0, y: -18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.55 }}
      >
        <a
          href="/"
          className="landing-brand"
          onClick={(event) => {
            event.preventDefault();
            navigate("/");
          }}
        >
          <div className="landing-brand-mark">
            <Sparkles size={18} />
          </div>
          <div className="landing-brand-copy">
            <span>StudyFlow</span>
            <small>AI study operating system</small>
          </div>
        </a>

        <div className="landing-nav-actions">
          <button className="landing-btn-secondary" onClick={() => navigate(currentUser ? "/dashboard" : "/login")}>
            {currentUser ? "Vào dashboard" : "Đăng nhập"}
          </button>
          <button className="landing-btn-primary" onClick={handleStart}>
            {currentUser ? "Tiếp tục học" : "Bắt đầu ngay"}
          </button>
        </div>
      </motion.header>

      <main className="landing-main landing-main-compact">
        <section className="landing-hero">
          <motion.div
            className="landing-hero-copy"
            initial={reduceMotion ? false : { opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7 }}
          >
            <div className="landing-badge">
              <Stars size={14} />
              Tài liệu vào một nơi, quyết định học ra ngay
            </div>
            <h1>
              Từ giáo trình tới
              <span> roadmap, lịch học và practice AI</span>
            </h1>
            <p>
              StudyFlow không chỉ lưu tài liệu. Nó tổ chức chúng thành một study cockpit để bạn biết học gì tiếp theo, khi nào cần tăng tốc và chỗ nào nên luyện lại.
            </p>

            <div className="landing-hero-actions">
              <button className="landing-btn-primary" onClick={handleStart}>
                Mở StudyFlow
                <ArrowRight size={16} />
              </button>
              <button
                className="landing-btn-secondary"
                onClick={() => document.getElementById("features-section")?.scrollIntoView({ behavior: "smooth" })}
              >
                Xem hệ thống hoạt động
              </button>
            </div>

            <div className="landing-hero-metrics">
              {HERO_METRICS.map((metric) => (
                <div key={metric.label} className="hero-metric-card">
                  <strong>{metric.value}</strong>
                  <span>{metric.label}</span>
                </div>
              ))}
            </div>
          </motion.div>

          <motion.div
            className="landing-hero-visual"
            initial={reduceMotion ? false : { opacity: 0, scale: 0.97, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.08 }}
          >
            <div
              ref={visualRef}
              className="cockpit-stage cockpit-stage-compact"
              onMouseMove={handleMouseMove}
              onMouseLeave={() => setTilt({ rotateX: -6, rotateY: 8 })}
              style={{
                transform: reduceMotion ? "none" : `perspective(1800px) rotateX(${tilt.rotateX}deg) rotateY(${tilt.rotateY}deg)`
              }}
            >
              <div className="cockpit-grid" aria-hidden="true" />
              <div className="cockpit-orbit orbit-a">
                <BrainCircuit size={15} />
                <span>AI study loop</span>
              </div>
              <div className="cockpit-orbit orbit-b">
                <Clock3 size={15} />
                <span>Adaptive flow</span>
              </div>
              <div className="cockpit-orbit orbit-c">
                <Zap size={15} />
                <span>{activeFeature.metric}</span>
              </div>

              <motion.div
                className="cockpit-glass-card cockpit-card-primary"
                animate={reduceMotion ? undefined : { y: [0, -8, 0] }}
                transition={{ duration: 5.8, repeat: Infinity, ease: "easeInOut" }}
              >
                <div className="cockpit-card-topline">
                  <span className="cockpit-pill">Current system</span>
                  <span className="cockpit-live-dot">Live</span>
                </div>
                <strong>{activeFeature.subtitle}</strong>
                <p>{activeFeature.description}</p>
              </motion.div>

              <motion.div
                className="cockpit-screen cockpit-screen-generated"
                animate={reduceMotion ? undefined : { y: [0, 12, 0] }}
                transition={{ duration: 7, repeat: Infinity, ease: "easeInOut" }}
              >
                <div className="cockpit-screen-header">
                  <div className="browser-dots">
                    <span className="browser-dot close" />
                    <span className="browser-dot minimize" />
                    <span className="browser-dot maximize" />
                  </div>
                  <div className="browser-address">studyflow.ai/system-preview</div>
                </div>
                <div className="cockpit-screen-body cockpit-screen-generated-body">
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={activeFeature.id}
                      initial={reduceMotion ? false : { opacity: 0, x: 14 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={reduceMotion ? undefined : { opacity: 0, x: -14 }}
                      transition={{ duration: 0.32 }}
                    >
                      <FeatureScene featureId={activeFeature.id} metric={activeFeature.metric} />
                    </motion.div>
                  </AnimatePresence>
                </div>
              </motion.div>
            </div>
          </motion.div>
        </section>

        <section id="features-section" className="showcase-section showcase-section-tight">
          <div className="section-kicker">
            <span>Four layers, one workflow</span>
            <h2>Mỗi lớp làm một việc rõ ràng, nhưng tất cả nối vào cùng một nhịp học.</h2>
          </div>

          <div className="showcase-tabs" role="tablist" aria-label="Tính năng chính">
            {FEATURES.map((feature) => {
              const TabIcon = feature.icon;
              return (
                <button
                  key={feature.id}
                  className={`showcase-tab ${activeTabId === feature.id ? "active" : ""}`}
                  onClick={() => setActiveTabId(feature.id)}
                  role="tab"
                  aria-selected={activeTabId === feature.id}
                >
                  <span className="showcase-tab-icon">
                    <TabIcon size={16} />
                  </span>
                  <span className="showcase-tab-copy">
                    <small>{feature.eyebrow}</small>
                    <strong>{feature.title}</strong>
                  </span>
                </button>
              );
            })}
          </div>

          <motion.div
            className="showcase-grid showcase-grid-compact"
            initial={reduceMotion ? false : { opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 0.65 }}
          >
            <div className="feature-info feature-info-wide">
              <div className="feature-info-header">
                <span>{activeFeature.eyebrow}</span>
                <h3>
                  <IconComponent size={22} />
                  {activeFeature.subtitle}
                </h3>
                <p className="feature-desc">{activeFeature.description}</p>
              </div>

              <div className="feature-highlights">
                {activeFeature.highlights.map((highlight) => (
                  <div key={highlight.title} className="highlight-item">
                    <CheckCircle2 size={16} />
                    <div>
                      <strong>{highlight.title}</strong>
                      <span>{highlight.desc}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="landing-cta-card">
              <span className="cta-kicker">Ready to start?</span>
              <h3>Một nơi để xem, quyết định và luyện.</h3>
              <p>Không cần ảnh demo của hệ thống thật để hiểu flow. Đây là cấu trúc trải nghiệm mà StudyFlow đang xây cho người học.</p>
              <button className="landing-btn-primary" onClick={handleStart}>
                {currentUser ? "Mở dashboard" : "Đăng nhập để bắt đầu"}
                <ArrowRight size={16} />
              </button>
            </div>
          </motion.div>
        </section>
      </main>

      <footer className="landing-footer">
        <p>&copy; 2026 StudyFlow AI. Một study cockpit cho tài liệu, lịch học và practice AI trên desktop.</p>
      </footer>
    </div>
  );
}
