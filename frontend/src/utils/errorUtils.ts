/**
 * Utilities for normalizing and formatting API errors across the OpusLex frontend.
 * Prevents non-string error payloads (e.g. FastAPI 422 detail arrays) from causing
 * rendering crashes or white-screens.
 */

export function normalizeApiError(detail: unknown, defaultMessage = "An unexpected error occurred"): string {
  if (!detail) return defaultMessage;

  if (typeof detail === "string") {
    return detail.trim() || defaultMessage;
  }

  // If passed the entire response object e.g. { detail: [...] } or { detail: "..." }
  if (detail && typeof detail === "object" && "detail" in detail) {
    return normalizeApiError((detail as Record<string, unknown>).detail, defaultMessage);
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const obj = item as Record<string, unknown>;
          const loc = Array.isArray(obj.loc) ? obj.loc.filter((x: unknown) => x !== "body").map(String).join(".") : "";
          const msg = obj.msg || obj.message;
          if (loc && msg) return `${loc}: ${String(msg)}`;
          if (msg) return String(msg);
        }
        return null;
      })
      .filter(Boolean);

    if (messages.length > 0) {
      return messages.join("; ");
    }
  }

  if (typeof detail === "object") {
    const obj = detail as Record<string, unknown>;
    if ("message" in obj && typeof obj.message === "string") {
      return obj.message;
    }
    if ("msg" in obj && typeof obj.msg === "string") {
      return obj.msg;
    }
    if ("error" in obj && typeof obj.error === "string") {
      return obj.error;
    }
  }

  try {
    return JSON.stringify(detail);
  } catch {
    return defaultMessage;
  }
}

export function safeString(val: unknown, fallback = ""): string {
  if (typeof val === "string") return val;
  if (val === null || val === undefined) return fallback;
  if (typeof val === "number" || typeof val === "boolean") return String(val);
  try {
    return JSON.stringify(val);
  } catch {
    return fallback;
  }
}
