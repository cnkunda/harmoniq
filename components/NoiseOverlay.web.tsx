import { createElement } from 'react'

/** Inline SVG turbulence — matches DESIGN_SYSTEM.md NoiseOverlay.web.tsx */
const NOISE_DATA_URI =
  "data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E"

export function NoiseOverlay() {
  return createElement('div', {
    style: {
      position: 'fixed',
      inset: 0,
      pointerEvents: 'none',
      zIndex: 50,
      opacity: 0.055,
      mixBlendMode: 'overlay',
      backgroundImage: `url("${NOISE_DATA_URI}")`,
      backgroundSize: '200px 200px',
    },
  })
}
