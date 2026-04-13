/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './src/**/*.{ts,tsx}',
  ],
  presets: [require('nativewind/preset')],
  theme: {
    extend: {
      colors: {
        wood: {
          900: '#2C1810',
          800: '#3D2317',
          700: '#3D2B1F',
          600: '#4A3728',
          500: '#5C4535',
        },
        amber: {
          accent: '#D4A574',
          light: '#E8B86D',
        },
        cream: {
          DEFAULT: '#F5E6D0',
          dark: '#EDE0CC',
        },
        ivory: '#F5F0E8',
        muted: {
          brown: '#8B7D6B',
        },
        danger: '#C17B5F',
        success: '#7A9B6D',
      },
      fontFamily: {
        serif: ['PlayfairDisplay-Regular'],
        'serif-bold': ['PlayfairDisplay-Bold'],
        'serif-italic': ['PlayfairDisplay-Italic'],
        sans: ['DMSans-Regular'],
        'sans-medium': ['DMSans-Medium'],
        mono: ['JetBrainsMono-Regular'],
      },
      boxShadow: {
        'soft-wood': '0 12px 40px rgba(44, 24, 16, 0.42)',
        'inner-wood': 'inset 0 2px 10px rgba(0, 0, 0, 0.28)',
      },
    },
  },
  plugins: [],
}
