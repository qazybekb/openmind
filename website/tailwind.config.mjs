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
        'text-primary': '#fafafa',        // headings, important — 19.1:1
        'text-body': '#d4d4d8',           // body text — 13.5:1
        'text-secondary': '#a1a1aa',      // nav, labels — 7.8:1
        'text-muted': '#71717a',          // captions, timestamps — 4.1:1 (large text only)
        'accent': '#e4e4e7',
        'cal-gold': '#FDB515',            // 11.2:1
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'SF Mono', 'Fira Code', 'monospace'],
      },
      fontSize: {
        // Override defaults for dark mode readability
        'xs': ['0.8125rem', { lineHeight: '1.5' }],    // 13px
        'sm': ['0.875rem', { lineHeight: '1.6' }],     // 14px
        'base': ['1rem', { lineHeight: '1.7' }],       // 16px
        'lg': ['1.125rem', { lineHeight: '1.65' }],    // 18px
        'xl': ['1.25rem', { lineHeight: '1.6' }],      // 20px
      },
    },
  },
  plugins: [],
};
