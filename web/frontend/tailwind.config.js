/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          orange:   "#F5A51B",
          dark:     "#D4880A",
          charcoal: "#2B2B2B",
          sky:      "#87C9E8",
          tint:     "#FFF5E0",
          gray:     "#F4F4F4",
          line:     "#DDDDDD",
        },
        verdict: {
          buy:      "#27AE60",
          consider: "#F5A51B",
          nobuy:    "#E74C3C",
          watch:    "#F39C12",
          info:     "#2980B9",
        },
      },
    },
  },
  plugins: [],
};
