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

## Web (IndexedDB) Migrations

### Location
- Migration runner: `src/db/idbWeb.ts` (openHarmoniqIdb function)
- Current version: 4

### Version Tracking
Migrations are tracked in the `schema_migrations` object store:
```typescript
type MigrationRow = { version: number; applied_at: string }
```

### Migration Pattern
IndexedDB uses built-in versioning:
```typescript
const DB_VERSION = 4
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
export const MIGRATION_V15_EXAMPLE = 'ALTER TABLE skill_nodes ADD COLUMN new_field TEXT'
export const ROLLBACK_V15_EXAMPLE = 'ALTER TABLE skill_nodes DROP COLUMN IF EXISTS new_field'
```

2. Add imports to `src/db/client.native.ts`:
```typescript
import {
  MIGRATION_V15_EXAMPLE,
  ROLLBACK_V15_EXAMPLE,
  // ... other imports
} from '@/src/db/schema'
```

3. Add migration logic to `applyMigrations()`:
```typescript
if (current < 15) {
  const cols = await db.getAllAsync<{ name: string }>('PRAGMA table_info(skill_nodes)')
  const names = new Set((cols ?? []).map((c) => c.name))
  if (!names.has('new_field')) {
    await applyMigrationWithRollback(15, MIGRATION_V15_EXAMPLE, ROLLBACK_V15_EXAMPLE)
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
const DB_VERSION = 5
```

2. Add version-specific logic in `onupgradeneeded`:
```typescript
if (oldVersion < 5) {
  // Add new object store or modify existing
  if (!db.objectStoreNames.contains(S_NEW_STORE)) {
    db.createObjectStore(S_NEW_STORE, { keyPath: 'id' })
  }
  // Record migration
  const tx = r.transaction
  if (tx) {
    const migrationStore = tx.objectStore(S_MIGRATIONS)
    migrationStore.put({ version: 5, applied_at: new Date().toISOString() })
  }
}
```

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

## Future Considerations

- Add automated migration tests
- Add migration dry-run mode
- Implement data backup before migration
- Add migration progress reporting
- Consider using a migration library for complex scenarios
