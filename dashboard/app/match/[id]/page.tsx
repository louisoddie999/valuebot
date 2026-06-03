"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, AlertTriangle } from "lucide-react";
import { getMatch, MatchDetail } from "@/lib/api";
import { Card, ConfChip, Odds, Spinner } from "@/components/ui";
import { AddButton } from "@/components/betslip";

export default function MatchPage({ params }: { params: { id: string } }) {
  const [d, setD] = useState<MatchDetail | null>(null);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");

  useEffect(() => {
    getMatch(params.id).then(setD).catch((e) => setErr(String(e)));
  }, [params.id]);

  const preds = useMemo(() => {
    if (!d?.predictions) return [];
    const s = q.toLowerCase();
    return d.predictions.filter((p) => !s || p.market.toLowerCase().includes(s) || p.selection.toLowerCase().includes(s));
  }, [d, q]);

  if (err) return <Card className="p-5 text-bad text-sm">API error: {err}</Card>;
  if (!d) return <Spinner label="Loading match…" />;

  return (
    <div>
      <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-text mb-5">
        <ArrowLeft size={15} /> Fixtures
      </Link>

      <Card className="p-5 mb-5">
        <div className="text-xs text-muted tnum mb-1">
          {d.country && <span className="text-primary/90">{d.country} · </span>}
          {d.league}
          {d.kickoff && ` · ${new Date(d.kickoff).toLocaleString([], { weekday: "short", year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}`}
        </div>
        <h1 className="font-mono text-2xl font-bold">{d.home} <span className="text-muted">v</span> {d.away}</h1>
        {d.enriched && (
          <div className="text-sm text-muted mt-2 tnum">
            {d.modeled} of {d.offered} markets modeled from stats
          </div>
        )}
        {(d.context?.home_missing || d.context?.away_missing) && (
          <div className="mt-3 flex flex-col gap-1 text-sm">
            {d.context?.home_missing && <div className="flex items-center gap-2 text-accent"><AlertTriangle size={14} /> {d.home}: {d.context.home_missing}</div>}
            {d.context?.away_missing && <div className="flex items-center gap-2 text-accent"><AlertTriangle size={14} /> {d.away}: {d.context.away_missing}</div>}
          </div>
        )}
        {!d.enriched && <div className="mt-2 text-accent text-sm">Not enriched yet — stats pending.</div>}
      </Card>

      {d.enriched && (
        <>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="filter markets…"
            className="w-full mb-4 rounded-lg border border-border bg-surface px-4 py-2.5 text-sm outline-none focus:border-primary tnum" />
          <div className="grid gap-2">
            {preds.map((p, i) => (
              <Card key={i} className="p-3.5 reveal" >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-xs text-muted">{p.market}{p.specifier ? ` · ${p.specifier}` : ""}</div>
                    <div className="font-medium">{p.selection}</div>
                    <div className="text-xs text-muted mt-1 leading-relaxed">{p.reason}</div>
                  </div>
                  <div className="flex flex-col items-end gap-1.5 shrink-0">
                    <div className="flex items-center gap-2.5"><ConfChip c={p.confidence} /> <Odds v={p.odds} /></div>
                    <AddButton sel={{
                      event_id: d.event_id, match: `${d.home} v ${d.away}`,
                      market: p.market, market_id: p.market_id, specifier: p.specifier,
                      outcome_id: p.outcome_id, selection: p.selection, odds: p.odds, confidence: p.confidence,
                      league: d.league, country: d.country, kickoff: d.kickoff,
                    }} />
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
