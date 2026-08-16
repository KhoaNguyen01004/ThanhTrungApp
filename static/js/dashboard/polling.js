// ================================================================
// Dispatch Dashboard — Polling Module
// ================================================================
window.DASH = window.DASH || {};

(function () {
  'use strict';

  const INTERVAL_MS = 12000;
  let timer = null;
  let isPolling = false;
  let tickFn = null;
  // Set when a refresh is requested while one is already running. The request
  // is honoured when the in-flight tick finishes rather than dropped.
  let refreshQueued = false;
  let visibilityBound = false;

  async function runTick() {
    if (!tickFn) return;

    if (isPolling) {
      // A poll is already in flight. Previously this silently returned, so a
      // refresh requested right after Advance/Skip/Cancel was thrown away and
      // the dispatcher saw no change for up to 12 seconds — on an action they
      // had just taken (audit F-04). Remember it instead.
      refreshQueued = true;
      return;
    }

    isPolling = true;
    try {
      await tickFn();
      DASH.polling.setStatus('ok');
    } catch (e) {
      console.error('Poll error:', e);
      DASH.polling.setStatus('error');
    } finally {
      // Must be `finally`. This used to be a plain statement after the
      // try/catch, so anything thrown from the catch block (setStatus
      // touching a missing element, say) left the flag latched true and
      // killed polling *and* manual refresh for the rest of the session,
      // with the status pill frozen on its last value (audit F-06).
      isPolling = false;
    }

    if (refreshQueued) {
      refreshQueued = false;
      runTick();
    }
  }

  function bindVisibility() {
    if (visibilityBound || typeof document.addEventListener !== 'function') return;
    visibilityBound = true;
    document.addEventListener('visibilitychange', () => {
      if (!tickFn) return;
      if (document.hidden) {
        // A background tab kept hammering the server and TTAS every 12s
        // forever. Dispatchers leave this open all day (audit P-08).
        if (timer) { clearInterval(timer); timer = null; }
      } else if (!timer) {
        runTick();                                  // catch up immediately
        timer = setInterval(runTick, INTERVAL_MS);
      }
    });
  }

  DASH.polling = {
    start(onTick) {
      tickFn = onTick;
      bindVisibility();
      if (timer) return;
      runTick();
      timer = setInterval(runTick, INTERVAL_MS);
    },

    stop() {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
      refreshQueued = false;
      DASH.polling.setStatus('paused');
    },

    // `onTick` is accepted for backward compatibility with existing callers;
    // the callback registered by start() is authoritative.
    async refreshNow(onTick) {
      if (onTick) tickFn = onTick;
      await runTick();
    },

    // A poll can succeed while the data it carried is not trustworthy — TTAS
    // returning nothing, or returning positions that match no plate at all.
    // "The request worked" and "the map is live" are different claims, and
    // this pill previously made the second one on the strength of the first.
    // main.js registers a provider that downgrades the 'ok' state in those
    // cases. With no provider registered, 'ok' means Live exactly as before.
    okStatusProvider: null,

    setStatus(status) {
      const el = document.getElementById('pollStatus');
      if (!el) return;

      const labels = { ok: 'Live', error: 'Error', paused: 'Paused', degraded: 'Degraded' };
      let resolvedStatus = status;
      let resolvedTitle = '';

      if (status === 'ok' && typeof DASH.polling.okStatusProvider === 'function') {
        try {
          const override = DASH.polling.okStatusProvider();
          if (override && override.status) {
            resolvedStatus = override.status;
            resolvedTitle = override.title || '';
            if (override.label) labels[resolvedStatus] = override.label;
          }
        } catch (e) {
          // A broken provider must never take polling's status reporting with
          // it — that is the failure mode audit F-06 was about.
          console.error('okStatusProvider failed:', e);
        }
      }

      el.className = 'poll-status poll-' + resolvedStatus;
      el.textContent = labels[resolvedStatus] || resolvedStatus;
      el.title = resolvedTitle;
    },
  };
})();
