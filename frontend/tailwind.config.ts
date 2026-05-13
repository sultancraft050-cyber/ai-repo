import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./machines/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#e5edf8",
        panel: "#172033",
        line: "#2b3851",
        muted: "#9ca8bd",
        signal: "#2dd4bf",
        caution: "#fbbf24",
        danger: "#fb7185",
        violet: "#a78bfa"
      },
      boxShadow: {
        tight: "0 18px 48px rgba(0, 0, 0, 0.22)"
      }
    }
  },
  plugins: []
};

export default config;
