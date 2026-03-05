/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#0c0c0c',
        bg1: '#111111',
        bg2: '#171717',
        bg3: '#1e1e1e',
        border: '#262626',
        border2: '#2e2e2e',
        text: '#d4c5a0',
        text2: '#8a7d65',
        text3: '#534d42',
        amber: '#f59e0b',
        amber2: '#d97706',
        green: '#10b981',
        red: '#ef4444',
        blue: '#60a5fa',
      },
      fontFamily: {
        mono: ["'JetBrains Mono'", 'monospace'],
      },
    },
  },
  plugins: [],
};
