import type { ReactNode } from 'react'
import { Text, View } from 'react-native'
import Toast, { type BaseToastProps } from 'react-native-toast-message'
import { AlertTriangle, Check, Info } from 'lucide-react-native'

import colors from '@/src/constants/colors'

function WoodToast({
  text1,
  icon,
}: BaseToastProps & { icon: ReactNode }) {
  return (
    <View className="mx-4 flex-row items-center gap-3 rounded-2xl border border-wood-600/50 bg-wood-700 px-4 py-3.5">
      {icon}
      <Text className="flex-1 font-sans text-sm text-cream">{text1}</Text>
    </View>
  )
}

export const toastConfig = {
  success: (props: BaseToastProps) => (
    <WoodToast {...props} icon={<Check color={colors.success} size={18} />} />
  ),
  error: (props: BaseToastProps) => (
    <WoodToast {...props} icon={<AlertTriangle color={colors.danger} size={18} />} />
  ),
  info: (props: BaseToastProps) => (
    <WoodToast {...props} icon={<Info color={colors.amber.accent} size={18} />} />
  ),
}

export const toast = {
  success: (text: string) =>
    Toast.show({
      type: 'success',
      text1: text,
      visibilityTime: 2500,
      position: 'bottom',
    }),
  error: (text: string) =>
    Toast.show({
      type: 'error',
      text1: text,
      visibilityTime: 3500,
      position: 'bottom',
    }),
  info: (text: string) =>
    Toast.show({
      type: 'info',
      text1: text,
      visibilityTime: 2200,
      position: 'bottom',
    }),
}
