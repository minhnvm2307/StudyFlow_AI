export function buildLegacySetupRedirectPath(pathname, search = "") {
  const studyMatch = pathname.match(/^\/study\/([^/]+)$/);
  if (!studyMatch) return "";

  const params = new URLSearchParams(search || "");
  const isCreatedFlow = params.get("created") === "1";
  const hasExplicitWorkspaceTarget = params.has("task") || params.has("topic") || params.has("thread");

  if (!isCreatedFlow || hasExplicitWorkspaceTarget) return "";

  return `/courses/detail/${studyMatch[1]}${search || ""}`;
}

export function buildWorkspaceBackPath(pathname, search = "") {
  const studyMatch = pathname.match(/^\/study\/([^/?]+)/);
  if (!studyMatch) return "/courses";

  const params = new URLSearchParams(search || "");
  const returnTo = params.get("returnTo") || "";
  const isSafeInternalReturnPath = returnTo.startsWith("/") && !returnTo.startsWith("//");

  if (isSafeInternalReturnPath) {
    return returnTo;
  }

  return `/courses/detail/${studyMatch[1]}`;
}
