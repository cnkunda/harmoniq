# Methodology — Harmoniq Technical Debt Audit

**Date:** 2026-11-11  
**Working directory:** `C:\workspace\harmoniq` (Git Bash on Windows; backend inspected through WSL where Python is required)  
**Constraint:** source files were read-only during the audit. Only the four files in `techdebt/` were created.

---

## 1. Reproducible command log

All commands below were actually run. Outputs quoted in the report come from these commands.

### Repository orientation

```bash
git log -1 --format='%H %ad %s' --date=iso
git log --reverse -1 --format='%H %ad %s' --date=iso
git rev-list --count HEAD
git branch --show-current
git status --porcelain
ls -la
git ls-files | wc -l
git ls-files | awk -F/ '{print $1}' | sort | uniq -c | sort -rn
git ls-files | sed -n 's/.*\.\([a-zA-Z0-9]*\)$/\1/p' | sort | uniq -c | sort -rn
```

### Size and languages

```bash
for ext in py ts tsx mjs js css md; do
  n=$(git ls-files "*.$ext" | wc -l)
  l=$(git ls-files "*.$ext" | while read f; do [ -f "$f" ] && wc -l "$f"; done | awk '{s+=$1} END {print s+0}')
  echo "$ext files=$n lines=$l"
done

git ls-files '*.py' '*.ts' '*.tsx' '*.mjs' '*.js' | while read f; do
  [ -f "$f" ] && wc -l "$f"
done | sort -rn | head -30
```

### History, churn, and ownership

```bash
git shortlog -sne --all
git log --format='%ad' --date=short | sort | sed -n '1p;$p'
git log --format='%ad' --date=format:'%Y-%m' | sort | uniq -c | tail -20
git log --format= --name-only | grep -v '^$' | sort | uniq -c | sort -rn | head -35
git log --format='%h %ad %s' --date=short --shortstat -12
```

### Code-quality signals

```bash
# Function length and line numbers (run in WSL; Windows python3 was blocked by the App Execution Alias)
wsl.exe bash -lc 'cd /mnt/c/workspace/harmoniq/backend && python3 - <<"EOF"
import ast, pathlib
rows=[]
for p in pathlib.Path("app").rglob("*.py"):
    try: tree=ast.parse(p.read_text(encoding="utf-8"))
    except Exception: continue
    for n in ast.walk(tree):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
            end=getattr(n,"end_lineno",n.lineno)
            rows.append((end-n.lineno+1,str(p),n.name,n.lineno))
for r in sorted(rows,reverse=True)[:25]: print(r)
EOF'

# Class / function / line counts in selected modules
for f in app/schemas.py app/main.py app/analyze_audio.py app/chord_inference.py \
         app/coach.py app/jobs.py app/musicxml_builder.py app/routers/analyze.py; do
  echo "$f classes=$(rg -c '^class ' $f) funcs=$(rg -c '^(async )?def ' $f) lines=$(wc -l < $f)"
done

# Nesting proxies
rg -c '^ {24,}\S' -g 'app/**'
rg -c '^ {20,}\S' -g 'src/**' -g 'app/**' -g 'components/**'

# Duplication / dead artifacts
sha256sum backend/research/*/chord_inference.py
diff <(sed 's/[[:space:]]//g' src/db/client.native.ts) \
     <(sed 's/[[:space:]]//g' src/db/client.web.ts) | wc -l
rg -n 'bak_phase1' -g '!*.md' .
```

### Markers

```bash
rg -n -g '!node_modules' -g '!package-lock.json' -g '!*.md' -g '!dist' -g '!artifacts' \
  -e 'TODO|FIXME|HACK|XXX|@deprecated'
```

### Dependencies and security

```bash
npm audit --json
npm outdated --json
cat package.json
cat backend/pyproject.toml
cat backend/requirements.txt

# Python audit tool check (WSL)
wsl.exe bash -lc 'cd /mnt/c/workspace/harmoniq/backend && (command -v pip-audit || echo NO_PIP_AUDIT) && python3 --version'
```

`pip-audit` was **not installed**. `npm audit` and `npm outdated` completed successfully. No Python CVE scan was performed; the report says so explicitly.

### Tests and CI

```bash
git ls-files 'backend/tests/*.py' | wc -l
rg -n -g 'backend/tests/**' -e 'pytest.mark.skip|skipif|xfail|pytest.mark.slow|time.sleep'
rg -c '^\s*assert ' -g 'backend/tests/**' | awk -F: '{s+=$2} END{print s+0}'
rg -c '^\s*(async )?def test_' -g 'backend/tests/**' | awk -F: '{s+=$2} END{print s+0}'
git ls-files '*.test.ts' '*.test.tsx' | wc -l
git ls-files 'tests/ui/*.spec.ts' | wc -l
cat .github/workflows/ci.yml
cat .github/workflows/scoring-tests.yml
cat vitest.config.ts
cat playwright.config.ts
cat detox.config.js
```

### Build, config, and secrets

```bash
cat Dockerfile
cat backend/Dockerfile
cat docker-compose.yml
cat .env.example
git ls-files | grep -E '(^|/)\.env$|secrets|credentials'
rg -n -g '!node_modules' -g '!package-lock.json' -g '!*.md' \
  -e 'sk-ant-|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN.*PRIVATE KEY' .
rg -o 'os\.getenv\("[A-Z0-9_]+"' -g 'app/**' | sort -u | wc -l   # run from backend/
git count-objects -vH
git ls-files | while read f; do [ -f "$f" ] && s=$(stat -c %s "$f") && [ "$s" -gt 500000 ] && echo "$s $f"; done | sort -rn
```

### Error handling and reliability

```bash
rg -c 'except:' -g 'app/**'
rg -c 'except Exception' -g 'app/**'
rg -n -U 'except[^\n]*:\n\s+(pass|return None|continue)\s*$' -g 'app/**'
rg -n -g 'app/**' -e 'httpx\.(get|post|Client|AsyncClient)|requests\.(get|post|put)'
rg -n 'shell=True' -g 'app/**'
rg -n 'UploadFile|MAX_UPLOAD_BYTES|batch size' app/routers/analyze.py
```

### Type check (non-mutating)

```bash
npm run lint    # tsc --noEmit; exit 0 at audit time
```

### Not run

- `pip-audit`, `npm ci`, Docker builds, `pytest`, `vitest run`, Playwright, Detox, or Expo startup. These were skipped to keep the audit read-only and because Docker/emulators are not available. Findings that depend on them are labelled **Likely** or listed under "What I could not assess."

---

## 2. Scoring rubric

### Severity (1-5)

| Score | Meaning |
|-------|---------|
| 5 | Continuity or data-integrity risk; could stop delivery or lose user data |
| 4 | Repeated production or release risk; expensive to work around |
| 3 | Meaningful velocity or reliability drag |
| 2 | Localized friction; manageable |
| 1 | Cosmetic or optional |

### Impact spread (1-5)

Breadth of the surface affected if the debt is left alone: `1` = one file/module, `3` = one feature area or platform, `5` = whole app/repo/team.

### Effort

| Size | Engineer-days | Numeric points |
|------|---------------|----------------|
| S | <= 2 | 1 |
| M | 3-7 | 3 |
| L | 8-20 | 8 |
| XL | > 20 | 20 |

### Priority score

```
priorityScore = (severity x impactSpread) / effortNumeric
```

Rounded to one decimal. This deliberately rewards cheap, broad fixes. Severity 5 items (such as the bus factor) can rank below cheap fixes, so the report calls out a severity override where leadership attention is warranted.

### Quadrants

- **Quick win:** high value, `S` effort (or otherwise cheap relative to score).
- **Strategic investment:** high value, `M`/`L`/`XL` effort.
- **Monitor:** real but low urgency; revisit if metrics worsen.
- **Accept:** not worth fixing; excluded from `backlog.json` and recorded in `REPORT.md`.

### Confidence

- **Confirmed:** directly observed in code, config, or command output.
- **Likely:** strongly indicated, but dependent on an unexecuted build/runtime.
- **Speculative:** judgement based on patterns, not a verified defect.

---

## 3. Sampling and limitations

- The audit covered all tracked files for counts, markers, dependency state, and CI/config. Deep manual reading focused on the largest/churn-heavy modules and all deployment/dependency configuration.
- Function-length and nesting metrics are proxies, not true cyclomatic complexity. `radon` was unavailable.
- Churn counts come from `git log --name-only` over the full history on `main`.
- Repository size is the packed Git object size (`git count-objects -vH`), not working-tree size.
- The working tree had uncommitted modifications at audit time; findings describe the committed state plus files present on disk.
- No production telemetry, infrastructure-as-code, or deployment manifests exist in the repo, so runtime SLOs, cloud cost, and incident history could not be assessed.

---

## 4. Post-review corrections (2026-11-11)

Each roadmap spec was re-verified against the code before promotion. The following audit claims were corrected:

- **API leakage:** 2 call sites outside `src/api/` (`app/session/listen.tsx:148`, `src/session/useOrientClip.ts:52`), not 7 files. `src/api/` itself contains 16 expected fetches.
- **Markers:** 13 TODO/@deprecated markers in 9 source files, not 14 in 10. A `bpmXXX` sample string and the tech-debt outputs were excluded.
- **Bus factor:** all 202 commits on `main` are by `cnkunda`; the earlier 205/210 figure came from `git shortlog --all`, which adds 5 "VS Code" entries.
- **Docker:** the `postgresql+asyncpg` URL is dead configuration because `backend/app/db.py` only reads `DATABASE_URL_SYNC`; the editable-install ordering remains a **Likely** build risk.
- **Audio test skips:** the three tests are `skipif`-guarded, so they skip only when ffmpeg is absent, not unconditionally.
- **Backlog scope:** the two accepted decisions (bundled assets, local development credentials) were removed; the docs item was converted from "retain" to an actionable stale-reference fix.
