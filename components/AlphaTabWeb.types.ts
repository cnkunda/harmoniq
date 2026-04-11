import type { StyleProp, ViewStyle } from 'react-native'

import type { NoteEventMessage, TabThemeColors } from '@/types/tabMessage'

export type AlphaTabWebProps = {
  gp5Base64?: string | null
  audioSrc?: string | null
  transposeSemitones?: number
  /** Merged over README / harness defaults (`TAB_HARNESS_THEME`). */
  theme?: Partial<TabThemeColors>
  style?: StyleProp<ViewStyle>
  onReady?: () => void
  onError?: (message: string) => void
  onNoteEvent?: (evt: NoteEventMessage) => void
}
