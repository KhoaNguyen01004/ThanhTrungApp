// ================================================================
// Dispatch Dashboard — Timeline Module (Right Panel)
// ================================================================
window.DASH = window.DASH || {};

(function () {
  'use strict';

  // Canonical escaper from utils.js (loaded before this file). The private
  // copy this replaces did not escape quotes, and was used inside title="..."
  // and alt="..." attributes in the photo gallery — where img.category comes
  // straight from an unvalidated form field (audit S-02).
  const escapeHtml = UI.escapeHtml;

  function statusClass(status) {
    const map = {
      draft: 'status-draft',
      confirmed: 'status-confirmed',
      executing: 'status-executing',
      arrived: 'status-arrived',
      completed: 'status-completed',
      skipped: 'status-skipped',
      cancelled: 'status-cancelled',
      planned: 'status-planned',
    };
    return map[status] || 'status-planned';
  }

  function statusLabel(status) {
    return (status || 'planned').replace('_', ' ');
  }

  function formatTime(dateStr) {
    if (!dateStr) return '--';
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return dateStr;
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return dateStr;
    }
  }

  function formatDate(dateStr) {
    if (!dateStr) return '';
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return dateStr;
      return d.toLocaleDateString([], { day: '2-digit', month: '2-digit' });
    } catch {
      return dateStr;
    }
  }

  function setText(el, text) {
    if (el && el.textContent !== text) el.textContent = text;
  }

  // When the ETA payload currently being rendered was received. eta_seconds is
  // measured from that instant, so it is the baseline every arrival time has to
  // be computed against — recomputing from Date.now() pushes arrivals later on
  // every repaint. Held at module scope rather than threaded through
  // render -> _patchStop -> buildDetailHtml -> etaCellHtml, all of which would
  // otherwise grow a parameter they do nothing else with.
  let etaBaselineMs = null;

  // ETA is shown as a clock time rather than a countdown — see UI.etaClock().
  // The remaining duration stays available on hover, since "how long from now"
  // is still the faster read when the question is "can he make one more drop".
  function etaCellHtml(eta) {
    const clock = UI.etaClock(eta, etaBaselineMs);
    if (clock) {
      const relative = UI.etaRelative(eta);
      return `<span class="label">ETA:</span><span class="value" title="in ${escapeHtml(relative)}">${escapeHtml(clock)}</span>`;
    }
    // A non-numeric eta ('--' from the API) is passed through as it was; a
    // null one shows nothing at all rather than a fabricated time.
    if (eta && typeof eta !== 'number') {
      return `<span class="label">ETA:</span><span class="value">${escapeHtml(String(eta))}</span>`;
    }
    return '';
  }

  const ACTIONABLE = ['planned', 'arrived'];
  const TERMINAL = ['completed', 'skipped', 'cancelled'];

  function isTerminal(s) {
    return TERMINAL.includes(s.execution_status || 'planned');
  }

  // The number shown on a stop's badge. execution_sequence is what the whole
  // dashboard orders by and what a reorder rewrites; planned_sequence is the
  // number the stop was given when the plan was built and never moves. Showing
  // the latter meant a reordered route rendered as 1, 3, 2 — the list was
  // right, the badges disagreed with it.
  function displaySeq(s) {
    return s.execution_sequence || s.planned_sequence || '?';
  }

  // ── Locate on the map ──────────────────────────────────────────
  // Clicking a stop in the timeline brings it up on the map. The timeline says
  // which stop; the map says where — needing a second control to connect the
  // two was the gap.
  //
  // Follow mode is switched off first: it re-centres on the vehicle every poll,
  // so leaving it on would drag the view off the stop within 12 seconds.
  function focusStopOnMap(stopId) {
    if (!DASH.map || typeof DASH.map.focusStop !== 'function') return;
    if (DASH.map.focusStop(stopId)) {
      if (DASH.state && typeof DASH.state.setFollowMode === 'function') {
        DASH.state.setFollowMode(false);
      }
      return;
    }
    // No marker means the stop was imported without coordinates. Say so —
    // a click that does nothing at all reads as a broken dashboard.
    UI.toast('This stop has no coordinates, so it is not on the map', 'error', 4000);
  }

  // ── Street view ────────────────────────────────────────────────
  // Coordinates are read from state rather than carried in data-lat/data-lng
  // attributes: the numbers are already there, and a stop whose coordinates
  // were corrected mid-shift would otherwise open the old position from
  // whenever the row was last rendered.
  //
  // Deliberately does NOT locate the stop on the map first. Opening street
  // view is a question about one address; moving the map is a separate
  // decision the dispatcher makes by clicking the row, and doing both would
  // drag the view off a truck they were watching.
  function openStreetViewForStop(stopId) {
    if (!DASH.streetview) return;
    const stop = (DASH.state.selectedStops || []).find((s) => s.id === stopId);
    if (!stop || stop.lat == null || stop.lng == null) {
      UI.toast('This stop has no coordinates, so there is no street view for it', 'error', 4000);
      return;
    }
    const label = stop.station_name || stop.station_code || `Stop #${displaySeq(stop)}`;
    DASH.streetview.openAt(stop.lat, stop.lng, label);
  }

  // ── Reorder ────────────────────────────────────────────────────
  // Up/down buttons rather than drag-and-drop: this panel is used on phones in
  // the field, where HTML5 drag events don't fire at all.
  //
  // A stop that is already completed, skipped or cancelled can't be moved, and
  // nothing can be moved across one — its position is a record of what actually
  // happened, and renumbering around it would rewrite history.
  function moveStop(stopId, delta) {
    const assignmentId = DASH.state.selectedAssignmentId;
    const stops = DASH.state.selectedStops || [];
    const from = stops.findIndex((s) => s.id === stopId);
    const to = from + delta;
    if (!assignmentId || from === -1 || to < 0 || to >= stops.length) return;
    if (isTerminal(stops[from]) || isTerminal(stops[to])) return;

    const reordered = stops.slice();
    const [moved] = reordered.splice(from, 1);
    reordered.splice(to, 0, moved);

    // Renumber locally so the badges read 1..n immediately. The server does the
    // same thing; its answer arrives with the refresh that follows.
    DASH.state.reorderStops(
      assignmentId,
      reordered.map((s, i) => ({ ...s, execution_sequence: i + 1 }))
    );
  }

  // ── Actions + inline reason row — shared markup/behavior between each
  // per-stop timeline body and the pinned current-stop card, so both get
  // the same Advance/Skip/Cancel handling from one place. Skip/Cancel no
  // longer use prompt()/alert(): clicking either swaps the buttons for an
  // inline input, confirmed with Enter or a Confirm button, with errors
  // reported via UI.toast() instead of a blocking alert().
  //
  // Revert is rendered from the server's `can_revert` flag rather than from a
  // status check here: the undo window is time-bounded, and a browser clock a
  // few minutes off would otherwise offer a button the API refuses. It shows
  // on terminal stops too — a stop mis-advanced to completed is exactly the
  // one a dispatcher needs it on, and that row has no other actions at all.
  function buildActionsHtml(stop, execStatus) {
    const actionable = ACTIONABLE.includes(execStatus);
    const revertible = !!stop.can_revert;
    const stopId = stop.id;

    // Street view is a question about a place, not a change to a stop, so it
    // is offered on every stop that has coordinates — including completed,
    // skipped and cancelled ones. "Where was that place again?" is asked about
    // yesterday's stops as often as today's, and those rows previously
    // rendered no action bar at all, which is why the early return that used
    // to sit above is gone.
    //
    // Rendered only when coordinates exist: a stop imported from the sheet
    // without them can never have imagery, and a button that only ever
    // produces an error message is worse than no button.
    const hasCoords = stop.lat != null && stop.lng != null;
    const streetViewHtml = hasCoords ? `
                <button class="btn-nav btn-streetview" data-action="streetview" data-stop-id="${stopId}" title="See street-level imagery of this address">&#128247; Street view</button>` : '';

    if (!actionable && !revertible) {
      if (!streetViewHtml) return '';
      return `
              <div class="timeline-actions" data-actions-for="${stopId}">${streetViewHtml}
              </div>`;
    }

    const forwardHtml = actionable ? `
                <button class="btn-nav" data-action="advance" data-stop-id="${stopId}" data-expected-status="${execStatus}">Advance</button>
                <button class="btn-nav" data-action="skip" data-stop-id="${stopId}">Skip</button>
                <button class="btn-danger" data-action="cancel" data-stop-id="${stopId}">Cancel</button>` : '';

    const revertHtml = revertible ? `
                <button class="btn-nav btn-revert" data-action="revert" data-stop-id="${stopId}" data-expected-status="${execStatus}" title="Undo the last change to this stop">&#8617; Revert</button>` : '';

    // The reason row only serves Skip/Cancel, so a terminal stop showing
    // nothing but Revert doesn't carry one.
    const reasonHtml = actionable ? `
              <div class="timeline-reason-row" data-reason-for="${stopId}" style="display:none;">
                <input type="text" class="timeline-reason-input" data-reason-input>
                <button class="btn-nav" data-reason-confirm="${stopId}">Confirm</button>
                <button class="btn-nav" data-reason-cancel="${stopId}">&times;</button>
              </div>` : '';

    return `
              <div class="timeline-actions" data-actions-for="${stopId}">${forwardHtml}${revertHtml}${streetViewHtml}
              </div>${reasonHtml}`;
  }

  // Stop ids with an open (mid-edit) reason row — content patching for
  // these is suppressed until the row closes, since a background poll is
  // non-blocking now (unlike the old prompt()) and would otherwise wipe
  // out whatever the dispatcher is typing.
  const openReasonStopIds = new Set();

  const REASON_PLACEHOLDER = {
    cancel: 'Reason (required)',
    skip: 'Reason (optional)',
    // Reached only after the server has refused the completion for want of
    // photos. A blank override would record that proof was waived and say
    // nothing about why, which is the one thing that makes the exception
    // defensible later.
    advance: 'No photo — why? (required)',
  };

  function showReasonRow(container, stopId, action) {
    const actionsRow = container.querySelector(`[data-actions-for="${stopId}"]`);
    const reasonRow = container.querySelector(`[data-reason-for="${stopId}"]`);
    if (!actionsRow || !reasonRow) return;
    openReasonStopIds.add(String(stopId));
    reasonRow.dataset.pendingAction = action;
    const input = reasonRow.querySelector('[data-reason-input]');
    input.placeholder = REASON_PLACEHOLDER[action] || 'Reason (optional)';
    input.value = '';
    actionsRow.style.display = 'none';
    reasonRow.style.display = '';
    input.focus();
  }

  function hideReasonRow(container, stopId) {
    openReasonStopIds.delete(String(stopId));
    const actionsRow = container.querySelector(`[data-actions-for="${stopId}"]`);
    const reasonRow = container.querySelector(`[data-reason-for="${stopId}"]`);
    if (!actionsRow || !reasonRow) return;
    reasonRow.style.display = 'none';
    actionsRow.style.display = '';
  }

  function confirmReason(container, stopId) {
    const reasonRow = container.querySelector(`[data-reason-for="${stopId}"]`);
    if (!reasonRow) return;
    const action = reasonRow.dataset.pendingAction;
    const input = reasonRow.querySelector('[data-reason-input]');
    const reason = input.value.trim();

    if (!reason && (action === 'cancel' || action === 'advance')) {
      UI.toast(action === 'advance'
        ? 'Say why there is no photo before completing without one'
        : 'A reason is required to cancel a stop', 'error');
      input.focus();
      return;
    }

    hideReasonRow(container, stopId);
    handleStopAction(parseInt(stopId, 10), action, reason,
                     reasonRow.dataset.expectedStatus, null, container);
  }

  // Guards against the same stop being actioned twice while the first request
  // is still in flight. The server also rejects a stale advance, but stopping
  // it here means the dispatcher never sees a confusing error for what was
  // just an impatient second tap.
  const inFlightStopIds = new Set();

  // How long the undo offer stays on screen. Deliberately longer than the
  // default toast: the mis-tap is usually noticed a beat after it happens,
  // once the panel repaints and shows the wrong stop.
  const UNDO_TOAST_MS = 9000;

  // The status a stop lands in, needed as the undo's staleness token before
  // the refresh that would tell us. Advance's response says "advanced" or
  // "completed", which are outcomes rather than statuses, so the walk is
  // reproduced here from the status the button was rendered with.
  //
  // Returns null when that status is unknown, and the undo then goes without
  // a token — the server still refuses anything it can't legally step back.
  function resultingStatus(action, expectedStatus) {
    if (action === 'skip') return 'skipped';
    if (action === 'cancel') return 'cancelled';
    if (action === 'advance') {
      if (expectedStatus === 'planned') return 'arrived';
      if (expectedStatus === 'arrived') return 'completed';
    }
    return null;
  }

  const UNDOABLE_MESSAGE = {
    arrived: 'Stop marked arrived',
    completed: 'Stop marked completed',
    skipped: 'Stop skipped',
    cancelled: 'Stop cancelled',
  };

  function offerUndo(stopId, action, expectedStatus) {
    const landed = resultingStatus(action, expectedStatus);
    const message = UNDOABLE_MESSAGE[landed] || 'Stop updated';
    UI.toast(message, 'success', UNDO_TOAST_MS, {
      actionLabel: 'Undo',
      // Goes through handleStopAction rather than DASH.api.revert directly, so
      // the undo inherits the same in-flight guard and error reporting as the
      // Revert button — a double-tapped Undo is one request, not two.
      onAction: () => handleStopAction(stopId, 'revert', '', landed || undefined),
    });
  }

  function handleStopAction(stopId, action, reason, expectedStatus, buttonEl, container) {
    const token = `${stopId}:${action}`;
    if (inFlightStopIds.has(token)) return;
    inFlightStopIds.add(token);
    if (buttonEl) buttonEl.disabled = true;

    let promise;
    if (action === 'advance') {
      // `reason` is the override — empty on a normal advance, which is what
      // lets the server refuse and ask for one.
      promise = DASH.api.advance(stopId, expectedStatus, reason || '');
    } else if (action === 'revert') {
      promise = DASH.api.revert(stopId, expectedStatus);
    } else if (action === 'skip') {
      promise = DASH.api.skip(stopId, reason || '');
    } else if (action === 'cancel') {
      promise = DASH.api.cancel(stopId, reason);
    } else {
      inFlightStopIds.delete(token);
      if (buttonEl) buttonEl.disabled = false;
      return;
    }

    promise
      .then((resp) => {
        // The action just added a row to this stop's log. If the dispatcher
        // has that panel open, it is now stale — and a history panel showing
        // a change that already happened as absent is worse than no panel.
        refreshHistoryFor(stopId);
        if (action === 'revert') {
          // No undo offered on an undo: the way forward from here is the
          // Advance button, which is sitting right there and says so.
          UI.toast(`Stop restored to ${statusLabel((resp && resp.status) || 'planned')}`, 'success');
        } else {
          offerUndo(stopId, action, expectedStatus);
        }
        return DASH.state.refreshNow();
      })
      .catch((err) => {
        // A completion blocked for want of photos is not a failure to report
        // and forget — it is a question. Offer the override inline, with the
        // server's own message explaining which photo is missing.
        if (err && err.body && err.body.proof_required && container) {
          UI.toast(err.message, 'warning', 7000);
          const reasonRow = container.querySelector(`[data-reason-for="${stopId}"]`);
          if (reasonRow) reasonRow.dataset.expectedStatus = expectedStatus || '';
          showReasonRow(container, String(stopId), 'advance');
          return;
        }
        UI.toast(`${action.charAt(0).toUpperCase()}${action.slice(1)} failed: ${err.message}`, 'error', 6000);
      })
      .finally(() => {
        inFlightStopIds.delete(token);
        // The button usually vanishes with the next render; re-enable anyway
        // so a failed action stays retryable if the node survives.
        if (buttonEl && buttonEl.isConnected) buttonEl.disabled = false;
      });
  }

  // Bound once per container (a stop's body, or the pinned current-stop
  // card) — regenerating the actions/reason markup inside never requires
  // rebinding, since delegation reads data-* attributes at click time.
  function bindActionDelegation(container) {
    container.addEventListener('click', (e) => {
      const actionBtn = e.target.closest('[data-action]');
      if (actionBtn) {
        e.stopPropagation();
        if (actionBtn.disabled) return;
        const stopId = parseInt(actionBtn.dataset.stopId, 10);
        const action = actionBtn.dataset.action;
        // Checked before the advance/revert split: street view changes
        // nothing about the stop, so it must not reach showReasonRow, which
        // is where every other unrecognised action ends up.
        if (action === 'streetview') {
          openStreetViewForStop(stopId);
          return;
        }
        if (action === 'advance' || action === 'revert') {
          handleStopAction(stopId, action, '', actionBtn.dataset.expectedStatus,
                           actionBtn, container);
        } else {
          showReasonRow(container, actionBtn.dataset.stopId, action);
        }
        return;
      }
      const confirmBtn = e.target.closest('[data-reason-confirm]');
      if (confirmBtn) {
        e.stopPropagation();
        confirmReason(container, confirmBtn.dataset.reasonConfirm);
        return;
      }
      const cancelBtn = e.target.closest('[data-reason-cancel]');
      if (cancelBtn) {
        e.stopPropagation();
        hideReasonRow(container, cancelBtn.dataset.reasonCancel);
      }
    });

    container.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return;
      const row = e.target.closest('.timeline-reason-row');
      if (!row) return;
      e.stopPropagation();
      confirmReason(container, row.dataset.reasonFor);
    });
  }

  // ── Lazy evidence gallery — fetched only when a stop's "Photos" toggle is
  // opened, and only once (cached in closure). Lives in its own DOM node
  // outside the diffed detail content so opening it survives every poll's
  // body-content patch (Phase 3's "preserve UI state").
  //
  // Read-only until 2026-08-15, when a remove control was added: dispatch runs
  // many vehicles at once and evidence lands on the wrong stop, and there was
  // no way to undo that from the dashboard at all. DELETE /api/images/<id> had
  // existed since the module shipped — it simply had no caller.
  function bindPhotosToggle(bodyEl, stopId) {
    const toggleBtn = bodyEl.querySelector(`[data-photos-toggle="${stopId}"]`);
    const photosEl = bodyEl.querySelector(`[data-photos-for="${stopId}"]`);
    if (!toggleBtn || !photosEl) return;

    let loaded = false;
    let loading = false;

    async function load() {
      if (loading) return;
      loading = true;
      try {
        const images = await DASH.api.stopImages(stopId);
        loaded = true;
        if (!images || images.length === 0) {
          photosEl.innerHTML = '<span class="timeline-photos-status">No photos for this stop</span>';
          return;
        }
        // media_kind comes from the server (image_service.media_kind, derived
        // from the stored extension). Rows that predate video have it too, so
        // there is no missing-field case to defend against — but default to
        // the image branch anyway, because a <video> pointed at a JPEG renders
        // as nothing at all while an <img> pointed at anything shows a broken
        // thumbnail the dispatcher can at least see and report.
        //
        // preload="metadata" fetches the header only, not the whole clip: a
        // stop with three 100 MB videos would otherwise pull 300 MB the moment
        // the panel opened, over the same mobile connection dispatch is on.
        photosEl.innerHTML = images.map((img) => {
          const href = `/api/images/${img.id}/file`;
          const label = escapeHtml(img.category || (img.media_kind === 'video' ? 'video' : 'photo'));
          const media = img.media_kind === 'video'
            ? `<video src="${href}" preload="metadata" muted playsinline></video>
               <span class="timeline-photo-badge" aria-hidden="true">&#9654;</span>`
            : `<img src="${href}" alt="${label}" loading="lazy">`;
          return `
          <span class="timeline-photo-item">
            <a href="${href}" target="_blank" rel="noopener" class="timeline-photo-thumb" title="${escapeHtml(img.category || '')}">
              ${media}
            </a>
            <button type="button" class="timeline-photo-remove" data-remove-image="${img.id}"
                    data-remove-label="${label}" title="Remove this evidence">&times;</button>
          </span>`;
        }).join('');
      } catch (err) {
        photosEl.innerHTML = `<span class="timeline-photos-status">Failed to load photos: ${escapeHtml(err.message)}</span>`;
      } finally {
        loading = false;
      }
    }

    // Uploading invalidates the cache. Without this the gallery keeps showing
    // the set of photos that existed when it was first opened — so the photo
    // the dispatcher just took would be absent from the panel immediately
    // below the button they took it with.
    photoReloaders.set(String(stopId), () => {
      loaded = false;
      if (photosEl.style.display !== 'none') load();
    });

    // Removing mis-uploaded evidence. Delegated to the gallery container
    // rather than bound per thumbnail, because load() replaces the whole
    // innerHTML on every refresh and per-node listeners would die with it.
    //
    // Confirmed, unlike the equivalent remove on delivery-export.js: that page
    // drops a photo uploaded seconds earlier in the same session, whereas this
    // deletes proof of delivery for a truck that has already left, and the file
    // is gone from disk immediately (image_service.delete_image unlinks it).
    // There is no undo and, by the operator's decision, no record.
    photosEl.addEventListener('click', async (e) => {
      const btn = e.target.closest('[data-remove-image]');
      if (!btn) return;
      // The button sits inside the gallery, not inside the <a> — but stop the
      // event anyway so a mis-aimed click can never open the file in a new tab
      // and fire the delete at the same time.
      e.preventDefault();
      e.stopPropagation();
      const label = btn.dataset.removeLabel || 'this evidence';
      if (!window.confirm(
        `Delete ${label}? This removes the file permanently and cannot be undone.`
      )) return;

      btn.disabled = true;
      try {
        await DASH.api.deleteStopImage(btn.dataset.removeImage);
        UI.toast('Evidence deleted', 'success');
        loaded = false;
        await load();
      } catch (err) {
        btn.disabled = false;
        UI.toast(`Could not delete: ${err.message}`, 'error', 6000);
      }
    });

    toggleBtn.addEventListener('click', () => {
      const opening = photosEl.style.display === 'none';
      photosEl.style.display = opening ? '' : 'none';
      if (!opening || loaded || loading) return;
      photosEl.innerHTML = '<span class="timeline-photos-status">Loading photos…</span>';
      load();
    });
  }

  // ── Proof upload ────────────────────────────────────────────────
  // The two photos a stop needs before it can be completed.
  //
  // Three inputs, one handler, because `capture` and `multiple` cannot be
  // combined: a browser that honours `capture` opens the camera for a single
  // shot and ignores `multiple` entirely. Collapsing to one input would mean
  // choosing which workflow to make worse, so all three exist —
  //   [data-upload-input]        `capture=environment`, one photo, straight
  //                              to the camera. The phone path, unchanged.
  //   [data-upload-video-input]  `capture=environment` with `accept=video/*`,
  //                              straight to the camcorder. Separate from the
  //                              photo input for the same reason it is
  //                              separate from the gallery one: `accept` with
  //                              both types makes the browser pick, and it
  //                              picks stills, so a combined button would be
  //                              a photo button wearing a video label.
  //   [data-upload-multi-input]  `multiple`, no capture, photos and video. The
  //                              gallery path, for a dispatcher who shot a
  //                              batch first or is working from a desktop.
  // None costs the others a tap, which matters for something pressed at
  // every stop of every run.
  //
  // Lives in the stop row rather than the pinned current-stop card: that
  // card is re-rendered by replacing its innerHTML whenever its content
  // changes, which on a poll mid-selection would discard the file input and
  // whatever the dispatcher had chosen. The row's nodes are stable.
  const PROOF_CATEGORIES = [
    ['unload', 'Unloaded goods'],
    ['door', 'Locked door / gate'],
  ];

  const photoReloaders = new Map(); // stop_id → () => void

  function buildUploadHtml(stopId) {
    const options = PROOF_CATEGORIES
      .map(([value, label]) => `<option value="${value}">${label}</option>`).join('');
    return `
            <div class="timeline-upload-wrap">
              <select class="timeline-upload-category" data-upload-category="${stopId}">${options}</select>
              <label class="btn-nav timeline-upload-btn">
                &#128248; Take photo
                <input type="file" accept="image/*" capture="environment"
                       data-upload-input="${stopId}" style="display:none;">
              </label>
              <label class="btn-nav timeline-upload-btn">
                &#127909; Record video
                <input type="file" accept="video/*" capture="environment"
                       data-upload-video-input="${stopId}" style="display:none;">
              </label>
              <label class="btn-nav timeline-upload-btn">
                &#128193; Add files
                <input type="file" accept="image/*,video/*" multiple
                       data-upload-multi-input="${stopId}" style="display:none;">
              </label>
              <span class="timeline-upload-status" data-upload-status="${stopId}"></span>
            </div>`;
  }

  function bindUpload(bodyEl, stopId) {
    const inputs = [
      bodyEl.querySelector(`[data-upload-input="${stopId}"]`),
      bodyEl.querySelector(`[data-upload-video-input="${stopId}"]`),
      bodyEl.querySelector(`[data-upload-multi-input="${stopId}"]`),
    ].filter(Boolean);
    const categoryEl = bodyEl.querySelector(`[data-upload-category="${stopId}"]`);
    const statusEl = bodyEl.querySelector(`[data-upload-status="${stopId}"]`);
    if (!inputs.length || !categoryEl || !statusEl) return;

    // All three inputs are disabled for the duration of a batch, not just the
    // one that fired: they upload to the same stop under the same category
    // dropdown, and a second batch started mid-flight would interleave its
    // progress counts into the shared status line.
    const setDisabled = (value) => inputs.forEach((el) => { el.disabled = value; });

    async function handleFiles(input) {
      const files = input.files ? Array.from(input.files) : [];
      if (!files.length) return;
      // Read once, up front: the dispatcher can change the dropdown while a
      // batch is in flight, and every file in one selection belongs to the
      // category that was showing when they picked it.
      const category = categoryEl.value;
      const label = (PROOF_CATEGORIES.find((c) => c[0] === category) || [, category])[1];

      setDisabled(true);
      let done = 0;
      const failures = [];
      try {
        for (const file of files) {
          statusEl.textContent = files.length > 1
            ? `Uploading ${done + failures.length + 1} of ${files.length}…`
            : 'Uploading…';
          try {
            // Sequential, not Promise.all: production is a single synchronous
            // worker, so firing a whole batch at once would queue them anyway
            // and starve every other dashboard request while they waited.
            // Same reasoning as delivery-export.js.
            await DASH.api.uploadStopImage(stopId, file, category);
            done += 1;
          } catch (err) {
            // One bad file must not abandon the rest of the batch — the
            // dispatcher would have no way to tell which of ten files
            // actually landed.
            failures.push(`${file.name || 'file'}: ${err.message}`);
          }
        }

        if (done && !failures.length) {
          statusEl.textContent = files.length > 1
            ? `${done} ${label} files saved`
            : `${label} saved`;
          UI.toast(done > 1 ? `${done} files uploaded` : 'Upload saved', 'success');
        } else if (done) {
          statusEl.textContent = `${done} saved, ${failures.length} failed`;
          UI.toast(`${failures.length} of ${files.length} failed: ${failures[0]}`, 'error', 6000);
        } else {
          statusEl.textContent = '';
          UI.toast(`Upload failed: ${failures[0]}`, 'error', 6000);
        }

        // The gallery caches its fetch, so without this the photos the
        // dispatcher just took would be missing from the panel directly
        // below the button they took them with. Once per batch, not per
        // file — a ten-photo selection should not fire ten refetches.
        if (done) {
          const reload = photoReloaders.get(String(stopId));
          if (reload) reload();
        }
      } finally {
        setDisabled(false);
        // Clearing the value matters: selecting the same file twice in a row
        // fires no change event otherwise, so a retry after a failure would
        // appear to do nothing.
        input.value = '';
      }
    }

    inputs.forEach((input) => {
      input.addEventListener('change', () => handleFiles(input));
    });
  }

  // ── Phase history ───────────────────────────────────────────────
  // Same lazy pattern as the photo gallery, with one deliberate difference:
  // photos cache forever, which is right for images and wrong here. This log
  // changes every time a button on the stop is pressed, so the cache is
  // invalidated by handleStopAction and the panel refetches while open.
  const historyReloaders = new Map(); // stop_id → () => void

  function historyRowsHtml(events) {
    return events.map((e) => {
      const when = formatTime(e.occurred_at);
      const from = e.from_status ? statusLabel(e.from_status) : '—';
      const move = `${from} &rarr; ${statusLabel(e.to_status)}`;
      const action = e.action === 'revert' ? ' <em>(reverted)</em>' : '';
      const reason = e.reason ? ` — ${escapeHtml(e.reason)}` : '';
      return `<div class="timeline-history-row">
                <span class="th-time">${escapeHtml(when)}</span>
                <span class="th-move">${move}${action}${reason}</span>
              </div>`;
    }).join('');
  }

  function bindHistoryToggle(bodyEl, stopId) {
    const toggleBtn = bodyEl.querySelector(`[data-history-toggle="${stopId}"]`);
    const historyEl = bodyEl.querySelector(`[data-history-for="${stopId}"]`);
    if (!toggleBtn || !historyEl) return;

    let loading = false;

    async function load() {
      if (loading) return;
      loading = true;
      try {
        const events = await DASH.api.stopHistory(stopId);
        if (!events || events.length === 0) {
          // Distinguishes "nothing has happened to this stop yet" from
          // "this stop predates the log" — the second is permanent, and a
          // dispatcher looking for a missing record deserves to know which.
          historyEl.innerHTML =
            '<span class="timeline-history-status">No phase changes recorded for this stop</span>';
          return;
        }
        historyEl.innerHTML = historyRowsHtml(events);
      } catch (err) {
        historyEl.innerHTML =
          `<span class="timeline-history-status">Failed to load history: ${escapeHtml(err.message)}</span>`;
      } finally {
        loading = false;
      }
    }

    historyReloaders.set(String(stopId), () => {
      if (historyEl.style.display !== 'none') load();
    });

    toggleBtn.addEventListener('click', () => {
      const opening = historyEl.style.display === 'none';
      historyEl.style.display = opening ? '' : 'none';
      if (!opening) return;
      historyEl.innerHTML = '<span class="timeline-history-status">Loading history…</span>';
      load();
    });
  }

  function refreshHistoryFor(stopId) {
    const reload = historyReloaders.get(String(stopId));
    if (reload) reload();
  }

  function buildDetailHtml(s, execStatus, eta) {
    return `
              <div class="timeline-detail">
                ${s.station_code ? '<span class="label">Code:</span><span class="value">' + escapeHtml(s.station_code) + '</span>' : ''}
                <span class="label">Status:</span><span class="value">${statusLabel(execStatus)}</span>
                ${s.address ? '<span class="label">Address:</span><span class="value">' + escapeHtml(s.address) + '</span>' : ''}
                ${s.lat && s.lng ? '<span class="label">Coords:</span><span class="value">' + parseFloat(s.lat).toFixed(5) + ', ' + parseFloat(s.lng).toFixed(5) + '</span>' : ''}
                ${s.manager_name ? '<span class="label">Manager:</span><span class="value">' + escapeHtml(s.manager_name) + '</span>' : ''}
                ${s.manager_phone ? '<span class="label">Phone:</span><span class="value"><a class="tel-link" href="tel:' + escapeHtml(s.manager_phone.replace(/[^0-9+]/g, '')) + '">' + escapeHtml(s.manager_phone) + '</a></span>' : ''}
                ${s.product_description ? '<span class="label">Product:</span><span class="value">' + escapeHtml(s.product_description) + '</span>' : ''}
                <span class="label">Arrival:</span><span class="value">${formatTime(s.actual_arrival_at)}</span>
                <span class="label">Departure:</span><span class="value">${formatTime(s.actual_departure_at)}</span>
                ${etaCellHtml(eta)}
                ${s.note ? '<span class="label">Notes:</span><span class="value" style="font-style:italic;">' + escapeHtml(s.note) + '</span>' : ''}
                ${s.skip_reason ? '<span class="label">Skip reason:</span><span class="value">' + escapeHtml(s.skip_reason) + '</span>' : ''}
                ${s.cancel_reason ? '<span class="label">Cancel reason:</span><span class="value">' + escapeHtml(s.cancel_reason) + '</span>' : ''}
              </div>
              ${buildActionsHtml(s, execStatus)}`;
  }

  function createStop(s) {
    const execStatus = s.execution_status || 'planned';
    const isCompleted = ['completed', 'skipped', 'cancelled'].includes(execStatus);

    const el = document.createElement('div');
    el.className = 'timeline-item';
    el.dataset.stopId = s.id;
    el.innerHTML = `
          <div class="timeline-header" data-toggle="${s.id}">
            <span class="timeline-seq"></span>
            <span class="timeline-station"></span>
            <span class="status-badge"></span>
            <span class="timeline-move" data-move-for="${s.id}">
              <button class="timeline-move-btn" data-move="up" title="Move earlier" aria-label="Move stop earlier">&#9650;</button>
              <button class="timeline-move-btn" data-move="down" title="Move later" aria-label="Move stop later">&#9660;</button>
            </span>
            <span class="timeline-chevron" data-chevron="${s.id}">&#9660;</span>
          </div>
          <div class="timeline-body" data-body="${s.id}">
            <div class="timeline-detail-wrap"></div>
            ${buildUploadHtml(s.id)}
            <div class="timeline-photos-wrap">
              <button class="btn-nav timeline-photos-toggle" data-photos-toggle="${s.id}">&#128247; Photos</button>
              <div class="timeline-photos" data-photos-for="${s.id}" style="display:none;"></div>
            </div>
            <div class="timeline-history-wrap">
              <button class="btn-nav timeline-history-toggle" data-history-toggle="${s.id}">&#128337; History</button>
              <div class="timeline-history" data-history-for="${s.id}" style="display:none;"></div>
            </div>
          </div>`;

    const headerEl = el.querySelector('.timeline-header');
    const bodyEl = el.querySelector('.timeline-body');
    const detailWrapEl = el.querySelector('.timeline-detail-wrap');
    const chevronEl = el.querySelector('.timeline-chevron');

    // Default open/closed only on first creation — later polls never touch this.
    if (!isCompleted) {
      bodyEl.classList.add('open');
      chevronEl.classList.add('open');
    }

    // Delegated listeners bound once — survive every future content patch,
    // so action buttons never need rebinding on poll.
    headerEl.addEventListener('click', (e) => {
      // A move button sits inside the header, whose click collapses the stop.
      // Reordering a stop and collapsing it are unrelated intents.
      const moveBtn = e.target.closest('[data-move]');
      if (moveBtn) {
        e.stopPropagation();
        moveStop(s.id, moveBtn.dataset.move === 'up' ? -1 : 1);
        return;
      }
      bodyEl.classList.toggle('open');
      chevronEl.classList.toggle('open');
      focusStopOnMap(s.id);
    });

    bindActionDelegation(detailWrapEl);
    bindUpload(bodyEl, s.id);
    bindPhotosToggle(bodyEl, s.id);
    bindHistoryToggle(bodyEl, s.id);

    return {
      el,
      seqEl: el.querySelector('.timeline-seq'),
      stationEl: el.querySelector('.timeline-station'),
      badgeEl: el.querySelector('.status-badge'),
      moveWrapEl: el.querySelector('.timeline-move'),
      moveUpEl: el.querySelector('[data-move="up"]'),
      moveDownEl: el.querySelector('[data-move="down"]'),
      detailWrapEl,
      itemClass: '',
      detailHtml: null,
    };
  }

  DASH.timeline = {
    _stopNodes: new Map(), // stop_id → node refs
    _setKey: null,
    _currentStopCardHtml: null,
    _currentStopCardBound: false,

    // The keyboard shortcuts in main.js must not fire while a skip/cancel
    // reason is mid-typing — 'a' would otherwise advance a stop under the
    // dispatcher's hands. Reuses the set that already suppresses content
    // patching for the same rows rather than tracking open state twice.
    hasOpenReasonRow() {
      return openReasonStopIds.size > 0;
    },

    // Full rebuild only when the set of stop ids changes (vehicle selection
    // switch, or a stop inserted); a same-assignment poll only patches the
    // header (status/seq/name) and swaps each stop's detail content when it
    // actually changed — collapse state, photo-gallery state, and button
    // bindings are untouched.
    render(stops, currentStopId, etas, emptyMessage) {
      const container = document.getElementById('timeline');
      const countEl = document.getElementById('stopCount');
      const list = stops || [];

      this._renderCurrentStopCard(list, currentStopId, etas);

      if (list.length === 0) {
        container.innerHTML =
          `<div class="empty-state">${escapeHtml(emptyMessage || 'Select a vehicle to view stops')}</div>`;
        if (countEl) countEl.textContent = '';
        this._stopNodes.clear();
        this._setKey = null;
        openReasonStopIds.clear();
        return;
      }

      if (countEl) countEl.textContent = list.length;

      // Order-independent on purpose. A reorder changes the sequence but not
      // the membership, and it is reconciled by moving the existing nodes
      // below — wiping the container would collapse every stop and drop any
      // open photo gallery, which is exactly the state a dispatcher is
      // mid-way through using when they resequence a route.
      const key = list.map((s) => s.id).sort((a, b) => a - b).join(',');
      if (key !== this._setKey) {
        // Any reason row belonged to DOM nodes being torn down below — an
        // abandoned (never confirmed/cancelled) edit must not permanently
        // freeze that stop's content on a future rebuild (its "open" state
        // no longer exists once the old node is gone).
        openReasonStopIds.clear();
        container.innerHTML = '';
        this._stopNodes.clear();
        this._setKey = key;
      }

      etaBaselineMs = (etas && etas._receivedAt) || null;

      const etaMap = {};
      if (etas && etas.etas) {
        etas.etas.forEach((e) => {
          if (e.stop_id != null) etaMap[e.stop_id] = e.eta_seconds != null ? e.eta_seconds : (e.eta || '--');
        });
      }

      this._renderRestrictionBanner(etas);

      list.forEach((s, idx) => {
        let entry = this._stopNodes.get(s.id);
        if (!entry) {
          entry = createStop(s);
          this._stopNodes.set(s.id, entry);
        }
        // insertBefore *moves* a node that is already in the container, so
        // this both places new stops and applies a reorder.
        if (container.children[idx] !== entry.el) {
          container.insertBefore(entry.el, container.children[idx] || null);
        }
        this._patchStop(entry, s, currentStopId, etaMap[s.id], list, idx);
      });
    },

    // One banner for the whole route rather than a warning per stop. The
    // dispatcher's question is "is this route safe for this truck", which is
    // answered once; repeating it on every affected stop would be noise, and
    // threading it through _patchStop would put new state inside the diffing
    // renderer for no gain. The map already says *which* legs are affected.
    //
    // Note this is per-selected-vehicle only: /api/execution/dashboard does no
    // routing, so there is no fleet-wide restriction signal to put in the
    // vehicle list without an ORS call per truck per poll.
    _renderRestrictionBanner(etas) {
      const el = document.getElementById('restrictionBanner');
      if (!el) return;

      const legs = (etas && etas.etas) || [];
      const violated = legs.filter((l) => l.restriction_status === 'violated').length;
      const source = etas && etas.restrictions_source;
      const restrictions = (etas && etas.restrictions) || {};

      // Nothing routed yet, or nothing worth saying.
      if (legs.length === 0 || (violated === 0 && source !== 'type_default' && source !== 'mixed' && source !== 'none')) {
        if (el.style.display !== 'none') {
          el.style.display = 'none';
          el.innerHTML = '';
        }
        return;
      }

      const limits = [];
      if (restrictions.height) limits.push(`${restrictions.height} m tall`);
      if (restrictions.width) limits.push(`${restrictions.width} m wide`);
      if (restrictions.length) limits.push(`${restrictions.length} m long`);
      if (restrictions.weight) limits.push(`${restrictions.weight} t`);
      const limitText = limits.length ? limits.join(' · ') : 'no limits recorded';

      let cls = 'restriction-banner';
      let html = '';

      if (violated > 0) {
        cls += ' violated';
        html = `<strong>${violated} leg${violated === 1 ? '' : 's'} shown in red exceed this vehicle's limits.</strong>
          <span>No route respecting ${escapeHtml(limitText)} was found, so the red sections ignore those limits.
          They may not be legal or physically passable for this truck — check before dispatching.</span>`;
      } else if (source === 'none') {
        cls += ' unchecked';
        html = `<strong>Route not checked against this vehicle.</strong>
          <span>No dimensions or weight are recorded for it, and its type has no estimate.</span>`;
      } else {
        cls += ' estimated';
        html = `<strong>Routed on estimated dimensions.</strong>
          <span>Using ${escapeHtml(limitText)} from the vehicle type${source === 'mixed' ? ' for the values this vehicle is missing' : ''},
          not its registration certificate.</span>`;
      }

      if (el.className !== cls) el.className = cls;
      if (el.innerHTML !== html) el.innerHTML = html;
      el.style.display = '';
    },

    // Resets to the empty state and drops the node cache — use this instead
    // of touching #timeline's innerHTML directly, or the cache above goes
    // stale (its nodes get detached without the module knowing).
    //
    // `message` lets a caller distinguish "nothing selected" from "selected,
    // waiting on the server", which are very different things to a dispatcher
    // who has just clicked a truck.
    clear(message) {
      this.render([], null, null, message);
    },

    _patchStop(entry, s, currentStopId, eta, list, idx) {
      const execStatus = s.execution_status || 'planned';
      const isCurrent = currentStopId && s.id === currentStopId;
      const isCompleted = ['completed', 'skipped', 'cancelled'].includes(execStatus);
      const itemClass = isCurrent ? 'timeline-item current' : isCompleted ? 'timeline-item completed' : 'timeline-item';
      if (entry.itemClass !== itemClass) {
        entry.el.className = itemClass;
        entry.itemClass = itemClass;
      }

      setText(entry.seqEl, displaySeq(s));
      setText(entry.stationEl, s.station_name || s.station_code || 'Stop');

      if (entry.moveWrapEl) {
        const neighbours = list || [];
        const here = idx == null ? -1 : idx;
        const prev = here > 0 ? neighbours[here - 1] : null;
        const next = here >= 0 ? neighbours[here + 1] : null;
        const movable = !isTerminal(s);
        entry.moveWrapEl.style.display = movable ? '' : 'none';
        entry.moveUpEl.disabled = !(movable && prev && !isTerminal(prev));
        entry.moveDownEl.disabled = !(movable && next && !isTerminal(next));
      }

      const badgeClass = 'status-badge ' + statusClass(execStatus);
      if (entry.badgeEl.className !== badgeClass) entry.badgeEl.className = badgeClass;
      setText(entry.badgeEl, statusLabel(execStatus));

      if (openReasonStopIds.has(String(s.id))) return;

      const detailHtml = buildDetailHtml(s, execStatus, eta);
      if (entry.detailHtml !== detailHtml) {
        entry.detailWrapEl.innerHTML = detailHtml;
        entry.detailHtml = detailHtml;
      }
    },

    // Pinned mini-card at the top of the panel: the current stop's contact
    // info and primary actions, always visible regardless of where the
    // dispatcher has scrolled the timeline below.
    _renderCurrentStopCard(stops, currentStopId, etas) {
      const card = document.getElementById('currentStopCard');
      if (!card) return;
      if (!this._currentStopCardBound) {
        this._currentStopCardBound = true;
        bindActionDelegation(card);
        // Same locate-on-click as a timeline row. The pinned card is the stop a
        // dispatcher asks "where is that?" about most often.
        card.addEventListener('click', (e) => {
          // Advance/Skip/Cancel, the tel: link and the reason input all live in
          // this card and mean something else entirely.
          if (e.target.closest('button, a, input')) return;
          const stopId = parseInt(card.dataset.stopId || '', 10);
          if (stopId) focusStopOnMap(stopId);
        });
      }

      const stop = currentStopId ? stops.find((s) => s.id === currentStopId) : null;
      if (!stop) {
        card.style.display = 'none';
        this._currentStopCardHtml = null;
        delete card.dataset.stopId;
        return;
      }
      // Read by the locate-on-click handler above, which is bound once and so
      // can't close over whichever stop happens to be current.
      card.dataset.stopId = stop.id;

      let eta = null;
      if (etas && etas.etas) {
        const match = etas.etas.find((e) => e.stop_id === stop.id);
        if (match) eta = match.eta_seconds != null ? match.eta_seconds : match.eta;
      }

      const execStatus = stop.execution_status || 'planned';
      const phone = (stop.manager_phone || '').trim();
      const phoneHtml = phone
        ? `<a class="cs-phone" href="tel:${escapeHtml(phone.replace(/[^0-9+]/g, ''))}">&#128222; ${escapeHtml(phone)}</a>`
        : '';
      const etaClock = UI.etaClock(eta, etas && etas._receivedAt);
      const etaText = etaClock ? `ETA ${etaClock}` : '';
      const etaTitle = etaClock ? ` title="in ${escapeHtml(UI.etaRelative(eta))}"` : '';

      const html = `
              <div class="cs-header">
                <span class="cs-label">Current Stop</span>
                <span class="status-badge ${statusClass(execStatus)}">${statusLabel(execStatus)}</span>
              </div>
              <div class="cs-station">#${displaySeq(stop)} ${escapeHtml(stop.station_name || stop.station_code || 'Stop')}</div>
              <div class="cs-detail">
                ${stop.address ? `<div class="cs-address">${escapeHtml(stop.address)}</div>` : ''}
                ${stop.manager_name ? `<div class="cs-manager">${escapeHtml(stop.manager_name)}</div>` : ''}
                ${phoneHtml}
                ${etaText ? `<div class="cs-eta"${etaTitle}>${etaText}</div>` : ''}
              </div>
              ${buildActionsHtml(stop, execStatus)}`;

      card.style.display = '';
      if (openReasonStopIds.has(String(stop.id))) return;
      if (this._currentStopCardHtml !== html) {
        card.innerHTML = html;
        this._currentStopCardHtml = html;
      }
    },
  };
})();
