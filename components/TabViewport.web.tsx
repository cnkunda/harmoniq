import { forwardRef, useCallback, useEffect, useState } from 'react'
import { Pressable, Text, View } from 'react-native'
import Animated, { FadeIn, FadeOut } from 'react-native-reanimated'

import type { AlphaTabSurfaceRef, SongScoreMeta } from '@/types/tabMessage'
import { LyricsStrip } from './LyricsStrip'
import { AlphaTabWeb } from './AlphaTabWeb'
import type { TabViewportProps } from './TabViewport.types'
import { getAppPref, setAppPref } from '@/src/db/client'
import { PREF_SHOW_LYRICS } from '@/src/db/schema'

export type { TabViewportProps } from './TabViewport.types'

/** Web: DOM AlphaTab — no `react-native-webview` in this bundle graph (PRIORITIES §22). */
export const TabViewport = forwardRef<AlphaTabSurfaceRef, TabViewportProps>(
  function TabViewport(
    {
      gp5Base64,
      prerenderArtifactUrl,
      audioSrc,
      transposeSemitones,
      soundFontProfile,
      renderPreset,
      style,
      onReady,
      onError,
      onNoteEvent,
      onScoreSeekMs,
      readOnlyFollowMode,
      onSongDetails,
      onSongPlayback,
      runtimeDiagnosticsEnabled,
      lyricWords,
      playbackSec,
      songTitle,
      songArtist,
      tabVariant,
      hasFull,
      hasSkeleton,
      hasAlt,
      onTabVariantChange,
      onSeekToStart,
    },
    ref,
  ) {
    const [songMeta, setSongMeta] = useState<SongScoreMeta | null>(null)
    const [showLyrics, setShowLyrics] = useState(true)

    // Persist showLyrics preference (Commit 97)
    useEffect(() => {
      void getAppPref(PREF_SHOW_LYRICS).then((v) => {
        if (v === '0') setShowLyrics(false)
      })
    }, [])

    const handleShowLyricsToggle = useCallback(() => {
      setShowLyrics((prev) => {
        const next = !prev
        void setAppPref(PREF_SHOW_LYRICS, next ? '1' : '0')
        return next
      })
    }, [])

    const handleSongDetails = useCallback((meta: SongScoreMeta) => {
      setSongMeta(meta)
      onSongDetails?.(meta)
    }, [onSongDetails])

    const isLight = renderPreset === 'light'
    const cardBg = isLight ? 'bg-ivory' : 'bg-[#2B1D0E]'
    const dividerBorder = isLight ? 'border-wood-600/20' : 'border-wood-600/40'
    const textColor = isLight ? 'text-wood-900' : 'text-cream'
    const pillBase = isLight ? 'border-wood-600/30 bg-cream-dark/40' : 'border-wood-600/35 bg-transparent'
    const pillActiveBase = 'border-amber-accent bg-amber-accent/10'

    const displayTitle = songTitle || songMeta?.title
    const displayArtist = songArtist || songMeta?.artist
    const hasLyrics = lyricWords && lyricWords.length > 0
    const hasVariantControls = !!onTabVariantChange
    const showHeader = displayTitle || displayArtist || hasVariantControls || hasLyrics || !!onSeekToStart

    const variantPill = (v: 'full' | 'skeleton' | 'alt', label: string, available?: boolean) => {
      if (!available) return null
      const active = tabVariant === v
      return (
        <Pressable
          key={v}
          onPress={() => onTabVariantChange?.(v)}
          className={`rounded-full border px-2.5 py-1 ${active ? pillActiveBase : pillBase}`}
          accessibilityRole="button"
        >
          <Text className={`font-sans-medium text-[10px] uppercase tracking-wide ${active ? 'text-amber-accent' : 'text-muted-brown'}`}>{label}</Text>
        </Pressable>
      )
    }

    return (
      <View style={[style, { overflow: 'hidden' }]} className={`flex-1 flex-col rounded-xl border border-wood-600/40 ${cardBg}`}>
        {/* Header: left = title/artist, right = controls */}
        {showHeader && (
          <View className={`flex-row items-center gap-3 border-b ${dividerBorder} px-3 py-2.5`}>
            {/* Left: song info */}
            <View className="flex-1 justify-center">
              {displayTitle && (
                <Text className={`font-sans-semibold text-[13px] leading-tight ${textColor}`} numberOfLines={1}>
                  {displayTitle}
                </Text>
              )}
              {displayArtist && (
                <Text className="font-sans text-[11px] leading-tight text-muted-brown" numberOfLines={1}>
                  {displayArtist}
                </Text>
              )}
              {songMeta?.tempoBpm ? (
                <Text className="font-sans text-[10px] leading-tight text-amber-accent/80">
                  {Math.round(songMeta.tempoBpm)} BPM
                </Text>
              ) : null}
            </View>

            {/* Right: pill controls */}
            <View className="flex-row flex-wrap items-center justify-end gap-1.5">
              {variantPill('full', 'Full', hasFull)}
              {variantPill('skeleton', 'Skeleton', hasSkeleton)}
              {variantPill('alt', 'Alt', hasAlt)}
              {hasLyrics && (
                <Pressable
                  onPress={handleShowLyricsToggle}
                  className={`rounded-full border px-2.5 py-1 ${showLyrics ? pillActiveBase : pillBase}`}
                  accessibilityRole="button"
                >
                  <Text className={`font-sans-medium text-[10px] uppercase tracking-wide ${showLyrics ? 'text-amber-accent' : 'text-muted-brown'}`}>Lyrics</Text>
                </Pressable>
              )}
              {onSeekToStart && (
                <Pressable
                  onPress={onSeekToStart}
                  className={`rounded-full border px-2.5 py-1 ${pillBase}`}
                  accessibilityRole="button"
                >
                  <Text className="font-sans-medium text-[10px] uppercase tracking-wide text-muted-brown">⏮ Start</Text>
                </Pressable>
              )}
            </View>
          </View>
        )}

        {/* AlphaTab Canvas */}
        <View className="flex-1" style={{ minHeight: 220 }}>
          <AlphaTabWeb
            ref={ref}
            gp5Base64={gp5Base64}
            prerenderArtifactUrl={prerenderArtifactUrl}
            audioSrc={audioSrc}
            transposeSemitones={transposeSemitones}
            soundFontProfile={soundFontProfile}
            renderPreset={renderPreset}
            runtimeDiagnosticsEnabled={runtimeDiagnosticsEnabled}
            style={{ flex: 1, backgroundColor: 'transparent' }}
            onReady={onReady}
            onError={onError}
            onNoteEvent={onNoteEvent}
            onScoreSeekMs={onScoreSeekMs}
            readOnlyFollowMode={readOnlyFollowMode}
            onSongDetails={handleSongDetails}
            onSongPlayback={onSongPlayback}
          />
        </View>

        {/* Lyrics Footer — animated to prevent layout shift */}
        {showLyrics && hasLyrics && (
          <Animated.View
            entering={FadeIn.duration(200)}
            exiting={FadeOut.duration(150)}
            className={`border-t ${dividerBorder} px-3 py-2.5`}
          >
            <LyricsStrip words={lyricWords} playbackSec={playbackSec ?? 0} hideHeading />
          </Animated.View>
        )}
      </View>
    )
  },
)

