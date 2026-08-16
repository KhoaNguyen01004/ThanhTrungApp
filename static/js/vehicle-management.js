/**
 * vehicle-management.js
 * CRUD for master vehicles + container configuration + interactive diagram.
 */

let allVehicles = [];
let filteredVehicles = [];
let allTypes = [];
let editingId = null;
let selectedIds = new Set();


const diagram = { currentVehicleId: null };

document.addEventListener('DOMContentLoaded', () => {
    loadVehicles().then(openPrefilledFromQuery);
    loadTypes();
    window.addEventListener('resize', () => {
        if (diagram3D.currentVehicleId) selectVehicleForDiagram(diagram3D.currentVehicleId);
    });
});

// ── Arrive-with-prefill (?new=1&plate=…&driver=…) ───────────────
// Other pages (fuel logging, delivery import) refuse to create a vehicle for
// an unrecognised plate and send the user here instead. They pass along what
// they already know so the Add Vehicle form opens pre-filled — the values are
// only ever suggestions in an editable form, never written without the user
// pressing Save. Size and dimensions are deliberately NOT pre-filled: nothing
// upstream knows them, and guessing core specs is exactly what we're avoiding.
function openPrefilledFromQuery() {
    const params = new URLSearchParams(window.location.search);
    if (params.get('new') !== '1') return;

    const plate = (params.get('plate') || '').trim();
    const driver = (params.get('driver') || '').trim();

    // If it turns out the vehicle already exists (someone else added it, or
    // the user came back after registering), edit it instead of offering a
    // duplicate.
    const existing = allVehicles.find(
        v => (v.plate_number || '').toUpperCase() === plate.toUpperCase()
    );
    if (existing) {
        UI.toast(`${existing.plate_number} is already registered.`, 'info', 5000);
        openModal(existing.plate_number);
    } else {
        openModal(null);
        const plateField = document.getElementById('field-plate');
        const driverField = document.getElementById('field-driver');
        if (plateField) plateField.value = plate;
        if (driverField) driverField.value = driver;
        if (plate) {
            UI.toast(
                `Review and save to register ${plate}. Check the plate format and add the vehicle type and dimensions.`,
                'info', 7000
            );
        }
        (document.getElementById('field-type') || plateField)?.focus();
    }

    // Drop the query string so a refresh doesn't reopen the dialog.
    window.history.replaceState({}, '', window.location.pathname);
}

// ── Vehicles ───────────────────────────────────────────────────
async function loadVehicles() {
    try {
        const data = await ApiClient.fetch('/fleet/vehicles');
        allVehicles = data.data || [];
        filteredVehicles = [...allVehicles];
        renderKPIs();
        renderTable();
        populateDiagramSelect();
    } catch (err) {
        UI.toast(`Failed to load: ${err.message}`, 'error');
    }
}

function renderKPIs() {
    const total = allVehicles.length;
    const types = new Set(allVehicles.filter(v => v.vehicle_type).map(v => v.vehicle_type)).size;
    const drivers = allVehicles.filter(v => v.current_driver).length;
    document.getElementById('kpi-count').textContent = total;
    document.getElementById('kpi-types').textContent = types;
    document.getElementById('kpi-drivers').textContent = drivers;
}

function renderTable() {
    const tbody = document.getElementById('table-body');
    const empty = document.getElementById('empty-state');
    document.getElementById('vehicle-count').textContent = filteredVehicles.length;
    if (!filteredVehicles.length) { tbody.innerHTML = ''; empty.style.display = 'block'; return; }
    empty.style.display = 'none';
    tbody.innerHTML = filteredVehicles.map(v => {
        const checked = selectedIds.has(v.id) ? 'checked' : '';
        return `<tr class="${checked ? 'selected-row' : ''}">
            <td><input type="checkbox" class="vehicle-checkbox" data-id="${v.id}" ${checked} onchange="toggleVehicle(${v.id}, this.checked)"></td>
            <td><span class="plate-badge">${UI.escapeHtml(v.plate_number)}</span></td>
            <td>${v.vehicle_type ? `<span class="type-badge">${UI.escapeHtml(v.vehicle_type)}</span>` : '<span style="color:#94a3b8;">—</span>'}</td>
            <td>${v.current_driver ? UI.escapeHtml(v.current_driver) : '<span style="color:#94a3b8;">—</span>'}</td>
            <td>${v.cargo_length_mm ? `<span class="container-badge">${v.cargo_length_mm}×${v.cargo_width_mm}×${v.cargo_height_mm} mm</span>` : '<span style="color:#94a3b8;">—</span>'}</td>
            <td>${envelopeBadge(v)}</td>
            <td><div style="display:flex;gap:6px;">
                <button class="btn-action btn-edit" onclick="openModal('${UI.escapeHtml(v.plate_number)}')">&#9998; Edit</button>
                <button class="btn-action btn-delete" onclick="deleteVehicle(${v.id}, '${UI.escapeHtml(v.plate_number)}')">&#128465;</button>
            </div></td>
        </tr>`;
    }).join('');
    updateBulkDeleteButton();
}

// Which trucks still have no routing envelope of their own. Phase B's real
// cost is transcribing 36 registration certificates, and a gap nobody can see
// is a gap nobody closes — so the estimate is labelled as an estimate here
// rather than quietly standing in for a measurement.
function envelopeBadge(v) {
    const source = v.envelope_source || 'none';
    if (source === 'vehicle') {
        const dims = [v.overall_length_mm, v.overall_width_mm, v.overall_height_mm];
        const size = dims.every(Boolean) ? `${dims.join('×')} mm` : 'partial';
        const gvw = v.gross_weight_kg ? ` · ${v.gross_weight_kg} kg` : '';
        return `<span class="container-badge">${UI.escapeHtml(size + gvw)}</span>`;
    }
    if (source === 'mixed') {
        return '<span class="type-badge" title="Some values come from the vehicle type estimate">Partly estimated</span>';
    }
    if (source === 'type_default') {
        return '<span class="type-badge" title="No envelope recorded for this vehicle — routing uses an estimate for its type">Estimated</span>';
    }
    return '<span style="color:#f87171;" title="No envelope, and no estimate for this vehicle type">Missing</span>';
}

function filterTable(q) {
    const query = q.trim().toLowerCase();
    filteredVehicles = query
        ? allVehicles.filter(v => v.plate_number.toLowerCase().includes(query) || (v.current_driver || '').toLowerCase().includes(query))
        : [...allVehicles];
    renderTable();
}

function onSideDoorToggle(checked) {
    document.getElementById('side-door-fields').style.display = checked ? 'block' : 'none';
    if (checked) {
        const len = parseFloat(document.getElementById('field-cc-length').value) || 6000;
        const sdw = parseFloat(document.getElementById('field-side-width').value) || 1200;
        document.getElementById('field-side-position').value = Math.round((len - sdw) / 2);
    }
    if (diagram3D.currentVehicleId) selectVehicleForDiagram(diagram3D.currentVehicleId);
}

function buildFeaturesFromForm() {
    const features = [];
    // Rear door (always)
    features.push({
        feature_type: 'rear_door',
        label: 'Rear Door',
        geometry: {
            width_mm: parseFloat(document.getElementById('field-rear-width').value) || 1800,
            height_mm: parseFloat(document.getElementById('field-rear-height').value) || 1900,
        },
    });
    // Side door (if enabled)
    if (document.getElementById('field-side-enabled').checked) {
        const len = parseFloat(document.getElementById('field-cc-length').value) || 6000;
        const sdw = parseFloat(document.getElementById('field-side-width').value) || 1200;
        let pos = parseInt(document.getElementById('field-side-position').value);
        if (!pos && pos !== 0) pos = Math.round((len - sdw) / 2);
        features.push({
            feature_type: 'side_door',
            label: 'Side Door',
            geometry: {
                width_mm: sdw,
                height_mm: parseFloat(document.getElementById('field-side-height').value) || 1800,
                position_from_front_mm: Math.max(0, Math.min(len - sdw, pos)),
            },
        });
    }
    return features;
}

// The vehicle envelope. Blank must round-trip as blank: an empty field means
// "unknown", which falls back to a type estimate, whereas a 0 would be sent to
// the router as a real limit. `|| ''` rather than `|| 0` for exactly that.
const ENVELOPE_FIELD_IDS = {
    overall_length_mm: 'field-env-length',
    overall_width_mm: 'field-env-width',
    overall_height_mm: 'field-env-height',
    gross_weight_kg: 'field-env-gvw',
    axle_load_kg: 'field-env-axle',
};

function populateEnvelopeFields(data) {
    Object.entries(ENVELOPE_FIELD_IDS).forEach(([key, id]) => {
        const el = document.getElementById(id);
        if (el) el.value = data[key] || '';
    });
}

function resetEnvelopeFields() {
    Object.values(ENVELOPE_FIELD_IDS).forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
}

function envelopeFromForm() {
    const out = {};
    Object.entries(ENVELOPE_FIELD_IDS).forEach(([key, id]) => {
        const raw = (document.getElementById(id)?.value || '').trim();
        // null, not 0 — the server keeps the distinction all the way to the
        // ORS request, where an unknown restriction is omitted rather than sent.
        out[key] = raw === '' ? null : parseInt(raw, 10);
    });
    return out;
}

function populateContainerFields(data) {
    document.getElementById('field-cc-length').value = data.cargo_length_mm || '';
    document.getElementById('field-cc-width').value = data.cargo_width_mm || '';
    document.getElementById('field-cc-height').value = data.cargo_height_mm || '';
    document.getElementById('field-cc-payload').value = data.payload_kg || 0;
    const feats = data.features || [];
    const rear = feats.find(f => f.feature_type === 'rear_door');
    const side = feats.find(f => f.feature_type === 'side_door');
    const rg = rear ? (typeof rear.geometry_json === 'string' ? JSON.parse(rear.geometry_json) : rear.geometry_json || rear.geometry || {}) : {};
    const sg = side ? (typeof side.geometry_json === 'string' ? JSON.parse(side.geometry_json) : side.geometry_json || side.geometry || {}) : {};
    document.getElementById('field-rear-width').value = rg.width_mm || 1800;
    document.getElementById('field-rear-height').value = rg.height_mm || 1900;
    const hasSide = !!side;
    document.getElementById('field-side-enabled').checked = hasSide;
    document.getElementById('side-door-fields').style.display = hasSide ? 'block' : 'none';
    document.getElementById('field-side-width').value = sg.width_mm || 1200;
    document.getElementById('field-side-height').value = sg.height_mm || 1800;
    document.getElementById('field-side-position').value = sg.position_from_front_mm || '';
}

function resetContainerFields() {
    document.getElementById('field-cc-length').value = '';
    document.getElementById('field-cc-width').value = '';
    document.getElementById('field-cc-height').value = '';
    document.getElementById('field-cc-payload').value = '';
    document.getElementById('field-rear-width').value = 1800;
    document.getElementById('field-rear-height').value = 1900;
    document.getElementById('field-side-enabled').checked = false;
    document.getElementById('side-door-fields').style.display = 'none';
    document.getElementById('field-side-width').value = 1200;
    document.getElementById('field-side-height').value = 1800;
    document.getElementById('field-side-position').value = '';
}

// ── Diagram preview from modal ─────────────────────────────────
let previewTimer = null;
function scheduleDiagramPreview() {
    if (previewTimer) clearTimeout(previewTimer);
    previewTimer = setTimeout(() => {
        if (editingId && diagram3D.renderer) {
            selectVehicleForDiagram(editingId);
        }
    }, 150);
}

// Attach auto-preview to container fields
function attachPreviewListeners() {
    ['field-cc-length','field-cc-width','field-cc-height','field-cc-payload',
     'field-rear-width','field-rear-height',
     'field-side-width','field-side-height','field-side-position'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('input', scheduleDiagramPreview);
    });
}

// ── Modal ──────────────────────────────────────────────────────
function openModal(plate) {
    editingId = null;
    document.getElementById('modal-title').textContent = plate ? 'Edit Vehicle' : 'Add Vehicle';
    document.getElementById('btn-save').textContent = plate ? 'Update Vehicle' : 'Save Vehicle';
    const plateField = document.getElementById('field-plate');
    const typeField = document.getElementById('field-type');
    const driverField = document.getElementById('field-driver');
    if (plate) {
        const v = allVehicles.find(x => x.plate_number === plate);
        if (v) {
            editingId = v.id;
            plateField.value = v.plate_number;
            typeField.value = v.vehicle_type || '';
            driverField.value = v.current_driver || '';
            // From the vehicle row, not the container-config fetch below —
            // the envelope lives on `vehicles`, and that fetch returns only
            // cargo-compartment data.
            populateEnvelopeFields(v);
            if (v.container_config_id) {
                populateContainerFields(v);
                fetch(`/api/tlp/container-configs/${v.container_config_id}`)
                    .then(r => r.json())
                    .then(data => {
                        populateContainerFields(data);
                        if (diagram3D.renderer) selectVehicleForDiagram(editingId);
                    });
            } else {
                resetContainerFields();
            }
        }
    } else {
        plateField.value = ''; typeField.value = ''; driverField.value = '';
        resetContainerFields();
        resetEnvelopeFields();
    }
    attachPreviewListeners();
    document.getElementById('modal-overlay').classList.add('open');
}

function closeModal() {
    document.getElementById('modal-overlay').classList.remove('open');
}

async function saveVehicle() {
    const plate = document.getElementById('field-plate').value.trim().toUpperCase();
    const vtype = document.getElementById('field-type').value;
    const driver = document.getElementById('field-driver').value.trim();
    if (!plate) { UI.toast('Plate number is required', 'error'); return; }
    const body = {
        plate_number: plate,
        vehicle_type: vtype,
        current_driver: driver,
        cargo_length_mm: parseFloat(document.getElementById('field-cc-length').value) || 0,
        cargo_width_mm: parseFloat(document.getElementById('field-cc-width').value) || 0,
        cargo_height_mm: parseFloat(document.getElementById('field-cc-height').value) || 0,
        payload_kg: parseFloat(document.getElementById('field-cc-payload').value) || 0,
        ...envelopeFromForm(),
        features: buildFeaturesFromForm(),
    };
    try {
        let result;
        if (editingId) {
            result = await ApiClient.fetch(`/fleet/vehicles/${editingId}`, {
                method: 'PUT',
                body: JSON.stringify(body),
            });
        } else {
            result = await ApiClient.fetch('/fleet/vehicles', {
                method: 'POST',
                body: JSON.stringify(body),
            });
        }
        UI.toast(`Vehicle ${editingId ? 'updated' : 'created'}`, 'success');
        // Implausible-but-saved envelope values. Shown after the success toast
        // and left on screen longer, because the point is a second look rather
        // than a blocked save — see app/services/vehicle_specs.py.
        (result?.warnings || []).forEach((w, i) => {
            setTimeout(() => UI.toast(w, 'error', 8000), 400 * (i + 1));
        });
        closeModal();
        await loadVehicles();
    } catch (err) { UI.toast(err.message, 'error'); }
}

async function deleteVehicle(id, plate) {
    if (!confirm(`Delete vehicle ${plate}?`)) return;
    try {
        await ApiClient.fetch(`/fleet/vehicles/${id}`, { method: 'DELETE' });
        selectedIds.delete(id);
        UI.toast(`Vehicle ${plate} deleted`, 'success');
        await loadVehicles();
    } catch (err) { UI.toast(err.message, 'error'); }
}

function toggleVehicle(id, checked) {
    if (checked) selectedIds.add(id);
    else selectedIds.delete(id);
    document.getElementById('select-all').checked = selectedIds.size === filteredVehicles.length;
    const row = document.querySelector(`.vehicle-checkbox[data-id="${id}"]`)?.closest('tr');
    if (row) row.classList.toggle('selected-row', checked);
    updateBulkDeleteButton();
}

function toggleSelectAll(checked) {
    for (const v of filteredVehicles) {
        if (checked) selectedIds.add(v.id);
        else selectedIds.delete(v.id);
    }
    for (const cb of document.querySelectorAll('.vehicle-checkbox')) {
        cb.checked = checked;
        const row = cb.closest('tr');
        if (row) row.classList.toggle('selected-row', checked);
    }
    updateBulkDeleteButton();
}

function updateBulkDeleteButton() {
    const btn = document.getElementById('btn-bulk-delete');
    const count = selectedIds.size;
    if (count > 0) {
        btn.textContent = `Delete Selected (${count})`;
        btn.style.display = 'inline-flex';
    } else {
        btn.style.display = 'none';
    }
}

async function bulkDelete() {
    const count = selectedIds.size;
    if (count === 0) return;
    if (!confirm(`Delete ${count} selected vehicle(s)? This will unlink their fuel log entries.`)) return;
    try {
        const result = await ApiClient.fetch('/fleet/vehicles/bulk-delete', {
            method: 'POST',
            body: JSON.stringify({ ids: [...selectedIds] }),
        });
        selectedIds.clear();
        UI.toast(result.message || `${count} vehicle(s) deleted`, 'success');
        await loadVehicles();
    } catch (err) { UI.toast(err.message, 'error'); }
}

// ── Types ──────────────────────────────────────────────────────
async function loadTypes() {
    try {
        const data = await ApiClient.fetch('/fleet/vehicle-types');
        allTypes = data.data || [];
        renderTypes();
        populateTypeSelect();
    } catch (err) { UI.toast(`Failed to load types: ${err.message}`, 'error'); }
}

function populateTypeSelect() {
    const sel = document.getElementById('field-type');
    sel.innerHTML = '<option value="">— Select type —</option>';
    for (const t of allTypes) { const opt = document.createElement('option'); opt.value = t.name; opt.textContent = t.name; sel.appendChild(opt); }
}

function renderTypes() {
    const tbody = document.getElementById('type-body');
    const empty = document.getElementById('type-empty');
    document.getElementById('type-count').textContent = allTypes.length;
    if (!allTypes.length) { tbody.innerHTML = ''; empty.style.display = 'block'; return; }
    empty.style.display = 'none';
    tbody.innerHTML = allTypes.map(t => `<tr><td>${UI.escapeHtml(t.name)}</td><td><button class="btn-action btn-delete" onclick="deleteVehicleType(${t.id}, '${UI.escapeHtml(t.name)}')">&#128465;</button></td></tr>`).join('');
}

async function addVehicleType() {
    const name = document.getElementById('new-type-input').value.trim();
    if (!name) return;
    try {
        await ApiClient.fetch('/fleet/vehicle-types', { method: 'POST', body: JSON.stringify({ name }) });
        document.getElementById('new-type-input').value = '';
        UI.toast(`Type "${name}" added`, 'success');
        await loadTypes();
    } catch (err) { UI.toast(err.message, 'error'); }
}

async function deleteVehicleType(id, name) {
    if (!confirm(`Delete type "${name}"?`)) return;
    try {
        await ApiClient.fetch(`/fleet/vehicle-types/${id}`, { method: 'DELETE' });
        UI.toast(`Type "${name}" deleted`, 'success');
        await loadTypes();
    } catch (err) { UI.toast(err.message, 'error'); }
}

// ── 3D Container Diagram (Three.js) ─────────────────────────────
const diagram3D = {
    scene: null, camera: null, renderer: null, controls: null,
    animFrame: null, currentVehicleId: null, currentData: null,
    sideDoorMeshes: [], sideDoorOutlines: [], sideDoorGeo: null,
    isDragging: false, dragIntersect: null,
    raycaster: new THREE.Raycaster(), mouse: new THREE.Vector2(),
};

function switchView(view) {
    if (!diagram3D.camera || !diagram3D.controls || !diagram3D.currentVehicleId) return;
    document.querySelectorAll('.view-btn').forEach(b => b.classList.toggle('active', b.dataset.view === view));
    const cc = diagram3D.currentData;
    const L = (cc.cargo_length_mm || 6000) / 1000;
    const W = (cc.cargo_width_mm || 2500) / 1000;
    const H = (cc.cargo_height_mm || 2500) / 1000;
    const targets = {
        free:   { pos: [L*0.9, H*0.7, W*1.3], target: [0, 0, 0] },
        top:    { pos: [0, Math.max(L,W)*0.8, 0.01], target: [0, 0, 0] },
        front:  { pos: [-L*0.9, 0, 0],  target: [0, 0, 0] },
        back:   { pos: [L*0.9, 0, 0],   target: [0, 0, 0] },
        right:  { pos: [0, 0, W*1.2],   target: [0, 0, 0] },
    };
    const t = targets[view] || targets.free;
    diagram3D.controls.target.set(t.target[0], t.target[1], t.target[2]);
    animateCamera(new THREE.Vector3(t.pos[0], t.pos[1], t.pos[2]));
}

function animateCamera(targetPos) {
    const cam = diagram3D.camera; if (!cam) return;
    const start = cam.position.clone();
    const startTime = performance.now();
    const duration = 350;
    function tick(now) {
        const t = Math.min((now - startTime) / duration, 1);
        const ease = 1 - Math.pow(1 - t, 3);
        cam.position.lerpVectors(start, targetPos, ease);
        cam.lookAt(diagram3D.controls ? diagram3D.controls.target : new THREE.Vector3(0,0,0));
        if (diagram3D.controls) diagram3D.controls.update();
        if (t < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
}

function populateDiagramSelect() {
    const sel = document.getElementById('diagram-vehicle-select');
    const cur = sel.value;
    sel.innerHTML = '<option value="">— Select vehicle —</option>';
    for (const v of allVehicles) {
        const opt = document.createElement('option');
        opt.value = v.id;
        const dims = v.cargo_length_mm ? `${v.cargo_length_mm}×${v.cargo_width_mm}×${v.cargo_height_mm}` : 'no container';
        opt.textContent = `${v.plate_number} (${dims})`;
        sel.appendChild(opt);
    }
    sel.value = cur;
    if (cur) selectVehicleForDiagram(cur);
}

function getFeaturesFromForm() {
    return buildFeaturesFromForm();
}

let _diagramReqId = 0;

function selectVehicleForDiagram(vehicleId) {
    const container = document.getElementById('container-diagram');
    const dims = document.getElementById('diagram-dims');
    if (!vehicleId) { container.innerHTML = ''; dims.textContent = ''; diagram3D.currentVehicleId = null; destroy3DScene(); return; }
    const v = allVehicles.find(x => x.id == vehicleId);
    const modalOpen = document.getElementById('modal-overlay').classList.contains('open');
    if (!v && !modalOpen) { dims.textContent = 'Vehicle not found'; destroy3DScene(); return; }
    diagram3D.currentVehicleId = vehicleId;
    const reqId = ++_diagramReqId;
    const useForm = modalOpen;
    Promise.resolve(useForm
        ? {
            cargo_length_mm: parseFloat(document.getElementById('field-cc-length').value) || 6000,
            cargo_width_mm: parseFloat(document.getElementById('field-cc-width').value) || 2500,
            cargo_height_mm: parseFloat(document.getElementById('field-cc-height').value) || 2500,
            payload_kg: parseFloat(document.getElementById('field-cc-payload').value) || 0,
            features: buildFeaturesFromForm(),
          }
        : (v && v.container_config_id
            ? fetch(`/api/tlp/container-configs/${v.container_config_id}`).then(r => r.json())
            : Promise.reject('No container configured'))
    ).then(cc => {
        if (reqId !== _diagramReqId) return;
        const len = cc.cargo_length_mm;
        const wid = cc.cargo_width_mm;
        const hei = cc.cargo_height_mm;
        dims.textContent = `${len} × ${wid} × ${hei} mm · ${(len*wid*hei/1e9).toFixed(2)} m³ · ${cc.payload_kg} kg payload`;
        diagram3D.currentData = cc;
        destroy3DScene();
        init3DScene(container, cc);
    }).catch(e => {
        if (e === 'No container configured') {
            dims.textContent = 'No container configured';
        } else {
            console.error('Failed to load container config:', e);
            dims.textContent = 'Error loading container';
        }
        destroy3DScene();
    });
}

// ── Three.js 3D Scene ──────────────────────────────────────────
function destroy3DScene() {
    if (diagram3D.animFrame) { cancelAnimationFrame(diagram3D.animFrame); diagram3D.animFrame = null; }
    if (diagram3D.renderer) {
        const el = diagram3D.renderer.domElement;
        if (el.parentNode) el.parentNode.removeChild(el);
        diagram3D.renderer.dispose();
        diagram3D.renderer = null;
    }
    diagram3D.scene = null;
    diagram3D.camera = null;
    diagram3D.controls = null;
    diagram3D.sideDoorMeshes = [];
    diagram3D.sideDoorOutlines = [];
    diagram3D.sideDoorGeo = null;
}

function init3DScene(containerEl, cc) {
    const L = (cc.cargo_length_mm || 6000) / 1000;
    const W = (cc.cargo_width_mm || 2500) / 1000;
    const H = (cc.cargo_height_mm || 2500) / 1000;
    const w = containerEl.clientWidth || 700;
    const h = containerEl.clientHeight || 460;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0d1117);
    const cam = new THREE.PerspectiveCamera(40, w / h, 0.1, 100);
    cam.position.set(L*0.9, H*0.7, W*1.3);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(w, h);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    containerEl.appendChild(renderer.domElement);

    const controls = new THREE.OrbitControls(cam, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.12;
    controls.minDistance = 1;
    controls.maxDistance = 40;
    controls.target.set(0, 0, 0);

    // Lights
    scene.add(new THREE.AmbientLight(0x404060, 0.7));
    const dl = new THREE.DirectionalLight(0xffffff, 1.2);
    dl.position.set(L, H*1.5, W); scene.add(dl);
    const dl2 = new THREE.DirectionalLight(0x8888ff, 0.4);
    dl2.position.set(-L, -H*0.5, -W); scene.add(dl2);

    // Floor grid
    const gridSize = Math.max(L, W) * 1.4;
    const grid = new THREE.GridHelper(gridSize, 12, 0x2f8ceb, 0x1a2332);
    grid.position.y = -H/2; scene.add(grid);

    // Container box
    const boxMat = new THREE.MeshStandardMaterial({
        color: 0x1a2744, transparent: true, opacity: 0.15,
        roughness: 0.4, metalness: 0.1, side: THREE.DoubleSide, depthWrite: false,
    });
    const boxGeo = new THREE.BoxGeometry(L, H, W);
    const boxMesh = new THREE.Mesh(boxGeo, boxMat);
    boxMesh.position.set(0, 0, 0); scene.add(boxMesh);

    // Edges
    const edgeMat = new THREE.LineBasicMaterial({ color: 0x2f8ceb, transparent: true, opacity: 0.4 });
    const edgeGeo = new THREE.EdgesGeometry(boxGeo);
    const edgeLine = new THREE.LineSegments(edgeGeo, edgeMat);
    edgeLine.position.copy(boxMesh.position); scene.add(edgeLine);

    // Floor plane (matching TLP style)
    const floorGeo = new THREE.PlaneGeometry(L, W);
    const floorMat = new THREE.MeshBasicMaterial({
        color: 0x1a2332, side: THREE.DoubleSide, transparent: true, opacity: 0.3,
    });
    const floorMesh = new THREE.Mesh(floorGeo, floorMat);
    floorMesh.rotation.x = -Math.PI / 2;
    floorMesh.position.set(0, -H / 2 + 0.01, 0);
    scene.add(floorMesh);

    // Corner labels (front/rear markers)
    function makeLabel(text, x, y, z, color) {
        const canvas = document.createElement('canvas');
        canvas.width = 128; canvas.height = 48;
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = 'transparent'; ctx.fillRect(0,0,128,48);
        ctx.font = 'bold 22px Inter, sans-serif';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillStyle = color; ctx.fillText(text, 64, 24);
        const tex = new THREE.CanvasTexture(canvas);
        tex.needsUpdate = true;
        const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false });
        const sprite = new THREE.Sprite(mat);
        sprite.position.set(x, y, z);
        sprite.scale.set(0.6, 0.22, 1);
        scene.add(sprite);
    }
    makeLabel('FRONT', -L/2-0.15, -H/2+0.05, 0, '#7c8fa3');
    makeLabel('REAR', L/2+0.15, -H/2+0.05, 0, '#7c8fa3');

    // Dimension labels (sprite)
    function dimLabel(text, x, y, z) {
        const c = document.createElement('canvas');
        c.width = 200; c.height = 40;
        const ctx = c.getContext('2d');
        ctx.font = '16px Inter, sans-serif';
        ctx.textAlign = 'center'; ctx.fillStyle = '#7c8fa3';
        ctx.fillText(text, 100, 26);
        const tex = new THREE.CanvasTexture(c); tex.needsUpdate = true;
        const m = new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false });
        const s = new THREE.Sprite(m);
        s.position.set(x, y, z); s.scale.set(1.2, 0.24, 1);
        scene.add(s);
    }
    dimLabel(`${(L*1000).toFixed(0)} mm`, 0, -H/2-0.4, -W/2-0.1);
    dimLabel(`${(W*1000).toFixed(0)} mm`, L/2+0.6, -H/2-0.4, 0);
    dimLabel(`${(H*1000).toFixed(0)} mm`, -L/2-0.6, 0, -W/2-0.1);

    // Features
    const features = cc.features || [];
    const sideMat = new THREE.MeshStandardMaterial({
        color: 0x10b981, transparent: true, opacity: 0.35, side: THREE.DoubleSide, depthWrite: false,
    });
    const rearMat = new THREE.MeshStandardMaterial({
        color: 0x2f8ceb, transparent: true, opacity: 0.35, side: THREE.DoubleSide, depthWrite: false,
    });

    features.forEach(f => {
        const geo = (typeof f.geometry_json === 'object' ? f.geometry_json : (typeof f.geometry_json === 'string' ? JSON.parse(f.geometry_json) : (f.geometry || {})));
        if (f.feature_type === 'rear_door') {
            const dw = (geo.width_mm || 1800) / 1000;
            const dh = (geo.height_mm || 1900) / 1000;
            const plane = new THREE.Mesh(new THREE.PlaneGeometry(dw, dh), rearMat);
            plane.position.set(L/2+0.01, dh/2 - H/2, 0);
            plane.rotation.y = Math.PI / 2;
            scene.add(plane);
            const outline = new THREE.LineSegments(
                new THREE.EdgesGeometry(new THREE.PlaneGeometry(dw, dh)),
                new THREE.LineBasicMaterial({ color: 0x2f8ceb, transparent: true, opacity: 0.6 })
            );
            outline.position.copy(plane.position);
            outline.rotation.copy(plane.rotation);
            scene.add(outline);
        }
        if (f.feature_type === 'side_door') {
            const dw = (geo.width_mm || 1200) / 1000;
            const dh = (geo.height_mm || 1800) / 1000;
            const pos = (geo.position_from_front_mm || 0) / 1000;
            const doorX = -L/2 + pos + dw/2;
            const doorY = dh/2 - H/2;
            diagram3D.sideDoorGeo = { dw, dh, L, W };
            function makeSideDoor(zPos, labelOffsetZ) {
                const doorGeo = new THREE.BoxGeometry(dw, dh, 0.04);
                const doorMesh = new THREE.Mesh(doorGeo, sideMat);
                doorMesh.position.set(doorX, doorY, zPos);
                scene.add(doorMesh);
                diagram3D.sideDoorMeshes.push(doorMesh);
                const out2 = new THREE.LineSegments(
                    new THREE.EdgesGeometry(new THREE.PlaneGeometry(dw, dh)),
                    new THREE.LineBasicMaterial({ color: 0x10b981, transparent: true, opacity: 0.6 })
                );
                out2.position.set(doorX, doorY, zPos + (zPos > 0 ? 0.01 : -0.01));
                scene.add(out2);
                diagram3D.sideDoorOutlines.push(out2);
                const lc = document.createElement('canvas');
                lc.width = 120; lc.height = 36;
                const lcx = lc.getContext('2d');
                lcx.font = 'bold 14px Inter, sans-serif'; lcx.textAlign = 'center';
                lcx.fillStyle = '#34d399'; lcx.fillText('SIDE DOOR', 60, 22);
                const lt = new THREE.CanvasTexture(lc); lt.needsUpdate = true;
                const lm = new THREE.SpriteMaterial({ map: lt, transparent: true, depthTest: false });
                const ls = new THREE.Sprite(lm);
                ls.position.set(doorX + dw/2 + labelOffsetZ, doorY + 0.2, zPos);
                ls.scale.set(1.2, 0.36, 1);
                scene.add(ls);
            }
            makeSideDoor(W/2, 0.6);
            makeSideDoor(-W/2, -0.6);
        }
    });

    diagram3D.scene = scene;
    diagram3D.camera = cam;
    diagram3D.renderer = renderer;
    diagram3D.controls = controls;

    // Pointer events for side door drag
    const canvas = renderer.domElement;
    canvas.addEventListener('pointerdown', on3DPointerDown);
    canvas.addEventListener('pointermove', on3DPointerMove);
    canvas.addEventListener('pointerup', on3DPointerUp);

    animate3D();
}

function animate3D() {
    diagram3D.animFrame = requestAnimationFrame(animate3D);
    if (diagram3D.controls) diagram3D.controls.update();
    if (diagram3D.renderer && diagram3D.scene && diagram3D.camera) {
        diagram3D.renderer.render(diagram3D.scene, diagram3D.camera);
    }
}

// ── Side Door Drag ─────────────────────────────────────────────
function on3DPointerDown(e) {
    if (!diagram3D.sideDoorMeshes.length) return;
    const rect = diagram3D.renderer.domElement.getBoundingClientRect();
    diagram3D.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    diagram3D.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    diagram3D.raycaster.setFromCamera(diagram3D.mouse, diagram3D.camera);
    for (const mesh of diagram3D.sideDoorMeshes) {
        const hits = diagram3D.raycaster.intersectObject(mesh, true);
        if (hits.length > 0) {
            diagram3D.isDragging = true;
            diagram3D.controls.enabled = false;
            diagram3D.dragIntersect = hits[0].point.clone();
            diagram3D.renderer.domElement.style.cursor = 'grabbing';
            break;
        }
    }
}

function on3DPointerMove(e) {
    if (!diagram3D.isDragging || !diagram3D.sideDoorMeshes.length) return;
    const rect = diagram3D.renderer.domElement.getBoundingClientRect();
    diagram3D.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    diagram3D.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    diagram3D.raycaster.setFromCamera(diagram3D.mouse, diagram3D.camera);

    const cc = diagram3D.currentData;
    const L = (cc.cargo_length_mm || 6000) / 1000;
    const dw = diagram3D.sideDoorGeo.dw;
    const doorY = diagram3D.sideDoorGeo.dh / 2 - (cc.cargo_height_mm || 2500) / 2000;
    // Use a horizontal plane at mid-door height so we get X regardless of which face is clicked
    const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -doorY);
    const intersect = new THREE.Vector3();
    const ray = diagram3D.raycaster.ray;
    if (ray.intersectPlane(plane, intersect)) {
        const minX = -L/2;
        const maxX = L/2 - dw;
        const newX = Math.max(minX, Math.min(maxX, intersect.x));
        const dx = newX - diagram3D.sideDoorMeshes[0].position.x;
        for (const mesh of diagram3D.sideDoorMeshes) {
            mesh.position.x = newX;
        }
        for (const out of diagram3D.sideDoorOutlines) {
            out.position.x += dx;
        }
        // Update input field — distance from front face (-L/2)
        const posMm = Math.max(0, Math.min(Math.round((newX - (-L/2)) * 1000), (cc.cargo_length_mm || 6000)));
        document.getElementById('field-side-position').value = posMm;
        // Update feature geometry in currentData
        const feats = cc.features || [];
        for (const f of feats) {
            if (f.feature_type === 'side_door') {
                const g = typeof f.geometry_json === 'object' ? f.geometry_json : {};
                g.position_from_front_mm = posMm;
                if (typeof f.geometry_json === 'string') f.geometry_json = g;
                break;
            }
        }
    }
}

function on3DPointerUp() {
    if (diagram3D.isDragging) {
        diagram3D.isDragging = false;
        diagram3D.controls.enabled = true;
        diagram3D.renderer.domElement.style.cursor = 'default';
        // Auto-save side door position if we have a container config ID
        const ccId = diagram3D.currentData && diagram3D.currentData.id;
        if (ccId) {
            const feats = diagram3D.currentData.features || [];
            const features = feats.map(f => {
                const geo = typeof f.geometry_json === 'object' ? f.geometry_json
                    : (typeof f.geometry_json === 'string' ? JSON.parse(f.geometry_json) : f.geometry || {});
                return { feature_type: f.feature_type, label: f.label || '', geometry: geo };
            });
            fetch(`/api/tlp/container-configs/${ccId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ features }),
            }).catch(e => console.error('Failed to save side door position:', e));
        }
    }
}
