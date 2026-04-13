import { Tabs } from 'expo-router'
import {
  BarChart3,
  FlaskConical,
  Home,
  Library,
  Music,
  Palette,
  Settings,
} from 'lucide-react-native'

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
      <Tabs.Screen
        name="library"
        options={{
          title: 'Library',
          tabBarIcon: ({ color, size }) => <Library color={color} size={size} strokeWidth={2} />,
        }}
      />
      <Tabs.Screen
        name="progress"
        options={{
          title: 'Progress',
          tabBarIcon: ({ color, size }) => <BarChart3 color={color} size={size} strokeWidth={2} />,
        }}
      />
      <Tabs.Screen
        name="jam"
        options={{
          title: 'Jam Mode',
          tabBarIcon: ({ color, size }) => <Music color={color} size={size} strokeWidth={2} />,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: 'Settings',
          tabBarIcon: ({ color, size }) => <Settings color={color} size={size} strokeWidth={2} />,
        }}
      />
      <Tabs.Screen
        name="design-preview"
        options={{
          title: 'Design',
          href: __DEV__ ? undefined : null,
          tabBarIcon: ({ color, size }) => <Palette color={color} size={size} strokeWidth={2} />,
        }}
      />
      <Tabs.Screen
        name="analyze-debug"
        options={{
          title: 'Analyze',
          href: __DEV__ ? undefined : null,
          tabBarIcon: ({ color, size }) => <FlaskConical color={color} size={size} strokeWidth={2} />,
        }}
      />
    </Tabs>
  )
}
