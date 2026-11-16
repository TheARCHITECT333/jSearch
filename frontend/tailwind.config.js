/** @type {import('tailwindcss').Config} */
// Tokens from DESIGN.md (Apple-style): one accent, photographic neutrals,
// near-black dark tiles, pills for actions.
const sans = [
  "-apple-system",
  "BlinkMacSystemFont",
  "SF Pro Text",
  "Inter Variable",
  "system-ui",
  "sans-serif",
];
const display = [
  "-apple-system",
  "BlinkMacSystemFont",
  "SF Pro Display",
  "Inter Variable",
  "system-ui",
  "sans-serif",
];

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Text + dark utility button.
        ink: {
          DEFAULT: "#1d1d1f",
          // Dark-tile palette, used by the setup rail.
          tile: "#272729",
          raised: "#2a2a2c",
          deep: "#252527",
          line: "#3a3a3c",
          text: "#ffffff",
          muted: "#cccccc",
          faint: "#a1a1a6",
        },
        nav: "#000000",
        paper: "#f5f5f7", // canvas-parchment
        surface: "#ffffff", // canvas
        pearl: "#fafafc",
        edge: "#e0e0e0", // hairline
        divider: "#f0f0f0",
        body: "#333333", // ink-muted-80
        faint: "#7a7a7a", // ink-muted-48
        chip: "#d2d2d7",

        // The single accent. Every "click me" and every "good" signal.
        primary: {
          DEFAULT: "#0066cc",
          focus: "#0071e3",
          dark: "#2997ff", // on dark tiles only
        },
        // DESIGN.md documents no error state; a ruled-out job and a failed
        // request still need one, so this is the only addition - text only.
        alert: {
          DEFAULT: "#d70015",
          soft: "#fff2f3",
          line: "#f5c6cb",
          dark: "#ff453a", // on dark tiles
        },
      },
      fontFamily: {
        sans,
        display,
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      borderRadius: {
        xs: "5px",
        sm: "8px",
        md: "11px",
        lg: "18px",
        pill: "9999px",
      },
      letterSpacing: {
        apple: "-0.374px", // body + display-md
        caption: "-0.224px",
        fine: "-0.12px",
        hero: "-0.28px",
      },
      boxShadow: {
        product: "rgba(0, 0, 0, 0.22) 3px 5px 30px 0",
      },
    },
  },
  plugins: [],
};
