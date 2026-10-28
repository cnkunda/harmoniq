import { Platform, Switch, type SwitchProps } from 'react-native'

import { colors } from '@/src/constants/colors'

export interface ThemedSwitchProps extends SwitchProps {
  trackColor?: { false?: string; true?: string }
}

/**
 * React Native Web ignores `thumbColor` when the switch is on and falls back
 * to its default teal. Pass the web-only `activeThumbColor` explicitly so the
 * control stays inside the Harmoniq palette on every platform.
 */
export function ThemedSwitch({ value, trackColor, thumbColor, ...props }: ThemedSwitchProps) {
  const resolvedTrack = trackColor ?? {
    false: colors.wood[600],
    true: colors.amber.accent,
  }
  const resolvedThumb = thumbColor ?? (value ? colors.amber.light : colors.wood[500])
  const webProps =
    Platform.OS === 'web'
      ? ({ activeThumbColor: value ? colors.amber.light : colors.wood[500] } as unknown as SwitchProps)
      : {}

  return (
    <Switch
      {...props}
      value={value}
      trackColor={resolvedTrack}
      thumbColor={resolvedThumb}
      {...webProps}
    />
  )
}
