import { Text, View } from 'react-native'

import type { TabNoteQueueEntry } from '@/src/session/usePlayCapture'

const VISIBLE = 7
const CENTER = Math.floor(VISIBLE / 2)

/** Matches ListenStemPanel choice-chip inactive / active pattern. */
const CHIP_OFF = 'items-center justify-center rounded-full border border-wood-600/40 bg-wood-900/10 px-2 py-1.5'
const CHIP_ON =
  'min-w-[52px] items-center justify-center rounded-full border border-amber-accent bg-amber-accent px-3 py-2'

type PlayTargetNoteQueueProps = {
  queue: TabNoteQueueEntry[]
  /** Whether stem capture is active — dims future slots slightly when false. */
  isActive: boolean
}

/**
 * Rolling window of tab targets (`noteEvent`). Center = **current** pitch target (B2: advances note-by-note).
 */
export function PlayTargetNoteQueue({ queue, isActive }: PlayTargetNoteQueueProps) {
  const n = queue.length
  const currentIndex = Math.max(0, n - 1)

  const slots: (TabNoteQueueEntry | null)[] = []
  for (let i = -CENTER; i <= CENTER; i += 1) {
    const idx = currentIndex + i
    if (idx >= 0 && idx < n) {
      slots.push(queue[idx]!)
    } else {
      slots.push(null)
    }
  }

  return (
    <View className="rounded-xl border border-wood-600/40 bg-cream-dark/50 p-4">
      <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-accent">Pitch targets</Text>
      <Text className="mt-1 font-sans text-xs leading-relaxed text-muted-brown">
        Each new tab note becomes the pitch you score against — not one static target. Latest note is highlighted.
      </Text>

      <View className="mt-3 flex-row items-center justify-between border-b border-wood-600/25 pb-2">
        <Text className="font-sans text-[11px] text-wood-900">Current from tab</Text>
        <Text className="font-mono text-[11px] text-muted-brown">
          {n > 0 ? `${n} note${n === 1 ? '' : 's'} buffered` : 'Waiting for tab…'}
        </Text>
      </View>

      <View className="mt-3 flex-row items-end justify-center gap-1.5">
        {slots.map((note, displayIdx) => {
          if (!note) {
            return <View key={`e-${displayIdx}`} className="h-12 w-8 shrink-0" />
          }
          const offset = displayIdx - CENTER
          const isCurrent = offset === 0
          const opacity = isCurrent ? 1 : Math.max(0.45, 1 - Math.abs(offset) * 0.18)
          return (
            <View
              key={`${note.midi}-${note.beat}-${displayIdx}`}
              className={isCurrent ? CHIP_ON : CHIP_OFF}
              style={{
                opacity,
                minHeight: isCurrent ? 52 : 40,
              }}
            >
              <Text
                className={`font-mono font-semibold ${isCurrent ? 'text-lg text-wood-900' : 'text-sm text-wood-900'}`}
              >
                {note.label}
              </Text>
              {isCurrent && note.string != null && note.fret != null ? (
                <Text className="mt-0.5 font-mono text-[10px] text-wood-900/80">
                  s{note.string} · f{note.fret}
                </Text>
              ) : null}
              {isCurrent ? (
                <Text className="mt-1 font-sans-medium text-[9px] uppercase tracking-wide text-wood-900/90">Now</Text>
              ) : null}
            </View>
          )
        })}
      </View>

      <Text className="mt-3 text-center font-sans text-[11px] text-muted-brown">
        {!isActive
          ? 'Start capture, then play — targets advance with every note the tab sends.'
          : 'As the piece moves, the highlighted target updates note-by-note; beats score against it.'}
      </Text>
    </View>
  )
}
