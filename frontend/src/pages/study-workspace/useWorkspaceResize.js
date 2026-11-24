import { useCallback, useState, useEffect } from "react";
import { clamp, MAX_LEFT_WIDTH, MAX_RIGHT_WIDTH, MIN_CENTER_WIDTH, MIN_LEFT_WIDTH, MIN_RIGHT_WIDTH } from "./helpers.js";

export function useWorkspaceResize() {
  const [isManuallyResized, setIsManuallyResized] = useState(false);
  const [leftWidth, setLeftWidth] = useState(() => {
    const w = typeof window !== "undefined" ? window.innerWidth : 1200;
    return Math.max(MIN_LEFT_WIDTH, Math.floor(w * 0.3));
  });
  const [rightWidth, setRightWidth] = useState(() => {
    const w = typeof window !== "undefined" ? window.innerWidth : 1200;
    return Math.max(MIN_RIGHT_WIDTH, Math.floor(w * 0.3));
  });
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);

  useEffect(() => {
    if (isManuallyResized) return;
    const handleResize = () => {
      const w = window.innerWidth;
      const target = Math.floor(w * 0.3);
      // Ensure Center column gets MIN_CENTER_WIDTH (400px) and resizers take 16px
      const maxAllowed = Math.floor((w - MIN_CENTER_WIDTH - 16) / 2);
      const safeWidth = Math.min(target, maxAllowed);
      setLeftWidth(clamp(safeWidth, MIN_LEFT_WIDTH, MAX_LEFT_WIDTH));
      setRightWidth(clamp(safeWidth, MIN_RIGHT_WIDTH, MAX_RIGHT_WIDTH));
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [isManuallyResized]);

  const beginResize = useCallback((side) => (event) => {
    event.preventDefault();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    document.body.classList.add("is-resizing-workspace");
    setIsManuallyResized(true);

    const handleMove = (moveEvent) => {
      const viewportWidth = window.innerWidth;
      if (side === "left") {
        const maxLeft = Math.min(MAX_LEFT_WIDTH, viewportWidth - rightWidth - MIN_CENTER_WIDTH - 16);
        setLeftWidth(clamp(moveEvent.clientX, MIN_LEFT_WIDTH, Math.max(MIN_LEFT_WIDTH, maxLeft)));
        return;
      }
      const proposedRight = viewportWidth - moveEvent.clientX;
      const maxRight = Math.min(MAX_RIGHT_WIDTH, viewportWidth - leftWidth - MIN_CENTER_WIDTH - 16);
      setRightWidth(clamp(proposedRight, MIN_RIGHT_WIDTH, Math.max(MIN_RIGHT_WIDTH, maxRight)));
    };

    const handleUp = () => {
      document.body.classList.remove("is-resizing-workspace");
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
      window.removeEventListener("pointercancel", handleUp);
    };

    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
    window.addEventListener("pointercancel", handleUp);
  }, [leftWidth, rightWidth]);

  return {
    beginResize, leftCollapsed, leftWidth, rightCollapsed, rightWidth,
    setLeftCollapsed, setRightCollapsed
  };
}
