/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Fitness-App-Palette: dunkler Slate-Hintergrund + kräftiger Akzent.
        background: "#0b0f14",
        surface: "#141a21",
        accent: "#22d3ee",
      },
    },
  },
  plugins: [],
};
