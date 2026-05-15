import { Text, View } from 'react-native'
import { AnimatedPressable } from '@/components/AnimatedPressable'

import colors from '@/src/constants/colors'
import { Check } from 'lucide-react-native'

export type FormCheckboxProps = {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  label: string
  disabled?: boolean
  /** Text color / tone; use `text-cream` on dark settings cards. */
  labelClassName?: string
  /** `wood` = unchecked box fits `bg-wood-800` cards; default matches ivory/session surfaces. */
  surface?: 'ivory' | 'wood'
}

export function FormCheckbox({
  checked,
  onCheckedChange,
  label,
  disabled = false,
  labelClassName,
  surface = 'ivory',
}: FormCheckboxProps) {
  const labelTone = labelClassName ?? 'text-wood-900'
  const onDarkSurface = surface === 'wood' || Boolean(labelClassName?.includes('text-cream'))
  const checkColor = onDarkSurface ? colors.cream : colors.wood[900]

  const boxTone = checked
    ? 'border-amber-accent bg-amber-accent/25'
    : surface === 'wood'
      ? 'border-wood-600/50 bg-wood-900/40'
      : 'border-wood-600/60 bg-cream-dark/50'

  return (
    <AnimatedPressable
      haptic="none"
      onPress={() => !disabled && onCheckedChange(!checked)}
      disabled={disabled}
      className={`flex-row items-start gap-3 ${disabled ? 'opacity-50' : ''}`}
      accessibilityRole="checkbox"
      accessibilityState={{ checked, disabled }}
    >
      <View className={`mt-0.5 h-5 w-5 items-center justify-center rounded border ${boxTone}`}>
        {checked ? <Check color={checkColor} size={14} strokeWidth={2.5} /> : null}
      </View>
      <Text className={`flex-1 font-sans text-sm leading-5 ${labelTone}`}>{label}</Text>
    </AnimatedPressable>
  )
}
