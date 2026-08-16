// ================================================================
// Dispatch Dashboard — API Module
// ================================================================
window.DASH = window.DASH || {};

(function () {
  'use strict';

  // /api/eta issues one ORS call per remaining stop, serially, each with a
  // 30-second server-side timeout — so a slow route can hang far longer than
  // the 12-second poll interval. Without a client timeout the poll's
  // in-flight guard stayed set and the dashboard froze showing a green
  // "Live" pill over stale data (audit P-08).
  const REQUEST_TIMEOUT_MS = 20000;

  async function fetchJSON(url, opts) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

    let resp;
    try {
      resp = await fetch(url, { ...opts, signal: controller.signal });
    } catch (e) {
      if (e.name === 'AbortError') {
        throw new Error(`Request timed out after ${REQUEST_TIMEOUT_MS / 1000}s: ${url}`);
      }
      throw e;
    } finally {
      clearTimeout(timeoutId);
    }

    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      const err = new Error(body.error || body.message || `HTTP ${resp.status}`);
      // The message alone is not enough for every failure. A blocked
      // completion answers 422 with `proof_required`, and the caller has to
      // tell that apart from an ordinary error to offer the override —
      // pattern-matching on English would break the first time the wording
      // changed. Attached rather than thrown differently so every existing
      // `catch (err) { err.message }` keeps working.
      err.status = resp.status;
      err.body = body;
      throw err;
    }
    return resp.json();
  }

  DASH.api = {
    dashboard() {
      return fetchJSON('/api/execution/dashboard');
    },

    plans() {
      return fetchJSON('/api/plans');
    },

    drivers() {
      return fetchJSON('/api/drivers');
    },

    stops(assignmentId) {
      return fetchJSON(`/api/stops?assignment_id=${assignmentId}`);
    },

    progress(assignmentId) {
      return fetchJSON(`/api/execution/progress?assignment_id=${assignmentId}`);
    },

    eta(assignmentId) {
      return fetchJSON(`/api/eta?assignment_id=${assignmentId}`);
    },

    // expectedStatus is the execution_status this stop's card was rendered
    // with. The server refuses the move if the stop has since changed, so a
    // double-tap can't walk it two steps (planned -> arrived -> completed).
    // overrideReason completes a stop that has no proof photos. Omitted for
    // an ordinary advance, in which case the server refuses with 422 and
    // `proof_required` so the dashboard can ask for one.
    advance(stopId, expectedStatus, overrideReason) {
      return fetchJSON('/api/execution/advance', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          stop_id: stopId,
          expected_status: expectedStatus,
          override_reason: overrideReason || '',
        }),
      });
    },

    // Multipart, so no Content-Type header — the browser has to set it
    // itself to include the multipart boundary. Setting it by hand produces
    // a body the server cannot parse.
    uploadStopImage(stopId, file, category) {
      const form = new FormData();
      form.append('file', file);
      form.append('category', category || 'unload');
      return fetchJSON(`/api/stops/${stopId}/images`, { method: 'POST', body: form });
    },

    // Steps a stop back: arrived -> planned, completed -> arrived, and
    // skipped/cancelled -> whatever they were before. expectedStatus carries
    // the same staleness guard as advance() — the server refuses a revert
    // aimed at a status the stop has already left.
    revert(stopId, expectedStatus) {
      return fetchJSON('/api/execution/revert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stop_id: stopId, expected_status: expectedStatus }),
      });
    },

    skip(stopId, reason) {
      return fetchJSON(`/api/stops/${stopId}/skip`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: reason || '' }),
      });
    },

    cancel(stopId, reason) {
      return fetchJSON(`/api/stops/${stopId}/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: reason || '' }),
      });
    },

    // The server insists on the assignment's *complete* stop list, in the
    // desired order — a partial list used to renumber only the stops it named
    // and leave duplicate execution_sequences behind.
    reorderStops(assignmentId, stopIds) {
      return fetchJSON('/api/stops/reorder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ assignment_id: assignmentId, stop_ids: stopIds }),
      });
    },

    planDetail(planId) {
      return fetchJSON(`/api/plans/${planId}`);
    },

    stopImages(stopId) {
      return fetchJSON(`/api/stops/${stopId}/images`);
    },

    // Deletes the row *and* unlinks the file — there is no soft delete and no
    // undo. The endpoint has existed since the delivery module shipped; it had
    // no caller until the gallery got a remove control (2026-08-15), which is
    // why dispatch previously had no way to correct evidence attached to the
    // wrong stop.
    deleteStopImage(imageId) {
      return fetchJSON(`/api/images/${imageId}`, { method: 'DELETE' });
    },

    stopHistory(stopId) {
      return fetchJSON(`/api/stops/${stopId}/history`);
    },

    deletePlans(planIds) {
      return fetchJSON('/api/plans/batch-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan_ids: planIds }),
      });
    },

    clearPlans() {
      return fetchJSON('/api/plans/clear', { method: 'POST' });
    },

    // Nearest Mapillary street-level image to a point. Proxied through Flask
    // rather than called directly so MAPILLARY_TOKEN stays server-side.
    //
    // Resolves for BOTH "here is a photo" ({found: true, image}) and "nothing
    // is mapped here" ({found: false, reason: 'no_imagery'}) — an uncovered
    // alley is an answer, not a failure, and fetchJSON only throws on a real
    // one (503 when Mapillary is unreachable or the token is bad). The panel
    // has to tell those apart or a token outage looks like empty coverage.
    streetview(lat, lng) {
      return fetchJSON(`/api/streetview?lat=${encodeURIComponent(lat)}&lng=${encodeURIComponent(lng)}`);
    },
  };
})();
