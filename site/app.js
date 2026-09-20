/* Composio research intelligence - explorer behaviour.
   Reads the projection written next to this file and turns the server-rendered
   report into something you can interrogate. No framework, no requests. */
(function () {
  "use strict";

  var PAYLOAD_GLOBAL = "COMPOSIO_RESEARCH";
  var PAYLOAD_FILE = "dataset.js?v=12b21759a526dcd4";
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

      tr.appendChild(el("td", "chev", "\u203a"));
      body.appendChild(tr);
    });
  }

  function renderChips(chips) {
    var bar = els.chips;
    bar.textContent = "";
    chips.forEach(function (chip) {
      var node = el("span", "chip");
      node.appendChild(document.createTextNode(chip.text));
      var clear = el("button", null, "\u00d7");
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
      if (arrow) { arrow.textContent = key === state.sort && state.dir === "desc" ? "\u25bc" : "\u25b2"; }
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
          : "View applications \u2192";
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
      row.appendChild(el("span", null, summary.join(" \u00b7 ")));
      wrap.appendChild(row);
    });
    app.reconciliation.forEach(function (decision) {
      if (decision.outcome === "confirmed") { return; }
      var row = el("div", "check-row");
      row.appendChild(el("span", "who", fieldLabel(decision.field)));
      var text = human(decision.outcome) + " \u2192 "
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
    sub.appendChild(document.createTextNode(app.category + " \u00b7 "));
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
