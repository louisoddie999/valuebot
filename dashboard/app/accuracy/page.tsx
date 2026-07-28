"use client";
import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { getAccuracy } from "@/lib/api";
import { Card, Spinner } from "@/components/ui";

export default function AccuracyPage() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => { getAccuracy().then(setD).catch((e) => setErr(String(e))); }, []);

  if (err) return <Card className="p-5 text-bad text-sm">API error: {err}</Card>;
  if (!d) return <Spinner label="Loading validation…" />;

  const bar = (act: number) => (
    <div className="h-2 w-full rounded-full bg-surface2 overflow-hidden">
      <div className="h-full rounded-full bg-primary" style={{ width: `${act}%` }} />
    </div>
  );

  return (
    <div>
      <div className="flex items-center gap-2 mb-1">
        <ShieldCheck size={20} className="text-good" />
        <h1 className="font-mono text-2xl font-bold tracking-tight">Accuracy & Trust</h1>
      </div>
      <p className="text-muted text-sm mb-6 tnum">
        {d.validated_matches > 0
          ? `Validated walk-forward on ${d.validated_matches.toLocaleString()} matches — no look-ahead.`
          : "Live calibration uses locally settled records. No precomputed public benchmark is bundled."}
      </p>

      {d.live_calibration && (() => {
        const lc = d.live_calibration;
        const pct = Math.min(100, Math.round((lc.n_total / lc.min_required) * 100));
        return (
          <Card className="p-5 mb-5 border-accent/30">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-mono font-semibold">Self-learning calibration {lc.active
                ? <span className="text-good text-xs ml-1">● LIVE</span>
                : <span className="text-accent text-xs ml-1">● learning</span>}</h2>
              <span className="text-xs text-muted tnum">{lc.n_total} / {lc.min_required} settled picks</span>
            </div>
            {!lc.active ? (
              <>
                <div className="h-2 w-full rounded-full bg-surface2 overflow-hidden">
                  <div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
                </div>
                <p className="text-xs text-muted mt-3">
                  ValueBot is recording its own results. Once {lc.min_required} picks settle, it auto-corrects
                  future confidence toward its real hit-rate. {lc.min_required - lc.n_total} more to go.
                </p>
              </>
            ) : (
              <>
                <div className="grid gap-3">
                  {lc.buckets.filter((b: any) => b.n > 0).map((b: any) => (
                    <div key={b.range} className="grid grid-cols-[80px_1fr_auto] items-center gap-3">
                      <span className="tnum text-sm text-muted">{b.range}</span>
                      <div className="h-2 w-full rounded-full bg-surface2 overflow-hidden">
                        <div className="h-full rounded-full bg-good" style={{ width: `${b.actual ?? 0}%` }} />
                      </div>
                      <span className="tnum text-sm">
                        <span className="text-muted">{b.predicted}% →</span> <span className="font-semibold text-good">{b.actual}%</span>
                        <span className="text-muted/60 ml-2">n={b.n}</span>
                        {b.offset !== 0 && <span className={`ml-2 ${b.offset < 0 ? "text-bad" : "text-good"}`}>{b.offset > 0 ? "+" : ""}{(b.offset * 100).toFixed(0)}pp</span>}
                      </span>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-muted mt-4">Live correction from {lc.n_total} of your own settled picks — confidence now reflects real results.</p>
              </>
            )}
          </Card>
        );
      })()}

      {d.calibration.length > 0 ? (
        <Card className="p-5 mb-5">
          <h2 className="font-mono font-semibold mb-4">Baseline calibration — predicted vs actual</h2>
          <div className="grid gap-3">
            {d.calibration.map((c: any) => (
              <div key={c.bucket} className="grid grid-cols-[80px_1fr_auto] items-center gap-3">
                <span className="tnum text-sm text-muted">{c.bucket}</span>
                {bar(c.actual)}
                <span className="tnum text-sm">
                  <span className="text-muted">{c.predicted}% →</span> <span className="font-semibold text-good">{c.actual}%</span>
                  <span className="text-muted/60 ml-2">n={c.n.toLocaleString()}</span>
                </span>
              </div>
            ))}
          </div>
        </Card>
      ) : (
        <Card className="p-5 mb-5">
          <h2 className="font-mono font-semibold mb-2">Reproducible benchmark required</h2>
          <p className="text-sm text-muted">
            Run the walk-forward validation utilities on a documented, time-ordered dataset before presenting benchmark results.
          </p>
        </Card>
      )}

      {d.markets.length > 0 && (
        <Card className="p-5">
          <h2 className="font-mono font-semibold mb-4">By market — observed hit rate</h2>
          <div className="grid sm:grid-cols-2 gap-2.5">
            {d.markets.map((m: any) => (
              <div key={m.market} className="flex items-center justify-between rounded-lg border border-border bg-surface2/50 px-4 py-2.5">
                <span className="text-sm">{m.market}</span>
                <span className="tnum text-sm"><span className="text-muted">{m.confidence}% →</span> <span className="font-semibold">{m.hit}%</span></span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
