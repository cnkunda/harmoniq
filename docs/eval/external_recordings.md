# External evaluation recordings (live / home / OOD)

The committed W0 manifest (`docs/eval/amt_manifest.json`) contains only
datasets that can be downloaded reproducibly. Live, home, and
out-of-distribution recordings are user-supplied and stay local.

This intake path lets you add them without contaminating the committed
manifest.

## Directory layout

```text
backend/data/eval_external/
  live/
    sunny_live.wav
    sunny_live.notes.json      # optional
  home/
    improv_blues.wav
    improv_blues.chords.json   # optional
  ood/
    kora_take.wav              # no annotations -> qualitative
  metadata.json                # optional overrides
```

`backend/data/` is gitignored. Do not commit the audio.

## Supported annotations (optional)

| File | Meaning |
| --- | --- |
| `<stem>.notes.json` | `[{pitch, onset, offset, velocity?, program?}]` |
| `<stem>.chords.json` | `[{start, end, chord}]` |
| `<stem>.jams` | JAMS `note_midi` and/or `chord` annotations |
| `<stem>.mid` | MIDI notes |

A recording with none of these is added as **qualitative**: the harness
records completion, runtime, and produced output, but does not score it and
does not assign a Pass/Warn/Fail verdict.

## Metadata overrides

`metadata.json` is optional. It can be a list or `{"tracks": [...]}`.

```json
{
  "tracks": [
    {
      "audio": "live/sunny_live.wav",
      "id": "external:live:sunny",
      "recording_type": "live",
      "instrument_count": 1,
      "instruments": [24],
      "tuning": "standard",
      "capo": 0,
      "split": "test",
      "notes": "Audience bleed, room reverb"
    }
  ]
}
```

`instruments` should be `[]` for non-GM instruments such as kora or mbira;
instrument-ID metrics then remain unscored instead of asserting a wrong
program.

## Commands

```bash
cd backend

# Create live/home/ood folders and emit the local manifest
python scripts/ingest_eval_recordings.py

# Evaluate the external manifest (qualitative tracks are unscored)
python scripts/eval_amt.py \
  --manifest data/eval_external/manifest.json \
  --tier all \
  --report ../docs/audit/amt/eval-external.json

# Or merge external tracks into a local copy of the main manifest
python scripts/ingest_eval_recordings.py \
  --merge-into ../docs/eval/amt_manifest.json \
  --out data/eval_external/amt_manifest_with_external.json
```

The merged manifest is local-only; the committed `docs/eval/amt_manifest.json`
is not modified.

## W0 coverage checklist

| Stratum | Expected input | Status |
| --- | --- | --- |
| Live | One recording with audience/room noise | Waiting on user audio |
| Home | Re-recorded blues with proper gain staging | Waiting on user audio |
| OOD | Clean kora or mbira recording | Waiting on user audio |
| Jazz harmony | EGSet12 + RWC-P | Covered by committed manifest |
| Studio | GuitarSet / Guitar-TECHS / RWC-P | Covered by committed manifest |

Once the three audio files are dropped into the folders and the manifest is
ingested, the W0 strata gap is closed.
