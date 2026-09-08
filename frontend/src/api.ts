const SESSION_KEY = "niteos_session";

export type Role = "staff" | "guest" | "telegram" | string | null;

export type PresenceItem = {
  value?: string;
  status?: string;
  hint?: string;
  opening?: string;
  reason?: string;
};

export type Company = {
  inn?: string;
  name?: string;
  stamp?: string;
  stamp_label?: string;
  stamp_hint?: string;
  score?: number;
  status?: string;
  okved?: string;
  address?: string;
  object_address?: string;
  management?: string;
  management_label?: string;
  management_post?: string;
  revenue_text?: string;
  profit_text?: string;
  expense_text?: string;
  photos?: string[];
  object?: {
    title?: string;
    address?: string;
    maps_yandex?: string;
    photo_notes?: string[];
    relation?: { status?: string; confidence?: number; found_via?: string };
  };
  presence?: Record<string, PresenceItem> & {
    recommend?: PresenceItem;
    photos?: PresenceItem & { value?: string[] | string };
    vk_group?: PresenceItem & { contacts?: Array<Record<string, string>> };
  };
  kp?: { title?: string; offer?: string; message_short?: string };
};

export type HuntPayload = {
  id?: number;
  status?: string;
  progress?: string;
  companies?: Company[];
  target_count?: number;
  queries?: string[];
  errors?: string[];
};

export type MetaPayload = {
  spheres: Array<{
    id: string;
    title: string;
    idea?: string;
    options: Array<{ id: string; label: string; query: string }>;
  }>;
  counts: number[];
  geo?: {
    districts?: Array<{ id: string; title: string }>;
    flat?: Array<{
      kind: string;
      title: string;
      label?: string;
      dadata_region?: string;
      fo?: string;
    }>;
  };
  role?: Role;
};

export type KpItem = {
  inn?: string;
  name?: string;
  object_title?: string;
  object_address?: string;
  address?: string;
  management?: string;
  phone?: string;
  photos?: string[];
  kp_at?: string;
};

function getSession(): string {
  try {
    return localStorage.getItem(SESSION_KEY) || "";
  } catch {
    return "";
  }
}

export function saveSession(value: string) {
  try {
    if (value) localStorage.setItem(SESSION_KEY, value);
    else localStorage.removeItem(SESSION_KEY);
  } catch {
    /* ignore */
  }
}

export function clearSession() {
  saveSession("");
}

function headers(extra?: HeadersInit): Headers {
  const h = new Headers(extra);
  if (!h.has("Content-Type")) h.set("Content-Type", "application/json");
  const tg = window.Telegram?.WebApp;
  if (tg?.initData) h.set("X-Telegram-Init-Data", tg.initData);
  const params = new URLSearchParams(location.search);
  const token = params.get("t") || "";
  if (token) h.set("X-Niteos-Token", token);
  const session = getSession();
  if (session) h.set("X-Niteos-Session", session);
  return h;
}

async function parseError(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const data = JSON.parse(text);
    return String(data.error || data.message || text || res.statusText);
  } catch {
    return text || res.statusText || `HTTP ${res.status}`;
  }
}

export async function api<T = unknown>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: headers(init?.headers),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const text = await res.text();
  if (!text) return {} as T;
  return JSON.parse(text) as T;
}

export async function authStatus() {
  return api<{ ok: boolean; role: Role; password_required?: boolean }>("/api/auth");
}

export async function login(password: string) {
  const data = await api<{ ok: boolean; role: Role; session?: string }>("/api/login", {
    method: "POST",
    body: JSON.stringify({ password }),
  });
  if (data.session) saveSession(data.session);
  return data;
}

export async function shareEnter(token: string) {
  const data = await api<{ ok: boolean; role: Role; session?: string; hint?: string }>(
    "/api/share/enter",
    { method: "POST", body: JSON.stringify({ token }) },
  );
  if (data.session) saveSession(data.session);
  return data;
}

export async function shareCreate(hours = 72) {
  return api<{ ok: boolean; url: string; hint?: string }>("/api/share/create", {
    method: "POST",
    body: JSON.stringify({ label: "клиент", max_uses: 1, hours }),
  });
}

export async function fetchMeta() {
  return api<MetaPayload>("/api/meta");
}

export async function startHunt(body: Record<string, unknown>) {
  return api<{ id: number; status: string }>("/api/hunt", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function pollHunt(id: number) {
  return api<HuntPayload>(`/api/hunt/${id}`);
}

export async function takeToKp(inn: string) {
  return api<{ ok: boolean }>("/api/company/kp", {
    method: "POST",
    body: JSON.stringify({ inn }),
  });
}

export async function listKp() {
  return api<{ items: KpItem[]; count: number }>("/api/kp");
}
