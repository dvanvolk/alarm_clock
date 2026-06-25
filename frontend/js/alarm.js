/**
 * alarm.js — snooze / dismiss button handlers.
 */

function sendSnooze() {
  sendMsg({ type: "snooze" });
}

function sendDismiss() {
  sendMsg({ type: "dismiss" });
}
