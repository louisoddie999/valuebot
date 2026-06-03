import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0a0e14",
        surface: "#11161f",
        surface2: "#161d29",
        border: "#1f2937",
        primary: "#3B82F6",
        primaryDeep: "#1E40AF",
        accent: "#D97706",
        good: "#16A34A",
        warn: "#D97706",
        bad: "#DC2626",
        text: "#E5EAF2",
        muted: "#8593A8",
      },
      fontFamily: {
        mono: ["var(--font-mono)", "monospace"],
        sans: ["var(--font-sans)", "system-ui"],
      },
      fontFeatureSettings: { tnum: '"tnum" 1' },
    },
  },
  plugins: [],
};
export default config;
