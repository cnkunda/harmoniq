module.exports = function (api) {
  api.cache(true)
  return {
    presets: [
      ['babel-preset-expo', { jsxImportSource: 'nativewind' }],
      'nativewind/babel',
    ],
    env: {
      // Commit 19: strip debug-level console noise from release bundles.
      // warn/error stay — they are support diagnostics (see AGENTS.md Logging).
      production: {
        plugins: [['transform-remove-console', { exclude: ['error', 'warn'] }]],
      },
    },
  }
}
