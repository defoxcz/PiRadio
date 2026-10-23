const TOKEN_KEY = "piradio-token";

function read(storage: "localStorage" | "sessionStorage"): string {
  try {
    return globalThis[storage].getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

function write(
  storage: "localStorage" | "sessionStorage",
  value: string,
): boolean {
  try {
    if (value) globalThis[storage].setItem(TOKEN_KEY, value);
    else globalThis[storage].removeItem(TOKEN_KEY);
    return true;
  } catch {
    return false;
  }
}

export function restoreToken(): string {
  const saved = read("localStorage");
  if (saved) return saved;
  const legacy = read("sessionStorage");
  // Existing sessions migrate without asking for the token again.
  if (legacy && write("localStorage", legacy)) write("sessionStorage", "");
  return legacy;
}

export function rememberToken(value: string): boolean {
  if (!value) {
    const localCleared = write("localStorage", "");
    const sessionCleared = write("sessionStorage", "");
    return localCleared && sessionCleared;
  }
  const remembered = write("localStorage", value);
  write("sessionStorage", remembered ? "" : value);
  return remembered;
}
