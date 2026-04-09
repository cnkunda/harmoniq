import { Stack } from 'expo-router'
import { View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { SessionStepIndicator } from '@/components/SessionStepIndicator'

export default function SessionLayout() {
  return (
    <SafeAreaView className="flex-1 bg-ivory" edges={['top', 'left', 'right']}>
      <SessionStepIndicator />
      <View className="flex-1">
        <Stack screenOptions={{ headerShown: false, animation: 'slide_from_right' }} />
      </View>
    </SafeAreaView>
  )
}
