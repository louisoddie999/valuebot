"use client";
import { useState } from "react";
import { Sparkles, Send, Plus, Ticket } from "lucide-react";
import { chatBuild, createBooking, fmtKick, BuildSlip } from "@/lib/api";
import { Card, ConfChip, Odds } from "@/components/ui";
import { useBetslip } from "@/components/betslip";

const SUGGESTIONS = [
  "Build me a ~300 odds for the week",
  "Give me 3 different slips around 20 odds",
  "Safe 5-leg slip for today",
  "Corners-only acca this weekend",
];

export function BuildChat() {
  const { add, setOpen } = useBetslip();
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [reply, setReply] = useState("");
  const [engine, setEngine] = useState("");
  const [slips, setSlips] = useState<BuildSlip[]>([]);
  const [err, setErr] = useState("");

  async function send(text?: string) {
    const m = (text ?? msg).trim();
    if (!m) return;
    setBusy(true); setErr(""); setReply(""); setSlips([]); setMsg(m);
    try {
      const r = await chatBuild(m);
      setReply(r.reply); setEngine(r.engine); setSlips(r.slips);
    } catch (e) { setErr("Build failed — is the API running?"); }
    finally { setBusy(false); }
  }

  function addAll(s: BuildSlip) {
    s.legs.forEach((l) =>
      add({ event_id: l.event_id, match: l.match, market: l.market, market_id: l.market_id,
            specifier: l.specifier, outcome_id: l.outcome_id, selection: l.selection,
            odds: l.odds, confidence: l.confidence, league: l.league, country: l.country, kickoff: l.kickoff }));
    setOpen(true);
  }

  return (
    <Card className="p-4 mb-6">
      <div className="flex items-center gap-2 mb-3">
        <Sparkles size={16} className="text-accent" />
        <span className="font-mono font-semibold">Build Control</span>
        <span className="text-xs text-muted">— tell it what slip you want</span>
        {engine && <span className="ml-auto text-[10px] text-muted/70 tnum uppercase">{engine}</span>}
      </div>

      <div className="flex gap-2">
        <input value={msg} onChange={(e) => setMsg(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="e.g. build me a 300 odds for the week"
          className="flex-1 rounded-lg border border-border bg-surface2 px-4 py-2.5 text-sm outline-none focus:border-accent" />
        <button onClick={() => send()} disabled={busy}
          className="flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-black hover:brightness-110 disabled:opacity-50">
          <Send size={15} /> {busy ? "…" : "Build"}
        </button>
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {SUGGESTIONS.map((s) => (
          <button key={s} onClick={() => send(s)} disabled={busy}
            className="rounded-full border border-border px-2.5 py-1 text-xs text-muted hover:text-text hover:border-accent/50">
            {s}
          </button>
        ))}
      </div>

      {err && <div className="mt-3 text-bad text-sm">{err}</div>}
      {reply && <div className="mt-3 text-sm text-text">{reply}</div>}

      {slips.map((s, i) => (
        <div key={i} className="mt-3 rounded-lg border border-border overflow-hidden">
          <div className="flex items-center justify-between bg-surface2 px-4 py-2.5">
            <div className="text-sm"><span className="text-muted">Slip {i + 1} · {s.n_legs} legs</span>
              <span className="ml-3 font-mono text-lg font-bold text-primary tnum">{s.combined_odds.toFixed(2)}</span>
              <span className="ml-2 text-xs text-muted tnum">~{s.hit_estimate.toFixed(1)}% hit</span>
            </div>
            <div className="flex gap-2">
              <button onClick={() => addAll(s)} className="flex items-center gap-1 rounded-md border border-accent/50 bg-accent/10 text-accent px-2.5 py-1 text-xs font-medium hover:bg-accent/20">
                <Plus size={13} /> Add all
              </button>
              <BookBtn legs={s.legs} />
            </div>
          </div>
          <div className="divide-y divide-border">
            {s.legs.map((l, j) => (
              <div key={j} className="px-4 py-2 flex items-start justify-between gap-3 text-sm">
                <div className="min-w-0">
                  <div className="text-[11px] text-muted/80 tnum">{l.country} · {l.league} · {fmtKick(l.kickoff)}</div>
                  <div className="text-xs text-muted truncate">{l.match}</div>
                  <div className="font-medium">{l.market} — {l.selection}</div>
                </div>
                <div className="flex items-center gap-2 shrink-0"><ConfChip c={l.confidence} /> <Odds v={l.odds} /></div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </Card>
  );
}

function BookBtn({ legs }: { legs: BuildSlip["legs"] }) {
  const [code, setCode] = useState<{ code: string; url: string } | null>(null);
  const [busy, setBusy] = useState(false);
  async function go() {
    setBusy(true);
    try { const r = await createBooking(legs as any); setCode({ code: r.shareCode, url: r.shareURL }); }
    catch {} finally { setBusy(false); }
  }
  if (code) return <a href={code.url} target="_blank" rel="noreferrer" className="font-mono text-sm font-bold text-accent tracking-wider">{code.code} ↗</a>;
  return (
    <button onClick={go} disabled={busy} className="flex items-center gap-1 rounded-md bg-accent px-2.5 py-1 text-xs font-semibold text-black hover:brightness-110 disabled:opacity-50">
      <Ticket size={13} /> {busy ? "…" : "Book"}
    </button>
  );
}
