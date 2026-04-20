/** Passed from ListenStemPanel into Play capture UI (backing transport lives in the stem panel). */
export type PlayLessonCaptureContext = {
  songTitle: string
  sectionLine: string
  loading: boolean
  ready: boolean
  playing: boolean
}
