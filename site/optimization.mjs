/* Saved-state inspection only. All numbers originate in the versioned payload. */
const $ = id => document.getElementById(id);
const page = $('optimization');
const reduce = matchMedia('(prefers-reduced-motion: reduce)');
let payload = null;
let initialized = false;
let selected = 'S0';
let playing = false;
let timer = 0;
let anchorFrame = 0;
let navResizeFrame = 0;
let routeRevision = 0;
let readinessWatch = null;
const interval = 1350;
const controlIds = ['opt-play', 'opt-reset', 'opt-prev', 'opt-next'];
const sourceAnchor = id => 'opt-source-' + id.replace(/[^A-Za-z0-9_-]/g, '-');
const onPage = () => page?.classList.contains('active') || !document.documentElement.classList.contains('js-ready');
const readerOrder = () => payload ? payload.theory.main4500.states.map(s => s.id) : [];
const nativeOrder = () => payload ? [...payload.theory.main4500.native_order] : [];
const readyMessage = () => `Saved-data inspection is ready. ${readerOrder().length} state records; ${payload.theory.main4500.states.filter(s => !s.native_trajectory).length} explicitly separate diagnostic branches. All values and source tables remain available below.`;

function currentHash() {
  try { return decodeURIComponent(location.hash.replace(/^#/, '').split('?')[0]); }
  catch { return ''; }
}

function revealNavigationLink() {
  if (!onPage()) return;
  const nav = document.querySelector('header nav') || document.querySelector('nav');
  const link = document.querySelector('[data-route="optimization"]');
  if (!nav || !link) return;
  const a = link.getBoundingClientRect(), n = nav.getBoundingClientRect();
  if (a.right > n.right || a.left < n.left) nav.scrollLeft += a.left - n.left - 12;
}

// This handler is independent of the JSON request. Static deep links keep working
// if the enhancement fails, and run after the legacy app's hash scroll-to-top.
function followAnchor() {
  const raw = currentHash();
  if (raw !== 'optimization' && !raw.startsWith('opt-')) return;
  revealNavigationLink();
  if (raw === 'optimization') return;
  const target = $(raw);
  if (!target || !page?.contains(target)) return;
  for (let node = target.parentElement; node && node !== page; node = node.parentElement) {
    if (node.tagName === 'DETAILS') node.open = true;
  }
  if (target.tagName === 'DETAILS') target.open = true;
  if (!target.hasAttribute('tabindex') && !target.matches('a,button,input,select,textarea,summary')) {
    target.setAttribute('tabindex', '-1');
  }
  target.focus({preventScroll: true});
  target.scrollIntoView({behavior: 'auto', block: 'start'});
}

function scheduleAnchor() {
  const revision = ++routeRevision;
  if (anchorFrame) cancelAnimationFrame(anchorFrame);
  anchorFrame = requestAnimationFrame(() => {
    anchorFrame = requestAnimationFrame(() => {
      anchorFrame = 0;
      if (revision === routeRevision) followAnchor();
    });
  });
}

function setControls(enabled) {
  for (const id of controlIds) if ($(id)) $(id).disabled = !enabled;
  page?.querySelectorAll('[data-opt-select]').forEach(button => { button.disabled = !enabled; });
}

function stop() {
  clearTimeout(timer);
  timer = 0;
  playing = false;
  const button = $('opt-play');
  if (button) {
    button.textContent = 'Play native sequence';
    button.setAttribute('aria-pressed', 'false');
  }
}

function selectState(id, options = {}) {
  if (!initialized || !payload) return false;
  const state = payload.theory.main4500.states.find(s => s.id === id);
  if (!state) return false;
  if (!options.fromPlayback) stop();
  selected = state.id;
  const branch = !state.native_trajectory;
  const role = branch ? `Diagnostic branch from ${id === 'S1c' ? 'S1' : 'S2'}` : 'Native sequence';
  $('opt-selected-role').textContent = `${role} · ${id}`;
  $('opt-selected-title').textContent = state.label;
  $('opt-selected-value').textContent = state.native_J === null ? 'Not measured' : String(state.native_J);
  $('opt-selected-scope').textContent = state.scope;
  $('opt-selected-evidence').textContent = state.evidence_status;
  $('opt-selected-status').textContent = state.status;
  const link = document.createElement('a');
  link.className = 'opt-source-link';
  link.href = '#' + sourceAnchor(state.source_id);
  link.textContent = state.source_id + ' ↗';
  $('opt-selected-source').replaceChildren(link);
  $('opt-selected-source-field').textContent = 'Field: ' + state.source_field;
  $('opt-selected-live').textContent = state.separate_live_objective_parity
    ? 'Separate live objective parity: verified.'
    : (state.native_J === null
      ? 'No independent objective measurement. No plotted position.'
      : (branch ? 'New derived copy; detached physical evaluation. No historical byte identity claimed.' : 'Saved live state; detached objective evaluation. No separate live S1 objective was measured.'));
  page.querySelectorAll('[data-opt-select]').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.optSelect === id));
  });
  page.querySelectorAll('[data-opt-row]').forEach(row => row.classList.toggle('opt-is-selected', row.dataset.optRow === id));
  page.querySelectorAll('[data-opt-state]').forEach(row => row.classList.toggle('opt-is-selected', row.dataset.optState === id));
  const order = readerOrder(), index = order.indexOf(id);
  $('opt-prev').disabled = index === 0;
  $('opt-next').disabled = index === order.length - 1;
  // Set the container's semantic selected state after its complete narrative.
  $('opt-selection').dataset.optSelected = id;
  if (options.focus) page.querySelector(`[data-opt-select="${id}"]`)?.focus({preventScroll: true});
  return true;
}

function moveReader(delta, focus = false) {
  if (!initialized) return false;
  const order = readerOrder();
  const index = Math.max(0, Math.min(order.length - 1, order.indexOf(selected) + delta));
  return selectState(order[index], {focus});
}

function reset() { return selectState(readerOrder()[0]); }
function next() { return moveReader(1); }
function previous() { return moveReader(-1); }

function play() {
  if (!initialized || !onPage() || document.hidden) return false;
  if (playing) { stop(); return false; }
  if (reduce.matches) {
    stop();
    $('opt-load-status').textContent = 'Reduced motion is enabled. Inspect each exact state with the buttons or keyboard; the selected state is unchanged.';
    return false;
  }
  const order = nativeOrder();
  let index = order.indexOf(selected);
  if (index < 0 || index === order.length - 1) index = 0;
  selectState(order[index], {fromPlayback: true});
  playing = true;
  $('opt-play').textContent = 'Pause native sequence';
  $('opt-play').setAttribute('aria-pressed', 'true');
  function advance() {
    if (!playing || !onPage() || document.hidden || reduce.matches) { stop(); return; }
    index += 1;
    if (index >= order.length) { stop(); return; }
    selectState(order[index], {fromPlayback: true});
    if (index === order.length - 1) stop();
    else timer = setTimeout(advance, interval);
  }
  timer = setTimeout(advance, interval);
  return true;
}

function getState() {
  const reader = readerOrder(), native = nativeOrder();
  return {
    ready: initialized,
    interactive: initialized,
    selectedState: selected,
    selectedIndex: reader.indexOf(selected),
    nativeIndex: native.indexOf(selected),
    readerOrder: reader,
    nativeOrder: native,
    playing,
    reducedMotion: reduce.matches
  };
}

function checkPayload(data) {
  if (data?.schema !== 'proton-optimization-v1') throw new Error('Unsupported saved-data schema');
  const states = data?.theory?.main4500?.states;
  const expected = ['S0', 'S1', 'S1c', 'S2', 'S2q', 'S3', 'S4'];
  if (!Array.isArray(states) || states.map(s => s.id).join('|') !== expected.join('|')) throw new Error('Saved state identities do not match');
  if (data.theory.main4500.native_order.join('|') !== 'S0|S1|S2|S3|S4') throw new Error('Native sequence is inconsistent');
  if (!Array.isArray(data.sources) || new Set(data.sources.map(s => s.id)).size !== data.sources.length) throw new Error('Source identities are inconsistent');
  const ids = new Set(data.sources.map(s => s.id));
  for (const state of states) {
    if (!ids.has(state.source_id)) throw new Error('A state source is unavailable');
    if (state.id === 'S3') {
      if (state.native_J !== null || state.status !== 'NOT_MEASURED') throw new Error('S3 must remain unmeasured');
    } else if (!Number.isFinite(state.native_J) || state.native_J <= 0) throw new Error('A saved objective is not a positive finite value');
    if (state.native_trajectory !== data.theory.main4500.native_order.includes(state.id)) throw new Error('Diagnostic branch membership is inconsistent');
    const row = page.querySelector(`[data-opt-state="${state.id}"]`);
    if (!row || row.dataset.optSource !== state.source_id || row.dataset.optEvidence !== state.evidence_status) throw new Error('Static state evidence does not match the payload');
    const value = row.querySelector('[data-opt-value]');
    if (state.native_J === null ? !!value : !value || Number(value.dataset.optValue) !== state.native_J) throw new Error('Static objective does not match the payload');
  }
  if (data.scope.T2_executed !== false || data.scope.COV_candidate_physical_evaluated_in_recovery !== false) throw new Error('Evidence scope differs from this edition');
  if (!Number.isFinite(data.theory.COV.percent_of_total_data_loss_removed)) throw new Error('Candidate aggregate is unavailable');
}

function initialize() {
  if (initialized || !payload || document.body.dataset.ready !== 'true') return;
  initialized = true;
  setControls(true);
  page.querySelectorAll('[data-opt-select]').forEach(button => {
    button.addEventListener('click', () => selectState(button.dataset.optSelect));
  });
  $('opt-play').addEventListener('click', play);
  $('opt-reset').addEventListener('click', reset);
  $('opt-prev').addEventListener('click', previous);
  $('opt-next').addEventListener('click', next);
  const keyboard = event => {
    if (!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(event.key)) return;
    if (!event.target.closest('[data-opt-select],.opt-playback')) return;
    event.preventDefault();
    if (event.key === 'Home') selectState(readerOrder()[0], {focus: true});
    else if (event.key === 'End') selectState(readerOrder().at(-1), {focus: true});
    else moveReader(['ArrowLeft','ArrowUp'].includes(event.key) ? -1 : 1, true);
  };
  page.addEventListener('keydown', keyboard);
  page.dataset.interactive = 'true';
  document.body.dataset.optimizationReady = 'true';
  $('opt-load-status').textContent = readyMessage();
  selectState('S0');
  scheduleAnchor();
}

function fail(message) {
  stop();
  initialized = false;
  setControls(false);
  page.dataset.interactive = 'false';
  document.body.dataset.optimizationReady = 'error';
  $('opt-load-status').textContent = message;
  scheduleAnchor();
}

if (page) {
  window.optimizationExhibit = {getState, data: () => payload, selectState, play, stop, reset, next, previous};
  setControls(false);
  window.addEventListener('hashchange', () => { stop(); scheduleAnchor(); });
  window.addEventListener('resize', () => {
    if (navResizeFrame) cancelAnimationFrame(navResizeFrame);
    navResizeFrame = requestAnimationFrame(() => {
      navResizeFrame = 0;
      const raw = currentHash();
      if ((raw === 'optimization' || raw.startsWith('opt-')) && page.classList.contains('active')) revealNavigationLink();
    });
  });
  // Clicking an already-current source link must also reopen its details.
  page.addEventListener('click', event => {
    const link = event.target.closest('a[href^="#opt-"]');
    if (link && link.hash === location.hash) scheduleAnchor();
  });
  document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
  reduce.addEventListener('change', () => {
    if (reduce.matches) {
      stop();
      if (initialized) $('opt-load-status').textContent = 'Reduced motion is enabled. Exact state selection stays available; no automatic sequence is running.';
    } else if (initialized) $('opt-load-status').textContent = readyMessage();
  });
  readinessWatch = new MutationObserver(() => {
    if (document.body.dataset.ready === 'true') {
      initialize();
      scheduleAnchor();
      if (payload) readinessWatch.disconnect();
    } else if (document.body.dataset.ready === 'error') {
      fail('Interactive site data could not be loaded. The complete static optimization results, figures, source links and tables remain available.');
      readinessWatch.disconnect();
    }
  });
  readinessWatch.observe(document.body, {attributes: true, attributeFilter: ['data-ready']});
  scheduleAnchor();
  try {
    const response = await fetch('data/optimization.json');
    if (!response.ok) throw new Error('The saved aggregate file is unavailable');
    const data = await response.json();
    checkPayload(data);
    payload = data;
    if (document.body.dataset.ready === 'error') {
      fail('Interactive site data could not be loaded. The complete static optimization results, figures, source links and tables remain available.');
      readinessWatch.disconnect();
    } else {
      initialize();
      if (initialized) readinessWatch.disconnect();
    }
  } catch {
    fail('Interactive optimization data could not be loaded or did not match this saved edition. The complete static results, source links and tables remain available; state controls are disabled.');
    // Keep observing only until the legacy router finishes its initial navigation.
    if (document.body.dataset.ready) readinessWatch.disconnect();
  }
}
