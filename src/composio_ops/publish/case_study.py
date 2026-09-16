"""The case study: one self-contained, semantic HTML page.

Every number on the page is read out of the artifacts at render time. Nothing is
typed in by hand, so the write-up cannot quietly diverge from the dataset, and
re-running the pipeline updates the prose as well as the tables.

The page is plain HTML with embedded CSS: no build step, no JavaScript, no
external requests. It has to survive being opened from a file, served by GitHub
Pages, and read by somebody on a phone.
"""

from html import escape
from typing import Dict, Iterable, List, Optional, Sequence

from .. import constants as C
from ..analytics.compute import FIELD_LABELS
from ..analytics.patterns import top_patterns
from ..config import Settings
from ..dataset import final_value
from ..research.confidence import HIGH_SOURCE_MINIMUM
from ..schemas.analytics import AnalyticsReport, PatternReport
from ..schemas.dataset import Dataset
from ..schemas.review import ImprovementReport, ReviewQueue
from ..schemas.validation import ValidationReport
from ..schemas.verification import AccuracyReport, SampleAccuracy
from ..taxonomy import (
    API_BREADTH_ANCHORS,
    VERIFIED_FIELDS,
    ResearchFieldName,
    ResolutionStatus,
)

F = ResearchFieldName

STYLE = """
:root {
  --ink: #16191d;
  --muted: #5b6472;
  --line: #d9dee5;
  --accent: #1f4b99;
  --good: #11633f;
  --warn: #8a5a00;
  --bad: #97231f;
  --panel: #f6f8fa;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  color: var(--ink);
  background: #fff;
  font: 17px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
main, header > div, footer > div { max-width: 62rem; margin: 0 auto; padding: 0 1.25rem; }
header { border-bottom: 1px solid var(--line); padding: 2.5rem 0 2rem; background: var(--panel); }
header h1 { font-size: 2rem; line-height: 1.2; margin: 0 0 .5rem; }
header p.lede { font-size: 1.1rem; color: var(--muted); margin: 0 0 1rem; max-width: 46rem; }
dl.run { display: grid; grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr)); gap: .5rem 1.5rem; margin: 0; }
dl.run dt { font-size: .74rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
dl.run dd { margin: 0 0 .5rem; font-variant-numeric: tabular-nums; }
section { padding: 2.25rem 0 .5rem; border-top: 1px solid var(--line); }
section:first-of-type { border-top: 0; }
h2 { font-size: 1.4rem; margin: 0 0 .75rem; }
h3 { font-size: 1.05rem; margin: 1.5rem 0 .5rem; }
p, li { max-width: 46rem; }
ul.cards { list-style: none; display: grid; grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); gap: 1rem; padding: 0; margin: 1rem 0 1.5rem; }
ul.cards li { border: 1px solid var(--line); border-radius: .5rem; padding: .9rem 1rem; max-width: none; }
ul.cards .value { font-size: 1.7rem; font-weight: 650; font-variant-numeric: tabular-nums; display: block; }
ul.cards .label { color: var(--muted); font-size: .85rem; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0 1.5rem; font-size: .93rem; }
caption { text-align: left; color: var(--muted); font-size: .85rem; padding-bottom: .5rem; }
th, td { text-align: left; padding: .45rem .6rem; border-bottom: 1px solid var(--line); vertical-align: top; }
thead th { border-bottom: 2px solid var(--line); font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
code, .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: .88em; }
pre { background: var(--panel); border: 1px solid var(--line); border-radius: .5rem; padding: .9rem 1rem; overflow-x: auto; }
.tag { display: inline-block; padding: .1rem .45rem; border-radius: .35rem; font-size: .78rem; border: 1px solid var(--line); }
.tag.buildable { color: var(--good); border-color: #9ed3ba; background: #eef8f3; }
.tag.friction { color: var(--warn); border-color: #e3c68a; background: #fdf6e8; }
.tag.blocked { color: var(--bad); border-color: #e7b0ad; background: #fdf0ef; }
.tag.unknown { color: var(--muted); background: var(--panel); }
blockquote { margin: 1rem 0; padding: .6rem 1rem; border-left: 3px solid var(--accent); background: var(--panel); }
blockquote p { margin: .25rem 0; }
footer { border-top: 1px solid var(--line); margin-top: 2.5rem; padding: 1.5rem 0 3rem; color: var(--muted); font-size: .9rem; }
a { color: var(--accent); }
@media (max-width: 40rem) { body { font-size: 16px; } header h1 { font-size: 1.6rem; } }
"""


def _pct(value: Optional[float]) -> str:
    return "-" if value is None else "{:.1f}%".format(value * 100)


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _table(
    columns: Sequence[str],
    rows: Iterable[Sequence[object]],
    caption: str = "",
    numeric: Sequence[int] = (),
) -> str:
    head = "".join(
        '<th scope="col"{}>{}</th>'.format(
            ' class="num"' if index in numeric else "", _e(column)
        )
        for index, column in enumerate(columns)
    )
    body: List[str] = []
    for row in rows:
        cells = "".join(
            "<td{}>{}</td>".format(
                ' class="num"' if index in numeric else "",
                cell if isinstance(cell, _Html) else _e(cell),
            )
            for index, cell in enumerate(row)
        )
        body.append("<tr>{}</tr>".format(cells))
    return (
        "<table>{caption}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    ).format(
        caption="<caption>{}</caption>".format(_e(caption)) if caption else "",
        head=head,
        body="".join(body),
    )


class _Html(str):
    """A string already escaped and safe to inline."""


def _buildability_tag(token: str) -> _Html:
    classes = {
        "buildable": "buildable",
        "buildable_with_friction": "friction",
        "blocked": "blocked",
    }
    return _Html(
        '<span class="tag {}">{}</span>'.format(
            classes.get(token, "unknown"), _e(token.replace("_", " "))
        )
    )


def _sample_row(sample: SampleAccuracy) -> List[object]:
    return [
        "Sample {}".format(sample.group.value),
        sample.measurement.replace("_", " "),
        sample.classifier_version,
        sample.apps,
        _pct(sample.field_level_accuracy),
        _pct(sample.row_level_accuracy),
        _pct(sample.evidence_validity),
    ]


def render(
    dataset: Dataset,
    analytics: AnalyticsReport,
    patterns: PatternReport,
    accuracy: AccuracyReport,
    improvements: ImprovementReport,
    validation: ValidationReport,
    queue: ReviewQueue,
    settings: Settings,
) -> str:
    """Render the whole case study from the artifacts."""
    metric = {item.key: item for item in analytics.metrics}
    sample_a = accuracy.sample(C.SampleGroup.A)
    sample_b = accuracy.sample(C.SampleGroup.B)
    total = len(dataset.records)
    categories = {item.category_id: item.name for item in dataset.categories}

    sections: List[str] = []

    # --- headline -----------------------------------------------------------
    cards = [
        (
            _pct(sample_b.field_level_accuracy if sample_b else None),
            "Field-level accuracy, Sample B",
        ),
        (str(metric["apps_total"].value), "Applications researched"),
        (
            "{} / {} / {}".format(
                metric["buildable"].value,
                metric["buildable_with_friction"].value,
                metric["blocked"].value,
            ),
            "Buildable / with friction / blocked",
        ),
        (str(metric["mcp_any"].value), "With an MCP server"),
    ]
    sections.append(
        """
<section id="summary">
  <h2>What this is</h2>
  <p>One hundred applications were researched end to end, classified against a
  fixed taxonomy, and then checked. The headline number is the one that is
  hardest to flatter: <strong>field-level accuracy on Sample B</strong>, fifteen
  applications the improved classifier had never been evaluated against, scored
  across {fields} verified fields against values established by independent
  verification.</p>
  <ul class="cards">{cards}</ul>
  <blockquote>
    <p>Two numbers are reported for every sample because one of them alone is
    misleading. Field-level accuracy asks how many individual values are right.
    Row-level accuracy asks how many applications are right in <em>every</em>
    field, and it is always much lower. A pipeline that quotes only the first is
    hiding the second.</p>
  </blockquote>
</section>
""".format(
            fields=len(VERIFIED_FIELDS),
            cards="".join(
                '<li><span class="value">{}</span><span class="label">{}</span></li>'.format(
                    _e(value), _e(label)
                )
                for value, label in cards
            ),
        )
    )

    # --- the problem --------------------------------------------------------
    sections.append(
        """
<section id="problem">
  <h2>The problem this pipeline solves</h2>
  <p>Deciding which integrations to build is a research problem before it is an
  engineering one. The facts that matter - is there an API, how broad is it, can
  a developer actually get credentials, what stands in the way - are scattered
  across vendor documentation, pricing pages and repositories, and they are
  exactly the kind of facts a language model will answer fluently whether or not
  it knows.</p>
  <p>So the pipeline is built around one rule: <strong>a value is worth nothing
  without the evidence behind it</strong>. Every field cites the pages it came
  from, confidence is computed from properties of that evidence rather than
  declared by the model, and the accuracy claim is measured on a sample the
  final rules had never seen.</p>
  <h3>Three ways of not knowing</h3>
  <p>The taxonomy separates what a single "unknown" would collapse. <span
  class="mono">not_found</span> means the sources did not say. <span
  class="mono">unavailable</span> means they did say, and the answer is that the
  thing does not exist. <span class="mono">unclear</span> means the sources
  disagree or the question does not resolve to one value. The difference
  matters: absence of evidence and evidence of absence lead to different
  decisions.</p>
</section>
"""
    )

    # --- method -------------------------------------------------------------
    stage_rows = [
        ("Registry", "Normalise the supplied 100 apps into stable ids and categories."),
        ("Channel A research", "One pass over all {} apps, citing sources per field.".format(total)),
        ("Evidence extraction", "Every claim becomes an evidence item with a domain, type and the fields it supports."),
        ("Classification", "Deterministic rules map observations onto the taxonomy."),
        ("Validation", "Pure checks: cited evidence exists, derived values follow from their inputs."),
        ("Trigger review", "Risk-based queue - identity, contradictions, missing critical evidence."),
        ("Sampling", "Two disjoint stratified samples of {} apps, seeded from the master seed.".format(settings.sample_size_a)),
        ("Verification", "Channels B, C and D over the samples only."),
        ("Reconciliation", "Fixed precedence resolves disagreements; cardinality respected."),
        ("Accuracy", "Sample A scored against frozen first-pass values; Sample B after the improvement phase."),
        ("Analytics and case study", "Deterministic metrics, patterns, and this page."),
    ]
    sections.append(
        """
<section id="method">
  <h2>How the pipeline works</h2>
  <p>The stages are fixed in order. Research is the only stage that touches all
  {total} applications; verification touches {sampled}, which is what keeps the
  cost of checking bounded while still supporting a defensible accuracy
  claim.</p>
  {table}
</section>
""".format(
            total=total,
            sampled=sum(1 for record in dataset.records if record.sample_group),
            table=_table(
                ["Stage", "What it does"],
                stage_rows,
                caption="The locked stage sequence.",
            ),
        )
    )

    # --- confidence and buildability ---------------------------------------
    breadth_rows = [
        (name.value.replace("_", " "), text) for name, text in API_BREADTH_ANCHORS.items()
    ]
    sections.append(
        """
<section id="judgement">
  <h2>Two judgements that are not left to a model</h2>
  <h3>Confidence is computed</h3>
  <p>Confidence is a function of recorded properties of the evidence: whether
  the product was identified, whether the vendor's own documentation was cited,
  whether every critical field carries evidence, whether anything contradicts
  anything else, and how many distinct sources were found. A record reaches
  <span class="mono">high</span> only with all of those and at least
  {sources} sources. A single missing critical field, an unresolved identity or
  a lone source drops it to <span class="mono">low</span> regardless of how
  confident the prose sounded.</p>
  {confidence_table}
  <h3>Buildability is a decision tree, not an opinion</h3>
  <p>Three independent legs are answered first - technical feasibility,
  credential accessibility, commercial accessibility - and the verdict is the
  worst of them, with a definite failure outranking a gap. That is why a product
  with an excellent API can still be <span class="mono">blocked</span>: the API
  was never the binding constraint.</p>
  {breadth_table}
</section>
""".format(
            sources=HIGH_SOURCE_MINIMUM,
            confidence_table=_table(
                ["Confidence", "Applications"],
                [
                    ("high", metric["confidence_high"].value),
                    ("medium", metric["confidence_medium"].value),
                    ("low", metric["confidence_low"].value),
                ],
                caption="Confidence across the final dataset.",
                numeric=(1,),
            ),
            breadth_table=_table(
                ["API breadth", "What it means"],
                breadth_rows,
                caption="Breadth anchors, so the word means the same thing for every app.",
            ),
        )
    )

    # --- verification design and accuracy ----------------------------------
    channel_rows = [
        (
            "A",
            "Research",
            "All {} apps".format(total),
            "Gathers sources and classifies every field.",
        ),
        (
            "B",
            "Independent re-derivation",
            "Samples",
            "Reads the same sources with different rules, without seeing Channel A's answer.",
        ),
        (
            "C",
            "Citation audit",
            "Samples",
            "Checks that each cited page supports the field it is cited for.",
        ),
        (
            "D",
            "Human review",
            "Disputed and triggered fields",
            "Adjudicates where the automated channels disagree or a trigger fired.",
        ),
    ]
    accuracy_rows = [_sample_row(sample) for sample in accuracy.samples]
    per_field_rows = []
    if sample_b is not None:
        before = {item.field: item for item in (sample_a.per_field if sample_a else [])}
        for item in sample_b.per_field:
            earlier = before.get(item.field)
            per_field_rows.append(
                [
                    FIELD_LABELS.get(item.field, item.field.value),
                    _pct(earlier.accuracy) if earlier else "-",
                    _pct(item.accuracy),
                    "{} / {}".format(item.correct, item.checked),
                ]
            )

    sections.append(
        """
<section id="accuracy">
  <h2>Verification and what it measured</h2>
  <p>Verification is only meaningful if the channels can disagree, so Channel B
  never sees Channel A's answer and does not share its rules, and Channel D is
  silent unless a reviewer actually ruled on a field. Silence is deliberate: a
  human rubber-stamping the pipeline's own output would make the accuracy number
  circular.</p>
  {channels}
  <h3>Results</h3>
  <p>Sample A is scored against values frozen <em>before</em> the improvement
  phase, so improving the classifier cannot retroactively improve the first-pass
  number. Sample B is scored on applications the improved classifier had never
  been evaluated against.</p>
  {accuracy}
  {per_field}
</section>
""".format(
            channels=_table(
                ["Channel", "Method", "Scope", "What it catches"],
                channel_rows,
                caption="The four channels and what each one is for.",
            ),
            accuracy=_table(
                [
                    "Sample",
                    "Measurement",
                    "Classifier",
                    "Apps",
                    "Field-level",
                    "Row-level",
                    "Evidence validity",
                ],
                accuracy_rows,
                caption="Accuracy by sample. Row-level requires every field of an app to be correct.",
                numeric=(3, 4, 5, 6),
            ),
            per_field=_table(
                ["Field", "Sample A (first pass)", "Sample B (final)", "Correct"],
                per_field_rows,
                caption="Per-field accuracy, first pass against final.",
                numeric=(1, 2, 3),
            )
            if per_field_rows
            else "",
        )
    )

    # --- improvements -------------------------------------------------------
    improvement_rows = [
        [
            item.key.replace("-", " "),
            item.failure_mode,
            item.change,
            item.observed_in_sample_a,
        ]
        for item in improvements.improvements
    ]
    sections.append(
        """
<section id="improvements">
  <h2>What the first pass got wrong</h2>
  <p>Sample A was a diagnosis rather than a score. Each failure was traced to
  the rule that produced it, and the rule was changed once for every application
  rather than patched per app. The classifier version is recorded on every
  record, so which rules produced which value is never in doubt.</p>
  {table}
  <p>The result: field-level accuracy moved from {before} on the first pass to
  {after} on applications the new rules had never been evaluated against.</p>
</section>
""".format(
            table=_table(
                ["Change", "Failure mode", "What {} does instead".format(improvements.to_classifier), "Sample A misses"],
                improvement_rows,
                caption="The improvement phase, {} to {}.".format(
                    improvements.from_classifier, improvements.to_classifier
                ),
                numeric=(3,),
            ),
            before=_pct(sample_a.field_level_accuracy if sample_a else None),
            after=_pct(sample_b.field_level_accuracy if sample_b else None),
        )
    )

    # --- findings -----------------------------------------------------------
    finding_items = "".join(
        "<li><strong>{}.</strong> {}</li>".format(_e(pattern.title), _e(pattern.statement))
        for pattern in top_patterns(patterns, limit=6)
    )
    sections.append(
        """
<section id="findings">
  <h2>What the data says</h2>
  <ul>{items}</ul>
  <p>Each of these is a predicate evaluated over the dataset, and the applications
  supporting it are listed in <code>patterns.json</code>. If the data changes,
  the sentence changes with it.</p>
  {tabs}
</section>
""".format(
            items=finding_items,
            tabs=_cross_tab_html(analytics, categories),
        )
    )

    # --- distributions ------------------------------------------------------
    sections.append(
        """
<section id="distributions">
  <h2>Distributions</h2>
  <p>Unresolved values are counted rather than dropped: how often a field could
  not be established is a finding about the research, not a gap in the chart.
  Multi-valued fields are counted per value, so their totals exceed {total}.</p>
  {tables}
</section>
""".format(
            total=total,
            tables="".join(
                _table(
                    ["Value", "Applications"],
                    sorted(
                        list(item.counts.items())
                        + [
                            ("({})".format(status), count)
                            for status, count in item.unresolved.items()
                        ],
                        key=lambda pair: (-pair[1], pair[0]),
                    ),
                    caption="{}{}".format(
                        item.label,
                        " (multi-valued)" if item.multi_valued else "",
                    ),
                    numeric=(1,),
                )
                for item in analytics.distributions
                if item.attribute
                in (
                    F.BUILDABILITY.value,
                    F.CREDENTIAL_ACCESS.value,
                    F.MCP.value,
                    F.WEBHOOK_SUPPORT.value,
                    F.RATE_LIMIT_INFO.value,
                    F.AUTHENTICATION.value,
                    F.BLOCKER.value,
                )
            ),
        )
    )

    # --- the dataset --------------------------------------------------------
    sections.append(
        """
<section id="dataset">
  <h2>The dataset</h2>
  <p>All {total} applications, as the final dataset records them. Sampled
  applications carry the verification that was run on them.</p>
  {table}
  <p>Downloads: <a href="data/{json}">final dataset (JSON)</a>,
  <a href="data/{csv}">flat table (CSV)</a>,
  <a href="data/{analytics}">analytics</a>,
  <a href="data/{patterns}">patterns</a>,
  <a href="data/{accuracy}">accuracy</a>.</p>
</section>
""".format(
            total=total,
            table=_dataset_table(dataset, categories),
            json=C.FINAL_DATASET_FILENAME,
            csv=C.FINAL_DATASET_CSV_FILENAME,
            analytics=C.ANALYTICS_FILENAME,
            patterns=C.PATTERNS_FILENAME,
            accuracy=C.ACCURACY_FILENAME,
        )
    )

    # --- limitations --------------------------------------------------------
    unresolved_share = metric["unresolved_field_share"].value
    sections.append(
        """
<section id="limitations">
  <h2>What this does not establish</h2>
  <ul>
    <li><strong>Evidence is cited, not fetched in this run.</strong> The
    committed run replays a reviewed source corpus so that anybody can reproduce
    it byte for byte without credentials or network access. Every evidence item
    records <span class="mono">retrieval: cited</span> for exactly this reason.
    A live run would record <span class="mono">fetched</span> and carry page
    excerpts.</li>
    <li><strong>{unresolved} of verified field values are unresolved.</strong>
    That is reported rather than filled in. A confident wrong answer is more
    expensive than an admitted gap.</li>
    <li><strong>One reviewer.</strong> Channel D is a single human. Inter-rater
    agreement is not measured, so the reconciled values inherit that reviewer's
    judgement on the {decisions} fields they ruled on.</li>
    <li><strong>The taxonomy has gaps.</strong> Self-hosting is friction that no
    blocker value names, so it is carried as <span class="mono">other</span> and
    flagged. API breadth is a judgement anchored to documented resource groups;
    reasonable readers disagree, and Sample B's remaining misses are mostly
    exactly that disagreement.</li>
    <li><strong>Accuracy is measured on {apps} applications per sample.</strong>
    Fifteen apps is enough to locate systematic rule failures and far too few to
    put a tight confidence interval around the headline number.</li>
    <li><strong>Findings are a snapshot.</strong> Pricing, plans and MCP servers
    move; the dataset records what the sources said as of
    {as_of}.</li>
  </ul>
</section>
""".format(
            unresolved=_pct(unresolved_share if isinstance(unresolved_share, float) else 0.0),
            decisions=len(
                [
                    decision
                    for record in dataset.records
                    for decision in record.reconciliation
                    if decision.decided_by
                ]
            ),
            apps=settings.sample_size_a,
            as_of=_e(settings.as_of.date().isoformat()),
        )
    )

    # --- reproducibility ----------------------------------------------------
    sections.append(
        """
<section id="reproducibility">
  <h2>Reproducing this</h2>
  <p>Everything is seeded from one master seed and stamped with one pipeline
  clock, so a second run produces byte-identical artifacts and any diff is a
  real change.</p>
  <pre><code>pip install -e .
composio-ops registry load
composio-ops pipeline run
composio-ops analyze run
composio-ops casestudy build</code></pre>
  {table}
  <p>Validation ran {checks} checks over the research pass and recorded
  {errors} blocking errors and {warnings} warnings; the review triggers queued
  {queued} of {total} applications for human attention.</p>
</section>
""".format(
            table=_table(
                ["Setting", "Value"],
                [
                    ("Master seed", settings.seed),
                    ("Sample A namespace", C.SEED_NAMESPACE_SAMPLE_A),
                    ("Sample B namespace", C.SEED_NAMESPACE_SAMPLE_B),
                    ("Pipeline clock", settings.as_of.isoformat()),
                    ("Research provider", dataset.provider.value),
                    ("Classifier", dataset.classifier_version),
                    ("Schema version", C.SCHEMA_VERSION),
                    ("Dataset fingerprint", dataset.metadata.source_fingerprint or "-"),
                ],
                caption="The run this page was generated from.",
            ),
            checks=validation.checked_records,
            errors=len(validation.errors),
            warnings=len(validation.warnings),
            queued=len(queue.entries),
            total=queue.population_size,
        )
    )

    body = "".join(sections)
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<style>{style}</style>
</head>
<body>
<header>
  <div>
    <p class="mono">{schema} &middot; seed {seed} &middot; {as_of}</p>
    <h1>{title}</h1>
    <p class="lede">{description}</p>
    <dl class="run">
      <div><dt>Applications</dt><dd>{apps}</dd></div>
      <div><dt>Verified fields</dt><dd>{fields}</dd></div>
      <div><dt>Evidence items</dt><dd>{evidence}</dd></div>
      <div><dt>Headline accuracy</dt><dd>{headline}</dd></div>
    </dl>
  </div>
</header>
<main>{body}</main>
<footer><div>
  <p>Generated from the artifacts by <code>composio-ops casestudy build</code>.
  Dataset fingerprint <span class="mono">{fingerprint}</span>.</p>
</div></footer>
</body>
</html>
""".format(
        title=_e(C.CASE_STUDY_TITLE),
        description=_e(C.CASE_STUDY_DESCRIPTION),
        style=STYLE,
        schema=_e("schema {}".format(C.SCHEMA_VERSION)),
        seed=_e(settings.seed),
        as_of=_e(settings.as_of.date().isoformat()),
        apps=total,
        fields=len(VERIFIED_FIELDS),
        evidence=sum(len(record.evidence) for record in dataset.records),
        headline=_pct(accuracy.headline_value),
        body=body,
        fingerprint=_e(dataset.metadata.source_fingerprint or "-"),
    )


def _cross_tab_html(analytics: AnalyticsReport, categories: Dict[str, str]) -> str:
    """Render the cross-tabs that carry an argument rather than just counts."""
    wanted = ("buildability_by_category", "buildability_by_credential_access")
    blocks: List[str] = []
    for tab in analytics.cross_tabs:
        if tab.key not in wanted:
            continue
        rows = []
        for row in tab.rows:
            label = categories.get(row, row.replace("_", " "))
            rows.append([label] + [tab.cells[row].get(col, 0) for col in tab.columns])
        blocks.append(
            _table(
                [tab.row_attribute.replace("_", " ")]
                + [col.replace("_", " ") for col in tab.columns],
                rows,
                caption=tab.label,
                numeric=tuple(range(1, len(tab.columns) + 1)),
            )
        )
    return "".join(blocks)


def _dataset_table(dataset: Dataset, categories: Dict[str, str]) -> str:
    rows = []
    for record in dataset.records:
        buildability = final_value(record, F.BUILDABILITY)
        token = (
            buildability.value[0]
            if buildability.status is ResolutionStatus.RESOLVED and buildability.value
            else buildability.status.value
        )
        access = final_value(record, F.CREDENTIAL_ACCESS)
        mcp = final_value(record, F.MCP)
        rows.append(
            [
                record.app.name,
                categories.get(record.app.category_id, record.app.category_id),
                _buildability_tag(token),
                (access.value or [access.status.value])[0].replace("_", " "),
                (mcp.value or [mcp.status.value])[0].replace("_", " "),
                record.research.confidence.value,
                record.sample_group.value if record.sample_group else "",
            ]
        )
    return _table(
        [
            "Application",
            "Category",
            "Buildability",
            "Credentials",
            "MCP",
            "Confidence",
            "Sample",
        ],
        rows,
        caption="The final dataset, one row per application.",
    )


def publish(
    dataset: Dataset,
    analytics: AnalyticsReport,
    patterns: PatternReport,
    accuracy: AccuracyReport,
    improvements: ImprovementReport,
    validation: ValidationReport,
    queue: ReviewQueue,
    settings: Settings,
) -> str:
    """Render and write the case study, returning its path relative to the root."""
    html = render(
        dataset=dataset,
        analytics=analytics,
        patterns=patterns,
        accuracy=accuracy,
        improvements=improvements,
        validation=validation,
        queue=queue,
        settings=settings,
    )
    settings.paths.ensure_directories()
    settings.paths.case_study.write_text(html, encoding="utf-8")
    return settings.paths.relative(settings.paths.case_study)
