import { useRouter } from 'expo-router'

import { SessionStepScreen } from '@/components/SessionStepScreen'
import { sessionHref } from '@/src/constants/sessionFlow'

export default function StudyScreen() {
  const router = useRouter()

  return (
    <SessionStepScreen
      title="Study"
      subtitle="Bare session step 2 — review what to work on (no tab UI in this commit)."
      showBack
      onBack={() => router.back()}
      showNext
      nextLabel="Next: Slow"
      onNext={() => router.push(sessionHref('slow'))}
    />
  )
}
