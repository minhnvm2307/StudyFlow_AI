export const MIN_LEFT_WIDTH = 300;
export const MAX_LEFT_WIDTH = 800;
export const MIN_RIGHT_WIDTH = 300;
export const MAX_RIGHT_WIDTH = 800;
export const MIN_CENTER_WIDTH = 400;

export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

export function getCourseId() {
  return window.location.pathname.split("/study/")[1]?.split("/")[0] || "";
}
