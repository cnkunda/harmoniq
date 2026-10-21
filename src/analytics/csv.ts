import type { AnalyticsEventRow } from '@/src/db/types'

const CSV_HEADER = 'id,user_id,event_type,timestamp,payload_json'

function escapeCsvField(value: string): string {
  if (!/[",\r\n]/.test(value)) return value
  return `"${value.replace(/"/g, '""')}"`
}

/**
 * Serialize analytics rows as RFC 4180 CSV. Deterministic order: timestamp, then id.
 */
export function analyticsEventsToCsv(events: AnalyticsEventRow[]): string {
  const sorted = [...events].sort((a, b) => {
    if (a.timestamp !== b.timestamp) return a.timestamp < b.timestamp ? -1 : 1
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0
  })

  const lines = [CSV_HEADER]
  for (const event of sorted) {
    lines.push(
      [
        escapeCsvField(event.id),
        escapeCsvField(event.user_id),
        escapeCsvField(event.event_type),
        escapeCsvField(event.timestamp),
        escapeCsvField(event.payload_json),
      ].join(','),
    )
  }
  return lines.join('\r\n')
}
