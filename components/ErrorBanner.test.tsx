import { fireEvent, render, screen } from '@testing-library/react-native'
import { describe, expect, it, vi } from 'vitest'

import { ErrorBanner } from '@/components/ErrorBanner'

vi.mock('expo-haptics', () => ({
  ImpactFeedbackStyle: { Light: 0, Medium: 1, Heavy: 2 },
  impactAsync: vi.fn(async () => undefined),
}))

function rootClassName(result: ReturnType<typeof render>): string {
  const tree = result.toJSON()
  if (tree === null || Array.isArray(tree)) return ''
  return String(tree.props.className ?? '')
}

/** Banner pressables all receive a `haptic` prop; render order: action first, X last. */
function pressables(result: ReturnType<typeof render>) {
  return result.UNSAFE_queryAllByProps({ haptic: 'light' })
}

describe('ErrorBanner', () => {
  it('renders the message', () => {
    render(<ErrorBanner message="Could not save" />)

    expect(screen.getByText('Could not save')).toBeTruthy()
  })

  it('renders the optional detail line', () => {
    render(<ErrorBanner message="Could not save" detail="Check your connection" />)

    expect(screen.getByText('Could not save')).toBeTruthy()
    expect(screen.getByText('Check your connection')).toBeTruthy()
  })

  it.each([
    ['warning', 'bg-amber-accent/12'],
    ['error', 'bg-danger/12'],
    ['info', 'bg-wood-700/50'],
  ] as const)('styles the "%s" variant', (variant, expectedClass) => {
    const result = render(<ErrorBanner message="Boom" variant={variant} />)

    expect(rootClassName(result)).toContain(expectedClass)
  })

  it('defaults to the warning styling', () => {
    const result = render(<ErrorBanner message="Boom" />)

    expect(rootClassName(result)).toContain('bg-amber-accent/12')
  })

  it('invokes the action handler', () => {
    const onPress = vi.fn()
    render(
      <ErrorBanner message="Could not save" action={{ label: 'Retry', onPress }} />,
    )

    fireEvent.press(screen.getByText('Retry'))

    expect(onPress).toHaveBeenCalledTimes(1)
    expect(screen.getByText('Could not save')).toBeTruthy()
  })

  it('hides the banner and reports dismissal when the X is pressed', () => {
    const onDismissed = vi.fn()
    const result = render(<ErrorBanner message="Could not save" onDismissed={onDismissed} />)
    const [dismissButton] = pressables(result)

    expect(dismissButton).toBeTruthy()
    fireEvent.press(dismissButton!)

    expect(screen.queryByText('Could not save')).toBeNull()
    expect(onDismissed).toHaveBeenCalledTimes(1)
  })

  it('keeps the banner visible when only the action is pressed', () => {
    const onDismissed = vi.fn()
    const onPress = vi.fn()
    const result = render(
      <ErrorBanner
        message="Could not save"
        onDismissed={onDismissed}
        action={{ label: 'Retry', onPress }}
      />,
    )

    expect(pressables(result)).toHaveLength(2)
    fireEvent.press(screen.getByText('Retry'))

    expect(onPress).toHaveBeenCalledTimes(1)
    expect(onDismissed).not.toHaveBeenCalled()
    expect(screen.getByText('Could not save')).toBeTruthy()
  })

  it('omits the dismiss control when dismissible is false', () => {
    const result = render(<ErrorBanner message="Could not save" dismissible={false} />)

    expect(pressables(result)).toHaveLength(0)
    expect(screen.getByText('Could not save')).toBeTruthy()
  })

  it('renders no dismiss control for a dismissed banner', () => {
    const result = render(<ErrorBanner message="Could not save" />)
    const [dismissButton] = pressables(result)

    fireEvent.press(dismissButton!)

    expect(result.toJSON()).toBeNull()
  })
})
