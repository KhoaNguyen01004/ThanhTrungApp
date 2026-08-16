(function () {
  'use strict';

  // ================================================================
  // State
  // ================================================================
  let state = {
    currentStep: 1,
    planId: null,
    planInfo: { plan_name: '', plan_date: '', description: '' },
    assignments: [],
    readOnly: false,
    isDirty: false,
    isSaving: false,
    autoSaveTimer: null,
    stationDb: [], // persisted in localStorage
  };

  let nextAssignmentId = 1;
  let nextStopId = 1;

  // ================================================================
  // DOM refs
  // ================================================================
  const $ = (id) => document.getElementById(id);
  const $$ = (sel) => document.querySelectorAll(sel);

  const stepIndicator = $('stepIndicator');
  const panels = {
    1: $('step1Panel'),
    2: $('step2Panel'),
    3: $('step3Panel'),
    4: $('step4Panel'),
    5: $('step5Panel'),
  };

  // ================================================================
  // Utilities
  // ================================================================
  function formatCoords(v) {
    if (v == null || v === '') return '';
    return parseFloat(v).toFixed(6);
  }

  function loadStationDb() {
    try {
      const raw = localStorage.getItem('planBuilder_stations');
      state.stationDb = raw ? JSON.parse(raw) : [];
    } catch { state.stationDb = []; }
  }

  function saveStationToDb(stop) {
    const key = (stop.station_code || stop.station_name || '').trim().toLowerCase();
    if (!key) return;
    const existing = state.stationDb.findIndex(
      (s) => (s.station_code || '').toLowerCase() === key || (s.station_name || '').toLowerCase() === key
    );
    const entry = {
      station_code: stop.station_code || '',
      station_name: stop.station_name || '',
      address: stop.address || '',
      lat: stop.lat,
      lng: stop.lng,
      manager_name: stop.manager_name || '',
      manager_phone: stop.manager_phone || '',
    };
    if (existing >= 0) {
      state.stationDb[existing] = entry;
    } else {
      state.stationDb.push(entry);
    }
    try { localStorage.setItem('planBuilder_stations', JSON.stringify(state.stationDb)); } catch {}
  }

  function totalStops() {
    return state.assignments.reduce((sum, a) => sum + a.stops.length, 0);
  }

  function markDirty() {
    state.isDirty = true;
    updateAutoSaveIndicator();
  }

  function markClean() {
    state.isDirty = false;
    updateAutoSaveIndicator();
  }

  // ================================================================
  // Step Indicator
  // ================================================================
  function updateStepIndicator() {
    const steps = stepIndicator.querySelectorAll('.step');
    const connectors = stepIndicator.querySelectorAll('.step-connector');
    steps.forEach((s, i) => {
      const num = i + 1;
      s.classList.toggle('step-active', num === state.currentStep);
      s.classList.toggle('step-completed', num < state.currentStep);
    });
    connectors.forEach((c, i) => {
      c.classList.toggle('completed', i + 1 < state.currentStep);
    });
  }

  function showPanel(step) {
    Object.entries(panels).forEach(([key, el]) => {
      el.style.display = String(key) === String(step) ? '' : 'none';
    });
    updateStepIndicator();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  // ================================================================
  // Data fetching
  // ================================================================
  async function fetchJSON(url, opts) {
    const resp = await fetch(url, opts);
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));

      // Delivery endpoints return raw JSON rather than utils.js's
      // {success: ...} envelope, so this page can't use ApiClient directly.
      const err = new Error(body.error || body.message || `HTTP ${resp.status}`);
      // Status and body are attached so callers can distinguish *why* a call
      // failed. The sheet importer needs this: a 409 with reason
      // 'in_progress' offers the dispatcher an override, while a 409 with
      // reason 'unknown_vehicles' has no override and must not offer one.
      // The message is unchanged, so existing callers behave as before.
      err.status = resp.status;
      err.body = body;
      throw err;
    }
    return resp.json();
  }

  async function loadVehicles() {
    try {
      const data = await fetchJSON('/api/fleet/vehicles');
      state.vehicles = data.data || [];
    } catch (e) {
      console.error('Failed to load vehicles:', e);
      state.vehicles = [];
    }
  }

  async function loadDrivers() {
    try {
      state.drivers = await fetchJSON('/api/drivers');
    } catch (e) {
      console.error('Failed to load drivers:', e);
      state.drivers = [];
    }
  }

  // ================================================================
  // Auto-save
  // ================================================================
  function updateAutoSaveIndicator() {
    const el = $('autoSaveIndicator');
    if (!el) return;
    if (state.isSaving) {
      el.textContent = 'Saving...';
      el.className = 'auto-save-saving';
    } else if (state.isDirty) {
      el.textContent = 'Unsaved changes';
      el.className = 'auto-save-dirty';
    } else if (state.planId) {
      el.textContent = 'Saved';
      el.className = 'auto-save-saved';
    } else {
      el.textContent = '';
      el.className = '';
    }
  }

  function startAutoSave() {
    if (state.autoSaveTimer) return;
    state.autoSaveTimer = setInterval(async () => {
      if (state.isDirty && !state.isSaving && state.planId) {
        await saveDraft(true);
      }
    }, 30000);
  }

  function stopAutoSave() {
    if (state.autoSaveTimer) {
      clearInterval(state.autoSaveTimer);
      state.autoSaveTimer = null;
    }
  }

  window.addEventListener('beforeunload', (e) => {
    if (state.isDirty && !state.isSaving) {
      e.preventDefault();
      e.returnValue = 'You have unsaved changes. Leave anyway?';
    }
  });

  // ================================================================
  // Step 1 — Plan Information
  // ================================================================
  function renderStep1() {
    $('planName').value = state.planInfo.plan_name;
    $('planDate').value = state.planInfo.plan_date;
    $('planDescription').value = state.planInfo.description;
    if (!$('planDate').value) {
      $('planDate').value = new Date().toISOString().slice(0, 10);
    }
  }

  function saveStep1() {
    const name = $('planName').value.trim();
    const date = $('planDate').value;
    const desc = $('planDescription').value.trim();

    clearValidation($('planName'));
    clearValidation($('planDate'));

    let valid = true;
    if (!name) { showValidation($('planName'), 'Plan name is required'); valid = false; }
    if (!date) { showValidation($('planDate'), 'Plan date is required'); valid = false; }

    if (!valid) return false;

    if (state.planInfo.plan_name !== name || state.planInfo.plan_date !== date || state.planInfo.description !== desc) {
      markDirty();
    }
    state.planInfo.plan_name = name;
    state.planInfo.plan_date = date;
    state.planInfo.description = desc;
    return true;
  }

  // ================================================================
  // Step 2 — Vehicle Assignments
  // ================================================================
  function renderStep2() {
    renderAssignmentsList();
  }

  function renderAssignmentsList() {
    const container = $('assignmentsList');
    if (state.assignments.length === 0) {
      container.innerHTML = '<div class="empty-state">No vehicles added yet. Click "+ Add Vehicle" to begin.</div>';
      return;
    }
    let html = '';
    state.assignments.forEach((a) => {
      const vehicle = state.vehicles.find((v) => String(v.id) === String(a.vehicle_id));
      const driver = state.drivers.find((d) => d.id && String(d.id) === String(a.driver_id));
      const vlabel = vehicle ? vehicle.plate_number : 'Unknown';
      var dlabel = 'Unknown';
      if (driver) { dlabel = driver.name; }
      else if (a._driverName) { dlabel = a._driverName; }
      else if (vehicle && vehicle.current_driver) { dlabel = vehicle.current_driver + ' (auto)'; }
      html += `
        <div class="assignment-card">
          <div class="assignment-info">
            <div class="assignment-vehicle">${UI.escapeHtml(vlabel)}</div>
            <div class="assignment-driver">Driver: ${UI.escapeHtml(dlabel)}</div>
            ${a.notes ? `<div class="assignment-notes">${UI.escapeHtml(a.notes)}</div>` : ''}
          </div>
          <div class="assignment-actions">
            <button class="btn-secondary" data-edit-assignment="${a._id}" title="Edit">Edit</button>
            <button class="btn-secondary" data-duplicate-assignment="${a._id}" title="Duplicate">Copy</button>
            <button class="btn-danger" data-remove-assignment="${a._id}" title="Remove">Delete</button>
          </div>
        </div>`;
    });
    container.innerHTML = html;

    container.querySelectorAll('[data-edit-assignment]').forEach((btn) => {
      btn.addEventListener('click', () => openAssignmentModal(btn.dataset.editAssignment));
    });
    container.querySelectorAll('[data-duplicate-assignment]').forEach((btn) => {
      btn.addEventListener('click', () => duplicateAssignment(btn.dataset.duplicateAssignment));
    });
    container.querySelectorAll('[data-remove-assignment]').forEach((btn) => {
      btn.addEventListener('click', () => removeAssignment(btn.dataset.removeAssignment));
    });
  }

  let _selectedVehicleId = null;
  let _vehicleAutocompleteBound = false;
  let _selectedDriverId = null;
  let _driverAutocompleteBound = false;
  let _driverCustomText = null;

  function _bindVehicleAutocomplete() {
    if (_vehicleAutocompleteBound) return;
    _vehicleAutocompleteBound = true;

    const input = $('assignVehicle');
    const list = $('vehicleAutocompleteList');
    const selD = $('assignDriver');

    list.addEventListener('click', function (e) {
      const item = e.target.closest('.autocomplete-item');
      if (!item) return;
      const v = state.vehicles.find((x) => String(x.id) === String(item.dataset.vid));
      if (!v) return;
      _selectedVehicleId = String(v.id);
      input.value = v.plate_number + (v.current_driver ? ' \u2014 ' + v.current_driver : '');
      list.style.display = 'none';
      const drvName = (v.current_driver || '').trim();
      if (drvName) {
        selD.value = drvName;
        var match = state.drivers.find(function (d) { return d.name.toLowerCase() === drvName.toLowerCase(); });
        if (match && match.id) {
          _selectedDriverId = String(match.id);
          _driverCustomText = null;
        } else {
          _selectedDriverId = null;
          _driverCustomText = drvName;
        }
      }
    });

    input.addEventListener('input', function () {
      _selectedVehicleId = null;
      if (this.value.trim()) {
        const q = this.value.toLowerCase().trim();
        const matches = state.vehicles.filter((v) =>
          (v.plate_number || '').toLowerCase().includes(q) ||
          (v.current_driver || '').toLowerCase().includes(q)
        );
        if (matches.length === 0) { list.style.display = 'none'; return; }
        list.innerHTML = matches.map((v) =>
          `<div class="autocomplete-item" data-vid="${v.id}">
            <strong>${UI.escapeHtml(v.plate_number)}</strong>
            <small class="autocomplete-type">${UI.escapeHtml(v.current_driver || 'No driver')}</small>
          </div>`
        ).join('');
        list.style.display = '';
      } else {
        list.style.display = 'none';
      }
      selD.value = '';
    });

    input.addEventListener('focus', function () {
      if (!_selectedVehicleId && state.vehicles.length <= 20) {
        const q = this.value.trim().toLowerCase();
        const matches = state.vehicles.filter((v) =>
          (v.plate_number || '').toLowerCase().includes(q) ||
          (v.current_driver || '').toLowerCase().includes(q)
        );
        if (matches.length === 0) { list.style.display = 'none'; return; }
        list.innerHTML = matches.map((v) =>
          `<div class="autocomplete-item" data-vid="${v.id}">
            <strong>${UI.escapeHtml(v.plate_number)}</strong>
            <small class="autocomplete-type">${UI.escapeHtml(v.current_driver || 'No driver')}</small>
          </div>`
        ).join('');
        list.style.display = '';
      }
    });

    document.addEventListener('click', function _closeVehicleList(e) {
      if (!e.target.closest('.autocomplete-wrapper')) {
        list.style.display = 'none';
      }
    });
  }

  function _bindDriverAutocomplete() {
    if (_driverAutocompleteBound) return;
    _driverAutocompleteBound = true;

    const input = $('assignDriver');
    const list = $('driverAutocompleteList');
    const modal = $('assignmentModal');

    function render(q) {
      _selectedDriverId = null;
      _driverCustomText = null;
      if (!q) { list.style.display = 'none'; return; }
      const lq = q.toLowerCase();
      var items = [];
      var seen = {};
      state.drivers.forEach(function (d) {
        var name = d.name || '';
        if (name.toLowerCase().includes(lq) && !seen[name.toLowerCase()]) {
          items.push({ label: name, id: d.id });
          seen[name.toLowerCase()] = true;
        }
      });
      items.sort(function (a, b) { return a.label.localeCompare(b.label); });
      if (items.length === 0) {
        list.innerHTML = '<div class="autocomplete-item muted" style="cursor:default;opacity:0.6;">No matching drivers</div>';
        list.style.display = '';
        return;
      }
      list.innerHTML = items.map(function (d) {
        return '<div class="autocomplete-item" data-driver-id="' + (d.id || '') + '">' + UI.escapeHtml(d.label) + '</div>';
      }).join('');
      list.style.display = '';
    }

    list.addEventListener('click', function (e) {
      var item = e.target.closest('.autocomplete-item');
      if (!item || !('driverId' in item.dataset)) return;
      input.value = item.textContent;
      list.style.display = 'none';
      var rawId = item.dataset.driverId;
      if (rawId && rawId !== '') {
        _selectedDriverId = rawId;
        _driverCustomText = null;
      } else {
        _selectedDriverId = null;
        _driverCustomText = item.textContent;
      }
    });

    input.addEventListener('input', function () {
      render(this.value.trim());
    });

    input.addEventListener('focus', function () {
      if (!_selectedDriverId && !_driverCustomText) {
        render(this.value.trim());
      }
    });

    document.addEventListener('click', function _closeDriverList(e) {
      if ($('assignmentModal').style.display !== 'none' && !e.target.closest('#assignmentModal .autocomplete-wrapper')) {
        list.style.display = 'none';
      }
    });

    modal.addEventListener('scroll', function () { if ($('assignmentModal').style.display !== 'none') list.style.display = 'none'; }, true);
  }

  function openAssignmentModal(editId) {
    state.editingAssignmentId = editId || null;
    const isEdit = !!state.editingAssignmentId;
    $('assignmentModalTitle').textContent = isEdit ? 'Edit Vehicle Assignment' : 'Add Vehicle Assignment';

    _bindVehicleAutocomplete();
    _bindDriverAutocomplete();

    const input = $('assignVehicle');
    const drvInput = $('assignDriver');
    _selectedVehicleId = null;
    _selectedDriverId = null;
    _driverCustomText = null;
    drvInput.value = '';
    $('assignNotes').value = '';
    $('driverAutocompleteList').style.display = 'none';

    if (isEdit) {
      const a = state.assignments.find((x) => x._id === editId);
      if (a) {
        const v = state.vehicles.find((x) => String(x.id) === String(a.vehicle_id));
        if (v) {
          _selectedVehicleId = String(v.id);
          input.value = v.plate_number + (v.current_driver ? ' \u2014 ' + v.current_driver : '');
        }
        if (a.driver_id) {
          const match = state.drivers.find(function (d) { return String(d.id) === String(a.driver_id); });
          if (match) {
            drvInput.value = match.name;
            _selectedDriverId = String(match.id);
          }
        } else if (a._driverName) {
          drvInput.value = a._driverName;
          _driverCustomText = a._driverName;
        } else if (v && v.current_driver) {
          drvInput.value = v.current_driver;
          _driverCustomText = v.current_driver;
        }
        $('assignNotes').value = a.notes || '';
      }
    }

    $('assignmentModal').style.display = '';
    setTimeout(() => input.focus(), 100);
  }

  function saveAssignmentFromModal() {
    const vehicleId = _selectedVehicleId;
    var driverId = null;
    if (_selectedDriverId) {
      driverId = _selectedDriverId;
    }
    const notes = $('assignNotes').value.trim();

    if (!vehicleId) { alert('Please select a vehicle.'); return false; }

    var driverName = null;
    if (_selectedDriverId) {
      var d = state.drivers.find(function (x) { return String(x.id) === String(_selectedDriverId); });
      if (d) driverName = d.name;
    } else {
      var drvText = ($('assignDriver').value || '').trim();
      if (drvText) driverName = drvText;
    }

    if (state.editingAssignmentId) {
      const existing = state.assignments.find((a) => a._id === state.editingAssignmentId);
      if (existing) {
        existing.vehicle_id = vehicleId;
        existing.driver_id = driverId;
        existing._driverName = driverName;
        existing.notes = notes;
      }
    } else {
      state.assignments.push({
        _id: String(nextAssignmentId++),
        vehicle_id: vehicleId,
        driver_id: driverId,
        _driverName: driverName,
        notes: notes,
        stops: [],
      });
    }

    $('assignVehicle').value = '';
    _selectedVehicleId = null;
    $('assignmentModal').style.display = 'none';
    state.editingAssignmentId = null;
    markDirty();
    renderAssignmentsList();
    renderAssignmentTabs();
    return true;
  }

  function duplicateAssignment(id) {
    const a = state.assignments.find((x) => x._id === id);
    if (!a) return;
    const newA = {
      _id: String(nextAssignmentId++),
      vehicle_id: a.vehicle_id,
      driver_id: a.driver_id,
      _driverName: a._driverName || null,
      notes: (a.notes || '') + ' (copy)',
      stops: a.stops.map((s) => ({ ...s, _id: String(nextStopId++) })),
    };
    state.assignments.push(newA);
    markDirty();
    renderAssignmentsList();
    renderAssignmentTabs();
  }

  function removeAssignment(id) {
    if (!confirm('Remove this vehicle assignment and all its stops?')) return;
    state.assignments = state.assignments.filter((a) => a._id !== id);
    if (selectedAssignmentId === id) {
      selectedAssignmentId = state.assignments.length > 0 ? state.assignments[0]._id : null;
    }
    markDirty();
    renderAssignmentsList();
    if (state.currentStep === 3) renderStep3();
  }

  // ================================================================
  // Step 3 — Stops
  // ================================================================
  let selectedAssignmentId = null;
  let dragSourceId = null;

  function renderStep3() {
    renderAssignmentTabs();
    if (state.assignments.length > 0) {
      if (!selectedAssignmentId || !state.assignments.find((a) => a._id === selectedAssignmentId)) {
        selectedAssignmentId = state.assignments[0]._id;
      }
      selectAssignmentTab(selectedAssignmentId);
    } else {
      selectedAssignmentId = null;
      $('stopsAssignmentTitle').textContent = 'No vehicles added yet. Go back to Step 2.';
      $('addStopBtn').style.display = 'none';
      $('stopsList').innerHTML = '<div class="empty-state">Add vehicles in Step 2 first</div>';
    }
  }

  function renderAssignmentTabs() {
    const container = $('assignmentTabs');
    if (state.assignments.length === 0) { container.innerHTML = ''; return; }
    let html = '';
    state.assignments.forEach((a) => {
      const vehicle = state.vehicles.find((v) => String(v.id) === String(a.vehicle_id));
      const label = vehicle ? vehicle.plate_number : 'Vehicle';
      const active = a._id === selectedAssignmentId ? ' assignment-tab-active' : '';
      html += `<div class="assignment-tab${active}" data-tab-id="${a._id}">${UI.escapeHtml(label)} <span class="stop-count">(${a.stops.length})</span></div>`;
    });
    container.innerHTML = html;
    container.querySelectorAll('.assignment-tab').forEach((tab) => {
      tab.addEventListener('click', () => selectAssignmentTab(tab.dataset.tabId));
    });
  }

  function selectAssignmentTab(id) {
    selectedAssignmentId = id;
    renderAssignmentTabs();
    const a = state.assignments.find((x) => x._id === id);
    if (!a) return;
    const vehicle = state.vehicles.find((v) => String(v.id) === String(a.vehicle_id));
    const label = vehicle ? vehicle.plate_number : 'Vehicle';
    $('stopsAssignmentTitle').textContent = `Stops for ${UI.escapeHtml(label)}`;
    $('addStopBtn').style.display = '';
    renderStopsList(id);
  }

  function renderStopsList(assignmentId) {
    const container = $('stopsList');
    const a = state.assignments.find((x) => x._id === assignmentId);
    if (!a || a.stops.length === 0) {
      container.innerHTML = '<div class="empty-state">No stops yet. Click "+ Add Stop" to add one.</div>';
      return;
    }
    let html = '';
    a.stops.forEach((s, idx) => {
      const errors = validateStop(s);
      const errorBadge = errors.length > 0 ? `<span class="stop-error-badge" title="${UI.escapeHtml(errors.join('; '))}">!</span>` : '';
      html += `
        <div class="stop-card" draggable="true" data-stop-id="${s._id}" data-assignment-id="${assignmentId}">
          <span class="stop-drag-handle" title="Drag to reorder">&#9776;</span>
          <span class="stop-order">${idx + 1}</span>
          <div class="stop-info">
            <div class="stop-name">${UI.escapeHtml(s.station_name || s.station_code || 'Unnamed')}${errorBadge}</div>
            <div class="stop-details">
              ${s.station_code ? `<span>Code: ${UI.escapeHtml(s.station_code)}</span>` : ''}
              ${s.address ? `<span>${UI.escapeHtml(s.address)}</span>` : ''}
              ${s.lat && s.lng ? `<span>${formatCoords(s.lat)}, ${formatCoords(s.lng)}</span>` : ''}
              ${s.product_description ? `<span>${UI.escapeHtml(s.product_description)}</span>` : ''}
            </div>
          </div>
          <div class="stop-actions">
            <button class="btn-secondary" data-stop-edit="${s._id}" title="Edit">Edit</button>
            <button class="btn-danger" data-stop-delete="${s._id}" title="Delete">Del</button>
          </div>
        </div>`;
    });
    container.innerHTML = html;

    container.querySelectorAll('[data-stop-edit]').forEach((btn) => {
      btn.addEventListener('click', () => openStopModal(selectedAssignmentId, btn.dataset.stopEdit));
    });
    container.querySelectorAll('[data-stop-delete]').forEach((btn) => {
      btn.addEventListener('click', () => deleteStop(selectedAssignmentId, btn.dataset.stopDelete));
    });

    // Drag-and-drop
    const cards = container.querySelectorAll('.stop-card[draggable]');
    cards.forEach((card) => {
      card.addEventListener('dragstart', (e) => {
        dragSourceId = card.dataset.stopId;
        card.classList.add('stop-dragging');
        e.dataTransfer.effectAllowed = 'move';
      });
      card.addEventListener('dragend', () => {
        card.classList.remove('stop-dragging');
        document.querySelectorAll('.stop-drop-target').forEach((el) => el.classList.remove('stop-drop-target'));
      });
      card.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        document.querySelectorAll('.stop-drop-target').forEach((el) => el.classList.remove('stop-drop-target'));
        card.classList.add('stop-drop-target');
      });
      card.addEventListener('dragleave', () => {
        card.classList.remove('stop-drop-target');
      });
      card.addEventListener('drop', (e) => {
        e.preventDefault();
        card.classList.remove('stop-drop-target');
        if (!dragSourceId || dragSourceId === card.dataset.stopId) return;
        const a = state.assignments.find((x) => x._id === selectedAssignmentId);
        if (!a) return;
        const fromIdx = a.stops.findIndex((s) => s._id === dragSourceId);
        const toIdx = a.stops.findIndex((s) => s._id === card.dataset.stopId);
        if (fromIdx === -1 || toIdx === -1) return;
        const [moved] = a.stops.splice(fromIdx, 1);
        a.stops.splice(toIdx, 0, moved);
        dragSourceId = null;
        markDirty();
        renderAssignmentTabs();
        renderStopsList(selectedAssignmentId);
      });
    });
  }

  // ================================================================
  // Station Search
  // ================================================================
  let stationSearchFocused = false;

  function openStopModal(assignmentId, editId) {
    state.editingStopAssignmentId = assignmentId;
    state.editingStopId = editId || null;
    const isEdit = !!state.editingStopId;
    $('stopModalTitle').textContent = isEdit ? 'Edit Stop' : 'Add Stop';

    const stationInput = $('stopStationSearch');
    const suggestions = $('stopStationSuggestions');

    if (isEdit) {
      const a = state.assignments.find((x) => x._id === assignmentId);
      const s = a ? a.stops.find((x) => x._id === editId) : null;
      if (s) {
        $('stopStationCode').value = s.station_code || '';
        $('stopStationName').value = s.station_name || '';
        $('stopAddress').value = s.address || '';
        $('stopLat').value = s.lat || '';
        $('stopLng').value = s.lng || '';
        $('stopManager').value = s.manager_name || '';
        $('stopPhone').value = s.manager_phone || '';
        $('stopProduct').value = s.product_description || '';
        $('stopNotes').value = s.note || '';
        stationInput.value = s.station_name || s.station_code || '';
      }
      suggestions.style.display = 'none';
    } else {
      $('stopStationCode').value = '';
      $('stopStationName').value = '';
      $('stopAddress').value = '';
      $('stopLat').value = '';
      $('stopLng').value = '';
      $('stopManager').value = '';
      $('stopPhone').value = '';
      $('stopProduct').value = '';
      $('stopNotes').value = '';
      stationInput.value = '';
      suggestions.style.display = 'none';
    }

    $('stopModal').style.display = '';
    window.setTimeout(() => stationInput.focus(), 100);
  }

  function filterStations(query) {
    if (!query) return state.stationDb;
    const q = query.toLowerCase();
    return state.stationDb.filter((s) =>
      (s.station_name || '').toLowerCase().includes(q) ||
      (s.station_code || '').toLowerCase().includes(q) ||
      (s.address || '').toLowerCase().includes(q)
    );
  }

  function renderStationSuggestions(query) {
    const container = $('stopStationSuggestions');
    const results = filterStations(query).slice(0, 8);
    if (results.length === 0 || !query) {
      container.style.display = 'none';
      return;
    }
    let html = '';
    results.forEach((s) => {
      const label = [s.station_name, s.station_code].filter(Boolean).join(' — ');
      const detail = [s.address, s.manager_name].filter(Boolean).join(' • ');
      html += `<div class="station-suggestion" data-station="${UI.escapeHtml(s.station_code || s.station_name)}">
        <div class="suggestion-name">${UI.escapeHtml(label)}</div>
        ${detail ? `<div class="suggestion-detail">${UI.escapeHtml(detail)}</div>` : ''}
      </div>`;
    });
    container.innerHTML = html;
    container.style.display = '';
    container.querySelectorAll('.station-suggestion').forEach((el) => {
      el.addEventListener('click', () => applyStation(el.dataset.station));
    });
  }

  function applyStation(key) {
    const k = key.toLowerCase();
    const s = state.stationDb.find((x) =>
      (x.station_code || '').toLowerCase() === k || (x.station_name || '').toLowerCase() === k
    );
    if (!s) return;
    $('stopStationCode').value = s.station_code || '';
    $('stopStationName').value = s.station_name || '';
    $('stopAddress').value = s.address || '';
    $('stopLat').value = s.lat || '';
    $('stopLng').value = s.lng || '';
    $('stopManager').value = s.manager_name || '';
    $('stopPhone').value = s.manager_phone || '';
    $('stopStationSearch').value = s.station_name || s.station_code || '';
    $('stopStationSuggestions').style.display = 'none';
    $('stopStationName').focus();
  }

  function saveStopFromModal() {
    const stationCode = $('stopStationCode').value.trim();
    const stationName = $('stopStationName').value.trim();
    const address = $('stopAddress').value.trim();
    const latRaw = $('stopLat').value.trim();
    const lngRaw = $('stopLng').value.trim();
    const managerName = $('stopManager').value.trim();
    const managerPhone = $('stopPhone').value.trim();
    const productDescription = $('stopProduct').value.trim();
    const note = $('stopNotes').value.trim();

    let lat = null;
    let lng = null;
    if (latRaw) {
      lat = parseFloat(latRaw);
      if (isNaN(lat)) { showValidation($('stopLat'), 'Must be a valid number'); return false; }
    }
    if (lngRaw) {
      lng = parseFloat(lngRaw);
      if (isNaN(lng)) { showValidation($('stopLng'), 'Must be a valid number'); return false; }
    }
    if (!stationName) { showValidation($('stopStationName'), 'Station name is required'); return false; }

    clearValidation($('stopStationName'));
    clearValidation($('stopLat'));
    clearValidation($('stopLng'));

    const stopData = {
      station_code: stationCode,
      station_name: stationName,
      address: address,
      lat: lat,
      lng: lng,
      manager_name: managerName,
      manager_phone: managerPhone,
      product_description: productDescription,
      note: note,
    };

    const a = state.assignments.find((x) => x._id === state.editingStopAssignmentId);
    if (!a) return false;

    if (state.editingStopId) {
      const s = a.stops.find((x) => x._id === state.editingStopId);
      if (s) Object.assign(s, stopData);
    } else {
      stopData._id = String(nextStopId++);
      a.stops.push(stopData);
    }

    saveStationToDb(stopData);
    $('stopModal').style.display = 'none';
    state.editingStopId = null;
    state.editingStopAssignmentId = null;
    markDirty();
    renderAssignmentTabs();
    renderStopsList(selectedAssignmentId);
    return true;
  }

  function deleteStop(assignmentId, stopId) {
    if (!confirm('Delete this stop?')) return;
    const a = state.assignments.find((x) => x._id === assignmentId);
    if (!a) return;
    a.stops = a.stops.filter((s) => s._id !== stopId);
    markDirty();
    renderAssignmentTabs();
    renderStopsList(selectedAssignmentId);
  }

  // ================================================================
  // Map Picker
  // ================================================================
  let mapPickerInstance = null;
  let mapPickerMarker = null;

  function openMapPicker() {
    const overlay = $('mapPickerOverlay');
    overlay.style.display = '';
    const lat = parseFloat($('stopLat').value) || 10.8231;
    const lng = parseFloat($('stopLng').value) || 106.6297;

    window.setTimeout(() => {
      if (mapPickerInstance) {
        mapPickerInstance.invalidateSize();
        return;
      }
      mapPickerInstance = L.map('mapPickerMap', { zoomControl: true }).setView([lat, lng], 12);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap contributors',
      }).addTo(mapPickerInstance);

      mapPickerMarker = L.marker([lat, lng], { draggable: true }).addTo(mapPickerInstance);

      mapPickerInstance.on('click', (e) => {
        mapPickerMarker.setLatLng(e.latlng);
        $('stopLat').value = e.latlng.lat.toFixed(6);
        $('stopLng').value = e.latlng.lng.toFixed(6);
      });

      mapPickerMarker.on('dragend', () => {
        const pos = mapPickerMarker.getLatLng();
        $('stopLat').value = pos.lat.toFixed(6);
        $('stopLng').value = pos.lng.toFixed(6);
      });
    }, 200);
  }

  function closeMapPicker() {
    $('mapPickerOverlay').style.display = 'none';
  }

  // ================================================================
  // Validation
  // ================================================================
  function showValidation(el, msg) {
    const existing = el.parentNode.querySelector('.field-error');
    if (existing) existing.remove();
    const err = document.createElement('div');
    err.className = 'field-error';
    err.textContent = msg;
    el.classList.add('field-invalid');
    el.parentNode.appendChild(err);
  }

  function clearValidation(el) {
    el.classList.remove('field-invalid');
    const existing = el.parentNode.querySelector('.field-error');
    if (existing) existing.remove();
  }

  function clearAllValidation() {
    $$('.field-invalid').forEach((el) => el.classList.remove('field-invalid'));
    $$('.field-error').forEach((el) => el.remove());
  }

  function validateStop(s) {
    const errs = [];
    if (!s.station_name) errs.push('Station name required');
    if (s.lat != null && (isNaN(parseFloat(s.lat)) || parseFloat(s.lat) < -90 || parseFloat(s.lat) > 90)) errs.push('Invalid latitude');
    if (s.lng != null && (isNaN(parseFloat(s.lng)) || parseFloat(s.lng) < -180 || parseFloat(s.lng) > 180)) errs.push('Invalid longitude');
    return errs;
  }

  function validateAll(errorsContainer) {
    clearAllValidation();
    const errors = [];

    // Plan info
    if (!state.planInfo.plan_name) errors.push('Plan name is required');
    if (!state.planInfo.plan_date) errors.push('Plan date is required');

    // Assignments
    if (state.assignments.length === 0) errors.push('At least one vehicle assignment is required');

    state.assignments.forEach((a) => {
      const vehicle = state.vehicles.find((v) => String(v.id) === String(a.vehicle_id));
      const vlabel = vehicle ? vehicle.plate_number : 'Unknown';

      if (!a.vehicle_id) errors.push(`Assignment "${vlabel}": vehicle is required`);

      if (a.stops.length === 0) {
        errors.push(`Assignment "${vlabel}": at least one stop required`);
      }

      // Duplicate station codes within assignment
      const codes = a.stops.map((s) => s.station_code).filter(Boolean);
      const dupes = codes.filter((c, i) => codes.indexOf(c) !== i);
      if (dupes.length > 0) {
        errors.push(`Assignment "${vlabel}": duplicate station code "${dupes[0]}"`);
      }

      a.stops.forEach((s) => {
        const serrs = validateStop(s);
        serrs.forEach((e) => errors.push(`Assignment "${vlabel}", stop "${s.station_name || '?'}": ${e}`));
      });
    });

    if (errorsContainer) {
      errorsContainer.innerHTML = errors.map((e) => `<div class="validation-item">${UI.escapeHtml(e)}</div>`).join('');
    }

    return errors;
  }

  // ================================================================
  // Step 4 — Review
  // ================================================================
  function renderStep4() {
    const container = $('reviewContent');

    // Validation summary
    const valContainer = $('reviewValidation');
    const errors = validateAll(valContainer);
    const hasErrors = errors.length > 0;

    // Stats
    const statsHtml = `
      <div class="review-summary-stats">
        <div class="review-stat">
          <div class="review-stat-value">${UI.escapeHtml(state.planInfo.plan_name)}</div>
          <div class="review-stat-label">Plan Name</div>
        </div>
        <div class="review-stat">
          <div class="review-stat-value">${UI.escapeHtml(state.planInfo.plan_date)}</div>
          <div class="review-stat-label">Plan Date</div>
        </div>
        <div class="review-stat">
          <div class="review-stat-value">${state.assignments.length}</div>
          <div class="review-stat-label">Vehicles</div>
        </div>
        <div class="review-stat">
          <div class="review-stat-value">${totalStops()}</div>
          <div class="review-stat-label">Total Stops</div>
        </div>
        <div class="review-stat">
          <div class="review-stat-value">&mdash;</div>
          <div class="review-stat-label">Est. Distance</div>
        </div>
      </div>`;

    // Plan info
    const planHtml = `
      <div class="review-section">
        <div class="review-section-title">Plan Information</div>
        <div class="review-grid">
          <span class="review-label">Name:</span>
          <span class="review-value">${UI.escapeHtml(state.planInfo.plan_name)}</span>
          <span class="review-label">Date:</span>
          <span class="review-value">${UI.escapeHtml(state.planInfo.plan_date)}</span>
          ${state.planInfo.description ? `<span class="review-label">Description:</span><span class="review-value">${UI.escapeHtml(state.planInfo.description)}</span>` : ''}
          <span class="review-label">Status:</span>
          <span class="review-value">${state.planId ? (state.planInfo.status === 'confirmed' ? 'Confirmed' : 'Draft') : 'New (not yet saved)'}</span>
        </div>
      </div>`;

    // Assignments
    let assignmentsHtml = '';
    state.assignments.forEach((a) => {
      const vehicle = state.vehicles.find((v) => String(v.id) === String(a.vehicle_id));
      const driver = state.drivers.find((d) => String(d.id) === String(a.driver_id));
      const vlabel = vehicle ? vehicle.plate_number : 'Unknown';
      var dlabel = 'Unknown';
      if (driver) { dlabel = driver.name; }
      else if (a._driverName) { dlabel = a._driverName; }
      else if (vehicle && vehicle.current_driver) { dlabel = vehicle.current_driver + ' (auto)'; }

      let stopsHtml = '';
      a.stops.forEach((s, idx) => {
        const serrs = validateStop(s);
        const warnIcon = serrs.length > 0 ? ' &#9888;' : '';
        stopsHtml += `
          <div class="review-stop">
            <span class="review-stop-order">${idx + 1}</span>
            <span class="review-stop-info">${UI.escapeHtml(s.station_name)}${s.station_code ? ' (' + UI.escapeHtml(s.station_code) + ')' : ''}${warnIcon}</span>
            <span class="review-stop-extra">${s.product_description ? UI.escapeHtml(s.product_description) : ''}${s.lat && s.lng ? ' &middot; ' + formatCoords(s.lat) + ', ' + formatCoords(s.lng) : ''}</span>
          </div>`;
      });

      const stopWord = a.stops.length === 1 ? 'stop' : 'stops';
      assignmentsHtml += `
        <div class="review-assignment">
          <div class="review-assignment-header">
            <h4>${UI.escapeHtml(vlabel)} &mdash; ${UI.escapeHtml(dlabel)}</h4>
            <span style="font-size:12px;color:var(--text-secondary);">${a.stops.length} ${stopWord}</span>
          </div>
          ${a.notes ? `<div style="font-size:12px;color:var(--text-secondary);margin-bottom:8px;font-style:italic;">${UI.escapeHtml(a.notes)}</div>` : ''}
          ${stopsHtml}
        </div>`;
    });

    container.innerHTML = statsHtml + planHtml + assignmentsHtml;

    // Button states — confirmed plans remain editable, so always show Save/Confirm
    const isConfirmed = state.planInfo.status === 'confirmed';
    if (isConfirmed) {
      $('step4SaveDraft').style.display = '';
      $('step4Confirm').style.display = '';
      $('step4ConfirmedInfo').style.display = '';
    } else {
      $('step4SaveDraft').style.display = '';
      $('step4Confirm').style.display = '';
      $('step4ConfirmedInfo').style.display = 'none';
      $('step4Confirm').disabled = hasErrors;
      $('step4SaveDraft').disabled = hasErrors;
    }
  }

  // ================================================================
  // Save as Draft / Confirm
  // ================================================================
  async function saveDraft(isAuto) {
    if (state.readOnly) return;
    if (state.isSaving) return;
    state.isSaving = true;
    updateAutoSaveIndicator();

    try {
      let planId = state.planId;

      if (!planId) {
        // Create plan
        const result = await fetchJSON('/api/plans', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            plan_name: state.planInfo.plan_name,
            plan_date: state.planInfo.plan_date,
            description: state.planInfo.description || '',
            created_by: 'dispatcher',
          }),
        });
        planId = result.id;
        state.planId = planId;
      } else {
        // Update plan info
        await fetchJSON(`/api/plans/${planId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            plan_name: state.planInfo.plan_name,
            plan_date: state.planInfo.plan_date,
            description: state.planInfo.description || '',
          }),
        });
      }

      // Sync assignments: simple approach — delete all existing, recreate
      // First, get existing assignments
      let existingAssignments = [];
      try {
        existingAssignments = await fetchJSON(`/api/assignments?plan_id=${planId}`);
      } catch {}

      // Delete existing assignments (cascades to stops)
      for (const ea of existingAssignments) {
        try {
          await fetchJSON(`/api/assignments/${ea.id}`, { method: 'DELETE' });
        } catch {}
      }

      // Create current assignments with stops
      for (let i = 0; i < state.assignments.length; i++) {
        const a = state.assignments[i];
        const assignResult = await fetchJSON('/api/assignments', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            plan_id: planId,
            vehicle_id: a.vehicle_id,
            driver_id: a.driver_id || null,
            // Most drivers have no `drivers` row (they exist only as
            // vehicles.current_driver text), so driver_id is usually null.
            // Send the name too or the dispatch page falls back to the
            // vehicle's default driver and the override is lost.
            driver_name: a._driverName || '',
            sequence: i,
            notes: a.notes || '',
          }),
        });
        const assignmentId = assignResult.id;

        for (let j = 0; j < a.stops.length; j++) {
          const s = a.stops[j];
          await fetchJSON('/api/stops', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              assignment_id: assignmentId,
              planned_sequence: j,
              station_code: s.station_code || '',
              station_name: s.station_name || '',
              address: s.address || '',
              lat: s.lat,
              lng: s.lng,
              manager_name: s.manager_name || '',
              manager_phone: s.manager_phone || '',
              product_description: s.product_description || '',
              note: s.note || '',
            }),
          });
        }
      }

      markClean();
      // Preserve confirmed status when editing an existing plan; only a
      // brand-new plan (no backend record yet) starts as a draft.
      if (!state._confirmedStatus) state.planInfo.status = 'draft';
      if (!isAuto) {
        showToast(state._confirmedStatus ? 'Changes saved' : 'Draft saved successfully');
      }
    } catch (e) {
      if (!isAuto) alert('Error saving draft: ' + e.message);
    } finally {
      state.isSaving = false;
      updateAutoSaveIndicator();
    }
  }

  async function confirmPlan() {
    if (state.readOnly) return;
    const errors = validateAll($('reviewValidation'));
    if (errors.length > 0) {
      alert('Please fix validation errors before confirming.');
      return;
    }

    const btn = $('step4Confirm');
    btn.disabled = true;
    btn.textContent = 'Saving...';

    try {
      // Save draft first if needed
      if (state.isDirty || !state.planId) {
        await saveDraft(false);
      }

      // Confirm
      await fetchJSON(`/api/plans/${state.planId}/confirm`, { method: 'POST' });
      state.planInfo.status = 'confirmed';

      // Fetch full plan
      const fullPlan = await fetchJSON(`/api/plans/${state.planId}`);
      showSuccess(fullPlan);
    } catch (e) {
      alert('Error confirming plan: ' + e.message);
      btn.disabled = false;
      btn.textContent = 'Confirm & Save';
    }
  }

  // ================================================================
  // Step 5 — Success
  // ================================================================
  function showSuccess(plan) {
    goToStep(5);

    const aCount = plan.assignments ? plan.assignments.length : state.assignments.length;
    const stopCount = plan.assignments
      ? plan.assignments.reduce((s, a) => s + (a.stops ? a.stops.length : 0), 0)
      : totalStops();

    $('successDetails').innerHTML = `
      <div class="detail-row"><span class="detail-label">Plan ID:</span> #${state.planId}</div>
      <div class="detail-row"><span class="detail-label">Vehicles:</span> ${aCount}</div>
      <div class="detail-row"><span class="detail-label">Stops:</span> ${stopCount}</div>
    `;
    $('openPlanLink').href = `/delivery/edit/${state.planId}`;
    $('openPlanLink').style.display = 'inline-flex';
    $('createAnotherPlanBtn').style.display = 'inline-flex';
    $('returnToDashboardBtn').style.display = 'inline-flex';
  }

  // ================================================================
  // Toast notifications
  // ================================================================
  function showToast(msg) {
    let toast = $('toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'toast';
      toast.className = 'toast';
      document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.classList.add('toast-visible');
    clearTimeout(toast._hideTimer);
    toast._hideTimer = setTimeout(() => toast.classList.remove('toast-visible'), 3000);
  }

  // ================================================================
  // Google Sheet import
  // ================================================================
  // Reads the manager's planning sheet and builds the whole plan in one go,
  // bypassing steps 2-4. Two clicks by design: "Read sheet" only fetches and
  // shows what would be written, "Create plan" commits. The sheet is hand-typed
  // and its defects (missing coordinates, blank station codes) have to be
  // visible before the plan is live, not discovered on the dashboard.

  let sheetPreview = null;

  function sheetDateValue() {
    const input = $('sheetImportDate');
    return input && input.value ? input.value : '';
  }

  function tomorrowISO() {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    // Local date parts, not toISOString(): in UTC+7 an evening toISOString()
    // returns the wrong calendar day, which would default the picker to today.
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${d.getFullYear()}-${mm}-${dd}`;
  }

  function sheetResultBox() {
    return $('sheetImportResult');
  }

  function showSheetError(message) {
    const box = sheetResultBox();
    box.style.display = 'block';
    box.innerHTML = `<div class="sheet-import-error">${UI.escapeHtml(message)}</div>`;
  }

  function renderSheetWarnings(warnings) {
    if (!warnings || !warnings.length) return '';
    const items = warnings.map((w) => {
      const where = w.station_code
        ? `${UI.escapeHtml(w.station_code)} (row ${w.sheet_row})`
        : `Row ${w.sheet_row}`;
      return `<li><strong>${where}:</strong> ${UI.escapeHtml(w.message)}</li>`;
    }).join('');
    return `
      <div class="sheet-warnings">
        <h4>${warnings.length} thing${warnings.length === 1 ? '' : 's'} to check in the sheet</h4>
        <ul>${items}</ul>
      </div>`;
  }

  function renderSheetTrucks(assignments) {
    return assignments.map((a) => {
      const plate = a.resolved
        ? UI.escapeHtml(a.resolved_plate)
        : `${UI.escapeHtml(a.vehicle_identifier)} — not in the fleet`;
      const sheetPlate = a.resolved && a.resolved_plate !== a.vehicle_identifier
        ? ` <small>(sheet: ${UI.escapeHtml(a.vehicle_identifier)})</small>`
        : '';
      const stops = a.stops.map((s) => {
        const noCoord = (s.lat == null || s.lng == null)
          ? '<span class="sheet-stop-nocoord">no coordinates</span>'
          : `${formatCoords(s.lat)}, ${formatCoords(s.lng)}`;
        return `
          <div class="sheet-stop">
            <span class="sheet-stop-seq">${s.sequence}</span>
            <span class="sheet-stop-code">${UI.escapeHtml(s.station_code || '(no code)')}</span>
            <span>${noCoord}</span>
          </div>`;
      }).join('');
      return `
        <div class="sheet-truck">
          <div class="sheet-truck-head">
            <span>${plate}${sheetPlate}</span>
            <span>${a.stop_count} stop${a.stop_count === 1 ? '' : 's'}</span>
          </div>
          ${stops}
        </div>`;
    }).join('');
  }

  function renderSheetPreview(data) {
    sheetPreview = data;
    const box = sheetResultBox();
    const p = data.preview || {};
    const assignments = p.assignments || [];
    const unknown = p.unknown_vehicles || [];
    const stopCount = assignments.reduce((sum, a) => sum + a.stop_count, 0);
    const noCoords = assignments.reduce(
      (sum, a) => sum + a.stops.filter((s) => s.lat == null || s.lng == null).length, 0);

    let blockers = '';
    if (unknown.length) {
      blockers = `<div class="sheet-import-error">
        These plates are not in the fleet, so nothing can be imported:
        ${UI.escapeHtml(unknown.join(', '))}. Add them under Vehicle Management,
        or correct the sheet.</div>`;
    }

    let existing = '';
    const plans = data.existing_plans || [];
    if (plans.length) {
      const active = plans.reduce((sum, pl) => sum + pl.active_executions, 0);
      existing = active
        ? `<div class="sheet-warnings"><h4>A plan for this date is already in progress</h4>
             <p style="margin:0;font-size:12px;">${active} stop(s) have been started,
             skipped or completed. Replacing the plan deletes that record.</p></div>`
        : `<div class="sheet-warnings"><h4>Replacing the existing plan for this date</h4>
             <p style="margin:0;font-size:12px;">
             ${UI.escapeHtml(plans.map((pl) => pl.plan_name).join(', '))} — no stops started yet.</p></div>`;
    }

    box.style.display = 'block';
    box.innerHTML = `
      <div class="sheet-import-summary">
        <span>Tab <strong>${UI.escapeHtml(data.tab_name)}</strong></span>
        <span><strong>${assignments.length}</strong> truck${assignments.length === 1 ? '' : 's'}</span>
        <span><strong>${stopCount}</strong> stop${stopCount === 1 ? '' : 's'}</span>
        ${noCoords ? `<span class="sheet-stop-nocoord">${noCoords} without coordinates</span>` : ''}
      </div>
      ${blockers}
      ${existing}
      ${renderSheetWarnings(data.warnings)}
      ${renderSheetTrucks(assignments)}
      <div class="sheet-import-actions">
        <button class="btn-primary" id="sheetCommitBtn"${unknown.length ? ' disabled' : ''}>
          Create plan for ${UI.escapeHtml(data.date)}
        </button>
        <button class="btn-secondary" id="sheetCancelBtn">Cancel</button>
      </div>`;

    if (!unknown.length) {
      $('sheetCommitBtn').addEventListener('click', () => commitSheetImport(false));
    }
    $('sheetCancelBtn').addEventListener('click', () => {
      sheetPreview = null;
      box.style.display = 'none';
      box.innerHTML = '';
    });
  }

  async function readSheet() {
    const day = sheetDateValue();
    if (!day) { showToast('Pick a dispatch date first'); return; }
    const btn = $('sheetImportBtn');
    btn.disabled = true;
    btn.textContent = 'Reading...';
    try {
      const data = await fetchJSON(
        `/api/plans/import/sheet/preview?date=${encodeURIComponent(day)}`);
      renderSheetPreview(data);
    } catch (e) {
      showSheetError(e.message);
    } finally {
      btn.disabled = false;
      btn.textContent = 'Read sheet';
    }
  }

  async function commitSheetImport(override) {
    const day = sheetDateValue();
    const btn = $('sheetCommitBtn');
    if (btn) { btn.disabled = true; btn.textContent = 'Creating...'; }
    try {
      const result = await fetchJSON('/api/plans/import/sheet/commit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date: day, override_in_progress: !!override }),
      });
      showToast(`Plan created: ${result.stops_created} stops, ${result.assignments_created} trucks`);
      // Land on the plan itself so the dispatcher can fix any flagged stop
      // straight away.
      window.location.href = `/delivery/edit/${result.plan_id}`;
    } catch (e) {
      const reason = e.body && e.body.reason;
      if (reason === 'in_progress' && !override) {
        offerSheetOverride(e.message);
      } else {
        showSheetError(e.message);
      }
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Create plan'; }
    }
  }

  function offerSheetOverride(message) {
    const box = sheetResultBox();
    const panel = document.createElement('div');
    panel.className = 'sheet-import-error';
    panel.innerHTML = `
      <p style="margin:0 0 8px;">${UI.escapeHtml(message)}</p>
      <button class="btn-secondary" id="sheetOverrideBtn">Replace anyway, discarding progress</button>`;
    box.appendChild(panel);
    $('sheetOverrideBtn').addEventListener('click', () => {
      panel.remove();
      commitSheetImport(true);
    });
  }

  function initSheetImport() {
    const box = $('sheetImportBox');
    if (!box) return;
    // Importing builds a plan from scratch; it has no meaning while editing an
    // existing one.
    if (document.body.dataset.editPlanId) {
      box.style.display = 'none';
      return;
    }
    $('sheetImportDate').value = tomorrowISO();
    $('sheetImportBtn').addEventListener('click', readSheet);
  }

  // ================================================================
  // Navigation
  // ================================================================
  function goToStep(step) {
    state.currentStep = step;
    showPanel(step);
    switch (step) {
      case 1: renderStep1(); break;
      case 2: renderStep2(); break;
      case 3: renderStep3(); break;
      case 4: renderStep4(); break;
    }
    startAutoSave();
  }

  // ================================================================
  // Load existing plan for editing
  // ================================================================
  async function loadExistingPlan(planId) {
    try {
      const plan = await fetchJSON(`/api/plans/${planId}`);
      state.planId = plan.id;
      state.readOnly = false;
      state._confirmedStatus = plan.status === 'confirmed';
      const banner = $('readOnlyBanner');
      if (banner) banner.style.display = 'none';
      state.planInfo = {
        plan_name: plan.plan_name || '',
        plan_date: plan.plan_date || '',
        description: plan.description || '',
        status: plan.status || 'draft',
      };

      if (plan.assignments) {
        state.assignments = plan.assignments.map((a, idx) => ({
          _id: String(nextAssignmentId++),
          backendId: a.id,
          vehicle_id: a.vehicle_id,
          driver_id: a.driver_id,
          _driverName: a.driver_name || null,
          notes: a.notes || '',
          stops: (a.stops || []).map((s) => ({
            _id: String(nextStopId++),
            station_code: s.station_code || '',
            station_name: s.station_name || '',
            address: s.address || '',
            lat: s.lat,
            lng: s.lng,
            manager_name: s.manager_name || '',
            manager_phone: s.manager_phone || '',
            product_description: s.product_description || '',
            note: s.note || '',
          })),
        }));
      }

      markClean();
      return plan;
    } catch (e) {
      alert('Failed to load plan: ' + e.message);
      return null;
    }
  }

  // ================================================================
  // Event Binding & Init
  // ================================================================
  function init() {
    loadStationDb();

    // Step 1
    $('step1Next').addEventListener('click', () => {
      if (saveStep1()) goToStep(2);
    });

    // Step 2
    $('step2Back').addEventListener('click', () => goToStep(1));
    $('step2Next').addEventListener('click', () => {
      if (state.assignments.length === 0) {
        alert('Please add at least one vehicle assignment.');
        return;
      }
      goToStep(3);
    });
    $('addAssignmentBtn').addEventListener('click', () => openAssignmentModal(null));

    $('assignmentModalCancel').addEventListener('click', () => {
      $('assignmentModal').style.display = 'none';
      state.editingAssignmentId = null;
    });
    $('assignmentModalSave').addEventListener('click', saveAssignmentFromModal);

    // Step 3
    $('step3Back').addEventListener('click', () => goToStep(2));
    $('step3Next').addEventListener('click', () => {
      const hasEmpty = state.assignments.some((a) => a.stops.length === 0);
      if (hasEmpty) {
        alert('Every vehicle assignment must have at least one stop.');
        return;
      }
      goToStep(4);
    });
    $('addStopBtn').addEventListener('click', () => {
      if (selectedAssignmentId) openStopModal(selectedAssignmentId, null);
    });

    $('stopModalCancel').addEventListener('click', () => {
      $('stopModal').style.display = 'none';
      state.editingStopId = null;
    });
    $('stopModalSave').addEventListener('click', saveStopFromModal);

    // Station search
    const stationInput = $('stopStationSearch');
    stationInput.addEventListener('input', () => renderStationSuggestions(stationInput.value.trim()));
    stationInput.addEventListener('focus', () => {
      stationSearchFocused = true;
      renderStationSuggestions(stationInput.value.trim());
    });
    stationInput.addEventListener('blur', () => {
      window.setTimeout(() => { $('stopStationSuggestions').style.display = 'none'; }, 200);
    });

    // Map picker
    $('pickMapBtn').addEventListener('click', openMapPicker);
    $('mapPickerClose').addEventListener('click', closeMapPicker);
    $('mapPickerOverlay').addEventListener('click', (e) => {
      if (e.target === $('mapPickerOverlay')) closeMapPicker();
    });

    // Step 4
    $('step4Back').addEventListener('click', () => goToStep(3));
    $('step4SaveDraft').addEventListener('click', () => saveDraft(false));
    $('step4Confirm').addEventListener('click', confirmPlan);

    // Close modals on overlay click
    $$('.modal-overlay').forEach((overlay) => {
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
          overlay.style.display = 'none';
          state.editingAssignmentId = null;
          state.editingStopId = null;
        }
      });
    });

    initSheetImport();

    // Check for edit mode
    const editPlanId = document.body.dataset.editPlanId;

    Promise.all([loadVehicles(), loadDrivers()]).then(async () => {
      if (editPlanId) {
        await loadExistingPlan(editPlanId);
      }
      renderStep1();
      showPanel(1);
      updateStepIndicator();
    });
  }

  document.addEventListener('DOMContentLoaded', init);
})();
