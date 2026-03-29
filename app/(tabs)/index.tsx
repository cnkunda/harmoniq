import { Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

export default function HomeScreen() {
  return (
    <SafeAreaView className="flex-1 bg-wood-900">
      <View className="flex-1 items-center justify-center px-6">
        <Text className="text-4xl font-serif text-amber-accent">Harmoniq</Text>
        <Text className="mt-4 text-center font-sans text-cream text-base">
          NativeWind + fonts sanity check (Playfair / DM Sans / JetBrains Mono below).
        </Text>
        <Text className="mt-2 text-center font-serif-italic text-amber-light text-sm">Playfair Italic - design token check</Text>
        <Text className="mt-2 font-serif-bold text-cream text-sm">Playfair Bold - heading weight</Text>
        <Text className="mt-2 font-sans-medium text-muted-brown text-sm">DM Sans Medium - tab labels use this</Text>
        <Text className="mt-2 font-mono text-amber-light text-sm">{'const demo = "JetBrains Mono"'}</Text>
      </View>
    </SafeAreaView>
  )
}
