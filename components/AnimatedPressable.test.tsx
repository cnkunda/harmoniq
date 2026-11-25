import * as Haptics from 'expo-haptics'
import { fireEvent, render, screen } from '@testing-library/react-native'
import { Text } from 'react-native'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AnimatedPressable } from '@/components/AnimatedPressable'

vi.mock('expo-haptics', () => ({
  ImpactFeedbackStyle: { Light: 0, Medium: 1, Heavy: 2 },
  impactAsync: vi.fn(async () => undefined),
}))

const impactAsync = vi.mocked(Haptics.impactAsync)

beforeEach(() => {
  impactAsync.mockClear()
})

describe('AnimatedPressable', () => {
  it('renders its children and a button role', () => {
    render(
      <AnimatedPressable accessibilityRole="button"><Text>Tap me</Text></AnimatedPressable>,
    )

    expect(screen.getByRole('button')).toBeTruthy()
    expect(screen.getByText('Tap me')).toBeTruthy()
  })

  it('invokes onPress and triggers a light haptic by default', () => {
    const onPress = vi.fn()
    render(
      <AnimatedPressable accessibilityRole="button" onPress={onPress}>
        <Text>Go</Text>
      </AnimatedPressable>,
    )

    fireEvent.press(screen.getByText('Go'))

    expect(onPress).toHaveBeenCalledTimes(1)
    expect(impactAsync).toHaveBeenCalledWith(Haptics.ImpactFeedbackStyle.Light)
  })

  it.each([
    ['medium', Haptics.ImpactFeedbackStyle.Medium],
    ['heavy', Haptics.ImpactFeedbackStyle.Heavy],
  ] as const)('maps haptic "%s" to its impact style', (haptic, expectedStyle) => {
    render(
      <AnimatedPressable accessibilityRole="button" haptic={haptic}>
        <Text>Go</Text>
      </AnimatedPressable>,
    )

    fireEvent.press(screen.getByText('Go'))

    expect(impactAsync).toHaveBeenCalledWith(expectedStyle)
  })

  it('skips the haptic when haptic is "none"', () => {
    const onPress = vi.fn()
    render(
      <AnimatedPressable accessibilityRole="button" haptic="none" onPress={onPress}>
        <Text>Go</Text>
      </AnimatedPressable>,
    )

    fireEvent.press(screen.getByText('Go'))

    expect(impactAsync).not.toHaveBeenCalled()
    expect(onPress).toHaveBeenCalledTimes(1)
  })

  it('skips the haptic when disabled', () => {
    const onPress = vi.fn()
    render(
      <AnimatedPressable accessibilityRole="button" disabled onPress={onPress}>
        <Text>Go</Text>
      </AnimatedPressable>,
    )

    fireEvent.press(screen.getByText('Go'))

    expect(impactAsync).not.toHaveBeenCalled()
  })

  it('passes pressIn and pressOut events through', () => {
    const onPressIn = vi.fn()
    const onPressOut = vi.fn()
    render(
      <AnimatedPressable
        accessibilityRole="button"
        onPressIn={onPressIn}
        onPressOut={onPressOut}
      >
        <Text>Go</Text>
      </AnimatedPressable>,
    )

    fireEvent(screen.getByText('Go'), 'pressIn')
    fireEvent(screen.getByText('Go'), 'pressOut')

    expect(onPressIn).toHaveBeenCalledTimes(1)
    expect(onPressOut).toHaveBeenCalledTimes(1)
    expect(impactAsync).not.toHaveBeenCalled()
  })

  it('does not fire the haptic on pressIn', () => {
    render(
      <AnimatedPressable accessibilityRole="button"><Text>Go</Text></AnimatedPressable>,
    )

    fireEvent(screen.getByText('Go'), 'pressIn')

    expect(impactAsync).not.toHaveBeenCalled()
  })
})
