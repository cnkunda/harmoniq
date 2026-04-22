/**
 * Focus area rotation for AI coach variation agents (commit 90).
 * Cycles through focus areas across sessions to prevent feedback redundancy.
 */

export type CoachFocusArea = 'timing' | 'vibrato' | 'dynamics' | 'phrasing' | 'bending' | 'rhythm' | 'expression'

const FOCUS_AREA_ROTATION: CoachFocusArea[] = [
  'timing',
  'vibrato',
  'dynamics',
  'phrasing',
  'bending',
  'rhythm',
  'expression',
]

/**
 * Determine focus area for this session based on session count.
 * Mirrors backend rotate_focus_area function in coach.py.
 */
export function rotateFocusArea(sessionCount: number): CoachFocusArea {
  if (sessionCount < 0) {
    sessionCount = 0
  }
  return FOCUS_AREA_ROTATION[sessionCount % FOCUS_AREA_ROTATION.length]
}

/**
 * Session counting key for localStorage (web) or AsyncStorage (native).
 */
export const SESSION_COUNT_KEY = 'harmoniq_session_count'

/**
 * Platform-agnostic storage interface.
 */
interface StorageAdapter {
  getItem: (key: string) => Promise<string | null>
  setItem: (key: string, value: string) => Promise<void>
  removeItem: (key: string) => Promise<void>
}

/**
 * localStorage adapter for web.
 */
class WebStorageAdapter implements StorageAdapter {
  async getItem(key: string): Promise<string | null> {
    try {
      return localStorage.getItem(key)
    } catch {
      return null
    }
  }

  async setItem(key: string, value: string): Promise<void> {
    try {
      localStorage.setItem(key, value)
    } catch {
      // Ignore errors
    }
  }

  async removeItem(key: string): Promise<void> {
    try {
      localStorage.removeItem(key)
    } catch {
      // Ignore errors
    }
  }
}

/**
 * AsyncStorage adapter for React Native.
 * @ts-expect-error - AsyncStorage may not be available in web builds
 */
class NativeStorageAdapter implements StorageAdapter {
  private asyncStorage: any = null

  private async getAsyncStorage(): Promise<any> {
    if (this.asyncStorage) return this.asyncStorage
    try {
      // @ts-expect-error - Dynamic import for native-only package
      const module = await import('@react-native-async-storage/async-storage')
      this.asyncStorage = module.default || module.AsyncStorage
      return this.asyncStorage
    } catch {
      return null
    }
  }

  async getItem(key: string): Promise<string | null> {
    try {
      const storage = await this.getAsyncStorage()
      if (storage) {
        return await storage.getItem(key)
      }
    } catch {
      // Fall through to web storage
    }
    // Fallback to localStorage if AsyncStorage fails or is unavailable
    const webAdapter = new WebStorageAdapter()
    return webAdapter.getItem(key)
  }

  async setItem(key: string, value: string): Promise<void> {
    try {
      const storage = await this.getAsyncStorage()
      if (storage) {
        await storage.setItem(key, value)
        return
      }
    } catch {
      // Fall through to web storage
    }
    // Fallback to localStorage if AsyncStorage fails or is unavailable
    const webAdapter = new WebStorageAdapter()
    await webAdapter.setItem(key, value)
  }

  async removeItem(key: string): Promise<void> {
    try {
      const storage = await this.getAsyncStorage()
      if (storage) {
        await storage.removeItem(key)
        return
      }
    } catch {
      // Fall through to web storage
    }
    // Fallback to localStorage if AsyncStorage fails or is unavailable
    const webAdapter = new WebStorageAdapter()
    await webAdapter.removeItem(key)
  }
}

/**
 * Get appropriate storage adapter based on platform.
 */
function getStorageAdapter(): StorageAdapter {
  // Check if we're in a React Native environment
  if (typeof window !== 'undefined' && (window as any).__REACT_NATIVE__) {
    return new NativeStorageAdapter()
  }
  // Default to web storage
  return new WebStorageAdapter()
}

const storage = getStorageAdapter()

/**
 * Increment session count and return new count.
 * This should be called when a new session/analysis is started.
 */
export async function incrementSessionCount(): Promise<number> {
  const raw = await storage.getItem(SESSION_COUNT_KEY)
  const current = raw ? parseInt(raw, 10) : 0
  const next = Math.max(0, current + 1)
  await storage.setItem(SESSION_COUNT_KEY, next.toString())
  return next
}

/**
 * Get current session count without incrementing.
 */
export async function getSessionCount(): Promise<number> {
  const raw = await storage.getItem(SESSION_COUNT_KEY)
  return raw ? parseInt(raw, 10) : 0
}

/**
 * Reset session count (useful for testing or user preference reset).
 */
export async function resetSessionCount(): Promise<void> {
  await storage.removeItem(SESSION_COUNT_KEY)
}

/**
 * Get focus area for the next session and increment session count.
 * Convenience function that combines getSessionCount and incrementSessionCount.
 */
export async function getNextFocusArea(): Promise<CoachFocusArea> {
  const count = await incrementSessionCount()
  return rotateFocusArea(count)
}
