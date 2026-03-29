import { Tabs } from 'expo-router'
import { Home } from 'lucide-react-native'

import colors from '@/src/constants/colors'

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: colors.wood[800],
          borderTopColor: `${colors.wood[700]}80`,
          paddingBottom: 8,
          height: 64,
        },
        tabBarActiveTintColor: colors.amber.light,
        tabBarInactiveTintColor: colors.muted.brown,
        tabBarLabelStyle: {
          fontFamily: 'DMSans-Medium',
          fontSize: 10,
          letterSpacing: 0.5,
        },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Home',
          tabBarIcon: ({ color, size }) => <Home color={color} size={size} strokeWidth={2} />,
        }}
      />
    </Tabs>
  )
}
