import { ActivityIndicator, Text, type TextProps } from 'react-native'

import { AnimatedPressable, type AnimatedPressableProps } from '@/components/AnimatedPressable'
import colors from '@/src/constants/colors'

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
type ButtonSize = 'sm' | 'md' | 'lg'

export interface ButtonProps extends Omit<AnimatedPressableProps, 'children'> {
  variant?: ButtonVariant
  size?: ButtonSize
  label: string
  loading?: boolean
  labelProps?: TextProps
  fullWidth?: boolean
}

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: 'bg-amber-accent shadow-soft-wood',
  secondary: 'border border-wood-600 bg-wood-800',
  ghost: 'border border-wood-600/50 bg-transparent',
  danger: 'border border-danger/45 bg-wood-900/60',
}

const VARIANT_TEXT: Record<ButtonVariant, string> = {
  primary: 'text-wood-900',
  secondary: 'text-cream',
  ghost: 'text-cream',
  danger: 'text-danger',
}

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: 'min-h-[40px] px-4 py-2 rounded-lg',
  md: 'min-h-[48px] px-6 py-3 rounded-xl',
  lg: 'min-h-[52px] px-8 py-3.5 rounded-xl',
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
  loading = false,
  disabled,
  labelProps,
  fullWidth = false,
  className = '',
  ...props
}: ButtonProps) {
  const isDisabled = Boolean(disabled || loading)
  const widthClass = fullWidth ? 'w-full self-stretch' : ''
  return (
    <AnimatedPressable
      {...props}
      disabled={isDisabled}
      className={`items-center justify-center ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${widthClass} ${isDisabled ? 'opacity-40' : 'active:opacity-95'} ${className}`}
      accessibilityRole="button"
      accessibilityState={{ disabled: isDisabled, busy: loading }}
    >
      {loading ? (
        <ActivityIndicator color={variant === 'primary' ? colors.wood[900] : colors.cream} size="small" />
      ) : (
        <Text
          {...labelProps}
          className={`text-center font-sans-medium ${SIZE_TEXT[size]} ${VARIANT_TEXT[variant]} ${labelProps?.className ?? ''}`}
        >
          {label}
        </Text>
      )}
    </AnimatedPressable>
  )
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
