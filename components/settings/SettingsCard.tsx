import { LinearGradient } from 'expo-linear-gradient'
import { type LucideIcon } from 'lucide-react-native'
import { Text, View } from 'react-native'

import colors from '@/src/constants/colors'

interface SettingsCardProps {
  title: string
  description?: string
  icon?: LucideIcon
  children: React.ReactNode
  variant?: 'default' | 'gradient'
}

export function SettingsCard({
  title,
  description,
  icon: Icon,
  children,
  variant = 'default',
}: SettingsCardProps) {
  if (variant === 'gradient') {
    return (
      <LinearGradient
        colors={['rgba(74, 55, 40, 0.98)', 'rgba(44, 24, 16, 0.99)']}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        className="mb-6 overflow-hidden rounded-2xl border border-wood-600/50"
      >
        <View className="relative p-6">
          {/* Amber accent strip */}
          <View className="absolute left-0 top-0 bottom-0 w-1 bg-amber-accent/40" />

          <View className="flex-row items-start gap-4">
            {Icon && (
              <View className="h-12 w-12 items-center justify-center rounded-full bg-wood-800/60 border border-wood-600">
                <Icon color={colors.amber.accent} size={24} strokeWidth={2} />
              </View>
            )}
            <View className="flex-1">
              <Text className="font-serif text-xl text-cream">{title}</Text>
              {description && (
                <Text className="mt-1 font-sans text-sm text-muted-brown leading-relaxed">
                  {description}
                </Text>
              )}
            </View>
          </View>

          <View className="mt-4">{children}</View>
        </View>
      </LinearGradient>
    )
  }

  return (
    <View className="mb-6 overflow-hidden rounded-xl border border-wood-600/50 bg-wood-800/80">
      <View className="p-4">
        <View className="flex-row items-center gap-3 mb-4">
          {Icon && (
            <View className="h-10 w-10 items-center justify-center rounded-full bg-wood-700">
              <Icon color={colors.amber.accent} size={20} strokeWidth={2} />
            </View>
          )}
          <View className="flex-1">
            <Text className="font-sans-medium text-sm uppercase tracking-wide text-amber-light">
              {title}
            </Text>
            {description && (
              <Text className="mt-0.5 font-sans text-xs text-muted-brown">{description}</Text>
            )}
          </View>
        </View>
        {children}
      </View>
    </View>
  )
}
