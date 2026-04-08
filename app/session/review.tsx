import { useRouter } from 'expo-router'

import { SessionStepScreen } from '@/components/SessionStepScreen'

export default function ReviewScreen() {
  const router = useRouter()

  const finish = () => {
    router.replace('/(tabs)')
  }

  return (
    <SessionStepScreen
      title="Review"
      subtitle="Bare session step 5 — wrap-up placeholder (no coach summary UI in this commit)."
      showBack
      onBack={() => router.back()}
      showNext
      nextLabel="Done"
      onNext={finish}
    />
  )
}
