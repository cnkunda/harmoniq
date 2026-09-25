import { Tabs } from 'expo-router'
import {
    BarChart3,
    Compass,
    FlaskConical,
    Home,
    Library,
    Music,
    Palette,
    Settings
} from 'lucide-react-native'

import colors from '@/src/constants/colors'

/** Slightly larger than React Navigation default (~24) for clearer tab targets. */
const TAB_BAR_ICON_SIZE = 26

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarAccessibilityLabel: 'Main navigation',
        tabBarStyle: {
          backgroundColor: colors.wood[800],
          borderTopColor: `${colors.wood[700]}80`,
          paddingBottom: 8,
          paddingTop: 6,
          height: 68,
        },
        tabBarLabelPosition: 'below-icon',
        tabBarActiveTintColor: colors.amber.light,
        tabBarInactiveTintColor: colors.muted.brown,
        tabBarLabelStyle: {
          fontFamily: 'DMSans-Medium',
          fontSize: 10,
          letterSpacing: 0.4,
        },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Home',
          tabBarIcon: ({ color }) => <Home color={color} size={TAB_BAR_ICON_SIZE} strokeWidth={2} />,
        }}
      />
      <Tabs.Screen
        name="library"
        options={{
          title: 'Library',
          tabBarIcon: ({ color }) => <Library color={color} size={TAB_BAR_ICON_SIZE} strokeWidth={2} />,
        }}
      />
      <Tabs.Screen
        name="progress"
        options={{
          title: 'Progress',
          tabBarIcon: ({ color }) => <BarChart3 color={color} size={TAB_BAR_ICON_SIZE} strokeWidth={2} />,
        }}
      />
      <Tabs.Screen
        name="jam"
        options={{
          title: 'Jam',
          tabBarIcon: ({ color }) => <Music color={color} size={TAB_BAR_ICON_SIZE} strokeWidth={2} />,
        }}
      />
      <Tabs.Screen
        name="discover"
        options={{
          title: 'Discover',
          tabBarIcon: ({ color }) => <Compass color={color} size={TAB_BAR_ICON_SIZE} strokeWidth={2} />,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: 'Settings',
          tabBarIcon: ({ color }) => <Settings color={color} size={TAB_BAR_ICON_SIZE} strokeWidth={2} />,
        }}
      />
      {/* Hidden from tab bar; open via router.push('/(tabs)/design-preview') or /design-preview on web. */}
      <Tabs.Screen
        name="design-preview"
        options={{
          title: 'Design',
          href: null,
          tabBarIcon: ({ color }) => <Palette color={color} size={TAB_BAR_ICON_SIZE} strokeWidth={2} />,
        }}
      />
      {/* Hidden from tab bar; open via router.push('/(tabs)/analyze-debug') or /analyze-debug on web. */}
      <Tabs.Screen
        name="analyze-debug"
        options={{
          title: 'Analyze',
          href: null,
          tabBarIcon: ({ color }) => <FlaskConical color={color} size={TAB_BAR_ICON_SIZE} strokeWidth={2} />,
        }}
      />
    </Tabs>
  )
}
