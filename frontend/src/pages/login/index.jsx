import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ArrowRight, CheckCircle2, LogIn, Sparkles, UserPlus } from "lucide-react";
import { Button, SegmentedControl } from "../../components/shared/common.jsx";
import { navigate } from "../../router.jsx";
import { saveCurrentSession } from "../../services/authSession.js";
import { authApi } from "../../services/studyflowApi.js";

const MODES = ["Login", "Register"];

const LOGIN_POINTS = [
  "Roadmap, lịch học và AI practice nối vào cùng một study cockpit.",
  "Chuyển từ tài liệu sang quiz và flashcard mà không rơi khỏi ngữ cảnh học.",
  "Cùng visual system, cùng nhịp chuyển động như landing page của StudyFlow."
];

export default function LoginPage() {
  const [mode, setMode] = useState("Login");
  const [form, setForm] = useState({ email: "", username: "", identifier: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const reduceMotion = useReducedMotion();

  const update = (field) => (event) => {
    setForm((current) => ({ ...current, [field]: event.target.value }));
    setError("");
  };

  const submit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const user = mode === "Register"
        ? await authApi.register({ email: form.email, username: form.username, password: form.password })
        : await authApi.login({ identifier: form.identifier, password: form.password });
      saveCurrentSession(user);
      navigate("/dashboard");
    } catch (err) {
      setError(err.message || "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  const isRegister = mode === "Register";

  return (
    <main className="login-shell login-shell-vivid">
      <div className="login-aurora login-aurora-left" aria-hidden="true" />
      <div className="login-aurora login-aurora-right" aria-hidden="true" />

      <motion.section
        className="login-stage"
        initial={reduceMotion ? false : { opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      >
        <aside className="login-story">
          <a
            href="/"
            className="login-story-brand"
            onClick={(event) => {
              event.preventDefault();
              navigate("/");
            }}
          >
            <span className="brand-mark"><Sparkles size={18} /></span>
            <div>
              <strong>StudyFlow</strong>
              <small>Study operating system</small>
            </div>
          </a>

          <div className="login-story-copy">
            <h1>{isRegister ? "Tạo studio học tập của bạn." : "Quay lại nhịp học đang chạy."}</h1>
            <p>
              {isRegister
                ? "Chỉ vài bước để biến tài liệu, lịch học và AI practice thành một hệ làm việc liền mạch."
                : "Đăng nhập để tiếp tục dashboard, lịch học và workspace AI mà bạn đã thiết lập."}
            </p>
          </div>

          <div className="login-story-panel" aria-hidden="true">
            <div className="login-mini-window">
              <div className="login-mini-header">
                <span />
                <span />
                <span />
              </div>
              <div className="login-mini-body">
                <div className="login-mini-card login-mini-card-wide">
                  <small>Current focus</small>
                  <strong>Review • Vector space</strong>
                  <div className="login-mini-progress"><span /></div>
                </div>
                <div className="login-mini-grid">
                  <div className="login-mini-card">
                    <small>Mastery</small>
                    <strong>78%</strong>
                  </div>
                  <div className="login-mini-card">
                    <small>Quiz ready</small>
                    <strong>12</strong>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="login-story-points">
            {LOGIN_POINTS.map((point) => (
              <div key={point} className="login-story-point">
                <CheckCircle2 size={16} />
                <span>{point}</span>
              </div>
            ))}
          </div>
        </aside>

        <form className="login-panel login-panel-vivid" onSubmit={submit}>
          <div className="login-panel-top">
            <div className="login-brand">
              <span className="brand-mark">{isRegister ? <UserPlus size={18} /> : <LogIn size={18} />}</span>
              <div>
                <h2>{isRegister ? "Create account" : "Sign in"}</h2>
                <p>{isRegister ? "Bắt đầu với course đầu tiên của bạn." : "Tiếp tục phiên học và tiến độ gần nhất."}</p>
              </div>
            </div>

            <SegmentedControl
              options={MODES}
              active={mode}
              onChange={(next) => {
                setMode(next);
                setError("");
              }}
              className="login-switch"
            />
          </div>

          <AnimatePresence mode="wait">
            <motion.div
              key={mode}
              className="login-fields"
              initial={reduceMotion ? false : { opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduceMotion ? undefined : { opacity: 0, y: -10 }}
              transition={{ duration: 0.22 }}
            >
              {isRegister ? (
                <>
                  <label>
                    <span>Email</span>
                    <input type="email" value={form.email} onChange={update("email")} autoComplete="email" placeholder="ban@vinuni.edu.vn" required />
                  </label>
                  <label>
                    <span>Username</span>
                    <input value={form.username} onChange={update("username")} autoComplete="username" minLength={3} pattern="[A-Za-z0-9_\.\-]{3,}" placeholder="username A" required />
                  </label>
                </>
              ) : (
                <label>
                  <span>Username or email</span>
                  <input value={form.identifier} onChange={update("identifier")} autoComplete="username" placeholder="username A or uet@vnu.edu.vn" required />
                </label>
              )}

              <label>
                <span>Password</span>
                <input type="password" value={form.password} onChange={update("password")} autoComplete={isRegister ? "new-password" : "current-password"} minLength={3} pattern="[A-Za-z0-9_\.\-]{3,}" placeholder={isRegister ? "Tạo mật khẩu" : "Nhập mật khẩu"} required />
              </label>
            </motion.div>
          </AnimatePresence>

          {!isRegister && (
            <button
              type="button"
              className="login-demo-button"
              onClick={() => setForm({ email: "", username: "", identifier: "test", password: "test" })}
            >
              <Sparkles size={15} />
              Dùng tài khoản demo `test / test`
            </button>
          )}

          {error ? <p className="login-error">{error}</p> : null}

          <Button type="submit" variant="primary" icon={isRegister ? UserPlus : ArrowRight} disabled={loading} className="login-submit">
            {loading ? "Please wait" : isRegister ? "Create account" : "Continue to dashboard"}
          </Button>
        </form>
      </motion.section>
    </main>
  );
}
