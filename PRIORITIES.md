# Harmoniq — Engineering Roadmap

Three-phase product roadmap for **risk first**, **vertical slices**, and **mobile + web** parity. Follow in sequence unless a kill-switch fails.

**Phase 0 (0.1–0.6)** — **complete**. **Phase 1 (commits 1–97)** — **complete**.

---

## At a glance

| | |
|--|--|
| **Roadmap status** | **Phase 2: Feedback, Retention & ML Refinement. Phase 3: Planned.** |
| **Product spec** | [`README.md`](README.md) |
| **UI spec** | [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md) |
| **E2E / release** | [`docs/E2E_DEMO.md`](docs/E2E_DEMO.md) |
| **Manual QA** | [`docs/MANUAL_QA.md`](docs/MANUAL_QA.md) |
| **Scoring** | [`docs/SCORING.md`](docs/SCORING.md) |
| **Archive** | [`priorities-archive.md`](priorities-archive.md) (Phase 0 + Phase 1) |

---

## PHASE 2: Feedback, Retention & ML Refinement

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

### Commit 98: Advanced Extension Recognition

**Goal:** Upgrade the TFLite chord estimator from 25 classes (major/minor/no-chord) to 60+ chord types including 7ths, 9ths, 11ths, 13ths, and altered dominants (7#9, 7b13, alt7).

**Current State:** `build_chord_tflite.py` has only 25 classes (12 major + 12 minor + N) with synthetic 12-bin chroma templates.

**Scope:**
- Extend `CHORD_VOCAB` in `build_chord_tflite.py` with chord qualities:
  - 7th chords: dominant 7 (C7), major 7 (Cmaj7), minor 7 (Cm7)
  - Extended: 9ths (C9, Cm9, Cmaj9), 11ths, 13ths
  - Altered: 7#9, 7b9, 7#5, 7b5, alt7
  - Suspended: sus2, sus4, sus7
  - Other: dim, dim7, aug, 6, m6
- Define `CHORD_INTERVALS` mapping for all qualities
- Update `make_chroma_template()` to generate templates for extended chords including overtones
- Regenerate `chord_model.tflite` with expanded vocabulary

**Acceptance Criteria:**
- [ ] Chord vocabulary expanded from 25 to 60+ classes
- [ ] `CHORD_INTERVALS` defines semitone patterns for all qualities
- [ ] Synthetic templates include extended chord tones (9th=+14, 11th=+17, 13th=+21)
- [ ] Model trains successfully with expanded vocabulary
- [ ] TFLite conversion completes without errors
- [ ] Smoke test passes for D7, Cmaj7, Am7 chord types

---

### Commit 98a: Chord Data Generation Improvements

**Goal:** Enhance synthetic training data to better approximate real-world audio variability.

**Current State:** `generate_dataset()` produces clean synthetic chroma with Gaussian noise only.

**Scope:**
- Add inversion simulation: rotate chord tones so bass ≠ root (1st/2nd inversions)
- Implement missing note simulation: randomly drop chord tones to model sparse arrangements
- Add pitch-shifting augmentation: circular shift chroma bins (±1 semitone)
- Implement time-stretching: interpolate chroma frames (±10% speed variation)
- Add bass-note ambiguity: inject low-frequency energy to simulate non-root bass
- Replace Gaussian white noise with pink noise for more realistic spectral profile
- Generate chord transition samples: 50/50 mixed windows at chord boundaries

**Acceptance Criteria:**
- [ ] Inversion parameter generates 1st/2nd inversion templates
- [ ] Missing note dropout rate configurable (default 15%)
- [ ] Pitch shift augmentation covers ±2 semitones
- [ ] Time stretch factor range: 0.9x - 1.1x
- [ ] Pink noise generation replaces white Gaussian noise
- [ ] Transition samples improve boundary detection accuracy

---

### Commit 98b: 36-Bin CQT Feature Extraction

**Goal:** Replace 12-bin chroma with 36-bin CQT (3 octaves × 12 bins) to preserve octave information for better chord discrimination.

**Current State:** Model uses 12-bin chroma which loses octave context needed for bass-note detection.

**Scope:**
- Update `CHROMA_BINS = 36` in model input shape
- Implement `librosa.cqt()` extraction with `n_bins=36, bins_per_octave=12`
- Reshape CQT: sum magnitude across octaves but preserve octave structure
- Update `make_chroma_template()` to generate 36-bin templates
- Add bass-chroma separation: low CQT bins (0-3) as separate feature channel
- Update data generation to produce 36-bin synthetic features

**Acceptance Criteria:**
- [ ] Model input shape updated to `(WINDOW, 36)`
- [ ] CQT extraction produces 36-bin features with octave preservation
- [ ] Bass chroma (low 4 bins) separated as additional input channel
- [ ] Synthetic templates generate 36-bin harmonic distributions
- [ ] Training accuracy improves vs 12-bin baseline (target: +5%)

---

### Commit 98c: CRNN Architecture with Bidirectional LSTM

**Goal:** Extend temporal context from 9 frames (~200ms) to 128+ frames (~2.5-6s) and add recurrent layers for chord progression modeling.

**Current State:** Shallow CNN with only 9-frame window cannot model chord progressions or temporal dependencies.

**Scope:**
- Increase `WINDOW` from 9 to 128 frames (configurable 64-256)
- Add CNN frontend: Conv1D(64) → MaxPool → Conv1D(128) → MaxPool
- Insert Bidirectional LSTM layers after CNN:
  - `Bidirectional(LSTM(128, return_sequences=True))`
  - `Bidirectional(LSTM(128, return_sequences=False))`
- Add Dropout(0.3) between recurrent layers
- Update `build_model()` to return CRNN architecture
- Ensure TFLite compatibility with SELECT_TF_OPS

**Acceptance Criteria:**
- [ ] Model accepts 128-frame temporal windows
- [ ] CNN frontend reduces temporal resolution before LSTM
- [ ] Bidirectional LSTM layers capture forward and backward dependencies
- [ ] TFLite conversion succeeds with recurrent layers
- [ ] Inference latency <100ms on target mobile device
- [ ] Validation accuracy improves vs shallow CNN (target: +8%)

---

### Commit 98d: Multi-Head Self-Attention Mechanism

**Goal:** Add attention layers to let model focus on salient harmonic peaks in chroma features.

**Current State:** No attention mechanism; model treats all chroma bins equally.

**Scope:**
- Add `MultiHeadAttention(num_heads=4, key_dim=64)` after CNN frontend
- Implement attention masking for valid sequence positions
- Add LayerNorm after attention block
- Update model architecture: CNN → Attention → LSTM → Dense
- Verify TFLite conversion compatibility with attention ops

**Acceptance Criteria:**
- [ ] Multi-head attention attends to chroma bin relationships
- [ ] Attention weights visualizable for interpretability
- [ ] TFLite conversion includes attention ops (SELECT_TF_OPS)
- [ ] Model size increase <20% from attention parameters
- [ ] Accuracy improvement on extended chords (target: +3%)

---

### Commit 98e: Viterbi Decoding for Chord Progressions

**Goal:** Post-process frame-wise predictions with Viterbi algorithm to enforce plausible chord transitions and smooth sequences.

**Current State:** No post-processing; frame-wise predictions can flicker between chords.

**Scope:**
- Build transition probability matrix from training data (60×60 for extended vocab)
- Implement Viterbi decoder in Python for backend post-processing
- Add log-probability computation for soft-max outputs
- Implement backtracking for optimal path reconstruction
- Integrate into chord inference pipeline after TFLite inference
- Add transition matrix caching for performance

**Acceptance Criteria:**
- [ ] Transition matrix computed from real chord progression data
- [ ] Viterbi decoder produces smoothed chord sequences
- [ ] Decoding latency <10ms for 30-second audio
- [ ] Reduced chord flickering in predictions (target: 40% reduction)
- [ ] Integration test with known chord progression (e.g., ii-V-I)

---

### Commit 98f: Real Dataset Integration (Isophonics/Billboard)

**Goal:** Train on real annotated audio instead of purely synthetic data to improve real-world accuracy.

**Current State:** Model trained only on synthetic chroma templates; no exposure to real audio characteristics.

**Scope:**
- Download Isophonics dataset (Beatles, Queen, etc. with chord annotations)
- Download McGill Billboard dataset (pop/rock with chord labels)
- Write preprocessing script to extract CQT and align with chord labels
- Convert annotations to extended chord vocabulary (map rare qualities to closest match)
- Combine real + synthetic data (70/30 split recommended)
- Add dataset mixing to training pipeline

**Acceptance Criteria:**
- [ ] Isophonics dataset loaded and preprocessed
- [ ] Billboard dataset loaded and preprocessed
- [ ] CQT features extracted and aligned with chord labels
- [ ] Train/val/test split with no artist overlap
- [ ] Real data comprises 70% of training batches
- [ ] Validation accuracy on Isophonics test set >75% root accuracy

---

### Commit 98g: Training Infrastructure Improvements

**Goal:** Add proper training callbacks, augmentation, and evaluation metrics.

**Current State:** Only 12 epochs, no callbacks, no validation metrics beyond accuracy.

**Scope:**
- Add `EarlyStopping` callback (patience=5, restore_best_weights)
- Add `ReduceLROnPlateau` callback (factor=0.5, patience=3)
- Implement time-stretch augmentation in training loop
- Add pitch-shift augmentation (±2 semitones)
- Generate confusion matrix during validation
- Compute per-class precision/recall/F1 metrics
- Add class weighting to handle chord imbalance
- Increase training epochs from 12 to 50

**Acceptance Criteria:**
- [ ] Early stopping prevents overfitting
- [ ] Learning rate reduces automatically on plateau
- [ ] Time stretch and pitch shift augmentations active
- [ ] Confusion matrix identifies confused chord pairs
- [ ] Per-class metrics reveal rare chord performance
- [ ] Training completes in <2 hours on available hardware

---

### Commit 98h: Quantization-Aware Training

**Goal:** Improve TFLite quantization accuracy by training with quantization constraints rather than post-training quantization.

**Current State:** Post-training quantization may degrade accuracy for extended chord vocabulary.

**Scope:**
- Integrate `tensorflow_model_optimization` toolkit
- Apply `quantize_model()` wrapper to training model
- Implement QAT (Quantization-Aware Training) for 4-5 epochs
- Compare accuracy vs post-training quantization baseline
- Generate INT8 quantized model for mobile deployment

**Acceptance Criteria:**
- [ ] QAT model trained with simulated quantization
- [ ] INT8 quantized model produced
- [ ] Accuracy degradation <3% vs float32 model
- [ ] Model size <500KB after quantization
- [ ] Inference latency reduction confirmed on mobile device

---

### Commit 99: Inversion & Slash Chord Logic

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

### Commit 100: Voicing & Position Inference

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

### Commit 101: Live Mic Mode

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

### Commit 102: The "Chord Pulse" Dashboard

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

### Commit 103: Multi-Instrument Diagram Support

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

### Commit 104: 6-Stem High-Fidelity Demucs

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

### Commit 105: Real-Time Stem Mixer & Export

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

### Commit 106: Dynamic Session Engine

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

### Commit 107: Orient-as-Hint

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

### Commit 108: Mastery & Integrity

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

### Commit 109: Dynamic Tempo Support (Variable BPM)

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

### Commit 110: Redis Job Queue + Celery Workers

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

### Commit 111: Dedicated ML Model Server

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

### Commit 112: GPU Job Queue for Demucs

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

### Commit 113: Error Resilience (Circuit Breakers, Retry, DLQ)

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

### Commit 114: Monitoring & Observability (Prometheus, Grafana)

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

### Commit 115: Audio Fingerprinting & Quality Scoring

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

