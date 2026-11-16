# Database Migration Strategy

**Commit 88** implements a versioned database migration system to prevent data loss during app updates as the `LessonJSON` structure evolves.

## Overview

The migration system provides:
- **Version tracking**: Each migration has a unique version number
- **Rollback support**: Failed migrations can be rolled back to previous state
- **Data validation**: Ensures mastery percentages and practice history are preserved
- **Platform parity**: Consistent behavior across native (SQLite) and web (IndexedDB)

## Native (SQLite) Migrations

### Location
- Schema definitions: `src/db/schema.ts`
- Migration runner: `src/db/client.native.ts` (applyMigrations function)
- Validation utilities: `src/db/migrations.ts`

### Version Tracking
Migrations are tracked in the `schema_migrations` table:
```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);
```

### Migration Pattern
Each migration includes:
- **Up SQL**: Schema changes to apply
- **Down SQL**: Rollback SQL to undo changes
- **Validation**: Optional pre-migration data checks

Example:
```typescript
if (current < 14) {
  const cols = await db.getAllAsync<{ name: string }>('PRAGMA table_info(skill_nodes)')
  const names = new Set((cols ?? []).map((c) => c.name))
  if (!names.has('schema_version')) {
    await applyMigrationWithRollback(
      14,
      MIGRATION_V14_SKILL_NODES_SCHEMA_VERSION,
      ROLLBACK_V14_SKILL_NODES_SCHEMA_VERSION,
      async () => validateSkillNodesPreservation(getAllSkillNodes)
    )
  }
}
```

### Rollback Mechanism
If a migration fails:
1. The error is logged with `logMigration()`
2. The rollback SQL is executed automatically
3. The transaction is aborted, leaving the database at the previous version
4. The app will retry the migration on next startup

### Current Migration Versions
- V1: Initial schema (skill_nodes, sessions, licks, jam_snapshots)
- V2: Add sm2_repetitions to skill_nodes
- V3: Add app_prefs table
- V4: Add review_snapshot, waveform paths to sessions
- V5: Add stems_json to licks
- V6: Add context fields to jam_snapshots
- V7: Add reliability fields to jam_snapshots
- V8: Add lessons table
- V9: Add technique_roll_json to skill_nodes
- V10: Add practice_plan_completions table
- V11: Add ghost reference fields to sessions
- V12: Add ghost_recording_mime to sessions
- V13: Add mood to sessions
- V14: Add schema_version to skill_nodes (Jazz Extensions support)
- V15: Add summary_bundle_json and phrases_json to jam_snapshots
- V16: Add inferred_mode to jam_snapshots (Milestone B — Commit B3)
- V17: Add user_feedback table + job/dedupe indexes (Commit 159)
- V18: Add summary_status to jam_snapshots (Commit 160; web IndexedDB is schemaless, no version bump)
- V19: Add analytics_events table + type/timestamp indexes (Commit 161)
- V20: Add practice_plans active-plan persistence table + status/updated index (Commit 162)
- V21: Add practice_plans.session_id + applied_sessions replay ledger (Commit 164)
- V22: Add jam_snapshots backing-bed context columns (J6; web IndexedDB is schemaless, no version bump)

## Web (IndexedDB) Migrations

### Location
- Migration runner: `src/db/idbWeb.ts` (openHarmoniqIdb function)
- Current version: 8

### Version Tracking
Migrations are tracked in the `schema_migrations` object store:
```typescript
type MigrationRow = { version: number; applied_at: string }
```

> **Note:** the `schema_version` field written on web skill-node rows
> (`src/db/client.web.ts`, value `1`) is the **skill-node row schema version**
> (matches native migration V14), **not** the IndexedDB database version.
> The database version is `DB_VERSION` in `src/db/idbWeb.ts` (currently 8).

### Migration Pattern
IndexedDB uses built-in versioning:
```typescript
const DB_VERSION = 8
const r = indexedDB.open(DB_NAME, DB_VERSION)
r.onupgradeneeded = (event) => {
  const oldVersion = (event as IDBVersionChangeEvent).oldVersion
  // Apply schema changes based on version
}
```

### Rollback Mechanism
IndexedDB provides automatic rollback:
- If `onupgradeneeded` throws an error, the transaction is aborted
- The database remains at the previous version
- No manual rollback SQL needed

### Current Migration Versions
- V1-V3: Initial object stores (prefs, sessions, skill_nodes, licks, jams, lesson cache, lessons, plan_completions)
- V4: Add schema_migrations tracking store
- V5: Add user_feedback store with job_id index (Commit 159)
- V6: Add analytics_events store with timestamp index (Commit 161)
- V7: Add practice_plans store with status/updated index (Commit 162)
- V8: Add applied_sessions store with plan_id index for scored-session replay guard (Commit 164)

## Data Validation

### Skill Nodes Validation
Ensures mastery percentages (score) are preserved:
```typescript
export async function validateSkillNodesPreservation(
  getNodes: () => Promise<{ id: string; score: number }[]>,
): Promise<{ valid: boolean; error?: string }>
```
- Validates scores are finite numbers between 0 and 1
- Returns error if validation fails

### Sessions Validation
Ensures session count is preserved:
```typescript
export async function validateSessionsPreservation(
  getSessionCount: () => Promise<number>,
): Promise<{ valid: boolean; error?: string }>
```

## Adding New Migrations

### Native (SQLite)

1. Add migration SQL to `src/db/schema.ts`:
```typescript
export const MIGRATION_V18_EXAMPLE = 'ALTER TABLE skill_nodes ADD COLUMN new_field TEXT'
export const ROLLBACK_V18_EXAMPLE = 'ALTER TABLE skill_nodes DROP COLUMN IF EXISTS new_field'
```

2. Add imports to `src/db/client.native.ts`:
```typescript
import {
  MIGRATION_V18_EXAMPLE,
  ROLLBACK_V18_EXAMPLE,
  // ... other imports
} from '@/src/db/schema'
```

3. Add migration logic to `applyMigrations()`:
```typescript
if (current < 18) {
  const cols = await db.getAllAsync<{ name: string }>('PRAGMA table_info(skill_nodes)')
  const names = new Set((cols ?? []).map((c) => c.name))
  if (!names.has('new_field')) {
    await applyMigrationWithRollback(18, MIGRATION_V18_EXAMPLE, ROLLBACK_V18_EXAMPLE)
  }
}
```

4. Update types in `src/db/types.ts` if needed:
```typescript
export type SkillNodeRow = {
  // ... existing fields
  new_field?: string | null
}
```

### Web (IndexedDB)

1. Increment `DB_VERSION` in `src/db/idbWeb.ts`:
```typescript
const DB_VERSION = 9
```

2. Add version-specific logic in `onupgradeneeded`:
```typescript
if (oldVersion < 9) {
  // Add new object store or modify existing
  if (!db.objectStoreNames.contains(S_NEW_STORE)) {
    db.createObjectStore(S_NEW_STORE, { keyPath: 'id' })
  }
  // Record migration
  const tx = r.transaction
  if (tx) {
    const migrationStore = tx.objectStore(S_MIGRATIONS)
    migrationStore.put({ version: 9, applied_at: new Date().toISOString() })
  }
}
```

## Native ↔ Web version mapping (Commit 17)

Web is schemaless (object stores of JSON rows), so the two version sequences
are **not numerically aligned and must never be renumbered into each other** —
web users already exist on v1–v8 and renumbering would invent meaningless
"schemaless migrations". The mapping below is feature-based; keep it updated
when either side gains a migration.

| Feature | Native | Web |
|---|---|---|
| Initial stores: skill_nodes, sessions, licks, jam_snapshots (+ prefs, lesson cache, lessons, plan completions) | V1–V3 | V1–V3 |
| schema_migrations tracking store | — (native tracks versions natively) | V4 |
| review_snapshot + waveform paths on sessions | V4 | schemaless (row fields) |
| stems_json on licks | V5 | schemaless |
| jam context / reliability fields | V6–V7 | schemaless |
| lessons table | V8 | store existed since V1 |
| technique_roll_json, skill_nodes.schema_version | V9, V14 | schemaless (row fields; `schema_version: 1` written by `client.web.ts`) |
| practice_plan_completions | V10 | store existed since V1 |
| ghost fields + mime + mood on sessions | V11–V13 | schemaless |
| jam summary fields + summary_status | V15, V18 | schemaless |
| inferred_mode | V16 | schemaless |
| user_feedback store | V17 | V5 |
| analytics_events store | V19 | V6 |
| practice_plans store | V20 | V7 |
| applied_sessions replay ledger | V21 | V8 |
| jam backing-bed context columns | V22 | schemaless |

## Testing

### Manual Testing
1. Start with a fresh database (delete app data)
2. Run the app and verify migrations apply
3. Check that `schema_migrations` table/store has correct versions
4. Verify data integrity (scores, sessions, etc.)

### Migration Path Testing
1. Create a database at version N
2. Upgrade to version N+1
3. Verify data is preserved
4. Test rollback by intentionally failing migration

## Best Practices

1. **Always include rollback SQL**: Even if you think it won't fail
2. **Validate before migrating**: Use validation functions to check data integrity
3. **Test with real user data**: Use beta tester data to verify migration path
4. **Keep migrations idempotent**: Check if column exists before adding
5. **Document changes**: Add comments explaining why the migration is needed
6. **Increment version sequentially**: Never skip version numbers

## Backward Compatibility

The migration system ensures:
- Early beta testers' practice history is preserved
- Mastery percentages are not lost during schema updates
- App can handle missing fields gracefully (using optional types with defaults)
- Failed migrations don't corrupt the database

## Troubleshooting

### Migration Fails
1. Check console logs for error message
2. Verify rollback SQL is correct
3. Check if data validation is failing
4. Test with a clean database

### Data Loss After Migration
1. Verify validation functions are working
2. Check that default values are set correctly
3. Ensure field types match between schema and code
4. Review rollback SQL for errors

## GP5 contract deprecation (non-DB)

Commit 108 made MusicXML the primary render format, but GP5 remains in the
`LessonJSON` contract. This section is the removal plan; it is not a database
migration.

### Why GP5 is still present

- `src/demo/demoLesson.ts` renders from `tab_full_gp5_base64` only.
- `src/jam/jamReferenceTabGp5Base64.ts` is a GP5-only fixture.
- `components/SessionStemAndTab.tsx` prefers `musicxml` and falls back to GP5
  when a lesson has none.
- `app/(tabs)/library.tsx` exports MIDI by sending GP5 to `POST /export`;
  `backend/app/routers/export.py` requires `gp5_base64`.
- `backend/app/tabgen.py` also emits GP5-only skeleton/alternate-position
  variants and last-resort stub artifacts.

MusicXML is not yet a full replacement, so the `@deprecated` tags on
`src/types/index.ts` (`tab_full_gp5_base64`, `tab_skeleton_gp5_base64`,
`tab_alt_position_gp5_base64`, tracked as `M-04`) mean "prefer MusicXML", not
"safe to delete".

### Removal gates

All gates must pass before removing GP5 from the contract:

1. **Render parity** — every render path has MusicXML: demo lesson, jam
   reference fixture, and saved lessons. Skeleton and alternate-position
   variants have MusicXML equivalents or a documented UX decision to drop them.
2. **Legacy data** — a backfill or re-analysis makes `musicxml` present for
   persisted lessons, or a documented cutoff keeps read-only GP5 fallback for
   old rows.
3. **Export parity** — MIDI export works without GP5 (add MusicXML→MIDI or an
   export route that accepts MusicXML).
4. **Verification** — `backend/tests/test_musicxml_corpus.py`,
   `tests/ui/musicxml-render.spec.ts`, and `tests/mobile/musicxml-render.e2e.js`
   pass, and the Partial items in
   [`docs/ALPHATAB_MUSICXML_LIMITATIONS.md`](./ALPHATAB_MUSICXML_LIMITATIONS.md)
   are accepted or fixed.
5. **Stub parity** — `STUB_TAB_*_GP5_BASE64` fallbacks are replaced by
   MusicXML fallbacks.

### Removal order

1. Types and helpers: `LessonSection.tab_*_gp5_base64`,
   `firstGp5Base64FromLessonSections`, `readSectionTabPayloads` GP5 fields.
2. Render call sites: `SessionStemAndTab`, `study`, `review`.
3. Fixtures: demo lesson and jam reference tab.
4. Backend emission and stubs in `backend/app/tabgen.py`.
5. `POST /export` GP5 path in `backend/app/routers/export.py`.

Do not remove GP5 in Commit 11. This plan is tracked as `M-04` in
[`techdebt/MARKERS.md`](../techdebt/MARKERS.md).

## Future Considerations

- Add automated migration tests
- Add migration dry-run mode
- Implement data backup before migration
- Add migration progress reporting
- Consider using a migration library for complex scenarios
