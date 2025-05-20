/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}", // Scans these files for Tailwind classes
  ],
  theme: {
    extend: {
      // You can extend your theme here if you prefer JS-based config
      // over or in addition to CSS-based @theme directive
    },
  },
  plugins: [
    // You can add Tailwind plugins here
  ],
}