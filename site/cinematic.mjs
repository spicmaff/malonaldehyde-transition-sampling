/* Progressive inspection of static, source-derived figures. No new fetch or solver. */
const page = document.getElementById('optimization');
const atlas = document.getElementById('opt-coefficient-atlas');
const groups = [...document.querySelectorAll('[data-cin-group-select]')];
const steps = [...document.querySelectorAll('[data-cin-step]')];
const ready = () => document.body.dataset.optimizationReady === 'true';
let initialized = false;
const original = atlas ? ['cin-atlas-count','cin-atlas-label','cin-atlas-detail'].map(id => document.getElementById(id).textContent) : [];
function selectGroup(key) {
  if (!ready() || !atlas) return false;
  const group = [...atlas.querySelectorAll('[data-cin-group]')].find(el => el.dataset.cinGroup === key);
  if (key !== 'all' && !group) return false;
  atlas.dataset.selection = key;
  groups.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.cinGroupSelect === key)));
  const values = group ? [group.dataset.cinCount, group.dataset.cinLabel, group.dataset.cinDetail] : original;
  ['cin-atlas-count','cin-atlas-label','cin-atlas-detail'].forEach((id, i) => { document.getElementById(id).textContent = values[i]; });
  return true;
}
function syncState() {
  const selected = document.getElementById('opt-selection')?.dataset.optSelected;
  steps.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.cinStep === selected)));
  if (page) page.dataset.cinState = selected || 'S0';
}
function initialize() {
  const enabled = ready();
  [...groups, ...steps].forEach(b => { b.disabled = !enabled; });
  if (!enabled || initialized) return;
  initialized = true;
  groups.forEach(b => b.addEventListener('click', () => selectGroup(b.dataset.cinGroupSelect)));
  steps.forEach(b => b.addEventListener('click', () => window.optimizationExhibit?.selectState(b.dataset.cinStep)));
  atlas?.addEventListener('keydown', e => {
    const at = groups.indexOf(e.target);
    if (at < 0 || !['ArrowLeft','ArrowRight','Home','End'].includes(e.key)) return;
    e.preventDefault();
    const index = e.key === 'Home' ? 0 : e.key === 'End' ? groups.length - 1 : (at + (e.key === 'ArrowLeft' ? -1 : 1) + groups.length) % groups.length;
    groups[index].focus(); selectGroup(groups[index].dataset.cinGroupSelect);
  });
  syncState();
}
if (page && atlas) {
  const readiness = new MutationObserver(initialize);
  readiness.observe(document.body, {attributes: true, attributeFilter: ['data-optimization-ready']});
  const selection = new MutationObserver(syncState);
  selection.observe(document.getElementById('opt-selection'), {attributes: true, attributeFilter: ['data-opt-selected']});
  initialize();
  window.cinematicExhibit = {selectGroup, getState: () => ({ready: ready(), group: atlas.dataset.selection, selectedState: page.dataset.cinState})};
}
// Keep keyboard navigation on the current chapter, instead of routing #main to Overview.
document.querySelector('.skip-link')?.addEventListener('click', e => {
  e.preventDefault();
  const target = document.querySelector('[data-page].active') || document.getElementById('main');
  if (!target) return;
  if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1');
  target.focus({preventScroll: true}); target.scrollIntoView({behavior: 'instant', block: 'start'});
});
// The visible label is the accessible name, including after an animation stops.
document.querySelectorAll('button.play-button').forEach(button => {
  const sync = () => button.setAttribute('aria-label', button.textContent.trim());
  new MutationObserver(sync).observe(button, {childList: true, subtree: true, characterData: true}); sync();
});
// Keep the active chapter visible in the narrow horizontal menu without moving
// the document or stealing focus. Returning from Optimization must reveal Overview.
const navigation = document.querySelector('.nav-shell nav');
let navigationFrame = 0;
function revealActiveChapter() {
  cancelAnimationFrame(navigationFrame);
  navigationFrame = requestAnimationFrame(() => {
    navigationFrame = 0;
    revealNavigationLink(navigation?.querySelector('[aria-current="page"]'));
  });
}
function revealNavigationLink(current) {
  if (!current || !navigation?.contains(current)) return;
  const box = navigation.getBoundingClientRect(), link = current.getBoundingClientRect();
  if (link.left < box.left + 8) navigation.scrollLeft -= box.left + 8 - link.left;
  else if (link.right > box.right - 8) navigation.scrollLeft += link.right - box.right + 8;
}
if (navigation) {
  // Native Tab scrolling can leave the end of a partly visible label clipped.
  // Reveal that focused link horizontally without moving focus or the document.
  navigation.addEventListener('focusin', event => {
    const link = event.target.closest('a[data-route]');
    if (link) revealNavigationLink(link);
  });
  new MutationObserver(revealActiveChapter).observe(navigation, {subtree: true, attributes: true, attributeFilter: ['aria-current']});
  window.addEventListener('resize', revealActiveChapter);
  revealActiveChapter();
}
// Motion only decorates the heading; recorded numerical positions never interpolate.
document.documentElement.classList.add('cin-ready');
if (new URLSearchParams(location.search).has('still')) document.documentElement.classList.add('cin-still');

// Reading position is a quiet location cue. It never changes hash, focus or scroll.
const chapterMap = page?.querySelector('.cin-chapter-map');
const chapterLinks = chapterMap ? [...chapterMap.querySelectorAll('a[href^="#opt-"]')] : [];
const chapters = chapterLinks.map(link => document.getElementById(link.hash.slice(1)));
const chapterHeader = document.querySelector('.site-header');
let readingFrame = 0;
function updateReadingPosition() {
  readingFrame = 0;
  if (!page?.classList.contains('active') || !chapterMap || document.hidden) return;
  const headerHeight = Math.ceil(chapterHeader?.getBoundingClientRect().height || 0);
  const guideHeight = Math.ceil(chapterMap.getBoundingClientRect().height);
  const sticky = matchMedia('(min-width: 1101px)').matches;
  const documentPadding = parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop) || 0;
  for (const [key, value] of [['--cin-header-height', headerHeight], ['--cin-guide-height', guideHeight],
      ['--cin-guide-offset', sticky ? guideHeight : 0], ['--cin-document-scroll-padding', documentPadding]]) {
    const next = value + 'px';
    if (page.style.getPropertyValue(key) !== next) page.style.setProperty(key, next);
  }
  const readingLine = Math.max(documentPadding, headerHeight + (sticky ? guideHeight : 0) + 18) + 6;
  let active = -1;
  chapters.forEach((section, i) => { if (section && section.getBoundingClientRect().top <= readingLine) active = i; });
  chapterLinks.forEach((link, i) => {
    if (i === active) link.setAttribute('aria-current', 'location');
    else link.removeAttribute('aria-current');
  });
  const label = document.getElementById('cin-reading-position');
  const next = active < 0 ? 'Six connected questions' :
    String(active + 1).padStart(2, '0') + ' / ' + String(chapterLinks.length).padStart(2, '0') +
    ' · ' + chapterLinks[active].textContent.replace(/^\d+\s*·\s*/, '').trim();
  if (label && label.textContent !== next) label.textContent = next;
  chapterMap.dataset.readingSection = active < 0 ? '' : chapters[active].id;
}
function scheduleReadingPosition() {
  if (!readingFrame) readingFrame = requestAnimationFrame(updateReadingPosition);
}
if (chapterMap) {
  window.addEventListener('scroll', scheduleReadingPosition, {passive: true});
  window.addEventListener('resize', scheduleReadingPosition);
  document.addEventListener('visibilitychange', scheduleReadingPosition);
  new MutationObserver(scheduleReadingPosition).observe(page, {attributes: true, attributeFilter: ['class']});
  if (typeof ResizeObserver !== 'undefined') {
    const sizes = new ResizeObserver(scheduleReadingPosition);
    if (chapterHeader) sizes.observe(chapterHeader);
    sizes.observe(chapterMap);
  }
  scheduleReadingPosition();
}
