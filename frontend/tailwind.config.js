/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#EEF0FB', 100: '#DDE1F7', 200: '#BAC3EF', 300: '#8E9BE3',
          400: '#6472D4', 500: '#4750C4', 600: '#373DA6', 700: '#2C3182',
          800: '#232764', 900: '#1B1E4D', 950: '#121432',
        },
        // The gold from the logo's "uru". The indigo above carries the product;
        // this carries the marketing site, where a single accent is the
        // difference between "clean" and "blank".
        accent: {
          50: '#FFF8EC', 100: '#FEEDCC', 200: '#FDDB99', 300: '#FBC35C',
          400: '#F7AC2E', 500: '#EE9612', 600: '#D2790B', 700: '#A85A0D',
          800: '#894913', 900: '#713D13',
        },
        canvas: '#F5F6FA',
        line: '#E4E7EF',
      },
      fontFamily: {
        sans: ['Inter', 'Inter var', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem', letterSpacing: '0.01em' }],
      },
      boxShadow: {
        card: '0 1px 2px 0 rgba(16,24,40,0.04), 0 1px 3px 0 rgba(16,24,40,0.06)',
        lift: '0 4px 12px -2px rgba(16,24,40,0.08), 0 2px 6px -2px rgba(16,24,40,0.05)',
        pop: '0 12px 32px -8px rgba(16,24,40,0.18)',
      },
      keyframes: {
        fadeIn: { '0%': { opacity: 0 }, '100%': { opacity: 1 } },
        popIn: { '0%': { opacity: 0, transform: 'translateY(6px) scale(.985)' }, '100%': { opacity: 1, transform: 'none' } },
        slideLeft: { '0%': { transform: 'translateX(-100%)' }, '100%': { transform: 'none' } },
        slideRight: { '0%': { transform: 'translateX(100%)' }, '100%': { transform: 'none' } },
        slideUp: { '0%': { transform: 'translateY(100%)' }, '100%': { transform: 'none' } },
        growY: { '0%': { transform: 'scaleY(0)' }, '100%': { transform: 'scaleY(1)' } },
      },
      animation: {
        fadeIn: 'fadeIn .15s ease-out',
        popIn: 'popIn .16s cubic-bezier(.2,.8,.3,1)',
        slideLeft: 'slideLeft .2s cubic-bezier(.2,.8,.3,1)',
        slideRight: 'slideRight .2s cubic-bezier(.2,.8,.3,1)',
        slideUp: 'slideUp .2s cubic-bezier(.2,.8,.3,1)',
        growY: 'growY .5s cubic-bezier(.2,.8,.3,1)',
      },
    },
  },
  plugins: [],
}
