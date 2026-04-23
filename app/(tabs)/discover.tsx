import { useFocusEffect } from '@react-navigation/native'
import { useCallback, useState } from 'react'
import { ActivityIndicator, ScrollView, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { DiscoveryCard } from '@/components/DiscoveryCard'
import { ErrorBanner } from '@/components/ErrorBanner'
import { WoodGradient } from '@/components/WoodGradient'
import { getDiscoveryRecommendations } from '@/src/api/discovery'
import colors from '@/src/constants/colors'
import { listSessionsJournal } from '@/src/db/client'
import { useLessonStore } from '@/src/stores/lessonStore'
import { useSkillStore } from '@/src/stores/skillStore'
import type { DiscoverySuggestion } from '@/src/types'
import { useRouter } from 'expo-router'

export default function DiscoverScreen() {
  const router = useRouter()
  const loadSkills = useSkillStore((s) => s.loadFromDb)
  const nodes = useSkillStore((s) => s.nodes)
  const lesson = useLessonStore((s) => s.lesson)
  
  const [suggestions, setSuggestions] = useState<DiscoverySuggestion[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadRecommendations = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // Get mastered job IDs from session history
      const sessions = await listSessionsJournal()
      const masteredJobIds = sessions.slice(0, 5).map(s => s.job_id).filter((id): id is string => Boolean(id))
      
      if (masteredJobIds.length === 0) {
        setSuggestions([])
        return
      }
      
      const skillNodesPayload = nodes.map(n => ({
        id: n.id,
        label: n.label,
        score: n.score,
      }))
      
      const response = await getDiscoveryRecommendations({
        mastered_job_ids: masteredJobIds,
        skill_nodes: skillNodesPayload,
        limit: 5,
        min_similarity: 0.3,
      })
      
      setSuggestions(response.suggestions)
    } catch (e) {
      setError('Failed to load recommendations')
      console.error('Discovery error:', e)
    } finally {
      setLoading(false)
    }
  }, [nodes])

  useFocusEffect(
    useCallback(() => {
      void loadSkills()
      void loadRecommendations()
    }, [loadSkills, loadRecommendations])
  )

  const handleAnalyze = (suggestion: DiscoverySuggestion) => {
    // Navigate to add-song with the job_id for one-tap analysis
    // Note: This is a one-tap deep-link to analyze, not directly to session play
    // The lesson must be loaded from the analyze job before entering session flow
    router.push({
      pathname: '/add-song',
      params: { jobId: suggestion.job_id },
    })
  }

  return (
    <SafeAreaView className="flex-1">
      <WoodGradient />
      <ScrollView className="flex-1">
        <View className="p-4">
          <Text className="mb-2 font-sans text-[24px] font-semibold text-cream/90">Discover</Text>
          <Text className="mb-4 font-sans text-[14px] text-cream/60">
            Song recommendations based on your progress
          </Text>

          {loading && (
            <View className="flex-1 items-center justify-center py-12">
              <ActivityIndicator color={colors.amber.accent} />
              <Text className="mt-3 font-sans text-[14px] text-cream/60">Loading recommendations...</Text>
            </View>
          )}

          {error && (
            <ErrorBanner
              dismissible
              message={error}
              onDismissed={() => setError(null)}
              action={{ label: 'Retry', onPress: () => void loadRecommendations() }}
            />
          )}

          {!loading && !error && suggestions.length === 0 && (
            <View className="flex-1 items-center justify-center py-12">
              <Text className="font-sans text-[14px] text-cream/60">
                Complete more lessons to get personalized recommendations
              </Text>
            </View>
          )}

          {!loading && !error && suggestions.map((suggestion, index) => (
            <DiscoveryCard
              key={suggestion.job_id}
              suggestion={suggestion}
              onAnalyze={() => handleAnalyze(suggestion)}
            />
          ))}
        </View>
      </ScrollView>
    </SafeAreaView>
  )
}
