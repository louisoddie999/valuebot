"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Activity, LayoutGrid, Layers, BarChart3, History, Info, Clock } from "lucide-react";

export function Skeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="grid gap-2.5">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="rounded-xl border border-border bg-surface/60 p-4 animate-pulse">
          <div className="h-2.5 w-40 rounded bg-surface2 mb-2.5" />
          <div className="h-4 w-56 rounded bg-surface2" />
        </div>
      ))}
    </div>
  );
}

// Loading state that warns about Render cold-start if the fetch is slow.
export function LoadingState({ rows = 6 }: { rows?: number }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => { const t = setTimeout(() => setSlow(true), 3500); return () => clearTimeout(t); }, []);
  return (
    <div>
      {slow && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-accent/30 bg-accent/10 px-4 py-2.5 text-sm text-accent">
          <Activity size={15} className="animate-pulse" />
          Waking the server… first load after idle takes ~50s. Hang tight.
        </div>
      )}
      <Skeleton rows={rows} />
    </div>
  );
}

export function ConfidenceLegend() {
  const items = [
    { c: "bg-good", t: "≥80% — high" },
    { c: "bg-primary", t: "65–80% — solid" },
    { c: "bg-accent", t: "50–65% — lean" },
  ];
  return (
    <div className="group relative inline-flex items-center gap-2 text-xs text-muted">
      <Info size={13} /> <span>confidence</span>
      <span className="flex items-center gap-2 tnum">
        {items.map((i) => (
          <span key={i.t} className="flex items-center gap-1">
            <span className={`h-2 w-2 rounded-full ${i.c}`} /> {i.t}
          </span>
        ))}
      </span>
      <span className="pointer-events-none absolute left-0 top-6 z-20 w-64 rounded-lg border border-border bg-surface2 p-2.5 text-[11px] text-muted opacity-0 shadow-xl transition-opacity group-hover:opacity-100">
        Validated on 8,263 matches: an 80% pick lands ~81% of the time. Color = how confident the data is.
      </span>
    </div>
  );
}

export function Freshness({ iso }: { iso?: string | null }) {
  if (!iso) return null;
  let txt = "";
  try {
    const h = (Date.now() - new Date(iso).getTime()) / 36e5;
    txt = h < 1 ? "just now" : h < 24 ? `${Math.round(h)}h ago` : `${Math.round(h / 24)}d ago`;
  } catch { return null; }
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted/70 tnum">
      <Clock size={12} /> updated {txt}
    </span>
  );
}

export function confColor(c: number) {
  if (c >= 0.8) return "text-good border-good/40 bg-good/10";
  if (c >= 0.65) return "text-primary border-primary/40 bg-primary/10";
  if (c >= 0.5) return "text-accent border-accent/40 bg-accent/10";
  return "text-muted border-border bg-surface2";
}

export function ConfChip({ c }: { c: number }) {
  return (
    <span className={`tnum inline-flex items-center rounded-md border px-2 py-0.5 text-sm font-semibold ${confColor(c)}`}>
      {(c * 100).toFixed(0)}%
    </span>
  );
}

export function Odds({ v }: { v: number }) {
  return <span className="tnum text-muted">{v.toFixed(2)}</span>;
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-border bg-surface/80 backdrop-blur-sm ${className}`}>
      {children}
    </div>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-muted py-16 justify-center">
      <Activity className="animate-pulse" size={18} /> <span className="tnum">{label}</span>
    </div>
  );
}

const NAV = [
  { href: "/", label: "Fixtures", icon: LayoutGrid },
  { href: "/slips", label: "Slips", icon: Layers },
  { href: "/results", label: "Results", icon: History },
  { href: "/accuracy", label: "Accuracy", icon: BarChart3 },
];

export function Nav() {
  const path = usePathname();
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-bg/80 backdrop-blur-md">
      <div className="mx-auto max-w-6xl px-5 h-14 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5">
          <span className="grid place-items-center h-7 w-7 rounded-md bg-primaryDeep text-white font-mono font-bold text-sm">V</span>
          <span className="font-mono font-semibold tracking-tight">VALUE<span className="text-primary">BOT</span></span>
        </Link>
        <nav className="flex items-center gap-1">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? path === "/" : path.startsWith(href);
            return (
              <Link key={href} href={href}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition-colors ${active ? "bg-surface2 text-text" : "text-muted hover:text-text hover:bg-surface"}`}>
                <Icon size={15} /> {label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}

export function ScopeTabs({ value, onChange, scopes }: { value: string; onChange: (s: string) => void; scopes: string[] }) {
  return (
    <div className="inline-flex rounded-lg border border-border bg-surface p-1">
      {scopes.map((s) => (
        <button key={s} onClick={() => onChange(s)}
          className={`rounded-md px-3 py-1.5 text-sm font-medium capitalize transition-colors ${value === s ? "bg-primaryDeep text-white" : "text-muted hover:text-text"}`}>
          {s}
        </button>
      ))}
    </div>
  );
}
