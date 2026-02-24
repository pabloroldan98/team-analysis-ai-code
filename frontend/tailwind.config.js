/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#76C7A1",
          dark: "#1f3b2d",
          text: "#36674F",
          light: "#eaffea",
        },
        danger: {
          light: "#ffeaea",
          DEFAULT: "#b22222",
          dark: "#8b0000",
          accent: "#cc0000",
        },
      },
      fontFamily: {
        sans: [
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Ubuntu",
          "Cantarell",
          "Noto Sans",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};
