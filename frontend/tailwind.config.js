/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          950: '#04140f',
          900: '#062018',
          800: '#0a3324',
          700: '#0f4a34',
          600: '#146144',
          500: '#1a7a56',
          400: '#2c9a70',
          300: '#5fbd94',
          200: '#a3dcc0',
          100: '#d6f0e3',
          50: '#eefaf3',
        },
        ink: {
          950: '#0a0e12',
          900: '#10161c',
          800: '#1a2229',
          700: '#252f38',
          600: '#37434e',
          500: '#4d5a66',
          400: '#71808c',
          300: '#9ba7b1',
          200: '#c6cdd3',
          100: '#e5e9eb',
          50: '#f4f6f7',
        },
        amber: {
          500: '#d97706',
        },
      },
      fontFamily: {
        sans: ['"Inter"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      boxShadow: {
        panel: '0 1px 2px rgba(10,20,15,0.06), 0 8px 24px -8px rgba(10,20,15,0.12)',
      },
    },
  },
  plugins: [],
}