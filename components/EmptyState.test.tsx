import { fireEvent, render, screen } from '@testing-library/react-native'
import type { LucideIcon } from 'lucide-react-native'
import type { ReactNode } from 'react'
import { Text } from 'react-native'
import { describe, expect, it, vi } from 'vitest'

import { EmptyState } from '@/components/EmptyState'

vi.mock('expo-haptics', () => ({
  ImpactFeedbackStyle: { Light: 0, Medium: 1, Heavy: 2 },
  impactAsync: vi.fn(async () => undefined),
}))

/** Stand-in for a Lucide icon; proves the Icon prop reaches the tree. */
const StubIcon = (): ReactNode => <Text>stub-icon</Text>
const Icon = StubIcon as unknown as LucideIcon

describe('EmptyState', () => {
  it('renders heading and subtext', () => {
    render(<EmptyState Icon={Icon} heading="No songs yet" subtext="Add a song to begin." />)

    expect(screen.getByText('No songs yet')).toBeTruthy()
    expect(screen.getByText('Add a song to begin.')).toBeTruthy()
  })

  it('renders the provided Icon', () => {
    render(<EmptyState Icon={Icon} heading="Empty" subtext="Nothing here" />)

    expect(screen.getByText('stub-icon')).toBeTruthy()
  })

  it('omits the CTA when no label is given', () => {
    render(<EmptyState Icon={Icon} heading="Empty" subtext="Nothing" onCta={vi.fn()} />)

    expect(screen.queryByText('Add song')).toBeNull()
  })

  it('omits the CTA when no handler is given', () => {
    render(<EmptyState Icon={Icon} heading="Empty" subtext="Nothing" ctaLabel="Add song" />)

    expect(screen.queryByText('Add song')).toBeNull()
  })

  it('renders the CTA when both label and handler are given and invokes it on press', () => {
    const onCta = vi.fn()
    render(
      <EmptyState Icon={Icon} heading="Empty" subtext="Nothing" ctaLabel="Add song" onCta={onCta} />,
    )

    fireEvent.press(screen.getByText('Add song'))

    expect(onCta).toHaveBeenCalledTimes(1)
    expect(screen.getByText('Empty')).toBeTruthy()
  })
})
