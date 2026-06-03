"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, LayoutGrid, Layers, BarChart3, History } from "lucide-react";

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
