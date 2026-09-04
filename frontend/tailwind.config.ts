import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          50: "#f6f7f9",
          100: "#eceef2",
          200: "#d5d9e2",
          300: "#b0b8c8",
          400: "#8491a8",
          500: "#64728c",
          600: "#4e5a72",
          700: "#40495c",
          800: "#373e4e",
          900: "#131722",
        },
      },
      fontFamily: {
        sans: [
          "system-ui",
          "-apple-system",
          "Hiragino Kaku Gothic ProN",
          "Meiryo",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};

export default config;
