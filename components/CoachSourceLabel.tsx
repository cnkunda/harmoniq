import { Text } from 'react-native'

import { coachSourceLabel, type CoachSource } from '@/src/coach/coachSource'

type Props = {
  source?: CoachSource | null
  className?: string
}

/** Small provenance label rendered next to coach copy. */
export function CoachSourceLabel({ source, className = '' }: Props) {
  const label = coachSourceLabel(source)
  if (!label) return null
  return (
    <Text className={`font-sans text-[10px] uppercase tracking-wide text-muted-brown ${className}`}>
      {label}
    </Text>
  )
}
