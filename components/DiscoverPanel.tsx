import type { LucideIcon } from 'lucide-react-native'
import { Music } from 'lucide-react-native'
import { ActivityIndicator, ScrollView, Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import colors from '@/src/constants/colors'

/** A single row in a populated panel. */
export interface DiscoverPanelItem {
  key: string
  /** Primary line (e.g. song title). Truncates with ellipsis. */
  title: string
  /** Secondary muted line (e.g. artist). Truncates with ellipsis. */
  subtitle: string
  /** Optional third line (e.g. a recommendation reason). */
  caption?: string
  /** Highlights the row as the active selection. */
  selected?: boolean
  onPress: () => void
}

/** Empty-state configuration shown when there are no items. */
export interface DiscoverPanelEmpty {
  Icon: LucideIcon
  /** 1–2 lines of explanatory copy. */
  message: string
  /** Label for the concrete next-action link. */
  ctaLabel: string
  onCta: () => void
}

export interface DiscoverPanelProps {
  Icon: LucideIcon
  title: string
  subtitle: string
  loading?: boolean
  /** Loading text shown next to the spinner. */
  loadingLabel?: string
  items?: DiscoverPanelItem[]
  emptyState: DiscoverPanelEmpty
  /** Max height of the scrollable list body. */
  listMaxHeight?: number
  className?: string
}

/**
 * Decorative-icon wrapper: hides the icon from assistive tech (it's purely
 * visual and always paired with a text label).
 */
function DecorativeIcon({ children }: { children: React.ReactNode }) {
  return (
    <View importantForAccessibility="no-hide-descendants" accessibilityElementsHidden aria-hidden>
      {children}
    </View>
  )
}

/** Small square album-art placeholder (no artwork exists in the data). */
function ArtPlaceholder() {
  return (
    <DecorativeIcon>
      <View className="h-10 w-10 items-center justify-center rounded-md border border-wood-700/50 bg-wood-900/60">
        <Music size={16} color={colors.amber.accent} />
      </View>
    </DecorativeIcon>
  )
}

function PanelRow({ item }: { item: DiscoverPanelItem }) {
  const { selected } = item
  return (
    <AnimatedPressable
      onPress={item.onPress}
      haptic="light"
      accessibilityRole="button"
      accessibilityLabel={`${item.title} — ${item.subtitle}`}
      accessibilityState={{ selected: !!selected }}
      className={`flex-row items-center gap-3 rounded-lg border px-3 py-2.5 ${
        selected ? 'border-amber-accent bg-amber-accent/15' : 'border-wood-600/45 bg-wood-900/40'
      }`}
    >
      <ArtPlaceholder />
      <View className="flex-1">
        <Text
          numberOfLines={1}
          className={`font-sans-medium text-sm ${selected ? 'text-amber-accent' : 'text-cream'}`}
        >
          {item.title}
        </Text>
        <Text numberOfLines={1} className="mt-0.5 font-sans text-xs text-cream/60">
          {item.subtitle}
        </Text>
        {item.caption ? (
          <Text numberOfLines={2} className="mt-1 font-sans text-xs leading-relaxed text-cream/70">
            {item.caption}
          </Text>
        ) : null}
      </View>
    </AnimatedPressable>
  )
}

function PanelEmpty({ Icon, message, ctaLabel, onCta }: DiscoverPanelEmpty) {
  return (
    <View className="mt-4 items-center gap-3 px-2 py-2">
      <DecorativeIcon>
        <View className="h-12 w-12 items-center justify-center rounded-full border border-wood-700/50 bg-wood-800">
          <Icon size={20} color={colors.amber.accent} strokeWidth={1.5} />
        </View>
      </DecorativeIcon>
      <Text className="text-center font-sans text-sm leading-relaxed text-muted-brown">{message}</Text>
      <AnimatedPressable
        onPress={onCta}
        haptic="medium"
        accessibilityRole="button"
        accessibilityLabel={ctaLabel}
        className="rounded-md px-2 py-1"
      >
        <Text className="font-sans-medium text-sm text-amber-accent underline">{ctaLabel}</Text>
      </AnimatedPressable>
    </View>
  )
}

/**
 * Reusable Discover card: a titled panel that renders either a loading spinner,
 * a scrollable list of compact song rows, or an actionable empty state.
 *
 * Used by both the "Recommended songs" and "Your Library" sections so the two
 * cards share one implementation instead of duplicated markup.
 */
export function DiscoverPanel({
  Icon,
  title,
  subtitle,
  loading = false,
  loadingLabel = 'Loading…',
  items,
  emptyState,
  listMaxHeight = 260,
  className = '',
}: DiscoverPanelProps) {
  const hasItems = !!items && items.length > 0

  return (
    <View className={`flex-1 rounded-xl border border-wood-600/50 bg-wood-800/80 p-4 shadow-soft-wood ${className}`}>
      {/* Header */}
      <View className="flex-row items-center gap-2">
        <DecorativeIcon>
          <Icon size={16} color={colors.amber.accent} />
        </DecorativeIcon>
        <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-accent">{title}</Text>
      </View>
      <Text numberOfLines={1} className="mt-1 font-sans text-xs text-cream/70">
        {subtitle}
      </Text>

      {/* Body */}
      {loading ? (
        <View className="mt-3 flex-row items-center gap-2">
          <ActivityIndicator color={colors.amber.accent} size="small" />
          <Text className="font-sans text-sm text-cream/70">{loadingLabel}</Text>
        </View>
      ) : hasItems ? (
        <ScrollView
          className="mt-3"
          style={{ maxHeight: listMaxHeight }}
          nestedScrollEnabled
          showsVerticalScrollIndicator={false}
          contentContainerStyle={{ gap: 8 }}
        >
          {items!.map((item) => (
            <PanelRow key={item.key} item={item} />
          ))}
        </ScrollView>
      ) : (
        <PanelEmpty {...emptyState} />
      )}
    </View>
  )
}
