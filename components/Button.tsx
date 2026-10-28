import type { ReactNode } from 'react'
import { ActivityIndicator, Text, View, type TextProps } from 'react-native'

import { AnimatedPressable, type AnimatedPressableProps } from '@/components/AnimatedPressable'
import {
  BTN_BASE,
  BTN_DANGER,
  BTN_DISABLED,
  BTN_DISABLED_TEXT,
  BTN_GHOST,
  BTN_PRIMARY,
  BTN_SECONDARY,
  BTN_SM_BASE,
} from '@/src/constants/buttonStyles'
import { colors } from '@/src/constants/colors'

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
type ButtonSize = 'sm' | 'md' | 'lg'

export interface ButtonProps extends Omit<AnimatedPressableProps, 'children'> {
  variant?: ButtonVariant
  size?: ButtonSize
  label: string
  icon?: ReactNode
  loading?: boolean
  labelProps?: TextProps
  fullWidth?: boolean
  /** Layout classes for the outer wrapper (e.g. flex-1 in a row). */
  containerClassName?: string
}

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: BTN_PRIMARY,
  secondary: BTN_SECONDARY,
  ghost: BTN_GHOST,
  danger: BTN_DANGER,
}

const VARIANT_TEXT: Record<ButtonVariant, string> = {
  primary: 'text-wood-900',
  secondary: 'text-cream',
  ghost: 'text-cream',
  danger: 'text-danger',
}

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: BTN_SM_BASE,
  md: BTN_BASE,
  lg: `${BTN_BASE} min-h-[52px] px-8 py-3.5`,
}

const SIZE_TEXT: Record<ButtonSize, string> = {
  sm: 'text-sm',
  md: 'text-[15px]',
  lg: 'text-base',
}

export function Button({
  variant = 'primary',
  size = 'md',
  label,
  icon,
  loading = false,
  disabled,
  labelProps,
  fullWidth = false,
  containerClassName,
  className = '',
  ...props
}: ButtonProps) {
  const isDisabled = Boolean(disabled || loading)
  const showDisabledStyles = Boolean(disabled) && !loading
  const surfaceClass = showDisabledStyles
    ? BTN_DISABLED
    : `${VARIANT_CLASSES[variant]} ${isDisabled ? 'opacity-90' : 'active:opacity-95'}`
  const inner = (
    <AnimatedPressable
      {...props}
      disabled={isDisabled}
      className={`${SIZE_CLASSES[size]} ${surfaceClass} ${className}`}
      accessibilityRole="button"
      accessibilityState={{ disabled: isDisabled, busy: loading }}
    >
      {loading ? (
        <ActivityIndicator color={variant === 'primary' ? colors.wood[900] : colors.cream} size="small" />
      ) : (
        <>
          {icon}
          <Text
            {...labelProps}
            className={`text-center font-sans-medium ${SIZE_TEXT[size]} ${
              showDisabledStyles ? BTN_DISABLED_TEXT : VARIANT_TEXT[variant]
            } ${labelProps?.className ?? ''}`}
          >
            {label}
          </Text>
        </>
      )}
    </AnimatedPressable>
  )

  if (containerClassName) {
    return <View className={containerClassName}>{inner}</View>
  }
  if (fullWidth) {
    return <View className="w-full self-stretch">{inner}</View>
  }
  return inner
}

export function PrimaryButton(props: Omit<ButtonProps, 'variant'>) {
  return <Button {...props} variant="primary" />
}

export function SecondaryButton(props: Omit<ButtonProps, 'variant'>) {
  return <Button {...props} variant="secondary" />
}

export function GhostButton(props: Omit<ButtonProps, 'variant'>) {
  return <Button {...props} variant="ghost" />
}

export function DangerButton(props: Omit<ButtonProps, 'variant'>) {
  return <Button {...props} variant="danger" />
}
