import { useRouter, usePathname } from 'expo-router'
import { Text, View } from 'react-native'
import { AnimatedPressable } from '@/components/AnimatedPressable'

import { navigateToPracticePlanSlot } from '@/src/session/practicePlanNavigation'
import { useLessonStore } from '@/src/stores/lessonStore'
import { usePlanStore } from '@/src/stores/planStore'

/** Commit 70: advance ordered practice plan while inside `/session/*`.
 *  Superseded by `SessionChromeBar` in `app/session/_layout.tsx`; kept for imports/tests if needed.
 */
export function SessionPlanBar() {
  const pathname = usePathname()
  const router = useRouter()
  const plan = usePlanStore((s) => s.currentPlan)
  const idx = usePlanStore((s) => s.currentSlotIndex)
  const clearPlan = usePlanStore((s) => s.clearPlan)
  const saveLesson = useLessonStore((s) => s.saveLesson)
  const setLessonSectionIndex = useLessonStore((s) => s.setLessonSectionIndex)

  if (!plan?.slots?.length) return null
  if (!pathname.includes('/session/')) return null

  const slot = plan.slots[idx]
  const hasNext = idx < plan.slots.length - 1

  return (
    <View className="border-b border-wood-600/25 bg-ivory px-4 py-2">
      <Text className="font-sans text-xs text-muted-brown" numberOfLines={1}>
        Plan · {idx + 1}/{plan.slots.length}: {slot?.title ?? '—'}
      </Text>
      {hasNext ? (
        <AnimatedPressable
          haptic="light"
          onPress={() => {
            void (async () => {
              try {
                await navigateToPracticePlanSlot(router, { saveLesson, setLessonSectionIndex }, idx + 1)
              } catch (e) {
                console.warn('[SessionPlanBar] next section failed', e)
              }
            })()
          }}
          className="mt-2 self-start rounded-lg border border-amber-accent/50 bg-amber-accent/15 px-3 py-2"
          accessibilityRole="button"
          accessibilityLabel="Go to next section in practice plan"
        >
          <Text className="font-sans-medium text-sm text-wood-900">Next section</Text>
        </AnimatedPressable>
      ) : (
        <AnimatedPressable
          haptic="light"
          onPress={() => clearPlan()}
          className="mt-2 self-start rounded-lg border border-wood-600/40 px-3 py-2"
          accessibilityRole="button"
          accessibilityLabel="Clear practice plan"
        >
          <Text className="font-sans-medium text-sm text-wood-900">End plan</Text>
        </AnimatedPressable>
      )}
    </View>
  )
}
