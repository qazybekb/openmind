/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}'],
  theme: {
    extend: {
      colors: {
        'bg': '#09090b',
        'bg-card': '#111113',
        'bg-card-hover': '#18181b',
        'border': '#27272a',
        'border-hover': '#3f3f46',
        'text-primary': '#fafafa',
        'text-secondary': '#a1a1aa',
        'text-muted': '#52525b',
        'accent': '#e4e4e7',
        'cal-gold': '#FDB515',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'SF Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
};
