const SESSION_KEY = "studyflow.currentUser";
const SESSION_EVENT = "studyflow-auth-changed";

function isValidSession(value) {
  return Boolean(value?.user?.id && value?.accessToken);
}

function normalizeSession(session) {
  if (!isValidSession(session)) return null;

  const expiresAt = Number(session.expiresAt);
  if (Number.isFinite(expiresAt) && expiresAt <= Date.now()) return null;

  return {
    user: session.user,
    accessToken: session.accessToken,
    expiresAt: Number.isFinite(expiresAt) ? expiresAt : null,
  };
}

function clearStoredSession() {
  window.localStorage.removeItem(SESSION_KEY);
}

export function getCurrentSession() {
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    if (!raw) return null;

    const parsed = JSON.parse(raw);
    const session = normalizeSession(parsed);
    if (!session) {
      clearStoredSession();
      return null;
    }
    return session;
  } catch {
    clearStoredSession();
    return null;
  }
}

export function getCurrentUser() {
  return getCurrentSession()?.user ?? null;
}

export function getAccessToken() {
  return getCurrentSession()?.accessToken ?? null;
}

export function saveCurrentUser(session) {
  const normalized = normalizeSession(session);
  if (!normalized) {
    clearCurrentSession();
    return;
  }
  window.localStorage.setItem(SESSION_KEY, JSON.stringify(normalized));
  window.dispatchEvent(new CustomEvent(SESSION_EVENT, { detail: normalized.user }));
}

export function saveCurrentSession(authPayload) {
  if (!authPayload?.user || !authPayload?.accessToken) {
    clearCurrentSession();
    return;
  }
  const expiresIn = Number(authPayload.expiresIn);
  saveCurrentUser({
    user: authPayload.user,
    accessToken: authPayload.accessToken,
    expiresAt: Number.isFinite(expiresIn) ? Date.now() + (expiresIn * 1000) : null,
  });
}

export function clearCurrentSession() {
  clearStoredSession();
  window.dispatchEvent(new CustomEvent(SESSION_EVENT, { detail: null }));
}

export function clearCurrentUser() {
  clearCurrentSession();
}

export function onAuthChange(callback) {
  const handler = (event) => callback(event.detail ?? getCurrentUser());
  window.addEventListener(SESSION_EVENT, handler);
  return () => window.removeEventListener(SESSION_EVENT, handler);
}
