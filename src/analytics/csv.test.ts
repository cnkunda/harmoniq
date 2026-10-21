import { describe, expect, it } from 'vitest'

import { analyticsEventsToCsv } from '@/src/analytics/csv'
import type { AnalyticsEventRow } from '@/src/db/types'

function row(overrides: Partial<AnalyticsEventRow> & Pick<AnalyticsEventRow, 'id' | 'timestamp'>): AnalyticsEventRow {
  return {
    user_id: 'user-1',
    event_type: 'feature_usage',
    payload_json: JSON.stringify({ feature: 'practice_insights' }),
    ...overrides,
  }
}

describe('analyticsEventsToCsv', () => {
  it('returns only the header for an empty export', () => {
    expect(analyticsEventsToCsv([])).toBe('id,user_id,event_type,timestamp,payload_json')
  })

  it('sorts rows by timestamp then id and uses CRLF separators', () => {
    const csv = analyticsEventsToCsv([
      row({ id: 'b', timestamp: '2026-10-21T10:00:00.000Z' }),
      row({ id: 'a', timestamp: '2026-10-21T10:00:00.000Z' }),
      row({ id: 'c', timestamp: '2026-10-20T09:00:00.000Z' }),
    ])

    const lines = csv.split('\r\n')
    expect(lines[0]).toBe('id,user_id,event_type,timestamp,payload_json')
    expect(lines[1]?.startsWith('c,')).toBe(true)
    expect(lines[2]?.startsWith('a,')).toBe(true)
    expect(lines[3]?.startsWith('b,')).toBe(true)
    expect(csv).not.toContain('\n\n')
  })

  it('escapes quotes, commas, and newlines per RFC 4180', () => {
    const payloadJson = JSON.stringify({ note: 'line one\nline two, with "quotes"' })
    const csv = analyticsEventsToCsv([
      row({
        id: 'event-1',
        timestamp: '2026-10-21T10:00:00.000Z',
        payload_json: payloadJson,
      }),
    ])

    const expectedPayloadField = `"${payloadJson.replace(/"/g, '""')}"`
    expect(csv.endsWith(expectedPayloadField)).toBe(true)
    expect(expectedPayloadField).toContain('line two, with')
    expect(expectedPayloadField).toContain('\\""quotes\\""')
  })

  it('does not mutate the input array order', () => {
    const events = [
      row({ id: 'b', timestamp: '2026-10-21T10:00:00.000Z' }),
      row({ id: 'a', timestamp: '2026-10-20T10:00:00.000Z' }),
    ]

    analyticsEventsToCsv(events)

    expect(events.map((event) => event.id)).toEqual(['b', 'a'])
  })
})
