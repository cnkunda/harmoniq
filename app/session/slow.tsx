import { useRouter } from 'expo-router'

import { SessionStepScreen } from '@/components/SessionStepScreen'
import { sessionHref } from '@/src/constants/sessionFlow'

export default function SlowScreen() {
  const router = useRouter()

  return (
    <SessionStepScreen
      title="Slow"
      subtitle="Bare session step 3 — slow practice pass (no playback controls in this commit)."
      showBack
      onBack={() => router.back()}
      showNext
      nextLabel="Next: Play"
      onNext={() => router.push(sessionHref('play'))}
    />
  )
}
