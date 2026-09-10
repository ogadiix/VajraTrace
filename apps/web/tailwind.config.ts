import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx,js,jsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        ink: "#12161C",
        paper: "#F7F8FA",
        "signal-amber": "#C8801F",
        "signal-red": "#A6392E",
        "trace-teal": "#3E8E85",
        line: "#2A313C",
      },
    },
  },
  plugins: [],
};

export default config;
