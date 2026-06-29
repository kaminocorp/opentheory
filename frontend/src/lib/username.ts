// Frontend mirror of the backend handle rules (`app/core/usernames.py`) so a `PATCH /me`-bound
// rename can be validated *before* the round-trip — showing a legible message instead of the
// server's raw 422 body. The server validator remains the canonical enforcement (0.8.3); this is a
// UX shortcut + defense-in-depth. Keep the pattern + reserved set in sync with the backend.
export const USERNAME_PATTERN = /^[a-z0-9_]{3,30}$/;

const RESERVED_USERNAMES = new Set([
  "me",
  "admin",
  "administrator",
  "system",
  "accounts",
  "account",
  "api",
  "anonymous",
  "owner",
  "support",
  "root",
  "null",
  "undefined",
]);

// Returns a human-readable error if `value` (already trimmed + lowercased) is not an acceptable
// handle, else null. Mirrors `AccountUpdate`'s validator: shape first, then the reserved set.
export function usernameError(value: string): string | null {
  if (!USERNAME_PATTERN.test(value)) {
    return "Username must be 3–30 characters: lowercase letters, digits, or underscores.";
  }
  if (RESERVED_USERNAMES.has(value)) {
    return "That username is reserved.";
  }
  return null;
}
