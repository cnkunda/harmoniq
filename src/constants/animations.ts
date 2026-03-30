/** Shared animation presets for Reanimated — pass to withSpring / withTiming. */
export const spring = {
  gentle: { damping: 20, stiffness: 200 },
  snappy: { damping: 20, stiffness: 400 },
  bounce: { damping: 12, stiffness: 300 },
} as const

export const timing = {
  fast: 150,
  normal: 250,
  slow: 400,
} as const

/** Stagger entrance animations: multiply by child index */
export function entranceDelay(index: number): number {
  return index * 60
}
