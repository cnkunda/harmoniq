import type { StyleProp, ViewStyle } from 'react-native'

export type TabViewportProps = {
  gp5Base64?: string | null
  style?: StyleProp<ViewStyle>
  onReady?: () => void
  onError?: (message: string) => void
}
