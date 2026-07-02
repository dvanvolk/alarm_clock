/**
 * settings.js — alarm settings page: WebSocket client + form rendering.
 */

const WS_URL = `ws://${location.host}/ws`;
let ws = null;
let reconnectDelay = 1000;
let currentAlarms = [];

const ALL_DAYS   = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];
const DAY_LABELS = ['M',   'T',   'W',   'T',   'F',   'S',   'S'];

const MELODY_OPTIONS = [
  { value: 'default', label: 'Default' },
  { value: 'gentle',  label: 'Gentle'  },
  { value: 'classic', label: 'Classic' },
];

// ---------------------------------------------------------------------------
// WebSocket
// ---------------------------------------------------------------------------

function connect() {
  ws = new WebSocket(WS_URL);

  ws.addEventListener('open', () => {
    const dot = document.getElementById('ws-status');
    if (dot) dot.className = 'connected';
    reconnectDelay = 1000;
  });

  ws.addEventListener('close', () => {
    const dot = document.getElementById('ws-status');
    if (dot) dot.className = 'disconnected';
    setTimeout(connect, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, 30000);
  });

  ws.addEventListener('message', (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'config_update') {
      currentAlarms = msg.alarms || [];
      renderAlarms(currentAlarms);
      const urlInput = document.getElementById('dashboard-url');
      if (urlInput && msg.dashboard_url !== undefined) {
        urlInput.value = msg.dashboard_url;
      }
    }
  });
}

function sendMsg(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(obj));
  }
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function renderAlarms(alarms) {
  const list = document.getElementById('alarm-list');
  if (!alarms.length) {
    list.innerHTML = '<p style="color:var(--dim)">No alarms configured.</p>';
    return;
  }
  list.innerHTML = alarms.map((alarm, i) => alarmCardHtml(alarm, i)).join('');
}

function alarmCardHtml(alarm, index) {
  const daysHtml = ALL_DAYS.map((d, i) => `
    <label class="day-cb">
      <input type="checkbox" name="days_${index}" value="${d}" ${alarm.days && alarm.days.includes(d) ? 'checked' : ''}>
      <span>${DAY_LABELS[i]}</span>
    </label>
  `).join('');

  const isMusic = alarm.sound === 'music_assistant';

  const melodyOptions = MELODY_OPTIONS.map(opt =>
    `<option value="${opt.value}" ${alarm.melody === opt.value ? 'selected' : ''}>${opt.label}</option>`
  ).join('');

  return `
    <div class="alarm-card" data-index="${index}">

      <div class="alarm-header-row">
        <input type="checkbox" class="alarm-enabled" ${alarm.enabled ? 'checked' : ''} title="Enabled">
        <input type="text" class="alarm-label-input" value="${escHtml(alarm.label || '')}" placeholder="Alarm name">
      </div>

      <div class="card-row">
        <span class="card-label">Time</span>
        <input type="time" class="alarm-time" value="${alarm.time || '00:00'}">
      </div>

      <div class="card-row">
        <span class="card-label">Days</span>
        <div class="days-row">${daysHtml}</div>
      </div>

      <div class="card-row">
        <span class="card-label">Sound</span>
        <select class="alarm-sound-select" onchange="onSoundChange(this)">
          <option value="music_assistant" ${isMusic ? 'selected' : ''}>Music Assistant</option>
          <option value="buzzer" ${!isMusic ? 'selected' : ''}>Buzzer</option>
        </select>
      </div>

      <div class="card-row alarm-music-row${isMusic ? '' : ' hidden'}">
        <span class="card-label">URI</span>
        <input type="text" class="alarm-music-uri" value="${escHtml(alarm.music_uri || '')}" placeholder="media-source://music_assistant/…">
      </div>

      <div class="card-row alarm-melody-row${isMusic ? ' hidden' : ''}">
        <span class="card-label">Melody</span>
        <select class="alarm-melody-select">${melodyOptions}</select>
      </div>

    </div>
  `;
}

function escHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

// ---------------------------------------------------------------------------
// Interaction
// ---------------------------------------------------------------------------

function onSoundChange(select) {
  const card = select.closest('.alarm-card');
  const isMusic = select.value === 'music_assistant';
  card.querySelector('.alarm-music-row').classList.toggle('hidden', !isMusic);
  card.querySelector('.alarm-melody-row').classList.toggle('hidden', isMusic);
}

function saveSettings() {
  const cards = document.querySelectorAll('.alarm-card');
  const alarms = Array.from(cards).map(card => {
    const index = parseInt(card.dataset.index, 10);
    const checkedDays = Array.from(
      card.querySelectorAll('input[type=checkbox][name^="days_"]:checked')
    ).map(cb => cb.value);

    return {
      label:     card.querySelector('.alarm-label-input').value.trim() || currentAlarms[index]?.label || '',
      time:      card.querySelector('.alarm-time').value,
      days:      checkedDays,
      enabled:   card.querySelector('.alarm-enabled').checked,
      sound:     card.querySelector('.alarm-sound-select').value,
      music_uri: card.querySelector('.alarm-music-uri').value.trim(),
      melody:    card.querySelector('.alarm-melody-select').value,
    };
  });

  const dashboardUrl = (document.getElementById('dashboard-url')?.value ?? '').trim();
  sendMsg({ type: 'settings_save', settings: { alarms, dashboard_url: dashboardUrl } });
  showSaveStatus('Saved', 'ok');
}

function showSaveStatus(text, cssClass) {
  const el = document.getElementById('save-status');
  el.textContent = text;
  el.className = cssClass;
  setTimeout(() => { el.textContent = ''; el.className = ''; }, 3000);
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

connect();
