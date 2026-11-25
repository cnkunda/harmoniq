// Read-only recon probe: can these modules load under Vitest/Vite transform?
const results: Record<string, string> = {}
for (const mod of ['react-native', 'expo-av', 'react-native-reanimated', 'expo-haptics', 'lucide-react-native']) {
  try {
    await import(mod)
    results[mod] = 'OK'
  } catch (e) {
    results[mod] = 'FAIL: ' + String(e).slice(0, 160).replace(/\n/g, ' ')
  }
}
console.log(JSON.stringify(results, null, 2))
