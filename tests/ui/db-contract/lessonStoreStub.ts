/**
 * Test-only stand-in for `src/stores/lessonStore` inside the db-contract
 * browser bundle: the real store's module graph pulls react-native (toast,
 * async-storage), which cannot be bundled in a plain page. The contract cases
 * never drive lesson analysis, so idle state with the used surface
 * (`getState().lesson`, `setState(...)`) is sufficient.
 */
type LessonStoreState = {
  lesson: unknown
  status: string
  error: string | null
}

const state: LessonStoreState = { lesson: null, status: 'idle', error: null }

export const useLessonStore = {
  getState: (): LessonStoreState => state,
  setState: (partial: Partial<LessonStoreState>): void => {
    Object.assign(state, partial)
  },
}
