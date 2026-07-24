import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: "var(--color-primary)",
        "primary-dark": "var(--color-primary-dark)",
        bg: "var(--color-bg)",
        surface: "var(--color-surface)",
        cta: "var(--color-cta)",
        highlight: "var(--color-highlight)",
        neutral: "var(--color-neutral)",
        text: "var(--color-text)",
        "text-muted": "var(--color-text-muted)",

        "bg-primary": "var(--color-bg-primary)",
        "brand-primary": "var(--color-brand-primary)",
        "text-primary": "var(--color-text-primary)",
        "data-highlight": "var(--color-data-highlight)",
        "accent-cta": "var(--color-accent-cta)",

        border: "var(--color-border)",
      },
      fontFamily: {
        sans: ['"Instrument Sans"', "sans-serif"],
        display: ['"Instrument Sans"', "sans-serif"],
        mono: ['"DM Mono"', "monospace"],
      },
      fontSize: {
        /* Compact app scale — nav mono 10px is the density reference */
        "eyebrow-sm": [
          "10px",
          { lineHeight: "1.2", letterSpacing: "0.12em" },
        ],
        eyebrow: ["11px", { lineHeight: "1.2", letterSpacing: "0.14em" }],
        label: ["9px", { lineHeight: "1.2", letterSpacing: "0.08em" }],
        btn: ["13px", { lineHeight: "1.2" }],
        "body-sm": ["0.8125rem", { lineHeight: "1.45" }],
        body: ["0.875rem", { lineHeight: "1.5" }],
        subtitle: ["0.9375rem", { lineHeight: "1.4" }],
        title: ["1.05rem", { lineHeight: "1.3" }],
        "nav-logo": ["1.15rem", { lineHeight: "1.2" }],
        heading: ["1.35rem", { lineHeight: "1.25" }],
        "heading-lg": ["1.5rem", { lineHeight: "1.2" }],
        display: ["2rem", { lineHeight: "1.15" }],
      },
      borderRadius: {
        card: "var(--radius-card)",
        tile: "var(--radius-tile)",
        pill: "var(--radius-pill)",
        input: "var(--radius-input)",
      },
      width: {
        sidebar: "240px",
        "right-panel": "320px",
      },
      spacing: {
        sidebar: "240px",
        "right-panel": "320px",
      },
    },
  },
  plugins: [],
};

export default config;
