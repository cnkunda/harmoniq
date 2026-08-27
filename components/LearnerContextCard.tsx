import { useFocusEffect } from '@react-navigation/native'
import { useCallback, useState } from 'react'
import { Text, View } from 'react-native'

import { parseTasteProfileJson } from '@/src/api/analyze'
import { getAppPref } from '@/src/db/client'
import {
  PREF_EXPERIENCE_LEVEL,
  PREF_STYLE_FOCUS,
  PREF_TASTE_PROFILE_JSON,
} from '@/src/db/schema'
import type { SkillNodeRow } from '@/src/db/types'
import { pickWeakAreaPulseNode } from '@/src/home/weakAreaPulseLogic'

function weakAreaPhrase(nodes: readonly SkillNodeRow[]): string | null {
  const pulse = pickWeakAreaPulseNode(nodes)
  if (pulse != null) {
    const raw = pulse.label ?? pulse.id
    return raw.replace(/_/g, ' ')
  }
  const sorted = [...nodes].sort((a, b) => a.score - b.score || (a.label ?? '').localeCompare(b.label ?? ''))
  const w = sorted[0]
  if (!w || w.score >= 0.55) return null
  const raw = w.label ?? w.id
  return raw.replace(/_/g, ' ')
}

/**
 * Summary of declared learner settings + inferred weak focus for Progress / coach transparency.
 */
export function LearnerContextCard({ skillNodes }: { skillNodes: readonly SkillNodeRow[] }) {
  const [experience, setExperience] = useState<string | null>(null)
  const [styleFocus, setStyleFocus] = useState('')
  const [tasteLane, setTasteLane] = useState<string | null>(null)

  const refresh = useCallback(() => {
    void Promise.all([
      getAppPref(PREF_EXPERIENCE_LEVEL),
      getAppPref(PREF_STYLE_FOCUS),
      getAppPref(PREF_TASTE_PROFILE_JSON),
    ]).then(([expRaw, styleRaw, tasteRaw]) => {
      const ex = expRaw?.trim().toLowerCase()
      setExperience(ex === 'beginner' || ex === 'intermediate' || ex === 'advanced' ? ex : null)
      setStyleFocus(styleRaw?.trim() ?? '')
      const dt = parseTasteProfileJson(tasteRaw)
      setTasteLane(dt?.style_label?.trim() ? dt.style_label.trim() : null)
    })
  }, [])

  useFocusEffect(
    useCallback(() => {
      refresh()
    }, [refresh]),
  )

  const weak = weakAreaPhrase(skillNodes)

  return (
    <View className="rounded-xl border border-wood-600/50 bg-wood-800/80 p-4">
      <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">Coach context</Text>
      <Text className="mt-2 font-sans text-xs text-muted-light">
        What you have set in Settings and the style quiz, plus the weakest skill focus we infer from practice.
      </Text>
      <View className="mt-3 gap-2">
        <Text className="font-sans text-sm text-cream">
          Experience:{' '}
          <Text className="font-sans-medium capitalize text-amber-light">
            {experience ?? 'Not set — update in Settings'}
          </Text>
        </Text>
        <Text className="font-sans text-sm text-cream">
          Style lane:{' '}
          <Text className="font-sans-medium text-amber-light">{tasteLane ?? '—'}</Text>
        </Text>
        <Text className="font-sans text-sm text-cream">
          Style focus:{' '}
          <Text className="text-cream">{styleFocus.length ? styleFocus : '—'}</Text>
        </Text>
        <Text className="font-sans text-sm text-cream">
          Inferred focus: <Text className="font-sans-medium capitalize text-amber-light">{weak ?? '—'}</Text>
        </Text>
      </View>
    </View>
  )
}
