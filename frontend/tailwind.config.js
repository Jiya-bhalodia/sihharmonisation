/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          950: '#173447', 900: '#1b4658', 800: '#1d5b68', 700: '#226d77',
          600: '#087f83', 500: '#328f8d', 400: '#62ad9f', 300: '#8ac9b9',
          200: '#9fd3bf', 100: '#d5ebe2', 50: '#eff8f4',
        },
        ink: {
          950: '#102838', 900: '#173447', 800: '#244657', 700: '#365b69',
          600: '#58727d', 500: '#718891', 400: '#91a4a8', 300: '#b2c3c1',
          200: '#c8ddd7', 100: '#e4efeb', 50: '#fbfefd',
        },
        amber: {
          500: '#d97706',
        },
      },
      fontFamily: {
        sans: ['"DM Sans"', 'system-ui', 'sans-serif'],
        serif: ['"DM Serif Display"', 'Georgia', 'serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      boxShadow: {
        panel: '0 1px 2px rgba(10,20,15,0.06), 0 8px 24px -8px rgba(10,20,15,0.12)',
      },
    },
  },
  plugins: [],
}
