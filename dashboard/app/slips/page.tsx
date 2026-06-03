"use client";
import { useEffect, useState } from "react";
import { Layers } from "lucide-react";
import { getSlips, createBooking, fmtKick, Slips, Slip, SCOPES } from "@/lib/api";
import { Card, ConfChip, Odds, Spinner, ScopeTabs } from "@/components/ui";
import { Ticket, ExternalLink } from "lucide-react";
import { BuildChat } from "@/components/buildchat";

const TIERS = ["SAFE", "MID", "LONGSHOT"];
const TIER_DESC: Record<string, string> = {
  SAFE: "3–5 legs · high confidence", MID: "6–12 legs · balanced", LONGSHOT: "15+ legs · stacked",
};

export default function SlipsPage() {
  const [scope, setScope] = useState("today");
  const [tier, setTier] = useState("SAFE");
  const [data, setData] = useState<Slips | null>(null);
  const [err, setErr] = useState("");
  const [booking, setBooking] = useState<{ code: string; url: string } | null>(null);
  const [bookingBusy, setBookingBusy] = useState(false);
  const [bookErr, setBookErr] = useState("");

  useEffect(() => {
    setData(null); setErr("");
    getSlips(scope).then(setData).catch((e) => setErr(String(e)));
  }, [scope]);

  useEffect(() => { setBooking(null); setBookErr(""); }, [scope, tier]);

  const slip: Slip = data?.tiers?.[tier] ?? null;

  async function book() {
    if (!slip) return;
    setBookingBusy(true); setBookErr(""); setBooking(null);
    try {
      const r = await createBooking(slip.legs);
      setBooking({ code: r.shareCode, url: r.shareURL });
    } catch (e) {
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
        <ScopeTabs value={scope} onChange={setScope} scopes={SCOPES} />
      </div>

      <BuildChat />

      <div className="flex gap-2 mb-5">
        {TIERS.map((t) => (
          <button key={t} onClick={() => setTier(t)}
            className={`flex-1 rounded-lg border p-3 text-left transition-colors ${tier === t ? "border-primary bg-primary/10" : "border-border bg-surface hover:border-primary/40"}`}>
            <div className="font-mono font-semibold flex items-center gap-2"><Layers size={15} /> {t}</div>
            <div className="text-xs text-muted mt-0.5">{TIER_DESC[t]}</div>
          </button>
        ))}
      </div>

      {err && <Card className="p-5 text-bad text-sm">API error: {err}</Card>}
      {!data && !err && <Spinner label="Building slips…" />}

      {data && !slip && <Card className="p-6 text-muted text-sm">No {tier} slip for this scope — not enough qualifying legs. Try a wider scope.</Card>}

      {slip && (
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between gap-4 border-b border-border bg-surface2 px-5 py-4">
            <div>
              <div className="text-xs text-muted">{tier} · {slip.legs.length} legs</div>
              <div className="font-mono text-3xl font-bold text-primary tnum">{slip.combined_odds.toFixed(2)}</div>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-right">
                <div className="text-xs text-muted">est. hit chance</div>
                <div className="font-mono text-xl tnum">{slip.hit_estimate.toFixed(2)}%</div>
              </div>
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
                <div className="flex items-center gap-2.5 shrink-0"><ConfChip c={l.confidence} /> <Odds v={l.odds} /></div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
