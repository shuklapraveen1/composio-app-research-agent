"""The case study: a small research application rendered from the artifacts.

Every number on the page is read out of the artifacts at render time. Nothing is
typed in by hand, so the write-up cannot quietly diverge from the dataset, and
re-running the pipeline updates the prose as well as the tables.

The page ships as four files - markup, stylesheet, script, and the dataset
projection the script explores - with no build step and no external requests.
The markup alone is a complete report: the script turns it into something you
can filter, sort and drill into, but nothing is hidden behind it.
"""

from html import escape
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .. import constants as C
from ..analytics.compute import FIELD_LABELS
from ..config import Settings
from ..dataset import final_value
from ..research.confidence import HIGH_SOURCE_MINIMUM
from ..schemas.analytics import AnalyticsReport, Distribution, PatternReport
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
from . import assets, viewmodel

F = ResearchFieldName

#: Tone per taxonomy token, mirroring the palette the stylesheet defines.
TONES: Dict[str, str] = {
    "buildable": "good",
    "buildable_with_friction": "warn",
    "blocked": "bad",
    "official": "good",
    "third_party": "accent",
    "high": "good",
    "medium": "warn",
    "low": "bad",
    "self_serve_free": "good",
    "self_serve_trial": "good",
}

#: Navigation, in page order.
NAV = (
    ("overview", "Overview"),
    ("findings", "Findings"),
    ("verification", "Verification"),
    ("dataset", "Dataset"),
    ("methodology", "Methodology"),
)

#: The commands that produce everything on this page.
COMMANDS = (
    ("pip install -e .", "Install the package and its dependencies."),
    ("composio-ops registry load --source apps.json", "Ingest the supplied 100-app list."),
    ("composio-ops pipeline run", "Research, verify, reconcile, measure, publish."),
    ("composio-ops analyze run", "Recompute analytics and patterns alone."),
    ("composio-ops casestudy build", "Re-render this page from the artifacts."),
)


class _Html(str):
    """A string already escaped and safe to inline."""


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _pct(value: Optional[float]) -> str:
    return "-" if value is None else "{:.1f}%".format(value * 100)


def _humanise(token: str) -> str:
    return token.replace("_", " ")


def _tone(token: str) -> str:
    return TONES.get(token, "")


def _tag(token: str, tone: Optional[str] = None) -> _Html:
    classes = " ".join(filter(None, ("tag", _tone(token) if tone is None else tone)))
    return _Html('<span class="{}">{}</span>'.format(classes, _e(_humanise(token))))


def _table(
    columns: Sequence[str],
    rows: Iterable[Sequence[object]],
    caption: str = "",
    numeric: Sequence[int] = (),
) -> _Html:
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
    return _Html(
        '<div class="table-wrap"><table>{caption}<thead><tr>{head}</tr></thead>'
        "<tbody>{body}</tbody></table></div>".format(
            caption="<caption>{}</caption>".format(_e(caption)) if caption else "",
            head=head,
            body="".join(body),
        )
    )


def _panel(title: str, body: str, meta: str = "") -> _Html:
    return _Html(
        '<div class="panel"><div class="panel-head"><h3>{title}</h3>'
        '<span class="meta">{meta}</span></div>'
        '<div class="panel-body">{body}</div></div>'.format(
            title=_e(title), meta=_e(meta), body=body
        )
    )


def _bar_rows(
    distribution: Distribution, filter_key: Optional[str] = None
) -> _Html:
    """One distribution as a bar list, unresolved buckets included.

    When a filter key is given the rows become buttons that drive the explorer,
    so a bar and the applications behind it are one click apart.
    """
    entries: List[Tuple[str, int, bool]] = [
        (token, count, False) for token, count in distribution.counts.items()
    ]
    entries += [
        (status, count, True) for status, count in distribution.unresolved.items()
    ]
    entries.sort(key=lambda item: (-item[1], item[0]))
    largest = max([count for _, count, _ in entries] or [1])

    rows: List[str] = []
    for token, count, unresolved in entries:
        share = (count / largest) if largest else 0
        fill = "neutral" if unresolved else (_tone(token) or "accent")
        inner = (
            '<span class="name">{label}</span>'
            '<span class="track"><span class="fill {fill}" style="width:{width:.1f}%"></span></span>'
            '<span class="count">{count}<em> / {total}</em></span>'
        ).format(
            label=_e(_humanise(token)),
            fill=fill,
            width=share * 100,
            count=count,
            total=distribution.total,
        )
        title = "{} - {} of {} applications".format(
            _humanise(token), count, distribution.total
        )
        if filter_key:
            rows.append(
                '<button type="button" class="bar-row" data-filter-key="{key}" '
                'data-filter-value="{value}" aria-pressed="false" title="{title}">'
                "{inner}</button>".format(
                    key=_e(filter_key), value=_e(token), title=_e(title), inner=inner
                )
            )
        else:
            rows.append(
                '<div class="bar-row" title="{title}">{inner}</div>'.format(
                    title=_e(title), inner=inner
                )
            )
    return _Html('<div class="bars">{}</div>'.format("".join(rows)))


def _kpi(value: str, label: str, context: str) -> str:
    return (
        '<div class="kpi"><div class="value">{value}</div>'
        '<div class="label">{label}</div>'
        '<div class="context">{context}</div></div>'
    ).format(value=_e(value), label=_e(label), context=_e(context))


def _row_dimension_label(attribute: str) -> str:
    """The header for a cross-tab's row dimension, in the project's own words."""
    if attribute == "category_id":
        return "Category"
    for field in F:
        if field.value == attribute:
            return viewmodel.field_label(field)
    return _humanise(attribute)


def _distribution_of(analytics: AnalyticsReport, field: F) -> Optional[Distribution]:
    for item in analytics.distributions:
        if item.attribute == field.value:
            return item
    return None


def _stage_rows(
    dataset: Dataset, queue: ReviewQueue, settings: Settings, total: int
) -> List[Tuple[str, str, str, str, str]]:
    """The locked stage sequence: name, scope, what it does, why it exists."""
    sampled = sum(1 for record in dataset.records if record.sample_group)
    return [
        (
            "registry",
            "Registry",
            "{} applications".format(total),
            "Normalise the supplied list into stable ids and the ten supplied categories.",
            "Ids have to be stable and order-independent, or every later stage "
            "would reshuffle when the input list is re-sorted.",
        ),
        (
            "research",
            "Research",
            "{} applications".format(total),
            "Channel A reads the sources for every application and records what they say.",
            "This is the only stage that touches all one hundred, which is what "
            "keeps the cost of the expensive checks bounded.",
        ),
        (
            "evidence",
            "Evidence extraction",
            "{} evidence items".format(
                sum(len(record.evidence) for record in dataset.records)
            ),
            "Each claim becomes an evidence item with a URL, a source type and the fields it supports.",
            "A value that cannot name the page it came from is an opinion, and "
            "the citation audit later needs something to audit.",
        ),
        (
            "classification",
            "Classification",
            "{} fields per application".format(len(viewmodel.DETAIL_FIELDS)),
            "Deterministic rules map the observations onto the fixed taxonomy.",
            "Rules can be versioned, diffed and re-run; a model's judgement "
            "cannot, so the improvement phase would have nothing to change.",
        ),
        (
            "validation",
            "Validation",
            "{} records checked".format(total),
            "Pure checks: cited evidence exists, derived values follow from their inputs.",
            "Catches contradictions mechanically before a human spends attention on them.",
        ),
        (
            "trigger-review",
            "Trigger review",
            "{} of {} queued".format(len(queue.entries), queue.population_size),
            "Risk rules queue records with unresolved identity, contradictions or missing critical evidence.",
            "Review capacity is finite, so it goes where the risk is rather than "
            "spreading evenly over a hundred applications.",
        ),
        (
            "sampling",
            "Sampling",
            "2 x {} applications".format(settings.sample_size_a),
            "Two disjoint stratified samples, seeded from the master seed and frozen at selection.",
            "Freezing Sample A before the improvement phase is what stops a "
            "better classifier from retroactively improving its own first-pass score.",
        ),
        (
            "verification",
            "Verification",
            "{} applications".format(sampled),
            "Channels B, C and D re-derive, audit citations and adjudicate disputes.",
            "Verification only means something if the channels are able to "
            "disagree, so they do not share rules or see each other's answers.",
        ),
        (
            "reconciliation",
            "Reconciliation",
            "{} decisions".format(
                sum(len(record.reconciliation) for record in dataset.records)
            ),
            "Fixed precedence D > C > B > A; single-valued disputes downgrade to unclear, multi-valued merge.",
            "Settling a disagreement by majority would invent a winner; "
            "recording it as unclear keeps the disagreement visible.",
        ),
        (
            "accuracy",
            "Accuracy",
            "{} verified fields".format(len(VERIFIED_FIELDS)),
            "Score each sample field by field against the values verification established.",
            "Field-level and row-level accuracy are both reported because either "
            "one alone flatters the pipeline.",
        ),
        (
            "analytics",
            "Analytics",
            "{} applications".format(total),
            "Deterministic metrics, distributions, cross-tabs and patterns, computed from the final dataset only.",
            "One canonical source means the page, the CSV and the JSON can never "
            "quote different numbers.",
        ),
    ]


def _header(meta: Dict[str, object]) -> str:
    tabs = "".join(
        '<a href="#{id}">{label}</a>'.format(id=_e(key), label=_e(label))
        for key, label in NAV
    )
    return """
<header class="app-header">
  <div class="wrap">
    <div class="brand">
      <span class="brand-mark" aria-hidden="true">CR</span>
      <span class="brand-text">
        <span class="brand-name">Composio Research</span>
        <span class="brand-sub">Integration Intelligence</span>
      </span>
    </div>
    <nav class="tabs" aria-label="Sections">{tabs}</nav>
    <div class="header-meta">
      <span class="hide-sm">Dataset: <b>{apps} apps</b></span>
      <span>Updated: <b>{as_of}</b></span>
    </div>
  </div>
</header>
""".format(tabs=tabs, apps=_e(meta["apps"]), as_of=_e(meta["as_of"]))


def _overview(
    dataset: Dataset,
    accuracy: AccuracyReport,
    settings: Settings,
    metric: Dict[str, object],
    total: int,
) -> str:
    sample_b = accuracy.sample(C.SampleGroup.B)
    evidence_items = sum(len(record.evidence) for record in dataset.records)
    kpis = "".join(
        [
            _kpi(
                str(metric["apps_total"]),
                "Applications",
                "{} supplied categories".format(metric["categories_total"]),
            ),
            _kpi(
                _pct(sample_b.field_level_accuracy if sample_b else None),
                "Field-level accuracy",
                "Sample B \u00b7 {} applications \u00b7 {} verified fields".format(
                    sample_b.apps if sample_b else 0, len(VERIFIED_FIELDS)
                ),
            ),
            _kpi(
                str(evidence_items),
                "Evidence items",
                "Cited across {} applications".format(total),
            ),
            _kpi(
                str(metric["mcp_any"]),
                "Applications with MCP",
                "{} vendor-published, {} third-party".format(
                    metric["mcp_official"],
                    int(metric["mcp_any"]) - int(metric["mcp_official"]),
                ),
            ),
        ]
    )
    facts = [
        ("Schema", C.SCHEMA_VERSION),
        ("Master seed", settings.seed),
        ("Pipeline clock", settings.as_of.date().isoformat()),
        ("Classifier", dataset.classifier_version),
        ("Provider", dataset.provider.value),
        ("Fingerprint", dataset.metadata.source_fingerprint or "-"),
    ]
    return """
<section id="overview" class="hero">
  <div class="wrap">
    <div class="hero-grid">
      <div>
        <span class="eyebrow">Research run \u00b7 {as_of}</span>
        <h1>Integration buildability intelligence</h1>
        <p class="question">Which integrations can actually be built, and how do we know?</p>
        <div class="prose">
          <p>{description}</p>
          <p>One hundred applications were researched end to end, classified
          against a fixed taxonomy, and then checked. The headline number is the
          one that is hardest to flatter: <strong>field-level accuracy on Sample
          B</strong>, {sample} applications the improved classifier had never been
          evaluated against, scored across {fields} verified fields against values
          established by independent verification.</p>
        </div>
      </div>
      <dl class="run-facts">{facts}</dl>
    </div>
    <div class="kpis">{kpis}</div>
    <div class="note">Two numbers are reported for every sample because one of
    them alone is misleading. Field-level accuracy asks how many individual
    values are right. Row-level accuracy asks how many applications are right in
    <em>every</em> field, and it is always much lower. A pipeline that quotes
    only the first is hiding the second.</div>
  </div>
</section>
""".format(
        as_of=_e(settings.as_of.date().isoformat()),
        description=_e(C.CASE_STUDY_DESCRIPTION),
        sample=_e(sample_b.apps if sample_b else 0),
        fields=len(VERIFIED_FIELDS),
        facts="".join(
            "<div><dt>{}</dt><dd>{}</dd></div>".format(_e(label), _e(value))
            for label, value in facts
        ),
        kpis=kpis,
    )


def _snapshot(analytics: AnalyticsReport, categories: Dict[str, str], total: int) -> str:
    panels = []
    for field, filter_key, title in (
        (F.BUILDABILITY, "buildability", "Buildability"),
        (F.MCP, "mcp", "MCP server availability"),
        (F.CREDENTIAL_ACCESS, "credential_access", "How credentials are obtained"),
    ):
        item = _distribution_of(analytics, field)
        if item is None:
            continue
        panels.append(
            _panel(
                title,
                _bar_rows(item, filter_key=filter_key),
                meta="{} applications".format(item.total),
            )
        )

    breakdowns = "".join(
        "<details><summary>{label}</summary>{table}</details>".format(
            label=_e(tab.label),
            table=_table(
                [_row_dimension_label(tab.row_attribute)]
                + [_humanise(column) for column in tab.columns],
                [
                    [categories.get(row, _humanise(row))]
                    + [tab.cells[row].get(column, 0) for column in tab.columns]
                    for row in tab.rows
                ],
                numeric=tuple(range(1, len(tab.columns) + 1)),
            ),
        )
        for tab in analytics.cross_tabs
    )

    return """
<section id="snapshot">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Research snapshot</span>
      <h2>Where the {total} applications landed</h2>
      <p class="prose">Unresolved values are counted rather than dropped: how
      often a field could not be established is a finding about the research, not
      a gap in the chart. <span data-js-only>Select any bar to filter the dataset
      below.</span></p>
    </div>
    <div class="grid-3">{panels}</div>
    <div class="breakdowns">{breakdowns}</div>
  </div>
</section>
""".format(total=total, panels="".join(panels), breakdowns=breakdowns)


def _findings(patterns: PatternReport) -> str:
    cards = []
    for pattern in sorted(
        patterns.patterns, key=lambda item: (-item.observed, item.key)
    ):
        cards.append(
            """
<button type="button" class="finding" data-finding="{key}" aria-pressed="false">
  <span class="count">{observed}<span> / {population}</span></span>
  <h3>{title}</h3>
  <p>{statement}</p>
  <span class="action">View applications \u2192</span>
</button>
""".format(
                key=_e(pattern.key),
                observed=_e(pattern.observed),
                population=_e(pattern.population),
                title=_e(pattern.title),
                statement=_e(pattern.statement),
            )
        )
    return """
<section id="findings">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Key findings</span>
      <h2>What the data says</h2>
      <p class="prose">Each of these is a predicate evaluated over the dataset,
      and the applications supporting it are listed in
      <code>patterns.json</code>. If the data changes, the sentence changes with
      it. <span data-js-only>Open any finding to see exactly which applications
      it counts.</span></p>
    </div>
    <div class="findings">{cards}</div>
  </div>
</section>
""".format(cards="".join(cards))


def _sample_row(sample: SampleAccuracy) -> List[object]:
    return [
        "Sample {}".format(sample.group.value),
        _humanise(sample.measurement),
        sample.classifier_version,
        sample.apps,
        _pct(sample.field_level_accuracy),
        _pct(sample.row_level_accuracy),
        _pct(sample.evidence_validity),
    ]


def _accuracy_section(
    accuracy: AccuracyReport, improvements: ImprovementReport
) -> str:
    sample_a = accuracy.sample(C.SampleGroup.A)
    sample_b = accuracy.sample(C.SampleGroup.B)
    before = sample_a.field_level_accuracy if sample_a else None
    after = sample_b.field_level_accuracy if sample_b else None
    delta = (after - before) if (before is not None and after is not None) else None

    moves = []
    for row in viewmodel.per_field_accuracy(accuracy):
        change = (
            (row["b"] - row["a"])
            if (row["a"] is not None and row["b"] is not None)
            else None
        )
        direction = "flat"
        if change:
            direction = "up" if change > 0 else "down"
        moves.append(
            """
<div class="field-move">
  <span class="label">{label} <span class="delta {dir}">{delta}</span></span>
  <div class="move-bars">
    <span class="move-line"><span>{v1}</span>
      <span class="track"><span class="fill" style="width:{a_width:.1f}%"></span></span>
      <span class="pct">{a}</span></span>
    <span class="move-line final"><span>{v2}</span>
      <span class="track"><span class="fill" style="width:{b_width:.1f}%"></span></span>
      <span class="pct">{b}</span></span>
  </div>
</div>
""".format(
                label=_e(row["label"]),
                dir=direction,
                delta=_e(
                    "{}{:.1f} pts".format(
                        "+" if (change or 0) > 0 else "", (change or 0) * 100
                    )
                    if change
                    else "no change"
                ),
                v1=_e(improvements.from_classifier),
                v2=_e(improvements.to_classifier),
                a=_pct(row["a"]),
                b=_pct(row["b"]),
                a_width=(row["a"] or 0) * 100,
                b_width=(row["b"] or 0) * 100,
            )
        )

    improvement_rows = [
        [
            _humanise(item.key.replace("-", "_")),
            item.failure_mode,
            item.change,
            item.observed_in_sample_a,
        ]
        for item in improvements.improvements
    ]

    return """
<section id="verification">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Accuracy</span>
      <h2>What the first pass got wrong, and what changed</h2>
      <p class="prose">Sample A is scored against values frozen <em>before</em>
      the improvement phase, so improving the classifier cannot retroactively
      improve the first-pass number. Sample B is scored on applications the
      improved classifier had never been evaluated against.</p>
    </div>

    <div class="compare">
      <div class="compare-card">
        <div class="who">Sample A \u00b7 first pass</div>
        <div class="value">{before}</div>
        <div class="detail">classifier {v1} \u00b7 {a_apps} applications \u00b7 {a_correct} of {a_checked} field values correct</div>
      </div>
      <div class="compare-arrow" aria-hidden="true">\u2192</div>
      <div class="compare-card final">
        <div class="who">Sample B \u00b7 final</div>
        <div class="value">{after}</div>
        <div class="detail">classifier {v2} \u00b7 {b_apps} applications \u00b7 {b_correct} of {b_checked} field values correct</div>
      </div>
    </div>
    <p class="prose mt-sm">{delta_sentence}</p>

    <div class="mt-md">{samples_panel}</div>
    <div class="mt-sm">{per_field_panel}</div>

    <div class="section-head mt-lg">
      <h3>The rules that changed</h3>
      <p class="prose">Each failure was traced to the rule that produced it, and
      the rule was changed once for every application rather than patched per
      app. The classifier version is recorded on every record, so which rules
      produced which value is never in doubt.</p>
    </div>
    {improvements}
  </div>
</section>
""".format(
        before=_pct(before),
        after=_pct(after),
        v1=_e(improvements.from_classifier),
        v2=_e(improvements.to_classifier),
        a_apps=_e(sample_a.apps if sample_a else 0),
        a_correct=_e(sample_a.fields_correct if sample_a else 0),
        a_checked=_e(sample_a.fields_checked if sample_a else 0),
        b_apps=_e(sample_b.apps if sample_b else 0),
        b_correct=_e(sample_b.fields_correct if sample_b else 0),
        b_checked=_e(sample_b.fields_checked if sample_b else 0),
        delta_sentence=_e(
            "Field-level accuracy moved {:+.1f} points across the improvement phase. "
            "Not every field improved: the per-field panel shows where the rules "
            "still disagree with the verified values.".format((delta or 0) * 100)
        ),
        per_field_panel=_panel(
            "Per-field accuracy",
            '<div class="moves">{}</div>'.format("".join(moves)),
            meta="first pass vs final",
        ),
        samples_panel=_panel(
            "Both samples, both measurements",
            _table(
                [
                    "Sample",
                    "Measurement",
                    "Classifier",
                    "Apps",
                    "Field-level",
                    "Row-level",
                    "Evidence validity",
                ],
                [_sample_row(sample) for sample in accuracy.samples],
                numeric=(3, 4, 5, 6),
            ),
            meta="row-level requires every field of an app to be right",
        ),
        improvements=_table(
            [
                "Change",
                "Failure mode",
                "What {} does instead".format(improvements.to_classifier),
                "Sample A misses",
            ],
            improvement_rows,
            numeric=(3,),
        ),
    )


def _channels(dataset: Dataset, total: int) -> str:
    sampled = sum(1 for record in dataset.records if record.sample_group)
    human_decisions = sum(
        1
        for record in dataset.records
        for decision in record.reconciliation
        if decision.decided_by
    )
    cards = [
        (
            "A",
            "Research",
            "{} applications".format(total),
            "Gathers sources and classifies every field.",
            False,
        ),
        (
            "B",
            "Independent re-derivation",
            "{} sampled applications".format(sampled),
            "Reads the same sources with different rules, without seeing Channel A's answer.",
            True,
        ),
        (
            "C",
            "Citation audit",
            "{} sampled applications".format(sampled),
            "Checks that each cited page supports the field it is cited for.",
            False,
        ),
        (
            "D",
            "Human review",
            "{} adjudicated fields".format(human_decisions),
            "Rules on disputed and triggered fields, and stays silent everywhere else.",
            False,
        ),
    ]
    return """
<section id="channels">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Verification design</span>
      <h2>Four channels, and what each one can catch</h2>
    </div>
    <div class="channels">{cards}</div>
    <div class="note"><strong>Channel B is blind to Channel A.</strong> It does
    not see the recorded answer and does not share the classifier's rules, so
    agreement between them is evidence rather than an echo. Channel D is silent
    unless a reviewer actually ruled on a field: a human rubber-stamping the
    pipeline's own output would make the accuracy number circular.</div>
  </div>
</section>
""".format(
        cards="".join(
            """
<div class="channel{blind}">
  <div class="letter">{letter}</div>
  <h3>{method}</h3>
  <div class="scope">{scope}</div>
  <p>{what}</p>
</div>
""".format(
                blind=" blind" if blind else "",
                letter=_e(letter),
                method=_e(method),
                scope=_e(scope),
                what=_e(what),
            )
            for letter, method, scope, what, blind in cards
        )
    )


def _explorer(dataset: Dataset, payload: Dict[str, object], categories: Dict[str, str]) -> str:
    facets = payload["facets"]  # type: ignore[index]

    def options(key: str, placeholder: str) -> str:
        items = facets[key]  # type: ignore[index]
        parts = ['<option value="">{}</option>'.format(_e(placeholder))]
        for item in items:
            parts.append(
                '<option value="{value}">{label} ({count})</option>'.format(
                    value=_e(item["value"]),
                    label=_e(
                        item["label"]
                        if key != "sample"
                        else "Sample {}".format(item["label"])
                    ),
                    count=_e(item["count"]),
                )
            )
        return "".join(parts)

    columns = (
        ("name", "Application"),
        ("category", "Category"),
        ("buildability", "Buildability"),
        ("credential_access", "Credentials"),
        ("mcp", "MCP"),
        ("confidence", "Confidence"),
        ("sample", "Sample"),
    )
    head = "".join(
        '<th scope="col" class="sortable" data-sort="{key}" aria-sort="none" '
        'tabindex="0" role="columnheader">{label}<span class="arrow">\u25b2</span></th>'.format(
            key=_e(key), label=_e(label)
        )
        for key, label in columns
    )

    return """
<section id="dataset">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Dataset explorer</span>
      <h2>All {total} applications</h2>
      <p class="prose">The final dataset, one row per application. Sampled
      applications carry the verification that was run on them.
      <span data-js-only>Filter, sort, and open any row for its fields,
      rationales and the evidence behind them. Press <kbd>/</kbd> to
      search.</span></p>
    </div>

    <div id="explorer-error" class="panel error-state" data-js-only hidden>
      <h3>Unable to load the dataset</h3>
      <p data-error-detail>The dataset projection did not load.</p>
      <button type="button" class="btn primary" data-retry>Retry</button>
    </div>

    <div id="explorer-shell" class="explorer" data-js-only hidden>
      <div class="toolbar">
        <div class="field search">
          <label for="search">Search</label>
          <span class="icon" aria-hidden="true">\u2315</span>
          <input id="search" type="search" placeholder="Application, id, or category"
                 autocomplete="off" spellcheck="false">
          <kbd>/</kbd>
        </div>
        <div class="field">
          <label for="filter-category-id">Category</label>
          <select id="filter-category-id">{categories}</select>
        </div>
        <div class="field">
          <label for="filter-buildability">Buildability</label>
          <select id="filter-buildability">{buildability}</select>
        </div>
        <div class="field">
          <label for="filter-credential-access">Credentials</label>
          <select id="filter-credential-access">{credentials}</select>
        </div>
        <div class="field">
          <label for="filter-mcp">MCP</label>
          <select id="filter-mcp">{mcp}</select>
        </div>
        <div class="field">
          <label for="filter-confidence">Confidence</label>
          <select id="filter-confidence">{confidence}</select>
        </div>
        <div class="field">
          <label for="filter-sample">Sample</label>
          <select id="filter-sample">{sample}</select>
        </div>
      </div>

      <div class="status-bar">
        <span class="count" id="result-count"></span>
        <span id="chips"></span>
        <span class="spacer"></span>
        <button type="button" class="btn" id="clear-filters" hidden>Clear filters</button>
      </div>

      <div class="table-scroll" id="table-scroll">
        <table>
          <caption class="visually-hidden">Applications in the final dataset</caption>
          <thead><tr>{head}<th scope="col"><span class="visually-hidden">Open</span></th></tr></thead>
          <tbody id="rows"></tbody>
        </table>
      </div>

      <div class="empty" id="empty-state" hidden>
        <h3>No applications match these filters.</h3>
        <p>Nothing in the dataset satisfies every condition at once.</p>
        <button type="button" class="btn" id="empty-clear">Clear filters</button>
      </div>
    </div>

    <noscript>
      <p class="prose">The interactive explorer needs JavaScript. The full table
      is below, and the same data is downloadable as JSON and CSV.</p>
    </noscript>
    <div class="no-js-only">{static_table}</div>

    <div class="downloads mt-sm">
      <a href="data/{json}" download>Final dataset (JSON)</a>
      <a href="data/{csv}" download>Flat table (CSV)</a>
      <a href="data/{analytics}" download>Analytics</a>
      <a href="data/{patterns}" download>Patterns</a>
      <a href="data/{accuracy}" download>Accuracy</a>
    </div>
  </div>
</section>
""".format(
        total=len(dataset.records),
        categories=options("category", "All categories"),
        buildability=options("buildability", "Any buildability"),
        credentials=options("credential_access", "Any credential path"),
        mcp=options("mcp", "Any MCP status"),
        confidence=options("confidence", "Any confidence"),
        sample=options("sample", "Any sample"),
        head=head,
        static_table=_dataset_table(dataset, categories),
        json=C.FINAL_DATASET_FILENAME,
        csv=C.FINAL_DATASET_CSV_FILENAME,
        analytics=C.ANALYTICS_FILENAME,
        patterns=C.PATTERNS_FILENAME,
        accuracy=C.ACCURACY_FILENAME,
    )


def _dataset_table(dataset: Dataset, categories: Dict[str, str]) -> _Html:
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
                _tag(token),
                _humanise((access.value or [access.status.value])[0]),
                _humanise((mcp.value or [mcp.status.value])[0]),
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


def _methodology(
    dataset: Dataset,
    analytics: AnalyticsReport,
    queue: ReviewQueue,
    settings: Settings,
    metric: Dict[str, object],
    total: int,
) -> str:
    stages = _stage_rows(dataset, queue, settings, total)
    rail = []
    panels = []
    for index, (key, name, scope, what, why) in enumerate(stages):
        rail.append(
            '<button type="button" data-stage="{key}" role="tab" '
            'aria-selected="{selected}">{name}</button>'.format(
                key=_e(key), name=_e(name), selected="true" if index == 0 else "false"
            )
        )
        if index < len(stages) - 1:
            rail.append('<span class="sep" aria-hidden="true">\u203a</span>')
        panels.append(
            """
<div class="panel stage-detail" data-stage-panel="{key}">
  <div class="panel-head"><h3>{name}</h3><span class="meta">{scope}</span></div>
  <div class="panel-body"><dl>
    <div><dt>What it does</dt><dd>{what}</dd></div>
    <div><dt>Scope</dt><dd>{scope}</dd></div>
    <div><dt>Why it exists</dt><dd>{why}</dd></div>
  </dl></div>
</div>
""".format(
                key=_e(key),
                name=_e(name),
                scope=_e(scope),
                what=_e(what),
                why=_e(why),
            )
        )

    dimensions = [
        (
            "Technical feasibility",
            "Is there an API, and does it cover a meaningful part of the product?",
            "api_exists, api_breadth, api_capabilities",
        ),
        (
            "Credential accessibility",
            "Can a developer obtain working credentials, and on what terms?",
            "credential_access, authentication",
        ),
        (
            "Commercial accessibility",
            "Does reaching the API require a paid plan, a contract or a partner programme?",
            "access_restrictions, blocker",
        ),
    ]
    breadth_rows = [
        (_humanise(name.value), text) for name, text in API_BREADTH_ANCHORS.items()
    ]

    return """
<section id="methodology">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Method</span>
      <h2>How the pipeline works</h2>
      <p class="prose">Deciding which integrations to build is a research problem
      before it is an engineering one. The facts that matter - is there an API,
      how broad is it, can a developer actually get credentials, what stands in
      the way - are scattered across vendor documentation, pricing pages and
      repositories, and they are exactly the kind of facts a language model will
      answer fluently whether or not it knows. So the pipeline is built around
      one rule: <strong>a value is worth nothing without the evidence behind
      it</strong>.</p>
      <p class="prose">The stages are fixed in order.
      <span data-js-only>Select a stage to see what it does, what it covers, and
      why it is there.</span></p>
    </div>
    <div class="rail" role="tablist" aria-label="Pipeline stages">{rail}</div>
    {panels}

    <div class="section-head mt-lg">
      <h2>Two judgements that are not left to a model</h2>
      <p class="prose">Confidence is a function of recorded properties of the
      evidence: whether the product was identified, whether the vendor's own
      documentation was cited, whether every critical field carries evidence,
      whether anything contradicts anything else, and how many distinct sources
      were found. A record reaches <span class="mono">high</span> only with all
      of those and at least {sources} sources. A single missing critical field,
      an unresolved identity or a lone source drops it to
      <span class="mono">low</span> regardless of how confident the prose
      sounded.</p>
    </div>
    <div class="grid-2">
      {confidence_panel}
      {breadth_panel}
    </div>

    <div class="section-head mt-lg">
      <h3>Buildability is a decision tree, not an opinion</h3>
      <p class="prose">Three independent legs are answered first, and the verdict
      is the worst of them, with a definite failure outranking a gap. That is why
      a product with an excellent API can still be
      <span class="mono">blocked</span>: the API was never the binding
      constraint. Each leg, and the evidence confidence behind it, is recorded on
      every application and shown in its detail panel.</p>
    </div>
    <div class="grid-3">{dimensions}</div>

    <div class="section-head mt-lg">
      <h3>Three ways of not knowing</h3>
      <p class="prose">The taxonomy separates what a single "unknown" would
      collapse. <span class="mono">not_found</span> means the sources did not
      say. <span class="mono">unavailable</span> means they did say, and the
      answer is that the thing does not exist. <span class="mono">unclear</span>
      means the sources disagree or the question does not resolve to one value.
      The difference matters: absence of evidence and evidence of absence lead to
      different decisions.</p>
    </div>
  </div>
</section>
""".format(
        rail="".join(rail),
        panels="".join(panels),
        sources=HIGH_SOURCE_MINIMUM,
        confidence_panel=_panel(
            "Confidence across the final dataset",
            _bar_rows(
                Distribution(
                    attribute="confidence",
                    label="Confidence",
                    counts={
                        "high": int(metric["confidence_high"]),
                        "medium": int(metric["confidence_medium"]),
                        "low": int(metric["confidence_low"]),
                    },
                    unresolved={},
                    total=total,
                    multi_valued=False,
                ),
                filter_key="confidence",
            ),
            meta="computed, not declared",
        ),
        breadth_panel=_panel(
            "API breadth anchors",
            _table(["Breadth", "What it means"], breadth_rows),
            meta="so the word means the same thing for every app",
        ),
        dimensions="".join(
            """
<div class="dimension">
  <h3>{title}</h3>
  <p>{question}</p>
  <div class="asks">{fields}</div>
</div>
""".format(title=_e(title), question=_e(question), fields=_e(fields))
            for title, question, fields in dimensions
        ),
    )


def _boundaries(
    dataset: Dataset, metric: Dict[str, object], settings: Settings
) -> str:
    unresolved_share = metric.get("unresolved_field_share")
    decisions = sum(
        1
        for record in dataset.records
        for decision in record.reconciliation
        if decision.decided_by
    )
    items = [
        (
            "Evidence is cited, not fetched in this run",
            "The committed run replays a reviewed source corpus so that anybody "
            "can reproduce it byte for byte without credentials or network "
            "access. Every evidence item records retrieval: cited for exactly "
            "this reason. A live run would record fetched and carry page excerpts.",
        ),
        (
            "{} of verified field values are unresolved".format(
                _pct(unresolved_share if isinstance(unresolved_share, float) else 0.0)
            ),
            "That is reported rather than filled in. A confident wrong answer is "
            "more expensive than an admitted gap.",
        ),
        (
            "One reviewer",
            "Channel D is a single human. Inter-rater agreement is not measured, "
            "so the reconciled values inherit that reviewer's judgement on the "
            "{} fields they ruled on.".format(decisions),
        ),
        (
            "The taxonomy has gaps",
            "Self-hosting is friction that no blocker value names, so it is "
            "carried as other and flagged. API breadth is a judgement anchored to "
            "documented resource groups; reasonable readers disagree, and Sample "
            "B's remaining misses are mostly exactly that disagreement.",
        ),
        (
            "Accuracy is measured on {} applications per sample".format(
                settings.sample_size_a
            ),
            "Fifteen apps is enough to locate systematic rule failures and far "
            "too few to put a tight confidence interval around the headline number.",
        ),
        (
            "Findings are a snapshot",
            "Pricing, plans and MCP servers move; the dataset records what the "
            "sources said as of {}.".format(settings.as_of.date().isoformat()),
        ),
    ]
    return """
<section id="boundaries">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Research boundaries</span>
      <h2>What this does not establish</h2>
      <p class="prose">These are the limits of the claim, kept next to the claim
      rather than at the bottom of a page nobody reaches.</p>
    </div>
    <div class="boundaries">{items}</div>
  </div>
</section>
""".format(
        items="".join(
            '<div class="boundary"><h3>{title}</h3><p>{body}</p></div>'.format(
                title=_e(title), body=_e(body)
            )
            for title, body in items
        )
    )


def _reproducibility(
    dataset: Dataset, validation: ValidationReport, queue: ReviewQueue, settings: Settings
) -> str:
    lines = "".join(
        """
<div class="terminal-line">
  <span class="prompt" aria-hidden="true">$</span>
  <code>{command}</code>
  <button type="button" class="copy" data-copy="{command}"
          aria-label="Copy command: {command}">Copy</button>
</div>
""".format(command=_e(command))
        for command, _ in COMMANDS
    )
    facts = [
        ("Master seed", settings.seed),
        ("Sample A namespace", C.SEED_NAMESPACE_SAMPLE_A),
        ("Sample B namespace", C.SEED_NAMESPACE_SAMPLE_B),
        ("Pipeline clock", settings.as_of.isoformat()),
        ("Research provider", dataset.provider.value),
        ("Classifier", dataset.classifier_version),
        ("Schema version", C.SCHEMA_VERSION),
        ("Dataset fingerprint", dataset.metadata.source_fingerprint or "-"),
    ]
    return """
<section id="reproducibility">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Reproducibility</span>
      <h2>Running this yourself</h2>
      <p class="prose">Everything is seeded from one master seed and stamped with
      one pipeline clock, so a second run produces byte-identical artifacts and
      any diff is a real change.</p>
    </div>
    <div class="grid-2">
      <div class="terminal">
        <div class="terminal-head"><span>composio-ops</span><span>{provider} provider \u00b7 no network</span></div>
        <div class="terminal-body">{lines}</div>
      </div>
      {facts_panel}
    </div>
    <p class="prose mt-sm">Validation ran {checks} checks over
    the research pass and recorded {errors} blocking errors and {warnings}
    warnings; the review triggers queued {queued} of {total} applications for
    human attention.</p>
  </div>
</section>
""".format(
        provider=_e(dataset.provider.value),
        lines=lines,
        facts_panel=_panel(
            "This run",
            _table(["Setting", "Value"], facts),
            meta="recorded on every artifact",
        ),
        checks=validation.checked_records,
        errors=len(validation.errors),
        warnings=len(validation.warnings),
        queued=len(queue.entries),
        total=queue.population_size,
    )


def _drawer() -> str:
    return """
<div id="backdrop" class="backdrop" data-js-only></div>
<aside id="drawer" class="drawer" role="dialog" aria-modal="true"
       aria-labelledby="drawer-title" aria-hidden="true" data-js-only>
  <div class="drawer-head">
    <div>
      <h2 id="drawer-title">Application</h2>
      <div class="sub" id="drawer-sub"></div>
    </div>
    <button type="button" class="drawer-close" id="drawer-close" aria-label="Close details">\u00d7</button>
  </div>
  <div class="drawer-body" id="drawer-body"></div>
</aside>
"""


def _page(
    payload: Dict[str, object],
    dataset: Dataset,
    analytics: AnalyticsReport,
    patterns: PatternReport,
    accuracy: AccuracyReport,
    improvements: ImprovementReport,
    validation: ValidationReport,
    queue: ReviewQueue,
    settings: Settings,
) -> str:
    """The markup, given a projection that has already been built."""
    meta = payload["meta"]  # type: ignore[index]
    metric = meta["metrics"]  # type: ignore[index]
    total = len(dataset.records)
    categories = {item.category_id: item.name for item in dataset.categories}

    body = "".join(
        [
            _header(meta),
            '<main id="main">',
            _overview(dataset, accuracy, settings, metric, total),
            _snapshot(analytics, categories, total),
            _findings(patterns),
            _accuracy_section(accuracy, improvements),
            _channels(dataset, total),
            _explorer(dataset, payload, categories),
            _methodology(dataset, analytics, queue, settings, metric, total),
            _boundaries(dataset, metric, settings),
            _reproducibility(dataset, validation, queue, settings),
            "</main>",
            _footer(dataset, accuracy),
            _drawer(),
        ]
    )

    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="stylesheet" href="{styles}">
<script>document.documentElement.classList.add("js");</script>
</head>
<body>
<a class="visually-hidden" href="#main">Skip to content</a>
{body}
<script src="{payload}"></script>
<script src="{script}"></script>
</body>
</html>
""".format(
        title=_e(C.CASE_STUDY_TITLE),
        description=_e(C.CASE_STUDY_DESCRIPTION),
        styles=_e(_versioned(C.SITE_STYLES_FILENAME, dataset)),
        payload=_e(_versioned(C.SITE_PAYLOAD_FILENAME, dataset)),
        script=_e(_versioned(C.SITE_SCRIPT_FILENAME, dataset)),
        body=body,
    )


def _versioned(filename: str, dataset: Dataset) -> str:
    """Asset URL stamped with the dataset fingerprint.

    The markup, the styles, the script and the projection only make sense as a
    set. Stamping them means a reader who saw an earlier run cannot end up with
    last week's script driving this week's data out of the browser cache.
    """
    return "{}?v={}".format(filename, dataset.metadata.source_fingerprint or "dev")


def _footer(dataset: Dataset, accuracy: AccuracyReport) -> str:
    return """
<footer>
  <div class="wrap">
    <p>Generated from the artifacts by <code>composio-ops casestudy build</code>.
    Headline metric <span class="mono">{metric}</span> at {headline}. Dataset
    fingerprint <span class="mono">{fingerprint}</span>.</p>
    <div class="downloads">
      <a href="data/{json}" download>JSON</a>
      <a href="data/{csv}" download>CSV</a>
      <a href="data/{analytics}" download>Analytics</a>
      <a href="data/{patterns}" download>Patterns</a>
      <a href="data/{accuracy}" download>Accuracy</a>
    </div>
  </div>
</footer>
""".format(
        metric=_e(accuracy.headline_metric),
        headline=_e(_pct(accuracy.headline_value)),
        fingerprint=_e(dataset.metadata.source_fingerprint or "-"),
        json=C.FINAL_DATASET_FILENAME,
        csv=C.FINAL_DATASET_CSV_FILENAME,
        analytics=C.ANALYTICS_FILENAME,
        patterns=C.PATTERNS_FILENAME,
        accuracy=C.ACCURACY_FILENAME,
    )


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
    """Render the case study markup from the artifacts."""
    html, _ = _render_all(
        dataset=dataset,
        analytics=analytics,
        patterns=patterns,
        accuracy=accuracy,
        improvements=improvements,
        validation=validation,
        queue=queue,
        settings=settings,
    )
    return html


def _render_all(
    dataset: Dataset,
    analytics: AnalyticsReport,
    patterns: PatternReport,
    accuracy: AccuracyReport,
    improvements: ImprovementReport,
    validation: ValidationReport,
    queue: ReviewQueue,
    settings: Settings,
) -> Tuple[str, Dict[str, object]]:
    """The markup and the projection it assumes, built from one pass."""
    payload = viewmodel.build(
        dataset=dataset,
        analytics=analytics,
        patterns=patterns,
        accuracy=accuracy,
        improvements=improvements,
        validation=validation,
        queue=queue,
        settings=settings,
    )
    html = _page(
        payload=payload,
        dataset=dataset,
        analytics=analytics,
        patterns=patterns,
        accuracy=accuracy,
        improvements=improvements,
        validation=validation,
        queue=queue,
        settings=settings,
    )
    return html, payload


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
    """Render and write the page and its assets, returning the page's path."""
    html, payload = _render_all(
        dataset=dataset,
        analytics=analytics,
        patterns=patterns,
        accuracy=accuracy,
        improvements=improvements,
        validation=validation,
        queue=queue,
        settings=settings,
    )

    paths = settings.paths
    paths.ensure_directories()
    paths.case_study.write_text(html, encoding="utf-8")
    paths.site_styles.write_text(assets.STYLES.lstrip("\n"), encoding="utf-8")
    paths.site_script.write_text(
        assets.script(
            C.SITE_PAYLOAD_GLOBAL, _versioned(C.SITE_PAYLOAD_FILENAME, dataset)
        ).lstrip("\n"),
        encoding="utf-8",
    )
    paths.site_payload.write_text(
        "window.{name} = {payload};\n".format(
            name=C.SITE_PAYLOAD_GLOBAL, payload=viewmodel.serialise(payload)
        ),
        encoding="utf-8",
    )
    return paths.relative(paths.case_study)
