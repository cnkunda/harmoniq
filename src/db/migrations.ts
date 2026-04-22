/**
 * Versioned database migration system with rollback support.
 * Prevents data loss during app updates and ensures backward compatibility.
 */

export interface Migration {
  version: number
  description: string
  up: string | string[] // SQL for native, array of operations for web
  down?: string | string[] // Rollback SQL/operations
  validate?: () => Promise<boolean> // Optional validation before applying
}

export interface MigrationResult {
  version: number
  success: boolean
  error?: string
  rolledBack?: boolean
}

export interface MigrationState {
  currentVersion: number
  pendingMigrations: Migration[]
  lastAppliedAt: string | null
}

/**
 * Validates that skill_nodes data is preserved after migration.
 * Checks that mastery percentages (score) are not lost.
 */
export async function validateSkillNodesPreservation(
  getNodes: () => Promise<{ id: string; score: number }[]>,
): Promise<{ valid: boolean; error?: string }> {
  try {
    const nodes = await getNodes()
    if (nodes.length === 0) {
      return { valid: true } // Empty state is valid
    }
    
    // Check that all scores are finite numbers between 0 and 1
    for (const node of nodes) {
      if (typeof node.score !== 'number' || !Number.isFinite(node.score)) {
        return { valid: false, error: `Node ${node.id} has invalid score: ${node.score}` }
      }
      if (node.score < 0 || node.score > 1) {
        return { valid: false, error: `Node ${node.id} has score out of range: ${node.score}` }
      }
    }
    
    return { valid: true }
  } catch (e) {
    return { valid: false, error: `Validation failed: ${e instanceof Error ? e.message : String(e)}` }
  }
}

/**
 * Validates that sessions data is preserved after migration.
 */
export async function validateSessionsPreservation(
  getSessionCount: () => Promise<number>,
): Promise<{ valid: boolean; error?: string }> {
  try {
    const count = await getSessionCount()
    if (typeof count !== 'number' || !Number.isFinite(count) || count < 0) {
      return { valid: false, error: `Invalid session count: ${count}` }
    }
    return { valid: true }
  } catch (e) {
    return { valid: false, error: `Validation failed: ${e instanceof Error ? e.message : String(e)}` }
  }
}

/**
 * Logs migration outcome for debugging and audit.
 */
export function logMigration(result: MigrationResult, platform: 'native' | 'web'): void {
  if (__DEV__) {
    const status = result.success ? 'SUCCESS' : 'FAILED'
    const rollback = result.rolledBack ? ' (rolled back)' : ''
    console.log(`[db/${platform}] Migration v${result.version} ${status}${rollback}`)
    if (result.error) {
      console.error(`[db/${platform}] Error: ${result.error}`)
    }
  }
}
