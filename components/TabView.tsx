import { ScrollView, Text, View } from 'react-native'

export interface TabViewProps {
  isSkeleton?: boolean
  label?: string
}

const FULL_TAB = [
  'e|--------------------------------|--------------------------------|',
  'B|-------7---10b12--10~-----------|-------7---10b12r10p7-----------|',
  'G|---7-9---7----------------------|---7-9---7------------9b11~-----|',
  'D|-9------------------------------|-9------------------------------|',
  'A|--------------------------------|--------------------------------|',
  'E|--------------------------------|--------------------------------|',
].join('\n')

const SKELETON_TAB = [
  'e|--------------------------------|--------------------------------|',
  'B|-----------10b12----------------|-----------10b12r10-------------|',
  'G|--------------------------------|----------------------9b11~-----|',
  'D|-9------------------------------|-9------------------------------|',
  'A|--------------------------------|--------------------------------|',
  'E|--------------------------------|--------------------------------|',
].join('\n')

export function TabView({ isSkeleton = false, label }: TabViewProps) {
  return (
    <View className="w-full overflow-hidden rounded-xl border border-wood-600/50 bg-wood-900 p-4">
      <View className="mb-3 flex-row items-center justify-between">
        {label && (
          <Text className="font-sans text-xs uppercase tracking-wider text-muted-brown">
            {label}
          </Text>
        )}
        <View className="rounded border border-wood-700 bg-wood-800 px-2 py-1">
          <Text className="font-sans text-[10px] uppercase tracking-wider text-muted-brown">
            {isSkeleton ? 'Skeleton' : 'Full Tab'}
          </Text>
        </View>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        <Text className="font-mono text-sm leading-relaxed text-cream/90">
          {isSkeleton ? SKELETON_TAB : FULL_TAB}
        </Text>
      </ScrollView>
    </View>
  )
}
