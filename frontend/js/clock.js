/**
 * clock.js — WebSocket client, time display, brightness, view routing.
 */

const WS_URL = `ws://${location.host}/ws`;
let ws = null;
let reconnectDelay = 1000;

function connect() {
  ws = new WebSocket(WS_URL);

  ws.addEventListener("open", () => {
    document.getElementById("ws-status").className = "connected";
    reconnectDelay = 1000;
  });

  ws.addEventListener("close", () => {
    document.getElementById("ws-status").className = "disconnected";
    setTimeout(connect, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, 30000);
  });

  ws.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data);
    dispatch(msg);
  });
}

function renderTime(time) {
  const el = document.getElementById("time");
  // Split "H:MM:SS AM" → main "H:MM" + seconds ":SS" + suffix " AM"
  const match = time.match(/^(.+):(\d{2})(\s*[AP]M)?$/);
  if (match) {
    const [, main, sec, suffix] = match;
    el.innerHTML = `${main}<span class="seconds">:${sec}${suffix || ""}</span>`;
  } else {
    el.textContent = time;
  }
}

function dispatch(msg) {
  switch (msg.type) {
    case "settings_update":
      document.documentElement.style.setProperty(
        "--seconds-scale", msg.seconds_scale ?? 0.55
      );
      break;

    case "time_update":
      renderTime(msg.time);
      document.getElementById("date").textContent = msg.date;
      document.getElementById("day").textContent  = msg.day;
      break;

    case "brightness_update":
      document.documentElement.style.setProperty("--brightness", `${msg.brightness}%`);
      break;

    case "alarm_state":
      updateAlarmIndicator(msg);
      break;

    case "alarm_firing":
      showAlarmOverlay(msg);
      break;

    case "alarm_snoozed":
      hideAlarmOverlay();
      document.getElementById("next-alarm").textContent = `Snoozed until ${msg.until}`;
      break;

    case "alarm_dismissed":
      hideAlarmOverlay();
      break;

    case "switch_view":
      handleSwitchView(msg.view);
      break;
  }
}

function updateAlarmIndicator(msg) {
  const el = document.getElementById("next-alarm");
  if (msg.next_alarm_label && msg.next_alarm_time) {
    el.textContent = `Next: ${msg.next_alarm_label} at ${msg.next_alarm_time}`;
  } else {
    el.textContent = "";
  }
}

function showAlarmOverlay(msg) {
  const overlay = document.getElementById("alarm-overlay");
  document.getElementById("alarm-label").textContent = msg.label || "Alarm";
  document.getElementById("alarm-time-display").textContent = msg.time || "";
  overlay.classList.remove("hidden");
  overlay.classList.add("firing");
}

function hideAlarmOverlay() {
  const overlay = document.getElementById("alarm-overlay");
  overlay.classList.add("hidden");
  overlay.classList.remove("firing");
}

function handleSwitchView(view) {
  // Phase 8 will navigate to dashboard.html; stub for MVP
  if (view === "dashboard") {
    window.location.href = "/dashboard.html";
  } else if (view === "settings") {
    window.location.href = "/settings.html";
  } else if (view === "clock") {
    window.location.href = "/";
  }
}

// Expose send helpers so alarm.js can call them
function sendMsg(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(obj));
  }
}

connect();
