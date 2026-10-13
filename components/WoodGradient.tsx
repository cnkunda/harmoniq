import { LinearGradient } from 'expo-linear-gradient'
import type { LinearGradientProps } from 'expo-linear-gradient'

import { colors } from '@/src/constants/colors'

export interface WoodGradientProps extends Omit<LinearGradientProps, 'colors'> {
  variant?: 'background' | 'card' | 'translucentCard' | 'accentVertical'
}

const GRADIENTS = {
  background: [colors.wood[800], colors.wood[900]] as const,
  card: [colors.wood[600], colors.wood[700]] as const,
  /** Commit 154: translucent card overlay (settings cards, home hero). */
  translucentCard: [colors.translucentCardFrom, colors.translucentCardTo] as const,
  /** Commit 154: vertical amber rod (metronome pendulum). */
  accentVertical: [colors.amber.accent, colors.amber.light] as const,
}

const GRADIENT_END = {
  background: { x: 0, y: 1 },
  card: { x: 1, y: 1 },
  translucentCard: { x: 1, y: 1 },
  accentVertical: { x: 0.5, y: 1 },
} as const

export function WoodGradient({ variant = 'background', style, ...props }: WoodGradientProps) {
  return (
    <LinearGradient
      colors={[...GRADIENTS[variant]]}
      start={variant === 'accentVertical' ? { x: 0.5, y: 0 } : { x: 0, y: 0 }}
      end={GRADIENT_END[variant]}
      style={[{ flex: 1 }, style]}
      {...props}
    />
  )
}
