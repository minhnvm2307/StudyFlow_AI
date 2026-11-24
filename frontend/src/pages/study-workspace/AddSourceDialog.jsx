import { useState } from "react";
import { FileText, Upload } from "lucide-react";
import { Button, Modal } from "../../components/common.jsx";

export function AddSourceModal({ open, onClose, onSubmit, busy, error }) {
  const [mode, setMode] = useState("file");
  const [files, setFiles] = useState([]);
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("pasted-notes.txt");
  const [text, setText] = useState("");

  const resetAndClose = () => {
    setFiles([]);
    setUrl("");
    setTitle("pasted-notes.txt");
    setText("");
    onClose();
  };

  const submit = async () => {
    const ok = await onSubmit({ mode, files, url, title, text });
    if (ok) {
      setFiles([]);
      setUrl("");
      setTitle("pasted-notes.txt");
      setText("");
    }
  };

  return (
    <Modal
      title="Thêm tài liệu"
      open={open}
      onClose={busy ? undefined : resetAndClose}
      footer={
        <>
          <Button variant="secondary" onClick={resetAndClose} disabled={busy}>Hủy</Button>
          <Button variant="primary" onClick={submit} disabled={busy}>{busy ? "Đang xử lý..." : "Tạo tài liệu"}</Button>
        </>
      }
    >
      <div className="add-source-modal">
        <div className="source-mode-tabs">
          {[
            ["file", "File"],
            ["text", "Paste text"],
            ["web", "Website"]
          ].map(([value, label]) => (
            <button key={value} type="button" className={mode === value ? "active" : ""} onClick={() => setMode(value)} disabled={busy}>{label}</button>
          ))}
        </div>

        {mode === "file" ? (
          <label className="source-dropzone">
            <Upload size={24} />
            <strong>Upload tài liệu</strong>
            <span>Hỗ trợ DOCX, PDF, TXT, MD. Có thể chọn nhiều file.</span>
            <input accept=".docx,.pdf,.txt,.md,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" type="file" multiple onChange={(event) => setFiles(Array.from(event.target.files || []))} disabled={busy} />
          </label>
        ) : null}

        {mode === "file" && files.length ? (
          <div className="selected-source-list">
            {files.map((file) => <span key={`${file.name}-${file.size}`}><FileText size={14} />{file.name}</span>)}
          </div>
        ) : null}

        {mode === "text" ? (
          <div className="form-grid">
            <label>
              <span>Tên tài liệu</span>
              <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="chapter-1-notes.txt" disabled={busy} />
            </label>
            <label>
              <span>Nội dung</span>
              <textarea rows="7" value={text} onChange={(event) => setText(event.target.value)} placeholder="Dán ghi chú, syllabus, outline chương/topic..." disabled={busy} />
            </label>
          </div>
        ) : null}

        {mode === "web" ? (
          <label className="field">
            <span>Website URL</span>
            <input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://..." disabled={busy} />
          </label>
        ) : null}

        {error ? <div className="onboarding-error">{error}</div> : null}
      </div>
    </Modal>
  );
}
