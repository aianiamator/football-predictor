/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        home: "#16a34a",   // green  - home win
        draw: "#cbd5e1",   // light slate - draw. Deliberately lighter than any
                           // confidence grey so the two never read as the same thing.
        away: "#2563eb",   // blue   - away win
      },
      fontFamily: {
        // System stack only. No web fonts: they cost bytes and block paint.
        sans: ["system-ui", "-apple-system", "Segoe UI", "Roboto",
               "Helvetica Neue", "Arial", "sans-serif"],
      },
    },
  },
  plugins: [],
}
