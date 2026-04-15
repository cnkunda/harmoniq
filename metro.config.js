const { getDefaultConfig } = require('expo/metro-config')
const { withNativeWind } = require('nativewind/metro')

const config = getDefaultConfig(__dirname)

if (!config.resolver.assetExts.includes('html')) {
  config.resolver.assetExts.push('html')
}
if (!config.resolver.assetExts.includes('sf2')) {
  config.resolver.assetExts.push('sf2')
}

// Python venv dirs (especially WSL-created `.venv-wsl` on NTFS) confuse Metro's file watcher
// (EACCES on `lib64` symlinks). They are never part of the JS bundle.
//
// Use an array of RegExps with explicit [\\/] — NOT `exclusionList([RegExp])` alone. On Windows,
// `exclusionList` rewrites `/` to `\` in patterns; FallbackWatcher then tests **relative** paths
// after `posixPathMatchesPattern` converts them to `/`, so backslash-only patterns never match
// and the walker still descends into `.venv-wsl` (see metro-file-map `common.posixPathMatchesPattern`).
// `(?:[/\\]|$)` after segment: walker's `filterDir` uses absolute dirs with no trailing sep,
// e.g. `...\backend\.venv-wsl` — a pattern that only allows `...\venv-wsl\` misses and the
// walker still descends into `lib64` (EACCES on WSL symlinks).
config.resolver.blockList = [
  /[/\\]__tests__(?:[/\\]|$)/,
  /^backend[/\\]\.venv-wsl(?:[/\\]|$)/,
  /[/\\]backend[/\\]\.venv-wsl(?:[/\\]|$)/,
  /^backend[/\\]\.venv(?:[/\\]|$)/,
  /[/\\]backend[/\\]\.venv(?:[/\\]|$)/,
  /[/\\]\.venv-wsl(?:[/\\]|$)/,
  /[/\\]\.venv(?:[/\\]|$)/,
]

module.exports = withNativeWind(config, { input: './global.css' })
