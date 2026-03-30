import { LinearGradient } from 'expo-linear-gradient'
import type { LinearGradientProps } from 'expo-linear-gradient'

export interface WoodGradientProps extends Omit<LinearGradientProps, 'colors'> {
  variant?: 'background' | 'card'
}

const GRADIENTS = {
  background: ['#3D2317', '#2C1810'] as const,
  card: ['#4A3728', '#3D2B1F'] as const,
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
