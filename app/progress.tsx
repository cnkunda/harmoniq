import { useFocusEffect } from '@react-navigation/native'
import { useRouter } from 'expo-router'
import { useCallback, useMemo, useRef, useState } from 'react'
import { Modal, Pressable, ScrollView, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { DEFAULT_SKILL_NODES } from '@/src/db/schema'
import { getLatestSessionSnippetForNode, listSessionsJournal } from '@/src/db/client'
import type { NodeSessionSnippet, SessionJournalRow } from '@/src/db/types'
import { useSkillStore } from '@/src/stores/skillStore'

const RADIAL_R = 78
const RADIAL_CX = 100
const RADIAL_CY = 102

export default function ProgressScreen() {
  const router = useRouter()
  const loadSkills = useSkillStore((s) => s.loadFromDb)
  const nodes = useSkillStore((s) => s.nodes)
  const [journal, setJournal] = useState<SessionJournalRow[]>([])
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [snippet, setSnippet] = useState<NodeSessionSnippet | null>(null)
  const [snippetLoading, setSnippetLoading] = useState(false)
  /** Bumps on each new node open or close so stale async snippet fetches are ignored. */
  const snippetRequestRef = useRef(0)

  const refresh = useCallback(() => {
    void loadSkills()
    void listSessionsJournal()
      .then(setJournal)
      .catch(() => setJournal([]))
  }, [loadSkills])

  useFocusEffect(
    useCallback(() => {
      refresh()
    }, [refresh]),
  )

  const displayNodes = useMemo(() => {
    return DEFAULT_SKILL_NODES.map((def) => {
      const row = nodes.find((n) => n.id === def.id)
      const value = row != null ? row.score : 0
      return { id: def.id, label: def.label, value }
    })
  }, [nodes])

  const openNode = useCallback((nodeId: string) => {
    const token = ++snippetRequestRef.current
    setSelectedNodeId(nodeId)
    setSnippet(null)
    setSnippetLoading(true)
    void getLatestSessionSnippetForNode(nodeId)
      .then((s) => {
        if (snippetRequestRef.current !== token) return
        setSnippetLoading(false)
        setSnippet(s)
      })
      .catch(() => {
        if (snippetRequestRef.current !== token) return
        setSnippetLoading(false)
        setSnippet(null)
      })
  }, [])

  const closeNode = useCallback(() => {
    snippetRequestRef.current += 1
    setSelectedNodeId(null)
    setSnippet(null)
    setSnippetLoading(false)
  }, [])

  const detailLabel = selectedNodeId ? displayNodes.find((d) => d.id === selectedNodeId)?.label : null
  const detailScore = selectedNodeId ? displayNodes.find((d) => d.id === selectedNodeId)?.value : null

  const detailCopy = useMemo(() => {
    if (snippetLoading) {
      return 'Loading latest session for this skill…'
    }
    if (!snippet) {
      return 'No sessions targeting this node yet. Complete a review session to see coach copy here.'
    }
    if (snippet.coach_review && snippet.coach_review.trim()) {
      return snippet.coach_review.trim()
    }
    const parts: string[] = []
    if (snippet.pitch_accuracy != null && Number.isFinite(snippet.pitch_accuracy)) {
      parts.push(`Pitch ${(snippet.pitch_accuracy * 100).toFixed(0)}%`)
    }
    if (snippet.phrasing_score != null && Number.isFinite(snippet.phrasing_score)) {
      parts.push(`phrasing ${(snippet.phrasing_score * 100).toFixed(0)}%`)
    }
    if (parts.length > 0) {
      return `Latest session (${snippet.date.slice(0, 10)}): ${parts.join(', ')}. Coach line not stored yet.`
    }
    return `Latest session (${snippet.date.slice(0, 10)}). No coach line stored yet.`
  }, [snippet, snippetLoading])

  return (
    <SafeAreaView className="flex-1 bg-wood-900" edges={['top', 'left', 'right']}>
      <ScrollView className="flex-1 px-6 py-6" contentContainerStyle={{ paddingBottom: 40 }}>
        <Text className="font-serif text-2xl text-cream">Progress</Text>
        <Text className="mt-2 font-sans text-sm text-muted-brown">
          Skill map from your local data and a session journal (newest first). Tap a node for the latest coach note (or
          score summary). Tap a journal row to open the saved review.
        </Text>

        <Text className="mt-8 font-sans-medium text-xs uppercase tracking-wide text-amber-light">Skill map</Text>
        <View className="mt-4 h-[210px] w-[200px] self-center">
          {displayNodes.map((s, i) => {
            const angle = -Math.PI / 2 + (i * 2 * Math.PI) / 5
            const x = RADIAL_CX + RADIAL_R * Math.cos(angle) - 36
            const y = RADIAL_CY + RADIAL_R * Math.sin(angle) - 22
            return (
              <Pressable
                key={s.id}
                onPress={() => openNode(s.id)}
                className="absolute w-[72px] items-center active:opacity-80"
                style={{ left: x, top: y }}
                accessibilityRole="button"
                accessibilityLabel={`${s.label}, ${(s.value * 100).toFixed(0)} percent`}
              >
                <View className="h-3.5 w-3.5 rounded-full bg-amber-accent" />
                <Text className="mt-1 text-center text-[9px] leading-3 text-cream" numberOfLines={2}>
                  {s.label}
                </Text>
                <Text className="text-[9px] text-muted-brown">{(s.value * 100).toFixed(0)}%</Text>
              </Pressable>
            )
          })}
        </View>

        <Text className="mt-10 font-sans-medium text-xs uppercase tracking-wide text-amber-light">Session journal</Text>
        {journal.length === 0 ? (
          <Text className="mt-3 font-sans text-sm text-muted-brown">No completed sessions in the local journal yet.</Text>
        ) : (
          <View className="mt-3 gap-2">
            {journal.map((j) => (
              <Pressable
                key={j.id}
                onPress={() => router.push({ pathname: '/review-archive/[sessionId]', params: { sessionId: j.id } })}
                className="rounded-xl border border-wood-600/50 bg-wood-800/80 px-4 py-3 active:opacity-90"
                accessibilityRole="button"
                accessibilityLabel={`Open session ${j.song_title ?? 'practice'}`}
              >
                <Text className="font-sans-medium text-sm text-cream">
                  {j.song_title?.trim() ? j.song_title : 'Practice session'}
                  {j.artist ? <Text className="font-sans text-muted-brown">{` · ${j.artist}`}</Text> : null}
                </Text>
                <Text className="mt-1 font-mono text-[10px] text-muted-brown">{j.date}</Text>
                {j.section_label ? (
                  <Text className="mt-1 font-sans text-xs text-muted-brown">{j.section_label}</Text>
                ) : null}
                <View className="mt-2 flex-row flex-wrap gap-2">
                  {j.has_review_snapshot ? (
                    <Text className="rounded bg-amber-accent/20 px-2 py-0.5 font-sans text-[10px] text-amber-light">
                      Saved review
                    </Text>
                  ) : null}
                  {(j.waveform_user_path?.length ?? 0) > 0 || (j.waveform_ref_path?.length ?? 0) > 0 ? (
                    <Text className="rounded bg-success/20 px-2 py-0.5 font-sans text-[10px] text-success">
                      Waveform files
                    </Text>
                  ) : null}
                </View>
              </Pressable>
            ))}
          </View>
        )}

        <Pressable
          onPress={() => router.back()}
          className="mt-8 rounded-lg border border-wood-600/45 bg-cream-dark/45 px-4 py-3"
          accessibilityRole="button"
        >
          <Text className="text-center font-sans-medium text-wood-900">Back</Text>
        </Pressable>
      </ScrollView>

      <Modal visible={selectedNodeId != null} transparent animationType="fade" onRequestClose={closeNode}>
        <Pressable className="flex-1 justify-end bg-black/50" onPress={closeNode} accessibilityRole="button">
          <Pressable
            className="rounded-t-2xl border border-wood-600/50 bg-ivory px-5 pb-8 pt-5"
            onPress={(e) => e.stopPropagation()}
          >
            <Text className="font-serif text-xl text-wood-900">{detailLabel}</Text>
            {detailScore != null ? (
              <Text className="mt-1 font-mono text-sm text-muted-brown">Model score · {(detailScore * 100).toFixed(0)}%</Text>
            ) : null}
            <Text className="mt-4 font-sans text-sm leading-6 text-wood-900">{detailCopy}</Text>
            <Pressable
              onPress={closeNode}
              className="mt-6 self-stretch rounded-lg bg-amber-accent px-4 py-3"
              accessibilityRole="button"
            >
              <Text className="text-center font-sans-medium text-wood-900">Close</Text>
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>
    </SafeAreaView>
  )
}
