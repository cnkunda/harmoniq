import * as FileSystem from 'expo-file-system/legacy'
import { Platform } from 'react-native'

/** Write server-returned base64 audio to a playable local URI; `release` revokes blob or deletes temp file. */
export async function prepareJamBackingPlayable(
  audioBase64: string,
  mimeType: string,
): Promise<{ uri: string; release: () => void }> {
  if (Platform.OS === 'web') {
    const binary = Uint8Array.from(atob(audioBase64), (c) => c.charCodeAt(0))
    const blob = new Blob([binary], { type: mimeType || 'audio/wav' })
    const uri = URL.createObjectURL(blob)
    return {
      uri,
      release: () => URL.revokeObjectURL(uri),
    }
  }
  const dir = FileSystem.cacheDirectory
  if (!dir) {
    throw new Error('Cache directory not available for jam backing.')
  }
  const path = `${dir}jam-backing-${Date.now()}.wav`
  await FileSystem.writeAsStringAsync(path, audioBase64, { encoding: FileSystem.EncodingType.Base64 })
  return {
    uri: path,
    release: () => {
      void FileSystem.deleteAsync(path, { idempotent: true })
    },
  }
}
