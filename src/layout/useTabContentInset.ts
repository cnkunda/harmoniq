import { useBottomTabBarHeight } from '@react-navigation/bottom-tabs'

/** Bottom scroll padding that keeps content clear of the tab bar. */
export function useTabContentInset(extra = 24): number {
  return useBottomTabBarHeight() + extra
}
