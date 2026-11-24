import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, Send, Sparkles, ChevronsRight, History, Plus, MessageSquare } from "lucide-react";
import { clamp } from "./helpers.js";

function StarterPrompts({ course, activeTopicId, topics, onSelectPrompt, disabled }) {
  const activeTopic = topics?.find(t => t.id === activeTopicId);
  const subjectName = course?.name || "môn học";

  const prompts = activeTopic 
    ? [
        `Giải thích lý thuyết cốt lõi của chủ đề: ${activeTopic.title}`,
        `Lấy ví dụ thực tế minh họa cho chủ đề: ${activeTopic.title}`,
        `Tóm tắt các ý chính trong tài liệu về: ${activeTopic.title}`,
        `Hãy hỏi tôi một câu hỏi ôn tập về: ${activeTopic.title}`
      ]
    : [
        `Tóm tắt syllabus và các chương học chính của môn ${subjectName}`,
        `Giải thích các khái niệm quan trọng nhất trong tài liệu học`,
        `Tạo 5 câu hỏi nhanh tự kiểm tra kiến thức môn học này`,
        `Lập sơ đồ tư duy tổng hợp kiến thức môn ${subjectName}`
      ];

  return (
    <div className="conversation-starter">
      <Sparkles size={24} />
      <div>
        <h2>{activeTopic ? `Bạn muốn tìm hiểu về "${activeTopic.title}"?` : "Hãy bắt đầu không gian học của bạn..."}</h2>
        <p style={{ marginBottom: "16px" }}>
          {activeTopic 
            ? `Hãy chọn một câu hỏi gợi ý bên dưới hoặc tự nhập tin nhắn để AI giải thích chi tiết chủ đề "${activeTopic.title}".`
            : "Thêm slide, PDF, đề thi hoặc ghi chú để StudyFlow tạo quiz, flashcard, lịch ôn và trả lời câu hỏi dựa trên nguồn."}
        </p>
        <div className="starter-prompts-grid">
          {prompts.map((p, idx) => (
            <button key={idx} type="button" className="starter-prompt-card" onClick={() => onSelectPrompt(p)} disabled={disabled}>
              {p}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export function CitationChip({ sourceRef, index, inline = false }) {
  const buttonRef = useRef(null);
  const popoverRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [popoverStyle, setPopoverStyle] = useState(null);
  const passage = cleanCitationText(sourceRef.passage || sourceRef.quote || sourceRef.excerpt || "");
  const section = [sourceRef.section, sourceRef.page ? `trang ${sourceRef.page}` : ""].filter(Boolean).join(" · ");
  const tooltipId = `cite-${sourceRef.chunkId || sourceRef.sourceId || "source"}-${index}`;
  const updatePopoverPosition = useCallback(() => {
    const button = buttonRef.current;
    const popover = popoverRef.current;
    if (!button || !popover) return;

    const buttonRect = button.getBoundingClientRect();
    const panelRect = button.closest(".conversation-panel")?.getBoundingClientRect();
    const boundary = panelRect || {
      left: 0,
      top: 0,
      right: window.innerWidth,
      bottom: window.innerHeight,
      width: window.innerWidth
    };
    const margin = 14;
    const availableWidth = Math.max(180, Math.min(window.innerWidth - margin * 2, boundary.width - margin * 2));
    const width = Math.min(380, availableWidth);
    const availableAbove = Math.max(96, buttonRect.top - boundary.top - margin - 10);
    const maxHeight = Math.min(360, availableAbove);
    const height = Math.min(popover.scrollHeight || 0, maxHeight);
    const shouldAlignRight = buttonRect.left + width > boundary.right - margin;
    const rawLeft = shouldAlignRight ? buttonRect.right - width : buttonRect.left;
    const left = clamp(rawLeft, boundary.left + margin, boundary.right - width - margin);
    const rawTop = buttonRect.top - height - 10;
    const top = clamp(rawTop, boundary.top + margin, Math.max(boundary.top + margin, boundary.bottom - height - margin));

    setPopoverStyle({
      left: `${Math.round(left)}px`,
      top: `${Math.round(top)}px`,
      width: `${Math.round(width)}px`,
      maxHeight: `${Math.round(maxHeight)}px`
    });
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    const frame = window.requestAnimationFrame(updatePopoverPosition);
    window.addEventListener("resize", updatePopoverPosition);
    window.addEventListener("scroll", updatePopoverPosition, true);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", updatePopoverPosition);
      window.removeEventListener("scroll", updatePopoverPosition, true);
    };
  }, [open, updatePopoverPosition]);

  const showPopover = () => setOpen(true);
  const hidePopover = () => {
    setOpen(false);
    setPopoverStyle(null);
  };

  return (
    <span className={`citation-wrap ${inline ? "citation-wrap-inline" : ""}`} onMouseEnter={showPopover} onMouseLeave={hidePopover} onFocus={showPopover} onBlur={hidePopover}>
      <button ref={buttonRef} type="button" className={inline ? "inline-cite" : "citation-card"} aria-describedby={tooltipId} aria-expanded={open}>
        [{index + 1}]{inline ? "" : ` ${sourceRef.filename || "Nguồn"}${sourceRef.page ? ` · trang ${sourceRef.page}` : ""}`}
      </button>
      <span ref={popoverRef} id={tooltipId} role="tooltip" className={`citation-popover ${open ? "is-open" : ""}`} style={open ? { ...popoverStyle, visibility: popoverStyle ? "visible" : "hidden" } : undefined}>
        <strong>{sourceRef.filename || "Nguồn học"}</strong>
        {section ? <small>{section}</small> : null}
        <span className="citation-passage">{passage}</span>
      </span>
    </span>
  );
}

function cleanCitationText(text = "") {
  return repairMojibake(String(text || ""))
    .replace(/\u00a0/g, " ")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/\s+([,.;:!?%])/g, "$1")
    .replace(/([([{])\s+/g, "$1")
    .trim();
}

function repairMojibake(text = "") {
  const value = String(text || "");
  if (!/[\u00c2\u00c3\u00c4\u00c6]|\u00e1[\u00ba\u00bb]|\u00c3[\u0080-\u00bf]/u.test(value)) return value;
  const bytes = [];
  for (const char of value) {
    const cp = char.codePointAt(0);
    const byte = windows1252Byte(cp);
    if (byte === null) return value;
    bytes.push(byte);
  }
  const repaired = new TextDecoder("utf-8").decode(new Uint8Array(bytes));
  return mojibakeScore(repaired) < mojibakeScore(value) ? repaired : value;
}

function windows1252Byte(cp) {
  if (cp <= 0xff) return cp;
  return new Map([
    [0x20ac, 0x80], [0x201a, 0x82], [0x0192, 0x83], [0x201e, 0x84],
    [0x2026, 0x85], [0x2020, 0x86], [0x2021, 0x87], [0x02c6, 0x88],
    [0x2030, 0x89], [0x0160, 0x8a], [0x2039, 0x8b], [0x0152, 0x8c],
    [0x017d, 0x8e], [0x2018, 0x91], [0x2019, 0x92], [0x201c, 0x93],
    [0x201d, 0x94], [0x2022, 0x95], [0x2013, 0x96], [0x2014, 0x97],
    [0x02dc, 0x98], [0x2122, 0x99], [0x0161, 0x9a], [0x203a, 0x9b],
    [0x0153, 0x9c], [0x017e, 0x9e], [0x0178, 0x9f]
  ]).get(cp) ?? null;
}

function mojibakeScore(text) {
  return (String(text).match(/[\u00c2\u00c3\u00c4\u00c6]|\u00e1[\u00ba\u00bb]|\u00c3[\u0080-\u00bf]/gu) || []).length;
}

function renderInlineContent(content, refs = [], keyPrefix = "inline") {
  const parts = [];
  const tokenPattern = /(\[(\d+)\]|`([^`]+)`|\*\*([^*]+)\*\*|__([^_]+)__|\*([^*]+)\*|_([^_]+)_)/g;
  let cursor = 0;
  let match;

  while ((match = tokenPattern.exec(content)) !== null) {
    if (match.index > cursor) parts.push(content.slice(cursor, match.index));
    if (match[2]) {
      const refIndex = Number(match[2]) - 1;
      const ref = refs[refIndex];
      parts.push(ref ? <CitationChip key={`${keyPrefix}-cite-${match.index}-${match[2]}`} sourceRef={ref} index={refIndex} inline /> : match[0]);
    } else if (match[3]) {
      parts.push(<code key={`${keyPrefix}-code-${match.index}`}>{match[3]}</code>);
    } else if (match[4] || match[5]) {
      parts.push(<strong key={`${keyPrefix}-strong-${match.index}`}>{match[4] || match[5]}</strong>);
    } else if (match[6] || match[7]) {
      parts.push(<em key={`${keyPrefix}-em-${match.index}`}>{match[6] || match[7]}</em>);
    }
    cursor = match.index + match[0].length;
  }

  if (cursor < content.length) parts.push(content.slice(cursor));
  return parts.length ? parts : content;
}

function MessageMarkdown({ content = "", refs = [] }) {
  const blocks = parseMarkdownBlocks(content);
  return (
    <div className="message-content">
      {blocks.map((block, index) => renderMarkdownBlock(block, refs, index))}
    </div>
  );
}

function parseMarkdownBlocks(content = "") {
  const lines = String(content || "").replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed) {
      index += 1;
      continue;
    }

    if (trimmed.startsWith("```") || trimmed.startsWith("~~~")) {
      const fence = trimmed.slice(0, 3);
      const code = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith(fence)) {
        code.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push({ type: "code", text: code.join("\n") });
      continue;
    }

    const heading = trimmed.match(/^(#{2,4})\s+(.+)$/);
    if (heading) {
      blocks.push({ type: "heading", level: heading[1].length, text: heading[2] });
      index += 1;
      continue;
    }

    if (isTableStart(lines, index)) {
      const rows = [];
      while (index < lines.length && lines[index].trim().startsWith("|") && lines[index].trim().endsWith("|")) {
        rows.push(parseTableRow(lines[index]));
        index += 1;
      }
      blocks.push({ type: "table", header: rows[0] || [], rows: rows.slice(2) });
      continue;
    }

    const listMatch = trimmed.match(/^([-*])\s+(.+)$/) || trimmed.match(/^(\d+)\.\s+(.+)$/);
    if (listMatch) {
      const ordered = /^\d+$/.test(listMatch[1]);
      const items = [];
      while (index < lines.length) {
        const current = lines[index].trim();
        const currentMatch = ordered ? current.match(/^\d+\.\s+(.+)$/) : current.match(/^[-*]\s+(.+)$/);
        if (!currentMatch) break;
        items.push(currentMatch[1]);
        index += 1;
      }
      blocks.push({ type: ordered ? "orderedList" : "unorderedList", items });
      continue;
    }

    const paragraph = [trimmed];
    index += 1;
    while (index < lines.length && shouldContinueParagraph(lines[index])) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push({ type: "paragraph", text: paragraph.join(" ") });
  }

  return blocks.length ? blocks : [{ type: "paragraph", text: content }];
}

function shouldContinueParagraph(line = "") {
  const trimmed = line.trim();
  if (!trimmed) return false;
  if (/^(#{2,4})\s+/.test(trimmed)) return false;
  if (/^([-*])\s+/.test(trimmed) || /^\d+\.\s+/.test(trimmed)) return false;
  if (trimmed.startsWith("```") || trimmed.startsWith("~~~")) return false;
  if (trimmed.startsWith("|") && trimmed.endsWith("|")) return false;
  return true;
}

function isTableStart(lines, index) {
  const first = lines[index]?.trim() || "";
  const second = lines[index + 1]?.trim() || "";
  return first.startsWith("|") && first.endsWith("|") && /^\|\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(second);
}

function parseTableRow(line = "") {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}

function renderMarkdownBlock(block, refs, index) {
  const key = `block-${index}`;
  if (block.type === "heading") {
    return <h3 key={key}>{renderInlineContent(block.text, refs, key)}</h3>;
  }
  if (block.type === "unorderedList") {
    return <ul key={key}>{block.items.map((item, itemIndex) => <li key={`${key}-${itemIndex}`}>{renderInlineContent(item, refs, `${key}-${itemIndex}`)}</li>)}</ul>;
  }
  if (block.type === "orderedList") {
    return <ol key={key}>{block.items.map((item, itemIndex) => <li key={`${key}-${itemIndex}`}>{renderInlineContent(item, refs, `${key}-${itemIndex}`)}</li>)}</ol>;
  }
  if (block.type === "table") {
    return (
      <div key={key} className="message-table-wrap">
        <table>
          <thead><tr>{block.header.map((cell, cellIndex) => <th key={`${key}-h-${cellIndex}`}>{renderInlineContent(cell, refs, `${key}-h-${cellIndex}`)}</th>)}</tr></thead>
          <tbody>{block.rows.map((row, rowIndex) => <tr key={`${key}-r-${rowIndex}`}>{row.map((cell, cellIndex) => <td key={`${key}-r-${rowIndex}-${cellIndex}`}>{renderInlineContent(cell, refs, `${key}-r-${rowIndex}-${cellIndex}`)}</td>)}</tr>)}</tbody>
        </table>
      </div>
    );
  }
  if (block.type === "code") {
    return <pre key={key}><code>{block.text}</code></pre>;
  }
  return <p key={key}>{renderInlineContent(block.text, refs, key)}</p>;
}

function ThinkingHops({ route, tool, hopsCount = 0 }) {
  if (!route) {
    return (
      <div className="thinking-hops">
        <div className="thinking-header">
          <Sparkles className="thinking-sparkle-icon animate-pulse" size={16} />
          <span>Đang định tuyến yêu cầu...</span>
        </div>
      </div>
    );
  }

  let statusText = "Đang suy nghĩ...";
  if (route === "RAG_SEARCH") {
    statusText = hopsCount > 0 
      ? `Đang thực hiện phân tích bước ${hopsCount + 1}...` 
      : "Đang tìm kiếm thông tin trong tài liệu môn học...";
  } else if (route === "TOOL_CALL") {
    const toolName = tool === "get_study_schedule" ? "Lấy lịch học" : tool === "get_number_of_chapters" ? "Lấy số chương" : tool;
    statusText = `Đang chạy công cụ: ${toolName}...`;
  } else if (route === "GENERAL_CHAT") {
    statusText = "Đang soạn câu trả lời...";
  }

  return (
    <div className="thinking-hops">
      <div className="thinking-header">
        <Sparkles className="thinking-sparkle-icon animate-pulse" size={16} />
        <span>{statusText}</span>
      </div>
    </div>
  );
}

function CompletedHops({ hops }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="completed-hops-container">
      <button 
        type="button" 
        className="completed-hops-toggle" 
        onClick={() => setOpen(!open)}
      >
        <Sparkles size={14} className="hops-sparkle" />
        <span>Quá trình suy luận ({hops.length} bước)</span>
        <span className={`toggle-chevron ${open ? "open" : ""}`}>▼</span>
      </button>
      {open && (
        <div className="completed-hops-list">
          {hops.map((hop, index) => (
            <div key={index} className="completed-hop-item">
              <div className="hop-badge">Hop {hop.hop}</div>
              <div className="hop-detail">
                <p className="hop-query">Truy vấn: <code>"{hop.query}"</code></p>
                <p className="hop-meta">Tìm thấy {hop.results_count} đoạn trích (+{hop.new_chunks_added} mới)</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ChatMessage({ message }) {
  if (message.role === "user") {
    return <div className="message user-message"><p>{message.content}</p></div>;
  }

  if (message.isThinking) {
    const hopsAction = message.actions?.find(a => a.type === "reasoning_hops");
    const hops = hopsAction ? hopsAction.hops : null;
    return (
      <div className="message ai-message">
        <div className="ai-avatar"><Bot size={15} /></div>
        <div className="ai-bubble" style={{ minWidth: "280px" }}>
          {hops && hops.length > 0 ? <CompletedHops hops={hops} /> : null}
          <ThinkingHops route={message.route} tool={message.tool} hopsCount={hops?.length || 0} />
        </div>
      </div>
    );
  }

  const hopsAction = message.actions?.find(a => a.type === "reasoning_hops");
  const hops = hopsAction ? hopsAction.hops : null;

  return (
    <div className="message ai-message">
      <div className="ai-avatar"><Bot size={15} /></div>
      <div className="ai-bubble">
        {hops && hops.length > 0 ? <CompletedHops hops={hops} /> : null}
        <MessageMarkdown content={message.content} refs={message.sourceRefs || []} />
        {message.sourceRefs?.length ? (
          <div className="source-citations">
            {message.sourceRefs.map((ref, index) => <CitationChip key={`${ref.sourceId}-${ref.chunkId || index}`} sourceRef={ref} index={index} />)}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function ConversationPanel({ course, sources, messages, activeThreadId, onSend, sending, onToggleCollapsed, activeTopicId, topics, className = "", quizInProgress = false, threads = [], onSelectThread, onNewChat }) {
  const [draft, setDraft] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const submit = () => {
    const message = draft.trim();
    if (!message) return;
    setDraft("");
    onSend(message);
  };

  const quickSuggestions = [
    { label: "Xem lịch học của tôi", text: "Xem lịch học của tôi" },
    { label: "Chương này nội dung là gì", text: "Chương này nội dung là gì" },
    { label: "Môn này có bao nhiêu chương", text: "Môn này có bao nhiêu chương" },
    { label: "Tóm tắt tài liệu", text: "Tóm tắt nội dung chính trong tài liệu" },
    { label: "Giải thích khái niệm cốt lõi", text: "Giải thích chi tiết khái niệm cốt lõi" }
  ];

  return (
    <section className={`conversation-panel ${className}`.trim()} style={{ position: "relative" }}>
      <div className="conversation-head">
        <div>
          <h2>{course?.name || "StudyFlow"}</h2>
          <p>Đang dùng {sources.filter((source) => source.selected).length} nguồn</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          {!quizInProgress && onNewChat && (
            <button
              type="button"
              className="new-chat-header-btn"
              onClick={onNewChat}
              title="Chat mới"
              aria-label="Chat mới"
              style={{
                background: "transparent",
                border: "none",
                cursor: "pointer",
                padding: "6px",
                borderRadius: "6px",
                color: "var(--text-secondary)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                transition: "all 0.2s"
              }}
            >
              <Plus size={20} />
            </button>
          )}
          {!quizInProgress && onSelectThread && (
            <button
              type="button"
              className="history-toggle-btn"
              onClick={() => setShowHistory(!showHistory)}
              title="Lịch sử trò chuyện"
              aria-label="Lịch sử trò chuyện"
              style={{
                background: "transparent",
                border: "none",
                cursor: "pointer",
                padding: "6px",
                borderRadius: "6px",
                color: showHistory ? "var(--primary)" : "var(--text-secondary)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                transition: "all 0.2s"
              }}
            >
              <History size={20} />
            </button>
          )}
          {onToggleCollapsed && (
            <button type="button" className="sidebar-toggle-btn" onClick={onToggleCollapsed} aria-label="Đóng panel chat" title="Đóng panel chat">
              <ChevronsRight size={22} />
            </button>
          )}
        </div>
      </div>

      {showHistory && (
        <div className="chat-history-overlay" style={{
          position: "absolute",
          top: "68px",
          right: 0,
          bottom: 0,
          left: 0,
          background: "var(--bg-surface-elevated, #ffffff)",
          zIndex: 10,
          display: "flex",
          flexDirection: "column",
          padding: "16px",
          borderTop: "1px solid var(--border-light, #e2e8f0)"
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
            <h3 style={{ fontSize: "15px", fontWeight: "700", margin: 0, color: "var(--text-primary)" }}>Lịch sử hội thoại</h3>
            <button
              type="button"
              onClick={() => {
                onNewChat?.();
                setShowHistory(false);
              }}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                padding: "6px 12px",
                fontSize: "12px",
                fontWeight: "600",
                background: "var(--primary)",
                color: "#ffffff",
                border: "none",
                borderRadius: "6px",
                cursor: "pointer"
              }}
            >
              <Plus size={14} /> Chat mới
            </button>
          </div>
          
          <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: "8px" }}>
            {threads.length === 0 ? (
              <p style={{ color: "var(--text-secondary)", fontSize: "13px", fontStyle: "italic", textAlign: "center", marginTop: "24px" }}>
                Chưa có hội thoại nào trước đó.
              </p>
            ) : (
              threads.map((thread) => {
                const isActive = thread.id === activeThreadId;
                return (
                  <button
                    key={thread.id}
                    type="button"
                    onClick={() => {
                      onSelectThread?.(thread);
                      setShowHistory(false);
                    }}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "10px",
                      width: "100%",
                      padding: "10px 12px",
                      borderRadius: "8px",
                      border: isActive ? "1px solid var(--primary)" : "1px solid var(--border-light, #e2e8f0)",
                      background: isActive ? "var(--primary-soft, #f4fbf0)" : "transparent",
                      color: isActive ? "var(--primary-dark, #3f6212)" : "var(--text-primary)",
                      textAlign: "left",
                      fontSize: "13px",
                      fontWeight: isActive ? "600" : "500",
                      cursor: "pointer",
                      transition: "all 0.2s"
                    }}
                  >
                    <MessageSquare size={16} style={{ flexShrink: 0, color: isActive ? "var(--primary)" : "var(--text-secondary)" }} />
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {thread.title || "Cuộc trò chuyện mới"}
                    </span>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}

      <div ref={scrollRef} className="conversation-scroll">
        {!messages.length ? <StarterPrompts course={course} activeTopicId={activeTopicId} topics={topics} onSelectPrompt={onSend} disabled={quizInProgress} /> : null}
        {messages.map((message) => <ChatMessage key={message.id} message={message} />)}
      </div>
      {!quizInProgress ? (
        <div className="quick-suggestions-row">
          {quickSuggestions.map((suggestion, idx) => (
            <button
              key={idx}
              type="button"
              className="quick-suggestion-chip"
              onClick={() => onSend(suggestion.text)}
              disabled={sending}
            >
              <Sparkles size={13} className="suggestion-sparkle" />
              <span>{suggestion.label}</span>
            </button>
          ))}
        </div>
      ) : null}
      <div className={`chat-composer ${quizInProgress ? "disabled" : ""}`}>
        <textarea
          rows="1"
          disabled={quizInProgress}
          placeholder={quizInProgress ? "Hoàn thành quiz trước khi hỏi AI..." : activeThreadId ? "Đặt câu hỏi hoặc tạo nội dung..." : "Tin nhắn đầu tiên sẽ tạo cuộc trò chuyện mới..."}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !quizInProgress) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <button
          type="button"
          className="send-btn"
          aria-label="Gửi"
          onClick={submit}
          disabled={sending || quizInProgress}
        >
          <Send size={19} />
        </button>
      </div>
    </section>
  );
}
