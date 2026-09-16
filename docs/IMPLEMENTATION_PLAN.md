# Implementation record — Composio AI Product Ops take-home

What was built, which decisions the architecture did not make for us, and what
the result does not establish. The README explains how to run it; this document
explains why it looks the way it does.

Status: complete. Every stage below is implemented, tested, and produces a
committed artifact.

## 1. Locked architecture (source of truth — not redesigned)

```
100-app registry
  -> normalization
  -> Channel A research agent across all 100
  -> evidence extraction
  -> structured classification
  -> deterministic validation
  -> initial dataset
  -> trigger review + Sample A/B selection
  -> sampled independent / citation-audit / human verification
  -> reconciliation
  -> final dataset
  -> deterministic analytics
  -> case-study generation
  -> semantic HTML + JSON/CSV + proof
  -> GitHub Pages
```

Principles held constant throughout: evidence before conclusions; `unknown` is a
valid value; deterministic validation; deterministic analytics; human in the
loop; expensive verification only on samples; no database; no vector database;
no multi-agent swarm; no production infrastructure; exactly one canonical final
dataset.

## 2. Stages and where they live

| Stage | Module | Artifact |
| --- | --- | --- |
| Registry, normalization | `registry/loader.py` | `data/registry/registry_{raw,normalized}.json` |
| Channel A research | `research/runner.py`, `research/providers.py` | `data/interim/classification.json`, `data/raw/research_responses/` |
| Evidence extraction | `research/evidence.py` | `data/interim/evidence.json` |
| Classification | `research/rules.py`, `confidence.py`, `buildability.py` | fields on each research record |
| Validation | `validation/rules.py`, `validation/runner.py` | `data/interim/validation_report.json` |
| Initial dataset | `dataset.py` | `data/interim/initial_dataset.json` |
| Trigger review | `review/triggers.py` | `data/interim/review_queue.json` |
| Sampling | `verification/sampling.py` | `data/verification/sample_{a,b}.json` |
| Channels B/C/D | `verification/channels.py`, `independent.py` | `data/verification/channel_{b,c,d}_{a,b}.json` |
| Reconciliation | `verification/reconcile.py` | `data/verification/reconciliation_{a,b}.json` |
| Accuracy, improvements | `verification/accuracy.py`, `review/improvements.py` | `data/final/accuracy.json`, `data/interim/improvements.json` |
| Final dataset | `dataset.py` | `data/final/final_dataset.{json,csv}` |
| Analytics, patterns | `analytics/compute.py`, `analytics/patterns.py` | `data/final/{analytics,patterns}.json` |
| Case study, publication | `publish/case_study.py`, `publish/exports.py` | `site/index.html`, `site/data/` |

## 3. Decisions the architecture left open

Each of these was a genuine gap in the brief. The choice is recorded so it can
be overridden cheaply.

**Channel A is a research provider, not a vendor.** `ResearchProvider` has three
implementations. The committed run uses `corpus`, which replays a reviewed
source corpus of real documentation URLs; `composio` and `direct` are live
transports that require credentials. The corpus provider exists so the run is
reproducible byte for byte by a reviewer with no keys and no network, and every
evidence item it produces is honestly marked `cited` rather than `fetched`.

**Sample A and B are two disjoint samples, not a sample and a control.** A
measures the first-pass classifier; B measures the improved one on applications
it has never seen. Fifteen apps each, stratified across the ten supplied
categories, seeded from separate namespaces. Sizes are configuration
(`COMPOSIO_OPS_SAMPLE_SIZE_A` / `_B`), because the brief does not fix them.

**Sample A's values are frozen at selection.** Otherwise improving the
classifier would retroactively improve the first-pass score, and the improvement
number would measure nothing.

**Channel C audits citations rather than browsing.** The brief's "browser
verification" is implemented as an evidence audit: for each cited source, does it
exist in the evidence set, belong to that app, and actually declare support for
the claim it is cited for? That is the check a browser pass was there to perform,
and it is one that reruns deterministically.

**Human decisions are a committed file.** `data/corpus/ground_truth.json` holds
32 adjudications, each with a reason and the evidence it rests on, rather than
an external sheet. A decision nobody can re-read is not reviewable.

**Reconciliation precedence is D > C > B > A.** A single-valued field in dispute
is downgraded to `unclear` rather than settled by majority; a multi-valued field
takes the union. Downgrading loses information, but inventing a winner among two
sourced answers loses more.

**Duplicates block the load; they are not merged.** Two rows for one product is
an input defect a human should resolve, and merging silently changes the count.

**`other` plus a rationale, instead of a wider taxonomy.** Every vocabulary
carries an `other` member and requires prose when the status is not a clean
resolution, so an unusual product is not forced into a wrong bucket.

**Python 3.9 is the floor.** The only interpreter on the build machine was the
system 3.9.6, so the code avoids 3.10+ syntax (`X | Y` unions, `StrEnum`,
`tomllib`). CI runs 3.9 and 3.12.

## 4. The improvement phase

Sample A's failures were traced to the rule that produced them, and each rule was
changed once rather than patched per app. The five changes are declared in
`IMPROVEMENTS` in `research/rules.py`, gated behind flags on `ClassifierVersion`,
and reported next to the number of Sample A errors each one addresses:

| Change | Sample A misses |
| --- | --- |
| blocker completeness | 14 |
| credential access plan gating | 6 |
| api breadth coverage anchor | 1 |
| event mechanism distinction | 1 |
| derived restriction provenance | 0 (raises evidence validity, not field accuracy) |

Field-level accuracy: 86.1% on Sample A under v1, 97.6% on Sample B under v2.

## 5. What this does not establish

- Evidence is cited, not fetched, in the committed run.
- 5.3% of verified field values are unresolved, and are reported as such.
- Channel D is one reviewer; inter-rater agreement is not measured.
- Fifteen apps per sample locates systematic rule failures but does not support a
  tight confidence interval on the headline number.
- Self-hosting is friction that no blocker value names, so it is carried as
  `other` and flagged.
- Findings are a snapshot as of the pipeline clock, 2026-09-16.
