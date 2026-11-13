# Security Advisory Register

Last updated: 2026-11-12. This register tracks the npm advisories that remain
after the non-major dependency upgrades in Commit 6. Re-run the audit with:

```bash
npm audit --json
npm outdated --json
```

## Why `npm audit fix` is not used here

`npm audit fix --dry-run` plans to add 68 Expo `58.*` / React Native `0.88.*`
packages (a duplicate major tree) as peer resolution while keeping Expo 54 at
the root. That is the Commit 22 upgrade, not a non-major fix. Dependencies were
updated with targeted `npm install` / `npm update` instead, and the lockfile diff
was checked to contain no `58.` / `0.88.` additions.

## Snapshot

| Date | Critical | High | Moderate | Low | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-11-12 (before Commit 6) | 1 | 18 | 35 | 1 | 55 |
| 2026-11-12 (after Commit 6) | 0 | 5 | 29 | 1 | 35 |

Resolved in Commit 6: the critical `shell-quote` advisory and 13 highs
(`@react-navigation/core`, `@xmldom/xmldom`, `brace-expansion`, `browserslist`,
`compression`, `fast-uri`, `js-yaml`, `nanoid`, `node-forge`, `source-map-js`,
`tar`, `undici`, `vite`) plus the `vitest`/`@vitest/mocker` moderate. Remaining
moderate findings are Expo SDK 58, Detox major, Jest major, or transitive
majors; they are not individually listed because no non-major fix exists.

## Remaining high / critical findings

All five remaining highs require the Expo SDK 58 / React Native 0.88 upgrade
tracked as **Commit 22**. None of them is fixed in this commit.

| Package | Severity | Dependency path | Runtime reachability | Decision | Owner | Review |
| --- | --- | --- | --- | --- | --- | --- |
| `expo-router` | high | direct (`package.json`) | **Runtime** — app router parses web URLs and native deep links; advisory is a DoS via malformed percent-encoding | Tracked in **Commit 22** (`expo-router` 6.0.24 → 58.0.31) | `cnkunda` | 2026-12-12 |
| `query-string` | high | `expo-router → query-string@7.1.3` | **Runtime** — reached through `expo-router` URL parsing | Tracked in **Commit 22** (fixed only in the Expo 58 router line) | `cnkunda` | 2026-12-12 |
| `decode-uri-component` | high | `expo-router → query-string → decode-uri-component@0.2.2` | **Runtime** — reached through `query-string` decoding | Tracked in **Commit 22** | `cnkunda` | 2026-12-12 |
| `postcss` | high | `expo → @expo/metro-config@54.0.16 → postcss@8.4.49` | **Build-time only** — Metro CSS pipeline; not shipped to the app runtime | Pinned by Expo 54 (`@expo/metro-config` requires `~8.4.32`); track in **Commit 22** | `cnkunda` | 2026-12-12 |
| `image-size` | high | `expo → @expo/metro@54.2.0 → metro@0.83.3 → image-size@1.2.1` | **Build-time only** — Metro image parsing; not shipped to the app runtime | `metro` requires `image-size@^1.0.2`; fix is `2.x`, only in the Expo 58 Metro line — **Commit 22** | `cnkunda` | 2026-12-12 |

## Remaining moderate findings (summary)

| Group | Packages | Reachability | Decision |
| --- | --- | --- | --- |
| Expo SDK 54 | `expo`, `expo-asset`, `expo-auth-session`, `expo-constants`, `expo-linking`, `expo-sharing`, `expo-splash-screen`, `@expo/config*`, `@expo/prebuild-config`, `@expo/fingerprint`, `@expo/metro-config`, `uuid`, `xcode`, `glob`, `minimatch` | build / prebuild / dev server | **Commit 22** |
| Detox | `detox`, `bunyamin`, `jest-environment-emit`, `stream-json` | mobile E2E only | upgrade with a Detox major (not runtime) |
| Jest | `jest`, `jest-circus`, `@jest/core`, `@jest/reporters`, `jest-cli`, `jest-config`, `jest-runner`, `jest-runtime` | test runner only | upgrade with a Jest major (not runtime) |
| Low | `deepmerge` | build (Expo config merge) | **Commit 22** |

## Review cadence

- **Monthly**, or whenever `npm audit` reports a new high/critical: re-run the
  snapshot, update this register, and confirm the Commit 22 tracking is still
  accurate.
- Next review: 2026-12-12. Owner: `cnkunda`.
