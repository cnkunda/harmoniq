import * as Haptics from 'expo-haptics'
import { fireEvent, render, screen } from '@testing-library/react-native'
import { Text } from 'react-native'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Button, DangerButton, GhostButton, PrimaryButton, SecondaryButton } from '@/components/Button'
import { BTN_BASE, BTN_PRIMARY, BTN_SECONDARY } from '@/src/constants/buttonStyles'

vi.mock('expo-haptics', () => ({
  ImpactFeedbackStyle: { Light: 0, Medium: 1, Heavy: 2 },
  impactAsync: vi.fn(async () => undefined),
}))

const impactAsync = vi.mocked(Haptics.impactAsync)

/** Collects className props across the tree — Button styles the inner pressable, wrappers style the root. */
function allClassNames(result: ReturnType<typeof render>): string {
  const names: string[] = []
  const walk = (node: unknown): void => {
    if (Array.isArray(node)) {
      node.forEach(walk)
      return
    }
    if (node === null || typeof node !== 'object') return
    const { children, props } = node as { children?: unknown; props?: { className?: unknown } }
    if (typeof props?.className === 'string') names.push(props.className)
    walk(children)
  }
  walk(result.toJSON())
  return names.join(' ')
}

beforeEach(() => {
  impactAsync.mockClear()
})

describe('Button', () => {
  it('renders its label as a button', () => {
    render(<Button label="Continue" />)

    expect(screen.getByRole('button')).toBeTruthy()
    expect(screen.getByText('Continue')).toBeTruthy()
  })

  it('invokes onPress when pressed', () => {
    const onPress = vi.fn()
    render(<Button label="Continue" onPress={onPress} />)

    fireEvent.press(screen.getByText('Continue'))

    expect(onPress).toHaveBeenCalledTimes(1)
    expect(impactAsync).toHaveBeenCalledWith(Haptics.ImpactFeedbackStyle.Light)
  })

  it('marks itself busy and hides the label while loading', () => {
    render(<Button label="Continue" loading />)

    const button = screen.getByRole('button')
    expect(button.props.accessibilityState).toEqual({ disabled: true, busy: true })
    expect(screen.queryByText('Continue')).toBeNull()
  })

  it('does not fire the haptic while loading', () => {
    const onPress = vi.fn()
    render(<Button label="Continue" loading onPress={onPress} />)

    fireEvent.press(screen.getByRole('button'))

    expect(impactAsync).not.toHaveBeenCalled()
  })

  it('exposes the disabled state and keeps its label', () => {
    render(<Button label="Continue" disabled />)

    const button = screen.getByRole('button')
    expect(button.props.accessibilityState).toEqual({ disabled: true, busy: false })
    expect(screen.getByText('Continue')).toBeTruthy()
  })

  it('does not fire the haptic while disabled', () => {
    render(<Button label="Continue" disabled />)

    fireEvent.press(screen.getByRole('button'))

    expect(impactAsync).not.toHaveBeenCalled()
  })

  it('renders the icon next to the label', () => {
    render(<Button label="Continue" icon={<Text>icon-mark</Text>} />)

    expect(screen.getByText('icon-mark')).toBeTruthy()
    expect(screen.getByText('Continue')).toBeTruthy()
  })

  it.each([
    ['primary', BTN_PRIMARY],
    ['secondary', BTN_SECONDARY],
  ] as const)('applies the %s variant styling', (variant, expectedClass) => {
    const result = render(<Button label="Go" variant={variant} />)

    expect(allClassNames(result)).toContain(expectedClass)
  })

  it('applies the medium size styling by default', () => {
    const result = render(<Button label="Go" />)

    expect(allClassNames(result)).toContain(BTN_BASE)
  })

  it('wraps itself when fullWidth is set', () => {
    const result = render(<Button label="Go" fullWidth />)

    expect(allClassNames(result)).toContain('w-full')
  })

  it('wraps itself in the container class when provided', () => {
    const result = render(<Button label="Go" containerClassName="flex-1" />)

    expect(allClassNames(result)).toContain('flex-1')
  })

  it('returns the bare pressable without wrappers by default', () => {
    const result = render(<Button label="Go" />)

    expect(allClassNames(result)).not.toContain('w-full')
    expect(allClassNames(result)).toContain(BTN_PRIMARY)
  })

  it.each([
    ['PrimaryButton', PrimaryButton],
    ['SecondaryButton', SecondaryButton],
    ['GhostButton', GhostButton],
    ['DangerButton', DangerButton],
  ])('%s renders its label', (_name, Component) => {
    render(<Component label="Save" />)

    expect(screen.getByRole('button')).toBeTruthy()
    expect(screen.getByText('Save')).toBeTruthy()
  })
})
