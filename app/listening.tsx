import { useFocusEffect } from '@react-navigation/native'
import { useRouter } from 'expo-router'
import * as Linking from 'expo-linking'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Platform, ScrollView, Switch, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { ErrorBanner } from '@/components/ErrorBanner'
import { TabViewport } from '@/components/TabViewport'
import {
  createSpotifyPlaybackBridge,
  isSpotifyPlaybackBridgeSkipped,
  type SpotifyPlaybackBridgeError,
} from '@/src/audio/spotifyPlaybackBridge'
import { getAppPref, getLessonByJobId, listLessonsJournal } from '@/src/db/client'
import { PREF_SPOTIFY_CLIENT_SESSION } from '@/src/db/schema'
import type { LessonListRow } from '@/src/db/types'
import type { LessonJSON, SpotifyPlaybackStatePayload } from '@/src/types'
import { readSectionTabPayloads } from '@/src/utils/lessonTabs'
import { lessonStemUrl, stemRelPathToPlaybackUri } from '@/src/utils/lessonAudio'
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

export default function ListeningScreen() {
  const router = useRouter()
  const tabRef = useRef<AlphaTabSurfaceRef>(null)

  const [lessons, setLessons] = useState<LessonListRow[]>([])
  const [selectedJobId, setSelectedJobId] = useState<string>('')
  const [selectedLesson, setSelectedLesson] = useState<LessonJSON | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [tabReady, setTabReady] = useState(false)
  const [followAlong, setFollowAlong] = useState(true)
  const [clientSession, setClientSession] = useState<string>('')
  const [playbackState, setPlaybackState] = useState<SpotifyPlaybackStatePayload | null>(null)
  const [bridgeError, setBridgeError] = useState<SpotifyPlaybackBridgeError | null>(null)

  const playbackSkipped = isSpotifyPlaybackBridgeSkipped()

  const loadLibrary = useCallback(() => {
    setLoading(true)
    setLoadError(null)
    void listLessonsJournal()
      .then((rows) => {
        setLessons(rows)
        const first = rows[0]?.job_id ?? ''
        setSelectedJobId((prev) => prev || first)
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : 'Could not load analyzed songs.'))
      .finally(() => setLoading(false))
  }, [])

  useFocusEffect(
    useCallback(() => {
      loadLibrary()
    }, [loadLibrary]),
  )

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

  useEffect(() => {
    let cancelled = false
    if (!selectedJobId) {
      setSelectedLesson(null)
      return () => {
        cancelled = true
      }
    }
    setLoadError(null)
    setTabReady(false)
    void getLessonByJobId(selectedJobId)
      .then((lesson) => {
        if (cancelled) return
        if (!lesson) {
          setLoadError('Could not load this analyzed song.')
          setSelectedLesson(null)
          return
        }
        setSelectedLesson(lesson)
      })
      .catch((e) => {
        if (cancelled) return
        setSelectedLesson(null)
        setLoadError(e instanceof Error ? e.message : 'Could not load this analyzed song.')
      })
    return () => {
      cancelled = true
    }
  }, [selectedJobId])

  const section = selectedLesson?.sections?.[0]
  const tabs = useMemo(() => readSectionTabPayloads(section), [section])
  /** MusicXML is primary (Commit 107); GP5 falls back when absent. */
  const lessonMusicXml = selectedLesson?.musicxml?.trim() ?? null
  const gp5Base64 = lessonMusicXml ? null : tabs.full ?? tabs.skeleton ?? tabs.alt ?? null
  const audioSrc = useMemo(() => {
    const rel = selectedLesson?.stems?.guitar
    if (!rel || typeof rel !== 'string') return null
    return stemRelPathToPlaybackUri(rel) ?? lessonStemUrl(rel)
  }, [selectedLesson?.stems?.guitar])

  useEffect(() => {
    setBridgeError(null)
    setPlaybackState(null)
  }, [selectedJobId, followAlong])

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

  const listenOnSpotify = useCallback(async () => {
    if (!selectedLesson) return
    const title = selectedLesson.song_title?.trim() ?? ''
    const artist = selectedLesson.artist?.trim() ?? ''
    const query = [artist, title].filter(Boolean).join(' ').trim()
    if (!query) {
      setLoadError('This song is missing metadata for Spotify search.')
      return
    }
    const urls = spotifySearchUrls(query)
    for (const url of urls) {
      try {
        await Linking.openURL(url)
        return
      } catch {
        // Try next URL variant.
      }
    }
    setLoadError('Could not open Spotify on this device.')
  }, [selectedLesson])

  return (
    <SafeAreaView className="flex-1 bg-wood-900" edges={['top', 'left', 'right']}>
      <ScrollView className="flex-1 px-6 py-6" contentContainerStyle={{ paddingBottom: 36 }}>
        <Text className="font-serif text-3xl text-cream">Listening mode</Text>
        <Text className="mt-2 font-sans text-sm text-muted-brown">
          Play a Spotify track while Harmoniq follows the tab in real time.
        </Text>

        {loadError ? <ErrorBanner message={loadError} variant="error" className="mt-4" /> : null}
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

        <View className="mt-6 rounded-xl border border-wood-600/50 bg-wood-800/80 p-4">
          <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">Analyzed songs</Text>
          {loading ? <Text className="mt-3 font-sans text-sm text-muted-brown">Loading songs…</Text> : null}
          {!loading && lessons.length === 0 ? (
            <Text className="mt-3 font-sans text-sm text-muted-brown">
              No analyzed songs yet. Add one first from Home or Library.
            </Text>
          ) : (
            <View className="mt-3 gap-2">
              {lessons.slice(0, 10).map((row) => {
                const selected = row.job_id === selectedJobId
                return (
                  <AnimatedPressable
                    key={row.job_id}
                    onPress={() => setSelectedJobId(row.job_id)}
                    haptic="light"
                    className={`rounded-lg border px-3 py-2.5 ${
                      selected ? 'border-amber-accent bg-amber-accent/15' : 'border-wood-600/45 bg-wood-900/40'
                    }`}
                  >
                    <Text className={`font-sans-medium text-sm ${selected ? 'text-amber-light' : 'text-cream'}`}>
                      {row.song_title?.trim() || 'Untitled song'}
                    </Text>
                    <Text className="mt-0.5 font-sans text-xs text-muted-brown">
                      {row.artist?.trim() || 'Unknown artist'}
                    </Text>
                  </AnimatedPressable>
                )
              })}
            </View>
          )}
        </View>

        <View className="mt-4 rounded-xl border border-wood-600/50 bg-wood-800/80 p-4">
          <View className="flex-row items-center justify-between gap-3">
            <View className="flex-1 pr-2">
              <Text className="font-sans-medium text-sm text-cream">Follow along</Text>
              <Text className="mt-1 font-sans text-xs text-muted-brown">
                Sync tab cursor to Spotify playback position.
              </Text>
            </View>
            <Switch value={followAlong} onValueChange={setFollowAlong} disabled={playbackSkipped} />
          </View>
          <AnimatedPressable
            onPress={() => void listenOnSpotify()}
            haptic="medium"
            className="mt-4 rounded-lg bg-amber-accent/90 px-4 py-3"
          >
            <Text className="text-center font-sans-medium text-sm text-wood-900">Listen on Spotify</Text>
          </AnimatedPressable>
          <Text className="mt-2 font-sans text-[11px] text-muted-brown">
            This opens Spotify search for the selected song. Harmoniq never starts/stops Spotify playback.
          </Text>
          {playbackState ? (
            <Text className="mt-3 font-sans text-xs text-cream">
              Now tracking:{' '}
              <Text className="font-sans-medium text-amber-light">
                {playbackState.track_name?.trim() || 'Unknown track'}
              </Text>{' '}
              {playbackState.artists?.length ? `· ${playbackState.artists.join(', ')}` : ''} ·{' '}
              {playbackState.is_playing ? 'Playing' : 'Paused'}
            </Text>
          ) : null}
        </View>

        <View className="mt-4 h-[340px] w-full">
          <TabViewport
            ref={tabRef}
            gp5Base64={gp5Base64}
            musicXml={lessonMusicXml}
            audioSrc={audioSrc}
            renderPreset="listen"
            runtimeDiagnosticsEnabled={false}
            readOnlyFollowMode
            onReady={() => setTabReady(true)}
            onError={(message) => setLoadError(message)}
            style={{ flex: 1, height: '100%', width: '100%' }}
          />
        </View>

        <AnimatedPressable
          onPress={() => router.back()}
          className="mt-6 rounded-lg border border-wood-600/45 bg-cream-dark/45 px-4 py-3"
        >
          <Text className="text-center font-sans-medium text-wood-900">Back</Text>
        </AnimatedPressable>
      </ScrollView>
    </SafeAreaView>
  )
}
