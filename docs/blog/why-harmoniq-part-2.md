# Why I'm Building Harmoniq, Part 2: The Pipeline That's Honest About Its Limits

*July 2026 — 7 minute read*

In Part 1, I described the plateau — playing notes that arrive on time but don't sound like music — and why I started building Harmoniq, an AI-powered practice companion that adapts to your playing instead of grinding you through levels.

Part 2 is about what I actually built. Not what I planned to build. Not what I hope to build. The pipeline that exists today, running on a CPU, transcribing real songs, failing gracefully when it should.

---

### The architecture, as it lives right now

Every guitar practice app needs to answer one question: what is the user playing? That's Automatic Music Transcription (AMT) — taking audio and producing notes, chords, and timing. It's a hard problem that researchers have been working on for decades.

Harmoniq's pipeline has four layers, each one catching what the previous one misses:

```
Audio → Demucs (stem separation) → MT3 (primary transcription)
                                         │
                                    CRNN fallback (when MT3 is unavailable)
                                         │
                                    Chroma matching (when CRNN is uncertain)
                                         │
                                    LessonJSON with confidence scores
```

**Layer 1: Demucs.** Separates the audio into six stems: guitar, bass, drums, vocals, piano, and other. This runs via PyTorch with the `htdemucs_6s` model. It takes about a minute on CPU and produces clean splits for most studio recordings. Live recordings with bleed between microphones are harder — some guitar ends up in the vocals stem, some vocals bleed into guitar. We take the best separation we can get and route from there.

**Layer 2: MT3 (primary).** Google's Music Transcription Transformer (ICLR 2022) is the workhorse. It takes log-mel spectrograms from the full mix and decodes a token stream where every note event has a pitch, time, duration, velocity, and instrument program number. It transcribes everything — guitar, piano, drums, vocals — in one pass.

MT3 is remarkable. It doesn't need instrument-specific training. It was trained on thousands of hours of multi-instrument audio and generalizes to instruments it's never explicitly seen. I run it on CPU with the T5-small checkpoint (60 million parameters). A 3-minute song takes about 5 minutes to transcribe. It's not fast, but it works.

**Layer 3: CRNN (fallback).** When MT3 isn't available — missing dependencies, network timeout, or the user just needs an answer faster — there's a smaller Convolutional Recurrent Neural Network trained specifically for guitar chord recognition. It uses 36-bin CQT features with 12.8-second context windows and a bidirectional LSTM.

This model achieves 70% accuracy on synthetic guitar audio and 34.7% on real recordings. That number deserves its own section.

**Layer 4: Chroma matching (last resort).** When the neural model predicts "no chord" on more than 80% of frames — which it does when the audio looks nothing like guitar — a purity-of-chroma template matcher takes over. It's simple, it's been around for decades, and it produces usable results for straightforward major/minor harmony. It won't get your extensions right, but it won't crash either.

---

### Why 34.7% is not a failure

The CRNN model's 34.7% real-world accuracy was a defining number in this project. In Part 1, I called it "the plateau." Let me be more precise now.

The model predicts "N" (no chord) on the majority of frames when given unfamiliar audio. This is not incorrect behavior. The model was trained on 12,825 labeled CQT windows from datasets like GuitarSet and IDMT-SMT-Guitar — clean recordings made in controlled conditions. When you feed it a live recording with room reverb, mic bleed, and compression artifacts, it correctly identifies that it's out of its training distribution.

The model isn't saying "this is an unknown chord." It's saying "I don't know." That is the correct output for a confidence-aware system.

The quality gate — a function called `_neural_model_too_noisy()` — checks whether the CRNN's predictions are concentrated on the no-chord class. If >80% of frames predict N, the system doesn't show those results to the user. It falls through to chroma matching. This prevents the two worst outcomes in AMT: silently wrong chords displayed as correct, or the app being unusable because the model fails entirely.

Most AMT demos show the best case — clean studio audio, perfect separation, confident transcriptions. Real pipelines need to handle the messy middle, and that requires explicit confidence reporting and honest fallback behavior.

---

### The two-branch insight

The design decision I'm most proud of isn't a model architecture. It's a routing decision:

**Chords come from the full mix. Solo notes come from the guitar stem.**

Most AMT systems do everything from one input. If you extract chords from the guitar stem alone, you miss chord tones played by the bass or piano. If you extract solo notes from the full mix, you get instrument bleed and ghost notes.

Harmoniq has two branches:

- **Branch A (chords):** Takes the full mix (or a harmonic-bed submix with drums removed) and runs instrument-agnostic chord extraction. It doesn't care which instrument is playing a pitch, only that the pitch is present. This gives correct chord symbols even when the guitar is playing sparse accompaniment while the piano fills in the harmony.

- **Branch B (solo):** Takes the isolated guitar stem from Demucs and transcribes the melodic line. Because the input is already guitar-only, there's no risk of transcribing vocal or piano notes as guitar notes.

This separation doubles the inference cost (two passes instead of one) but produces correct output that a single-pass approach can't match. For a research project running on a CPU, the tradeoff is worth it.

---

### What breaks

I've tested the pipeline on about a dozen songs. Here's what I've learned:

| Scenario | Result |
|----------|--------|
| Clean studio recording, clear guitar | MT3 produces excellent output on both branches |
| Live recording with crowd noise | MT3 works but confidence is lower; CRNN fallback may trigger |
| Complex extended harmony (jazz chords) | MT3 captures them; chroma fallback misses extensions |
| No guitar in the mix | Branch A still produces chords (correct), Branch B returns empty |
| Poor quality YouTube rip | Demucs separation suffers; bleed between stems lowers confidence |
| Song longer than 5 minutes | MT3 CPU inference exceeds reasonable time; CRNN covers it |

The system is honest about all of this. Every note and chord in the LessonJSON carries a confidence score. The UI can show uncertain transcriptions differently from confident ones. Users learn to read the confidence signal just as they learn to read chord symbols.

---

### What I'd do with more resources

If I had access to a GPU, HT-MT3 (Headed and Tailed MT3) would be the next step — it adds per-instrument decoder heads that reduce instrument confusion. I'd also retrain the CRNN on MT3-generated pseudo-labels, which could close the synthetic-to-real gap by giving it millions of training examples instead of 12,825.

Without a GPU, the pipeline is CPU-only and that's fine. It runs. It produces output. It's honest about its confidence. The code is open source, which means anyone with a GPU can pick up where I left off.

---

### What this project actually contributes

When I started, I thought I was building a novel AMT model. What I built instead is a working reference architecture for deploying AMT in a real application. The contributions are:

1. **A four-tier fallback chain** with explicit confidence gates at every level. Not a research paper — a deployment pattern.

2. **A two-branch routing decision** (chords from full-mix, solo from guitar stem) that prevents common failure modes of single-input AMT.

3. **Honest evaluation of off-the-shelf models on real-world audio.** Most AMT papers report results on curated datasets. This project reports results on YouTube rips, live recordings, and whatever else users throw at it.

4. **An open-source, runnable demo app** that connects AMT output to a real guitar practice interface. Not a Jupyter notebook — a shipped product.

These aren't the contributions I expected to make. They're the ones that matter.

---

### What's next

Part 3 will be about the meta-layer of this project: building an AI product with AI assistance, and what that recursive loop taught me about learning, building, and when to push through a plateau versus when to find a different path.

The code is open source at [github.com/cnkunda/harmoniq](https://github.com/cnkunda/harmoniq). The pipeline will process any audio you give it — just run the server, upload a track, and see what comes back. It might be confident. It might fall back to "I don't know." Either way, it'll be honest about it.
