import { Image, StyleSheet, View } from 'react-native'

const noisePng = require('../assets/images/noise.png')

/**
 * Tiled grain fallback for iOS / Android. Opacity matches web (~3%).
 * Asset: `assets/images/noise.png` (procedural RGB noise).
 */
export function NoiseOverlay() {
  return (
    <View pointerEvents="none" style={[StyleSheet.absoluteFillObject, { zIndex: 50 }]} collapsable={false}>
      <Image
        source={noisePng}
        accessibilityElementsHidden
        importantForAccessibility="no-hide-descendants"
        style={[StyleSheet.absoluteFillObject, { opacity: 0.03 }]}
        resizeMode="repeat"
      />
    </View>
  )
}
