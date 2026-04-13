import type { StyleProp, ViewStyle } from 'react-native'
import type { NoteEventMessage } from '@/types/tabMessage'

export type TabViewportProps = {
  gp5Base64?: string | null
  audioSrc?: string | null
  transposeSemitones?: number
  style?: StyleProp<ViewStyle>
  onReady?: () => void
  onError?: (message: string) => void
  onNoteEvent?: (evt: NoteEventMessage) => void
  onScoreSeekMs?: (positionMs: number) => void
}
