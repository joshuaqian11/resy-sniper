const API_KEY = import.meta.env.VITE_API_KEY ?? "";
const BASE = (import.meta.env.VITE_API_BASE ?? "") + "/api";

function headers(): HeadersInit {
  return { "Content-Type": "application/json", "x-api-key": API_KEY };
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    method,
    headers: headers(),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) throw new Error(`${method} ${path} → ${resp.status}`);
  if (resp.status === 204) return undefined as unknown as T;
  return resp.json();
}

export interface Target {
  id: number;
  venue_id: string;
  venue_name: string;
  date: string;
  party_size: number;
  opening_time: string;
  preferred_start: string | null;
  preferred_end: string | null;
  status: "pending" | "sniping" | "booked" | "failed";
  booked_at: string | null;
  reservation_details: string | null;
}

export interface TargetCreate {
  venue_id: string;
  venue_name: string;
  date: string;
  party_size: number;
  opening_time: string;
  preferred_start?: string;
  preferred_end?: string;
}

export interface AppSettings {
  resy_api_key: string;
  resy_email: string;
  resy_password: string;
  resy_cookies: string;
  twilio_account_sid: string;
  twilio_auth_token: string;
  twilio_from: string;
  phone_number: string;
}

export interface Reservation {
  venue: { name: string };
  date: string;
  time_slot: string;
  party_size: number;
  resy_token: string;
  [key: string]: unknown;
}

export const api = {
  targets: {
    list: () => request<Target[]>("GET", "/targets"),
    add: (t: TargetCreate) => request<Target>("POST", "/targets", t),
    delete: (id: number) => request<void>("DELETE", `/targets/${id}`),
  },
  settings: {
    get: () => request<AppSettings>("GET", "/settings"),
    update: (s: AppSettings) => request<AppSettings>("PUT", "/settings", s),
  },
  reservations: {
    list: () => request<Reservation[]>("GET", "/reservations"),
  },
};
