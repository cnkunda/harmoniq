import type { SessionStep } from '@/src/constants/sessionFlow'

/** Steps that show demo tour UI (full session loop). */
export type DemoTourStep = Extract<
  SessionStep,
  'tune' | 'listen' | 'study' | 'slow' | 'play' | 'review'
>

/** Short explanation under the step title when touring the bundled demo. */
export const DEMO_TOUR_SUBTITLE: Record<DemoTourStep, string> = {
  tune:
    'Sessions begin here so Play scoring knows your room noise — optional for this offline clip. Continue when ready, or use Skip for now.',
  listen:
    'Use the mixer to solo or blend stems before you pick up the guitar — every session starts from sound.',
  study:
    'The tab is your map for this section — works for bundled clips, analyzed tracks, or drills from your Library.',
  slow:
    'Slow the loop and lock a region while the tab stays synced — same idea for practice loops or full arrangements.',
  play:
    'Mute the guitar stem and record a take — scoring compares your pitch and timing to the tab notes.',
  review:
    'See how this session fits together: scores, DNA hints, optional export. Add your own material from Home when you are ready.',
}

/** Amber callout body — expands on “how Harmoniq works” without replacing the subtitle. */
export const DEMO_TOUR_CALLOUT: Record<DemoTourStep, string> = {
  tune:
    'Mic calibration keeps pitch scoring fair in noisy rooms. For this bundled WAV you can skim tuning and tap Skip for now — real sessions benefit from a quick calibration.',
  listen:
    'Try toggling stems: you are shaping what you hear before you play. That is the same mixer behavior you get after you add a track.',
  study:
    'Scroll to the interactive tab — tap notes for fingerings and context. You do not need songs in your library first; this demo uses an offline stem plus a reference tab.',
  slow:
    'Speed and loop controls let you chop a phrase without losing sync to the stems and cursor.',
  play:
    'This step is where Harmoniq listens back through the mic and lines your performance up with the tab grid.',
  review:
    'You just walked Listen → Study → Slow → Play. Next, add your own audio from Home or open Library for saved licks.',
}
