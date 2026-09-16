"""Static assets for the published site: one stylesheet, one script.

They are kept here as plain strings rather than as files in the repository so
that `casestudy build` writes the whole site from one code path, and so that the
page, its styles and its behaviour version together with the renderer that
assumes them.

Neither asset fetches anything or depends on a framework. The script reads the
dataset projection that `viewmodel` writes alongside it and turns the static
markup into a filterable explorer; with scripting off, the server-rendered
markup is still a complete, readable report.
"""

STYLES = """
/* Composio research intelligence - presentation layer.
   Design tokens first, then layout, then components. One accent, flat
   surfaces, borders instead of shadows except where something floats. */

:root {
  --bg: #fbfbfc;
  --surface: #ffffff;
  --surface-2: #f5f6f8;
  --surface-3: #eef0f4;
  --line: #e4e6eb;
  --line-2: #d3d7df;
  --ink: #111419;
  --ink-2: #39414f;
  --muted: #6a7382;
  --accent: #2f56c9;
  --accent-ink: #1d3b94;
  --accent-weak: #eef2fd;
  --good: #11674a;
  --good-weak: #e9f4ef;
  --good-line: #b6ddca;
  --warn: #8a5709;
  --warn-weak: #fcf3e3;
  --warn-line: #e8cf9c;
  --bad: #a3231f;
  --bad-weak: #fbeeed;
  --bad-line: #e8b8b5;
  --radius: 8px;
  --radius-sm: 6px;
  --shadow-sm: 0 1px 2px rgba(17, 20, 25, .05);
  --shadow-lg: 0 18px 44px rgba(17, 20, 25, .18);
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, Helvetica, Arial, sans-serif;
  --header-h: 56px;
}

* { box-sizing: border-box; }

html { scroll-behavior: smooth; }
@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } }

body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 15px/1.6 var(--sans);
  -webkit-font-smoothing: antialiased;
  font-variant-numeric: tabular-nums;
}

a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }

h1, h2, h3, h4 { margin: 0; font-weight: 620; letter-spacing: -.011em; }
p { margin: 0 0 .75rem; }
p:last-child { margin-bottom: 0; }

:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  border-radius: 3px;
}

.wrap { max-width: 1240px; margin: 0 auto; padding: 0 24px; }
.prose { max-width: 62ch; color: var(--ink-2); }
.prose strong { color: var(--ink); }
.mono { font-family: var(--mono); font-size: .86em; }
.muted { color: var(--muted); }
.nowrap { white-space: nowrap; }
.visually-hidden {
  position: absolute; width: 1px; height: 1px; margin: -1px;
  clip: rect(0 0 0 0); clip-path: inset(50%); overflow: hidden;
}

/* --- header ------------------------------------------------------------- */

.app-header {
  position: sticky;
  top: 0;
  z-index: 40;
  height: var(--header-h);
  background: rgba(255, 255, 255, .88);
  backdrop-filter: saturate(180%) blur(8px);
  border-bottom: 1px solid var(--line);
}
.app-header .wrap {
  height: 100%;
  display: flex;
  align-items: center;
  gap: 24px;
}
/* The brand never shrinks; the tab strip scrolls instead. */
.brand { display: flex; align-items: center; gap: 10px; flex: none; }
.brand-mark {
  width: 26px; height: 26px; border-radius: 7px; flex: none;
  background: var(--accent);
  color: #fff;
  display: grid; place-items: center;
  font-size: 12px; font-weight: 700; letter-spacing: -.02em;
}
.brand-text { display: flex; flex-direction: column; line-height: 1.15; min-width: 0; }
.brand-name { font-size: 13.5px; font-weight: 620; }
.brand-sub { font-size: 11.5px; color: var(--muted); }

.tabs { display: flex; gap: 2px; margin-left: 8px; overflow-x: auto; scrollbar-width: none; min-width: 0; }
.tabs::-webkit-scrollbar { display: none; }
.tabs a {
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--ink-2);
  white-space: nowrap;
}
.tabs a:hover { background: var(--surface-2); text-decoration: none; }
.tabs a[aria-current="true"] { background: var(--accent-weak); color: var(--accent-ink); font-weight: 560; }

.header-meta {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 12px;
  color: var(--muted);
}
.header-meta span { white-space: nowrap; }
.header-meta b { color: var(--ink-2); font-weight: 560; }

/* --- sections ----------------------------------------------------------- */

section { padding: 44px 0; border-top: 1px solid var(--line); scroll-margin-top: calc(var(--header-h) + 8px); }
section:first-of-type { border-top: 0; }
.section-head { margin-bottom: 20px; }
.section-head h2 { font-size: 20px; }
.section-head .prose { margin-top: 8px; }
.eyebrow {
  display: block;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: .07em;
  color: var(--muted);
  font-weight: 600;
  margin-bottom: 6px;
}

/* --- hero --------------------------------------------------------------- */

.hero { padding-top: 40px; }
.hero h1 { font-size: 30px; line-height: 1.22; max-width: 22ch; }
.hero .question {
  margin: 14px 0 12px;
  font-size: 17px;
  color: var(--ink-2);
  border-left: 3px solid var(--accent);
  padding-left: 14px;
  max-width: 60ch;
}
.hero-grid { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); gap: 40px; align-items: start; }
.run-facts {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  padding: 14px 16px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 18px;
  font-size: 12.5px;
}
.run-facts div { min-width: 0; }
.run-facts dt { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .05em; }
.run-facts dd { margin: 2px 0 0; font-family: var(--mono); font-size: 12px; word-break: break-word; }

.kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-top: 26px;
}
.kpi {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  padding: 14px 16px;
}
.kpi .value { font-size: 27px; font-weight: 640; letter-spacing: -.02em; line-height: 1.15; }
.kpi .label { font-size: 13px; font-weight: 560; margin-top: 2px; }
.kpi .context { font-size: 12px; color: var(--muted); margin-top: 3px; }

/* --- panels ------------------------------------------------------------- */

.panel {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
}
.panel-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--line);
}
.panel-head h3 { font-size: 13.5px; }
.panel-head .meta { font-size: 11.5px; color: var(--muted); }
.panel-body { padding: 14px 16px; }
.grid-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
.grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.mt-sm { margin-top: 14px; }
.mt-md { margin-top: 24px; }
.mt-lg { margin-top: 34px; }

/* --- disclosures -------------------------------------------------------- */

.breakdowns { margin-top: 16px; display: grid; gap: 8px; }
.breakdowns details {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
}
.breakdowns summary {
  cursor: pointer;
  padding: 10px 14px;
  font-size: 13px;
  font-weight: 560;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 8px;
}
.breakdowns summary::-webkit-details-marker { display: none; }
.breakdowns summary::before {
  content: "\\203a";
  color: var(--muted);
  transition: transform .12s ease;
}
.breakdowns details[open] summary::before { transform: rotate(90deg); }
.breakdowns summary:hover { background: var(--surface-2); }
.breakdowns details[open] summary { border-bottom: 1px solid var(--line); }
.breakdowns .table-wrap { padding: 4px 14px 12px; }

/* --- bar charts --------------------------------------------------------- */

.bars { display: flex; flex-direction: column; gap: 9px; }
.bar-row {
  display: grid;
  grid-template-columns: minmax(7.5rem, 11rem) minmax(0, 1fr) 3.4rem;
  align-items: center;
  gap: 12px;
  width: 100%;
  border: 0;
  background: none;
  padding: 2px 4px;
  margin: 0 -4px;
  border-radius: var(--radius-sm);
  font: inherit;
  color: inherit;
  text-align: left;
}
button.bar-row { cursor: pointer; }
button.bar-row:hover { background: var(--surface-2); }
button.bar-row[aria-pressed="true"] { background: var(--accent-weak); }
.bar-row .name { font-size: 12.5px; color: var(--ink-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bar-row .track { height: 8px; border-radius: 999px; background: var(--surface-3); overflow: hidden; }
.bar-row .fill { display: block; height: 100%; background: var(--accent); border-radius: 999px; }
.bar-row .count { font-size: 12.5px; color: var(--ink-2); text-align: right; }
.bar-row .count em { font-style: normal; color: var(--muted); font-size: 11.5px; }
.fill.good { background: var(--good); }
.fill.warn { background: #c08324; }
.fill.bad { background: var(--bad); }
.fill.neutral { background: var(--line-2); }
.fill.accent { background: var(--accent); }

/* --- tags --------------------------------------------------------------- */

.tag {
  display: inline-block;
  padding: 1px 7px;
  border-radius: 999px;
  border: 1px solid var(--line-2);
  background: var(--surface-2);
  color: var(--ink-2);
  font-size: 11.5px;
  line-height: 1.55;
  white-space: nowrap;
}
.tag.good { color: var(--good); background: var(--good-weak); border-color: var(--good-line); }
.tag.warn { color: var(--warn); background: var(--warn-weak); border-color: var(--warn-line); }
.tag.bad { color: var(--bad); background: var(--bad-weak); border-color: var(--bad-line); }
.tag.accent { color: var(--accent-ink); background: var(--accent-weak); border-color: #c5d3f5; }
.tag.plain { background: transparent; }
.tag.mono { font-family: var(--mono); }

/* --- tables ------------------------------------------------------------- */

table { border-collapse: collapse; width: 100%; font-size: 13px; }
caption { text-align: left; color: var(--muted); font-size: 11.5px; padding: 0 0 8px; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
thead th {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: .05em;
  color: var(--muted);
  font-weight: 600;
  background: var(--surface-2);
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
}
tbody tr:last-child td { border-bottom: 0; }
td.num, th.num { text-align: right; }
.table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
.table-wrap table { min-width: 640px; }

/* --- findings ----------------------------------------------------------- */

.findings { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.finding {
  display: flex;
  flex-direction: column;
  gap: 6px;
  text-align: left;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  padding: 14px 16px;
  font: inherit;
  color: inherit;
  cursor: pointer;
}
.finding:hover { border-color: var(--line-2); box-shadow: var(--shadow-sm); }
.finding .count { font-size: 21px; font-weight: 640; letter-spacing: -.02em; }
.finding .count span { font-size: 13px; font-weight: 500; color: var(--muted); }
.finding h3 { font-size: 13.5px; }
.finding p { font-size: 12.5px; color: var(--ink-2); margin: 0; }
.finding .action { margin-top: auto; padding-top: 8px; font-size: 12.5px; color: var(--accent); font-weight: 560; }

/* --- accuracy ----------------------------------------------------------- */

.compare { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 18px; }
.compare-card {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  padding: 16px;
}
.compare-card .value { font-size: 34px; font-weight: 650; letter-spacing: -.025em; line-height: 1.1; }
.compare-card .who { font-size: 13px; font-weight: 600; }
.compare-card .detail { font-size: 12px; color: var(--muted); margin-top: 4px; }
.compare-card.final { border-color: #c5d3f5; background: var(--accent-weak); }
.compare-arrow { color: var(--muted); font-size: 20px; text-align: center; }
.delta { font-size: 12px; font-weight: 600; }
.delta.up { color: var(--good); }
.delta.down { color: var(--bad); }
.delta.flat { color: var(--muted); }

.moves { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px 24px; }
.field-move { display: grid; grid-template-columns: minmax(0, 1fr); gap: 5px; }
.field-move .label {
  display: flex; align-items: baseline; justify-content: space-between; gap: 10px;
  font-size: 12.5px; font-weight: 560;
}
.field-move .delta { white-space: nowrap; }
.move-bars { display: grid; gap: 4px; }
.move-line { display: grid; grid-template-columns: 2.2rem 1fr 3.6rem; align-items: center; gap: 8px; font-size: 11.5px; color: var(--muted); }
.move-line .track { height: 6px; background: var(--surface-3); border-radius: 999px; overflow: hidden; }
.move-line .fill { display: block; height: 100%; border-radius: 999px; background: var(--line-2); }
.move-line.final .fill { background: var(--accent); }
.move-line .pct { text-align: right; color: var(--ink-2); }

/* --- pipeline ----------------------------------------------------------- */

.rail { display: flex; flex-wrap: wrap; gap: 6px; }
.rail button {
  font: inherit;
  font-size: 12.5px;
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--ink-2);
  border-radius: 999px;
  padding: 5px 12px;
  cursor: pointer;
}
.rail button:hover { border-color: var(--line-2); background: var(--surface-2); }
.rail button[aria-selected="true"] { background: var(--accent); border-color: var(--accent); color: #fff; }
.rail .sep { color: var(--line-2); align-self: center; font-size: 11px; }
.stage-detail { margin-top: 14px; }
.stage-detail dl { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin: 0; }
.stage-detail dt { font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); margin-bottom: 3px; }
.stage-detail dd { margin: 0; font-size: 13px; color: var(--ink-2); }
.js .stage-detail[hidden] { display: none; }

/* --- channels ----------------------------------------------------------- */

.channels { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.channel {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  padding: 14px 16px;
}
.channel.blind { border-color: #c5d3f5; }
.channel .letter {
  width: 24px; height: 24px; border-radius: 6px;
  display: grid; place-items: center;
  background: var(--surface-3); color: var(--ink-2);
  font-size: 12px; font-weight: 680;
  margin-bottom: 8px;
}
.channel.blind .letter { background: var(--accent); color: #fff; }
.channel h3 { font-size: 13.5px; }
.channel .scope { font-size: 11.5px; color: var(--muted); margin: 2px 0 8px; }
.channel p { font-size: 12.5px; color: var(--ink-2); margin: 0; }
.note {
  margin-top: 14px;
  border-left: 3px solid var(--accent);
  background: var(--accent-weak);
  padding: 10px 14px;
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  font-size: 13px;
  color: var(--ink-2);
}

/* --- dimensions / boundaries ------------------------------------------- */

.dimension { border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); padding: 14px 16px; }
.dimension h3 { font-size: 13.5px; margin-bottom: 4px; }
.dimension p { font-size: 12.5px; color: var(--ink-2); margin: 0; }
.dimension .asks { font-size: 12px; color: var(--muted); margin-top: 8px; font-family: var(--mono); }

.boundaries { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.boundary { border: 1px solid var(--line); border-left: 3px solid var(--warn-line); border-radius: var(--radius); background: var(--surface); padding: 13px 16px; }
.boundary h3 { font-size: 13px; margin-bottom: 4px; }
.boundary p { font-size: 12.5px; color: var(--ink-2); margin: 0; }

/* --- terminal / reproducibility ---------------------------------------- */

.terminal { border: 1px solid var(--line-2); border-radius: var(--radius); overflow: hidden; background: #14181f; }
.terminal-head {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 8px 12px; background: #1c222c; border-bottom: 1px solid #2a3240;
  font-size: 11.5px; color: #9aa6b8; font-family: var(--mono);
}
.terminal-body { padding: 12px; margin: 0; overflow-x: auto; }
.terminal-line { display: flex; align-items: center; gap: 8px; font-family: var(--mono); font-size: 12.5px; color: #dbe3ef; padding: 2px 0; }
.terminal-line .prompt { color: #5f6f88; user-select: none; }
.terminal-line code { flex: 1; white-space: pre; }
.copy {
  font: inherit; font-size: 11px;
  border: 1px solid #2f3947; background: #232b37; color: #aab6c8;
  border-radius: 5px; padding: 2px 8px; cursor: pointer;
  opacity: 0; transition: opacity .12s ease;
}
.terminal-line:hover .copy, .copy:focus-visible { opacity: 1; }
.copy:hover { background: #2b3542; color: #e4ebf5; }
.copy.done { color: #7fd4a8; border-color: #2f5a45; }
@media (hover: none) { .copy { opacity: 1; } }

/* --- explorer ----------------------------------------------------------- */

.explorer { border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); overflow: hidden; }
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 10px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--line);
  background: var(--surface-2);
}
.field { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.field label { font-size: 10.5px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); font-weight: 600; }
.field select, .field input {
  font: inherit;
  font-size: 13px;
  padding: 6px 9px;
  border: 1px solid var(--line-2);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--ink);
  min-width: 9.5rem;
  max-width: 100%;
}
.field select { cursor: pointer; }
.search { position: relative; flex: 1 1 15rem; min-width: 12rem; }
.search input { width: 100%; padding-left: 30px; }
.search .icon { position: absolute; left: 10px; bottom: 8px; color: var(--muted); font-size: 12px; pointer-events: none; }
.search kbd {
  position: absolute; right: 8px; bottom: 7px;
  font-family: var(--mono); font-size: 10.5px; color: var(--muted);
  border: 1px solid var(--line-2); border-radius: 4px; padding: 0 4px; background: var(--surface-2);
}
.toolbar .spacer { flex: 1 1 auto; }
.btn {
  font: inherit; font-size: 12.5px;
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  border-radius: var(--radius-sm);
  padding: 6px 11px;
  cursor: pointer;
}
.btn:hover { background: var(--surface-2); }
.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn.primary:hover { background: var(--accent-ink); }

.status-bar {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
  padding: 9px 14px; border-bottom: 1px solid var(--line);
  font-size: 12.5px; color: var(--muted);
}
.status-bar .count { color: var(--ink-2); }
.status-bar .count b { color: var(--ink); font-weight: 620; }
.chip {
  display: inline-flex; align-items: center; gap: 6px;
  border: 1px solid #c5d3f5; background: var(--accent-weak); color: var(--accent-ink);
  border-radius: 999px; padding: 2px 4px 2px 10px; font-size: 11.5px;
}
.chip button {
  border: 0; background: none; color: inherit; cursor: pointer;
  font: inherit; line-height: 1; padding: 2px 4px; border-radius: 999px; opacity: .7;
}
.chip button:hover { opacity: 1; background: rgba(47, 86, 201, .12); }

.table-scroll { max-height: 640px; overflow: auto; }
/* Separate borders rather than collapsed: sticky table cells are unreliable
   under border-collapse, and both axes of this table stick. */
.table-scroll table { min-width: 860px; border-collapse: separate; border-spacing: 0; }
.table-scroll thead th { position: sticky; top: 0; z-index: 2; }
.table-scroll th.sortable { cursor: pointer; user-select: none; }
.table-scroll th.sortable:hover { color: var(--ink-2); }
.table-scroll th .arrow { opacity: .35; font-size: 9px; margin-left: 3px; }
.table-scroll th[aria-sort="ascending"] .arrow, .table-scroll th[aria-sort="descending"] .arrow { opacity: 1; color: var(--accent); }
#rows tr { cursor: pointer; }
#rows tr:hover { background: var(--surface-2); }
#rows tr[aria-selected="true"] { background: var(--accent-weak); }
#rows td { white-space: nowrap; }
#rows td.app { white-space: normal; min-width: 11rem; }
#rows .app-name { font-weight: 560; }
#rows .app-id { display: block; font-family: var(--mono); font-size: 10.5px; color: var(--muted); }
#rows td.chev { color: var(--muted); text-align: right; width: 1.6rem; }

.empty, .error-state { padding: 46px 20px; text-align: center; }
.empty h3, .error-state h3 { font-size: 14px; margin-bottom: 4px; }
.empty p, .error-state p { font-size: 13px; color: var(--muted); margin-bottom: 12px; }

/* --- detail drawer ------------------------------------------------------ */

.backdrop {
  position: fixed; inset: 0; z-index: 50;
  background: rgba(17, 20, 25, .32);
  opacity: 0; pointer-events: none; transition: opacity .14s ease;
}
.backdrop.open { opacity: 1; pointer-events: auto; }
.drawer {
  position: fixed; top: 0; right: 0; bottom: 0; z-index: 51;
  width: min(520px, 100%);
  background: var(--surface);
  border-left: 1px solid var(--line);
  box-shadow: var(--shadow-lg);
  transform: translateX(100%);
  transition: transform .18s ease;
  display: flex; flex-direction: column;
}
.drawer.open { transform: none; }
@media (prefers-reduced-motion: reduce) { .drawer, .backdrop { transition: none; } }
.drawer-head {
  display: flex; align-items: flex-start; gap: 12px;
  padding: 14px 16px; border-bottom: 1px solid var(--line);
}
.drawer-head h2 { font-size: 16px; }
.drawer-head .sub { font-size: 12px; color: var(--muted); margin-top: 2px; }
.drawer-close {
  margin-left: auto; border: 1px solid var(--line-2); background: var(--surface);
  border-radius: var(--radius-sm); width: 28px; height: 28px; cursor: pointer;
  color: var(--ink-2); font-size: 14px; line-height: 1;
}
.drawer-close:hover { background: var(--surface-2); }
.drawer-body { overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 18px; }
.drawer-body h3 { font-size: 12px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); margin-bottom: 8px; }
.summary-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 14px; }
.summary-grid dt { font-size: 11px; color: var(--muted); }
.summary-grid dd { margin: 2px 0 0; font-size: 13px; }
.dim-row { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.field-list { display: flex; flex-direction: column; gap: 10px; }
.field-item { border: 1px solid var(--line); border-radius: var(--radius-sm); padding: 9px 11px; }
.field-item .head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.field-item .name { font-size: 12.5px; font-weight: 580; }
.field-item .vals { margin-top: 4px; display: flex; flex-wrap: wrap; gap: 4px; }
.field-item .why { margin-top: 6px; font-size: 12px; color: var(--muted); }
.evidence-item { border-top: 1px solid var(--line); padding: 10px 0; }
.evidence-item:first-child { border-top: 0; padding-top: 0; }
.evidence-item .title { font-size: 12.5px; font-weight: 560; }
.evidence-item .src { font-size: 11px; color: var(--muted); font-family: var(--mono); margin: 2px 0 4px; word-break: break-all; }
.evidence-item .claim { font-size: 12.5px; color: var(--ink-2); }
.evidence-item .supports { margin-top: 5px; display: flex; flex-wrap: wrap; gap: 4px; }
.check-row { display: flex; align-items: baseline; gap: 8px; font-size: 12.5px; padding: 5px 0; border-top: 1px solid var(--line); }
.check-row:first-child { border-top: 0; }
.check-row .who { font-weight: 560; min-width: 5.5rem; }

/* --- footer ------------------------------------------------------------- */

footer { border-top: 1px solid var(--line); padding: 26px 0 44px; color: var(--muted); font-size: 12.5px; background: var(--surface); }
footer .wrap { display: flex; flex-wrap: wrap; gap: 12px 24px; align-items: baseline; justify-content: space-between; }
.downloads { display: flex; flex-wrap: wrap; gap: 8px; }
.downloads a {
  border: 1px solid var(--line-2); border-radius: var(--radius-sm);
  padding: 5px 10px; font-size: 12.5px; color: var(--ink-2); background: var(--surface);
}
.downloads a:hover { background: var(--surface-2); text-decoration: none; border-color: var(--accent); color: var(--accent-ink); }

/* --- progressive enhancement ------------------------------------------- */

/* Anything that only makes sense with scripting is hidden until the script
   announces itself, and the static fallback is hidden once it has. */
html:not(.js) [data-js-only] { display: none !important; }
.js .no-js-only { display: none; }
/* If the projection fails to load, the static table comes back rather than
   leaving the reader with an apology and no data. */
.js.data-fallback .no-js-only { display: block; }
noscript .table-wrap { margin-top: 12px; }

/* --- responsive --------------------------------------------------------- */

@media (max-width: 980px) {
  /* The header is the first thing to run out of room; the tagline goes before
     the navigation does. */
  .brand-sub { display: none; }
  .brand-name { white-space: nowrap; }
  .app-header .wrap { gap: 14px; }
  .header-meta .hide-sm { display: none; }
}

@media (max-width: 1080px) {
  .moves { grid-template-columns: minmax(0, 1fr); }
  .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .findings { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .channels { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .hero-grid { grid-template-columns: minmax(0, 1fr); gap: 24px; }
  .grid-3 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .stage-detail dl { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 760px) {
  body { font-size: 14.5px; }
  .wrap { padding: 0 16px; }
  section { padding: 32px 0; }
  .hero h1 { font-size: 24px; }
  .brand-sub { display: none; }
  .tabs { order: 3; width: 100%; }
  .header-meta { font-size: 11px; gap: 10px; }
  .header-meta .hide-sm { display: none; }
  .kpis, .findings, .channels, .grid-3, .grid-2, .boundaries { grid-template-columns: minmax(0, 1fr); }
  .compare { grid-template-columns: minmax(0, 1fr); }
  .compare-arrow { transform: rotate(90deg); }
  .moves { grid-template-columns: minmax(0, 1fr); }
  .run-facts { grid-template-columns: minmax(0, 1fr); }
  .stage-detail dl { grid-template-columns: minmax(0, 1fr); }
  .summary-grid { grid-template-columns: minmax(0, 1fr); }
  .field select, .field input { min-width: 0; width: 100%; }
  .field { flex: 1 1 8.5rem; }
  .table-scroll { max-height: none; }
  .drawer { width: 100%; border-left: 0; }

  /* Sideways scrolling is the honest answer for seven columns on a phone, but
     the application name has to stay put or the other columns mean nothing. */
  .table-scroll table { min-width: 680px; }
  .table-scroll th, .table-scroll td { padding: 7px 8px; }
  .table-scroll thead th:first-child,
  #rows td.app {
    position: sticky;
    left: 0;
    z-index: 1;
    background: var(--surface);
    box-shadow: 1px 0 0 var(--line);
  }
  .table-scroll thead th:first-child { z-index: 3; background: var(--surface-2); }
  #rows tr:hover td.app { background: var(--surface-2); }
  #rows tr[aria-selected="true"] td.app { background: var(--accent-weak); }
}

@media (max-width: 560px) {
  /* Category is a filter and is repeated in the detail panel, so it is the
     first column to give up its space. */
  .table-scroll th:nth-child(2), .table-scroll td:nth-child(2) { display: none; }
  .table-scroll table { min-width: 560px; }
}

@media (max-width: 520px) {
  .app-header { height: auto; padding: 8px 0; }
  .app-header .wrap { flex-wrap: wrap; gap: 8px 12px; }
  .header-meta { margin-left: 0; width: 100%; }
}
"""


SCRIPT = """
/* Composio research intelligence - explorer behaviour.
   Reads the projection written next to this file and turns the server-rendered
   report into something you can interrogate. No framework, no requests. */
(function () {
  "use strict";

  var PAYLOAD_GLOBAL = "__PAYLOAD_GLOBAL__";
  var PAYLOAD_FILE = "__PAYLOAD_FILE__";
  var PAYLOAD_NAME = PAYLOAD_FILE.split("?")[0];
  var data = null;

  /* Severity orders, so sorting a column groups by meaning rather than by
     alphabet. Anything unlisted sorts after, alphabetically. */
  var ORDERS = {
    buildability: ["buildable", "buildable_with_friction", "blocked"],
    credential_access: [
      "self_serve_free", "self_serve_trial", "self_serve_paid", "admin_approval",
      "contact_sales", "partner_program", "enterprise", "self_hosted_deployment_dependent"
    ],
    mcp: ["official", "third_party", "unavailable", "not_found"],
    confidence: ["high", "medium", "low"],
    sample: ["A", "B"]
  };

  var TONE = {
    buildable: "good", buildable_with_friction: "warn", blocked: "bad",
    official: "good", third_party: "accent",
    high: "good", medium: "warn", low: "bad",
    self_serve_free: "good", self_serve_trial: "good"
  };

  var FILTERS = ["category_id", "buildability", "credential_access", "mcp", "confidence", "sample"];

  var state = {
    q: "",
    sort: "name",
    dir: "asc",
    finding: null,
    selected: null
  };
  FILTERS.forEach(function (key) { state[key] = ""; });

  var els = {};
  var lastFocus = null;

  /* --- helpers ---------------------------------------------------------- */

  function $(id) { return document.getElementById(id); }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined && text !== null) { node.textContent = String(text); }
    return node;
  }

  function human(token) {
    return token === null || token === undefined ? "-" : String(token).replace(/_/g, " ");
  }

  function pct(value) {
    return value === null || value === undefined ? "-" : (value * 100).toFixed(1) + "%";
  }

  function tone(token) { return TONE[token] || ""; }

  function tag(token, extra) {
    var node = el("span", "tag " + (extra !== undefined ? extra : tone(token)), human(token));
    return node;
  }

  function fieldLabel(name) {
    var schema = (data && data.field_schema) || [];
    for (var i = 0; i < schema.length; i++) {
      if (schema[i].field === name) { return schema[i].label; }
    }
    return human(name);
  }

  function rank(key, value) {
    var order = ORDERS[key];
    if (!order) { return -1; }
    var index = order.indexOf(value);
    return index === -1 ? order.length : index;
  }

  /* --- filtering -------------------------------------------------------- */

  function matches(app) {
    for (var i = 0; i < FILTERS.length; i++) {
      var key = FILTERS[i];
      if (state[key] && app[key] !== state[key]) { return false; }
    }
    if (state.finding && state.finding.ids.indexOf(app.id) === -1) { return false; }
    if (state.q) {
      var needle = state.q.toLowerCase();
      var haystack = [app.name, app.id, app.category, app.buildability,
        app.credential_access, app.mcp, (app.description || "")].join(" ").toLowerCase();
      if (haystack.indexOf(needle) === -1) { return false; }
    }
    return true;
  }

  function visibleApps() {
    var rows = data.apps.filter(matches);
    var key = state.sort;
    var factor = state.dir === "desc" ? -1 : 1;
    rows.sort(function (a, b) {
      var left = a[key], right = b[key];
      if (ORDERS[key]) {
        var diff = rank(key, left) - rank(key, right);
        if (diff !== 0) { return diff * factor; }
      } else {
        left = (left === null || left === undefined) ? "" : String(left).toLowerCase();
        right = (right === null || right === undefined) ? "" : String(right).toLowerCase();
        if (left < right) { return -1 * factor; }
        if (left > right) { return 1 * factor; }
      }
      return a.name.localeCompare(b.name);
    });
    return rows;
  }

  function activeFilters() {
    var chips = [];
    FILTERS.forEach(function (key) {
      if (!state[key]) { return; }
      var label = key === "category_id" ? "Category"
        : key === "credential_access" ? "Credentials"
        : key === "mcp" ? "MCP"
        : key === "sample" ? "Sample"
        : key.charAt(0).toUpperCase() + key.slice(1);
      var value = state[key];
      if (key === "category_id") {
        data.categories.forEach(function (item) { if (item.id === value) { value = item.name; } });
      }
      chips.push({ key: key, text: label + ": " + human(value) });
    });
    if (state.q) { chips.push({ key: "q", text: 'Search: "' + state.q + '"' }); }
    if (state.finding) { chips.push({ key: "finding", text: "Finding: " + state.finding.title }); }
    return chips;
  }

  /* --- rendering -------------------------------------------------------- */

  function renderRows(rows) {
    var body = els.rows;
    body.textContent = "";
    rows.forEach(function (app) {
      var tr = el("tr");
      tr.tabIndex = 0;
      tr.setAttribute("data-id", app.id);
      tr.setAttribute("role", "button");
      tr.setAttribute("aria-label", "Open details for " + app.name);
      if (state.selected === app.id) { tr.setAttribute("aria-selected", "true"); }

      var name = el("td", "app");
      name.appendChild(el("span", "app-name", app.name));
      name.appendChild(el("span", "app-id", app.id));
      tr.appendChild(name);

      tr.appendChild(el("td", null, app.category));

      var build = el("td");
      build.appendChild(tag(app.buildability));
      tr.appendChild(build);

      tr.appendChild(el("td", null, human(app.credential_access)));

      var mcp = el("td");
      mcp.appendChild(tag(app.mcp, app.mcp === "official" ? "good" : "plain"));
      tr.appendChild(mcp);

      var confidence = el("td");
      confidence.appendChild(tag(app.confidence));
      tr.appendChild(confidence);

      var sample = el("td");
      if (app.sample) { sample.appendChild(tag("Sample " + app.sample, "accent")); }
      else { sample.appendChild(el("span", "muted", "-")); }
      tr.appendChild(sample);

      tr.appendChild(el("td", "chev", "\\u203a"));
      body.appendChild(tr);
    });
  }

  function renderChips(chips) {
    var bar = els.chips;
    bar.textContent = "";
    chips.forEach(function (chip) {
      var node = el("span", "chip");
      node.appendChild(document.createTextNode(chip.text));
      var clear = el("button", null, "\\u00d7");
      clear.type = "button";
      clear.setAttribute("aria-label", "Remove filter " + chip.text);
      clear.addEventListener("click", function () { clearOne(chip.key); });
      node.appendChild(clear);
      bar.appendChild(node);
    });
  }

  function render() {
    var rows = visibleApps();
    var chips = activeFilters();

    renderRows(rows);
    renderChips(chips);

    els.count.innerHTML = "";
    els.count.appendChild(el("b", null, rows.length));
    els.count.appendChild(document.createTextNode(
      " of " + data.apps.length + " application" + (data.apps.length === 1 ? "" : "s")
    ));

    els.clear.hidden = chips.length === 0;
    els.empty.hidden = rows.length !== 0;
    els.tableScroll.hidden = rows.length === 0;

    document.querySelectorAll("th.sortable").forEach(function (th) {
      var key = th.getAttribute("data-sort");
      th.setAttribute("aria-sort", key === state.sort
        ? (state.dir === "asc" ? "ascending" : "descending") : "none");
      var arrow = th.querySelector(".arrow");
      if (arrow) { arrow.textContent = key === state.sort && state.dir === "desc" ? "\\u25bc" : "\\u25b2"; }
    });

    document.querySelectorAll("[data-filter-value]").forEach(function (node) {
      var key = node.getAttribute("data-filter-key");
      var value = node.getAttribute("data-filter-value");
      node.setAttribute("aria-pressed", state[key] === value ? "true" : "false");
    });

    syncUrl();
  }

  /* --- URL state -------------------------------------------------------- */

  function syncUrl() {
    var parts = [];
    FILTERS.forEach(function (key) {
      if (state[key]) { parts.push(key + "=" + encodeURIComponent(state[key])); }
    });
    if (state.q) { parts.push("q=" + encodeURIComponent(state.q)); }
    if (state.finding) { parts.push("finding=" + encodeURIComponent(state.finding.key)); }
    if (state.sort !== "name" || state.dir !== "asc") {
      parts.push("sort=" + state.sort + ":" + state.dir);
    }
    var current = window.location.hash || "";
    if (!parts.length && current.indexOf("#dataset?") !== 0) {
      /* Nothing is filtered and nothing was: leave the reader's URL alone. */
      return;
    }
    var hash = parts.length ? "#dataset?" + parts.join("&") : "#dataset";
    if (current !== hash) {
      history.replaceState(null, "", window.location.pathname + window.location.search + hash);
    }
  }

  function readUrl() {
    var hash = window.location.hash || "";
    var at = hash.indexOf("?");
    if (at === -1) { return false; }
    var applied = false;
    hash.slice(at + 1).split("&").forEach(function (pair) {
      var bits = pair.split("=");
      var key = bits[0];
      var value = decodeURIComponent(bits.slice(1).join("=") || "");
      if (FILTERS.indexOf(key) !== -1) { state[key] = value; applied = true; }
      else if (key === "q") { state.q = value; applied = true; }
      else if (key === "finding") { applied = selectFinding(value, false) || applied; }
      else if (key === "sort") {
        var sort = value.split(":");
        state.sort = sort[0] || "name";
        state.dir = sort[1] === "desc" ? "desc" : "asc";
        applied = true;
      }
    });
    return applied;
  }

  function syncControls() {
    FILTERS.forEach(function (key) {
      var control = els.controls[key];
      if (control) { control.value = state[key]; }
    });
    els.search.value = state.q;
  }

  /* --- actions ---------------------------------------------------------- */

  function clearOne(key) {
    if (key === "q") { state.q = ""; els.search.value = ""; }
    else if (key === "finding") { state.finding = null; markFindings(); }
    else { state[key] = ""; }
    syncControls();
    render();
  }

  function clearAll() {
    FILTERS.forEach(function (key) { state[key] = ""; });
    state.q = "";
    state.finding = null;
    markFindings();
    syncControls();
    render();
  }

  function selectFinding(key, scroll) {
    var found = null;
    data.findings.forEach(function (item) { if (item.key === key) { found = item; } });
    if (!found) { return false; }
    if (state.finding && state.finding.key === key) {
      state.finding = null;
    } else {
      FILTERS.forEach(function (name) { state[name] = ""; });
      state.q = "";
      state.finding = { key: found.key, title: found.title, ids: found.app_ids };
    }
    markFindings();
    syncControls();
    if (scroll) {
      render();
      $("dataset").scrollIntoView({ behavior: "smooth", block: "start" });
    }
    return true;
  }

  function markFindings() {
    document.querySelectorAll("[data-finding]").forEach(function (node) {
      var active = state.finding && state.finding.key === node.getAttribute("data-finding");
      node.setAttribute("aria-pressed", active ? "true" : "false");
      var action = node.querySelector(".action");
      if (action) {
        action.textContent = active
          ? "Showing these applications - click to clear"
          : "View applications \\u2192";
      }
    });
  }

  function applyFilter(key, value, scroll) {
    state[key] = state[key] === value ? "" : value;
    state.finding = null;
    markFindings();
    syncControls();
    render();
    if (scroll) { $("dataset").scrollIntoView({ behavior: "smooth", block: "start" }); }
  }

  /* --- detail drawer ---------------------------------------------------- */

  function appById(id) {
    var found = null;
    data.apps.forEach(function (app) { if (app.id === id) { found = app; } });
    return found;
  }

  function definition(term, value) {
    var wrap = document.createDocumentFragment();
    wrap.appendChild(el("dt", null, term));
    var dd = el("dd");
    if (typeof value === "string" || typeof value === "number") { dd.textContent = value; }
    else if (value) { dd.appendChild(value); }
    wrap.appendChild(dd);
    return wrap;
  }

  function block(title, body) {
    var section = el("section");
    section.appendChild(el("h3", null, title));
    section.appendChild(body);
    return section;
  }

  function summaryBlock(app) {
    var dl = el("dl", "summary-grid");
    dl.appendChild(definition("Buildability", tag(app.buildability)));
    dl.appendChild(definition("Credentials", human(app.credential_access)));
    dl.appendChild(definition("MCP", human(app.mcp)));
    dl.appendChild(definition("Confidence", tag(app.confidence)));
    dl.appendChild(definition("API breadth", human(app.api_breadth)));
    dl.appendChild(definition("Evidence items", app.evidence_count));
    dl.appendChild(definition("Sample", app.sample ? "Sample " + app.sample : "Not sampled"));
    dl.appendChild(definition("Verification", human(app.verification_status)));
    return dl;
  }

  function dimensionsBlock(app) {
    if (!app.dimensions) { return null; }
    var wrap = el("div");
    var row = el("div", "dim-row");
    [["Technical", app.dimensions.technical],
     ["Credential", app.dimensions.credential],
     ["Commercial", app.dimensions.commercial]].forEach(function (pair) {
      var toneName = pair[1] === "pass" ? "good" : pair[1] === "fail" ? "bad"
        : pair[1] === "friction" ? "warn" : "";
      row.appendChild(tag(pair[0] + ": " + human(pair[1]), toneName));
    });
    wrap.appendChild(row);
    var reason = null;
    app.fields.forEach(function (field, index) {
      if (data.field_schema[index].field === "buildability" && field.rationale) {
        reason = field.rationale;
      }
    });
    if (reason) { wrap.appendChild(el("p", "muted", reason)); }
    return wrap;
  }

  function fieldsBlock(app) {
    var list = el("div", "field-list");
    app.fields.forEach(function (field, index) {
      var schema = data.field_schema[index];
      var item = el("div", "field-item");
      var head = el("div", "head");
      head.appendChild(el("span", "name", schema.label));
      if (field.status !== "resolved") { head.appendChild(tag(field.status, "warn")); }
      if (field.reconciled) { head.appendChild(tag("reconciled", "accent")); }
      item.appendChild(head);

      var values = el("div", "vals");
      (field.values || []).forEach(function (value) { values.appendChild(tag(value, "plain")); });
      if (!field.values || !field.values.length) {
        values.appendChild(el("span", "muted", human(field.status)));
      }
      item.appendChild(values);

      if (field.rationale) { item.appendChild(el("p", "why", field.rationale)); }
      if (field.evidence_ids && field.evidence_ids.length) {
        var cites = el("p", "why");
        cites.textContent = "Cites: " + field.evidence_ids.map(function (id) {
          return id.split("::")[1] || id;
        }).join(", ");
        item.appendChild(cites);
      }
      list.appendChild(item);
    });
    return list;
  }

  function evidenceBlock(app) {
    var list = el("div");
    app.evidence.forEach(function (item) {
      var node = el("div", "evidence-item");
      var link = el("a", "title", item.title);
      link.href = item.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      node.appendChild(link);
      node.appendChild(el("div", "src", item.url));
      node.appendChild(el("p", "claim", item.claim));
      var supports = el("div", "supports");
      supports.appendChild(tag(human(item.type), "plain"));
      supports.appendChild(tag(item.retrieval, "plain"));
      item.supports.forEach(function (field) { supports.appendChild(tag(fieldLabel(field), "plain")); });
      node.appendChild(supports);
      list.appendChild(node);
    });
    return list;
  }

  function verificationBlock(app) {
    if (!app.verification.length && !app.reconciliation.length) { return null; }
    var wrap = el("div");
    app.verification.forEach(function (run) {
      var row = el("div", "check-row");
      row.appendChild(el("span", "who", human(run.channel)));
      var summary = [];
      if (run.checked) {
        summary.push(run.checked + (run.checked === 1 ? " field checked" : " fields checked"));
      }
      if (run.evidence_checked) {
        summary.push(run.evidence_valid + "/" + run.evidence_checked + " citations valid");
      }
      if (run.discrepancies.length) {
        summary.push("disagrees on " + run.discrepancies.map(fieldLabel).join(", "));
      } else if (run.checked) {
        summary.push("no disagreement");
      }
      if (run.reviewer) { summary.push("reviewer: " + run.reviewer); }
      row.appendChild(el("span", null, summary.join(" \\u00b7 ")));
      wrap.appendChild(row);
    });
    app.reconciliation.forEach(function (decision) {
      if (decision.outcome === "confirmed") { return; }
      var row = el("div", "check-row");
      row.appendChild(el("span", "who", fieldLabel(decision.field)));
      var text = human(decision.outcome) + " \\u2192 "
        + ((decision.value && decision.value.length) ? decision.value.map(human).join(", ") : human(decision.status));
      if (decision.decided_by) { text += " (" + decision.decided_by + ")"; }
      row.appendChild(el("span", null, text));
      wrap.appendChild(row);
    });
    return wrap;
  }

  function openApp(id) {
    var app = appById(id);
    if (!app) { return; }
    state.selected = id;
    lastFocus = document.activeElement;

    els.drawerTitle.textContent = app.name;
    var sub = el("span");
    sub.appendChild(document.createTextNode(app.category + " \\u00b7 "));
    var link = el("a", null, app.id);
    link.href = app.homepage;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    sub.appendChild(link);
    els.drawerSub.textContent = "";
    els.drawerSub.appendChild(sub);

    var body = els.drawerBody;
    body.textContent = "";
    if (app.description) { body.appendChild(el("p", "prose", app.description)); }
    body.appendChild(block("Summary", summaryBlock(app)));
    var dims = dimensionsBlock(app);
    if (dims) { body.appendChild(block("Buildability assessment", dims)); }
    var checks = verificationBlock(app);
    if (checks) { body.appendChild(block("Verification", checks)); }
    body.appendChild(block("Researched fields", fieldsBlock(app)));
    body.appendChild(block("Evidence (" + app.evidence.length + ")", evidenceBlock(app)));

    els.drawer.classList.add("open");
    els.drawer.setAttribute("aria-hidden", "false");
    els.backdrop.classList.add("open");
    els.drawerClose.focus();
    body.scrollTop = 0;
    render();
  }

  function closeDrawer() {
    if (!els.drawer.classList.contains("open")) { return; }
    els.drawer.classList.remove("open");
    els.drawer.setAttribute("aria-hidden", "true");
    els.backdrop.classList.remove("open");
    state.selected = null;
    render();
    if (lastFocus && lastFocus.focus) { lastFocus.focus(); }
  }

  /* --- pipeline --------------------------------------------------------- */

  function wirePipeline() {
    var buttons = document.querySelectorAll("[data-stage]");
    if (!buttons.length) { return; }
    document.querySelectorAll(".stage-detail").forEach(function (panel, index) {
      panel.hidden = index !== 0;
    });
    buttons.forEach(function (button, index) {
      button.setAttribute("aria-selected", index === 0 ? "true" : "false");
      button.addEventListener("click", function () {
        var key = button.getAttribute("data-stage");
        buttons.forEach(function (other) {
          other.setAttribute("aria-selected", other === button ? "true" : "false");
        });
        document.querySelectorAll(".stage-detail").forEach(function (panel) {
          panel.hidden = panel.getAttribute("data-stage-panel") !== key;
        });
      });
    });
  }

  /* --- clipboard -------------------------------------------------------- */

  function wireCopy() {
    document.querySelectorAll("[data-copy]").forEach(function (button) {
      button.addEventListener("click", function () {
        var text = button.getAttribute("data-copy");
        var done = function () {
          var original = button.textContent;
          button.textContent = "Copied";
          button.classList.add("done");
          window.setTimeout(function () {
            button.textContent = original;
            button.classList.remove("done");
          }, 1200);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done, function () { fallbackCopy(text, done); });
        } else {
          fallbackCopy(text, done);
        }
      });
    });
  }

  function fallbackCopy(text, done) {
    var area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    try { document.execCommand("copy"); done(); } catch (error) { /* clipboard unavailable */ }
    document.body.removeChild(area);
  }

  /* --- section navigation ----------------------------------------------- */

  function wireNav() {
    var links = Array.prototype.slice.call(document.querySelectorAll(".tabs a"));
    if (!links.length || !window.IntersectionObserver) { return; }
    var sections = links
      .map(function (link) { return document.querySelector(link.getAttribute("href")); })
      .filter(Boolean);
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) { return; }
        links.forEach(function (link) {
          if (link.getAttribute("href") === "#" + entry.target.id) {
            link.setAttribute("aria-current", "true");
          } else {
            link.removeAttribute("aria-current");
          }
        });
      });
    }, { rootMargin: "-40% 0px -55% 0px" });
    sections.forEach(function (section) { observer.observe(section); });
  }

  /* --- boot ------------------------------------------------------------- */

  function wireExplorer() {
    FILTERS.forEach(function (key) {
      var control = $("filter-" + key.replace(/_/g, "-"));
      if (!control) { return; }
      els.controls[key] = control;
      control.addEventListener("change", function () {
        state[key] = control.value;
        state.finding = null;
        markFindings();
        render();
      });
    });

    els.search.addEventListener("input", function () {
      state.q = els.search.value.trim();
      render();
    });

    els.clear.addEventListener("click", clearAll);
    $("empty-clear").addEventListener("click", clearAll);

    document.querySelectorAll("th.sortable").forEach(function (th) {
      th.addEventListener("click", function () {
        var key = th.getAttribute("data-sort");
        if (state.sort === key) { state.dir = state.dir === "asc" ? "desc" : "asc"; }
        else { state.sort = key; state.dir = "asc"; }
        render();
      });
    });

    els.rows.addEventListener("click", function (event) {
      var row = event.target.closest("tr[data-id]");
      if (row) { openApp(row.getAttribute("data-id")); }
    });
    els.rows.addEventListener("keydown", function (event) {
      if (event.key !== "Enter" && event.key !== " ") { return; }
      var row = event.target.closest("tr[data-id]");
      if (row) { event.preventDefault(); openApp(row.getAttribute("data-id")); }
    });

    els.drawerClose.addEventListener("click", closeDrawer);
    els.backdrop.addEventListener("click", closeDrawer);

    document.querySelectorAll("[data-finding]").forEach(function (card) {
      card.addEventListener("click", function () {
        selectFinding(card.getAttribute("data-finding"), true);
      });
    });

    document.querySelectorAll("[data-filter-value]").forEach(function (node) {
      node.addEventListener("click", function () {
        applyFilter(node.getAttribute("data-filter-key"), node.getAttribute("data-filter-value"), true);
      });
    });

    /* While the drawer is open it owns the keyboard: tabbing must not walk off
       into the table behind it. */
    els.drawer.addEventListener("keydown", function (event) {
      if (event.key !== "Tab") { return; }
      var focusable = els.drawer.querySelectorAll(
        'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (!focusable.length) { return; }
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") { closeDrawer(); return; }
      if (event.key === "/" && document.activeElement !== els.search) {
        event.preventDefault();
        els.search.focus();
        els.search.select();
      }
    });
  }

  function showError(message) {
    var panel = $("explorer-error");
    if (!panel) { return; }
    panel.hidden = false;
    var detail = panel.querySelector("[data-error-detail]");
    if (detail) {
      detail.textContent = message + " The full table is below, and the dataset "
        + "is still downloadable as JSON and CSV.";
    }
    var shell = $("explorer-shell");
    if (shell) { shell.hidden = true; }
    document.documentElement.classList.add("data-fallback");
  }

  function clearError() {
    $("explorer-error").hidden = true;
    $("explorer-shell").hidden = false;
    document.documentElement.classList.remove("data-fallback");
  }

  function start() {
    data = window[PAYLOAD_GLOBAL];
    if (!data || !data.apps || !data.apps.length) {
      showError("The dataset projection (" + PAYLOAD_NAME + ") did not load, so the explorer cannot be built.");
      return false;
    }
    clearError();

    els.rows = $("rows");
    els.chips = $("chips");
    els.count = $("result-count");
    els.clear = $("clear-filters");
    els.empty = $("empty-state");
    els.tableScroll = $("table-scroll");
    els.search = $("search");
    els.drawer = $("drawer");
    els.drawerBody = $("drawer-body");
    els.drawerTitle = $("drawer-title");
    els.drawerSub = $("drawer-sub");
    els.drawerClose = $("drawer-close");
    els.backdrop = $("backdrop");
    els.controls = {};

    wireExplorer();
    wirePipeline();
    wireCopy();
    wireNav();
    markFindings();
    readUrl();
    syncControls();
    render();
    return true;
  }

  function boot() {
    if (!start()) {
      var retry = document.querySelector("[data-retry]");
      if (retry) {
        retry.addEventListener("click", function () {
          /* The payload is a sibling script: re-request it, then rebuild. */
          var script = document.createElement("script");
          script.src = PAYLOAD_FILE + (PAYLOAD_FILE.indexOf("?") === -1 ? "?" : "&")
            + "retry=" + Date.now();
          script.onload = start;
          script.onerror = function () {
            showError("Retry failed: " + PAYLOAD_NAME + " is still unavailable.");
          };
          document.head.appendChild(script);
        });
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
"""


def script(payload_global: str, payload_file: str) -> str:
    """The client script, bound to the names the renderer actually wrote."""
    return (
        SCRIPT.replace("__PAYLOAD_GLOBAL__", payload_global)
        .replace("__PAYLOAD_FILE__", payload_file)
    )
