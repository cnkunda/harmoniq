import { Linking, Platform } from 'react-native'

/** Open OS app settings (native only). */
export async function openHarmoniqAppSettings(): Promise<void> {
  if (Platform.OS === 'web') return
  try {
    await Linking.openSettings()
  } catch {
    /* ignore */
  }
}
