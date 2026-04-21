import { Ghost } from 'lucide-react-native'
import { Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import colors from '@/src/constants/colors'

export type GhostPlayerControlProps = {
  playWithGhost: boolean
  onTogglePlayWithGhost: (next: boolean) => void
  /** ISO date string from latest ghost row, or null. */
  ghostRecordedAtLabel: string | null
  /** When false, toggle is disabled (no ghost for this section). */
  hasGhost: boolean
}

function formatGhostDate(iso: string | null): string {
  if (!iso || !iso.trim()) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso.trim()
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

/**
 * Commit 75 — compact control below Play transport: hear your last ghost take while recording.
 */
export function GhostPlayerControl({
  playWithGhost,
  onTogglePlayWithGhost,
  ghostRecordedAtLabel,
  hasGhost,
}: GhostPlayerControlProps) {
  const disabled = !hasGhost
  const subtitle = disabled
    ? 'Record a ghost take on Review (flag after capture) to hear it on the next Play session.'
    : playWithGhost
      ? `Ghost from ${formatGhostDate(ghostRecordedAtLabel)} — mixed at 20% while you record.`
      : 'Enable to mix your saved ghost take at 20% under the backing track while recording.'

  return (
    <View className="rounded-xl border border-wood-600/40 bg-cream-dark/35 px-3 py-2">
      <Text className="mb-2 font-sans-medium text-[10px] uppercase tracking-[0.12em] text-amber-accent">
        Ghost player
      </Text>
      <View className="flex-row items-center justify-between gap-3">
        <View className="min-w-0 flex-1 flex-row items-center gap-2">
          <Ghost size={18} color={colors.amber.accent} strokeWidth={2} />
          <Text className="font-sans-medium text-sm text-wood-900">Play with ghost</Text>
        </View>
        <AnimatedPressable
          accessibilityRole="switch"
          accessibilityState={{ checked: playWithGhost, disabled }}
          disabled={disabled}
          onPress={() => {
            if (!disabled) onTogglePlayWithGhost(!playWithGhost)
          }}
          className={`rounded-full px-3 py-1.5 ${disabled ? 'bg-wood-700/60' : playWithGhost ? 'bg-amber-accent/90' : 'border border-wood-600/50 bg-wood-900/20'}`}
        >
          <Text
            className={`font-sans-medium text-xs ${disabled ? 'text-muted-brown' : playWithGhost ? 'text-wood-900' : 'text-muted-brown'}`}
          >
            {disabled ? 'Off' : playWithGhost ? 'On' : 'Off'}
          </Text>
        </AnimatedPressable>
      </View>
      <Text className="mt-2 font-sans text-[11px] leading-snug text-muted-brown">{subtitle}</Text>
    </View>
  )
}
