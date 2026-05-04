import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#121417",
        paper: "#f7f3ea",
        line: "#d8d1c3",
        signal: "#1f7a6d",
        ember: "#c44e2d",
      },
      fontFamily: {
        sans: ["Inter", "Arial", "Helvetica", "sans-serif"],
        mono: ["Menlo", "Consolas", "monospace"],
      },
      boxShadow: {
        panel: "0 18px 60px rgba(18, 20, 23, 0.10)",
      },
    },
  },
  plugins: [],
};

export default config;
