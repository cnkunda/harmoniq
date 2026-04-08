import { useRouter } from 'expo-router'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Pressable, Text, View } from 'react-native'

import { AlphaTabWebView, type AlphaTabWebViewRef } from '@/components/AlphaTabWebView'
import { SessionStepScreen } from '@/components/SessionStepScreen'
import { sessionHref } from '@/src/constants/sessionFlow'
import { useLessonStore } from '@/src/stores/lessonStore'
import { readSectionTabPayloads } from '@/src/utils/lessonTabs'

type TabVariant = 'full' | 'skeleton' | 'alt'

export default function StudyScreen() {
  const router = useRouter()
  const tabRef = useRef<AlphaTabWebViewRef>(null)
  const lesson = useLessonStore((s) => s.lesson)
  const lessonSectionIndex = useLessonStore((s) => s.lessonSectionIndex)

  const section = lesson?.sections?.[lessonSectionIndex]
  const tabs = useMemo(() => readSectionTabPayloads(section), [section])

  const [variant, setVariant] = useState<TabVariant>('full')

  useEffect(() => {
    setVariant(tabs.full ? 'full' : tabs.skeleton ? 'skeleton' : tabs.alt ? 'alt' : 'full')
  }, [lesson?.job_id, lessonSectionIndex, tabs.alt, tabs.full, tabs.skeleton])

  const gp5Base64 = useMemo(() => {
    if (variant === 'full') return tabs.full ?? null
    if (variant === 'skeleton') return tabs.skeleton ?? null
    return tabs.alt ?? null
  }, [variant, tabs.alt, tabs.full, tabs.skeleton])

  const variantButton = (v: TabVariant, label: string) => {
    const disabled = v === 'full' ? !tabs.full : v === 'skeleton' ? !tabs.skeleton : !tabs.alt
    return (
      <Pressable
        onPress={() => setVariant(v)}
        disabled={disabled}
        className={`rounded-full border px-3 py-1.5 ${
          variant === v ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600 bg-wood-800'
        } ${disabled ? 'opacity-40' : ''}`}
        accessibilityRole="button"
        accessibilityState={{ selected: variant === v }}
      >
        <Text
          className={`font-sans text-xs ${variant === v ? 'text-amber-light' : 'text-cream'}`}
        >
          {label}
        </Text>
      </Pressable>
    )
  }

  return (
    <SessionStepScreen
      title="Study"
      subtitle="AlphaTab in WebView: switch full vs skeleton GP5 (same section). External links stay blocked in the harness."
      showBack
      onBack={() => router.back()}
      showNext
      nextLabel="Next: Slow"
      onNext={() => router.push(sessionHref('slow'))}
    >
      <View className="mt-3 flex-row flex-wrap items-center gap-2">
        {variantButton('full', 'Full tab')}
        {variantButton('skeleton', 'Skeleton')}
        {tabs.alt ? variantButton('alt', 'Alt position') : null}
        <Pressable
          onPress={() => tabRef.current?.scrollToBar(0)}
          className="rounded-full border border-wood-500 bg-wood-800 px-3 py-1.5"
          accessibilityRole="button"
        >
          <Text className="font-sans text-xs text-cream">Scroll to bar 0</Text>
        </Pressable>
      </View>

      <View className="mt-3 min-h-[300px] flex-1">
        <AlphaTabWebView ref={tabRef} gp5Base64={gp5Base64} style={{ flex: 1 }} />
      </View>
    </SessionStepScreen>
  )
}
