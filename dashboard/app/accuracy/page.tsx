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
        Validated walk-forward on {d.validated_matches.toLocaleString()} matches — no look-ahead. Does an X% prediction land ~X%?
      </p>

      <Card className="p-5 mb-5">
        <h2 className="font-mono font-semibold mb-4">Calibration — predicted vs actual</h2>
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
        <p className="text-xs text-muted mt-4">Actual ≈ predicted across every band → predictions are trustworthy.</p>
      </Card>

      <Card className="p-5">
        <h2 className="font-mono font-semibold mb-4">By market — most-likely pick hit-rate</h2>
        <div className="grid sm:grid-cols-2 gap-2.5">
          {d.markets.map((m: any) => (
            <div key={m.market} className="flex items-center justify-between rounded-lg border border-border bg-surface2/50 px-4 py-2.5">
              <span className="text-sm">{m.market}</span>
              <span className="tnum text-sm"><span className="text-muted">{m.confidence}% →</span> <span className="font-semibold">{m.hit}%</span></span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
