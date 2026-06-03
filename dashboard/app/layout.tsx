import "./globals.css";
import type { Metadata } from "next";
import { Nav } from "@/components/ui";
import { BetslipProvider } from "@/components/betslip";

export const metadata: Metadata = {
  title: "ValueBot — Football Prediction Engine",
  description: "Data-driven football predictions: form, xG, H2H, corners, injuries.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <BetslipProvider>
          <Nav />
          <main className="mx-auto max-w-6xl px-5 pt-7 pb-24 sm:pb-7">{children}</main>
          <footer className="mx-auto max-w-6xl px-5 py-8 text-xs text-muted/70 tnum">
            Predictions from data — form · goals · H2H · corners · half-time · injuries · rest.
            Calibrated, validated. Not financial advice.
          </footer>
        </BetslipProvider>
      </body>
    </html>
  );
}
