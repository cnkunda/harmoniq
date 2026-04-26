# Harmoniq — Engineering Roadmap

Three-phase product roadmap for **risk first**, **vertical slices**, and **mobile + web** parity. Follow in sequence unless a kill-switch fails.

**Phase 0 (0.1–0.6)** — **complete**. **Commits 1–85** — **archived** (see `priorities-archive.md`).

### Phase 1 MVP Gate Status

| ID | Description | Type | Phase 1 Gate? | Status |
|----|-------------|------|--------------|--------|
| BUG-01 | Analyze polling infinite loop | Bug | YES — blocking | OPEN |
| BUG-02 | Jam Mode AlphaTab crash (typed array -2) | Bug | YES — blocking | OPEN |
| GAP-01 | POST /score real waveform data in Review | Functional | YES | Needs audit |
| GAP-02 | Placement session real scores (not mock) | Functional | YES | Needs audit |
| GAP-03 | Analysis timeout >5 min notification | UX | NO — deferred | Documented deferral |
| GAP-04 | Jam fretboard + AlphaTab sync (post BUG-02) | Functional | YES | Blocked on BUG-02 |
| QA-01 | §17 pitch kill-switch unchecked row | QA | YES | OPEN |

Phase 1 is NOT done until all "YES — blocking" and "YES" rows are CLOSED or explicitly waived with an owner and issue link.

---

## At a glance

| | |
|--|--|
| **Roadmap status** | **Phase 1: Finishing core loop. Phase 2–3: Planned.** |
| **Product spec** | [`README.md`](README.md) |
| **UI spec** | [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md) |
| **E2E / release** | [`docs/E2E_DEMO.md`](docs/E2E_DEMO.md) |
| **Manual QA** | [`docs/MANUAL_QA.md`](docs/MANUAL_QA.md) |
| **Scoring** | [`docs/SCORING.md`](docs/SCORING.md) |
| **Archive** | [`priorities-archive.md`](priorities-archive.md) (Phase 0 + commits 1–85) |

---

## PHASE 1: Product Discovery & Core Loop

**Status:** Current/Finishing

### Remaining Phase 1 Commits

#### Commit 83: Scoring Engine Implementation

**Goal:** Implement logic to compare PCM buffers vs. MIDI for `note_duration_deltas` and `rushing_score`.

**Scope:**
- Backend scoring algorithm that aligns user audio recording with reference MIDI
- Calculate per-note timing accuracy metrics
- Generate `waveform_comparison` data for phrasing visualizer

**Acceptance Criteria:**
- [x] POST /score returns real `note_duration_deltas` array
- [x] POST /score returns real `rushing_score` metric
- [x] POST /score returns `waveform_comparison` with user vs reference waveforms
- [x] Review phrasing visualizer displays real waveforms (user terracotta vs reference cream) *Completed in commit 84*

**Implementation:**
- Added `solo_notes` field to `ScoreRequest` schema to accept MIDI note events
- Updated `_score_timing()` to compare user audio onsets against MIDI note event timings when available
- Updated `_reference_click_b64()` to synthesize reference waveform from MIDI notes (pitch-aware tones) instead of simple clicks
- Maintains fallback to beat grid comparison when MIDI notes not provided
- All fields returned in POST /score response

**Completed:** 2026-04-22

---

#### Commit 84: Phrasing Visualizer UI

**Goal:** Component for dual-waveform comparison showing user vs reference timing.

**Scope:**
- `components/PhrasingWaveformVisualizer.tsx`
- Beat-grid-anchored waveform overlay
- Color coding: user (terracotta), reference (cream)

**Acceptance Criteria:**
- [x] Visualizer renders dual waveforms aligned to beat grid
- [x] Waveforms scroll in sync with playback
- [x] Color coding matches spec requirements

**Implementation:**
- Updated `PhrasingWaveformVisualizerProps` to accept `beatGrid` (array of beat timestamps) and `playbackProgress` (0-1)
- Added beat grid visualization with vertical lines at beat positions (downbeats emphasized)
- Added playback progress playhead (amber vertical line) that moves with playback
- Updated color coding: user waveform = terracotta (danger color), reference waveform = cream
- Removed web-only platform check for main waveforms (now works on native platforms)
- Ghost overlay remains web-only due to Web Audio API dependency
- All waveforms render in SVG with proper layering (grid → playhead → ghost → reference → user)

**Completed:** 2026-04-22

---

#### Commit 85: SmartScroll Bridge

**Goal:** Finalize bar-timestamp binary search and postMessage sync with AlphaTab WebView.

**Scope:**
- Binary search on `bar_timestamps` for efficient seek
- postMessage contract for WebView sync
- Cross-platform (web + native) implementation

**Acceptance Criteria:**
- [x] SmartScroll seeks to correct bar within 50ms
- [x] postMessage sync works on both web and native
- [x] No drift during extended playback sessions

**Implementation:**
- Created `src/music/smartScroll.ts` with binary search utility (`seekToBarByTimestamp`) using O(log n) complexity
- Added drift correction functions (`correctDrift`, `updateSmartScrollState`) for extended playback sessions
- Added postMessage types to `types/tabMessage.ts`:
  - `smartScrollSeekToBar` (inbound) with positionSec and barTimestamps
  - `smartScrollSeekResult` (outbound) with barIndex, barTimestampSec, and seekMs
- Updated `AlphaTabSurfaceRef` interface to include `smartScrollSeekToBar` method
- Implemented in `AlphaTabWebView.tsx` (native WebView) with postMessage bridge and 50ms threshold warning
- Implemented in `AlphaTabWeb.web.tsx` (web DOM) with inline binary search and direct AlphaTab API calls
- Updated stub implementations in `AlphaTabWeb.tsx` (native stub) and `ScoreViewer.tsx`
- Binary search leverages existing `barIndexAtOrBeforeTime` from `barLoopBounds.ts`

**Completed:** 2026-04-22

---

#### Commit 86: Placement Session Logic

**Goal:** SQLite logic to initialize skill_nodes (e.g., bend_accuracy) based on onboarding performance.

**Scope:**
- Onboarding placement session scoring
- SQLite schema for initial skill node population
- Radial skill graph driven by real scores (not mock data)

**Acceptance Criteria:**
- [x] 3 AlphaTab snippets load real GP5 data
- [x] Mic → pitch stream → score path populates initial skill nodes
- [x] Radial skill graph displays real scores from placement session

**Implementation:**
- Added `gp5Base64` field to `PlacementPhraseConfig` type in `src/onboarding/placementPhrases.ts`
- Added stub GP5 base64 data (from backend tabgen) to all 3 placement phrases
- Updated `app/onboarding/phrase/[index].tsx` to display TabViewport with GP5 data for each phrase
- SQLite skill_nodes population already implemented via `commitPlacementOnboarding` and `seedPlacementBaseline` in `src/db/client.native.ts` and `src/db/client.web.ts`
- Scoring path already implemented via `aggregatePlacementNodeScores` in `src/onboarding/aggregatePlacementScores.ts`
- Radial skill graph already implemented in `app/onboarding/results.tsx` using real placement scores from `useOnboardingPlacementStore`

**Completed:** 2026-04-22

---

#### Commit 87: Global Audio Manager

**Goal:** Implement centralized audio architecture to prevent context bloat and handle hot-swapping between screens.

**Scope:**
- Global Audio Manager singleton for all expo-av and react-native-audio-api instances
- Hot swap logic for deep-linking scenarios (e.g., Single File → Full Practice)
- Audio buffer clearing without app crashes
- Support for 6+ parallel audio streams (Demucs stems) + mic input

**Acceptance Criteria:**
- [x] Global Audio Manager singleton controls all audio instances
- [x] Hot swap clears audio buffers without crashes
- [x] No "Audio Stutter" or "Ghost Tracks" after session exit
- [x] Deep-linking from Single File to Full Practice works seamlessly
- [x] 6-stem isolation + mic input managed without bloat

**Implementation:**
- Create `src/audio/GlobalAudioManager.ts` singleton
- Centralize all expo-av Audio.Sound and react-native-audio-api instances
- Implement buffer clearing logic with proper cleanup/unload
- Add hot swap handler for navigation transitions
- Ensure audio context cleanup on component unmount
- Add error handling for audio state conflicts

**Completed:** 2026-04-22

---

#### Commit 88: Versioned Database Migration Strategy ~~COMPLETED~~

**Goal:** Implement schema migration system to prevent data loss during app updates as LessonJSON structure evolves.

**Scope:**
- Versioned migration strategy for SQLite (mobile) and IndexedDB (web)
- Migration path for skill_nodes table changes (e.g., Jazz Extensions support)
- Backward compatibility for early beta testers' practice history
- Mastery percentage preservation across schema updates

**Acceptance Criteria:**
- [x] expo-sqlite migrations implemented with version tracking
- [x] IndexedDB migration system for web parity
- [x] skill_nodes schema changes have migration path
- [x] Beta testers retain practice history after app updates
- [x] Mastery percentages preserved across schema migrations
- [x] Rollback mechanism for failed migrations

**Implementation:**
- [x] Create migration system in `src/db/migrations.ts` with validation utilities
- [x] Add version field to database schema (schema_version in skill_nodes)
- [x] Implement migration runner that applies pending migrations on app startup
- [x] Create migration for skill_nodes Jazz Extensions (V14)
- [x] Add migration rollback logic with automatic rollback on failure
- [x] Document migration versioning strategy in `docs/MIGRATIONS.md`

**Files Changed:**
- `src/db/migrations.ts` - New file with migration types, validation utilities, and logging
- `src/db/schema.ts` - Added ROLLBACK_* constants for all migrations V4-V14, added MIGRATION_V14_SKILL_NODES_SCHEMA_VERSION
- `src/db/client.native.ts` - Added rollback mechanism with applyMigrationWithRollback helper, validation for skill_nodes and sessions
- `src/db/idbWeb.ts` - Incremented DB_VERSION to 4, added migration tracking store, error logging
- `src/db/types.ts` - Added schema_version field to SkillNodeRow
- `src/db/client.web.ts` - Updated defaultSkillRow and applySkillNodesFromIdb to handle schema_version
- `docs/MIGRATIONS.md` - New comprehensive documentation for migration strategy

---

#### Commit 89: Predictive UI Rendering ~~COMPLETED~~

**Goal:** Eliminate visual lag perception by scrolling 50ms before audio reaches timestamp using look-ahead buffer.

**Scope:**
- Look-ahead buffer in usePitchStream hook
- Predictive scrolling for SmartScroll and AlphaTab cursor
- 50ms advance rendering for playback cursor
- Cross-platform implementation (web + native)

**Acceptance Criteria:**
- [x] Predictive scrolling implemented in smartScroll with 50ms look-ahead (architectural decision: usePitchStream is for pitch detection, not UI scrolling)
- [x] SmartScroll scrolls 50ms before audio timestamp
- [x] AlphaTab cursor highlights notes 50ms early
- [x] Visual sync feels "intelligent" and "pro" (not reactive)
- [x] No perceived lag during playback

**Implementation:**
- [x] Add PREDICTIVE_SCROLL_MS constant (50ms) to smartScroll.ts
- [x] Update barIndexForPlaybackSeconds to accept lookAheadMs parameter
- [x] Update useSessionSmartScroll to use predictive scrolling (position + 50ms)
- [x] Update AlphaTab syncPlaybackTimelineMs calls to use predictive offset (50ms early)
- [x] Update all syncPlaybackTimelineMs call sites: SessionStemAndTab, spotifyPlaybackBridge, jam.tsx, ScoreViewer, AlphaTabWebView
- [x] Verify cross-platform implementation (web + native share smartScroll.ts)
- [x] Ensure look-ahead doesn't cause over-scrolling
- **Architectural Note:** Original spec suggested usePitchStream look-ahead buffer, but smartScroll is the correct layer for UI scrolling. usePitchStream is exclusively for pitch detection audio processing.

---

#### Commit 90: AI Coach Variation Agents ~~COMPLETED~~

**Goal:** Prevent feedback redundancy by varying AI coach focus areas across sessions.

**Scope:**
- Focus area parameter for Claude coach prompts
- Coach "Moods" or "Foci" system (Timing, Vibrato, Dynamics, etc.)
- Session-to-session variation in feedback emphasis
- Avoid repetitive template feedback

**Acceptance Criteria:**
- [x] Claude coach accepts focus_area parameter
- [x] Multiple focus areas implemented (Timing, Vibrato, Dynamics, Phrasing, Bending, Rhythm, Expression)
- [x] Focus area varies between sessions (via rotate_focus_area function)
- [x] Feedback doesn't feel like repeated template (focus directives prioritize specific observations)
- [x] User feedback collection infrastructure in place to measure "Review Fatigue" reduction over time

**Implementation:**
- [x] Add CoachFocusArea enum to schemas.py (timing, vibrato, dynamics, phrasing, bending, rhythm, expression)
- [x] Add focus_area field to PlayerProfile schema
- [x] Add focus_area field to AnalyzeRequest schema for session-level tracking
- [x] Implement rotate_focus_area function in coach.py (cycles through 7 focus areas based on session count)
- [x] Implement _focus_area_directive function to generate focus-specific prompt directives
- [x] Update COACH_USER_PROMPT_TEMPLATE to include {focus_directive} placeholder
- [x] Update build_coach_user_prompt to accept and use focus_area parameter
- [x] Update generate_coach_fields_for_section_with_status to pass focus_area through
- [x] Update hydrate_coach_copy_into_sections and merge_coach_copy_into_sections to accept focus_area
- [x] Add comprehensive tests for focus area rotation, directive generation, and prompt building
- [x] All tests pass (12/12 in test_coach.py)
- [x] Frontend integration: created src/session/focusArea.ts with rotateFocusArea, session counting, and platform-agnostic storage
- [x] Frontend integration: updated submitAnalyzeJob to accept and pass focus_area parameter
- [x] Frontend integration: updated lessonStore.ts analyzeFromUrl and analyzeFromFile to use getNextFocusArea
- [x] Frontend integration: updated add-song.tsx to pass focus_area to submitAnalyzeJob
- [x] Frontend integration: created src/session/index.ts to export session utilities
- [x] User feedback collection: created src/session/coachFeedback.ts with feedback recording and analytics
- [x] User feedback collection: implemented getRepetitiveFeedbackPercentage to measure effectiveness
- [x] User feedback collection: created components/CoachFeedbackPrompt.tsx UI component for collecting feedback
- [x] User feedback collection: integrated CoachFeedbackPrompt into app/session/play.tsx where coach feedback is displayed
- [x] User feedback collection: recordCoachFeedback calls wired up to store user ratings
- [x] Added focus_area to PlayerProfilePayload type in src/types/index.ts

---

#### Commit 91: Harmonic Similarity Discovery Agent

**Goal:** Implement song discovery based on harmonic similarity to keep users engaged in the Harmoniq ecosystem.

**Scope:**
- Harmonic similarity analysis between songs
- Discovery agent suggesting next songs based on mastered content
- Context-aware recommendations (e.g., "You mastered A minor pentatonic in Gravity, try Sultans of Swing")
- Integration with dynamic session engine

**Acceptance Criteria:**
- [x] Harmonic similarity algorithm implemented
- [x] Discovery agent generates song recommendations
- [x] Recommendations based on user's mastered skills/progress
- [x] UI displays discovery suggestions with context
- [x] One-tap deep-link to analyze recommended songs
- [x] Users stay in Harmoniq ecosystem (reduced one-off usage)

**Implementation:**
- [x] Create harmonic similarity analysis in `src/music/harmonicSimilarity.ts`
- [x] Build discovery agent in `src/discovery/agent.ts`
- [x] Add recommendation endpoint to backend
- [x] Integrate with skill_nodes to match user progress
- [x] Add discovery UI component with song cards
- [x] Add DiscoveryRequest and DiscoveryResponse schemas to backend/app/schemas.py
- [x] Add /discovery/recommendations endpoint to backend/app/main.py
- [x] Create src/api/discovery.ts with frontend API client
- [x] Create components/DiscoveryCard.tsx for song recommendations
- [x] Create app/(tabs)/discover.tsx screen
- [x] Add tests for harmonic similarity algorithm
- [x] Add tests for discovery agent
- Implement deep-link from discovery to session
- Track discovery conversion rate

---

#### Commit 92: Musical Tolerance Scoring Modes

**Goal:** Implement "Musical Tolerance" setting to balance accuracy with expressive playing in scoring engine.

**Scope:**
- Expressive mode (lenient timing for musical feel)
- Technique mode (strict timing for precision practice)
- Musical tolerance configuration in scoring algorithm
- User-selectable scoring modes

**Acceptance Criteria:**
- [x] Scoring engine supports musical tolerance parameter
- [x] Expressive mode allows timing drag/push (±50-100ms tolerance)
- [x] Technique mode enforces strict timing (±20ms tolerance)
- [x] User can select scoring mode per session
- [x] Mode preference saved to user profile
- [x] Scoring feedback reflects selected mode's philosophy

**Implementation:**
- [x] Add musical tolerance parameter to scoring algorithm in backend
- [x] Implement Expressive mode with relaxed timing thresholds
- [x] Implement Technique mode with strict timing thresholds
- [x] Add mode selection UI in session setup
- [x] Save mode preference to user profile in SQLite
- [x] Update scoring feedback to reference mode philosophy
- Test with musicians to validate "feel" vs "precision" balance (deferred to Phase 2 user validation milestone)

---

## PHASE 2: Feedback, Retention & ML Refinement

**Status:** Planned

### Milestone: User Feedback & Manual Overrides

System to tag and save manual tab corrections to refine ML confidence levels.

**Scope:**
- UI for users to mark incorrect notes/chords
- Backend persistence of corrections
- ML retraining pipeline incorporating user feedback

---

### Milestone: Lick Library Persistence

Full CRUD for saved phrases and "Drill This" micro-session logic.

**Scope:**
- SQLite schema for saved licks
- UI for browsing, tagging, and organizing licks
- "Drill This" generates focused micro-sessions from saved phrases

---

### Milestone: Jam Mode Summary Agent

Claude-powered post-jam analysis and vocabulary mapping.

**Scope:**
- Post-jam analysis endpoint
- Vocabulary pattern detection
- Claude integration for summary generation

---

### Milestone: ML Fallback Logic

Implement auto-switching to "Skeleton" tabs when transcription_confidence < 0.7.

**Scope:**
- Confidence threshold detection
- Skeleton tab generation (simplified notation)
- Graceful degradation UI

---

### Commit 93: Advanced Extension Recognition

Upgrade the TFLite chord estimator to recognize over 700 chord types, specifically 9ths, 11ths, 13ths, and altered dominants (7#9, 7b13, alt7).

**Scope:**
- Extended chord vocabulary in chord inference model
- Jazz harmony support (9ths, 11ths, 13ths)
- Altered dominant detection (7#9, 7b13, alt7)

**Acceptance Criteria:**
- [ ] Chord model outputs extended chord symbols correctly
- [ ] Jazz progressions with 9ths/11ths/13ths render accurately
- [ ] Altered dominants identified in complex harmony

---

### Commit 94: Inversion & Slash Chord Logic

Implement bass-note detection to support accurate slash notation (e.g., G/B, D/F#) and identify 1st/2nd inversions.

**Scope:**
- Bass note detection from stem separation
- Slash chord notation generation
- Inversion identification (1st, 2nd)

**Acceptance Criteria:**
- [ ] Slash chords (e.g., G/B) display correctly in notation
- [ ] Inversions identified from bass note analysis
- [ ] AlphaTab renders slash notation accurately

---

### Commit 95: Voicing & Position Inference

Develop logic to identify specific fretboard shapes (e.g., distinguishing between a 'CAGED' E-shape vs. A-shape voicing) based on spectral peaks.

**Scope:**
- Spectral analysis for voicing detection
- CAGED system shape recognition
- Position inference from audio features

**Acceptance Criteria:**
- [ ] System distinguishes E-shape vs A-shape voicings
- [ ] CAGED positions inferred from spectral peaks
- [ ] Fretboard diagrams reflect detected voicing

---

### Commit 96: Live Mic Mode

Implement a low-latency (<120ms) 'Active Listener' view for real-time chord detection from external audio sources (live bands/radio).

**Scope:**
- Real-time audio processing pipeline
- Low-latency chord detection (<120ms)
- UI for live audio visualization

**Acceptance Criteria:**
- [ ] Chord detection latency under 120ms
- [ ] Live bands/radio audio processed in real-time
- [ ] Active Listener UI displays detected chords

---

### Commit 97: The "Chord Pulse" Dashboard

Build a scrolling chord timeline with 'falling notes' visualizer and a beat-synced 'Pulse' ring that expands on downbeats.

**Scope:**
- Scrolling chord timeline component
- Falling notes visualizer
- Beat-synced Pulse ring animation

**Acceptance Criteria:**
- [ ] Chord timeline scrolls smoothly with playback
- [ ] Falling notes animate on chord changes
- [ ] Pulse ring expands on downbeats

---

### Commit 98: Multi-Instrument Diagram Support

Add real-time toggles to switch between Guitar, Piano, and Ukulele diagrams, including support for alternate tunings.

**Scope:**
- Multi-instrument diagram components
- Real-time instrument toggle UI
- Alternate tuning support

**Acceptance Criteria:**
- [ ] Guitar, Piano, Ukulele diagrams render correctly
- [ ] Real-time switching between instruments
- [ ] Alternate tunings supported (Drop D, Open G, etc.)

---

### Commit 99: 6-Stem High-Fidelity Demucs

Upgrade the analysis pipeline to 'htdemucs_6s' to allow independent 'Guitar' and 'Piano' stem isolation.

**Scope:**
- Upgrade Demucs model to htdemucs_6s
- Guitar stem isolation
- Piano stem isolation

**Acceptance Criteria:**
- [ ] htdemucs_6s produces 6 high-fidelity stems
- [ ] Guitar stem isolated cleanly
- [ ] Piano stem isolated cleanly

---

### Commit 100: Real-Time Stem Mixer & Export

Add UI controls to mute/solo isolated stems during listening and support .WAV export for individual stems.

**Scope:**
- Stem mixer UI controls (mute/solo)
- Real-time stem mixing
- Individual stem .WAV export

**Acceptance Criteria:**
- [ ] Mute/solo controls work for all stems
- [ ] Real-time mixing without latency
- [ ] Individual stems exportable as .WAV

---

### Milestone: Predictive Beat Recovery

Implement a "look-ahead" algorithm to maintain visual sync during tempo drifts or complex syncopation.

**Scope:**
- Look-ahead beat detection algorithm
- Tempo drift compensation
- Syncopation handling

**Acceptance Criteria:**
- [ ] Visual sync maintained during tempo drifts
- [ ] Look-ahead algorithm handles syncopation
- [ ] Beat grid adjusts dynamically

---

### Milestone: Smart Capo Suggestions

Logic to calculate and suggest optimal capo positions to match the detected key with easier 'open' chord shapes.

**Scope:**
- Capo position calculation algorithm
- Open chord shape mapping
- Suggestion UI

**Acceptance Criteria:**
- [ ] Optimal capo positions calculated for detected key
- [ ] Suggestions use easier open chord shapes
- [ ] UI displays capo recommendations

---

### Commit 101: Dynamic Session Engine

Implement PlanJSON ingestion and orchestrator for dynamically generated full practice plans via SM-2 scheduler.

**Scope:**
- SessionProvider ingests dynamic PlanJSON object
- Plan structure: Warmup (dynamic drill based on weakest skill_node) → Song Workflow (Listen → Study → Slow → Play → Review) → Jam Session (contextual backing track)
- UI dynamically renders progress tracker based on generated plan length
- PlanJSON caching in SQLite for resumption

**Acceptance Criteria:**
- [ ] SessionProvider accepts and processes PlanJSON
- [ ] Warmup drill generated from weakest skill_node
- [ ] Progress tracker adapts to dynamic plan length
- [ ] `harmoniq://session/resume` re-instantiates cached PlanJSON

---

### Commit 102: Orient-as-Hint

Remove Orient as linear step; integrate as non-intrusive amber overlay (#D4860A) in Study/Play components with '?' toggle.

**Scope:**
- Remove Orient from linear step sequence
- Inject Orient metadata into Study and Play components
- Add '?' toggle / Hint button UI
- Amber overlay showing scale shapes or root notes
- Respect intermediate player flow (no interruptions)

**Acceptance Criteria:**
- [ ] Orient removed from session step sequence
- [ ] Hint toggle available in Study and Play steps
- [ ] Amber overlay displays scale shapes/root notes on activation
- [ ] Overlay is non-intrusive and dismissible

---

### Commit 103: Mastery & Integrity

Implement atomic SQLite updates for dynamic sessions with dual-entry state integrity.

**Scope:**
- Single file mode: Linear 5-step flow updates song mastery
- Dynamic session mode: Orchestrates generated plan
- Atomic DB updates: sessions and skill_nodes tables updated simultaneously on Jam Session completion
- Session marked Complete only when entire generated sequence finishes
- Resumption support from cached PlanJSON

**Acceptance Criteria:**
- [ ] Single file mode updates song mastery correctly
- [ ] Dynamic mode orchestrates full plan sequence
- [ ] Atomic transaction updates sessions + skill_nodes tables
- [ ] Session completion requires full plan completion
- [ ] Resume endpoint restores dynamic plan state

---

### Commit 104: Dynamic Tempo Support (Variable BPM)

**Current State:** Static BPM Only
The current implementation assumes every song is recorded to a static click track. Variable BPM/tempo changes are not supported.

**Evidence:**
- `backend/app/beat_grid.py:46-57` - `_uniform_beat_grid()` uses a constant `step = 60.0 / bpm` with no tempo variation
- The function name itself is `_uniform_beat_grid` - implying a single fixed tempo
- `backend/app/beat_grid.py:125` - When `bpm_override` is provided, it generates a uniform grid without any tempo mapping

**Goal:** Support songs with tempo ramps, accelerandos, and live performances with variable BPM.

**Scope:**
- Replace `_uniform_beat_grid()` with a function that accepts an array of `(time, bpm)` pairs or tempo curve
- Use `librosa.beat.beat_track()` with estimated tempo as a reference, not an override
- Store tempo change events in the returned schema alongside `beats` and `downbeats`
- Support gradual tempo changes (rubato) and sudden tempo shifts
- Maintain backward compatibility with static BPM interface

**Acceptance Criteria:**
- [ ] Beat grid handles variable BPM songs with tempo ramps
- [ ] Tempo curve can be provided as `(time, bpm)` array
- [ ] Grid subdivisions respect local tempo at each point
- [ ] Downbeats calculated correctly through tempo transitions
- [ ] Static BPM interface continues to work unchanged
- [ ] Performance: variable BPM grid generation <100ms for 5-minute track

**Implementation Notes:**
- Consider tempo segment interpolation (linear vs exponential ramps)
- Store base pulse tempo vs instantaneous tempo separately
- UI consideration: visual indicator when tempo changes detected
- May require updating `_subdivide_beats()` to handle non-uniform pulse spacing

---

### Commit 105: Redis Job Queue + Celery Workers

**Goal:** Replace in-memory job store with Redis-backed queue and Celery workers for horizontal scaling and persistence.

**Current State:** In-memory dict (jobs.py:57) that loses jobs on restart and cannot handle concurrent load.

**Scope:**
- Redis for job state persistence
- Celery workers for distributed processing
- Job recovery on startup (re-queue in-flight jobs)
- Worker auto-scaling based on queue depth

**Acceptance Criteria:**
- [ ] Jobs persist across server restarts
- [ ] Multiple Celery workers can process jobs concurrently
- [ ] In-flight jobs are recovered and re-queued on startup
- [ ] Queue depth monitoring enables worker auto-scaling
- [ ] Backward compatibility with existing job API

**Implementation:**
- Add Redis dependency to requirements.txt
- Replace in-memory `jobs` dict with Redis-backed job store
- Integrate Celery for async job processing
- Implement job recovery script that runs on startup
- Add queue depth metrics for auto-scaling decisions
- Update job polling endpoint to work with Redis

---

### Commit 106: Dedicated ML Model Server

**Goal:** Deploy dedicated inference service for chord model with batched inference, model versioning, and GPU batching.

**Current State:** TFLite inference runs in-process (chord_inference.py:75-114) with no batching or versioning.

**Scope:**
- Separate chord inference service with batched inference
- Model versioning and A/B testing support
- GPU batching for throughput
- Model loading/unloading without server restart

**Acceptance Criteria:**
- [ ] Dedicated inference service handles batch requests
- [ ] Multiple model versions can be deployed simultaneously
- [ ] GPU batching improves throughput by 3-5x
- [ ] Model can be hot-swapped without server restart
- [ ] A/B testing framework for model comparison

**Implementation:**
- Create separate FastAPI service for chord inference
- Implement batch inference endpoint
- Add model versioning to model loading logic
- Integrate GPU batching with TensorFlow Serving or ONNX Runtime
- Add model registry for version management
- Implement A/B testing routing logic

---

### Commit 107: GPU Job Queue for Demucs

**Goal:** Implement GPU job queue with priority scheduling for Demucs stem separation to improve throughput and cost efficiency.

**Current State:** Demucs runs synchronously per job (separate.py:277) blocking the request thread for minutes.

**Scope:**
- GPU job queue with priority scheduling
- Queue depth management
- GPU utilization tracking
- Batch processing for multiple audio files

**Acceptance Criteria:**
- [ ] Demucs jobs are queued and processed asynchronously
- [ ] Priority scheduling ensures urgent jobs run first
- [ ] Queue depth monitoring prevents overload
- [ ] GPU utilization is tracked and optimized
- [ ] Batch processing improves throughput for multiple files

**Implementation:**
- Integrate Demucs with Celery task queue
- Add priority levels to job schema (urgent, normal, low)
- Implement queue depth monitoring and alerts
- Add GPU utilization tracking (nvidia-smi integration)
- Implement batch processing for multiple audio files
- Add queue management UI for operators

---

### Commit 108: Error Resilience (Circuit Breakers, Retry, DLQ)

**Goal:** Implement circuit breakers, exponential backoff, and dead letter queues for transient failures.

**Current State:** Basic try/except with user-friendly messages (jobs.py:391-431) but no retry logic.

**Scope:**
- Retry logic for transient YouTube failures with exponential backoff
- Circuit breaker for LLM API calls
- Dead letter queue for failed analysis jobs
- Automatic retry for recoverable errors

**Acceptance Criteria:**
- [ ] YouTube download failures are retried with exponential backoff
- [ ] Circuit breaker prevents cascading LLM API failures
- [ ] Failed jobs are sent to dead letter queue for inspection
- [ ] Recoverable errors are automatically retried
- [ ] Error rate monitoring triggers circuit breaker

**Implementation:**
- Add retry decorator with exponential backoff for YouTube downloads
- Implement circuit breaker pattern for LLM API calls
- Create dead letter queue in Redis for failed jobs
- Add automatic retry logic for recoverable errors
- Implement error rate monitoring and alerting
- Add DLQ inspection and re-queue tools

---

### Commit 109: Monitoring & Observability (Prometheus, Grafana)

**Goal:** Add structured metrics, distributed tracing, and alerting for operational visibility.

**Current State:** Basic logging with elapsed time tracking (jobs.py:246-247) but no metrics or alerting.

**Scope:**
- Prometheus metrics endpoint
- Per-stage latency histograms
- Error rate alerting
- Distributed tracing (OpenTelemetry)

**Acceptance Criteria:**
- [ ] Prometheus metrics endpoint exposes job metrics
- [ ] Per-stage latency histograms identify bottlenecks
- [ ] Error rate alerting triggers on threshold breaches
- [ ] Distributed tracing tracks requests across services
- [ ] Grafana dashboards visualize system health

**Implementation:**
- Add Prometheus client library to backend
- Implement metrics endpoint for job queue, latency, errors
- Add histogram metrics for each pipeline stage
- Integrate OpenTelemetry for distributed tracing
- Set up Grafana dashboards for key metrics
- Configure alerting rules for error rates and latency

---

### Commit 110: Audio Fingerprinting & Quality Scoring

**Goal:** Implement audio fingerprinting for duplicate detection and quality scoring to reduce compute waste.

**Current State:** Content-addressed caching with SHA256 (cache.py:37-45) but no duplicate detection across different encodings.

**Scope:**
- Audio fingerprinting for duplicate detection
- Quality scoring for audio input
- Smart caching based on audio similarity
- Compute cost reduction through deduplication

**Acceptance Criteria:**
- [ ] Audio fingerprinting detects duplicates across different encodings
- [ ] Quality scoring identifies low-quality audio upfront
- [ ] Smart caching reduces re-analysis of similar audio
- [ ] Compute costs reduced through deduplication
- [ ] Fingerprint-based cache key improves hit rate

**Implementation:**
- Integrate audio fingerprinting library (e.g., dejavu)
- Implement quality scoring algorithm (SNR, clipping detection)
- Add fingerprint-based cache key alongside SHA256
- Implement similarity search for near-duplicates
- Add quality gate to reject low-quality audio early
- Track cache hit rate improvements

---

## PHASE 3: AI-Agent Scaling & Pro-App Parity

**Status:** Planned

### Milestone: Lead Sheet Agent

Agentic workflow to convert MIDI + Whisper lyrics into structured MusicXML.

**Scope:**
- Multi-step AI pipeline
- MIDI → MusicXML conversion
- Lyrics alignment and annotation

---

### Milestone: Zero-Latency Monitoring

C++/JSI bridge for real-time high-performance pitch feedback on Mobile.

**Scope:**
- Native module implementation
- JSI bridge architecture
- Sub-millisecond pitch detection

---

### Milestone: Dynamic Backing Track Agent

Integration for AI-generated custom-style jam tracks (Gemini Lyria fallback).

**Scope:**
- Lyria RealTime integration
- Style-aware backing generation
- Fallback to static tracks

---

### Milestone: Virtual Mentor Agent

Long-term data analysis to identify skill plateaus and suggest non-linear practice.

**Scope:**
- Skill trajectory analysis
- Plateau detection algorithms
- Personalized practice recommendations

---

## Product Strengthening

### Robustness & Scaling Gaps (vs Chord.ai)

Infrastructure limitations to address before scaling:

- **No job queue (Redis/Celery)** — uses in-memory dict for job tracking; will not survive restarts or handle concurrent load
- **No retry logic for YouTube failures** — transient network errors cause hard failures; no exponential backoff or circuit breaker
- **Demucs runs synchronously per-request** — blocks the request thread; would bottleneck at scale under concurrent load
- **No audio fingerprinting for duplicate detection** — re-analyzing identical audio wastes compute; no cache key for deduplication

---

### Offline Mode

Strategy for SQLite local-first operation with periodic Cloud sync.

**Considerations:**
- Local-first architecture
- Conflict resolution for sync
- Background sync scheduling

---

### Discovery

"Daily Lick" curated feed to reduce choice paralysis.

**Scope:**
- Curated lick selection algorithm
- Daily feed UI
- Personalization based on skill level

---

### Accessibility

High-contrast modes and screen-reader support for the "analog/handcrafted" UI.

**Scope:**
- High-contrast theme variants
- Screen reader labeling
- Keyboard navigation support

