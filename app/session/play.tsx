import { useRouter } from 'expo-router'

import { SessionStepScreen } from '@/components/SessionStepScreen'
import { sessionHref } from '@/src/constants/sessionFlow'

export default function PlayScreen() {
  const router = useRouter()

  return (
    <SessionStepScreen
      title="Play"
      subtitle="Bare session step 4 — play along at tempo (no mic UI in this commit)."
      showBack
      onBack={() => router.back()}
      showNext
      nextLabel="Next: Review"
      onNext={() => router.push(sessionHref('review'))}
    />
  )
}
