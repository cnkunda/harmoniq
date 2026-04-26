import { Switch, Text, View } from 'react-native'

import colors from '@/src/constants/colors'

interface SettingsSwitchProps {
  label: string
  description?: string
  value: boolean
  onValueChange: (value: boolean) => void
}

export function SettingsSwitch({ label, description, value, onValueChange }: SettingsSwitchProps) {
  return (
    <View className="flex-row items-center justify-between gap-3 py-2">
      <View className="flex-1 pr-2">
        <Text className="font-sans-medium text-sm text-cream">{label}</Text>
        {description && (
          <Text className="mt-1 font-sans text-[11px] text-muted-brown leading-relaxed">{description}</Text>
        )}
      </View>
      <Switch
        value={value}
        onValueChange={onValueChange}
        trackColor={{ false: colors.wood[600], true: colors.amber.accent }}
        thumbColor={value ? colors.amber.light : colors.wood[500]}
      />
    </View>
  )
}
