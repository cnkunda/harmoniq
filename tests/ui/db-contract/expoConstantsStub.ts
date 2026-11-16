/**
 * Test-only stand-in for `expo-constants`: the real package pulls react-native
 * into the browser bundle. The db contract harness only needs `Constants`
 * to exist so `src/config.ts` falls back to its default API URL.
 */
const Constants = { expoConfig: undefined }

export default Constants
