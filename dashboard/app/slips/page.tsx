"use client";
import { useEffect, useState } from "react";
import { Layers } from "lucide-react";
import { getSlips, createBooking, fmtKick, Slips, Slip, SCOPES, SPORTS } from "@/lib/api";
import { Card, ConfChip, Odds, Spinner, ScopeTabs } from "@/components/ui";
import { Ticket, ExternalLink, Copy, Check, Share2 } from "lucide-react";
import { BuildChat } from "@/components/buildchat";
import { AddButton, useBetslip } from "@/components/betslip";

const TIERS = ["SAFE", "MID", "LONGSHOT"];
const TIER_DESC: Record<string, string> = {
  SAFE: "3–5 legs · high confidence", MID: "6–12 legs · balanced",
  LONGSHOT: "stacked · auto-split into bookable slips",
};

export default function SlipsPage() {
  const [scope, setScope] = useState("today");
  const [tier, setTier] = useState("SAFE");
  const [sport, setSport] = useState("football");
  const [sub, setSub] = useState(0);
  const [data, setData] = useState<Slips | null>(null);
  const [err, setErr] = useState("");
  const [booking, setBooking] = useState<{ code: string; url: string } | null>(null);
  const [bookingBusy, setBookingBusy] = useState(false);
  const [bookErr, setBookErr] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setData(null); setErr("");
    getSlips(scope, sport).then(setData).catch((e) => setErr(String(e)));
  }, [scope, sport]);

  useEffect(() => { setSub(0); }, [tier, scope]);
  useEffect(() => { setBooking(null); setBookErr(""); setCopied(false); }, [scope, tier, sub]);

  const subSlips: Slip[] = data?.tiers?.[tier] ?? [];
  const slip: Slip | null = subSlips[sub] ?? null;
  const { add } = useBetslip();
  const toSel = (l: any) => ({ event_id: l.event_id, match: l.match, market: l.market,
    market_id: l.market_id, specifier: l.specifier, outcome_id: l.outcome_id,
    selection: l.selection, odds: l.odds, confidence: l.confidence,
    league: l.league, country: l.country, kickoff: l.kickoff });
  const label = subSlips.length > 1 ? `${tier} ${sub + 1}` : tier;

  async function copyCode() {
    if (!booking) return;
    try { await navigator.clipboard.writeText(booking.code); setCopied(true); setTimeout(() => setCopied(false), 1800); } catch {}
  }
  const shareText = booking && slip
    ? `ValueBot ${label} slip — ${slip.legs.length} legs\nSportyBet code: ${booking.code}\n${booking.url}`
    : "";

  async function book() {
    if (!slip) return;
    setBookingBusy(true); setBookErr(""); setBooking(null);
    try {
      const r = await createBooking(slip.legs);
      setBooking({ code: r.shareCode, url: r.shareURL });
    } catch {
      setBookErr("Could not generate code — try again.");
    } finally {
      setBookingBusy(false);
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Accumulator Builder</h1>
          <p className="text-muted text-sm mt-1 tnum">{data ? `${data.leg_pool} qualifying predictions` : "…"}</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="inline-flex rounded-lg border border-border bg-surface p-1">
          {SPORTS.map((sp) => (
            <button key={sp} onClick={() => setSport(sp)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium capitalize transition-colors ${sport === sp ? "bg-primaryDeep text-white" : "text-muted hover:text-text"}`}>
              {sp === "football" ? "⚽" : "🏀"}
            </button>
          ))}
        </div>
        <ScopeTabs value={scope} onChange={setScope} scopes={SCOPES} />
          <input type="date" value={/^\d{4}-\d{2}-\d{2}$/.test(scope) ? scope : ""}
            onChange={(e) => e.target.value && setScope(e.target.value)}
            aria-label="Pick a date"
            className="rounded-lg border border-border bg-surface px-3 py-2 text-sm tnum text-text outline-none focus:border-primary [color-scheme:dark]" />
        </div>
      </div>

      <BuildChat />

      <div className="flex gap-2 mb-3">
        {TIERS.map((t) => {
          const n = data?.tiers?.[t]?.length ?? 0;
          return (
            <button key={t} onClick={() => setTier(t)}
              className={`flex-1 rounded-lg border p-3 text-left transition-colors ${tier === t ? "border-primary bg-primary/10" : "border-border bg-surface hover:border-primary/40"}`}>
              <div className="font-mono font-semibold flex items-center gap-2"><Layers size={15} /> {t}{n > 1 && <span className="text-xs text-accent tnum">×{n}</span>}</div>
              <div className="text-xs text-muted mt-0.5">{TIER_DESC[t]}</div>
            </button>
          );
        })}
      </div>

      {subSlips.length > 1 && (
        <div className="flex flex-wrap gap-1.5 mb-4">
          {subSlips.map((s, i) => (
            <button key={i} onClick={() => setSub(i)}
              className={`rounded-md border px-3 py-1.5 text-xs tnum transition-colors ${sub === i ? "border-accent bg-accent/10 text-accent" : "border-border text-muted hover:text-text"}`}>
              {tier} {i + 1} · {s.legs.length} legs · {s.combined_odds.toFixed(0)}
            </button>
          ))}
        </div>
      )}

      {err && <Card className="p-5 text-bad text-sm">API error: {err}</Card>}
      {!data && !err && <Spinner label="Building slips…" />}

      {data && !slip && <Card className="p-6 text-muted text-sm">No {tier} slip for this scope — not enough qualifying legs. Try a wider scope.</Card>}

      {slip && (
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between gap-4 border-b border-border bg-surface2 px-5 py-4">
            <div>
              <div className="text-xs text-muted">{label} · {slip.legs.length} legs</div>
              <div className="font-mono text-3xl font-bold text-primary tnum">{slip.combined_odds.toFixed(2)}</div>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-right">
                <div className="text-xs text-muted">est. hit chance</div>
                <div className="font-mono text-xl tnum">{slip.hit_estimate.toFixed(2)}%</div>
              </div>
              <button onClick={() => slip.legs.forEach((l) => add(toSel(l)))}
                className="flex items-center gap-2 rounded-lg border border-primary/50 px-3 py-2.5 text-sm font-semibold text-primary hover:bg-primary/10 transition">
                + Add all {slip.legs.length}
              </button>
              <button onClick={book} disabled={bookingBusy}
                className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-black hover:brightness-110 disabled:opacity-50 transition">
                <Ticket size={16} /> {bookingBusy ? "Generating…" : "Booking code"}
              </button>
            </div>
          </div>

          {(booking || bookErr) && (
            <div className="border-b border-border bg-accent/10 px-5 py-3">
              {bookErr && <span className="text-bad text-sm">{bookErr}</span>}
              {booking && (
                <div className="flex flex-wrap items-center gap-4">
                  <span className="text-sm text-muted">SportyBet code:</span>
                  <span className="font-mono text-2xl font-bold text-accent tracking-widest">{booking.code}</span>
                  <button onClick={copyCode} className="flex items-center gap-1.5 rounded-md border border-border bg-surface px-2.5 py-1 text-sm text-text hover:border-accent/50 transition">
                    {copied ? <><Check size={14} className="text-good" /> copied</> : <><Copy size={14} /> copy</>}
                  </button>
                  <a href={`https://wa.me/?text=${encodeURIComponent(shareText)}`} target="_blank" rel="noreferrer"
                    className="flex items-center gap-1.5 rounded-md border border-border bg-surface px-2.5 py-1 text-sm text-text hover:border-good/50 transition">
                    <Share2 size={14} /> share
                  </a>
                  <a href={booking.url} target="_blank" rel="noreferrer"
                    className="flex items-center gap-1.5 text-sm text-primary hover:underline">
                    Open in SportyBet <ExternalLink size={14} />
                  </a>
                  <span className="text-xs text-muted">— load · review · stake yourself</span>
                </div>
              )}
            </div>
          )}
          <div className="divide-y divide-border">
            {slip.legs.map((l, i) => (
              <div key={i} className="px-5 py-3 flex items-start justify-between gap-3 hover:bg-surface2/50">
                <div className="min-w-0">
                  <div className="text-[11px] text-muted/80 tnum">
                    {l.country && <span className="text-primary/80">{l.country}</span>}
                    {l.league && <span> · {l.league}</span>}
                    {l.kickoff && <span> · {fmtKick(l.kickoff)}</span>}
                  </div>
                  <div className="text-xs text-muted tnum">{i + 1}. {l.match}</div>
                  <div className="text-sm font-medium">{l.market} — {l.selection}</div>
                  <div className="text-xs text-muted mt-0.5">{l.reason}</div>
                </div>
                <div className="flex flex-col items-end gap-1.5 shrink-0">
                  <div className="flex items-center gap-2.5"><ConfChip c={l.confidence} /> <Odds v={l.odds} /></div>
                  <AddButton sel={toSel(l)} />
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}