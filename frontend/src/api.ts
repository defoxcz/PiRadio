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
let token = sessionStorage.getItem("piradio-token") || "";
export function setToken(value: string) {
  token = value;
  sessionStorage.setItem("piradio-token", value);
}
export async function api<T>(
  path: string,
  method = "GET",
  data?: unknown,
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: data === undefined ? undefined : JSON.stringify(data),
    signal: AbortSignal.timeout(12000),
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      response.status === 401
        ? "Pro ovládání vložte token v Nastavení."
        : typeof body.detail === "string"
          ? body.detail
          : "Zkontrolujte vyplněné údaje a zkuste to znovu.",
    );
  }
  return response.json();
}
