# SoundFont provenance

## Current soundfont (commit 47)

- File: `guitar.sf2`
- Source repository: [ad-si/GeneralUser](https://github.com/ad-si/GeneralUser)
- Direct file URL: [GeneralUser.sf2](https://raw.githubusercontent.com/ad-si/GeneralUser/master/GeneralUser.sf2)
- Upstream license text: [LICENSE.txt](https://raw.githubusercontent.com/ad-si/GeneralUser/master/LICENSE.txt)
- Local copy fetched on: 2026-04-10

## Fluid R3 Mono GM (commit 60)

- File: `fluid-r3-mono-gm.sf3`
- Source repository: [musescore/MuseScore](https://github.com/musescore/MuseScore) — path `share/sound/FluidR3Mono_GM.sf3`
- Upstream license: `share/sound/FluidR3Mono_License.md` in the same repository (MIT-style terms for the Fluid R3 Mono bank)
- Local copy fetched on: 2026-04-19

## Notes

- Harmoniq uses **GeneralUser** (`guitar.sf2`) as the default AlphaTab SoundFont for guitar-forward lessons and **Fluid R3 Mono GM** (`fluid-r3-mono-gm.sf3`) as the fuller GM bank for rock / ensemble-oriented styles (see `src/audio/soundfontProfiles.ts`).
- The native harness loads the same pinned CDN URLs as the app for each profile and reports `soundFontLoad` status (including optional `profileId`, `loaded`, `total`) for UI feedback.
- If a future replacement is used, update this file with source URL, license, and fetch date.
