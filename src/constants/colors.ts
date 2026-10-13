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
    light: '#B8A99A',
    cream: '#C2B5A3',
  },
  /** muted2 — dimmer secondary text */
  muted2: '#8a7362',
  danger: '#C17B5F',
  success: '#7A9B6D',
  /** Commit B1: Purple indicator for chromatic/tension notes outside chord. */
  chromatic: '#9B7DB5',
  /** ember — warm emphasis, distinct from danger (error/missed) */
  ember: '#c1653a',
  /** Commit 154: solo-note active glow (artwork-specific, SVG radial gradient). */
  soloActive: '#E53935',
  /** Commit 154: AlphaTab scale-degree highlight tint for in-scale note heads. */
  scaleHighlight: '#6EC88C',
  /** Commit 154: light-theme score meta text (AlphaTab presets). */
  tabScoreInfo: '#6B5D4B',
  /** Commit 154: light-theme scrollbar thumb on cream parchment. */
  scrollThumbLight: '#b8956a',
  /** Commit 154: light-theme scrollbar thumb hover. */
  scrollThumbLightHover: '#a08055',
  /** Commit 154: alternate chart group color (fret-dot groups). */
  chartGroup: '#5a3f2d',
  /** Commit 154: finger-legend colors for fretboard diagram. */
  finger: {
    one: { fill: '#60A5FA', border: '#3B82F6' },
    two: { fill: '#34D399', border: '#10B981' },
    three: { fill: '#FBBF24', border: '#F59E0B' },
    four: { fill: '#F87171', border: '#EF4444' },
  },
  /** Commit 154: translucent card gradient stops (WoodGradient translucentCard). */
  translucentCardFrom: 'rgba(74, 55, 40, 0.98)',
  translucentCardTo: 'rgba(44, 24, 16, 0.99)',
  /** Commit 154: AlphaTab cursor bar wash (amber @ ~22% on dark score). */
  barWash: 'rgba(212, 165, 116, 0.22)',
  /** Commit 154: AlphaTab scrollbar track on dark score. */
  woodTrack: 'rgba(61, 35, 23, 0.92)',
  /** Commit 154: AlphaTab scrollbar track on cream parchment (light theme). */
  lightTrack: 'rgba(200, 190, 175, 0.6)',
  /** Commit 154: cursor beat glow shadow (AlphaTab player CSS). */
  beatGlow: 'rgba(44, 24, 16, 0.45)',
  /** Commit 154: Switch on-track tint (stem mixer toggles). */
  switchTrackOn: 'rgba(212, 165, 116, 0.5)',
  /** Commit 154: loop-bracket outline (AlphaTab loop selection overlay). */
  loopBracketBorder: 'rgba(240,222,180,0.92)',
  /** Commit 154: loop-bracket fill wash (AlphaTab loop selection overlay). */
  loopBracketWash: 'rgba(240,222,180,0.06)',
  /** Commit 154: harness screen divider (musicxml-render-test corpus header). */
  harnessDivider: 'rgba(163,123,76,0.4)',
  /** Commit 154: metronome bob glow ring. */
  metronomeRing: 'rgba(232, 184, 109, 0.4)',
} as const

export { colors }
