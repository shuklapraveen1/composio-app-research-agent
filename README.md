# Composio AI Product Ops take-home

An evidence-first research pipeline over a 100-application registry. It decides,
for every app, whether an integration is buildable and what stands in the way —
and it makes every one of those decisions traceable to a cited source.

Three properties hold throughout:

- **Every value cites evidence.** A field with no supporting source is recorded
  as unresolved, never guessed.
- **`unknown` is an answer.** "Not found", "unavailable", "unclear" and "not
  applicable" are distinct outcomes, and the dataset keeps them apart.
- **Re-runs are byte-identical.** One seed and a fixed pipeline clock drive
  everything, so the same input always produces the same 147 artifact files.

The published case study is `site/index.html`; the dataset behind it is
`data/final/final_dataset.json` and `data/final/final_dataset.csv`.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/composio-ops registry load --source apps.json   # tracked; only needed once
.venv/bin/composio-ops pipeline run
```

`pipeline run` runs every stage and rewrites the dataset, the analytics,
and the case study. It needs no API keys and makes no network calls: research
reads the reviewed source corpus committed under `data/corpus/`.

## The pipeline

```
registry -> normalization -> Channel A research (all 100 apps) -> evidence ->
classification -> deterministic validation -> initial dataset -> review queue ->
Sample A/B selection -> Channels B/C/D (samples only) -> reconciliation ->
accuracy -> classifier improvements -> final dataset -> analytics -> case study
```

Channel A researches all 100 apps once. The expensive channels run only over the
two seeded samples, 30 apps in total, plus any app a review trigger flags:

| Channel | What it does | Scope |
| --- | --- | --- |
| A | Primary research and classification | all 100 apps |
| B | Independent re-reading with different tie-breaks | sampled apps |
| C | Citation audit: does each cited source actually support the claim? | sampled apps |
| D | Human adjudication of disputed fields | disputed fields only |

Where channels disagree, reconciliation applies a fixed precedence — D beats C
beats B beats A. A single-valued field in dispute is downgraded to `unclear`
rather than resolved by majority; a multi-valued field takes the union.

### Two classifier passes

Sample A is measured against the classifier as it stood on the first pass (v1).
Its failures drive five specific, documented changes, and Sample B — drawn
disjoint from A — measures v2. The improvements are declared in
`research/rules.py` and each one is reported alongside the number of Sample A
errors it addresses, so the improvement story stays tied to observed data:

1. **Plan-gated credentials** — read the API plan, not just the account tier.
2. **Coverage-anchored breadth** — cap breadth by documented coverage.
3. **Event mechanism distinction** — keep polling and streaming out of webhooks.
4. **Blocker completeness** — record "none" explicitly instead of leaving a gap.
5. **Derived restriction provenance** — say in the rationale when a restriction
   was derived rather than stated.

Current run: Sample A scores 86.1% field-level accuracy under v1, Sample B 97.6%
under v2. The headline metric is Sample B's field-level accuracy across the 11
verified fields.

## Commands

```bash
composio-ops --help                            # every stage
composio-ops init                              # create the artifact directories
composio-ops status                            # config, derived seeds, artifact readiness
composio-ops pipeline run                      # the whole thing, in order

composio-ops registry load --source apps.json  # ingest the supplied 100-app list
composio-ops registry validate                 # counts, categories, duplicates
composio-ops registry show --by-category

composio-ops research run                      # Channel A over the registry
composio-ops research validate                 # deterministic validation report
composio-ops research dataset                  # initial dataset
composio-ops research review-queue             # risk-based review queue

composio-ops verify sample                     # draw and freeze Samples A and B
composio-ops verify run --sample A             # channels B/C/D, reconcile, score

composio-ops analyze run                       # analytics.json and patterns.json
composio-ops casestudy build                   # case study page and exports
```

Global options come before the subcommand: `composio-ops --seed 7 --log-level
WARNING pipeline run`. Each stage is also runnable on its own, for example
`python -m composio_ops.cli.research run`.

A stage run out of order exits with code 4 and names the artifact it needs,
rather than producing a partial result.

## Determinism

One master seed (`COMPOSIO_OPS_SEED`) drives everything. Each stage derives its
own seed from `(master_seed, stage_namespace)`, so stages never share an RNG
stream and adding a stage cannot reshuffle an earlier stage's sample. Artifacts
carry a fixed pipeline clock (`COMPOSIO_OPS_AS_OF`) instead of the wall clock and
are written with sorted keys and fixed formatting.

The consequence is checkable, and CI checks it: running the pipeline twice must
leave `git diff` empty.

```bash
composio-ops pipeline run && composio-ops pipeline run && git diff --exit-code
```

## Layout

```
src/composio_ops/
  config.py, paths.py, determinism.py, io_utils.py, errors.py, logging.py
  taxonomy.py, constants.py     the locked field taxonomy and stage vocabulary
  schemas/                      frozen, strict Pydantic records for every artifact
  research/                     corpus provider, classifier v1/v2, confidence, buildability
  validation/                   deterministic checks over a research pass
  review/                       risk triggers and the improvement report
  verification/                 sampling, channels B/C/D, reconciliation, accuracy
  analytics/                    distributions, cross-tabs, metrics, patterns
  publish/                      case study rendering and exports
  cli/                          one module per stage

data/corpus/       reviewed source corpus and human ground truth   (tracked)
data/registry/     the supplied 100-app list and its normalized form
data/raw/          verbatim research responses kept as provenance  (generated)
data/interim/      evidence, classification, validation, queue     (generated)
data/verification/ samples, channel outputs, reconciliation
data/final/        final dataset, analytics, patterns, accuracy
site/              the published case study and its data exports
apps.json          the supplied application registry
```

`data/raw/` and `data/interim/` are regenerated on every run and are not tracked.
The corpus and the human decisions are inputs, so they are.

## The corpus

Channel A reads `data/corpus/apps/*.json`: one file per category, one entry per
app, every entry carrying at least three real documentation URLs with the claim
each one supports. Evidence drawn this way is marked `cited` rather than
`fetched`, which keeps the run reproducible offline and keeps the artifact honest
about what was actually read.

`data/corpus/ground_truth.json` holds the human (Channel D) adjudications, each
with a reason and the evidence it rests on. `tests/test_corpus_integrity.py`
enforces the corpus rules: HTTPS sources, unique ids, no observation without a
source backing it, and no ground-truth override pointing at evidence that does
not exist.

### Adding an app

Add it to `apps.json` and to the corpus file for its category, then re-run the
pipeline. Validation will tell you if the entry cites nothing for a critical
field; the integrity tests will tell you if it cites something that is not there.

### Adding a classifier improvement

Add an entry to `IMPROVEMENTS` in `research/rules.py`, gate the behaviour behind
a flag on `ClassifierVersion`, and implement it in the v2 branch of the relevant
rule. The improvement report picks it up and pairs it with its observed Sample A
failure count automatically.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | success |
| 1 | unexpected error |
| 2 | configuration error |
| 4 | required upstream artifact missing |
| 5 | deterministic validation failed |
| 6 | other pipeline error |

## Tests

```bash
.venv/bin/python -m pytest
```

224 tests covering schema invariants, classifier rules and the v1/v2 divergences,
validation, sampling and the verification channels, reconciliation precedence,
analytics and patterns, corpus integrity, and a full end-to-end run over the real
100-app registry that asserts the artifacts are byte-stable.

## Publishing

`.github/workflows/pages.yml` rebuilds the case study from the committed corpus
on every push to `main` and deploys `site/` to GitHub Pages, so the published
page can never drift from the dataset behind it. `.github/workflows/ci.yml` runs
the test suite on Python 3.9 and 3.12 and fails if a second pipeline run changes
a tracked file.
