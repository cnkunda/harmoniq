import { ListMusic, Music, type LucideIcon } from 'lucide-react-native'
import { Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { colors } from '@/src/constants/colors'
import type { HomePracticeMode } from '@/src/stores/sessionPrefsStore'

export interface PracticeModeTabsProps {
  mode: HomePracticeMode
  onChange: (mode: HomePracticeMode) => void
}

function ModeTab({
  selected,
  label,
  Icon,
  onPress,
}: {
  selected: boolean
  label: string
  Icon: LucideIcon
  onPress: () => void
}) {
  return (
    <AnimatedPressable
      onPress={onPress}
      haptic="light"
      accessibilityRole="tab"
      accessibilityState={{ selected }}
      accessibilityLabel={label}
      className={`relative min-h-[52px] flex-1 flex-row items-center justify-center gap-2 rounded-t-2xl border border-b-0 px-4 md:flex-none ${
        selected ? 'border-wood-600/50 bg-wood-800/55' : 'border-transparent bg-wood-900/30'
      }`}
    >
      {selected ? (
        <View className="absolute left-0 right-0 top-0 h-[3px] rounded-t-2xl bg-amber-accent" />
      ) : null}
      <Icon color={selected ? colors.cream : colors.muted.brown} size={18} strokeWidth={2} />
      <Text className={`font-sans-medium text-[15px] ${selected ? 'text-cream' : 'text-muted-brown'}`}>
        {label}
      </Text>
    </AnimatedPressable>
  )
}

/** Home practice-mode switch styled as connected tabs above the suggestion card. */
export function PracticeModeTabs({ mode, onChange }: PracticeModeTabsProps) {
  return (
    <View accessibilityRole="tablist" className="mt-2 flex-row gap-1 md:self-start">
      <ModeTab
        selected={mode === 'single'}
        label="Practice a song"
        Icon={Music}
        onPress={() => onChange('single')}
      />
      <ModeTab
        selected={mode === 'plan'}
        label="Follow a plan"
        Icon={ListMusic}
        onPress={() => onChange('plan')}
      />
    </View>
  )
}
