# Harmoniq — v1 Build Prompt
### AI-Powered Adaptive Guitar Learning App

---

## What You Are Building

Build **Harmoniq**, a React Native **+ Web** app (iOS + Android + browser) for a specific type of guitar player: someone who can already play lead lines and rhythm but cannot yet solo expressively. The app's core promise is: *pick up your guitar, open the app, and play something that sounds musical within 20 minutes — no schedule required, no levels to grind.*

Harmoniq is not a Yousician clone. It does not reward grinding or streaks. It does not have a rigid lesson curriculum. It is an **AI-powered practice companion** that listens to you, understands where you actually are today, and hands you one high-value thing to work on — built around a real song you care about.

The target player: intermediate guitarist drawn to John Mayer, Tommy Emmanuel, and Jack White. Not a speed player. Wants to play expressively with few, well-chosen notes. Has tried apps like Yousician and felt no improvement because the feedback is robotic ("wrong note") rather than musical ("you're rushing the end of every phrase").

---

## Visual Direction

**Warm, analog, handcrafted.** The app should feel like a well-worn guitar workshop — wood grain textures, amber and cream tones, slightly imperfect edges, warm lighting. Think: a beautifully aged Les Paul in a room with good lamps. Nothing sterile. Nothing neon. Nothing that looks like a SaaS dashboard.

**Color palette:**
- Background: deep walnut `#1C1208` to warm espresso `#2B1D0E`
- Surface cards: `#3D2B1A` with subtle grain texture overlay
- Primary accent: warm amber `#D4860A`
- Secondary accent: aged cream `#F0DEB4`
- Text primary: `#F5EDDC`
- Text secondary: `#A08060`
- Danger/miss: muted terracotta `#C0522A`
- Success/hit: warm sage `#7A9E6A`

**Typography:**
- Display / headings: `Playfair Display` (serif, evocative of music notation and vintage print)
- Body / UI labels: `DM Sans` (clean but warm, not cold like Inter)
- Monospace / note names / tab display: `JetBrains Mono`

**Texture:** Apply a subtle paper/grain overlay across all backgrounds using a low-opacity noise SVG or PNG. Cards should have slight inner shadows and soft borders, not sharp drop shadows.

**Animations:** Slow, intentional. Waveforms pulse gently. Transitions use `Animated` with ease-in-out curves. Nothing bouncy or gamified. The feel is "jazz club lighting," not "mobile game."

**Icons:** Phosphor Icons (warm, slightly rounded, not Material or Heroicons). Custom SVG illustrations for key moments (placement session complete, lick saved, etc.).

---

## Tech Stack

### Frontend
- **Framework:**
  - React Native (Expo SDK 54, managed workflow) for iOS + Android
  - **React Native Web (Expo Web)** for browser support (v1)
- **State management:** Zustand (shared across platforms)
- **Navigation:** Expo Router (file-based routing, works on web and native)
- **Tab rendering:**
  - **Mobile:** AlphaTab via `<WebView>` harness — local HTML at `assets/alphatab-harness/index.html`, tab data as JSON via `window.postMessage`. Palette: background `#2B1D0E`, note heads `#F0DEB4`. Do not build a custom renderer.
  - **Web:** AlphaTab rendered directly in the DOM (no WebView). Shared `types/tabMessage.ts` contract for both.
- **Waveform / pitch display:** Custom animated bars component (`WaveformVisualizer`) using React Native `View` + `react-native-reanimated`; `PitchIndicator` using `react-native-reanimated` shared values. `react-native-svg` for the skill graph radar chart.
- **Gradients:** `expo-linear-gradient` (`WoodGradient` wrapper component). All screen backgrounds use this — not CSS gradients.
- **Icons:** `lucide-react-native` (native + web). Lucide is used in lieu of Phosphor — official RN package, consistent with DESIGN_SYSTEM component specs.
- **Animations:** `react-native-reanimated` v3 in place of `framer-motion` (web-only). Reanimated works across iOS, Android, and Expo Web.
- **Interaction feedback:** `expo-haptics` for impact / selection haptics on every `AnimatedPressable`. Calls are silent no-ops on web and simulator — no platform guards needed. `react-native-gesture-handler` required as a peer dependency of Reanimated and Expo Router.
- **Toast / notifications:** `react-native-toast-message` with a wood-themed config (`ToastConfig.tsx`). Use `toast.success()` / `toast.error()` helpers throughout.
- **Audio playback:** `expo-av` for stem playback, loop, and rate control (`shouldCorrectPitch: true`). **Web:** Web Audio API via Expo Web. Support: rate 50–100%, pitch correction (degrade gracefully on web), looping, per-stem mute via parallel `Sound` instances (native) or `GainNode` graph (web).
- **Mic / real-time pitch:**
  - **Mobile:** Native-safe low-latency path (JSI or dedicated Expo module). No JS worker thread DSP.
  - **Web:** `getUserMedia` + `AudioWorklet`. Shared `usePitchStream()` hook with `.native.ts` / `.web.ts` platform files.
  - On-device only — no network calls during play.
- **File handling (web):** Drag-and-drop via `AudioDropzone.web.tsx`, file picker, IndexedDB storage.

### Backend (Python FastAPI)
Runs locally during development. Deploy to Railway, Fly.io, or Render free tier for personal use.

**Endpoints:**
- `POST /analyze` — accepts `{ url: string }` (YouTube) or multipart audio file. Returns `{ job_id }` immediately. Processing is async.
- `GET /analyze/{job_id}` — polling endpoint. Returns `{ status: "processing" | "complete" | "failed", result: LessonJSON | null, error: string | null }`
- `POST /score` — accepts recorded PCM buffer + target section metadata. Returns `ScoreResult`
- `POST /jam-score` — accepts a jam session recording buffer. Returns `JamResult`

**Audio ML pipeline (Python, executed in sequence per analysis job):**
1. `yt-dlp --extract-audio --audio-format wav --audio-quality 0` → `song.wav` (44.1kHz mono). For uploaded files, accept WAV/MP3/M4A and normalize via `ffmpeg -ar 44100 -ac 1`.
2. `demucs --model htdemucs_6s --out ./stems song.wav` → 6 dedicated WAV stems: guitar, bass, drums, vocals, piano, other. The `htdemucs_6s` checkpoint is critical — it separates guitar as its own stem rather than burying it in "other." Do not use the default 4-stem model.
3. `librosa.load(guitar_stem)` → key string (e.g., "G major"), tempo float (BPM), beat grid (array of timestamps in seconds), structure segments array (intro / verse / chorus / solo / bridge / outro, detected via onset strength + RMS energy segmentation).
4. `whisper.transcribe(vocals_stem, word_timestamps=True)` (base model, runs locally) → lyrics with word-level timestamps. Map each word timestamp to the nearest beat in the beat grid.
5. `basic_pitch.predict(guitar_stem)` on solo/lead sections only → MIDI note events with timestamps. Convert MIDI → Guitar Pro format (`.gp5`) via `py-guitarpro`.
6. Skeleton tab generation: from the full MIDI note events, filter out ornaments — grace notes, bends shorter than 50ms, and hammer-ons/pull-offs faster than a 16th note at the song's BPM. Remaining events → second `.gp5` file.
7. Alternate position generation *(only if confidence is high)*: given key and detected primary position, compute alternate fingering map (e.g., position 2 → position 4) → third `.gp5` file.
8. `bar_timestamps` array: use beat grid and time signature to compute one timestamp per bar (e.g., 4/4 at 72 BPM → one bar every 3.33 seconds). This drives SmartScroll.
9. Claude API call: generate `coach_note` and `coach_explanation` strings for each solo/lead section.
10. Return `LessonJSON`.

**Pipeline reliability:** Every derived output includes confidence: `key_confidence`, `tempo_confidence`, `transcription_confidence`, `section_confidence` (per section where applicable). If transcription confidence is low: mark tab as approximate, disable alternate positions, default to skeleton tab. Users can ignore or override incorrect analysis.

**Caching:** Cache analysis results by audio hash and pipeline version.

**Source handling:** YouTube is convenience input only. Always support audio upload and a fallback path if extraction fails.

**AI Coach:** Anthropic Claude API (`claude-sonnet-4-20250514`). Used for lesson copy generation, session review feedback, study step explanations, and jam session summaries. System prompt design is specified in the AI Coach section below.

### Database
- **Mobile:** SQLite (`expo-sqlite`) — local-first, no account required for v1.
- **Web:** IndexedDB (wrapped to match the SQLite interface where practical for shared app code).

```sql
CREATE TABLE skill_nodes (
  id TEXT PRIMARY KEY,                -- e.g. "bend_accuracy"
  label TEXT,
  score REAL DEFAULT 0.0,             -- 0.0–1.0, moves slowly via weighted average
  sessions_count INTEGER DEFAULT 0,
  last_session_date TEXT,
  easiness_factor REAL DEFAULT 2.5,   -- SM-2
  interval_days INTEGER DEFAULT 1,    -- SM-2
  next_review_date TEXT               -- ISO date string; home screen suggestion uses this
);

CREATE TABLE sessions (
  id TEXT PRIMARY KEY,
  song_title TEXT,
  artist TEXT,
  section_label TEXT,
  date TEXT,
  coach_review TEXT,
  pitch_accuracy REAL,
  phrasing_score REAL,
  nodes_targeted TEXT                 -- JSON array of skill node IDs
);

CREATE TABLE licks (
  id TEXT PRIMARY KEY,
  song_title TEXT,
  artist TEXT,
  key TEXT,
  scale TEXT,
  position TEXT,
  tab_gp5_base64 TEXT,
  audio_segment_path TEXT,            -- local file path to isolated guitar clip
  coach_oneliner TEXT,
  technique_tags TEXT,                -- JSON array
  user_annotations TEXT,              -- JSON array of { bar, text }
  date_saved TEXT
);

CREATE TABLE jam_snapshots (
  id TEXT PRIMARY KEY,
  date TEXT,
  duration_seconds INTEGER,
  scale_position_map TEXT,            -- JSON: { "Am pent pos1": 0.6, ... }
  recurring_gestures TEXT,            -- JSON array of gesture description strings
  coach_summary TEXT
);
```

**Spaced repetition (SM-2 in TypeScript, ~80 lines):** After each session, update targeted skill node fields: `easiness_factor`, `interval_days`, `next_review_date`. The home screen suggestion is always the node whose `next_review_date` is earliest (or today). Skill node scores update via weighted moving average: `new_score = (old_score × 0.8) + (session_score × 0.2)`. Nodes move slowly by design — a single great session adds ~4% to a node.

---

## App Structure & Screens

### 1. Onboarding — Placement Session

*Runs once on first launch. ~5 minutes. Cannot be skipped — the app needs a baseline to give useful suggestions. Make it feel like tuning up, not a test.*

**Welcome screen:** App name + tagline — *"Practice less. Sound more like yourself."* Single CTA: "Let's hear you play." No feature list, no screenshots.

**Mic permission:** Requested before the first phrase. If denied: a warm explanation screen ("Harmoniq needs to hear you play — here's how to enable mic access in Settings") with a deep-link button to iOS/Android Settings. Do not proceed until granted.

**3 placement phrases:** Each displayed as a mini AlphaTab snippet + audio playback of the target phrase. Tap "Play along" to activate mic. The phrase loops twice; the user plays both times; the better take is scored.
- Phrase 1: A 4-note pentatonic run in A minor position 1, no ornaments. Tests pitch accuracy and basic position comfort.
- Phrase 2: A single bent note on the B string, held for 2 full beats, then released. Tests bend accuracy, hold duration, and release control.
- Phrase 3: A 4-bar lead phrase with deliberate space — two notes, rest, two more notes. Tests phrasing: does the user rush the rests? Cut notes short?

**Processing screen:** Warm pulsing animation. Text: *"Listening to how you play..."*

**Results screen:** 5 skill nodes as a simple radial diagram. Each node gets one plain-English sentence from Claude. Not scores. Not percentages. Examples:
- *"Your bends are close — you're landing the pitch but releasing too early."*
- *"You've got the notes. Your phrasing just needs to breathe more."*
- *"Solid position comfort. Let's start building vocabulary beyond position 1."*

**Cold start song prompt:** "What's a song you've always wanted to solo over?" → YouTube URL input. This becomes Session 1. If skipped, the app defaults to a built-in starter: "Gravity" by John Mayer (G major pentatonic, manageable tempo, expressive phrasing — a perfect first session).

---

### 2. Home Screen

*The screen you see every time you open the app. No streak counter. No guilt.*

**Top greeting:** One quiet, contextual line — not "Welcome back!" Examples:
- "Been a few days. No pressure — let's just play something." (last session > 5 days ago)
- "You've been working on bends. There's one more thing worth trying." (last session was yesterday)
- "First time here. Let's find out what you sound like." (right after onboarding)

**Suggested session card** (amber-accented, prominent): Driven by SM-2 — surfaces the skill node with the earliest `next_review_date`, tied to a song already in the library.
> *"Your bends are the thing to work on today. Let's use the solo from Gravity — 32 bars, G major pentatonic, position 2. Should take about 15 minutes."*
> `[Start Session]`

**Cold start (no session history yet):** Card reads: *"You haven't practiced a specific song yet. Add one below and we'll build your first session around it."* Start Session replaced by Add Song.

**Secondary options:**
- Work on a song → song picker
- Drill a technique → technique menu
- Add a new song → URL/upload input
- Jam Mode → passive listening screen

**Bottom nav:** Home | Library | Progress | Settings

---

### 3. Session Screen — The Core Loop

*A horizontal 5-dot step indicator at the top. Current dot filled amber.*

---

**Step 1 — Listen**

Isolated guitar stem plays at full speed. Gently pulsing waveform. Key, scale, and one coach note below.

**Section chips:** Intro / Verse / Solo / etc. — quick navigation by detected structure.

**Controls:** Play/Pause · Loop toggle · Speed slider (50%–100%) · Section jump markers

**Optional smart metronome:** Synced to the beat grid; follows tempo dynamically when the track’s tempo is known.

**Track mixer strip:** Pill-shaped toggles: `Guitar` `Bass` `Drums` `Vocals`. Independently mutable. Default: Guitar only. User can customize.

**Coach note:** One sentence auto-generated by Claude during analysis. Example: *"Mayer sits on the root note for a full beat before moving — that pause builds tension before the phrase resolves."*

---

**Step 2 — Study**

AlphaTab tab for the section rendered via WebView, styled to app palette.

**Full / Skeleton toggle:** Default to Skeleton on first view. Skeleton strips ornaments to the melodic core. Teaches the phrase's skeleton before adding expression.

**Scale overlay diagram:** 6-string fretboard (5 frets), root in amber, scale tones in cream, current position shown. "Alt position" link redraws both diagram and tab for the alternate position.

**Capo suggestion:** Based on key and position, suggest a capo placement when it keeps the phrase in a comfortable open or familiar shape.

**Lyrics timeline overlay:** A beat-aligned word strip above the tab for songs with vocals. Shows why guitar phrases land where they do — guitar phrasing in Mayer's playing mirrors the vocal. Toggle on/off.

**Personal annotations:** Long-press any bar → text input → saves as sticky note above that bar. User notes in cream. Claude auto-annotations in amber. Persist in SQLite with the lick record.

**Coach explanation:** 2–3 sentences from Claude on *why* this phrase sounds good musically — not technique instructions, musical reasoning.

---

**Step 3 — Slow & Loop**

Same playback controls, defaulting to 65% speed with pitch correction (`shouldCorrectPitch: true`).

**SmartScroll (timestamp-based):** The AlphaTab WebView scrolls to match the current playback position. Implementation: map `positionMillis` from `expo-av`'s `onPlaybackStatusUpdate` to the current bar index via binary search on the `bar_timestamps` array from the LessonJSON. Send `postMessage({ type: 'scrollToBar', barIndex: N })` to the WebView. AlphaTab scrolls smoothly. This is timestamp sync — reliable and straightforward to implement for v1. If measured drift exceeds 100ms, resync to the nearest bar.

The hardest bar (highest note density + ornament count from analysis) is pre-highlighted in amber and auto-looped on entry. User can change it.

---

**Step 4 — Play**

Mic activates. Track mixer defaults to Bass + Drums (guitar muted). Tab visible with SmartScroll active.

**Web:** Clear copy for the browser mic permission prompt; recommend headphones to reduce bleed and feedback.

**Real-time pitch indicator:** A small floating amber dot on a simplified pitch ladder (one octave, note names labeled). Tracks user's detected pitch in real time against target.
- Amber: within 50 cents of target
- Sage: within 15 cents (locked in)
- Terracotta: more than 50 cents off

SmartScroll advances from session start timestamp. Pauses if user stops for 2+ seconds.

**Session ends** when user taps "Done" or 5 seconds of silence is detected after the section's expected end. Recording buffer → `POST /score`.

---

**Step 5 — Review**

Not a score. A 3–4 sentence Claude coach paragraph: one observation, one actionable suggestion, one specific encouragement (or none if the session was rough — never generic praise).

**Phrasing visualizer:** User's recording waveform (terracotta) overlaid on the original guitar stem (cream), both anchored to vertical beat-grid lines. Visible at a glance: where you rushed, where you cut a note short. This is the single most powerful teaching tool in the app. Show it on every review.

**MIDI export:** Small "Export MIDI" link below the comparison. Exports the basic-pitch MIDI for the practiced section. Drop into GarageBand, slow to 40%, see every note as a piano roll. Zero extra build cost.

**Bottom actions:** `Save a Lick` · `Do it again` · `Next session →`

---

### 4. Lick Library

Scrollable personal library of saved phrases. Each lick card:
- Song title + artist
- Mini AlphaTab snippet (WebView, same approach)
- Playback button → isolated guitar audio clip
- Key, scale, position label
- Technique tags as pill badges
- Claude-generated one-liner
- Personal annotations
- `Drill this` → mini-session on just this lick
- `Transpose` key selector → tab redraws in new position (retranscoded from MIDI data)

Filter bar: by technique, by scale type, by song.

---

### 5. Progress Screen

No gamification. No XP. No level badges.

**Skill graph:** Radial diagram, 5–7 nodes. Tap any node for a plain-English status and one suggestion. Nodes move via weighted moving average from real session performance only.

**Session journal:** Past sessions listed reverse-chronologically — song, date, one-line coach takeaway. Tap any session to open the full phrasing visualizer for that recording.

**Jam vocabulary panel:** Horizontal bar chart of scale/position usage frequencies across all jam sessions. Shows natural tendencies — what the user reaches for when not thinking. Used by the coach to inform session suggestions.

---

### 6. Jam Mode — Passive Listening

*No task. No session. No score. Just play.*

Mic listens passively while the user noodles freely — over a backing track, a record in the room, or silence. Lightweight scale/position inference using pitch-class distribution (approximate) builds a timestamped map of scales and positions the user gravitates toward naturally — not full chord detection.

**Web:** Requires HTTPS and mic permission.

**Backing tracks** (bundled as MP3 loops in `/assets/backing-tracks/`, looped via `expo-av`):
- A minor, slow blues shuffle — 70 BPM
- A minor, open drone — ambient, no tempo
- G major, fingerpicking groove — 80 BPM (Tommy Emmanuel / acoustic)
- E minor, raw two-chord vamp — 90 BPM (Jack White style)
- G major, slow ballad — 65 BPM (Mayer ballad style)

**UI during jam:** Minimal. A gently pulsing ring animation. A real-time scale/position label in the center that updates as the user plays. No scoring. No waveform. Feels like a lit candle, not a dashboard.

**Ends** when user taps Stop or after 20 consecutive seconds of silence.

**After jam:** 2–3 sentence Claude summary. Vocabulary snapshot (scale/position frequencies) saved to SQLite. Example summaries:
- *"You kept coming back to position 1 of the A minor pentatonic. You've clearly got that shape. Let's start building vocabulary in position 2 next session."*
- *"You played a b5 passing tone three times. That blues note is already in you — next session, let's make it intentional."*

---

### 7. Settings Screen

**My guitar:**
- Guitar type: Acoustic | Electric | Acoustic-electric (affects technique suggestions — fingerpicking for acoustic, hybrid picking for electric)
- Tuning: Standard | Drop D | Open G | Custom (text input) — passed to analysis pipeline for accurate tab generation

**Practice style:**
- Style focus: Blues/Soul | Rock/Indie | Acoustic/Fingerpicking | All (multi-select) — weights SM-2 scheduler toward relevant skill nodes
- "Prefer simpler tabs when analysis is uncertain" toggle (favors skeleton / approximate labeling when confidences are low)

**Audio:**
- Mic input level (slider with live level meter)
- Playback output level
- Metronome toggle — adds a click track during the Play step, independent of stems
- Metronome BPM — auto-fills from song's detected tempo; editable

**Coach voice:**
- Feedback style: Encouraging | Direct | Mixed (adjusts Claude system prompt tone — see AI Coach section)

**Data:**
- Export practice journal (plain text file of all session coach takeaways)
- Clear all data (confirmation dialog — destructive, irreversible)

---

## Song Analysis Pipeline — Full Spec

**`POST /analyze` request:**
```json
{ "youtube_url": "https://youtube.com/watch?v=..." }
```
or multipart form with audio file (WAV/MP3/M4A, max 50MB).

**Processing sequence:**
1. `yt-dlp --extract-audio --audio-format wav --audio-quality 0` → `song.wav`. For uploads: `ffmpeg -i input -ar 44100 -ac 1 song.wav`
2. `demucs --model htdemucs_6s --out ./stems song.wav` → guitar / bass / drums / vocals / piano / other
3. Librosa analysis on guitar stem → key, tempo, beat grid, structure segments, bar_timestamps
4. Whisper on vocals stem → word-timestamped lyrics → mapped to beat grid
5. basic-pitch on guitar stem (solo/lead sections only) → MIDI → `.gp5` via py-guitarpro
6. Skeleton `.gp5` (ornaments filtered out)
7. Alternate position `.gp5` *(generate only if confidence is high; otherwise omit)*
8. Claude API call for coach_note + coach_explanation per section
9. Return LessonJSON

Cache results by **audio hash** and **pipeline version**. YouTube remains convenience input — always support direct audio upload and handle extraction failures gracefully.

**LessonJSON schema:**

Confidence fields (top-level and per section):

```json
{
  "key_confidence": 0.85,
  "tempo_confidence": 0.92,
  "transcription_confidence": 0.78,
  "sections": [
    {
      "confidence": 0.81
    }
  ]
}
```

Full example shape:

```json
{
  "job_id": "abc123",
  "song_title": "Gravity",
  "artist": "John Mayer",
  "key": "G major",
  "key_confidence": 0.85,
  "tempo": 72,
  "tempo_confidence": 0.92,
  "transcription_confidence": 0.78,
  "beat_grid": [0.0, 0.833, 1.667, 2.5],
  "bar_timestamps": [0.0, 3.33, 6.67, 10.0],
  "stems": {
    "guitar": "/stems/guitar.wav",
    "bass": "/stems/bass.wav",
    "drums": "/stems/drums.wav",
    "vocals": "/stems/vocals.wav",
    "piano": "/stems/piano.wav",
    "other": "/stems/other.wav"
  },
  "lyrics_aligned": [
    { "word": "Gravity", "time_seconds": 4.2, "bar": 2, "beat": 1 }
  ],
  "sections": [
    {
      "label": "Solo",
      "confidence": 0.81,
      "start_bar": 24,
      "end_bar": 32,
      "start_time_seconds": 79.2,
      "end_time_seconds": 105.6,
      "technique_tags": ["pre-bend", "vibrato", "phrasing"],
      "tab_full_gp5_base64": "...",
      "tab_skeleton_gp5_base64": "...",
      "tab_alt_position_gp5_base64": "...",
      "midi_base64": "...",
      "primary_position": "pentatonic position 2",
      "alt_position": "pentatonic position 4",
      "coach_note": "...",
      "coach_explanation": "..."
    }
  ]
}
```

**`POST /score` request:**
```json
{
  "recording_wav_base64": "...",
  "section": {
    "tab_full_gp5_base64": "...",
    "bar_timestamps": [...],
    "key": "G major"
  },
  "skill_nodes": ["bend_accuracy", "phrasing", "vibrato"]
}
```

**`ScoreResult` response:**
```json
{
  "pitch_accuracy": 0.78,
  "note_duration_deltas": [0.12, -0.34, 0.05, -0.8],
  "phrasing_score": 0.55,
  "bend_pitch_error_cents": 22,
  "rushing_score": 0.6,
  "node_scores": {
    "bend_accuracy": 0.72,
    "phrasing": 0.51,
    "vibrato": 0.0
  },
  "waveform_comparison": {
    "user_wav_base64": "...",
    "reference_wav_base64": "..."
  }
}
```

`note_duration_deltas`: array of (actual_duration − target_duration) in beats per note. Positive = held too long. Negative = cut short. Drives the phrasing visualizer bars.
`rushing_score`: 0.0–1.0 where 1.0 means consistently ahead of the beat. Computed by averaging note onset time offsets from the beat grid.

---

## AI Coach — Prompt Design

**Base system prompt (all calls):**
```
You are a warm, musical guitar coach — somewhere between a patient session musician
and a good friend who plays really well. You speak in plain English, never in music
theory jargon unless you explain it immediately. You never say "wrong note."
You talk about feel, space, tension, and where the music wants to go.
You give one specific, actionable observation per response — never a list.
You sound like a person, not an app.
Keep responses under 4 sentences. Never start with "Great job," "Nice work,"
or any generic praise opener. Lead with the observation.
The encouragement, if any, comes last and must be specific — never generic.
```

**Session review append:**
```
The player just practiced: [section.label] from [song_title] by [artist].
Key: [key]. Scale: [scale]. Position: [primary_position].
Pitch accuracy: [pitch_accuracy]. Phrasing score: [phrasing_score].
Rushing score: [rushing_score] (0 = behind the beat, 1 = rushing).
Note duration deltas: [note_duration_deltas] — negative = cut short, positive = held long.
Bend pitch error average: [bend_pitch_error_cents] cents.
Weakest skill nodes: [top 2 from SQLite]. Natural vocabulary from jams: [top 2 tendencies].
Generate a 3–4 sentence review. One observation. One actionable thing.
One specific encouragement — or none if the session was genuinely rough.
```

**Study step explanation append:**
```
Generate 2–3 sentences explaining why the following guitar phrase sounds good musically.
Section metadata: [section]. Technique tags: [tags].
Focus on musical reasoning (tension, resolution, phrasing, space) — not technique instructions.
Sound like a musician thinking out loud, not a teacher explaining a lesson.
```

**Jam session summary append:**
```
The player just jammed for [duration] minutes.
Scale/position usage: [scale_position_map].
Recurring gestures: [recurring_gestures].
Current skill graph gaps: [weak nodes].
Generate a 2–3 sentence summary. Note one natural tendency. 
Suggest one specific thing to make intentional in the next formal session.
```

**Coach voice variants** (driven by Settings preference):
- Encouraging: end every response with a warm, specific observation about what's working
- Direct: skip encouragement entirely if performance was weak — just the observation and the fix
- Mixed: default behavior above

---

## Error States

Every error should be warm, specific, and tell the user exactly what to do next. Never show a raw error code or stack trace.

| Situation | Message | Action |
|---|---|---|
| Mic permission denied | "Harmoniq needs to hear you play. Here's how to turn on mic access." | Deep-link to device Settings |
| YouTube URL invalid | "That URL didn't work — make sure it's a full YouTube link and try again." | Retry input |
| Analysis job failed | "Something went wrong processing that song. Try a studio recording — live versions sometimes have unusual audio." | Retry button |
| Analysis job timeout (>5 min) | "This one's taking longer than usual. We'll notify you when it's ready." | Background notification on completion |
| No internet during analysis | "You need a connection to analyze a new song. Your existing library works offline." | Dismiss |
| Audio too short (<30 sec) | "That clip is too short to analyze. Try a full song or a longer section." | Dismiss |
| Score endpoint failure | "Couldn't score that take — tap 'Do it again' to try once more." | Retry |
| No guitar stem detected | "Couldn't isolate a clear guitar track from this recording. Try a different version of the song." | Retry or pick different song |
| Low transcription confidence | "This part is a rough approximation — use it as a guide, not a rule." | Continue |
| Browser mic blocked | "Your browser is blocking mic access — click the lock icon to enable it." | Retry |

---

## V1 Scope Summary

**In v1:**
- Onboarding placement session (3 phrases, skill graph generation, cold start song, mic permission handling)
- Home screen with SM-2-driven session suggestion and cold start handling
- Full 5-step session loop (Listen → Study → Slow → Play → Review)
- Web support (React Native Web / Expo Web) alongside iOS and Android
- Song analysis via YouTube URL or upload (yt-dlp + htdemucs_6s + librosa + Whisper + basic-pitch); upload + fallback when extraction fails
- Drag-and-drop audio upload on web (plus file picker)
- 6-stem track mixer (Guitar / Bass / Drums / Vocals — independently mutable)
- AlphaTab: WebView on mobile, direct DOM on web; shared JSON interface (Full + Skeleton toggle)
- SmartScroll via bar timestamp sync (timestamp-based, not note-sequence-based — upgrade later); resync if drift >100ms
- Smart metronome (beat-synced, tempo-aware)
- Section navigation chips on Listen
- Capo suggestions on Study (key + position)
- Lyrics timeline overlay on Study step (Whisper-aligned)
- Scale overlay diagram + alternate position viewer (when confidence allows)
- Personal tab annotations (long-press any bar)
- Real-time on-device pitch detection: native-safe path on mobile (not JS worker threads); Web Audio on web — never hits network during play
- Beat-grid-anchored phrasing visualizer on Review step
- MIDI export per section
- Lick Library with transposition tool and Drill mode
- Progress screen: skill graph, session journal, full phrasing visualizer, jam vocabulary panel
- Jam Mode with 5 bundled backing tracks, lightweight scale/position inference (pitch-class distribution, approximate), Claude summary, vocabulary snapshot
- Settings screen (guitar type, tuning, style focus, metronome, coach voice, prefer simpler tabs when uncertain)
- Claude-powered coach (session review, study explanation, jam summary)
- Full error state handling for all failure modes
- Local storage: SQLite on mobile; IndexedDB on web — no account required
- Pipeline caching by audio hash + pipeline version; confidence-aware tabs and alternate positions

**Not in v1:**
- User accounts / cloud sync
- Social / sharing features
- Chord dictionary / rhythm playing curriculum
- Multi-instrument support
- Subscription / payments
- Spotify integration
- Offline song analysis (pipeline requires backend)
- Note-sequence-based SmartScroll (use timestamp sync for v1)

---

## Build Order (Recommended)

**Week 1–2 — Backend pipeline proof of concept**
Jupyter notebook only. Take one song (suggest: Gravity by John Mayer). Run yt-dlp → htdemucs_6s → librosa → basic-pitch → py-guitarpro. Confirm you can see the solo notes in an AlphaTab render. This is your "does the tech work" gate. Do not proceed until this pipeline produces a clean `.gp5` file.

**Week 3–4 — Real-time pitch detection**
Browser or React Native prototype. Mic → native-safe / AudioWorklet path (no JS worker threads for DSP) → pitch indicator on screen. Then: record yourself playing a phrase, compare your pitch trajectory to a target sequence. Add rush/lag detection using onset offsets from the beat grid.

**Week 5–6 — Core session UI**
Minimal React Native: song input → analysis polling → Listen step (expo-av + track mixer) → Study step (AlphaTab WebView + skeleton toggle) → Play step (pitch indicator) → Review (phrasing visualizer). No skill graph yet. Just the loop.

**Week 7–8 — Skill model + adaptive suggestions**
Placement session. Skill graph radial diagram. SM-2 scheduler. Home screen suggestion card. The app now knows what to drill and why.

**Week 9+ — Jam Mode + lick library + settings**
Jam Mode passive listener and vocabulary snapshots. Lick Library with transposition. Settings screen. Claude coach prompt tuning based on real usage.

---

## Guiding Principles for Every Build Decision

1. **Feel over score.** The app teaches musicality, not accuracy. Feedback is always framed musically.

2. **Song-first.** Every session anchors to a real song the user chose. No abstract exercises. No "play a C major scale." Always in context.

3. **No guilt, no schedule.** Zero streak mechanics. The app meets you where you are today, not where you were last week.

4. **One thing at a time.** Every session surfaces one insight. The coach never gives lists. The enemy of improvement is being overwhelmed.

5. **The app disappears.** The best session is one where the user forgets they're using an app and just plays. Fewer taps, fewer decisions, more music.

6. **Real-time is sacred.** Anything running while the user is playing must live on-device. Latency during live play breaks everything. Everything else can be async.

7. **Nodes move slowly.** A single great session adds ~4% to a node. Three consistent sessions add ~11%. Players should feel like they're genuinely improving, not collecting points.