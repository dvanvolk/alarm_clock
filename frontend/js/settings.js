/**
 * settings.js — alarm settings page: WebSocket client + form rendering.
 */

const WS_URL = `ws://${location.host}/ws`;
let ws = null;
let reconnectDelay = 1000;
let reloadOnReconnect = false;
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
    if (reloadOnReconnect) {
      location.reload();
      return;
    }
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
    if (msg.type === 'reload') {
      location.reload();
    } else if (msg.type === 'config_update') {
      currentAlarms = msg.alarms || [];
      renderAlarms(currentAlarms);
      const urlInput = document.getElementById('dashboard-url');
      if (urlInput && msg.dashboard_url !== undefined) {
        urlInput.value = msg.dashboard_url;
      }
    } else if (msg.type === 'settings_update') {
      const size = document.getElementById('clock-size-scale');
      const sizeVal = document.getElementById('clock-size-scale-value');
      if (size && msg.size_scale !== undefined) {
        size.value = msg.size_scale;
        if (sizeVal) sizeVal.textContent = Math.round(msg.size_scale * 100) + '%';
      }
      const dayInput = document.getElementById('clock-color-day');
      if (dayInput && msg.color_day) dayInput.value = msg.color_day;
      const nightInput = document.getElementById('clock-color-night');
      if (nightInput && msg.color_night) nightInput.value = msg.color_night;
    } else if (msg.type === 'ota_status') {
      handleOtaStatus(msg);
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
    list.innerHTML = '<p style="color:var(--dim);padding:20px;">No alarms configured.</p>';
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
  const sunriseOn = alarm.sunrise_enabled !== false;

  const melodyOptions = MELODY_OPTIONS.map(opt =>
    `<option value="${opt.value}" ${alarm.melody === opt.value ? 'selected' : ''}>${opt.label}</option>`
  ).join('');

  return `
    <div class="alarm-card" data-index="${index}">

      <div class="alarm-header-row">
        <input type="checkbox" class="alarm-enabled" ${alarm.enabled ? 'checked' : ''} title="Enabled">
        <input type="text" class="alarm-label-input" value="${escHtml(alarm.label || '')}" placeholder="Alarm name">
        <button class="btn-delete-alarm" onclick="deleteAlarm(${index})" title="Delete alarm">✕</button>
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

      <div class="card-row alarm-buzzer-row${isMusic ? ' hidden' : ''}">
        <span class="card-label">Duty</span>
        <input type="number" class="alarm-number-input alarm-buzzer-duty"
               value="${alarm.buzzer_duty_cycle ?? 50}" min="1" max="100">
        <span class="card-unit">%</span>
      </div>

      <div class="card-row">
        <span class="card-label">Snooze</span>
        <input type="number" class="alarm-number-input alarm-snooze-minutes"
               value="${alarm.snooze_minutes ?? 9}" min="1" max="60">
        <span class="card-unit">min</span>
      </div>

      <div class="card-row">
        <span class="card-label">Sunrise</span>
        <label style="display:flex;align-items:center;gap:6px;cursor:pointer">
          <input type="checkbox" class="alarm-sunrise-enabled"
                 ${sunriseOn ? 'checked' : ''}
                 onchange="onSunriseChange(this)">
          <span style="color:var(--dim);font-size:0.8rem">Enable</span>
        </label>
        <input type="number" class="alarm-number-input alarm-sunrise-ramp${sunriseOn ? '' : ' hidden'}"
               value="${alarm.sunrise_ramp_minutes ?? 20}" min="1" max="120">
        <span class="card-unit alarm-sunrise-ramp-unit${sunriseOn ? '' : ' hidden'}">min before</span>
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
  card.querySelector('.alarm-buzzer-row').classList.toggle('hidden', isMusic);
}

function onSunriseChange(checkbox) {
  const card = checkbox.closest('.alarm-card');
  const enabled = checkbox.checked;
  card.querySelector('.alarm-sunrise-ramp').classList.toggle('hidden', !enabled);
  card.querySelector('.alarm-sunrise-ramp-unit').classList.toggle('hidden', !enabled);
}

function addAlarm() {
  currentAlarms.push({
    label: 'New Alarm',
    time: '07:00',
    days: ['mon', 'tue', 'wed', 'thu', 'fri'],
    enabled: true,
    sound: 'buzzer',
    music_uri: '',
    melody: 'default',
    snooze_minutes: 9,
    sunrise_enabled: true,
    sunrise_ramp_minutes: 20,
    buzzer_duty_cycle: 50,
  });
  renderAlarms(currentAlarms);
}

function deleteAlarm(index) {
  currentAlarms.splice(index, 1);
  renderAlarms(currentAlarms);
}

function saveSettings() {
  const cards = document.querySelectorAll('.alarm-card');
  const alarms = Array.from(cards).map(card => {
    const checkedDays = Array.from(
      card.querySelectorAll('input[type=checkbox][name^="days_"]:checked')
    ).map(cb => cb.value);

    return {
      label:               card.querySelector('.alarm-label-input').value.trim() || 'Alarm',
      time:                card.querySelector('.alarm-time').value,
      days:                checkedDays,
      enabled:             card.querySelector('.alarm-enabled').checked,
      sound:               card.querySelector('.alarm-sound-select').value,
      music_uri:           card.querySelector('.alarm-music-uri').value.trim(),
      melody:              card.querySelector('.alarm-melody-select').value,
      snooze_minutes:      parseInt(card.querySelector('.alarm-snooze-minutes').value) || 9,
      sunrise_enabled:     card.querySelector('.alarm-sunrise-enabled').checked,
      sunrise_ramp_minutes: parseInt(card.querySelector('.alarm-sunrise-ramp').value) || 20,
      buzzer_duty_cycle:   parseInt(card.querySelector('.alarm-buzzer-duty').value) || 50,
    };
  });

  const sizeScale  = parseFloat(document.getElementById('clock-size-scale')?.value ?? '1') || 1;
  const colorDay   = document.getElementById('clock-color-day')?.value || '#e8a020';
  const colorNight = document.getElementById('clock-color-night')?.value || '#c0392b';

  const dashboardUrl = (document.getElementById('dashboard-url')?.value ?? '').trim();
  sendMsg({
    type: 'settings_save',
    settings: {
      alarms,
      dashboard_url: dashboardUrl,
      clock: { size_scale: sizeScale, color_day: colorDay, color_night: colorNight },
    },
  });
  showSaveStatus('Saved', 'ok');
}

function showSaveStatus(text, cssClass) {
  const el = document.getElementById('save-status');
  el.textContent = text;
  el.className = cssClass;
  setTimeout(() => { el.textContent = ''; el.className = ''; }, 3000);
}

// ---------------------------------------------------------------------------
// Software update
// ---------------------------------------------------------------------------

function sendOtaTrigger() {
  const btn = document.getElementById('btn-update');
  if (btn) btn.disabled = true;
  sendMsg({ type: 'ota_trigger' });
}

function handleOtaStatus(msg) {
  if (msg.status === 'restarting') reloadOnReconnect = true;
  const el = document.getElementById('ota-status');
  const btn = document.getElementById('btn-update');
  if (!el) return;
  const labels = {
    starting:    'Checking for updates…',
    installing:  'Installing dependencies…',
    success:     `Updated: ${msg.detail || ''}`,
    restarting:  'Restarting — reconnecting shortly…',
    error:       `Update failed: ${msg.detail || 'unknown error'}`,
  };
  el.textContent = labels[msg.status] ?? msg.status;
  el.className = `ota-status-${msg.status}`;
  if (btn) btn.disabled = msg.status === 'starting' || msg.status === 'installing' || msg.status === 'restarting';
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

connect();
