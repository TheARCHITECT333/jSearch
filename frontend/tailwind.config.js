/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Dark chrome: the control rail and top bar.
        ink: {
          DEFAULT: "#101418",
          raised: "#191E24",
          line: "#2A313A",
          text: "#E7EAEE",
          muted: "#8D97A5",
          faint: "#5C6673",
        },
        // Light readout: where jobs are actually read.
        paper: "#F3F4F6",
        surface: "#FFFFFF",
        edge: "#E3E6EA",
        body: "#5A6470",
        faint: "#8A94A1",

        // The only two colors in the app, and both mean a verdict about a
        // job: worth your time, or barred. Nothing decorative is colored.
        signal: {
          DEFAULT: "#00966B",
          soft: "#E6F4EF",
          line: "#B9DFD1",
        },
        oxide: {
          DEFAULT: "#B4432C",
          soft: "#FBEDEA",
          line: "#EDC9C0",
        },
      },
      fontFamily: {
        sans: ["Archivo Variable", "Archivo", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      borderRadius: {
        card: "10px",
        control: "8px",
      },
      letterSpacing: {
        tightest: "-0.035em",
      },
    },
  },
  plugins: [],
};
