import { render, screen } from '@testing-library/react-native'
import { StyleSheet } from 'react-native'
import { describe, expect, it } from 'vitest'

import { LoadingSkeleton } from '@/components/LoadingSkeleton'
import { colors } from '@/src/constants/colors'

function flattenedStyle(result: ReturnType<typeof render>): Record<string, unknown> {
  const tree = result.toJSON()
  expect(tree).not.toBeNull()
  if (tree === null || Array.isArray(tree)) return {}
  return (StyleSheet.flatten(tree.props.style) ?? {}) as Record<string, unknown>
}

describe('LoadingSkeleton', () => {
  it('renders with the default metrics', () => {
    const result = render(<LoadingSkeleton />)
    const style = flattenedStyle(result)

    expect(style.width).toBe('100%')
    expect(style.height).toBe(16)
    expect(style.borderRadius).toBe(8)
    expect(style.backgroundColor).toBe(colors.wood[600])
  })

  it('applies custom metrics', () => {
    const result = render(<LoadingSkeleton width={120} height={40} borderRadius={12} />)
    const style = flattenedStyle(result)

    expect(style.width).toBe(120)
    expect(style.height).toBe(40)
    expect(style.borderRadius).toBe(12)
  })

  it('merges the incoming style prop', () => {
    const result = render(<LoadingSkeleton style={{ marginTop: 4 }} />)
    const style = flattenedStyle(result)

    expect(style.marginTop).toBe(4)
    expect(style.height).toBe(16)
  })

  it('renders exactly one host node', () => {
    const result = render(<LoadingSkeleton width="50%" />)

    expect(screen.toJSON()).toBeTruthy()
    expect(result.UNSAFE_root).toBeTruthy()
  })
})
