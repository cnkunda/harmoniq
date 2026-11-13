You are a senior staff engineer performing a technical debt audit of this repository. Work read-only: do not modify, refactor, or delete any existing source files. The only files you may create are the outputs listed at the end, inside a new folder called `techdebt/`.

## Goal

Produce an evidence-based, prioritized technical debt analysis I can act on and share with leadership.

## Step 1: Orient

- Map the repo: languages, frameworks, build system, entry points, major modules, test setup, CI config, and deploy method.
- Note the approximate size (files, lines of code per language) and the age and activity of the repo (use git log).
- State your assumptions about what the system does. Flag anything you are unsure of.

## Step 2: Gather evidence (run commands where possible, and show what you ran)

Analyze each category below. For every finding, cite specific file paths and line numbers or commit hashes. Do not report anything you cannot point to.

1. **Code quality**: very large files and functions, deep nesting, high cyclomatic complexity, duplicated code, dead or unreachable code, commented-out blocks, magic numbers, inconsistent patterns.
2. **Architecture**: circular dependencies, god classes and modules, leaky layers, tight coupling, missing boundaries, copy-pasted integrations.
3. **Dependencies**: outdated, deprecated, or unmaintained packages, major versions behind, known vulnerabilities (use `npm audit`, `pip-audit`, `cargo audit`, or the equivalent for this stack, if available), unpinned versions, unused dependencies.
4. **Testing**: coverage gaps (especially in critical paths), flaky or skipped tests, slow tests, missing integration tests, tests that assert nothing.
5. **Build, CI/CD, and infra**: slow or fragile builds, manual deploy steps, missing linting or type checking, config drift, hardcoded environment values, secrets in the repo.
6. **Documentation and knowledge**: missing or stale README and setup docs, undocumented modules, bus-factor risk (files touched by only one author, via git blame/shortlog).
7. **Hotspots**: use git history to find files with high churn AND high complexity. These are the highest-interest debt.
8. **Markers**: collect TODO, FIXME, HACK, XXX, and `@deprecated` annotations, and group them by theme.
9. **Security and reliability smells**: missing input validation, weak error handling, swallowed exceptions, missing timeouts and retries, lack of logging or observability.

## Step 3: Score and prioritize

For each distinct debt item, assign:

- **Category** (from the list above)
- **Severity** (1-5): impact if left unaddressed
- **Effort** (S / M / L / XL) with a rough estimate in engineer-days
- **Risk type**: security, reliability, velocity, cost, or onboarding
- **Priority score**: (Severity x spread of impact) / Effort, and show your reasoning briefly
- **Evidence**: file paths, line numbers, commands, or commits
- **Recommended fix**: concrete and incremental, not "rewrite it"

Separate the items into:

- **Quick wins** (high value, low effort)
- **Strategic investments** (high value, high effort)
- **Monitor** (low urgency)
- **Accept** (not worth fixing, with reasoning)

## Step 4: Outputs (write to `techdebt/`)

1. `REPORT.md`: executive summary (5-8 lines, plain language), an overall health rating (A-F) with justification, the top 10 priorities, findings by category, a suggested 30/60/90-day paydown plan, and a "what I could not assess" section.
2. `backlog.json`: an array of all debt items with the fields above, so it can be imported into a tracker or visualized.
3. `backlog.csv`: the same data in CSV.
4. `METHODOLOGY.md`: the commands you ran and the scoring rubric, so the analysis is reproducible.

## Rules

- Be honest about uncertainty. Mark each finding as Confirmed (verified in code), Likely, or Speculative.
- Do not pad the report. Fewer well-evidenced items beat a long generic list.
- Do not make up metrics. If a tool is not installed, say so and fall back to manual inspection or git commands rather than guessing.
- Prefer incremental fixes over rewrites.
- When finished, print a short summary of the top 5 items and the paths of the files you created.
