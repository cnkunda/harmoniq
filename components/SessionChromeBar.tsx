import { usePathname, useRouter } from 'expo-router'
import { ArrowRight } from 'lucide-react-native'
import { Text, View, useWindowDimensions } from 'react-native'
import { AnimatedPressable } from '@/components/AnimatedPressable'

import colors from '@/src/constants/colors'
import { SESSION_STEPS, sessionStepIndexFromPathname } from '@/src/constants/sessionFlow'
import { DEMO_LESSON_JOB_ID } from '@/src/demo/constants'
import { navigateToPracticePlanSlot } from '@/src/session/practicePlanNavigation'
import { useLessonStore } from '@/src/stores/lessonStore'
import { usePlanStore } from '@/src/stores/planStore'

const BRAND_MIN = 80
const ACTION_MIN = 80

/**
 * Session stack top bar: brand, step progress (active = wide pill, rest = dots), plan next action.
 * Replaces the old `SessionStepIndicator` + `SessionPlanBar` row for a single mock-aligned header.
 */
export function SessionChromeBar() {
  const pathname = usePathname()
  const router = useRouter()
  const { width } = useWindowDimensions()
  const plan = usePlanStore((s) => s.currentPlan)
  const idx = usePlanStore((s) => s.currentSlotIndex)
  const clearPlan = usePlanStore((s) => s.clearPlan)
  const saveLesson = useLessonStore((s) => s.saveLesson)
  const setLessonSectionIndex = useLessonStore((s) => s.setLessonSectionIndex)
  const lessonJobId = useLessonStore((s) => s.lesson?.job_id)
  const isDemoLesson = lessonJobId === DEMO_LESSON_JOB_ID

  const compact = width < 420
  const gapClass = compact ? 'gap-1' : 'gap-2'

  if (!pathname.includes('/session/')) return null

  const active = sessionStepIndexFromPathname(pathname)
  const showStepDots = active >= 0
  const onTuneScreen = pathname.replace(/\/+$/, '').split('/').pop() === 'tune'

  const closeSessionOrHome = () => {
    if (router.canGoBack()) router.back()
    else router.replace('/(tabs)')
  }
  const slot = plan?.slots?.[idx]
  const slots = plan?.slots
  const hasPlan = Boolean(slots?.length)
  const hasNext = hasPlan && slots != null && idx < slots.length - 1

  const goNextSection = () => {
    void (async () => {
      try {
        await navigateToPracticePlanSlot(router, { saveLesson, setLessonSectionIndex }, idx + 1)
      } catch (e) {
        console.warn('[SessionChromeBar] next section failed', e)
      }
    })()
  }

  return (
    <View className="border-b border-wood-600/20 bg-ivory">
      <View className="flex-row items-center px-4 py-3">
        <View style={{ minWidth: BRAND_MIN }}>
          <View className="flex-row flex-wrap items-center gap-2">
            <AnimatedPressable
              haptic="light"
              onPress={() => router.push('/(tabs)')}
              accessibilityRole="button"
              accessibilityLabel="Home"
            >
              <Text className="font-serif text-lg text-wood-900">Harmoniq</Text>
            </AnimatedPressable>
            {isDemoLesson ? (
              <View className="rounded-full border border-amber-accent/45 bg-amber-accent/12 px-2 py-0.5">
                <Text className="font-sans-medium text-[10px] uppercase tracking-wider text-wood-800">Demo</Text>
              </View>
            ) : null}
          </View>
        </View>

        {showStepDots ? (
          <View className={`flex-1 flex-row items-center justify-center px-1 ${gapClass}`}>
            {SESSION_STEPS.map((step, i) => (
              <View
                key={step}
                className={
                  i === active
                    ? compact
                      ? 'h-2 w-7 rounded-full bg-amber-accent'
                      : 'h-2 w-10 rounded-full bg-amber-accent'
                    : 'h-2 w-2 rounded-full bg-wood-600/35'
                }
                accessibilityElementsHidden
                importantForAccessibility="no-hide-descendants"
              />
            ))}
          </View>
        ) : (
          <View className="flex-1" />
        )}

        <View style={{ minWidth: ACTION_MIN, alignItems: 'flex-end' }}>
          {onTuneScreen ? (
            <View className="items-end gap-1">
              <AnimatedPressable
                haptic="light"
                onPress={closeSessionOrHome}
                accessibilityRole="button"
                accessibilityLabel="Close"
                hitSlop={10}
              >
                <Text className="font-sans-medium text-sm text-wood-900">Close</Text>
              </AnimatedPressable>
              {hasPlan && hasNext ? (
                <AnimatedPressable
                  haptic="light"
                  onPress={goNextSection}
                  accessibilityRole="button"
                  accessibilityLabel="Go to next section in practice plan"
                  hitSlop={10}
                  className="flex-row items-center gap-0.5"
                >
                  <Text className="font-sans-medium text-xs text-muted-light">Next section</Text>
                  <ArrowRight color={colors.muted.light} size={14} style={{ marginTop: 2 }} />
                </AnimatedPressable>
              ) : null}
            </View>
          ) : hasPlan ? (
            hasNext ? (
              <AnimatedPressable
                haptic="light"
                onPress={goNextSection}
                accessibilityRole="button"
                accessibilityLabel="Go to next section in practice plan"
                hitSlop={10}
                className="flex-row items-center gap-0.5"
              >
                <Text className="font-sans-medium text-sm text-wood-900">Next section</Text>
                <ArrowRight color={colors.wood[900]} size={16} style={{ marginTop: 2 }} />
              </AnimatedPressable>
            ) : (
              <AnimatedPressable
                haptic="light"
                onPress={() => clearPlan()}
                accessibilityRole="button"
                accessibilityLabel="Clear practice plan"
                hitSlop={10}
              >
                <Text className="font-sans-medium text-sm text-wood-900 text-right">End plan</Text>
              </AnimatedPressable>
            )
          ) : (
            <View />
          )}
        </View>
      </View>

      {hasPlan && slots != null ? (
        <Text className="border-t border-wood-600/10 px-4 py-2 font-sans text-xs text-muted-light" numberOfLines={1}>
          Plan · {idx + 1}/{slots.length}: {slot?.title ?? '—'}
        </Text>
      ) : null}
    </View>
  )
}
