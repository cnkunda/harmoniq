const colors = {
  wood: {
    /** bg — deepest backgrounds */
    900: '#1b120e',
    /** surface — card surfaces */
    800: '#2a1c15',
    /** surface2 — secondary card backgrounds */
    700: '#3a271b',
    /** surface3 — borders, muted backgrounds */
    600: '#4a3225',
    /** Subtle lines, secondary borders */
    500: '#5C4535',
  },
  amber: {
    /** brass — primary accent / CTA */
    accent: '#dba25e',
    /** Secondary accent, active tint */
    light: '#E8B86D',
    /** brassDim — accent at low opacity */
    dim: 'rgba(219,162,94,0.16)',
  },
  /** Tailwind `white` — AlphaTab primary glyphs on dark score. */
  white: '#FFFFFF',
  /** cream — primary text */
  cream: '#f3e7d6',
  creamDark: '#EDE0CC',
  ivory: '#F5F0E8',
  /** hairline — subtle borders, dividers */
  hairline: 'rgba(232,210,181,0.10)',
  muted: {
    /** ~5.2:1 contrast on bg-wood-900 — AA Normal text on dark surfaces. */
    brown: '#b39a86',
  },
  /** muted2 — dimmer secondary text */
  muted2: '#8a7362',
  danger: '#C17B5F',
  success: '#7A9B6D',
  /** Commit B1: Purple indicator for chromatic/tension notes outside chord. */
  chromatic: '#9B7DB5',
  /** ember — warm emphasis, distinct from danger (error/missed) */
  ember: '#c1653a',
} as const

export default colors
