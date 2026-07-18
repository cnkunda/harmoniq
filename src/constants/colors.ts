const colors = {
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
  /** Tailwind `white` — AlphaTab primary glyphs on dark score. */
  white: '#FFFFFF',
  cream: '#F5E6D0',
  creamDark: '#EDE0CC',
  ivory: '#F5F0E8',
  muted: {
    /** ~5.2:1 contrast on bg-wood-900 — AA Normal text on dark surfaces. */
    brown: '#A69580',
  },
  danger: '#C17B5F',
  success: '#7A9B6D',
  /** Commit B1: Purple indicator for chromatic/tension notes outside chord. */
  chromatic: '#9B7DB5',
} as const

export default colors
