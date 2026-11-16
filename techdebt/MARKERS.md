# In-code marker registry

Markers in source must reference a tracking ID from this table. The ID is
validated by `scripts/check-markers.mjs` in CI (`npm run check:markers`).

**Policy:** every `TODO`, `FIXME`, `HACK`, `XXX`, or `@deprecated` in `app/`,
`src/`, `components/`, `types/`, `backend/app/`, or `backend/scripts/` must carry
an `M-xx` ID on the marker line. Remove the marker when the work is done or no
longer relevant; do not leave orphaned registry rows. Tracker `TD-*` IDs refer
to [`backlog.json`](./backlog.json).

| ID | Location | Kind | Owner | Tracker | Target / removal condition | Status |
| --- | --- | --- | --- | --- | --- | --- |
| M-03 | `backend/app/coach.py:1441` | `TODO` | cnkunda | TD-13 | Orient tip is template copy and is labeled in the UI; replace with Claude output when available | labeled |
| M-04 | `src/types/index.ts:376-380` | `@deprecated` | cnkunda | TD-10 | Remove GP5 contract fields after all gates in [docs/MIGRATIONS.md](../docs/MIGRATIONS.md#gp5-contract-deprecation-non-db) pass | open |
| M-05 | `src/music/fingerSuggestion.ts:40` | `TODO` | cnkunda | TD-10 | Position-aware fingering using surrounding tab beats and capo (post-1.1) | open |
| M-06 | `backend/scripts/analyze_label_noise.py:139,161` | `TODO` | cnkunda | TD-10 | Load real ground-truth annotations when JAAH/Smithsonian audio is available | open |
