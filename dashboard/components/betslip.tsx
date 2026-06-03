"use client";
import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { Ticket, X, Trash2, Plus, Check, ExternalLink, Lock, Unlock, Save, FolderOpen } from "lucide-react";
import { createBooking, fmtKick } from "@/lib/api";
import { ConfChip, Odds } from "@/components/ui";

const MAX_LEGS = 50;
const KEY = "valuebot.betslip.v1";
const SAVED_KEY = "valuebot.saved.v1";
type SavedSlip = { name: string; items: Selection[] };

export type Selection = {
  event_id: string; match: string; market: string; market_id: string;
  specifier: string | null; outcome_id: string; selection: string;
  odds: number; confidence: number;
  league?: string; country?: string; kickoff?: string;
};

type Ctx = {
  items: Selection[];
  add: (s: Selection) => void;
  remove: (event_id: string) => void;
  clear: () => void;
  hasEvent: (event_id: string) => boolean;
  locked: Set<string>; toggleLock: (event_id: string) => void;
  saved: SavedSlip[]; saveCurrent: () => void; loadSaved: (i: number) => void; delSaved: (i: number) => void;
  open: boolean; setOpen: (b: boolean) => void;
};
const BetslipCtx = createContext<Ctx | null>(null);
export const useBetslip = () => {
  const c = useContext(BetslipCtx);
  if (!c) throw new Error("useBetslip outside provider");
  return c;
};

export function BetslipProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<Selection[]>([]);
  const [locked, setLocked] = useState<Set<string>>(new Set());
  const [saved, setSaved] = useState<SavedSlip[]>([]);
  const [open, setOpen] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try { const r = localStorage.getItem(KEY); if (r) setItems(JSON.parse(r)); } catch {}
    try { const s = localStorage.getItem(SAVED_KEY); if (s) setSaved(JSON.parse(s)); } catch {}
    setHydrated(true);
  }, []);
  useEffect(() => { if (hydrated) localStorage.setItem(KEY, JSON.stringify(items)); }, [items, hydrated]);
  useEffect(() => { if (hydrated) localStorage.setItem(SAVED_KEY, JSON.stringify(saved)); }, [saved, hydrated]);

  const toggleLock = useCallback((eid: string) => setLocked((p) => {
    const n = new Set(p); n.has(eid) ? n.delete(eid) : n.add(eid); return n;
  }), []);
  const saveCurrent = useCallback(() => {
    setItems((cur) => {
      if (cur.length) {
        const name = `${cur.length} legs @ ${cur.reduce((a, x) => a * x.odds, 1).toFixed(1)}`;
        setSaved((s) => [{ name, items: cur }, ...s].slice(0, 20));
      }
      return cur;
    });
  }, []);
  const loadSaved = useCallback((i: number) => setSaved((s) => { const sl = s[i]; if (sl) setItems(sl.items); return s; }), []);
  const delSaved = useCallback((i: number) => setSaved((s) => s.filter((_, j) => j !== i)), []);

  const add = useCallback((s: Selection) => {
    setItems((prev) => {
      const without = prev.filter((x) => x.event_id !== s.event_id); // one-per-match
      if (without.length >= MAX_LEGS) return prev;
      return [...without, s];
    });
    setOpen(true);
  }, []);
  const remove = useCallback((eid: string) => setItems((p) => p.filter((x) => x.event_id !== eid)), []);
  const clear = useCallback(() => setItems((p) => p.filter((x) => locked.has(x.event_id))), [locked]);
  const hasEvent = useCallback((eid: string) => items.some((x) => x.event_id === eid), [items]);

  return (
    <BetslipCtx.Provider value={{ items, add, remove, clear, hasEvent, locked, toggleLock, saved, saveCurrent, loadSaved, delSaved, open, setOpen }}>
      {children}
      <BetslipDock />
    </BetslipCtx.Provider>
  );
}

export function AddButton({ sel, label = "Add" }: { sel: Selection; label?: string }) {
  const { add, items } = useBetslip();
  const on = items.find((x) => x.event_id === sel.event_id);
  const same = on && on.outcome_id === sel.outcome_id && String(on.market_id) === String(sel.market_id);
  return (
    <button
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); add(sel); }}
      className={`flex items-center gap-1 rounded-md border px-2 py-1 text-xs font-medium transition-colors ${
        same ? "border-good/50 bg-good/15 text-good" : "border-accent/50 bg-accent/10 text-accent hover:bg-accent/20"}`}>
      {same ? <Check size={13} /> : <Plus size={13} />} {same ? "Added" : label}
    </button>
  );
}

function BetslipDock() {
  const { items, remove, clear, open, setOpen, locked, toggleLock, saved, saveCurrent, loadSaved, delSaved } = useBetslip();
  const combined = items.reduce((a, x) => a * x.odds, 1);
  const hit = items.reduce((a, x) => a * x.confidence, 1);
  const [code, setCode] = useState<{ code: string; url: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { setCode(null); setErr(""); }, [items.length]);

  async function book() {
    setBusy(true); setErr(""); setCode(null);
    try {
      const r = await createBooking(items as any);
      setCode({ code: r.shareCode, url: r.shareURL });
    } catch { setErr("Could not generate code — try again."); }
    finally { setBusy(false); }
  }

  return (
    <>
      {/* floating button */}
      <button onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-50 flex items-center gap-2.5 rounded-full bg-accent px-5 py-3 text-black font-semibold shadow-lg shadow-accent/20 hover:brightness-110 transition">
        <Ticket size={18} />
        <span className="tnum">{items.length}</span>
        {items.length > 0 && <span className="tnum text-sm opacity-80">@ {combined.toFixed(2)}</span>}
      </button>

      {/* slide-in panel */}
      {open && (
        <div className="fixed inset-0 z-50" onClick={() => setOpen(false)}>
          <div className="absolute inset-0 bg-black/50" />
          <aside onClick={(e) => e.stopPropagation()}
            className="absolute right-0 top-0 h-full w-full max-w-md bg-surface border-l border-border flex flex-col">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <div className="flex items-center gap-2 font-mono font-semibold"><Ticket size={18} className="text-accent" /> Betslip <span className="text-muted tnum">({items.length}/{MAX_LEGS})</span></div>
              <button onClick={() => setOpen(false)} className="text-muted hover:text-text"><X size={20} /></button>
            </div>

            {items.length === 0 ? (
              <div className="flex-1 grid place-items-center text-muted text-sm px-6 text-center">
                Empty. Tap <span className="text-accent mx-1">+ Add</span> on any prediction to build your slip.
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto divide-y divide-border">
                {items.map((x) => (
                  <div key={x.event_id} className="px-5 py-3 flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-[11px] text-muted/80 tnum truncate">
                        {x.country && <span className="text-primary/80">{x.country}</span>}
                        {x.league && <span> · {x.league}</span>}
                        {x.kickoff && <span> · {fmtKick(x.kickoff)}</span>}
                      </div>
                      <div className="text-xs text-muted truncate">{x.match}</div>
                      <div className="text-sm font-medium">{x.market} — {x.selection}</div>
                      <div className="mt-1 flex items-center gap-2"><ConfChip c={x.confidence} /> <Odds v={x.odds} /></div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <button onClick={() => toggleLock(x.event_id)}
                        className={locked.has(x.event_id) ? "text-accent" : "text-muted hover:text-text"}
                        title={locked.has(x.event_id) ? "locked (kept on clear)" : "lock leg"}>
                        {locked.has(x.event_id) ? <Lock size={14} /> : <Unlock size={14} />}
                      </button>
                      <button onClick={() => remove(x.event_id)} className="text-muted hover:text-bad"><Trash2 size={15} /></button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {saved.length > 0 && (
              <div className="border-t border-border px-5 py-2.5">
                <div className="flex items-center gap-1.5 text-xs text-muted mb-1.5"><FolderOpen size={13} /> Saved</div>
                <div className="flex flex-wrap gap-1.5">
                  {saved.map((s, i) => (
                    <span key={i} className="group flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs tnum">
                      <button onClick={() => loadSaved(i)} className="hover:text-primary">{s.name}</button>
                      <button onClick={() => delSaved(i)} className="text-muted hover:text-bad"><X size={11} /></button>
                    </span>
                  ))}
                </div>
              </div>
            )}

            {items.length > 0 && (
              <div className="border-t border-border p-5 space-y-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted">Combined odds</span>
                  <span className="font-mono text-2xl font-bold text-primary tnum">{combined.toFixed(2)}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted">Est. hit chance</span>
                  <span className="tnum">{(hit * 100).toFixed(2)}%</span>
                </div>
                {code ? (
                  <div className="rounded-lg bg-accent/10 border border-accent/30 p-3 text-center">
                    <div className="text-xs text-muted">SportyBet booking code</div>
                    <div className="font-mono text-3xl font-bold text-accent tracking-widest my-1">{code.code}</div>
                    <a href={code.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline">
                      Open in SportyBet <ExternalLink size={14} />
                    </a>
                    <div className="text-xs text-muted mt-1">load · review · stake yourself</div>
                  </div>
                ) : (
                  <button onClick={book} disabled={busy}
                    className="w-full rounded-lg bg-accent py-3 font-semibold text-black hover:brightness-110 disabled:opacity-50 transition">
                    {busy ? "Generating…" : "Generate booking code"}
                  </button>
                )}
                {err && <div className="text-bad text-sm text-center">{err}</div>}
                <div className="flex items-center justify-between text-xs">
                  <button onClick={saveCurrent} className="flex items-center gap-1 text-muted hover:text-accent"><Save size={13} /> save slip</button>
                  <button onClick={clear} className="text-muted hover:text-bad">clear {locked.size > 0 && `(keep ${locked.size} locked)`}</button>
                </div>
              </div>
            )}
          </aside>
        </div>
      )}
    </>
  );
}
