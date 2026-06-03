"use client";
import { useEffect, useState } from "react";
import { History, TrendingUp, Clock } from "lucide-react";
import { getResults } from "@/lib/api";
import { Card, Spinner } from "@/components/ui";

export default function ResultsPage() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => { getResults().then(setD).catch((e) => setErr(String(e))); }, []);

  if (err) return <Card className="p-5 text-bad text-sm">API error: {err}</Card>;
  if (!d) return <Spinner label="Settling results…" />;

  const roiPos = d.roi >= 0;
  return (
    <div>
      <div className="flex items-center gap-2 mb-1">
        <History size={20} className="text-primary" />
        <h1 className="font-mono text-2xl font-bold tracking-tight">Results</h1>
      </div>
      <p className="text-muted text-sm mb-6 tnum">
        Booked picks, settled against real scores. {d.pending} pending · {d.settled} settled.
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        {[
          { k: "Record", v: `${d.wins}-${d.losses}`, sub: "W–L" },
          { k: "Hit rate", v: `${d.hit_rate}%`, sub: `${d.settled} settled` },
          { k: "ROI", v: `${d.roi > 0 ? "+" : ""}${d.roi}%`, sub: "flat 1u", color: roiPos ? "text-good" : "text-bad" },
          { k: "P&L", v: `${d.pnl_units > 0 ? "+" : ""}${d.pnl_units}u`, sub: "units", color: d.pnl_units >= 0 ? "text-good" : "text-bad" },
        ].map((s) => (
          <Card key={s.k} className="p-4">
            <div className="text-xs text-muted">{s.k}</div>
            <div className={`font-mono text-2xl font-bold tnum ${s.color || "text-text"}`}>{s.v}</div>
            <div className="text-[11px] text-muted/70 tnum">{s.sub}</div>
          </Card>
        ))}
      </div>

      {d.calibration?.length > 0 && (
        <Card className="p-5 mb-6">
          <h2 className="font-mono font-semibold mb-4 flex items-center gap-2"><TrendingUp size={16} className="text-good" /> Live calibration (booked picks)</h2>
          <div className="grid gap-3">
            {d.calibration.map((c: any) => (
              <div key={c.bucket} className="grid grid-cols-[90px_1fr_auto] items-center gap-3">
                <span className="tnum text-sm text-muted">{c.bucket}</span>
                <div className="h-2 rounded-full bg-surface2 overflow-hidden"><div className="h-full bg-primary" style={{ width: `${c.actual}%` }} /></div>
                <span className="tnum text-sm"><span className="text-muted">{c.predicted}% →</span> <span className="font-semibold text-good">{c.actual}%</span> <span className="text-muted/60">n={c.n}</span></span>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card className="overflow-hidden">
        <div className="px-5 py-3 border-b border-border font-mono font-semibold text-sm">Recent settled</div>
        {d.recent?.length === 0 ? (
          <div className="px-5 py-10 text-center text-muted text-sm flex flex-col items-center gap-2">
            <Clock size={20} /> No settled picks yet — {d.pending} pending. Book slips; they settle after kickoff.
          </div>
        ) : (
          <div className="divide-y divide-border">
            {d.recent.map((r: any, i: number) => (
              <div key={i} className="px-5 py-3 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-xs text-muted truncate">{r.league} · {r.match}</div>
                  <div className="text-sm">{r.market_name} — {r.outcome_desc}</div>
                </div>
                <div className="flex items-center gap-3 shrink-0 tnum">
                  <span className="text-muted text-sm">{r.odds?.toFixed(2)}</span>
                  <span className={`rounded-md px-2 py-0.5 text-xs font-semibold ${r.result ? "bg-good/15 text-good" : "bg-bad/15 text-bad"}`}>
                    {r.result ? "WON" : "LOST"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
