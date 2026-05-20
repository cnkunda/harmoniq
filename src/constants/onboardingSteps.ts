/**
 * Unified onboarding step definitions.
 *
 * Full flow (with taste quiz): welcome(1) → quiz(2) → mic(3) → phrase0(4) → phrase1(5) → phrase2(6) → results(7)
 * Full flow (without quiz):    welcome(1) → mic(2) → phrase0(3) → phrase1(4) → phrase2(5) → results(6)
 */

export const ONBOARDING_WITH_QUIZ_TOTAL = 7
export const ONBOARDING_WITHOUT_QUIZ_TOTAL = 6

export type OnboardingScreenId =
  | 'welcome'
  | 'taste-quiz'
  | 'mic'
  | 'phrase-0'
  | 'phrase-1'
  | 'phrase-2'
  | 'results'

/** Step number for each screen when the taste quiz IS taken. */
export const ONBOARDING_STEP_WITH_QUIZ: Record<OnboardingScreenId, number> = {
  welcome: 1,
  'taste-quiz': 2,
  mic: 3,
  'phrase-0': 4,
  'phrase-1': 5,
  'phrase-2': 6,
  results: 7,
}

/** Step number for each screen when the taste quiz is SKIPPED. */
export const ONBOARDING_STEP_WITHOUT_QUIZ: Record<Exclude<OnboardingScreenId, 'taste-quiz'>, number> = {
  welcome: 1,
  mic: 2,
  'phrase-0': 3,
  'phrase-1': 4,
  'phrase-2': 5,
  results: 6,
}
