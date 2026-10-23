import { rememberToken, restoreToken } from "./token-storage";

export interface Station {
  id: string;
  name: string;
  url: string;
  image: string;
  favorite: boolean;
}
export interface Status {
  state: string;
  station_id: string | null;
  volume: number;
  error: string | null;
  demo: boolean;
}
export interface Settings {
  default_volume: number;
  audio_device: string;
  auto_recover: boolean;
  autoplay: boolean;
  shutdown_available?: boolean;
}
let token = restoreToken();
export function hasToken() {
  return Boolean(token);
}
export function setToken(value: string) {
  token = value.trim();
  return rememberToken(token);
}
export async function api<T>(
  path: string,
  method = "GET",
  data?: unknown,
  candidateToken = token,
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers: {
      "Content-Type":
        data instanceof Blob
          ? data.type || "application/octet-stream"
          : "application/json",
      ...(candidateToken ? { Authorization: `Bearer ${candidateToken}` } : {}),
    },
    body:
      data instanceof Blob
        ? data
        : data === undefined
          ? undefined
          : JSON.stringify(data),
    signal: AbortSignal.timeout(12000),
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      response.status === 401
        ? candidateToken
          ? "Server tento token odmítl. V Nastavení zadejte token z Raspberry Pi."
          : "Pro ovládání vložte token v Nastavení."
        : typeof body.detail === "string"
          ? body.detail
          : "Zkontrolujte vyplněné údaje a zkuste to znovu.",
    );
  }
  return response.json();
}
