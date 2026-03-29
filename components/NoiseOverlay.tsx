import { Platform, StyleSheet, View, type ViewStyle } from 'react-native'

/* Subtle full-screen grain. Native: no texture in 0.1 (commit 0.3 adds PNG).
   Web: inline SVG noise via RN-web backgroundImage on View. */
const NOISE_DATA_URI =
  'url("data:image/svg+xml,%3Csvg viewBox=\'0 0 200 200\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cfilter id=\'n\'%3E%3CfeTurbulence type=\'fractalNoise\' baseFrequency=\'0.85\' numOctaves=\'3\' stitchTiles=\'stitch\'/%3E%3C/filter%3E%3Crect width=\'100%25\' height=\'100%25\' filter=\'url(%23n)\'/%3E%3C/svg%3E")'

export function NoiseOverlay() {
  if (Platform.OS !== 'web') {
    return null
  }

  const webGrain: ViewStyle = {
    ...StyleSheet.absoluteFillObject,
    opacity: 0.03,
    zIndex: 50,
    // react-native-web forwards to CSS
    backgroundImage: NOISE_DATA_URI,
    mixBlendMode: 'overlay',
  }

  return <View pointerEvents="none" style={webGrain} />
}
