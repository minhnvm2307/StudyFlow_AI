import { beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";

function createMockWindow() {
  const storage = new Map();
  const listeners = new Map();

  return {
    localStorage: {
      getItem(key) {
        return storage.has(key) ? storage.get(key) : null;
      },
      setItem(key, value) {
        storage.set(key, String(value));
      },
      removeItem(key) {
        storage.delete(key);
      },
      clear() {
        storage.clear();
      },
    },
    addEventListener(type, handler) {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type).add(handler);
    },
    removeEventListener(type, handler) {
      listeners.get(type)?.delete(handler);
    },
    dispatchEvent(event) {
      for (const handler of listeners.get(event.type) ?? []) {
        handler(event);
      }
      return true;
    },
  };
}

globalThis.CustomEvent = class CustomEvent {
  constructor(type, init = {}) {
    this.type = type;
    this.detail = init.detail ?? null;
  }
};

globalThis.window = createMockWindow();

const {
  saveCurrentSession,
  getCurrentSession,
  getCurrentUser,
  getAccessToken,
  clearCurrentSession,
  onAuthChange,
} = await import("./authSession.js");

describe("authSession user persistence", () => {
  beforeEach(() => {
    globalThis.window.localStorage.clear();
  });

  it("saves and restores user profile and access token", () => {
    const events = [];
    const unsubscribe = onAuthChange((user) => events.push(user));

    saveCurrentSession({
      user: { id: "user-alice", email: "alice@example.com", username: "alice" },
      accessToken: "jwt-token-123",
      expiresIn: 3600,
    });

    const session = getCurrentSession();
    assert.equal(session?.user.id, "user-alice");
    assert.equal(getCurrentUser()?.username, "alice");
    assert.equal(getAccessToken(), "jwt-token-123");
    assert.equal(events.length, 1);
    assert.equal(events[0]?.id, "user-alice");

    unsubscribe();
  });

  it("clears expired sessions automatically", () => {
    globalThis.window.localStorage.setItem(
      "studyflow.currentUser",
      JSON.stringify({
        user: { id: "user-bob", email: "bob@example.com" },
        accessToken: "expired-token",
        expiresAt: Date.now() - 1000,
      }),
    );

    assert.equal(getCurrentSession(), null);
    assert.equal(getCurrentUser(), null);
    assert.equal(getAccessToken(), null);
    assert.equal(globalThis.window.localStorage.getItem("studyflow.currentUser"), null);
  });

  it("clears session on logout and notifies listeners", () => {
    saveCurrentSession({
      user: { id: "user-alice", email: "alice@example.com" },
      accessToken: "jwt-token-123",
      expiresIn: 3600,
    });

    const events = [];
    const unsubscribe = onAuthChange((user) => events.push(user));

    clearCurrentSession();

    assert.equal(getCurrentSession(), null);
    assert.equal(getCurrentUser(), null);
    assert.equal(events.length, 1);
    assert.equal(events[0], null);

    unsubscribe();
  });
});
