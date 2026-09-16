(function(){
"use strict";

var apps = APPS;
var cats = CATS;

/* ---------------- helpers ---------------- */
function label(s){
  if(s === null || s === undefined) return null;
  return String(s).split('_').map(function(w){ return w.charAt(0).toUpperCase()+w.slice(1); }).join(' ');
}
function labelList(v){
  if(!v) return null;
  if(Array.isArray(v)) return v.map(label).join(', ');
  return label(v);
}
function mcpDisplay(a){
  if(a.mcpVal === 'official') return 'Official';
  if(a.mcpVal === 'third_party') return 'Third party';
  if(a.mcp === 'unavailable') return 'Unavailable';
  return 'Not found';
}
function mcpClass(a){
  if(a.mcpVal === 'official') return 'mcp-official';
  if(a.mcpVal === 'third_party') return 'mcp-third_party';
  return 'mcp-none';
}
function buildClass(b){ return 'build-' + (b || 'none'); }
function confClass(c){ return 'conf-' + (c || 'none'); }

var catNameById = {};
cats.forEach(function(c){ catNameById[c.category_id] = c.name; });

/* ---------------- populate filter selects ---------------- */
function fillSelect(id, values, labeler){
  var el = document.getElementById(id);
  values.forEach(function(v){
    var opt = document.createElement('option');
    opt.value = v;
    opt.textContent = labeler ? labeler(v) : v;
    el.appendChild(opt);
  });
}
fillSelect('f-cat', cats.map(function(c){return c.category_id;}), function(v){ return catNameById[v]; });
fillSelect('f-build', ['buildable','buildable_with_friction','blocked'], label);
fillSelect('f-cred', ['self_serve_free','self_serve_trial','self_serve_paid','admin_approval','enterprise','contact_sales','self_hosted_deployment_dependent'], label);
fillSelect('f-mcp', ['official','third_party','not_found'], function(v){ return v==='not_found' ? 'Not found' : label(v); });
fillSelect('f-conf', ['high','medium','low'], label);
fillSelect('f-sample', ['A','B'], function(v){ return 'Sample ' + v; });

/* ---------------- ledger (category breakdown) ---------------- */
var ledgerEl = document.getElementById('ledger');
var byCat = {};
cats.forEach(function(c){ byCat[c.category_id] = {b:0,f:0,x:0,n:0,total:0}; });
apps.forEach(function(a){
  var bucket = byCat[a.cat]; if(!bucket) return;
  bucket.total++;
  if(a.build === 'buildable') bucket.b++;
  else if(a.build === 'buildable_with_friction') bucket.f++;
  else if(a.build === 'blocked') bucket.x++;
  else bucket.n++;
});
cats.slice().sort(function(a,b){
  var pa = byCat[a.category_id], pb = byCat[b.category_id];
  return (pb.b/pb.total) - (pa.b/pa.total);
}).forEach(function(c){
  var d = byCat[c.category_id];
  var row = document.createElement('div');
  row.className = 'ledger-row';
  row.innerHTML =
    '<div><div class="ledger-name">'+c.name+'</div><div class="ledger-count">'+d.total+' apps</div></div>' +
    '<div class="ledger-bar">' +
      '<div class="ledger-seg b" data-w="'+(d.b/d.total*100)+'"></div>' +
      '<div class="ledger-seg f" data-w="'+(d.f/d.total*100)+'"></div>' +
      '<div class="ledger-seg x" data-w="'+(d.x/d.total*100)+'"></div>' +
      '<div class="ledger-seg n" data-w="'+(d.n/d.total*100)+'"></div>' +
    '</div>' +
    '<div class="ledger-count" style="text-align:right;">'+d.b+' buildable · '+d.f+' friction · '+d.x+' blocked</div>';
  ledgerEl.appendChild(row);
});

var ledgerObserver = new IntersectionObserver(function(entries){
  entries.forEach(function(entry){
    if(entry.isIntersecting){
      var segs = entry.target.querySelectorAll('.ledger-seg');
      segs.forEach(function(seg, i){
        setTimeout(function(){ seg.style.width = seg.getAttribute('data-w') + '%'; }, i * 70);
      });
      ledgerObserver.unobserve(entry.target);
    }
  });
}, {threshold:0.25});
document.querySelectorAll('.ledger-row').forEach(function(row){ ledgerObserver.observe(row); });

/* ---------------- hero stat count-up ---------------- */
function animateCount(el, target, duration){
  var startTime = null;
  var span = el.querySelector('.n');
  function step(ts){
    if(!startTime) startTime = ts;
    var progress = Math.min((ts - startTime) / duration, 1);
    var eased = 1 - Math.pow(1 - progress, 3);
    span.textContent = Math.round(eased * target);
    if(progress < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}
document.querySelectorAll('.stat-num[data-count]').forEach(function(el, i){
  var target = parseInt(el.getAttribute('data-count'), 10);
  setTimeout(function(){ animateCount(el, target, 1100); }, 120 + i * 90);
});

/* ---------------- table state ---------------- */
var state = { search:'', cat:'', build:'', cred:'', mcp:'', conf:'', sample:'', sortKey:'name', sortDir:1 };
var tbody = document.getElementById('table-body');
var countEl = document.getElementById('result-count');
var emptyEl = document.getElementById('empty-state');

function matches(a){
  if(state.cat && a.cat !== state.cat) return false;
  if(state.build && a.build !== state.build) return false;
  if(state.cred && a.cred !== state.cred) return false;
  if(state.conf && a.conf !== state.conf) return false;
  if(state.sample && a.sample !== state.sample) return false;
  if(state.mcp){
    var m = a.mcpVal || 'not_found';
    if(state.mcp === 'not_found'){ if(a.mcpVal) return false; }
    else if(m !== state.mcp) return false;
  }
  if(state.search){
    var q = state.search.toLowerCase();
    var hay = (a.name + ' ' + a.id + ' ' + a.catName).toLowerCase();
    if(hay.indexOf(q) === -1) return false;
  }
  return true;
}

function sortVal(a, key){
  if(key === 'mcp') return a.mcpVal ? (a.mcpVal === 'official' ? 0 : 1) : 2;
  if(key === 'build'){
    var order = {buildable:0, buildable_with_friction:1, blocked:2};
    return order[a.build] !== undefined ? order[a.build] : 3;
  }
  if(key === 'conf'){
    var co = {high:0, medium:1, low:2};
    return co[a.conf] !== undefined ? co[a.conf] : 3;
  }
  if(key === 'sample') return a.sample ? a.sample : 'ZZ';
  return a[key] || '';
}

function render(){
  var filtered = apps.filter(matches);
  filtered.sort(function(x,y){
    var vx = sortVal(x, state.sortKey), vy = sortVal(y, state.sortKey);
    if(vx < vy) return -1 * state.sortDir;
    if(vx > vy) return 1 * state.sortDir;
    return 0;
  });
  countEl.textContent = filtered.length;
  tbody.innerHTML = '';
  emptyEl.style.display = filtered.length ? 'none' : 'block';

  filtered.forEach(function(a){
    var tr = document.createElement('tr');
    tr.tabIndex = 0;
    tr.innerHTML =
      '<td><div class="cell-app"><span class="cell-app-name">'+a.name+'</span><span class="cell-app-id">'+a.id+'</span></div></td>' +
      '<td>'+a.catName+'</td>' +
      '<td><span class="tag '+buildClass(a.build)+'">'+ (label(a.build) || '—') +'</span></td>' +
      '<td>'+(label(a.cred) || '<span class="dim">—</span>')+'</td>' +
      '<td><span class="tag '+mcpClass(a)+'">'+mcpDisplay(a)+'</span></td>' +
      '<td><span class="tag '+confClass(a.conf)+'">'+label(a.conf)+'</span></td>' +
      '<td>'+(a.sample ? '<span class="sample-chip">Sample '+a.sample+'</span>' : '<span class="dim">—</span>')+' <span class="row-go">→</span></td>';
    tr.addEventListener('click', function(){ openDrawer(a); });
    tr.addEventListener('keydown', function(e){ if(e.key === 'Enter') openDrawer(a); });
    tbody.appendChild(tr);
  });
}

document.getElementById('search').addEventListener('input', function(e){ state.search = e.target.value; render(); });
['cat','build','cred','mcp','conf','sample'].forEach(function(k){
  document.getElementById('f-'+k).addEventListener('change', function(e){ state[k] = e.target.value; render(); });
});
document.querySelectorAll('th[data-sort]').forEach(function(th){
  th.addEventListener('click', function(){
    var key = th.getAttribute('data-sort');
    if(state.sortKey === key){ state.sortDir *= -1; }
    else { state.sortKey = key; state.sortDir = 1; }
    document.querySelectorAll('th[data-sort]').forEach(function(t){ t.classList.remove('sort-asc','sort-desc'); });
    th.classList.add(state.sortDir === 1 ? 'sort-asc' : 'sort-desc');
    render();
  });
});
document.querySelector('th[data-sort="name"]').classList.add('sort-asc');

document.addEventListener('keydown', function(e){
  if(e.key === '/' && document.activeElement.tagName !== 'INPUT'){
    e.preventDefault();
    document.getElementById('search').focus();
  }
  if(e.key === 'Escape') closeDrawer();
});

/* ---------------- drawer ---------------- */
var drawer = document.getElementById('drawer');
var backdrop = document.getElementById('backdrop');

function factRow(k, v){
  if(v === null || v === undefined || v === '') return '';
  return '<div class="fact"><div class="fact-k">'+k+'</div><div class="fact-v">'+v+'</div></div>';
}

function openDrawer(a){
  document.getElementById('d-id').textContent = a.id;
  document.getElementById('d-name').textContent = a.name;
  document.getElementById('d-vendor').textContent = (a.vendor ? a.vendor + ' · ' : '') + a.catName;

  var body = document.getElementById('drawer-body');
  var stampLabel = a.build ? label(a.build).toUpperCase() : 'NOT APPLICABLE';
  var html = '';
  html += '<div class="stamp '+(a.build||'none')+'">'+stampLabel+'</div>';
  html += '<p class="drawer-desc">'+(a.desc || 'No description resolved from the corpus.')+'</p>';
  if(a.buildRationale){
    html += '<div class="drawer-rationale"><b>Why:</b> '+a.buildRationale+'</div>';
  }

  html += '<div class="fact-grid">';
  html += factRow('Blocker', labelList(a.blocker) || 'None recorded');
  html += factRow('Access conditions', labelList(a.access) || 'None');
  html += factRow('API breadth', label(a.breadth));
  html += factRow('Interface types', labelList(a.apiTypes));
  html += factRow('Authentication', labelList(a.auth));
  html += factRow('Rate limits', label(a.rate));
  html += factRow('Webhook support', label(a.webhook));
  html += factRow('Application type', label(a.appType));
  html += '</div>';

  var links = '';
  if(a.home) links += '<a href="'+a.home+'" target="_blank" rel="noopener">Homepage ↗</a>';
  if(a.docsUrl) links += '<a href="'+a.docsUrl+'" target="_blank" rel="noopener">API docs ↗</a>';
  if(links) html += '<div class="fact-links">'+links+'</div>';

  if(a.evidence && a.evidence.length){
    html += '<h4 class="drawer-h3">Evidence ('+a.evidence.length+')</h4>';
    html += '<ul class="evidence-list">';
    a.evidence.forEach(function(e, i){
      html += '<li class="evidence-item" style="animation-delay:'+(i*45)+'ms">' +
        '<span class="evidence-num">['+(i+1)+']</span>' +
        '<span class="evidence-body">' +
          '<div class="evidence-claim">'+e.c+'</div>' +
          '<div class="evidence-src"><a href="'+e.u+'" target="_blank" rel="noopener">'+e.t+'</a> <span>· '+e.d+'</span></div>' +
        '</span>' +
      '</li>';
    });
    html += '</ul>';
  }

  if(a.verification && a.verification.length){
    html += '<h4 class="drawer-h3">Verification channels</h4>';
    a.verification.forEach(function(v){
      html += '<div class="verif-item"><div class="verif-head"><b>'+v.ch.replace('channel_','Channel ')+'</b><span class="dim">Sample '+v.sample+'</span></div>';
      if(v.notes) html += '<div class="verif-note">'+v.notes+'</div>';
      if(v.disc && v.disc.length) html += '<div class="verif-disc">Disagreed on: '+v.disc.map(label).join(', ')+'</div>';
      html += '</div>';
    });
  } else if(a.sample){
    html += '<h4 class="drawer-h3">Verification channels</h4><div class="verif-note">Selected for Sample '+a.sample+'; channel detail not attached to this projection.</div>';
  }

  body.innerHTML = html;
  drawer.classList.add('open');
  backdrop.classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeDrawer(){
  drawer.classList.remove('open');
  backdrop.classList.remove('open');
  document.body.style.overflow = '';
}
document.getElementById('d-close').addEventListener('click', closeDrawer);
backdrop.addEventListener('click', closeDrawer);

/* ---------------- nav active state on scroll ---------------- */
var navLinks = document.querySelectorAll('.masthead-nav a');
var sectionIds = ['overview','findings','dataset','methodology'];
var sections = sectionIds.map(function(id){ return document.getElementById(id); });
var navObserver = new IntersectionObserver(function(entries){
  entries.forEach(function(entry){
    if(entry.isIntersecting){
      var id = entry.target.id;
      navLinks.forEach(function(l){ l.classList.toggle('active', l.getAttribute('href') === '#'+id); });
    }
  });
}, {rootMargin:'-40% 0px -55% 0px'});
sections.forEach(function(s){ if(s) navObserver.observe(s); });

render();
})();
