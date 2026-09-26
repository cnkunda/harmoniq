import { useFocusEffect } from '@react-navigation/native'
import * as Linking from 'expo-linking'
import { useRouter } from 'expo-router'
import { Headphones, Library, Music } from 'lucide-react-native'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Platform,
  ScrollView,
  Switch,
  Text,
  useWindowDimensions,
  View,
} from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { DiscoverPanel } from '@/components/DiscoverPanel'
import { ErrorBanner } from '@/components/ErrorBanner'
import { getDiscoveryRecommendations } from '@/src/api/discovery'
import {
  createSpotifyPlaybackBridge,
  isSpotifyPlaybackBridgeSkipped,
  type SpotifyPlaybackBridgeError,
} from '@/src/audio/spotifyPlaybackBridge'
import { ActiveListenerCard } from '@/src/chord/ActiveListenerCard'
import { colors } from '@/src/constants/colors'
import { getAppPref, getLessonByJobId, listLessonsJournal, listSessionsJournal } from '@/src/db/client'
import { PREF_SPOTIFY_CLIENT_SESSION } from '@/src/db/schema'
import type { LessonListRow } from '@/src/db/types'
import { useSkillStore } from '@/src/stores/skillStore'
import type { DiscoverySuggestion, LessonJSON, SpotifyPlaybackStatePayload } from '@/src/types'
import type { AlphaTabSurfaceRef } from '@/types/tabMessage'

function spotifySearchUrls(query: string): string[] {
  const q = encodeURIComponent(query)
  if (Platform.OS === 'web') {
    return [`https://open.spotify.com/search/${q}`]
  }
  return [`spotify:search:${q}`, `https://open.spotify.com/search/${q}`]
}

function spotifyBannerProps(error: SpotifyPlaybackBridgeError): { message: string; variant: 'warning' | 'error' } {
  if (error.code === 'inactive_playback') return { message: error.message, variant: 'warning' }
  return { message: error.message, variant: 'error' }
}

export default function DiscoverScreen() {
  const router = useRouter()
  const { width } = useWindowDimensions()
  const twoCol = width >= 640
  const tabRef = useRef<AlphaTabSurfaceRef>(null)
  const loadSkills = useSkillStore((s) => s.loadFromDb)
  const nodes = useSkillStore((s) => s.nodes)

  // Recommendations state
  const [suggestions, setSuggestions] = useState<DiscoverySuggestion[]>([])
  const [recsLoading, setRecsLoading] = useState(false)
  const [recsError, setRecsError] = useState<string | null>(null)

  // Library/Listening mode state
  const [libraryLessons, setLibraryLessons] = useState<LessonListRow[]>([])
  const [selectedJobId, setSelectedJobId] = useState<string>('')
  const [selectedLesson, setSelectedLesson] = useState<LessonJSON | null>(null)
  const [libraryLoading, setLibraryLoading] = useState(true)
  const [libraryLoadError, setLibraryLoadError] = useState<string | null>(null)
  const [tabReady, setTabReady] = useState(false)
  const [followAlong, setFollowAlong] = useState(true)
  const [clientSession, setClientSession] = useState<string>('')
  const [playbackState, setPlaybackState] = useState<SpotifyPlaybackStatePayload | null>(null)
  const [bridgeError, setBridgeError] = useState<SpotifyPlaybackBridgeError | null>(null)

  const playbackSkipped = isSpotifyPlaybackBridgeSkipped()

  const loadRecommendations = useCallback(async () => {
    setRecsLoading(true)
    setRecsError(null)
    try {
      // Get mastered job IDs from session history
      const sessions = await listSessionsJournal()
      const masteredJobIds = sessions.slice(0, 5).map(s => s.job_id).filter((id): id is string => Boolean(id))

      // Get all lessons from library (database) - like listening tab
      const libraryRows = await listLessonsJournal()

      if (masteredJobIds.length === 0 && libraryRows.length === 0) {
        setSuggestions([])
        return
      }

      const skillNodesPayload = nodes.map(n => ({
        id: n.id,
        label: n.label,
        score: n.score,
      }))

      // Fetch full lessons from database using getLessonByJobId
      const libraryLessonsPayload = await Promise.all(
        libraryRows.map(row => getLessonByJobId(row.job_id))
      )

      const validLibraryLessons = libraryLessonsPayload.filter((l): l is NonNullable<typeof l> => l !== null)

      const response = await getDiscoveryRecommendations({
        mastered_job_ids: masteredJobIds,
        library_lessons: validLibraryLessons,
        skill_nodes: skillNodesPayload,
        limit: 5,
        min_similarity: 0.3,
      })

      setSuggestions(response.suggestions)
    } catch (e) {
      setRecsError('Failed to load recommendations')
      console.error('Discovery error:', e)
    } finally {
      setRecsLoading(false)
    }
  }, [nodes])

  const loadLibrary = useCallback(() => {
    setLibraryLoading(true)
    setLibraryLoadError(null)
    void listLessonsJournal()
      .then((rows) => {
        setLibraryLessons(rows)
        const first = rows[0]?.job_id ?? ''
        setSelectedJobId((prev) => prev || first)
      })
      .catch((e) => setLibraryLoadError(e instanceof Error ? e.message : 'Could not load analyzed songs.'))
      .finally(() => setLibraryLoading(false))
  }, [])

  useFocusEffect(
    useCallback(() => {
      void loadSkills()
      void loadRecommendations()
      loadLibrary()
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [loadLibrary])
  )

  // Load Spotify client session
  useEffect(() => {
    let cancelled = false
    void getAppPref(PREF_SPOTIFY_CLIENT_SESSION).then((value) => {
      if (cancelled) return
      setClientSession((value ?? '').trim())
    })
    return () => {
      cancelled = true
    }
  }, [])

  // Load selected lesson when job ID changes
  useEffect(() => {
    let cancelled = false
    if (!selectedJobId) {
      setSelectedLesson(null)
      return () => {
        cancelled = true
      }
    }
    setLibraryLoadError(null)
    setTabReady(false)
    void getLessonByJobId(selectedJobId)
      .then((lesson) => {
        if (cancelled) return
        if (!lesson) {
          setLibraryLoadError('Could not load this analyzed song.')
          setSelectedLesson(null)
          return
        }
        setSelectedLesson(lesson)
      })
      .catch((e) => {
        if (cancelled) return
        setSelectedLesson(null)
        setLibraryLoadError(e instanceof Error ? e.message : 'Could not load this analyzed song.')
      })
    return () => {
      cancelled = true
    }
  }, [selectedJobId])

  // Reset bridge error when selection or follow mode changes
  useEffect(() => {
    setBridgeError(null)
    setPlaybackState(null)
  }, [selectedJobId, followAlong])

  // Spotify playback bridge
  useEffect(() => {
    const tab = tabRef.current
    if (!tab || !tabReady || !followAlong || playbackSkipped) {
      tab?.setStemPlaybackActive(false)
      return
    }
    if (!clientSession) {
      setBridgeError({
        code: 'disconnected',
        message: 'Connect Spotify in Settings before using follow mode.',
      })
      return
    }
    const bridge = createSpotifyPlaybackBridge({
      clientSession,
      tab,
      onPlaybackState: setPlaybackState,
      onError: setBridgeError,
    })
    bridge.start()
    return () => {
      bridge.stop()
    }
  }, [clientSession, followAlong, playbackSkipped, tabReady])

  const handleAnalyze = (suggestion: DiscoverySuggestion) => {
    // Navigate to add-song with the job_id for one-tap analysis
    // Note: This is a one-tap deep-link to analyze, not directly to session play
    // The lesson must be loaded from the analyze job before entering session flow
    router.push({
      pathname: '/add-song',
      params: { jobId: suggestion.job_id },
    })
  }

  const listenOnSpotify = useCallback(async () => {
    if (!selectedLesson) {
      setLibraryLoadError('Select a song from Your Library first to open it in Spotify.')
      return
    }
    const title = selectedLesson.song_title?.trim() ?? ''
    const artist = selectedLesson.artist?.trim() ?? ''
    const query = [artist, title].filter(Boolean).join(' ').trim()
    if (!query) {
      setLibraryLoadError('This song is missing metadata for Spotify search.')
      return
    }
    const urls = spotifySearchUrls(query)

    // On web, open Spotify search in a new tab so Harmoniq keeps running.
    // expo-linking's web `openURL` sets `window.location`, which navigates the
    // current tab away from the app instead of opening the search.
    if (Platform.OS === 'web') {
      const url = urls[0]
      if (typeof window !== 'undefined' && url) {
        const opened = window.open(url, '_blank', 'noopener,noreferrer')
        if (opened) return
        // Popup blocked — fall back to same-tab navigation.
        try {
          await Linking.openURL(url)
          return
        } catch {
          // Fall through to the shared error below.
        }
      }
      setLibraryLoadError('Could not open Spotify. Allow pop-ups for Harmoniq and try again.')
      return
    }

    for (const url of urls) {
      try {
        await Linking.openURL(url)
        return
      } catch {
        // Try next URL variant.
      }
    }
    setLibraryLoadError('Could not open Spotify on this device.')
  }, [selectedLesson])

  return (
    <SafeAreaView className="flex-1 bg-wood-900" edges={['top', 'left', 'right']}>
      <ScrollView className="flex-1 px-5 py-4" contentContainerStyle={{ paddingBottom: 36 }}>
        <Text className="font-serif text-3xl text-cream">Discover</Text>
        <Text className="mt-1 font-sans text-sm text-cream/80">
          Song recommendations and your library — play along with Spotify while tabs follow in real time.
        </Text>

        {/* Active Listener */}
        <View className="mt-4">
          <ActiveListenerCard />
        </View>

        {recsError && <ErrorBanner message={recsError} variant="error" className="mt-4" />}

        {/* Library / Listening Mode status banners */}
        {libraryLoadError ? <ErrorBanner message={libraryLoadError} variant="error" className="mt-4" /> : null}
        {playbackSkipped ? (
          <ErrorBanner
            message="Spotify playback polling is disabled via HARMONIQ_SKIP_SPOTIFY_PLAYBACK=1."
            detail="The tab still loads in static study mode."
            variant="info"
            className="mt-4"
            dismissible={false}
          />
        ) : null}
        {bridgeError ? (
          <ErrorBanner
            message={spotifyBannerProps(bridgeError).message}
            variant={spotifyBannerProps(bridgeError).variant}
            className="mt-4"
            dismissible={false}
          />
        ) : null}

        {/* Recommended songs + Your Library — responsive two-column grid */}
        <View className={`mt-4 ${twoCol ? 'flex-row items-stretch gap-4' : 'flex-col gap-4'}`}>
          <DiscoverPanel
            Icon={Music}
            title="Recommended songs"
            subtitle="Personalized from your finished lessons"
            loading={recsLoading}
            loadingLabel="Loading recommendations…"
            items={
              suggestions.length
                ? suggestions.map((suggestion) => ({
                    key: suggestion.job_id,
                    title: suggestion.song_title || 'Unknown Song',
                    subtitle: suggestion.artist || 'Unknown Artist',
                    caption: suggestion.reasonLabel,
                    onPress: () => handleAnalyze(suggestion),
                  }))
                : undefined
            }
            emptyState={{
              Icon: Music,
              message: 'Complete more lessons to get personalized recommendations.',
              ctaLabel: 'Add a song to analyze',
              onCta: () => router.push('/add-song'),
            }}
          />
          <DiscoverPanel
            Icon={Library}
            title="Your Library"
            subtitle="Select a song for tabs & Spotify follow-along"
            loading={libraryLoading}
            loadingLabel="Loading songs…"
            items={
              libraryLessons.length
                ? libraryLessons.slice(0, 10).map((row) => ({
                    key: row.job_id,
                    title: row.song_title?.trim() || 'Untitled song',
                    subtitle: row.artist?.trim() || 'Unknown artist',
                    selected: row.job_id === selectedJobId,
                    onPress: () => setSelectedJobId(row.job_id),
                  }))
                : undefined
            }
            emptyState={{
              Icon: Library,
              message: 'No analyzed songs yet. Add one first from Home or Library.',
              ctaLabel: 'Add a song',
              onCta: () => router.push('/add-song'),
            }}
          />
        </View>

        {/* Spotify Controls */}
        <View className="mt-4 rounded-xl border border-wood-600/50 bg-wood-800/80 p-4 shadow-soft-wood">
          <View className="flex-row items-center justify-between gap-3">
            <View className="flex-1 pr-2">
              <View className="flex-row items-center gap-2">
                <Headphones size={16} color={colors.amber.accent} />
                <Text className="font-sans-medium text-sm text-cream">Follow along</Text>
              </View>
              <Text className="mt-1 font-sans text-xs text-cream/70">
                Sync tab cursor to Spotify playback position.
              </Text>
            </View>
            <Switch
              value={followAlong}
              onValueChange={setFollowAlong}
              disabled={playbackSkipped}
              trackColor={{ false: colors.wood[500], true: colors.amber.accent }}
              thumbColor={followAlong ? colors.cream : colors.wood[600]}
            />
          </View>
          <AnimatedPressable
            onPress={() => void listenOnSpotify()}
            haptic="medium"
            className="mt-4 rounded-lg bg-amber-accent/90 px-5 py-3.5"
          >
            <View className="flex-row items-center justify-center gap-2">
              <Headphones size={16} color={colors.wood[900]} />
              <Text className="text-center font-sans-medium text-sm text-wood-900">Listen on Spotify</Text>
            </View>
          </AnimatedPressable>
          <Text className="mt-2 font-sans text-[11px] text-cream/60">
            This opens Spotify search for the selected song. Harmoniq never starts/stops Spotify playback.
          </Text>
          {playbackState ? (
            <Text className="mt-3 font-sans text-xs text-cream">
              Now tracking:{' '}
              <Text className="font-sans-medium text-amber-accent">
                {playbackState.track_name?.trim() || 'Unknown track'}
              </Text>{' '}
              {playbackState.artists?.length ? `· ${playbackState.artists.join(', ')}` : ''} ·{' '}
              {playbackState.is_playing ? 'Playing' : 'Paused'}
            </Text>
          ) : null}
        </View>

      </ScrollView>
    </SafeAreaView>
  )
}
