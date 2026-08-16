/**
 * oil-change.js
 * Controller for the Oil Change Maintenance Tracker dashboard.
 */

// ── State ──────────────────────────────────────────────────────
let allVehicles = [];          // full dataset from API
let filteredVehicles = [];     // after search filter
let sortKey = 'maintenance_status';
let sortDir = 1;               // 1 = asc, -1 = desc
let editingPlate = null;       // null = creating, string = editing

// Status sort order for custom sort
const STATUS_ORDER = { safe: 0, warning: 1, danger: 2 };

// ── Init ───────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    loadVehicles();
    // Set default date to today
    const dateField = document.getElementById('field-date');
    if (dateField) dateField.value = todayISO();
});

// ── Load Vehicles ──────────────────────────────────────────────
async function loadVehicles() {
    try {
        const data = await ApiClient.fetch('/oil-maintenance');
        allVehicles = data.data || [];
        filteredVehicles = [...allVehicles];
        renderKPIs();
        renderTable();
    } catch (err) {
        UI.toast(`Failed to load vehicles: ${err.message}`, 'error');
    }
}

// ── KPI Rendering ──────────────────────────────────────────────
function renderKPIs() {
    const total     = allVehicles.length;
    const attention = allVehicles.filter(v => v.maintenance_status !== 'safe').length;
    const avgPct    = total
        ? (allVehicles.reduce((s, v) => s + (v.progress_pct || 0), 0) / total).toFixed(1)
        : 0;

    document.getElementById('kpi-total').textContent     = total;
    document.getElementById('kpi-attention').textContent = attention;
    document.getElementById('kpi-avg').textContent       = `${avgPct}%`;
    document.getElementById('vehicle-count').textContent = filteredVehicles.length;
}

// ── Table Rendering ────────────────────────────────────────────
function renderTable() {
    const tbody = document.getElementById('table-body');
    const empty = document.getElementById('empty-state');

    if (!filteredVehicles.length) {
        tbody.innerHTML = '';
        empty.style.display = 'block';
        document.getElementById('vehicle-count').textContent = 0;
        return;
    }

    empty.style.display = 'none';
    document.getElementById('vehicle-count').textContent = filteredVehicles.length;

    tbody.innerHTML = filteredVehicles.map(v => {
        const pct     = Math.min(v.progress_pct || 0, 100);
        const status  = v.maintenance_status || 'safe';
        const pillCls = status;

        const pillLabel = { safe: 'Safe', warning: 'Due Soon', danger: 'Overdue' }[status] || status;

        const remStyle = v.remaining_km < 0
            ? 'color:#f87171; font-weight:700;'
            : '';

        return `
        <tr data-plate="${UI.escapeHtml(v.license_plate)}">
            <td><span class="plate-badge">${UI.escapeHtml(v.license_plate)}</span></td>
            <td>${formatDate(v.last_oil_change_date)}</td>
            <td><span class="km-value">${fmtNum(v.maintenance_interval)}</span> <span class="km-muted">km</span></td>
            <td><span class="km-value">${fmtNum(v.total_km_since_change)}</span> <span class="km-muted">km</span></td>
            <td style="${remStyle}"><span class="km-value">${fmtNum(v.remaining_km)}</span> <span class="km-muted">km</span></td>
            <td>
                <div class="progress-wrap">
                    <div class="progress-header">
                        <span class="status-pill ${pillCls}">${pillLabel}</span>
                        <span class="pct-text">${pct.toFixed(1)}%</span>
                    </div>
                    <div class="progress-track">
                        <div class="progress-fill ${status}" style="width:${pct}%"></div>
                    </div>
                </div>
            </td>
            <td>
                <div style="display:flex; gap:6px;">
                    <button class="btn-action btn-edit"
                            onclick="openModal('${UI.escapeHtml(v.license_plate)}')">✏️ Edit</button>
                    <button class="btn-action btn-maintenance"
                            onclick="markMaintenance('${UI.escapeHtml(v.license_plate)}')">🔧 Maintenance</button>
                    <button class="btn-action btn-delete"
                            onclick="deleteVehicle('${UI.escapeHtml(v.license_plate)}')">🗑</button>
                </div>
            </td>
        </tr>`;
    }).join('');
}

// ── Sorting ────────────────────────────────────────────────────
function sortTable(key) {
    if (sortKey === key) {
        sortDir *= -1;
    } else {
        sortKey = key;
        sortDir = 1;
    }

    // Update header visual
    document.querySelectorAll('.oc-table th').forEach(th => th.classList.remove('sorted'));
    const headers = document.querySelectorAll('.oc-table th');
    const keyMap = ['license_plate', 'last_oil_change_date',
                    'maintenance_interval', 'total_km_since_change', 'remaining_km',
                    'progress_pct'];
    const idx = keyMap.indexOf(key);
    if (idx >= 0 && headers[idx]) headers[idx].classList.add('sorted');

    filteredVehicles.sort((a, b) => {
        let va = a[key], vb = b[key];
        if (key === 'maintenance_status') {
            va = STATUS_ORDER[va] ?? 99;
            vb = STATUS_ORDER[vb] ?? 99;
        }
        if (typeof va === 'string') return va.localeCompare(vb) * sortDir;
        return ((va ?? 0) - (vb ?? 0)) * sortDir;
    });

    renderTable();
}

// ── Search Filter ──────────────────────────────────────────────
function filterTable(query) {
    const q = query.trim().toLowerCase();
    filteredVehicles = q
        ? allVehicles.filter(v => v.license_plate.toLowerCase().includes(q))
        : [...allVehicles];

    // Re-apply current sort
    if (sortKey) {
        filteredVehicles.sort((a, b) => {
            let va = a[sortKey], vb = b[sortKey];
            if (sortKey === 'maintenance_status') {
                va = STATUS_ORDER[va] ?? 99;
                vb = STATUS_ORDER[vb] ?? 99;
            }
            if (typeof va === 'string') return va.localeCompare(vb) * sortDir;
            return ((va ?? 0) - (vb ?? 0)) * sortDir;
        });
    }

    renderTable();
    document.getElementById('vehicle-count').textContent = filteredVehicles.length;
}

// ── Vehicle Search Autocomplete ────────────────────────────────
let searchTimeout = null;

function onVehicleInput(q) {
    const dropdown = document.getElementById('vehicle-dropdown');
    if (editingPlate) { dropdown.classList.remove('open'); return; }
    if (!q.trim()) { dropdown.classList.remove('open'); return; }

    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(async () => {
        try {
            const resp = await fetch(`/api/fleet/vehicles/search?q=${encodeURIComponent(q.trim())}`);
            const data = await resp.json();
            if (!data.success || !data.data.length) {
                dropdown.classList.remove('open');
                return;
            }
            dropdown.innerHTML = data.data.map(v =>
                `<div class="autocomplete-item" onclick="selectVehicle(${v.id}, '${UI.escapeHtml(v.plate_number)}', '${UI.escapeHtml(v.vehicle_type || '')}', '${UI.escapeHtml(v.current_driver || '')}')">
                    ${UI.escapeHtml(v.plate_number)}
                    <span class="sub">${v.vehicle_type || ''}${v.current_driver ? ' — ' + UI.escapeHtml(v.current_driver) : ''}</span>
                </div>`
            ).join('');
            dropdown.classList.add('open');
        } catch (_) {
            dropdown.classList.remove('open');
        }
    }, 200);
}

function selectVehicle(id, plate, vtype, driver) {
    document.getElementById('field-plate').value = plate;
    document.getElementById('vehicle-dropdown').classList.remove('open');
}

// ── Modal ──────────────────────────────────────────────────────
function openModal(plate = null) {
    editingPlate = plate;
    const overlay  = document.getElementById('modal-overlay');
    const title    = document.getElementById('modal-title');
    const btnSave  = document.getElementById('btn-save');
    const fieldPlt = document.getElementById('field-plate');

    if (plate) {
        const v = allVehicles.find(x => x.license_plate === plate);
        title.textContent          = 'Edit Vehicle';
        btnSave.textContent        = 'Save Changes';
        fieldPlt.value             = v ? v.license_plate : plate;
        fieldPlt.disabled          = true;
        document.getElementById('field-date').value     = v ? v.last_oil_change_date : '';
        document.getElementById('field-interval').value = v ? v.maintenance_interval  : 5000;
    } else {
        title.textContent          = 'Add Vehicle';
        btnSave.textContent        = 'Add Vehicle';
        fieldPlt.value             = '';
        fieldPlt.disabled          = false;
        document.getElementById('field-date').value     = todayISO();
        document.getElementById('field-interval').value = 5000;
    }

    overlay.classList.add('open');
    setTimeout(() => fieldPlt.focus(), 200);
}

function closeModal() {
    document.getElementById('modal-overlay').classList.remove('open');
    document.getElementById('vehicle-dropdown').classList.remove('open');
    editingPlate = null;
}

function handleOverlayClick(e) {
    if (e.target === document.getElementById('modal-overlay')) closeModal();
}

document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
});

// ── Save Vehicle ───────────────────────────────────────────────
async function saveVehicle() {
    const plate    = document.getElementById('field-plate').value.trim().toUpperCase();
    const date     = document.getElementById('field-date').value.trim();
    const interval = parseInt(document.getElementById('field-interval').value, 10);

    if (!plate)          return UI.toast('License plate is required.', 'warning');
    if (!date)           return UI.toast('Last oil change date is required.', 'warning');
    if (isNaN(interval) || interval < 100)
                         return UI.toast('Maintenance interval must be >= 100 km.', 'warning');

    const payload = {
        license_plate:        plate,
        last_oil_change_date: date,
        maintenance_interval: interval,
    };

    const btn = document.getElementById('btn-save');
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span> Saving…';

    try {
        if (editingPlate) {
            await ApiClient.fetch(`/oil-maintenance/${encodeURIComponent(editingPlate)}`, {
                method: 'PUT',
                body: JSON.stringify(payload),
            });
            UI.toast(`Vehicle ${plate} updated.`, 'success');
        } else {
            await ApiClient.fetch('/oil-maintenance', {
                method: 'POST',
                body: JSON.stringify(payload),
            });
            UI.toast(`Vehicle ${plate} added.`, 'success');
        }
        closeModal();
        await loadVehicles();
    } catch (err) {
        UI.toast(err.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = editingPlate ? 'Save Changes' : 'Add Vehicle';
    }
}

// ── Delete Vehicle ─────────────────────────────────────────────
async function deleteVehicle(plate) {
    if (!confirm(`Remove ${plate} from the oil change tracker?\n\nAll cached KM data for this vehicle will also be deleted.`)) return;

    try {
        await ApiClient.fetch(`/oil-maintenance/${encodeURIComponent(plate)}`, { method: 'DELETE' });
        UI.toast(`Vehicle ${plate} removed.`, 'success');
        await loadVehicles();
    } catch (err) {
        UI.toast(err.message, 'error');
    }
}

// ── Mark Maintenance Done ──────────────────────────────────────
let _maintenanceRunning = false;

async function markMaintenance(plate) {
    const fetchBtn = document.getElementById('btn-fetch-km');
    if (_maintenanceRunning || fetchBtn.disabled) return;
    if (!confirm(`Mark oil change as done for ${plate}?\n\nThis will set the last change date to today, clear the KM history, and fetch updated data.`)) return;

    const overlay  = document.getElementById('fetch-progress-overlay');
    const fill     = document.getElementById('fetch-progress-fill');
    const statusEl = document.getElementById('fetch-progress-status');
    const countEl  = document.getElementById('fetch-progress-count');
    const etaEl    = document.getElementById('fetch-progress-eta');

    _maintenanceRunning = true;
    fetchBtn.disabled = true;
    overlay.classList.add('active');
    fill.style.width = '0%';
    statusEl.textContent = `Processing maintenance for ${plate}...`;
    countEl.textContent = '—';
    etaEl.textContent = '';

    const fmt = (s) => {
        const m = Math.floor(s / 60);
        const sec = Math.round(s % 60);
        if (m > 0) return `${m}m ${sec}s`;
        return `${sec}s`;
    };

    let polling = true;
    const pollProgress = () => {
        if (!polling) return;
        fetch('/api/oil-maintenance/fetch-progress')
            .then(r => r.json())
            .then(p => {
                if (!polling) return;
                if (p.status === 'fetching' && p.total > 0) {
                    const pct = Math.round((p.current / p.total) * 100);
                    fill.style.width = pct + '%';
                    statusEl.textContent = p.plate ? `Processing ${p.plate}...` : 'Connecting to TTAS...';
                    countEl.textContent = `${p.current} / ${p.total} vehicles`;
                    if (p.current > 0 && p.started_at) {
                        const elapsed = (Date.now() / 1000) - p.started_at;
                        const perItem = elapsed / p.current;
                        const remaining = perItem * (p.total - p.current);
                        etaEl.textContent = `~${fmt(remaining)} remaining`;
                    } else {
                        etaEl.textContent = '';
                    }
                    setTimeout(pollProgress, 500);
                } else if (p.status === 'done' || p.status === 'error') {
                    fill.style.width = '100%';
                    statusEl.textContent = p.status === 'done' ? 'Complete' : 'Failed';
                    countEl.textContent = `${p.current || 0} / ${p.total || 0} vehicles`;
                    etaEl.textContent = '';
                }
            })
            .catch(() => {
                if (polling) setTimeout(pollProgress, 1000);
            });
    };

    try {
        // Step 1: Mark maintenance as done (quick DB update)
        statusEl.textContent = `Marking maintenance for ${plate}...`;
        await ApiClient.fetch(`/oil-maintenance/${encodeURIComponent(plate)}/maintenance`, { method: 'POST' });

        // Step 2: Fetch updated KM data from TTAS with progress tracking
        setTimeout(pollProgress, 300);
        const data = await ApiClient.fetch('/oil-maintenance/fetch-km', { method: 'POST' });
        polling = false;

        UI.toast(`Oil change marked as done for ${plate}. KM data refreshed.`, 'success');

        if (data.errors && data.errors.length) {
            data.errors.forEach(e => UI.toast(e, 'warning', 8000));
        }

        await loadVehicles();
    } catch (err) {
        polling = false;
        UI.toast(`Maintenance failed: ${err.message}`, 'error', 8000);
    } finally {
        overlay.classList.remove('active');
        fetchBtn.disabled = false;
        _maintenanceRunning = false;
    }
}

// ── Fetch KM Data ──────────────────────────────────────────────
async function fetchKmData() {
    const btn       = document.getElementById('btn-fetch-km');
    const icon      = document.getElementById('fetch-icon');
    const label     = document.getElementById('fetch-label');

    if (btn.disabled) return;
    btn.disabled    = true;
    icon.innerHTML  = '<span class="spin"></span>';
    label.textContent = 'Fetching…';

    const overlay  = document.getElementById('fetch-progress-overlay');
    const fill     = document.getElementById('fetch-progress-fill');
    const statusEl = document.getElementById('fetch-progress-status');
    const countEl  = document.getElementById('fetch-progress-count');
    const etaEl    = document.getElementById('fetch-progress-eta');

    overlay.classList.add('active');
    let polling = true;

    const fmt = (s) => {
        const m = Math.floor(s / 60);
        const sec = Math.round(s % 60);
        if (m > 0) return `${m}m ${sec}s`;
        return `${sec}s`;
    };

    const pollProgress = () => {
        if (!polling) return;
        fetch('/api/oil-maintenance/fetch-progress')
            .then(r => r.json())
            .then(p => {
                if (!polling) return;
                if (p.status === 'fetching' && p.total > 0) {
                    const pct = Math.round((p.current / p.total) * 100);
                    fill.style.width = pct + '%';
                    statusEl.textContent = p.plate ? `Processing ${p.plate}...` : 'Connecting to TTAS...';
                    countEl.textContent = `${p.current} / ${p.total} vehicles`;
                    if (p.current > 0 && p.started_at) {
                        const elapsed = (Date.now() / 1000) - p.started_at;
                        const perItem = elapsed / p.current;
                        const remaining = perItem * (p.total - p.current);
                        etaEl.textContent = `~${fmt(remaining)} remaining`;
                    } else {
                        etaEl.textContent = '';
                    }
                    setTimeout(pollProgress, 500);
                } else if (p.status === 'done' || p.status === 'error') {
                    fill.style.width = '100%';
                    statusEl.textContent = p.status === 'done' ? 'Complete' : 'Failed';
                    countEl.textContent = `${p.current || 0} / ${p.total || 0} vehicles`;
                    etaEl.textContent = '';
                }
            })
            .catch(() => {
                if (polling) setTimeout(pollProgress, 1000);
            });
    };
    setTimeout(pollProgress, 300);

    try {
        const data = await ApiClient.fetch('/oil-maintenance/fetch-km', { method: 'POST' });

        polling = false;
        overlay.classList.remove('active');

        UI.toast(data.message, 'success');

        if (data.errors && data.errors.length) {
            data.errors.forEach(e => UI.toast(e, 'warning', 8000));
        }

        await loadVehicles();
    } catch (err) {
        polling = false;
        overlay.classList.remove('active');
        UI.toast(`KM fetch failed: ${err.message}`, 'error', 8000);
    } finally {
        btn.disabled      = false;
        icon.textContent  = '';
        label.textContent = 'Refresh KM Data';
    }
}

// ── Export CSV ─────────────────────────────────────────────────
function exportCsv() {
    const a = document.createElement('a');
    a.href = '/api/oil-maintenance/export';
    a.download = 'oil_maintenance_report.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

