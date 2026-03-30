import { AlertTriangle, X } from 'lucide-react-native'
import { useState } from 'react'
import { Pressable, Text, View } from 'react-native'

import colors from '@/src/constants/colors'

type BannerVariant = 'warning' | 'error' | 'info'

export interface ErrorBannerProps {
  message: string
  variant?: BannerVariant
  action?: { label: string; onPress: () => void }
  dismissible?: boolean
  className?: string
}

const STYLES: Record<
  BannerVariant,
  { bg: string; border: string; text: string; iconColor: string }
> = {
  warning: {
    bg: 'bg-amber-accent/10',
    border: 'border-amber-accent/30',
    text: 'text-amber-light',
    iconColor: colors.amber.light,
  },
  error: {
    bg: 'bg-danger/10',
    border: 'border-danger/30',
    text: 'text-danger',
    iconColor: colors.danger,
  },
  info: {
    bg: 'bg-wood-700/50',
    border: 'border-wood-600/50',
    text: 'text-cream/80',
    iconColor: colors.muted.brown,
  },
}

export function ErrorBanner({
  message,
  variant = 'warning',
  action,
  dismissible = true,
  className = '',
}: ErrorBannerProps) {
  const [dismissed, setDismissed] = useState(false)
  const s = STYLES[variant]
  if (dismissed) return null

  return (
    <View
      className={`flex-row items-start gap-3 rounded-xl border px-4 py-3 ${s.bg} ${s.border} ${className}`}
    >
      <AlertTriangle color={s.iconColor} size={16} strokeWidth={2} style={{ marginTop: 2 }} />
      <Text className={`flex-1 font-sans text-sm leading-relaxed ${s.text}`}>{message}</Text>
      <View className="flex-row items-center gap-3">
        {action && (
          <Pressable onPress={action.onPress}>
            <Text className={`font-sans-medium text-sm underline ${s.text}`}>{action.label}</Text>
          </Pressable>
        )}
        {dismissible && (
          <Pressable onPress={() => setDismissed(true)} hitSlop={8}>
            <X color={s.iconColor} size={14} />
          </Pressable>
        )}
      </View>
    </View>
  )
}
