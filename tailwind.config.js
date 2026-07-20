/** @type {import('tailwindcss').Config} */
module.exports = {
  // NativeWind/react-native-css-interop defaults `darkMode` to 'media'. Its web
  // runtime calls `colorScheme.set(...)` on startup, which throws
  // "Cannot manually set color scheme, as dark mode is type 'media'" when left
  // as 'media'. The app uses a fixed dark palette (no `dark:` variants), so
  // 'class' is safe and silences that error.
  darkMode: 'class',
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
          900: '#1b120e',
          800: '#2a1c15',
          700: '#3a271b',
          600: '#4a3225',
          500: '#5C4535',
        },
        amber: {
          accent: '#dba25e',
          light: '#E8B86D',
          dim: 'rgba(219,162,94,0.16)',
        },
        cream: {
          DEFAULT: '#f3e7d6',
          dark: '#EDE0CC',
        },
        ivory: '#F5F0E8',
        hairline: 'rgba(232,210,181,0.10)',
        muted: {
          brown: '#b39a86',
        },
        muted2: '#8a7362',
        danger: '#C17B5F',
        success: '#7A9B6D',
        ember: '#c1653a',
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
