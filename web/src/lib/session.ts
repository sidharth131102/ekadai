// A per-tab session id, persisted in sessionStorage (cleared on tab close). This is a
// reasonable client-side proxy for "session" without trying to replicate the spec's
// 30-minute-inactivity boundary here — that's explicitly a downstream Gold-layer
// computation (§83), not this layer's job. Generated once and reused for every request.

const SESSION_KEY = "ekadai_session_id";

function generateId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  // Fallback for environments without crypto.randomUUID (older browsers).
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function getSessionId(): string {
  try {
    let id = sessionStorage.getItem(SESSION_KEY);
    if (!id) {
      id = generateId();
      sessionStorage.setItem(SESSION_KEY, id);
    }
    return id;
  } catch {
    // Private-mode / storage disabled — fall back to a per-call id rather than crash.
    return generateId();
  }
}
