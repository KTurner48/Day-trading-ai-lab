// Tiny API client with bearer-token auth, talking to the FastAPI backend.
const TOKEN_KEY = "aureus_token";

export function getToken(): string | null {
  return typeof localStorage !== "undefined" ? localStorage.getItem(TOKEN_KEY) : null;
}
export function setToken(t: string): void {
  localStorage.setItem(TOKEN_KEY, t);
}
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, { ...init, headers });
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      message = body?.error?.message ?? message;
    } catch {
      /* ignore */
    }
    throw new Error(message);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export interface CommandCenter {
  settings: { trading_mode: string; kill_switch_active: boolean; max_open_positions: number };
  account: { balance: string; equity: string; currency: string } | null;
  open_positions: { id: string; side: string; quantity: string; avg_entry_price: string }[];
  latest_signal: {
    id: string; action: string; status: string; score: number;
    reasoning: string | null; veto_reason: string | null;
  } | null;
  pending_count: number;
  brokers: { name: string; broker_type: string; status: string; order_capable: boolean }[];
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string }>("/api/v1/auth/login", {
      method: "POST", body: JSON.stringify({ email, password }),
    }),
  me: () => request<{ email: string; role: string }>("/api/v1/auth/me"),
  commandCenter: () => request<CommandCenter>("/api/v1/dashboard/command-center"),
  quote: (symbol: string) =>
    request<{ symbol: string; price: string; time: string }>(`/api/v1/market/quote/${symbol}`),
  setMode: (trading_mode: string) =>
    request<{ trading_mode: string }>("/api/v1/settings/trading-mode", {
      method: "PUT", body: JSON.stringify({ trading_mode }),
    }),
  setKillSwitch: (active: boolean, reason?: string) =>
    request<{ kill_switch_active: boolean }>("/api/v1/settings/kill-switch", {
      method: "PUT", body: JSON.stringify({ active, reason }),
    }),
  generate: (symbol = "XAU_USD") =>
    request<{ created: number; executed: number }>(
      `/api/v1/signals/generate?symbol=${symbol}`, { method: "POST" }),
};
