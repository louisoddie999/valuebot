export const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export type Pick = { market: string; selection: string; confidence: number; odds: number; market_id: string; specifier: string | null; outcome_id: string };
export type Fixture = {
  event_id: string; home: string; away: string; league: string; country: string;
  kickoff: string; enriched: boolean; top_pick: Pick | null;
};
export type Prediction = {
  market: string; specifier: string | null; selection: string;
  confidence: number; odds: number; reason: string;
  market_id: string; outcome_id: string;
};
export type MatchDetail = {
  event_id: string; home: string; away: string; league: string; country?: string; kickoff: string;
  enriched: boolean; modeled?: number; offered?: number;
  context?: { home_missing?: string; away_missing?: string; home_rest?: number; away_rest?: number };
  predictions: Prediction[]; note?: string;
};
export type SlipLeg = {
  match: string; market: string; selection: string; confidence: number; odds: number; reason: string;
  event_id: string; market_id: string; specifier: string | null; outcome_id: string;
  league?: string; country?: string; kickoff?: string;
};

export function fmtKick(iso?: string): string {
  if (!iso) return "";
  try { return new Date(iso).toLocaleString([], { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }); }
  catch { return ""; }
}
export type Slip = { combined_odds: number; hit_estimate: number; legs: SlipLeg[] } | null;
export type Slips = { scope: string; leg_pool: number; tiers: Record<string, Slip> };

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

export const getFixtures = (scope: string) =>
  get<{ scope: string; start: string; end: string; count: number; fixtures: Fixture[] }>(`/api/fixtures?scope=${encodeURIComponent(scope)}`);
export const getMatch = (id: string) => get<MatchDetail>(`/api/match/${encodeURIComponent(id)}`);
export const getSlips = (scope: string) => get<Slips>(`/api/slips?scope=${encodeURIComponent(scope)}`);
export const getAccuracy = () => get<any>(`/api/accuracy`);
export const getResults = () => get<any>(`/api/results`);

export async function createBooking(legs: SlipLeg[]): Promise<{ ok: boolean; shareCode: string; shareURL: string }> {
  const body = { legs: legs.map((l) => ({ event_id: l.event_id, market_id: String(l.market_id), specifier: l.specifier || "", outcome_id: String(l.outcome_id), odds: l.odds })) };
  const r = await fetch(`${API}/api/booking`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`booking ${r.status}`);
  return r.json();
}

export type BuildSlip = { combined_odds: number; hit_estimate: number; n_legs: number; legs: SlipLeg[] };
export type ChatResp = { reply: string; engine: string; scope: string; pool: number; slips: BuildSlip[]; params: any };

export async function chatBuild(message: string): Promise<ChatResp> {
  const r = await fetch(`${API}/api/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message }) });
  if (!r.ok) throw new Error(`chat ${r.status}`);
  return r.json();
}

export const SCOPES = ["today", "tomorrow", "week", "weekend"];
