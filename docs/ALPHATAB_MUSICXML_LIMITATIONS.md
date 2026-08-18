# AlphaTab MusicXML rendering limitations (living doc)

> Commit 107 made MusicXML the primary render format. AlphaTab officially
> labels its MusicXML importer **"experimental"** (`@coderline/alphatab` README),
> so this doc tracks what works, what degrades, and what to verify before
> shipping features that depend on MusicXML fidelity.

## Current verification status (Aug 2026)

- 24-file edge-case corpus renders without crash through AlphaTab (web DOM +
  native WebView share the same importer/rendering engine).
  See `backend/tests/test_musicxml_corpus.py` (`alphatab_corpus_check.mjs`).
- The corpus XML is validated against the official MusicXML 3.1 Partwise DTD
  (`backend/tests/fixtures/musicxml-dtd/`).
- Web visual baselines: `tests/ui/musicxml-render.spec.ts` + snapshots.
- Native gate: `tests/mobile/musicxml-render.e2e.js` (Detox, Android).
- Backend exporter guarantees for generated scores: `backend/tests/test_exporter.py`
  (harmony + frames, notation elements, `<defaults>`, trailing-content integrity,
  DTD validation).

## Known limitations

### Import fidelity (verified or upstream-labeled)

| Area | Status | Notes |
|------|--------|-------|
| Irregular meters (5/4, 7/8, 9/8) | Works | corpus `irregular-5-4`, `irregular-7-8`, `irregular-9-8-compound` |
| Meter changes | Works | corpus `meter-change-4-4-to-3-4` |
| Nested / non-power-of-2 tuplets | Partial | corpus `nested-tuplets`, `quintuplet-septuplet`; music21 itself warns on multi-tuplet durations — import survives, visual accuracy not asserted |
| Polyrhythms (multi-voice) | Works | corpus `polyrhythm-3-2`, `polyrhythm-4-3`, `multi-voice-staff` |
| Tempo changes | Works | corpus `tempo-change-60-to-240` |
| Keys / accidentals | Works | corpus `key-signature-fsharp-minor`, `key-signature-eb-major`, `accidentals-alter` |
| Ties + slurs | Works | corpus `ties-and-slurs`; exporter emits start/stop pairs |
| Dots + 32nds | Works | corpus `dots-and-32nds` |
| Rests (incl. multi-measure) | Works | corpus `rest-heavy`, `empty-measure-rests`, `multi-measure-rest` |
| Pickup measures | Works | corpus `pickup-measure` |
| Grace notes | Works | corpus `grace-notes` |
| Wide pitch range | Works | corpus `wide-range-lead` |
| Chord symbols (`<harmony>`) + frames | Partial | exporter renders `<harmony>` + `<frame>`; AlphaTab chord-diagram rendering fidelity not visually baselined |
| `<defaults>` page/scale | Partial | exporter emits defaults block; scale is `7/40` (0.175) to keep scores compact — layout differs from engraving tools |
| Dynamics/articulations | Partial | exporter emits them; visual placement fidelity not baselined |
| Tab staff (TAB clef part) | Partial | exporter emits parallel P2 part; standard tuning assumed — non-standard tunings are NOT asserted |
| `<forward>` / gap elements | Partial | alphaTab models gaps as linear beat structures (see `alphaTab.d.ts` importer notes) |

### Engine-level caveats (web vs native)

- Web renders via the **DOM** engine (SVG inside a scroll div); native WebView
  renders the same DOM engine inside the harness. Both use the same ScoreLoader,
  so import behavior is identical; **layout is not pixel-identical** between the
  two (fonts: `DM Sans`/web vs Android system fonts in WebView, `-webkit` metrics).
  Never share web snapshots as native expectations.
- `settings.core.engine = 'svg'` (Node, harness) and `'dom'` (web) share the
  layout pass; only rasterization differs. The corpus no-crash gate uses `svg`.

## Guardrails for future work

1. **Never ship a feature that depends on a MusicXML element listed "Partial"
   without adding a corpus case + baseline first** (add to `generate_musicxml_corpus.py`
   or `test_exporter.py`).
2. Run `backend/tests/test_musicxml_corpus.py` after any alphaTab version bump —
   the importer is experimental and can regress silently between minors.
3. Non-standard guitar tunings and `<harmony>` visuals are the two highest-risk
   gaps for the product; verify them manually on device before touching the
   session flow.
4. If AlphaTab upstream ships importer fixes, re-run:
   - `./backend/.venv-wsl/bin/python backend/scripts/generate_musicxml_corpus.py --force`
     (only if corpus source changes; files are committed)
   - `npm run test:visual:update` (web baselines)
   - `npm run test:mobile` (native)
