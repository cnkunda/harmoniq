import { LinearGradient } from 'expo-linear-gradient'
import type { LinearGradientProps } from 'expo-linear-gradient'

import colors from '@/src/constants/colors'

export interface WoodGradientProps extends Omit<LinearGradientProps, 'colors'> {
  variant?: 'background' | 'card'
}

const GRADIENTS = {
  background: [colors.wood[800], colors.wood[900]] as const,
  card: [colors.wood[600], colors.wood[700]] as const,
}

export function WoodGradient({ variant = 'background', style, ...props }: WoodGradientProps) {
  return (
    <LinearGradient
      colors={[...GRADIENTS[variant]]}
      start={{ x: 0, y: 0 }}
      end={variant === 'card' ? { x: 1, y: 1 } : { x: 0, y: 1 }}
      style={[{ flex: 1 }, style]}
      {...props}
    />
  )
}
