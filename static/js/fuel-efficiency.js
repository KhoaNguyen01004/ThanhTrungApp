/**
 * fuel-efficiency.js
 * Dashboard controller: monthly filter, time-series chart, CRUD, anomaly detection.
 */

let allEntries = [];
let filteredEntries = [];
let sortKey = 'log_date';
let sortDir = -1;
let editingId = null;
let selectedVehicleId = null;
let selectedVehicleType = '';
let chartInstance = null;
const PAGE_MODE = (document.getElementById('page-mode')?.value || 'regular');
let selectedChartVehicleId = null;
let allVehicles = [];

// ── Init ───────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    await populateMonthSelect();
    await loadVehicles();
    loadProfiles();
    onMonthChange();
    setDefaultTime();
});

function setDefaultTime() {
    const now = new Date();
    const d = document.getElementById('field-date');
    const t = document.getElementById('field-time');
    if (d) d.value = todayISO();
    if (t) t.value = String(now.getHours()).padStart(2,'0') + ':' + String(now.getMinutes()).padStart(2,'0');
}

// ── Month Selector ─────────────────────────────────────────────
async function populateMonthSelect() {
    const sel = document.getElementById('month-select');
    sel.innerHTML = '';
    let months = [];
    try {
        const data = await ApiClient.fetch(`/fuel-log/months?mode=${PAGE_MODE}`);
        months = data.data || [];
    } catch (_) {}
    const allOpt = document.createElement('option');
    allOpt.value = '';
    allOpt.textContent = 'All time';
    sel.appendChild(allOpt);

    sel.selectedIndex = 0;
    for (const ym of months) {
        const d = new Date(ym + '-01');
        const opt = document.createElement('option');
        opt.value = ym;
        opt.textContent = d.toLocaleDateString('en-US', { year: 'numeric', month: 'long' });
        sel.appendChild(opt);
    }
}

function getSelectedMonth() {
    return document.getElementById('month-select').value;
}

let availableDays = [];
let selectedDay = '';

async function populateDaySelect() {
    const sel = document.getElementById('day-select');
    const month = getSelectedMonth();
    sel.innerHTML = '<option value="">All days</option>';
    availableDays = [];
    if (!month) { sel.disabled = true; return; }
    sel.disabled = false;
    try {
        const data = await ApiClient.fetch(`/fuel-log/days?month=${month}&mode=${PAGE_MODE}`);
        availableDays = data.data || [];
    } catch (_) {}
    for (const day of availableDays) {
        const opt = document.createElement('option');
        opt.value = day;
        const d = new Date(day + 'T00:00:00');
        opt.textContent = d.getDate().toString();
        if (day === selectedDay) opt.selected = true;
        sel.appendChild(opt);
    }
    // If selectedDay not in available list, reset
    if (selectedDay && !availableDays.includes(selectedDay)) {
        selectedDay = '';
        sel.value = '';
    }
}

function changeDay(delta) {
    const sel = document.getElementById('day-select');
    const idx = sel.selectedIndex + delta;
    if (idx >= 0 && idx < sel.options.length) {
        sel.selectedIndex = idx;
        onDayChange();
    }
}

function onDayChange() {
    selectedDay = document.getElementById('day-select').value;
    const dayFiltered = selectedDay ? allEntries.filter(e => e.log_date === selectedDay) : allEntries;
    recomputeStats();
    renderChart(dayFiltered);
    filterTable(document.getElementById('table-search').value);
}

function changeMonth(delta) {
    const sel = document.getElementById('month-select');
    const idx = sel.selectedIndex + delta;
    if (idx >= 0 && idx < sel.options.length) {
        sel.selectedIndex = idx;
        onMonthChange();
    }
}

function onMonthChange() {
    selectedDay = '';
    populateDaySelect();
    loadDashboard();
}

// ── Load Dashboard ─────────────────────────────────────────────
async function loadDashboard() {
    const month = getSelectedMonth();
    try {
        const [listData, summaryData] = await Promise.all([
            ApiClient.fetch(`/fuel-log?month=${month}&mode=${PAGE_MODE}`),
            ApiClient.fetch(`/fuel-log/summary?month=${month}`),
        ]);
        allEntries = (listData.data || []).filter(e => {
            const isContainer = (e.vehicle_type || '').toLowerCase().includes('container');
            return PAGE_MODE === 'container' ? isContainer : !isContainer;
        });
        applyFilters();
        recomputeStats();
        renderChart(allEntries);
        renderTable();
        document.getElementById('entry-count').textContent = filteredEntries.length;
        loadProfiles();
    } catch (err) {
        UI.toast(`Failed to load: ${err.message}`, 'error');
    }
}

// ── Stats ───────────────────────────────────────────────────────
function recomputeStats() {
    let base = selectedChartVehicleId
        ? allEntries.filter(e => e.vehicle_id === selectedChartVehicleId)
        : allEntries;
    if (selectedDay) base = base.filter(e => e.log_date === selectedDay);
    const valid = base.filter(e => e.distance_km > 0 && e.liters > 0);
    const noKm = base.filter(e => e.distance_km === 0);
    const total_distance = valid.reduce((s, e) => s + e.distance_km, 0);
    const total_fuel = valid.reduce((s, e) => s + e.liters, 0);
    const sum_l100 = valid.reduce((s, e) => s + e.l_per_100km, 0);
    const spikeCount = valid.filter(e => e.is_anomaly).length;
    const totalEntries = base.length;
    const totalCost = base.reduce((s, e) => s + (e.total_cost || 0), 0);
    renderStats({
        total_distance,
        total_fuel: Math.round(total_fuel * 100) / 100,
        avg_l_per_100km: valid.length > 0 ? Math.round((sum_l100 / valid.length) * 100) / 100 : 0,
        entry_count: totalEntries,
        anomaly_count: spikeCount,
        no_km_count: noKm.length,
        total_cost: Math.round(totalCost * 100) / 100
    });
}

function renderStats(stats) {
    document.getElementById('kpi-distance').innerHTML = `${stats.total_distance.toLocaleString()} <span style="font-size:1rem;font-weight:400;color:#94a3b8;">km</span>`;
    document.getElementById('kpi-distance-sub').textContent = `${stats.entry_count} entries`;
    document.getElementById('kpi-fuel').innerHTML = `${stats.total_fuel.toLocaleString()} <span style="font-size:1rem;font-weight:400;color:#94a3b8;">L</span>`;
    const flags = [];
    if (stats.anomaly_count > 0) flags.push(`${stats.anomaly_count} spike`);
    if (stats.no_km_count > 0) flags.push(`${stats.no_km_count} no KM`);
    document.getElementById('kpi-fuel-sub').textContent = flags.length > 0 ? flags.join(', ') : 'No issues';
    document.getElementById('kpi-cost').innerHTML = `${Number(stats.total_cost || 0).toLocaleString('en-US')} <span style="font-size:1rem;font-weight:400;color:#94a3b8;">VND</span>`;
    document.getElementById('kpi-avg').innerHTML = `${Number(stats.avg_l_per_100km).toFixed(2)} <span style="font-size:1rem;font-weight:400;color:#94a3b8;">L/100km</span>`;
    document.getElementById('kpi-avg-sub').textContent = stats.entry_count > 0 ? `${Number(stats.avg_l_per_100km).toFixed(2)} L/100km avg` : 'No data';
}

// ── Filtering (search only) ────────────────────────────────────
function applyFilters() {
    const q = document.getElementById('table-search').value.trim().toLowerCase();
    const issueFilter = document.getElementById('issue-filter')?.value || '';
    filteredEntries = allEntries.filter(e => {
        if (selectedDay && e.log_date !== selectedDay) return false;
        if (selectedChartVehicleId && e.vehicle_id !== selectedChartVehicleId) return false;
        if (issueFilter === 'issues') {
            const isIssue = e.is_anomaly || e.distance_km === 0 || (PAGE_MODE === 'container' && !e.is_full_tank);
            if (!isIssue) return false;
        }
        if (!q) return true;
        return e.license_plate.toLowerCase().includes(q)
            || (e.driver_name || '').toLowerCase().includes(q)
            || (e.gas_store || '').toLowerCase().includes(q);
    });
    if (sortKey) {
        filteredEntries.sort((a, b) => {
            let va = a[sortKey], vb = b[sortKey];
            if (typeof va === 'string') return va.localeCompare(vb) * sortDir;
            return ((va ?? 0) - (vb ?? 0)) * sortDir;
        });
    }
}

function onFilterChange() {
    applyFilters();
    renderTable();
    recomputeStats();
    renderChart(allEntries);
    document.getElementById('entry-count').textContent = filteredEntries.length;
}

function filterTable(q) {
    applyFilters();
    renderTable();
    document.getElementById('entry-count').textContent = filteredEntries.length;
}

// ── Click row to filter by vehicle (All Time) ──────────────────
async function filterByVehicle(vehicleId, plate) {
    if (!vehicleId) return;
    selectedChartVehicleId = vehicleId;
    document.getElementById('month-select').value = '';
    selectedDay = '';
    populateDaySelect();
    await loadDashboard();
    const input = document.getElementById('table-search');
    input.value = plate;
    updateFilterLabel();
    renderSearchDropdown(plate);
}

// ── Table ──────────────────────────────────────────────────────
function renderTable() {
    const tbody = document.getElementById('table-body');
    const empty = document.getElementById('empty-state');
    if (!filteredEntries.length) {
        tbody.innerHTML = '';
        empty.style.display = 'block';
        document.getElementById('entry-count').textContent = 0;
        return;
    }
    empty.style.display = 'none';

    tbody.innerHTML = filteredEntries.map(e => {
        const anomaly = e.is_anomaly;
        const noKm = e.distance_km === 0;
        const partial = PAGE_MODE === 'container' && !e.is_full_tank;
        const dist = e.distance_km > 0 ? fmtNum(e.distance_km) : '—';
        const l100 = e.l_per_100km > 0 ? e.l_per_100km.toFixed(2) : '—';
        let anomalyBadge = '';
        if (partial) {
            anomalyBadge = '<span style="color:#f59e0b;font-size:11px;">⛽ Partial</span>';
        } else if (noKm) {
            anomalyBadge = '<span style="color:#f59e0b;font-size:11px;">⚠ No KM</span>';
        } else if (anomaly) {
            anomalyBadge = '<span class="anomaly-badge">⚠ Spike</span>';
        } else {
            anomalyBadge = '<span style="color:#4ade80;font-size:11px;">✓ Normal</span>';
        }
        const rowClass = anomaly ? 'anomaly-row' : noKm ? 'no-km-row' : '';
        return `<tr class="${rowClass}" data-vehicle-id="${e.vehicle_id || ''}" data-vehicle-plate="${UI.escapeHtml(e.license_plate)}">
            <td>${formatDate(e.log_date)}</td>
            <td>${UI.escapeHtml(e.log_time || '—')}</td>
            <td>${UI.escapeHtml(e.gas_store || '—')}</td>
            <td><span class="plate-badge">${UI.escapeHtml(e.license_plate)}</span></td>
            <td>${dist !== '—' ? `<span class="fuel-value">${dist}</span> <span class="fuel-muted">km</span>` : '<span class="fuel-muted">—</span>'}</td>
            <td><span class="fuel-value">${e.liters.toFixed(1)}</span> <span class="fuel-muted">L</span></td>
            <td><span class="fuel-value">${l100}</span></td>
            <td>${UI.escapeHtml(e.driver_name || '—')}</td>
            <td>${PAGE_MODE === 'container' ? (e.is_full_tank ? '<span style="color:#4ade80;font-size:11px;">Full</span>' : '<span style="color:#f59e0b;font-size:11px;">Partial</span>') : ''}</td>
            <td>${anomalyBadge}</td>
            <td>
                <div style="display:flex;gap:6px;">
                    <button class="btn-action btn-edit" onclick="event.stopPropagation();openModal(${e.id})">✏️</button>
                    <button class="btn-action btn-delete" onclick="event.stopPropagation();deleteEntry(${e.id})">🗑</button>
                </div>
            </td>
        </tr>`;
    }).join('');
}

function sortTable(key) {
    if (sortKey === key) { sortDir *= -1; }
    else { sortKey = key; sortDir = 1; }
    applyFilters();
    renderTable();
}

// ── Chart (Chart.js) ───────────────────────────────────────────
function renderChart(entries) {
    const canvas = document.getElementById('efficiency-chart');
    const noData = document.getElementById('no-chart-data');

    if (chartInstance) { chartInstance.destroy(); chartInstance = null; }

    const data = entries.filter(e => e.distance_km > 0 && e.liters > 0 && e.l_per_100km > 0);
    const filtered = selectedChartVehicleId
        ? data.filter(e => e.vehicle_id === selectedChartVehicleId)
        : data;

    if (filtered.length === 0) {
        noData.style.display = 'flex';
        return;
    }
    noData.style.display = 'none';

    // Build chart series: if All Vehicles, aggregate by date
    let sorted, chartEntries;
    if (selectedChartVehicleId) {
        chartEntries = [...filtered].sort((a, b) => a.log_date.localeCompare(b.log_date) || a.log_time.localeCompare(b.log_time));
        sorted = chartEntries;
    } else {
        const groups = {};
        for (const e of filtered) {
            if (!groups[e.log_date]) groups[e.log_date] = [];
            groups[e.log_date].push(e);
        }
        chartEntries = Object.keys(groups).sort().map(date => {
            const g = groups[date];
            const sumL100 = g.reduce((s, e) => s + e.l_per_100km, 0);
            const avgL100 = sumL100 / g.length;
            const isAnomaly = g.some(e => e.is_anomaly);
            const vehicles = g.map(e => e.license_plate).filter((v, i, a) => a.indexOf(v) === i);
            return {
                log_date: date,
                l_per_100km: avgL100,
                is_anomaly: isAnomaly,
                _count: g.length,
                _vehicles: vehicles.join(', ')
            };
        });
        sorted = chartEntries;
    }

    const labels = sorted.map(e => e.log_date);
    const values = sorted.map(e => e.l_per_100km);
    const anomalies = sorted.map(e => e.is_anomaly);
    const anomalyValues = sorted.map((e, i) => e.is_anomaly ? e.l_per_100km : null);

    const dataLabelPlugin = {
        id: 'dataLabels',
        afterDraw(chart) {
            const ctx = chart.ctx;
            chart.data.datasets.forEach((dataset, i) => {
                const meta = chart.getDatasetMeta(i);
                if (meta.hidden) return;
                meta.data.forEach((element, index) => {
                    const value = dataset.data[index];
                    if (value == null || value <= 0) return;
                    ctx.save();
                    ctx.font = 'bold 10px Inter, sans-serif';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'bottom';
                    const label = value.toFixed(1);
                    ctx.fillStyle = 'rgba(13,17,23,0.8)';
                    ctx.fillRect(element.x - 14, element.y - 20, 28, 14);
                    ctx.fillStyle = '#f8fafc';
                    ctx.fillText(label, element.x, element.y - 9);
                    ctx.restore();
                });
            });
        }
    };

    const ctx = canvas.getContext('2d');
    Chart.register(dataLabelPlugin);
    chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'L/100km',
                    data: values,
                    borderColor: '#2f8ceb',
                    backgroundColor: 'rgba(47,140,235,0.1)',
                    borderWidth: 2,
                    pointBackgroundColor: values.map((v, i) => anomalies[i] ? '#ef4444' : '#2f8ceb'),
                    pointBorderColor: values.map((v, i) => anomalies[i] ? '#ef4444' : '#2f8ceb'),
                    pointRadius: values.map((v, i) => anomalies[i] ? 7 : 4),
                    pointHoverRadius: values.map((v, i) => anomalies[i] ? 10 : 6),
                    fill: true,
                    tension: 0.3,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: true, mode: 'point' },
            onClick: (e, elements) => {
                if (elements.length > 0) {
                    const idx = elements[0].dataIndex;
                    const entry = sorted[idx];
                    if (entry.is_anomaly) {
                        showAnomalyTooltip(e, entry);
                    } else {
                        hideAnomalyTooltip();
                    }
                }
            },
            scales: {
                x: {
                    ticks: { color: '#94a3b8', maxTicksLimit: 12 },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                },
                y: {
                    beginAtZero: true,
                    ticks: { color: '#94a3b8' },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                }
            },
            plugins: {
                legend: {
                    labels: { color: '#b0bec9', font: { size: 12 } }
                },
                tooltip: {
                    enabled: true,
                    backgroundColor: '#1e293b',
                    titleColor: '#f8fafc',
                    bodyColor: '#cbd5e1',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    callbacks: {
                        label: (ctx) => {
                            const e = sorted[ctx.dataIndex];
                            if (e._count) {
                                return ` ${e.l_per_100km.toFixed(2)} L/100km avg (${e._count} entries, ${e._vehicles})`;
                            }
                            return ` ${e.l_per_100km.toFixed(2)} L/100km | ${e.liters.toFixed(1)} L | ${e.distance_km} km | ${e.license_plate}`;
                        }
                    }
                }
            }
        }
    });
}

function showAnomalyTooltip(event, entry) {
    const tooltip = document.getElementById('anomaly-tooltip');
    document.getElementById('tooltip-title').textContent = `⚠ Anomaly — ${entry.license_plate}`;
    document.getElementById('tooltip-body').innerHTML = `
        <div class="row"><span>Date</span><span class="val">${entry.log_date}</span></div>
        <div class="row"><span>Distance</span><span class="val">${entry.distance_km} km</span></div>
        <div class="row"><span>Fuel</span><span class="val">${entry.liters.toFixed(1)} L</span></div>
        <div class="row"><span>Efficiency</span><span class="val">${entry.l_per_100km.toFixed(2)} L/100km</span></div>
        <div class="row"><span>Baseline</span><span class="val">${entry.baseline} L/100km</span></div>
        <div class="row"><span>Driver</span><span class="val">${entry.driver_name || '—'}</span></div>
        <div class="row"><span>Store</span><span class="val">${entry.gas_store || '—'}</span></div>
    `;
    tooltip.style.left = Math.min(event.x, window.innerWidth - 280) + 'px';
    tooltip.style.top = Math.min(event.y + 10, window.innerHeight - 300) + 'px';
    tooltip.classList.add('show');
}

function hideAnomalyTooltip() {
    document.getElementById('anomaly-tooltip').classList.remove('show');
}

document.addEventListener('click', (e) => {
    if (!e.target.closest('#anomaly-tooltip') && !e.target.closest('canvas')) {
        hideAnomalyTooltip();
    }
});

// ── Combined Search & Vehicle Selector ───────────────────────
function isContainerV(vt) {
    return (vt || '').toLowerCase().includes('container');
}

async function loadVehicles() {
    try {
        const data = await ApiClient.fetch('/fleet/vehicles');
        allVehicles = data.data || [];
        updateFilterLabel();
    } catch (_) {}
}

function renderSearchDropdown(q) {
    const dropdown = document.getElementById('search-dropdown');
    const trimmed = q.trim();
    const modeVehicles = allVehicles.filter(v =>
        PAGE_MODE === 'container' ? isContainerV(v.vehicle_type) : !isContainerV(v.vehicle_type)
    );
    let matches;
    if (!trimmed) {
        matches = modeVehicles;
    } else {
        const lower = trimmed.toLowerCase();
        matches = modeVehicles.filter(v =>
            v.plate_number.toLowerCase().includes(lower)
            || (v.current_driver || '').toLowerCase().includes(lower)
        );
    }
    const limited = matches.slice(0, 10);

    if (limited.length === 0) {
        dropdown.innerHTML = `<div class="autocomplete-item" style="color:#f87171;cursor:default;">No vehicle found for "${UI.escapeHtml(trimmed)}"</div>`;
    } else {
        dropdown.innerHTML = `
            <div class="autocomplete-item ${!selectedChartVehicleId ? 'selected' : ''}" onclick="selectSearchVehicle(null, '')">All vehicles (${modeVehicles.length})</div>
            ${limited.map(v => `
                <div class="autocomplete-item ${selectedChartVehicleId === v.id ? 'selected' : ''}" onclick="selectSearchVehicle(${v.id}, '${UI.escapeHtml(v.plate_number)}')">
                    ${UI.escapeHtml(v.plate_number)}
                    <span class="sub">${v.vehicle_type || ''}${v.current_driver ? ' — ' + UI.escapeHtml(v.current_driver) : ''}</span>
                </div>
            `).join('')}
        `;
    }
    dropdown.classList.add('open');
}

function onSearchInput(q) {
    const trimmed = q.trim();
    if (!trimmed) {
        // Clear vehicle selection, show all
        selectedChartVehicleId = null;
        applyFilters();
        renderTable();
        recomputeStats();
        renderChart(allEntries);
        document.getElementById('entry-count').textContent = filteredEntries.length;
        updateFilterLabel();
    } else {
        // Filter table by text, keep chart on all vehicles unless one is selected
        applyFilters();
        renderTable();
        recomputeStats();
        renderChart(allEntries);
        document.getElementById('entry-count').textContent = filteredEntries.length;
        updateFilterLabel();
    }
    renderSearchDropdown(q);
}

function showSearchDropdown() {
    const input = document.getElementById('table-search');
    renderSearchDropdown(input.value);
}

function hideSearchDropdown() {
    document.getElementById('search-dropdown')?.classList.remove('open');
}

function selectSearchVehicle(id, plate) {
    selectedChartVehicleId = id;
    const input = document.getElementById('table-search');
    input.value = plate;
    hideSearchDropdown();
    // Filter table to this vehicle
    applyFilters();
    renderTable();
    recomputeStats();
    renderChart(allEntries);
    document.getElementById('entry-count').textContent = filteredEntries.length;
    updateFilterLabel();
}

function updateFilterLabel() {
    const label = document.getElementById('chart-filter-label');
    if (!label) return;
    if (selectedChartVehicleId) {
        const v = allVehicles.find(x => x.id === selectedChartVehicleId);
        label.textContent = v ? v.plate_number : 'All vehicles';
    } else {
        label.textContent = 'All vehicles';
    }
}

// ── Vehicle Autocomplete in Modal ──────────────────────────────
function onVehicleInput(q) {
    const dropdown = document.getElementById('vehicle-dropdown');
    if (!q.trim()) { dropdown.classList.remove('open'); selectedVehicleId = null; return; }
    const isContainer = (vt) => (vt || '').toLowerCase().includes('container');
    const matches = allVehicles.filter(v =>
        v.plate_number.toLowerCase().includes(q.toLowerCase()) &&
        (PAGE_MODE === 'container' ? isContainer(v.vehicle_type) : !isContainer(v.vehicle_type))
    ).slice(0, 8);
    if (matches.length === 0) { dropdown.classList.remove('open'); return; }
    dropdown.innerHTML = matches.map(v =>
        `<div class="autocomplete-item" onclick="selectVehicle(${v.id}, '${UI.escapeHtml(v.plate_number)}', '${UI.escapeHtml(v.vehicle_type || '')}', '${UI.escapeHtml(v.current_driver || '')}')">
            ${UI.escapeHtml(v.plate_number)}
            <span class="sub">${v.vehicle_type || ''} ${v.current_driver ? '— ' + UI.escapeHtml(v.current_driver) : ''}</span>
        </div>`
    ).join('');
    dropdown.classList.add('open');
}

async function selectVehicle(id, plate, vtype, driver) {
    selectedVehicleId = id;
    selectedVehicleType = vtype;
    document.getElementById('field-plate').value = plate;
    document.getElementById('field-vtype').value = vtype;
    document.getElementById('field-driver').value = driver;
    document.getElementById('vehicle-dropdown').classList.remove('open');
    if (editingId) return; // don't auto-fill on edit
    try {
        const data = await ApiClient.fetch(`/fuel-log/last-km?plate=${encodeURIComponent(plate)}`);
        const km = data.new_km || 0;
        document.getElementById('field-old-km').value = km > 0 ? km : '';
    } catch (_) {}
}

// ── Modal ──────────────────────────────────────────────────────
function openModal(id = null) {
    editingId = id;
    const overlay = document.getElementById('modal-overlay');
    const title = document.getElementById('modal-title');
    const btnSave = document.getElementById('btn-save');
    selectedVehicleId = null;
    selectedVehicleType = '';
    document.getElementById('field-time-group').style.display = PAGE_MODE === 'container' ? 'none' : '';
    document.getElementById('field-store-group').style.display = PAGE_MODE === 'container' ? 'none' : '';

    if (id) {
        const e = allEntries.find(x => x.id === id);
        title.textContent = 'Edit Refuel Entry';
        btnSave.textContent = 'Save Changes';
        selectedVehicleId = e.vehicle_id || null;
        document.getElementById('field-plate').value = e ? e.license_plate : '';
        document.getElementById('field-vtype').value = e ? (e.vehicle_type || '') : '';
        document.getElementById('field-driver').value = e ? (e.driver_name || '') : '';
        document.getElementById('field-date').value = e ? e.log_date : todayISO();
        document.getElementById('field-time').value = e ? e.log_time : '';
        document.getElementById('field-store').value = e ? (e.gas_store || '') : '';
        document.getElementById('field-old-km').value = e && e.old_km ? e.old_km : '';
        document.getElementById('field-new-km').value = e && e.new_km ? e.new_km : '';
        document.getElementById('field-liters').value = e ? e.liters : '';
        document.getElementById('field-price').value = e ? (e.unit_price || '') : '';
        document.getElementById('field-notes').value = e ? (e.notes || '') : '';
        const ft = document.getElementById('field-fulltank');
        if (ft) ft.checked = e ? (e.is_full_tank !== false) : true;
    } else {
        title.textContent = 'Add Refuel Entry';
        btnSave.textContent = 'Save Entry';
        document.getElementById('field-plate').value = '';
        document.getElementById('field-vtype').value = '';
        document.getElementById('field-driver').value = '';
        document.getElementById('field-store').value = '';
        document.getElementById('field-old-km').value = '';
        document.getElementById('field-new-km').value = '';
        document.getElementById('field-liters').value = '';
        document.getElementById('field-price').value = '';
        document.getElementById('field-notes').value = '';
        setDefaultTime();
        setTimeout(() => document.getElementById('field-plate').focus(), 200);
    }
    overlay.classList.add('open');
}

function closeModal() {
    document.getElementById('modal-overlay').classList.remove('open');
    editingId = null;
    selectedVehicleId = null;
    selectedVehicleType = '';
}

function handleOverlayClick(e) {
    if (e.target === document.getElementById('modal-overlay')) closeModal();
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

// ── Save Entry ─────────────────────────────────────────────────
async function saveEntry() {
    const plate = document.getElementById('field-plate').value.trim().toUpperCase();
    const date = document.getElementById('field-date').value.trim();
    const time = document.getElementById('field-time').value.trim();
    const store = document.getElementById('field-store').value.trim();
    const oldKmVal = document.getElementById('field-old-km').value.trim();
    const newKmVal = document.getElementById('field-new-km').value.trim();
    const hasKm = oldKmVal !== '' && newKmVal !== '';
    const oldKm = hasKm ? parseInt(oldKmVal, 10) || 0 : 0;
    const newKm = hasKm ? parseInt(newKmVal, 10) || 0 : 0;
    const liters = parseFloat(document.getElementById('field-liters').value);
    const driver = document.getElementById('field-driver').value.trim();
    const price = document.getElementById('field-price').value.trim();
    const notes = document.getElementById('field-notes').value.trim();

    if (!plate) return UI.toast('Select a vehicle.', 'warning');
    if (!date) return UI.toast('Date is required.', 'warning');
    if (!time && PAGE_MODE !== 'container') return UI.toast('Time is required.', 'warning');
    if (isNaN(liters) || liters <= 0) return UI.toast('Liters must be > 0.', 'warning');
    if (newKm > 0 && oldKm > 0 && newKm < oldKm) return UI.toast('New KM must be >= Old KM.', 'warning');
    if (newKm - oldKm > 2000 && !confirm('Distance exceeds 2000 km — are you sure?')) return;

    const isFullTank = document.getElementById('field-fulltank')?.checked !== false;
    const payload = {
        license_plate: plate,
        log_date: date, log_time: time, gas_store: store,
        old_km: oldKm, new_km: newKm, liters,
        driver_name: driver, notes,
        vehicle_id: selectedVehicleId,
        is_full_tank: isFullTank
    };
    if (price) payload.unit_price = parseFloat(price);

    const btn = document.getElementById('btn-save');
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span> Saving…';

    try {
        if (editingId) {
            const result = await ApiClient.fetch(`/fuel-log/${editingId}`, { method: 'PUT', body: JSON.stringify(payload) });
            if (result.warnings) result.warnings.forEach(w => UI.toast(w, 'warning', 6000));
            UI.toast('Entry updated.', 'success');
        } else {
            const result = await ApiClient.fetch('/fuel-log', { method: 'POST', body: JSON.stringify(payload) });
            if (result.warnings) result.warnings.forEach(w => UI.toast(w, 'warning', 6000));
            UI.toast('Entry created.', 'success');
        }
        closeModal();
        await loadDashboard();
        await loadProfiles();
    } catch (err) {
        if (!handleUnknownVehicle(err)) UI.toast(err.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = editingId ? 'Save Changes' : 'Save Entry';
    }
}

// ── Unknown vehicle → Vehicle Management ───────────────────────
// The server no longer creates a vehicle for an unrecognised plate, because
// that silently added rows to core fleet data (and, matching on the exact
// plate string, created duplicates of trucks that were already registered).
// Matching is loose — exact, then ignoring case/separators, then on the
// 5-digit serial — so this only fires for a plate genuinely not in the fleet.
// When it does, send the user to register it with everything we already know
// pre-filled, rather than making them retype it.
function handleUnknownVehicle(err) {
    const info = err && err.data;
    if (!info || info.error_code !== 'unknown_vehicle') return false;

    const v = info.unknown_vehicle || {};
    const entered = v.entered || '';
    const suggested = v.suggested_plate || entered;

    const proceed = confirm(
        `"${entered}" is not a registered vehicle, so nothing was saved.\n\n` +
        `Add it to Vehicle Management now?\n` +
        `The form will be pre-filled with plate ${suggested}` +
        (v.current_driver ? ` and driver ${v.current_driver}` : '') + `.`
    );
    if (proceed && info.redirect_to) {
        window.location.href = info.redirect_to;
    } else {
        UI.toast(info.message, 'error', 6000);
    }
    return true;
}

// ── Delete Entry ───────────────────────────────────────────────
async function deleteEntry(id) {
    const entry = allEntries.find(e => e.id === id);
    const label = entry ? `${entry.license_plate} on ${entry.log_date}` : `#${id}`;
    if (!confirm(`Delete entry for ${label}?`)) return;
    try {
        await ApiClient.fetch(`/fuel-log/${id}`, { method: 'DELETE' });
        UI.toast('Entry deleted.', 'success');
        await loadDashboard();
        await loadProfiles();
    } catch (err) {
        UI.toast(err.message, 'error');
    }
}

// ── Export CSV ─────────────────────────────────────────────────
function exportCsv() {
    const month = getSelectedMonth();
    const a = document.createElement('a');
    a.href = `/api/fuel-log/export?month=${month}&mode=${PAGE_MODE}`;
    a.download = 'fuel_efficiency_report.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

// ── Vehicle Baselines ──────────────────────────────────────────
async function loadProfiles() {
    try {
        const data = await ApiClient.fetch('/fuel-log/profiles');
        renderProfiles(data.data || []);
    } catch (_) {}
}

function renderProfiles(profiles) {
    const tbody = document.getElementById('profile-body');
    const empty = document.getElementById('profile-empty');
    const isContainer = (vt) => (vt || '').toLowerCase().includes('container');
    const filtered = profiles.filter(p => {
        const vt = (allVehicles.find(v => v.plate_number === p.license_plate) || {}).vehicle_type || '';
        return PAGE_MODE === 'container' ? isContainer(vt) : !isContainer(vt);
    });
    document.getElementById('profile-count').textContent = filtered.length;

    if (!filtered.length) {
        tbody.innerHTML = '';
        empty.style.display = 'block';
        return;
    }
    empty.style.display = 'none';

    const sorted = [...filtered].sort((a, b) => a.license_plate.localeCompare(b.license_plate));
    tbody.innerHTML = sorted.map(p => {
        const pid = UI.escapeHtml(p.license_plate);
        const normal = p.normal_l_per_100km || 0;
        const mult = p.anomaly_multiplier || (PAGE_MODE === 'container' ? 1.5 : 1.2);
        const updated = p.updated_at ? formatDateTime(p.updated_at) : '—';
        return `<tr>
            <td><span class="plate-badge">${pid}</span></td>
            <td>
                <span class="fuel-value" id="nd-${pid}">${normal > 0 ? normal.toFixed(2) : '—'} <span class="fuel-muted">L/100km</span></span>
                <input type="number" step="0.1" min="1" max="99" class="field-input" style="width:90px;display:none;padding:5px 8px;" id="ni-${pid}" value="${normal > 0 ? normal : ''}">
            </td>
            <td>
                <span class="fuel-value" id="md-${pid}">${mult.toFixed(2)} <span class="fuel-muted">x</span></span>
                <input type="number" step="0.05" min="1.0" max="5.0" class="field-input" style="width:75px;display:none;padding:5px 8px;" id="mi-${pid}" value="${mult}">
            </td>
            <td style="color:#94a3b8;font-size:12px;">${updated}</td>
            <td>
                <div style="display:flex;gap:6px;">
                    <button class="btn-action btn-edit" id="neb-${pid}" onclick="editNormal('${pid}')">✏️</button>
                    <button class="btn-action btn-edit" style="display:none;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.25);" id="nsb-${pid}" onclick="saveNormal('${pid}')">💾</button>
                    <button class="btn-action btn-delete" id="ncb-${pid}" ${normal > 0 || mult ? '' : 'style="display:none;"'} onclick="clearNormal('${pid}')">🗑</button>
                </div>
            </td>
        </tr>`;
    }).join('');
}

function editNormal(plate) {
    const sid = UI.escapeHtml(plate);
    document.getElementById(`nd-${sid}`).style.display = 'none';
    document.getElementById(`ni-${sid}`).style.display = 'inline-block';
    document.getElementById(`md-${sid}`).style.display = 'none';
    document.getElementById(`mi-${sid}`).style.display = 'inline-block';
    document.getElementById(`ni-${sid}`).focus();
    document.getElementById(`neb-${sid}`).style.display = 'none';
    document.getElementById(`nsb-${sid}`).style.display = 'inline-flex';
}

async function saveNormal(plate) {
    const pid = UI.escapeHtml(plate);
    const normalVal = parseFloat(document.getElementById(`ni-${pid}`)?.value);
    const multVal = parseFloat(document.getElementById(`mi-${pid}`)?.value);
    const body = {};
    if (!isNaN(normalVal) && normalVal > 0) body.normal_l_per_100km = normalVal;
    if (isNaN(normalVal) || normalVal <= 0) return UI.toast('Enter a valid L/100km > 0.', 'warning');
    if (!isNaN(multVal) && multVal >= 1.0) body.anomaly_multiplier = multVal;
    try {
        await ApiClient.fetch(`/fuel-log/profiles/${encodeURIComponent(plate)}`, {
            method: 'PUT', body: JSON.stringify(body)
        });
        const parts = [`Normal: ${normalVal.toFixed(2)} L/100km`];
        if (body.anomaly_multiplier) parts.push(`Multiplier: ${multVal.toFixed(2)}x`);
        UI.toast(`${plate} — ${parts.join(', ')}`, 'success');
        await loadProfiles();
        await loadDashboard();
    } catch (err) {
        UI.toast(err.message, 'error');
    }
}

async function clearNormal(plate) {
    if (!confirm(`Clear normal for ${plate}? Will revert to computed baseline.`)) return;
    try {
        await ApiClient.fetch(`/fuel-log/profiles/${encodeURIComponent(plate)}`, { method: 'DELETE' });
        UI.toast(`Normal for ${plate} cleared.`, 'success');
        await loadProfiles();
        await loadDashboard();
    } catch (err) {
        UI.toast(err.message, 'error');
    }
}

// ── Tooltip hide on scroll ─────────────────────────────────────
document.addEventListener('scroll', hideAnomalyTooltip);

// ── Row click: filter by vehicle ───────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('table-body').addEventListener('click', (e) => {
        const tr = e.target.closest('tr');
        if (!tr) return;
        if (e.target.closest('button')) return;
        const vehicleId = tr.dataset.vehicleId;
        const plate = tr.dataset.vehiclePlate;
        if (vehicleId) {
            filterByVehicle(parseInt(vehicleId), plate);
        }
    });
});

// ── Utilities ──────────────────────────────────────────────────
function formatDateTime(iso) {
    if (!iso) return '—';
    try {
        const d = new Date(iso);
        return `${String(d.getDate()).padStart(2,'0')}/${String(d.getMonth()+1).padStart(2,'0')}/${d.getFullYear()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
    } catch { return iso; }
}
