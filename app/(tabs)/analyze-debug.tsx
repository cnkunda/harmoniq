import * as DocumentPicker from 'expo-document-picker'
import { useRouter } from 'expo-router'
import { useCallback, useState } from 'react'
import { Platform, Pressable, ScrollView, Text, TextInput, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { AudioDropzone } from '@/components/AudioDropzone'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingSkeleton } from '@/components/LoadingSkeleton'
import { API_BASE_URL } from '@/src/config'
import colors from '@/src/constants/colors'
import { sessionEntryHref } from '@/src/constants/sessionFlow'
import { useSessionPrefsStore } from '@/src/stores/sessionPrefsStore'
import { useLessonStore } from '@/src/stores/lessonStore'

export default function AnalyzeDebugScreen() {
  const router = useRouter()
  const [url, setUrl] = useState('')
  const [pickError, setPickError] = useState<string | null>(null)
  const jobId = useLessonStore((s) => s.jobId)
  const status = useLessonStore((s) => s.status)
  const lesson = useLessonStore((s) => s.lesson)
  const error = useLessonStore((s) => s.error)
  const analyzeFromUrl = useLessonStore((s) => s.analyzeFromUrl)
  const analyzeFromFile = useLessonStore((s) => s.analyzeFromFile)
  const clearError = useLessonStore((s) => s.clearError)

  const isLoading = status === 'submitting' || status === 'processing'

  const onAnalyzeUrl = useCallback(() => {
    setPickError(null)
    void analyzeFromUrl(url)
  }, [analyzeFromUrl, url])

  const onPickFile = useCallback(async () => {
    const result = await DocumentPicker.getDocumentAsync({
      type: ['audio/*', 'audio/mpeg', 'audio/wav', 'audio/x-m4a', 'audio/mp4'],
      copyToCacheDirectory: true,
    })
    if (result.canceled || !result.assets?.[0]) return
    const asset = result.assets[0]
    setPickError(null)
    try {
      const res = await fetch(asset.uri)
      const blob = await res.blob()
      void analyzeFromFile(blob, asset.name ?? 'upload.mp3')
    } catch {
      setPickError('Could not read the selected file.')
    }
  }, [analyzeFromFile])

  const sectionCount = lesson?.sections?.length ?? 0
  const title = lesson?.song_title?.trim() || '(no title)'

  return (
    <SafeAreaView className="flex-1 bg-wood-900" edges={['top', 'left', 'right']}>
      <ScrollView
        className="flex-1 px-6 py-6"
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ paddingBottom: 32 }}
      >
        <Text className="text-2xl font-serif text-amber-accent">Analyze (debug)</Text>
        <Text className="mt-1 font-sans text-xs text-muted-brown">
          Backend: {API_BASE_URL}
        </Text>
        <Text className="mt-2 font-sans text-sm text-cream">
          Paste a YouTube URL or upload audio. Uses commit 18 lesson store +{' '}
          <Text className="font-mono text-xs text-muted-brown">src/api/analyze.ts</Text>.
        </Text>

        {error ? (
          <ErrorBanner
            message={error}
            variant="error"
            className="mt-4"
            action={{ label: 'Dismiss', onPress: clearError }}
          />
        ) : null}
        {pickError ? (
          <ErrorBanner
            message={pickError}
            variant="error"
            className="mt-4"
            action={{ label: 'Dismiss', onPress: () => setPickError(null) }}
          />
        ) : null}

        <View className="mt-6 gap-2">
          <Text className="font-sans-medium text-sm text-cream">YouTube URL</Text>
          <TextInput
            value={url}
            onChangeText={setUrl}
            placeholder="https://www.youtube.com/watch?v=…"
            placeholderTextColor={colors.muted.brown}
            autoCapitalize="none"
            autoCorrect={false}
            editable={!isLoading}
            className="rounded-xl border border-wood-600 bg-wood-800 px-4 py-3 font-sans text-sm text-cream"
          />
          <Pressable
            onPress={onAnalyzeUrl}
            disabled={isLoading || !url.trim()}
            className="mt-2 rounded-lg bg-amber-accent px-4 py-3 disabled:opacity-40"
            accessibilityRole="button"
          >
            <Text className="text-center font-sans-medium text-wood-900">Analyze URL</Text>
          </Pressable>
        </View>

        {Platform.OS === 'web' ? (
          <View className="mt-8">
            <Text className="mb-2 font-sans-medium text-sm text-cream">Or drop a file (web)</Text>
            <AudioDropzone
              onFile={(file) => {
                setPickError(null)
                const name = file instanceof File ? file.name : 'upload.mp3'
                void analyzeFromFile(file, name)
              }}
            />
          </View>
        ) : (
          <Pressable
            onPress={() => void onPickFile()}
            disabled={isLoading}
            className="mt-8 rounded-lg border border-amber-accent px-4 py-3 disabled:opacity-40"
            accessibilityRole="button"
          >
            <Text className="text-center font-sans-medium text-amber-light">Pick audio file</Text>
          </Pressable>
        )}

        {isLoading ? (
          <View className="mt-8 gap-3">
            <Text className="font-sans-medium text-sm text-cream">Analyzing…</Text>
            <LoadingSkeleton width="100%" height={16} borderRadius={8} />
            <LoadingSkeleton width="70%" height={16} borderRadius={8} />
            <LoadingSkeleton width="100%" height={72} borderRadius={12} />
            {jobId ? (
              <Text className="font-mono text-xs text-muted-brown">job: {jobId}</Text>
            ) : null}
          </View>
        ) : null}

        {status === 'complete' && lesson ? (
          <View className="mt-8 rounded-xl border border-wood-600 bg-wood-800 p-4">
            <Text className="font-sans-medium text-sm text-amber-light">Lesson result</Text>
            <Text className="mt-2 font-sans text-cream">
              Title: <Text className="font-sans-medium">{title}</Text>
            </Text>
            <Text className="mt-1 font-sans text-cream">
              Sections: <Text className="font-sans-medium">{sectionCount}</Text>
            </Text>
            <Pressable
              onPress={() => router.push(sessionEntryHref(useSessionPrefsStore.getState().skipTuneStep))}
              className="mt-4 rounded-lg bg-amber-accent px-4 py-3"
              accessibilityRole="button"
            >
              <Text className="text-center font-sans-medium text-wood-900">Continue to session</Text>
            </Pressable>
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  )
}
