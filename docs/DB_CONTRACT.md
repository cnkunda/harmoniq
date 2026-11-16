# DB Contract Suite (Commit 17)

Shared behavioral contract tests for the dual persistence layer:

- **Native** — `src/db/client.native.ts` (SQLite via expo-sqlite)
- **Web** — `src/db/client.web.ts` (in-memory mirrors hydrated from IndexedDB)

The suite prevents silent divergence between the two platforms: one shared
case list runs against **both real storage engines** in CI.

## Shared case list

`src/db/contract/dbContractCases.ts` exports `DB_CONTRACT_CASES` — framework
free (no Vitest imports, it is bundled into a browser page) — plus
`runDbContractCases(client)` which collects one result per case.
Assertions come from `src/db/contract/contractAssert.ts`
(`equal`, `deepEqual`, `truthy`, `rejects`).

Every case is self-contained: it wipes practice state (`clearAllPracticeData`)
first, so cases never depend on execution order.

## Harnesses

| Leg | File | Engine | CI |
|-----|------|--------|-----|
| Native | `src/db/contract/client.native.contract.test.ts` | `node:sqlite` (`DatabaseSync`) behind a `vi.mock('expo-sqlite')` adapter | Vitest job |
| Web | `tests/ui/db-contract.web.spec.ts` + `tests/ui/db-contract/browser-entry.ts` | Real Chromium IndexedDB | Playwright job (`@smoke`) |

Run locally:

```bash
npm run test -- src/db/contract/client.native.contract.test.ts   # native leg
npx playwright test tests/ui/db-contract.web.spec.ts              # web leg (starts Expo web server)
```

### Native leg details

- `expo-sqlite` is **mocked** (factory) because the real module graph pulls in
  react-native, which cannot be parsed in Vitest's node environment. The mock
  implements `openDatabaseAsync` returning an adapter over Node's built-in
  `node:sqlite` (requires Node ≥ 22.13; fails loudly, never skips).
- `expo-constants` is mocked for the same reason (reached through the dynamic
  `lessonStore` import inside `getHomeSuggestion`).
- `__DEV__` is defined on `globalThis` (it is a Metro bundle global).

### Web leg details

- The Playwright spec builds `browser-entry.ts` with the Vite JS API
  (`write: false`, IIFE), serves a blank `/db-contract.html` via
  `page.route`, deletes the `harmoniq_web_v1` database, injects the bundle,
  and asserts zero failures.
- Two build-time aliases keep the bundle browser-safe: `expo-constants` →
  `tests/ui/db-contract/expoConstantsStub.ts`, and
  `@/src/stores/lessonStore` → `tests/ui/db-contract/lessonStoreStub.ts`
  (the real store's graph pulls react-native toast / async-storage).
- Results are reported via `window.__dbContractResult` (case names + errors).

## Coverage

17 core user-data cases: app prefs, onboarding flag, session journal/archive
ordering + upsert, latest-song lookup, node snippets, scored-session
idempotency (Commit 164 ledger), ghost references (Commit 75), jam snapshots
(upsert + null tolerance + summary lifecycle, Commit 160), practice plans
(Commit 162/164), licks, lessons, user feedback upsert + deterministic
ordering (Commit 159), analytics events (Commit 161),
`clearAllPracticeData`, and the home suggestion ready path.

Full coverage of all 40 `HarmoniqDbClient` methods is deferred; the suite
targets the methods where user data is at risk.

## Intentional platform differences

| Difference | Native | Web | Why it stays |
|---|---|---|---|
| Cross-store atomicity | `withTransactionAsync` wraps multi-table writes in one SQLite transaction | Each store is flushed as a separate IndexedDB transaction | A cross-store atomic abstraction would be a persistence rewrite (out of scope, Commit 17). `commitScoredSession` / `finalizePracticePlan` on web are therefore best-effort, not atomic. |
| Storage failure | Fails loudly (migration errors throw) | Degrades to memory-only (`initDb` catches IDB open failure) | Best-effort web demo behavior; the app stays usable. |
| Lesson store hydration | No-op (`hydrateWebLessonStore`) | Restores the last `LessonJSON` into Zustand from IDB | Web loses module state on reload; native keeps it in memory. |
| Schema evolution | Versioned SQL migrations (v1–v22) in `schema_migrations` table | Schemaless object stores; IDB `versionchange` creates missing stores (v1–v8) | IndexedDB has no columns, so column-only native migrations have no web equivalent. See `docs/MIGRATIONS.md` for the mapping. |
| Read self-init | Every read awaits `initDb()` | Several reads rely on a prior `initDb()` call | The harness always calls `initDb()` first; a future consistency pass may add self-init to web reads. |
| Row identity for feedback ties | `ORDER BY timestamp DESC, id DESC` (SQL) | Same comparator in JS | Converged by this commit (was: no tie-break on either platform). |
