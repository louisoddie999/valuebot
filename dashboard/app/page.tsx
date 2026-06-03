"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ChevronRight, Filter } from "lucide-react";
import { getFixtures, Fixture, SCOPES } from "@/lib/api";
import { Card, ConfChip, Odds, ScopeTabs, LoadingState, ConfidenceLegend, Freshness } from "@/components/ui";
import { AddButton } from "@/components/betslip";

export default function FixturesPage() {
  const [scope, setScope] = useState("today");
  const [data, setData] = useState<Fixture[] | null>(null);
  const [label, setLabel] = useState("");
  const [range, setRange] = useState<{ start: string; end: string }>({ start: "", end: "" });
  const [err, setErr] = useState("");
  const [league, setLeague] = useState("ALL");
  const [updated, setUpdated] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    setData(null); setErr("");
    getFixtures(scope).then((d) => { setData(d.fixtures); setLabel(d.scope); setRange({ start: d.start, end: d.end }); setUpdated(d.updated ?? null); })
      .catch((e) => setErr(String(e)));
  }, [scope]);

  const dateLine = range.start
    ? (range.start === range.end
        ? new Date(range.start + "T00:00").toLocaleDateString([], { weekday: "short", day: "numeric", month: "short", year: "numeric" })
        : `${new Date(range.start + "T00:00").toLocaleDateString([], { day: "numeric", month: "short" })} – ${new Date(range.end + "T00:00").toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" })}`)
    : "";

  const [q, setQ] = useState("");
  const [minConf, setMinConf] = useState(0);

  const leagues = useMemo(
    () => ["ALL", ...Array.from(new Set((data || []).map((f) => f.league).filter(Boolean)))],
    [data]
  );
  const base = (data || []).filter((f) => {
    if (league !== "ALL" && f.league !== league) return false;
    if (minConf && !(f.top_pick && f.top_pick.confidence >= minConf)) return false;
    if (q) {
      const s = q.toLowerCase();
      if (!(`${f.home} ${f.away} ${f.league} ${f.country}`.toLowerCase().includes(s))) return false;
    }
    return true;
  });
  // hide no-stats (unenriched / no pick) by default; sort best-confidence first
  const hasPick = (f: Fixture) => f.enriched !== false && !!f.top_pick;
  const hiddenCount = base.filter((f) => !hasPick(f)).length;
  const rows = (showAll ? base : base.filter(hasPick))
    .slice()
    .sort((a, b) => (b.top_pick?.confidence ?? -1) - (a.top_pick?.confidence ?? -1));

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Fixtures</h1>
          <p className="text-muted text-sm mt-1 tnum">
            <span className="text-text">{dateLine || "…"}</span> · {label} · <span className="text-text">{base.length - hiddenCount}</span> picks of {base.length} fixtures
          </p>
          <div className="mt-2 flex items-center gap-4 flex-wrap">
            <ConfidenceLegend />
            <Freshness iso={updated} />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ScopeTabs value={scope} onChange={setScope} scopes={SCOPES} />
          <input type="date" value={scope.match(/^\d{4}-\d{2}-\d{2}$/) ? scope : ""}
            onChange={(e) => e.target.value && setScope(e.target.value)}
            aria-label="Pick a date"
            className="rounded-lg border border-border bg-surface px-3 py-2 text-sm tnum text-text outline-none focus:border-primary [color-scheme:dark]" />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-4">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="search team / league…"
          className="rounded-lg border border-border bg-surface px-3 py-1.5 text-sm tnum outline-none focus:border-primary w-56" />
        <span className="text-xs text-muted ml-1">min conf:</span>
        {[0, 0.7, 0.8, 0.9].map((c) => (
          <button key={c} onClick={() => setMinConf(c)}
            className={`rounded-full border px-2.5 py-1 text-xs tnum transition-colors ${minConf === c ? "border-good text-good bg-good/10" : "border-border text-muted hover:text-text"}`}>
            {c === 0 ? "any" : `${c * 100}%+`}
          </button>
        ))}
      </div>
      {leagues.length > 2 && (
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          <Filter size={14} className="text-muted" />
          {leagues.map((l) => (
            <button key={l} onClick={() => setLeague(l)}
              className={`rounded-full border px-3 py-1 text-xs transition-colors ${league === l ? "border-primary text-primary bg-primary/10" : "border-border text-muted hover:text-text"}`}>
              {l}
            </button>
          ))}
        </div>
      )}

      {err && <Card className="p-5 text-bad text-sm">API error: {err}. Is the backend running on :8000?</Card>}
      {!data && !err && <LoadingState rows={8} />}

      <div className="grid gap-2.5">
        {rows.map((f, i) => (
          <Link key={f.event_id} href={`/match/${f.event_id}`} className="reveal" style={{ animationDelay: `${Math.min(i, 12) * 28}ms` }}>
            <Card className="p-4 hover:border-primary/50 transition-colors cursor-pointer group">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 text-xs text-muted mb-1 tnum flex-wrap">
                    {f.country && <span className="text-primary/90">{f.country}</span>}
                    <span className="opacity-50">·</span>
                    <span>{f.league || "—"}</span>
                    {f.kickoff && <span className="opacity-60">· {new Date(f.kickoff).toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span>}
                    {!f.enriched && <span className="text-accent/80">· no stats yet</span>}
                  </div>
                  <div className="font-medium truncate">{f.home} <span className="text-muted">v</span> {f.away}</div>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  {f.top_pick ? (
                    <div className="text-right">
                      <div className="text-xs text-muted">{f.top_pick.market}</div>
                      <div className="text-sm font-medium flex items-center gap-2 justify-end">
                        {f.top_pick.selection} <ConfChip c={f.top_pick.confidence} /> <Odds v={f.top_pick.odds} />
                      </div>
                      <div className="mt-1.5 flex justify-end">
                        <AddButton sel={{
                          event_id: f.event_id, match: `${f.home} v ${f.away}`,
                          market: f.top_pick.market, market_id: f.top_pick.market_id,
                          specifier: f.top_pick.specifier, outcome_id: f.top_pick.outcome_id,
                          selection: f.top_pick.selection, odds: f.top_pick.odds, confidence: f.top_pick.confidence,
                          league: f.league, country: f.country, kickoff: f.kickoff,
                        }} />
                      </div>
                    </div>
                  ) : <span className="text-xs text-muted">no pick</span>}
                  <ChevronRight size={18} className="text-muted group-hover:text-primary group-hover:translate-x-0.5 transition-all" />
                </div>
              </div>
            </Card>
          </Link>
        ))}
      </div>

      {data && !err && hiddenCount > 0 && (
        <button onClick={() => setShowAll((v) => !v)}
          className="mt-4 w-full rounded-lg border border-border bg-surface/60 py-2.5 text-sm text-muted hover:text-text hover:border-primary/40 transition-colors tnum">
          {showAll ? "hide no-stats matches" : `show all (${hiddenCount} no-stats)`}
        </button>
      )}

      {data && !err && rows.length === 0 && (
        <Card className="p-8 text-center text-muted text-sm">No matches with stats for this scope yet.</Card>
      )}
    </div>
  );
}
