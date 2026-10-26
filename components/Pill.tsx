import type { ReactNode } from 'react'
import { Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import {
  PILL_ACCENT,
  PILL_BASE,
  PILL_DANGER,
  PILL_LABEL,
  PILL_LABEL_XS,
  PILL_LIGHT,
  PILL_NEUTRAL,
  PILL_SUCCESS,
  PILL_TEXT_ACCENT,
  PILL_TEXT_DANGER,
  PILL_TEXT_LIGHT,
  PILL_TEXT_NEUTRAL,
  PILL_TEXT_SUCCESS,
} from '@/src/constants/uiTokens'

export type PillVariant = 'neutral' | 'accent' | 'success' | 'danger' | 'light'
export type PillSize = 'xs' | 'sm'

export interface PillProps {
  children: ReactNode
  variant?: PillVariant
  size?: PillSize
  icon?: ReactNode
  className?: string
  textClassName?: string
  onPress?: () => void
  disabled?: boolean
  accessibilityLabel?: string
  haptic?: 'light' | 'medium' | 'heavy' | 'none'
}

const VARIANT_CLASSES: Record<PillVariant, string> = {
  neutral: PILL_NEUTRAL,
  accent: PILL_ACCENT,
  success: PILL_SUCCESS,
  danger: PILL_DANGER,
  light: PILL_LIGHT,
}

const VARIANT_TEXT: Record<PillVariant, string> = {
  neutral: PILL_TEXT_NEUTRAL,
  accent: PILL_TEXT_ACCENT,
  success: PILL_TEXT_SUCCESS,
  danger: PILL_TEXT_DANGER,
  light: PILL_TEXT_LIGHT,
}

/** Small rounded status/metadata label used across the app. */
export function Pill({
  children,
  variant = 'neutral',
  size = 'sm',
  icon,
  className = '',
  textClassName = '',
  onPress,
  disabled,
  accessibilityLabel,
  haptic = 'light',
}: PillProps) {
  const content = (
    <>
      {icon}
      {typeof children === 'string' ? (
        <Text
          className={`${size === 'xs' ? PILL_LABEL_XS : PILL_LABEL} ${VARIANT_TEXT[variant]} ${textClassName}`}
        >
          {children}
        </Text>
      ) : (
        children
      )}
    </>
  )

  if (onPress) {
    return (
      <AnimatedPressable
        onPress={onPress}
        disabled={disabled}
        haptic={haptic}
        accessibilityRole="button"
        accessibilityLabel={accessibilityLabel}
        accessibilityState={{ disabled: Boolean(disabled) }}
        className={`${PILL_BASE} ${VARIANT_CLASSES[variant]} ${disabled ? 'opacity-50' : 'active:opacity-90'} ${className}`}
      >
        {content}
      </AnimatedPressable>
    )
  }

  return <View className={`${PILL_BASE} ${VARIANT_CLASSES[variant]} ${className}`}>{content}</View>
}
