/**
 * Contract between the Expo app and `assets/alphatab-harness/index.html`
 * (WebView on native) or `AlphaTabWeb.web.tsx` (DOM on Expo web).
 */

/** Bar-aligned loop highlight in the score (Slow step). */
export type TabLoopBarRegion = {
  startBarIndex: number
  endBarIndexExclusive: number
}

/** Parent → harness */
export type TabInboundMessage =
  | { type: 'setScore'; gp5Base64: string }
  | { type: 'setAudioSrc'; audioSrc: string }
  | { type: 'setPlaybackRate'; playbackRate: number }
  | { type: 'seekTo'; positionMs: number }
  /** Listening mode: score follows external media, but user score taps/seeks are disabled. */
  | { type: 'setReadOnlyFollowMode'; enabled: boolean }
  | { type: 'syncTimelineMs'; positionMs: number }
  /** Host stem transport play/pause — AlphaTab cursor needs player active (see player.enableCursor). */
  | { type: 'setStemPlaybackActive'; active: boolean }
  /** Host reads hidden reference `<audio>` clock; harness/web convert to score timeline ms (÷ stem `playbackRate`). */
  | { type: 'getPosition' }
  | { type: 'setTranspose'; semitones: number }
  | { type: 'setTheme'; colors: Partial<TabThemeColors> }
  /** Commit 56: apply named display preset (`listen` | `study` | `slow` | `play`); unknown → `study`. */
  | { type: 'setRenderPreset'; presetName: string }
  | { type: 'setLoopRegion'; startBarIndex: number; endBarIndexExclusive: number }
  | { type: 'clearLoopRegion' }
  /** Jam: tint tab / notation for pitch classes in the detected scale (native WebView harness). */
  | { type: 'highlightScaleDegrees'; rootMidi: number; intervals: number[] }
  | { type: 'clearScaleHighlight' }
  /** After a discrete seek, scroll the host so master bar index is visible (Study annotation chips). */
  | { type: 'scrollMasterBarIntoView'; barIndex: number }
  /** Read static score metadata (title, sections, etc.); optional `requestId` pairs with `songDetails` for `getSongDetails()`. */
  | { type: 'getSongDetails'; requestId?: string }
  /** Commit 60: load or swap AlphaTab synth bank (`general_user` | `fluid_r3_mono`). */
  | { type: 'setSoundFontProfile'; profileId: string }
  /** Commit 61: enable/disable harness periodic `runtimeDiagnostics` (dev / explicit flag only). */
  | { type: 'setRuntimeDiagnosticsEnabled'; enabled: boolean }
  /** Commit 61: bridge RTT probe — harness replies with `diagPong`. */
  | { type: 'diagPing'; requestId: string; t0: number }

export type NoteEventMessage = {
  type: 'noteEvent'
  midi: number
  beat: number
  fret?: number
  string?: number
  /** True when both string and fret came from the score engine (Study prefers this over MIDI alone). */
  hasExplicitTabPosition?: boolean
  /** True only for direct score tap/click events (not playback stream). */
  fromScoreTap?: boolean
}

/**
 * Subset of alphaTab display `RenderingResources` the app may override.
 * Keys match `@coderline/alphatab` JSON settings where applicable.
 */
export type TabThemeColors = {
  mainGlyphColor?: string
  secondaryGlyphColor?: string
  barSeparatorColor?: string
  scoreInfoColor?: string
  staffLineColor?: string
  barNumberColor?: string
}

/** Serializable subset of `alphaTab.model.Score` + section markers (harness / web). */
export type SongSectionMarker = {
  startMasterBarIndex: number
  label: string
}

export type SongScoreMeta = {
  title?: string | null
  artist?: string | null
  album?: string | null
  subTitle?: string | null
  words?: string | null
  music?: string | null
  tab?: string | null
  /** Initial tempo (BPM) from the score when available. */
  tempoBpm?: number | null
  sectionMarkers?: SongSectionMarker[]
}

/** Imperative API shared by `AlphaTabWebView` (native) and `AlphaTabWeb` (Expo web DOM). */
export type AlphaTabSurfaceRef = {
  setAudioSrc: (audioSrc: string) => void
  setPlaybackRate: (playbackRate: number) => void
  seekTo: (positionMs: number) => void
  /** Drive cursor when audio comes from Web Audio (stems), not the tab reference audio element. */
  syncPlaybackTimelineMs: (positionMs: number) => void
  /** Call when stem mixer play/pause toggles so AlphaTab shows the beat cursor during host-driven playback. */
  setStemPlaybackActive: (active: boolean) => void
  /** Score timeline ms; hidden `<audio>` time ÷ stem playback rate (see harness `getPosition` / web `AlphaTabWeb`). */
  getPosition: () => Promise<number | null>
  setTheme: (colors: Partial<TabThemeColors>) => void
  /** Named session-step preset (native harness + web implementation). */
  setRenderPreset: (presetName: string) => void
  setTranspose: (semitones: number) => void
  /** Commit 60: swap bundled / pinned SoundFont bank for AlphaTab synth. */
  setSoundFontProfile: (profileId: string) => void
  /** Highlight loop bars on the score (null clears). */
  setLoopRegion: (region: TabLoopBarRegion | null) => void
  /** Jam (web + native harness): tint note heads / tab numbers matching scale degrees. */
  highlightScaleDegrees: (rootMidi: number, intervals: readonly number[]) => void
  clearScaleHighlight: () => void
  /** Horizontal scroll host so the given master bar is in view (e.g. after chip seek). */
  scrollMasterBarIntoView: (barIndex: number) => void
  /** Score metadata from AlphaTab (static; may be partial if the file omits fields). */
  getSongDetails: () => Promise<SongScoreMeta | null>
}

/** Harness → parent */
export type TabOutboundMessage =
  | { type: 'ready' }
  | { type: 'renderPresetApplied'; presetName: string }
  | { type: 'error'; message: string }
  | { type: 'position'; positionMs: number }
  /** User (or player) seeked via the score — host should move stem transport to this score time. */
  | { type: 'scoreSeek'; positionMs: number }
  | NoteEventMessage
  | {
      type: 'soundFontLoad'
      status: 'loading' | 'loaded' | 'error'
      /** Commit 60: which profile this event refers to when present. */
      profileId?: string
      loaded?: number
      total?: number
      message?: string
    }
  | { type: 'songDetails'; score: SongScoreMeta; requestId?: string }
  | { type: 'songPlayback'; masterBarIndex: number; sectionLabel: string | null }
  /** Commit 61: 5s aggregated AlphaTab metrics (harness or DOM path). */
  | {
      type: 'runtimeDiagnostics'
      windowMs: number
      driftMs: number | null
      noteEventHz: number
      renderFps: number
      breachFlags?: string[]
    }
  /** Commit 61: echo for `diagPing` RTT measurement. */
  | { type: 'diagPong'; requestId: string; t0: number }

export function encodeTabMessage(msg: TabInboundMessage): string {
  return JSON.stringify(msg)
}

function parseSongSectionMarker(v: unknown): SongSectionMarker | null {
  if (!v || typeof v !== 'object') return null
  const o = v as { startMasterBarIndex?: unknown; label?: unknown }
  if (typeof o.startMasterBarIndex !== 'number' || !Number.isFinite(o.startMasterBarIndex)) return null
  if (typeof o.label !== 'string' || !o.label.trim()) return null
  return { startMasterBarIndex: Math.max(0, Math.floor(o.startMasterBarIndex)), label: o.label.trim() }
}

function parseSongScoreMeta(v: unknown): SongScoreMeta {
  if (!v || typeof v !== 'object') return {}
  const o = v as Record<string, unknown>
  const str = (k: string) => {
    const x = o[k]
    if (x == null) return null
    return typeof x === 'string' ? x : null
  }
  const num = (k: string) => (typeof o[k] === 'number' && Number.isFinite(o[k]) ? o[k] : null)
  const rawMarkers = o.sectionMarkers
  const sectionMarkers: SongSectionMarker[] = []
  if (Array.isArray(rawMarkers)) {
    for (const m of rawMarkers) {
      const p = parseSongSectionMarker(m)
      if (p) sectionMarkers.push(p)
    }
  }
  return {
    title: str('title') || null,
    artist: str('artist') || null,
    album: str('album') || null,
    subTitle: str('subTitle') || null,
    words: str('words') || null,
    music: str('music') || null,
    tab: str('tab') || null,
    tempoBpm: num('tempoBpm'),
    sectionMarkers: sectionMarkers.length > 0 ? sectionMarkers : undefined,
  }
}

export function decodeTabMessage(raw: string): TabOutboundMessage | null {
  try {
    const v: unknown = JSON.parse(raw)
    if (!v || typeof v !== 'object' || !('type' in v)) return null
    const o = v as { type: unknown; message?: unknown }
    if (o.type === 'ready') return { type: 'ready' }
    const maybePreset = o as { type: unknown; presetName?: unknown }
    if (o.type === 'renderPresetApplied' && typeof maybePreset.presetName === 'string') {
      return { type: 'renderPresetApplied', presetName: maybePreset.presetName }
    }
    if (o.type === 'error' && typeof o.message === 'string') {
      return { type: 'error', message: o.message }
    }
    const maybePosition = o as { type: unknown; positionMs?: unknown }
    if (o.type === 'position' && typeof maybePosition.positionMs === 'number') {
      return { type: 'position', positionMs: maybePosition.positionMs }
    }
    if (o.type === 'scoreSeek' && typeof maybePosition.positionMs === 'number') {
      return { type: 'scoreSeek', positionMs: maybePosition.positionMs }
    }
    const maybeSf = o as { type: unknown; status?: unknown; message?: unknown }
    if (
      o.type === 'soundFontLoad' &&
      (maybeSf.status === 'loading' || maybeSf.status === 'loaded' || maybeSf.status === 'error')
    ) {
      const maybeExt = o as {
        profileId?: unknown
        loaded?: unknown
        total?: unknown
      }
      return {
        type: 'soundFontLoad',
        status: maybeSf.status,
        profileId: typeof maybeExt.profileId === 'string' ? maybeExt.profileId : undefined,
        loaded: typeof maybeExt.loaded === 'number' ? maybeExt.loaded : undefined,
        total: typeof maybeExt.total === 'number' ? maybeExt.total : undefined,
        message: typeof maybeSf.message === 'string' ? maybeSf.message : undefined,
      }
    }
    const maybeNote = o as {
      type: unknown
      midi?: unknown
      beat?: unknown
      fret?: unknown
      string?: unknown
      hasExplicitTabPosition?: unknown
      fromScoreTap?: unknown
    }
    if (o.type === 'noteEvent' && typeof maybeNote.midi === 'number' && typeof maybeNote.beat === 'number') {
      return {
        type: 'noteEvent',
        midi: maybeNote.midi,
        beat: maybeNote.beat,
        fret: typeof maybeNote.fret === 'number' ? maybeNote.fret : undefined,
        string: typeof maybeNote.string === 'number' ? maybeNote.string : undefined,
        hasExplicitTabPosition: maybeNote.hasExplicitTabPosition === true ? true : undefined,
        fromScoreTap: maybeNote.fromScoreTap === true ? true : undefined,
      }
    }
    const maybeSd = o as { type: unknown; score?: unknown; requestId?: unknown }
    if (o.type === 'songDetails' && maybeSd.score !== undefined) {
      const rid = maybeSd.requestId
      return {
        type: 'songDetails',
        score: parseSongScoreMeta(maybeSd.score),
        requestId: typeof rid === 'string' && rid ? rid : undefined,
      }
    }
    const maybePb = o as { type: unknown; masterBarIndex?: unknown; sectionLabel?: unknown }
    if (
      o.type === 'songPlayback' &&
      typeof maybePb.masterBarIndex === 'number' &&
      Number.isFinite(maybePb.masterBarIndex)
    ) {
      const sl = maybePb.sectionLabel
      return {
        type: 'songPlayback',
        masterBarIndex: Math.max(0, Math.floor(maybePb.masterBarIndex)),
        sectionLabel: sl === null ? null : typeof sl === 'string' ? sl : null,
      }
    }
    const maybeRd = o as {
      type: unknown
      windowMs?: unknown
      driftMs?: unknown
      noteEventHz?: unknown
      renderFps?: unknown
      breachFlags?: unknown
    }
    if (o.type === 'runtimeDiagnostics' && typeof maybeRd.windowMs === 'number') {
      const flags = maybeRd.breachFlags
      const breachList: string[] = []
      if (Array.isArray(flags)) {
        for (const f of flags) {
          if (typeof f === 'string' && f) breachList.push(f)
        }
      }
      return {
        type: 'runtimeDiagnostics',
        windowMs: Math.max(0, Math.floor(maybeRd.windowMs)),
        driftMs:
          maybeRd.driftMs === null
            ? null
            : typeof maybeRd.driftMs === 'number' && Number.isFinite(maybeRd.driftMs)
              ? maybeRd.driftMs
              : null,
        noteEventHz: typeof maybeRd.noteEventHz === 'number' && Number.isFinite(maybeRd.noteEventHz) ? maybeRd.noteEventHz : 0,
        renderFps: typeof maybeRd.renderFps === 'number' && Number.isFinite(maybeRd.renderFps) ? maybeRd.renderFps : 0,
        breachFlags: breachList.length > 0 ? breachList : undefined,
      }
    }
    const maybePong = o as { type: unknown; requestId?: unknown; t0?: unknown }
    if (o.type === 'diagPong' && typeof maybePong.requestId === 'string' && typeof maybePong.t0 === 'number') {
      return { type: 'diagPong', requestId: maybePong.requestId, t0: maybePong.t0 }
    }
  } catch {
    /* invalid */
  }
  return null
}
