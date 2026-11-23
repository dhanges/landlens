/**
 * Typed API client: the only bridge between the web app and FastAPI (ADR-003). Shapes mirror the FastAPI
 * routers in api/landlens/app (spec 2.9). Caddy serves /api on the same origin, so the session cookie
 * (httpOnly, SameSite=Lax, Secure: accepted on http://localhost, OQ-25) rides along with credentials
 * "same-origin". NEXT_PUBLIC_API_BASE_URL can point elsewhere for local development.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export type LandType = "urban_plot" | "peri_urban" | "agricultural";
export type GwCategory = "safe" | "semi_critical" | "critical" | "over_exploited";
export type Source = "real" | "synthetic" | "osm" | string;

/** The shared error shape {"error": {"code", "message", "details"?}} (spec 2.9). */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details?: unknown,
    readonly retryAfter?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Init = { method?: string; body?: unknown; headers?: Record<string, string>; signal?: AbortSignal };

async function request<T>(path: string, init: Init = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api${path}`, {
      method: init.method ?? "GET",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        ...(init.body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...init.headers,
      },
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
      signal: init.signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "network_error", "Could not reach LandLens. Check your connection and try again.");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }
  if (!res.ok) {
    const err = (body as { error?: { code?: string; message?: string; details?: unknown } } | null)?.error;
    const ra = Number(res.headers.get("retry-after"));
    throw new ApiError(
      res.status,
      err?.code ?? `http_${res.status}`,
      err?.message ?? `The server answered ${res.status}.`,
      err?.details,
      Number.isFinite(ra) && ra > 0 ? ra : undefined,
    );
  }
  return body as T;
}

// ---- auth (spec 2.10) ----------------------------------------------------------------------------------
export interface User {
  user_id: number;
  email: string;
  credit_balance: number;
}
export const signup = (email: string, password: string) =>
  request<User>("/auth/signup", { method: "POST", body: { email, password } });
export const login = (email: string, password: string) =>
  request<User>("/auth/login", { method: "POST", body: { email, password } });
export const logout = () => request<void>("/auth/logout", { method: "POST" });
/** The signed-in user, or null. Uses /auth/session (always 200) so signed-out pages log no 401. */
export async function me(): Promise<User | null> {
  return (await request<{ user: User | null }>("/auth/session")).user;
}

// ---- health ---------------------------------------------------------------------------------------------
export interface HealthResponse {
  db: string;
  openai: string;
}
export const getHealth = () => request<HealthResponse>("/health");

// ---- search (FR-2) -------------------------------------------------------------------------------------
export interface VillageHit {
  village_id: number;
  name: string;
  mandal: string;
  similarity: number;
  lat: number;
  lon: number;
}
export interface ParcelHit {
  parcel_id: number;
  village_id: number;
  village: string;
  survey_no: string;
  sub_div: string | null;
  land_type: LandType;
  area_sqm: number;
  lat: number;
  lon: number;
}
export const search = (q: string, signal?: AbortSignal) =>
  request<{ villages: VillageHit[]; parcels: ParcelHit[] }>(`/search?q=${encodeURIComponent(q)}&limit=8`, {
    signal,
  });

// ---- parcels (FR-3) ------------------------------------------------------------------------------------
export interface ParcelSummary {
  parcel_id: number;
  village_id: number;
  village: string;
  mandal_id: number;
  mandal: string;
  survey_no: string;
  sub_div: string | null;
  land_type: LandType;
  area_sqm: number;
  zone_code: string | null;
  zone_name: string | null;
  village_median_sqm: number | null;
  price_sqm: number | null;
  price_vs_median_pct: number | null;
  cagr_5y: number | null;
  nearest_active_project_m: number | null;
  nearest_active_project: string | null;
  source: Source;
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon;
  lat: number;
  lon: number;
  unlocked: boolean;
}
export const parcelAt = (lat: number, lon: number) =>
  request<ParcelSummary>(`/parcels/at?lat=${lat.toFixed(6)}&lon=${lon.toFixed(6)}`);
export const parcelSummary = (id: number) => request<ParcelSummary>(`/parcels/${id}/summary`);

// ---- report (FR-6, FR-7) -------------------------------------------------------------------------------
export interface ProjectNearby {
  project_id: number;
  name: string;
  project_type: string;
  distance_m: number;
  expected_completion: string | null;
  source: Source;
  status: string | null;
  announced_on: string | null;
}
export interface TrendPoint {
  yr: number;
  median_price_sqm: number;
  n_sales: number;
  yoy: number | null;
  yoy_base_yr: number | null;
  guideline_sqm: number | null;
}
export interface Sale {
  txn_id: number;
  registered_on: string;
  consideration_inr: number;
  area_sqm: number;
  price_sqm: number;
  doc_no: string | null;
  source: Source;
}
export interface Comparable {
  parcel_id: number;
  village_id: number;
  village: string | null;
  survey_no: string | null;
  sub_div: string | null;
  registered_on: string;
  price_sqm: number;
  adjusted_price_sqm: number;
  distance_m: number;
  area_sqm: number;
  factors: Record<"area" | "frontage" | "project" | "time", number>;
}
export interface Valuation {
  method: string;
  as_of: string;
  confidence: "high" | "medium" | "low" | "none";
  n_comparables: number;
  search_radius_m: number;
  search_months: number;
  median_distance_m: number | null;
  locality_median_sqm: number | null;
  p25_sqm: number | null;
  p50_sqm: number | null;
  p75_sqm: number | null;
  p25_inr: number | null;
  p50_inr: number | null;
  p75_inr: number | null;
  drivers: { factor: "area" | "frontage" | "project" | "time"; median_effect_pct: number }[];
  coefficients: Record<string, number>;
  note?: string;
}
export type SectionName =
  | "location"
  | "zoning"
  | "environment"
  | "price_history"
  | "locality_trend"
  | "comparables"
  | "valuation"
  | "provenance";
export interface Report {
  parcel_id: number;
  land_type: LandType;
  section_order: SectionName[];
  location: {
    parcel_id: number;
    survey_no: string;
    sub_div: string | null;
    land_type: LandType;
    area_sqm: number;
    road_frontage_m: number;
    village_id: number;
    village: string;
    mandal_id: number;
    mandal: string;
    district: string;
    lat: number;
    lon: number;
    distances_m: { highway: number | null; water: number | null; active_project: number | null };
    nearest_active_project: { project_id: number; name: string } | null;
    projects_within_10km: ProjectNearby[];
  };
  zoning: {
    primary_zone: string | null;
    primary_zone_name: string | null;
    overlap_pct: number | null;
    permitted_uses: string | null;
    source_clause: { document_id: number; title: string; page: number } | { document_id: null; note: string } | null;
    zones: { zone_code: string; name: string; overlap_pct: number; source: Source }[];
  };
  environment: {
    groundwater: {
      mandal_id: number;
      latest_category: GwCategory | null;
      trend: { assessment_year: number; extraction_pct: number; category: GwCategory; source: Source }[];
    };
    soil?: {
      soil_score: number | null;
      nearest_samples: {
        sample_id: number;
        sampled_on: string;
        ph: number;
        organic_carbon_pct: number;
        texture: string;
        distance_m: number;
        source: Source;
      }[];
    };
  };
  price_history: Sale[];
  locality_trend: { village_id: number; land_type: LandType; series: TrendPoint[] };
  comparables: Comparable[];
  valuation: Valuation;
  provenance: Record<string, string | string[]> & { synthetic_fields: string[] };
}
export const parcelReport = (id: number) => request<Report>(`/parcels/${id}/report`);

// ---- credits (FR-10, spec 2.11) ------------------------------------------------------------------------
export interface UnlockResponse {
  unlocked: boolean;
  charged: number;
  credit_balance: number;
}
/** Idempotency-Key is required: the caller keeps one key per unlock attempt so a retry is never charged twice. */
export const unlockReport = (id: number, idempotencyKey: string) =>
  request<UnlockResponse>(`/reports/${id}/unlock`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
  });
export type Pack = "5" | "20" | "50";
export interface TopUpResponse {
  pack: Pack;
  credits_added: number;
  price_inr: number;
  mock: true;
  note: string;
  credit_balance: number;
}
export const topUp = (pack: Pack, idempotencyKey: string) =>
  request<TopUpResponse>("/credits/topup", {
    method: "POST",
    body: { pack },
    headers: { "Idempotency-Key": idempotencyKey },
  });
export interface LedgerEntry {
  entry_id: number;
  delta: number;
  reason: "signup_bonus" | "top_up" | "report_unlock" | "refund" | string;
  parcel_id: number | null;
  created_at: string;
}
export const ledger = (cursor?: string | null) =>
  request<{ items: LedgerEntry[]; next_cursor: string | null; credit_balance: number | null }>(
    `/credits/ledger?limit=25${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
  );

// ---- screener (FR-4) -----------------------------------------------------------------------------------
export type SortKey = "cagr_5y" | "price_sqm" | "area_sqm" | "nearest_active_project_m";
export interface ScreenerFilters {
  land_type?: LandType;
  zone_code?: string[];
  area_sqm_min?: number;
  area_sqm_max?: number;
  price_sqm_min?: number;
  price_sqm_max?: number;
  max_active_project_m?: number;
  max_highway_m?: number;
  min_cagr_5y?: number;
  max_price_vs_median_pct?: number;
  exclude_gw?: GwCategory[];
  min_soil_score?: number;
  mandal_id?: number[];
}
export interface ScreenerRow {
  parcel_id: number;
  village_id: number;
  village_name: string;
  mandal_id: number;
  land_type: LandType;
  zone_code: string | null;
  area_sqm: number;
  price_sqm: number | null;
  village_median_sqm: number | null;
  price_vs_median_pct: number | null;
  cagr_5y: number | null;
  nearest_active_project_m: number | null;
  nearest_highway_m: number | null;
  gw_category: GwCategory | null;
  soil_score: number | null;
  guideline_rate_sqm: number | null;
  survey_no: string | null;
  sub_div: string | null;
  lat: number | null;
  lon: number | null;
}
export interface ScreenerPage {
  items: ScreenerRow[];
  next_cursor: string | null;
  approx_total: number;
  sort: SortKey;
  order: "asc" | "desc";
}
export const screener = (
  body: { filters: ScreenerFilters; sort?: SortKey; order?: "asc" | "desc"; cursor?: string | null; limit?: number },
  signal?: AbortSignal,
) =>
  request<ScreenerPage>("/screener", {
    method: "POST",
    body: { ...body, cursor: body.cursor ?? undefined },
    signal,
  });
export interface ScreenerOptions {
  filters: string[];
  land_types: LandType[];
  gw_categories: GwCategory[];
  zones: { zone_code: string; name: string }[];
  mandals: { mandal_id: number; name: string }[];
  ranges: Record<string, number>;
  sorts: { sort: SortKey; default_order: "asc" | "desc" }[];
  max_limit: number;
}
export const screenerOptions = () => request<ScreenerOptions>("/screener/options");

// ---- trends (FR-5) -------------------------------------------------------------------------------------
export interface VillageTrend {
  village_id: number;
  name: string;
  mandal_id: number;
  land_type: LandType | null;
  series: TrendPoint[];
}
export interface MandalTrend {
  mandal_id: number;
  name: string;
  land_type: LandType | null;
  series: TrendPoint[];
}
export const villageTrend = (id: number, landType?: LandType) =>
  request<VillageTrend>(`/trends/villages/${id}${landType ? `?land_type=${landType}` : ""}`);
export const mandalTrend = (id: number, landType?: LandType) =>
  request<MandalTrend>(`/trends/mandals/${id}${landType ? `?land_type=${landType}` : ""}`);

/** A UUID for Idempotency-Key. crypto.randomUUID needs a secure context, which http://localhost is. */
export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

// ---- document Q&A (FR-8, spec 2.13) --------------------------------------------------------------------
export interface ChatCitation {
  n: number;
  document_id: number;
  title: string;
  page_start: number;
  page_end: number;
  snippet: string;
}
export interface ChatResponse {
  found: boolean;
  degraded: boolean;
  answer: string | null;
  citations: ChatCitation[];
  note: string | null;
}
export const chat = (question: string, parcelId?: number) =>
  request<ChatResponse>("/chat", { method: "POST", body: { question, ...(parcelId ? { parcel_id: parcelId } : {}) } });
/** The PDF opened at a page by the browser's viewer. */
export const documentUrl = (id: number, page: number) => `${API_BASE_URL}/api/documents/${id}/file#page=${page}`;
