const $ = (selector) => document.querySelector(selector);
const state = { lectures: [], lecture: null, page: 1, tab: 'timeline', query: '', results: [], activeSegment: null, transcriber: null };
let searchTimer;
let toastTimer;

function el(tag, className = '', text = '') {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}
function formatTime(seconds) {
  if (seconds === null || seconds === undefined) return 'No time';
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`;
}
function toast(message) {
  $('#toast').textContent = message;
  $('#toast').classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('#toast').classList.remove('show'), 3500);
}
async function api(path, options = {}) {
  const response = await fetch(path, options);
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || `Request failed (${response.status})`);
  return value;
}
function media(path) { return `/media/${state.lecture.id}/${path}`; }

async function loadLibrary() {
  const result = await api('/api/lectures');
  state.lectures = result.lectures;
  renderLibrary();
  if (!state.lecture && state.lectures.length) await openLecture(state.lectures[0].id);
}
function renderLibrary() {
  const list = $('#lectureList');
  list.replaceChildren();
  for (const item of state.lectures) {
    const button = el('button', 'lecture-item' + (state.lecture?.id === item.id ? ' active' : ''));
    const icon = el('span', 'item-icon', '▤');
    const details = el('span');
    details.append(el('b', '', item.title), el('small', '', `${item.segments} passages · ${item.pages} slides`));
    button.append(icon, details);
    button.addEventListener('click', () => openLecture(item.id));
    list.append(button);
  }
}
async function openLecture(id) {
  try {
    state.lecture = await api(`/api/lectures/${id}`);
    state.page = 1;
    state.tab = 'timeline';
    state.query = '';
    state.results = [];
    state.activeSegment = null;
    $('#searchInput').value = '';
    $('#emptyView').classList.add('hidden');
    $('#lectureView').classList.remove('hidden');
    $('#crumbTitle').textContent = state.lecture.title;
    $('#lectureTitle').textContent = state.lecture.title;
    const created = new Date(state.lecture.created_at).toLocaleDateString(undefined, {day:'numeric',month:'long',year:'numeric'});
    $('#lectureMeta').textContent = `${created}  ·  ${state.lecture.segments.length} transcript passages  ·  ${state.lecture.pages.length} slides`;
    renderLibrary(); renderPlayer(); renderSlide(); renderTimeline(); setTab('timeline');
  } catch (error) { toast(error.message); }
}
function renderPlayer() {
  const host = $('#audioHost'); host.replaceChildren();
  if (!state.lecture.audio) { host.append(el('div', 'placeholder', 'No recording was imported. Add one in a new workspace to listen here.')); return; }
  const audio = el('audio'); audio.id = 'audioPlayer'; audio.controls = true; audio.preload = 'metadata'; audio.src = media(state.lecture.audio);
  const hint = el('p', 'hint', 'Click a timestamp in the timeline to play from that moment.');
  host.append(audio, hint);
  if (state.transcriber && state.lecture.audio.endsWith('.wav') && !state.lecture.segments.length) {
    const label = state.transcriber === 'qualcomm-qnn' ? 'Transcribe with Qualcomm Whisper' : 'Transcribe locally with Whisper';
    const button = el('button', 'transcribe-button', label);
    button.addEventListener('click', async () => {
      button.disabled = true; button.textContent = 'Transcribing… this can take a few minutes';
      try { state.lecture = await api(`/api/lectures/${state.lecture.id}/transcribe`, {method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}); renderTimeline(); renderPlayer(); renderLibrary(); toast('Local transcription complete'); }
      catch (error) { toast(error.message); button.disabled = false; button.textContent = label; }
    });
    host.append(button);
  }
}
function jumpTo(seconds, segmentId = null) {
  if (seconds === null || seconds === undefined) return;
  const player = $('#audioPlayer');
  if (player) { player.currentTime = seconds; player.play().catch(() => {}); }
  state.activeSegment = segmentId;
  renderTimeline();
  if (segmentId !== null) document.getElementById(`segment-${segmentId}`)?.scrollIntoView({block:'nearest',behavior:'smooth'});
}
function renderSlide() {
  const host = $('#slideHost'); host.replaceChildren();
  const pages = state.lecture.pages;
  $('#pageIndicator').textContent = pages.length ? `${state.page} / ${pages.length}` : '—';
  $('#prevPage').disabled = state.page <= 1;
  $('#nextPage').disabled = state.page >= pages.length;
  if (!pages.length) { host.append(el('div', 'placeholder', 'Import a PDF slide deck to see and search pages here.')); $('#slideText').textContent = ''; return; }
  const page = pages[state.page - 1];
  const image = el('img'); image.src = media(page.image); image.alt = `Slide page ${page.number}`;
  host.append(image);
  $('#slideText').textContent = page.text ? page.text.slice(0, 450) : 'No selectable text detected on this page.';
}
function selectPage(page) { if (!state.lecture.pages.length) return; state.page = Math.max(1, Math.min(page, state.lecture.pages.length)); renderSlide(); }
function renderTimeline() {
  const panel = $('#timelinePanel'); panel.replaceChildren();
  const segments = state.lecture.segments;
  $('#segmentCount').textContent = `${segments.length} passages`;
  if (!segments.length) { panel.append(el('div', 'placeholder', 'No transcript yet. Import an SRT or VTT transcript with your recording to unlock the timeline.')); return; }
  for (const segment of segments) {
    const item = el('article', 'segment' + (state.activeSegment === segment.id ? ' highlight' : ''));
    item.id = `segment-${segment.id}`;
    const top = el('div', 'segment-top');
    const time = el('button', 'timestamp' + (segment.start === null ? ' untimed' : ''), segment.start === null ? `PASSAGE ${segment.id + 1}` : formatTime(segment.start));
    time.disabled = segment.start === null || !state.lecture.audio;
    time.title = time.disabled ? 'No linked audio time' : 'Play from this moment';
    time.addEventListener('click', () => jumpTo(segment.start, segment.id));
    top.append(time);
    if (state.lecture.pages.length) {
      const select = el('select', 'slide-select'); select.title = 'Link this passage to a slide';
      const empty = el('option', '', 'Link slide…'); empty.value = ''; select.append(empty);
      for (const page of state.lecture.pages) { const option = el('option', '', `Slide ${page.number}`); option.value = String(page.number); select.append(option); }
      select.value = segment.page === null ? '' : String(segment.page);
      select.addEventListener('change', async () => {
        const page = select.value ? Number(select.value) : null;
        try { await api(`/api/lectures/${state.lecture.id}/segments/${segment.id}/page`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({page})}); segment.page = page; if (page) selectPage(page); toast(page ? `Linked to slide ${page}` : 'Slide link removed'); }
        catch (error) { toast(error.message); select.value = segment.page === null ? '' : String(segment.page); }
      });
      top.append(select);
    }
    item.append(top, el('p', '', segment.text)); panel.append(item);
  }
}
function setTab(tab) {
  state.tab = tab;
  document.querySelectorAll('.tab').forEach(button => button.classList.toggle('active', button.dataset.tab === tab));
  $('#timelinePanel').classList.toggle('hidden', tab !== 'timeline');
  $('#resultsPanel').classList.toggle('hidden', tab !== 'search');
  $('#listOverline').textContent = tab === 'search' ? 'SOURCE MATCHES' : 'LECTURE TRANSCRIPT';
  $('#listTitle').textContent = tab === 'search' ? 'Search results' : 'Timeline';
  $('#segmentCount').textContent = tab === 'search' ? `${state.results.length} matches` : `${state.lecture.segments.length} passages`;
}
async function performSearch() {
  const query = $('#searchInput').value.trim(); state.query = query;
  if (!query) { state.results = []; $('#resultCount').textContent = ''; setTab('timeline'); return; }
  try { const data = await api(`/api/lectures/${state.lecture.id}/search?q=${encodeURIComponent(query)}`); if (state.query !== query) return; state.results = data.results; $('#resultCount').textContent = `(${data.results.length})`; renderResults(); setTab('search'); }
  catch (error) { toast(error.message); }
}
function renderResults() {
  const panel = $('#resultsPanel'); panel.replaceChildren();
  if (!state.results.length) { panel.append(el('div', 'placeholder', 'No matching passages or slide text. Try a different term.')); return; }
  for (const result of state.results) {
    const item = el('article', 'result');
    const head = el('div', 'result-head'); head.append(el('span', 'result-type', result.kind === 'slide' ? `SLIDE ${result.page}` : `TRANSCRIPT · ${formatTime(result.start)}`), el('span', 'result-score', `match ${result.score.toFixed(2)}`));
    const actions = el('div', 'result-meta');
    if (result.start !== null && state.lecture.audio) { const play = el('button', '', `▶ Play at ${formatTime(result.start)}`); play.addEventListener('click', () => { jumpTo(result.start, result.id); setTab('timeline'); }); actions.append(play); }
    if (result.page) { const show = el('button', '', `▤ View slide ${result.page}`); show.addEventListener('click', () => selectPage(result.page)); actions.append(show); }
    item.append(head, el('p', '', result.snippet), actions); panel.append(item);
  }
}
function fileToUpload(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve({name:file.name,data:String(reader.result).split(',')[1]});
    reader.onerror = () => reject(new Error(`Could not read ${file.name}`));
    reader.readAsDataURL(file);
  });
}
function openImport() { $('#importError').textContent = ''; $('#importDialog').showModal(); $('#titleField').focus(); }
async function submitImport(event) {
  event.preventDefault();
  const title = $('#titleField').value.trim();
  const audio = $('#audioField').files[0], pdf = $('#pdfField').files[0], transcript = $('#transcriptField').files[0];
  if (!title) { $('#importError').textContent = 'Add a lecture title.'; return; }
  if (!audio && !pdf && !transcript) { $('#importError').textContent = 'Choose at least one file.'; return; }
  const limit = [[audio,120],[pdf,30],[transcript,4]].find(([file,mb]) => file && file.size > mb * 1024 * 1024);
  if (limit) { $('#importError').textContent = `${limit[0].name} is too large.`; return; }
  const button = $('#importSubmit'); button.disabled = true; button.textContent = 'Importing…'; $('#importError').textContent = '';
  try {
    const payload = {title, audio:audio ? await fileToUpload(audio) : null, pdf:pdf ? await fileToUpload(pdf) : null, transcript:transcript ? await fileToUpload(transcript) : null};
    const lecture = await api('/api/lectures', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    $('#importDialog').close(); $('#importForm').reset();
    for (const id of ['audioName','pdfName','transcriptName']) $(`#${id}`).textContent = 'Choose file';
    await loadLibrary(); await openLecture(lecture.id); toast('Lecture imported');
  } catch (error) { $('#importError').textContent = error.message; }
  finally { button.disabled = false; button.innerHTML = 'Create workspace <span>↗</span>'; }
}

$('#newLecture').addEventListener('click', openImport);
$('#heroImport').addEventListener('click', openImport);
$('#importAnother').addEventListener('click', openImport);
$('#closeDialog').addEventListener('click', () => $('#importDialog').close());
$('#importForm').addEventListener('submit', submitImport);
$('#helpButton').addEventListener('click', () => $('#helpDialog').showModal());
$('#closeHelp').addEventListener('click', () => $('#helpDialog').close());
$('#prevPage').addEventListener('click', () => selectPage(state.page - 1));
$('#nextPage').addEventListener('click', () => selectPage(state.page + 1));
document.querySelectorAll('.tab').forEach(button => button.addEventListener('click', () => setTab(button.dataset.tab)));
$('#searchInput').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(performSearch, 220); });
$('#searchInput').addEventListener('keydown', event => { if (event.key === 'Enter') { clearTimeout(searchTimer); performSearch(); } });
for (const [field,name] of [['audioField','audioName'],['pdfField','pdfName'],['transcriptField','transcriptName']]) {
  $(`#${field}`).addEventListener('change', event => { $(`#${name}`).textContent = event.target.files[0]?.name || 'Choose file'; });
}
Promise.all([api('/api/health'), loadLibrary()]).then(([health]) => { state.transcriber = health.transcriber; if (state.lecture) renderPlayer(); }).catch(error => toast(error.message));
