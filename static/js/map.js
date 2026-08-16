const MAP_CENTER = [10.8231, 106.6297];
const POLLING_INTERVAL_MS = 15000;
const DEFAULT_RADIUS_KM = 3;
const MIN_ZOOM_FOR_LABELS = 15; // Minimum zoom level to show location labels
let KNOWN_LOCATIONS = {};
let allLocationPolygons = []; // All polygons for saved locations
let allLocationLabels = []; // All location name labels

const STATUS_LABELS = {
    running: "Moving (Running)",
    stopped_engine_on: "Stopped (Engine On)",
    stopped_engine_off: "Stopped (Engine Off)",
    unknown: "No Signal (Unknown)"
};

const STATUS_COLORS = {
    running: "#10b981",
    stopped_engine_on: "#f59e0b",
    stopped_engine_off: "#ef4444",
    unknown: "#6b7280"
};

const state = {
    markers: new Map(),
    vehicleTypes: new Set(),
    activeTypes: new Set(),
    activeStatuses: new Set(Object.keys(STATUS_LABELS)),
    selectedLocation: "all", // either "all", known location name, or "__custom__"
    customLocation: null, // { lat, lng, name, radius_km }
    radiusKm: 3,
    proximityCircle: null,
    lastVehicles: [],
    routePolylines: {},
    destinationMarkers: {},
    routeData: {},
    selectedVehicleId: null,
    vehicleSearchTerm: "",
    hasRouteFilter: false,
    locationPinMode: false, // for pinning custom location
    customLocationMarker: null,
    hasInitialFocused: false // tracks whether the focusVehicle query-param focus has already fired
};

function updateSourceStatus(sourceInfo = {}) {
    const element = document.getElementById("source-status");
    if (!element) return;
    element.innerHTML = "";
    const li = document.createElement("li");
    const indicator = document.createElement("div");
    indicator.className = "source-indicator online";
    const text = document.createElement("span");
    if (sourceInfo.source === "live") {
        text.textContent = "Live data from TTAS. Refreshes every 15s.";
    } else if (sourceInfo.source === "sample") {
        text.textContent = "Showing saved sample data.";
    } else {
        text.textContent = "Markers refresh every 15 seconds.";
    }
    li.appendChild(indicator);
    li.appendChild(text);
    element.appendChild(li);
}

const map = L.map("map").setView(MAP_CENTER, 11);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors"
}).addTo(map);

map.on('click', (e) => {
    if (state.locationPinMode) {
        const { lat, lng } = e.latlng;
        state.selectedLocation = "__custom__";
        state.customLocation = {
            lat: lat,
            lng: lng,
            name: `Pinned Location (${lat.toFixed(4)}, ${lng.toFixed(4)})`,
            radius_km: state.radiusKm
        };
        
        const locationSearch = document.getElementById("location-search");
        if (locationSearch) {
            locationSearch.value = state.customLocation.name;
        }
        
        state.locationPinMode = false;
        const pinBtn = document.getElementById("location-pin-btn");
        if (pinBtn) {
            pinBtn.classList.remove("active");
            pinBtn.textContent = "Pin on Map";
        }
        map.getContainer().style.cursor = "";
        
        if (state.customLocationMarker) {
            state.customLocationMarker.setLatLng([lat, lng]);
            state.customLocationMarker.setPopupContent(`<strong>Custom Location:</strong><br>${UI.escapeHtml(state.customLocation.name)}`);
        } else {
            state.customLocationMarker = L.marker([lat, lng]).addTo(map);
            state.customLocationMarker.bindPopup(`<strong>Custom Location:</strong><br>${UI.escapeHtml(state.customLocation.name)}`);
        }
        state.customLocationMarker.openPopup();
        
        updateProximityCircle();
        applyFilters();
    } else {
        hideCurrentRoute();
    }
});
map.on('zoomend', updateLabelsVisibility);

function renderAllLocations() {
    // Clear existing polygons and labels
    allLocationPolygons.forEach(p => map.removeLayer(p));
    allLocationLabels.forEach(l => map.removeLayer(l));
    allLocationPolygons = [];
    allLocationLabels = [];

    Object.keys(KNOWN_LOCATIONS).forEach(name => {
        const loc = KNOWN_LOCATIONS[name];
        let polygonsToAdd = [];
        if (loc.polygons && Array.isArray(loc.polygons)) {
            polygonsToAdd = loc.polygons;
        } else if (loc.corners) {
            polygonsToAdd = [loc.corners];
        }

        // Add all polygons
        polygonsToAdd.forEach(polygon => {
            const poly = L.polygon(polygon, {
                color: "#2563eb",
                weight: 3,
                opacity: 0.7,
                fillOpacity: 0.15
            }).addTo(map);
            allLocationPolygons.push(poly);
        });

        // Add location name label at centroid
        const centroid = getLocationCentroid(loc);
        if (centroid) {
            const label = L.marker([centroid.lat, centroid.lng], {
                icon: L.divIcon({
                    className: 'location-name-label',
                    html: `<div style="
                        background: white;
                        padding: 6px 12px;
                        border-radius: 4px;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
                        font-weight: 600;
                        font-size: 14px;
                        color: #111827;
                        white-space: nowrap;
                    ">${UI.escapeHtml(name)}</div>`,
                    iconSize: [null, null],
                    iconAnchor: [0, 0]
                })
            });
            if (map.getZoom() >= MIN_ZOOM_FOR_LABELS) {
                label.addTo(map);
            }
            allLocationLabels.push(label);
        }
    });
    updateLabelsVisibility();
}

function updateLabelsVisibility() {
    const currentZoom = map.getZoom();
    allLocationLabels.forEach(label => {
        if (currentZoom >= MIN_ZOOM_FOR_LABELS) {
            if (!map.hasLayer(label)) {
                label.addTo(map);
            }
        } else {
            if (map.hasLayer(label)) {
                map.removeLayer(label);
            }
        }
    });
}

function createIcon(vehicle) {
    const label = vehicle.device_name || vehicle.id || vehicle.vehicle_type || "V";
    const bgColor = STATUS_COLORS[vehicle.vehicle_status] || STATUS_COLORS.unknown;
    return L.divIcon({
        html: `<div class="vehicle-icon" style="background-color: ${bgColor}; padding: 4px 8px; border-radius: 4px; white-space: nowrap; font-size: 11px; font-weight: bold; color: white; text-shadow: 1px 1px 2px rgba(0,0,0,0.5);">${UI.escapeHtml(label)}</div>`,
        className: "",
        iconSize: [80, 24],
        iconAnchor: [40, 12]
    });
}

function getActiveTripForVehicle(vehicleId) {
    for (const key in state.routeData) {
        const trip = state.routeData[key];
        if (trip.vehicle_id === vehicleId && trip.status === 'active') {
            return trip;
        }
    }
    return null;
}

function getAnyTripForVehicle(vehicleId) {
    for (const key in state.routeData) {
        const trip = state.routeData[key];
        if (trip.vehicle_id === vehicleId) {
            return trip;
        }
    }
    return null;
}

async function forceAdvanceTrip(vehicleId) {
    const trip = getActiveTripForVehicle(vehicleId);
    if (!trip) return;
    try {
        const res = await fetch('/api/advance-trip', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ trip_id: trip.trip_id, action: 'advance' })
        });
        const data = await res.json();
        if (data.success) {
            UI.toast(data.message || 'Trip advanced', 'success');
            fetchVehicles();
        } else {
            UI.toast(data.message || 'Failed to advance trip', 'error');
        }
    } catch (err) {
        UI.toast('Error advancing trip', 'error');
    }
}

async function forceCompleteTrip(vehicleId) {
    const trip = getActiveTripForVehicle(vehicleId);
    if (!trip) return;
    if (!confirm(`Force complete trip for ${UI.escapeHtml(trip.vehicle_name)}?`)) return;
    try {
        const res = await fetch('/api/advance-trip', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ trip_id: trip.trip_id, action: 'complete' })
        });
        const data = await res.json();
        if (data.success) {
            UI.toast(data.message || 'Trip completed', 'success');
            fetchVehicles();
        } else {
            UI.toast(data.message || 'Failed to complete trip', 'error');
        }
    } catch (err) {
        UI.toast('Error completing trip', 'error');
    }
}

async function cancelTripFromMap(vehicleId) {
    const trip = getActiveTripForVehicle(vehicleId) || getAnyTripForVehicle(vehicleId);
    if (!trip) return;
    const reason = prompt('Cancel reason (optional):', 'Manual cancellation');
    if (reason === null) return;
    try {
        const res = await fetch('/api/cancel-trip', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ trip_id: trip.trip_id, reason: reason || 'Manual cancellation' })
        });
        const data = await res.json();
        if (data.success) {
            UI.toast('Trip canceled', 'success');
            fetchVehicles();
        } else {
            UI.toast(data.message || 'Failed to cancel trip', 'error');
        }
    } catch (err) {
        UI.toast('Error canceling trip', 'error');
    }
}

function buildPopup(vehicle) {
    const trip = getActiveTripForVehicle(vehicle.id);
    let etaText = "Not set";
    let distanceText = "Not set";
    let customerText = "N/A";
    let pickupText = "N/A";
    let destinationText = "N/A";
    let phaseText = "N/A";
    let driverText = UI.escapeHtml(vehicle.driver_name);
    let durationText = "";
    let tripStatus = "";
    
    // Check for any trip (active or queued)
    let anyTrip = null;
    for (const key in state.routeData) {
        const t = state.routeData[key];
        if (t.vehicle_id === vehicle.id) {
            anyTrip = t;
            break;
        }
    }
    
    if (trip) {
        if (trip.distance_remaining_km !== null && trip.distance_remaining_km !== undefined) {
            distanceText = `${trip.distance_remaining_km.toFixed(2)} km`;
        }
        if (trip.eta_seconds !== null && trip.eta_seconds !== undefined && !isNaN(trip.eta_seconds)) {
            const etaDate = new Date(Date.now() + (trip.eta_seconds * 1000));
            const hours = String(etaDate.getHours()).padStart(2, '0');
            const minutes = String(etaDate.getMinutes()).padStart(2, '0');
            etaText = `${hours}:${minutes}`;
        }
        customerText = trip.customer_name || "N/A";
        pickupText = trip.pickup_name || "N/A";
        destinationText = trip.destination_name || "N/A";
        driverText = trip.driver_name || UI.escapeHtml(vehicle.driver_name);
        tripStatus = trip.status || "";
        
        // Duration display
        if (trip.created_at && trip.status === 'active') {
            const created = new Date(trip.created_at + 'Z');
            const elapsed = Math.floor((Date.now() - created.getTime()) / 1000);
            if (elapsed > 0) {
                const mins = Math.floor(elapsed / 60);
                const hrs = Math.floor(mins / 60);
                if (hrs > 0) durationText = `${hrs}h ${mins % 60}m`;
                else durationText = `${mins}m`;
            }
        }
        
        const p = Number(trip.phase);
        const wp = trip.waypoints || [];
        
        if (trip.status === 'active') {
            if (p === 1 && trip.pickup_name) {
                phaseText = "Phase 1: To Pickup";
            } else if (trip.pickup_name && !trip.pickup_name.startsWith('Custom')) {
                // Phase 2+ - determine target from waypoints
                let phaseIdx = p - 1;
                if (trip.pickup_name) phaseIdx -= 1; // phase 1 = pickup
                if (phaseIdx >= 0 && phaseIdx < wp.length) {
                    phaseText = `Phase ${p}: To ${wp[phaseIdx].name}`;
                } else {
                    phaseText = `Phase ${p}: To Destination`;
                }
            } else {
                phaseText = `Phase ${p}: To ${trip.destination_name || 'Destination'}`;
            }
        } else if (trip.status === 'queued') {
            phaseText = `Queued (#${trip.queue_order || 0})`;
        } else if (trip.status === 'completed') {
            phaseText = 'Completed';
        }
    } else if (anyTrip) {
        customerText = anyTrip.customer_name || "N/A";
        pickupText = anyTrip.pickup_name || "N/A";
        destinationText = anyTrip.destination_name || "N/A";
        driverText = anyTrip.driver_name || UI.escapeHtml(vehicle.driver_name);
        tripStatus = anyTrip.status || "";
        if (anyTrip.status === 'queued') {
            phaseText = `Queued (#${anyTrip.queue_order || 0})`;
        }
    }
    
    const statusLabel = vehicle.vehicle_status === "running" ? "Moving" :
        vehicle.vehicle_status === "stopped_engine_on" ? "Stopped (Engine On)" :
            vehicle.vehicle_status === "stopped_engine_off" ? "Stopped (Engine Off)" : "Unknown";

    const canAdvance = trip && trip.status === 'active';
    const actionButtons = canAdvance ? `
        <div style="display:flex; gap:6px; margin-top:8px;">
            <button onclick="event.stopPropagation(); forceAdvanceTrip('${vehicle.id}')" style="flex:1; padding:6px 10px; background:#f59e0b; color:white; border:none; border-radius:4px; cursor:pointer; font-size:12px; font-weight:600;">Advance</button>
            <button onclick="event.stopPropagation(); forceCompleteTrip('${vehicle.id}')" style="flex:1; padding:6px 10px; background:#10b981; color:white; border:none; border-radius:4px; cursor:pointer; font-size:12px; font-weight:600;">Complete</button>
            <button onclick="event.stopPropagation(); cancelTripFromMap('${vehicle.id}')" style="flex:1; padding:6px 10px; background:#ef4444; color:white; border:none; border-radius:4px; cursor:pointer; font-size:12px; font-weight:600;">Cancel</button>
        </div>
    ` : '';

    return `
        <div style="min-width: 240px;">
            <strong>${UI.escapeHtml(vehicle.device_name)}</strong><br />
            <small>${UI.escapeHtml(vehicle.car_type || vehicle.vehicle_type || "Unknown")}</small>
            <hr style="margin:8px 0; border:none; height:1px; background:#ddd;" />
            <div><strong>Driver:</strong> ${driverText}</div>
            <div><strong>Speed:</strong> ${UI.escapeHtml(vehicle.speed_status)}</div>
            <div><strong>Status:</strong> ${UI.escapeHtml(statusLabel)}</div>
            <div><strong>Customer:</strong> ${UI.escapeHtml(customerText)}</div>
            <div><strong>Pickup:</strong> ${UI.escapeHtml(pickupText)}</div>
            <div><strong>Destination:</strong> ${UI.escapeHtml(destinationText)}</div>
            <div><strong>Phase:</strong> ${UI.escapeHtml(phaseText)}</div>
            <div><strong>Distance:</strong> ${UI.escapeHtml(distanceText)}</div>
            <div><strong>ETA:</strong> ${UI.escapeHtml(etaText)}</div>
            ${durationText ? `<div><strong>Trip Time:</strong> ${UI.escapeHtml(durationText)}</div>` : ''}
            <div><strong>Updated:</strong> ${UI.escapeHtml(vehicle.last_update)}</div>
            <div><strong>Location:</strong> ${UI.escapeHtml(vehicle.position)}</div>
            ${actionButtons}
        </div>
    `;
}

function countVehiclesInLocation(location) {
    let count = 0;
    const vehicles = state.lastVehicles || [];
    for (const vehicle of vehicles) {
        if (!vehicle.latitude || !vehicle.longitude) continue;
        let inArea = false;
        if (location.polygons && Array.isArray(location.polygons)) {
            for (const polygon of location.polygons) {
                if (isPointInPolygon(vehicle.latitude, vehicle.longitude, polygon)) {
                    inArea = true;
                    break;
                }
            }
        } else if (location.corners) {
            inArea = isPointInPolygon(vehicle.latitude, vehicle.longitude, location.corners);
        } else if (location.latitude !== undefined && location.longitude !== undefined) {
            const distance = getDistanceMeters(
                location.latitude,
                location.longitude,
                vehicle.latitude,
                vehicle.longitude
            );
            const locRadius = location.radius_km !== undefined ? location.radius_km * 1000 : DEFAULT_RADIUS_KM * 1000;
            inArea = distance <= locRadius;
        }
        if (inArea) count++;
    }
    return count;
}

function focusOnLocation(locationName) {
    const location = KNOWN_LOCATIONS[locationName];
    if (!location) return;
    let allBounds = [];
    
    if (location.polygons && Array.isArray(location.polygons)) {
        location.polygons.forEach(polygon => {
            allBounds.push(L.latLngBounds(polygon));
        });
    } else if (location.corners && location.corners.length >= 3) {
        allBounds.push(L.latLngBounds(location.corners));
    }
    
    if (allBounds.length > 0) {
        let combinedBounds = allBounds[0];
        for (let i = 1; i < allBounds.length; i++) {
            combinedBounds.extend(allBounds[i]);
        }
        map.fitBounds(combinedBounds, { padding: [20, 20] });
    } else if (location.latitude !== undefined && location.longitude !== undefined) {
        map.setView([location.latitude, location.longitude], 13);
    }
}

function focusOnVehicle(vehicle) {
    if (!vehicle) return;
    map.setView([vehicle.latitude, vehicle.longitude], 15);
    const marker = state.markers.get(vehicle.id);
    if (marker) marker.openPopup();
}

function updateProximityCircle() {
    if (state.proximityCircleGroup) {
        state.proximityCircleGroup.clearLayers();
        map.removeLayer(state.proximityCircleGroup);
        state.proximityCircleGroup = null;
    }
    if (state.proximityCircle) {
        map.removeLayer(state.proximityCircle);
        state.proximityCircle = null;
    }
    
    if (state.selectedLocation === "all") return;
    
    if (state.selectedLocation === "__custom__") {
        if (state.customLocation && state.customLocation.lat !== undefined && state.customLocation.lng !== undefined) {
            const radius = (state.customLocation.radius_km || state.radiusKm || DEFAULT_RADIUS_KM) * 1000;
            state.proximityCircle = L.circle([state.customLocation.lat, state.customLocation.lng], {
                radius: radius,
                color: "#2f8ceb",
                weight: 2,
                opacity: 0.65,
                fillOpacity: 0.1
            }).addTo(map);
        }
        return;
    }
    
    const location = KNOWN_LOCATIONS[state.selectedLocation];
    if (!location) return;
    
    if (location.polygons && Array.isArray(location.polygons)) {
        state.proximityCircleGroup = L.layerGroup().addTo(map);
        location.polygons.forEach(polygon => {
            const layer = L.polygon(polygon, {
                color: "#2f8ceb",
                weight: 2,
                opacity: 0.65,
                fillOpacity: 0.1
            });
            state.proximityCircleGroup.addLayer(layer);
        });
    } else if (location.corners && location.corners.length >= 3) {
        state.proximityCircle = L.polygon(location.corners, {
            color: "#2f8ceb",
            weight: 2,
            opacity: 0.65,
            fillOpacity: 0.1
        }).addTo(map);
    } else if (location.latitude !== undefined && location.longitude !== undefined) {
        const radius = (location.radius_km || DEFAULT_RADIUS_KM) * 1000;
        state.proximityCircle = L.circle([location.latitude, location.longitude], {
            radius: radius,
            color: "#2f8ceb",
            weight: 2,
            opacity: 0.65,
            fillOpacity: 0.1
        }).addTo(map);
    }
}

function shouldShowMarker(vehicle) {
    if (state.vehicleSearchTerm) {
        const search = state.vehicleSearchTerm.toLowerCase();
        const plate = (vehicle.device_name || "").toLowerCase();
        const id = (vehicle.id || "").toLowerCase();
        if (!plate.includes(search) && !id.includes(search)) return false;
    }
    if (state.activeTypes.size > 0 && !state.activeTypes.has(vehicle.car_type) && !state.activeTypes.has(vehicle.vehicle_type)) return false;
    const vehicleStatus = vehicle.vehicle_status || "unknown";
    if (state.activeStatuses.size > 0 && !state.activeStatuses.has(vehicleStatus)) return false;
    if (state.hasRouteFilter && !getActiveTripForVehicle(vehicle.id)) return false;
    if (state.selectedLocation === "all") return true;
    
    if (state.selectedLocation === "__custom__") {
        if (!state.customLocation || state.customLocation.lat === undefined || state.customLocation.lng === undefined) {
            return true;
        }
        const distance = getDistanceMeters(state.customLocation.lat, state.customLocation.lng, vehicle.latitude, vehicle.longitude);
        const locRadius = (state.customLocation.radius_km || state.radiusKm || DEFAULT_RADIUS_KM) * 1000;
        return distance <= locRadius;
    }
    
    const location = KNOWN_LOCATIONS[state.selectedLocation];
    if (!location) return true;
    if (location.polygons && Array.isArray(location.polygons)) {
        for (const polygon of location.polygons) {
            if (isPointInPolygon(vehicle.latitude, vehicle.longitude, polygon)) {
                return true;
            }
        }
        return false;
    } else if (location.corners) {
        return isPointInPolygon(vehicle.latitude, vehicle.longitude, location.corners);
    } else if (location.latitude !== undefined && location.longitude !== undefined) {
        const distance = getDistanceMeters(location.latitude, location.longitude, vehicle.latitude, vehicle.longitude);
        const locRadius = location.radius_km !== undefined ? location.radius_km * 1000 : DEFAULT_RADIUS_KM * 1000;
        return distance <= locRadius;
    }
    return true;
}

function getMarkersFromVehicles(vehicles) {
    const newIds = new Set();
    const previousIds = new Set(state.markers.keys());
    vehicles.forEach((vehicle) => {
        const existing = state.markers.get(vehicle.id);
        newIds.add(vehicle.id);
        if (existing) {
            const oldVehicle = existing.vehicle;
            let needsUpdate = false;
            if (!oldVehicle || oldVehicle.latitude !== vehicle.latitude || oldVehicle.longitude !== vehicle.longitude) {
                existing.setLatLng([vehicle.latitude, vehicle.longitude]);
                needsUpdate = true;
            }
            if (!oldVehicle || oldVehicle.device_name !== vehicle.device_name || oldVehicle.vehicle_status !== vehicle.vehicle_status) {
                existing.setIcon(createIcon(vehicle));
                existing.setPopupContent(buildPopup(vehicle));
                needsUpdate = true;
            }
            existing.vehicle = vehicle;
        } else {
            const marker = L.marker([vehicle.latitude, vehicle.longitude], {
                icon: createIcon(vehicle),
                title: vehicle.device_name || vehicle.driver_name
            });
            marker.bindPopup(buildPopup(vehicle));
            marker.vehicle = vehicle;
            marker.on('click', (e) => {
                L.DomEvent.stopPropagation(e);
                if (getActiveTripForVehicle(vehicle.id) || getAnyTripForVehicle(vehicle.id)) showVehicleRoute(vehicle.id);
            });
            state.markers.set(vehicle.id, marker);
        }
    });
    previousIds.forEach((id) => {
        if (!newIds.has(id)) {
            const marker = state.markers.get(id);
            if (marker && map.hasLayer(marker)) map.removeLayer(marker);
            state.markers.delete(id);
        }
    });
}

function applyFilters() {
    let visibleCount = 0;
    const visibleVehicles = [];
    state.markers.forEach((marker) => {
        const vehicle = marker.vehicle;
        const visible = shouldShowMarker(vehicle);
        if (visible) {
            if (!map.hasLayer(marker)) marker.addTo(map);
            visibleCount++;
            visibleVehicles.push(vehicle);
        } else if (map.hasLayer(marker)) {
            map.removeLayer(marker);
        }
    });
    document.getElementById("vehicle-count").textContent = visibleCount;
    updateVehicleList(visibleVehicles);
}

function getVehicleStatusColor(vehicle) {
    if (vehicle.vehicle_status === "running") return "#10b981";
    if (vehicle.vehicle_status === "stopped_engine_on") return "#f59e0b";
    if (vehicle.vehicle_status === "stopped_engine_off") return "#ef4444";
    return "#6b7280";
}

function updateVehicleList(vehicles) {
    const container = document.getElementById("vehicle-list");
    container.innerHTML = "";
    if ((state.lastVehicles || []).length === 0) {
        const message = document.createElement("p");
        message.className = "hint";
        message.textContent = "No vehicles on map yet. Please wait for data to load or check connections.";
        container.appendChild(message);
        return;
    }
    if (vehicles.length === 0) {
        const message = document.createElement("p");
        message.className = "hint";
        message.textContent = state.selectedLocation === "all" ?
            "Showing all vehicles on map." : "No vehicles found in selected area.";
        container.appendChild(message);
        return;
    }
    const list = document.createElement("ul");
    list.className = "vehicle-list-items";
    vehicles.forEach((vehicle) => {
        const item = document.createElement("li");
        const color = getVehicleStatusColor(vehicle);
        item.innerHTML = `
            <div style="display:flex; align-items:center; gap:10px;">
                <div style="width:12px; height:12px; border-radius:50%; background:${color}; flex-shrink:0;"></div>
                <div>
                    <strong style="color:var(--panel-text);">${UI.escapeHtml(vehicle.device_name || vehicle.driver_name || vehicle.vehicle_type || "Vehicle")}</strong>
                    <div style="color:var(--muted);">${UI.escapeHtml(vehicle.car_type || vehicle.vehicle_type || "Unknown type")}</div>
                </div>
            </div>
        `;
        item.style.cursor = "pointer";
        item.addEventListener("click", () => focusOnVehicle(vehicle));
        list.appendChild(item);
    });
    container.appendChild(list);
}

function updateVehicleTypes(vehicles) {
    const types = new Set();
    vehicles.forEach((vehicle) => {
        if (vehicle.car_type) types.add(vehicle.car_type);
        else if (vehicle.vehicle_type) types.add(vehicle.vehicle_type);
    });
    if (!state.vehicleTypes.size || state.vehicleTypes.size !== types.size) {
        state.vehicleTypes = types;
        state.activeTypes = new Set(types);
        buildTypeFilters(types);
    }
    buildStatusFilters();
}

function buildTypeFilters(types) {
    const container = document.getElementById("vehicle-types");
    container.innerHTML = "";
    const sorted = Array.from(types).sort();
    sorted.forEach((type, index) => {
        const id = `vehicle-type-${index}`;
        const label = document.createElement("label");
        label.className = "vehicle-type-option";
        const checkbox = document.createElement("input");
        const text = document.createElement("span");
        checkbox.type = "checkbox";
        checkbox.id = id;
        checkbox.value = type;
        checkbox.checked = true;
        text.textContent = type;
        label.appendChild(checkbox);
        label.appendChild(text);
        container.appendChild(label);
        state.activeTypes.add(type);
        checkbox.addEventListener("change", () => {
            checkbox.checked ? state.activeTypes.add(type) : state.activeTypes.delete(type);
            applyFilters();
        });
    });
}

function buildStatusFilters() {
    const container = document.getElementById("vehicle-statuses");
    container.innerHTML = "";
    Object.keys(STATUS_LABELS).forEach((status) => {
        const id = `vehicle-status-${status}`;
        const label = document.createElement("label");
        label.className = "vehicle-status-option";
        const checkbox = document.createElement("input");
        const indicator = document.createElement("div");
        indicator.style.width = "12px";
        indicator.style.height = "12px";
        indicator.style.borderRadius = "50%";
        indicator.style.flexShrink = "0";
        indicator.style.background = getVehicleStatusColor({ vehicle_status: status });
        const text = document.createElement("span");
        text.textContent = STATUS_LABELS[status];
        checkbox.type = "checkbox";
        checkbox.id = id;
        checkbox.value = status;
        checkbox.checked = state.activeStatuses.has(status);
        label.appendChild(checkbox);
        label.appendChild(indicator);
        label.appendChild(text);
        container.appendChild(label);
        checkbox.addEventListener("change", () => {
            checkbox.checked ? state.activeStatuses.add(status) : state.activeStatuses.delete(status);
            applyFilters();
        });
    });
}

function fetchVehicles() {
    return Promise.all([fetch("/api/vehicles"), fetch("/api/route-data")])
        .then(async ([vehiclesRes, routeRes]) => {
            if (!vehiclesRes.ok) throw new Error(`Server returned ${vehiclesRes.status}`);
            const payload = await vehiclesRes.json();
            const vehicles = Array.isArray(payload) ? payload : payload.vehicles;
            if (!Array.isArray(vehicles)) throw new Error("Expected array from /api/vehicles");
            const routeDataArray = await routeRes.json();
            const routeDataObj = {};
            routeDataArray.forEach(trip => {
                routeDataObj[`${trip.vehicle_id}-${trip.trip_id}`] = trip;
            });
            updateSourceStatus(Array.isArray(payload) ? {} : payload);
            state.lastVehicles = vehicles;
            saveCacheToStorage("cachedVehicles", vehicles);
            updateVehicleTypes(vehicles);
            getMarkersFromVehicles(vehicles);
            updateProximityCircle();
            applyFilters();
            updateRoutes(routeDataObj);
            saveCacheToStorage("cachedRouteData", routeDataArray);

            if (!state.hasInitialFocused) {
                const focusVehicleId = getQueryParam("focusVehicle");
                if (focusVehicleId) {
                    const vehicleToFocus = vehicles.find(v => v.id === focusVehicleId);
                    if (vehicleToFocus) {
                        state.hasInitialFocused = true;
                        setTimeout(() => focusOnVehicle(vehicleToFocus), 100);
                    }
                }
            }
        })
        .catch((error) => {
            console.error("Unable to refresh vehicles:", error);
            updateSourceStatus();
        });
}

function updateRoutes(routeData) {
    state.routeData = routeData;
    state.markers.forEach((marker, vehicleId) => {
        if (marker.vehicle && getActiveTripForVehicle(vehicleId)) {
            marker.setPopupContent(buildPopup(marker.vehicle));
        }
    });
    if (state.selectedVehicleId && getActiveTripForVehicle(state.selectedVehicleId)) {
        showVehicleRoute(state.selectedVehicleId);
    }
}

function showVehicleRoute(vehicleId) {
    hideCurrentRoute();
    const trip = getActiveTripForVehicle(vehicleId) || getAnyTripForVehicle(vehicleId);
    if (!trip || !trip.route_coords || trip.route_coords.length === 0) return;
    const isActive = trip.status === 'active';
    const polyline = L.polyline(trip.route_coords, { 
        color: isActive ? "#2f8ceb" : "#6b7280", 
        weight: isActive ? 4 : 2, 
        opacity: isActive ? 0.8 : 0.4,
        dashArray: isActive ? null : '10, 10'
    }).addTo(map);
    state.routePolylines[vehicleId] = polyline;
    state.selectedVehicleId = vehicleId;
}

function hideCurrentRoute() {
    Object.values(state.routePolylines).forEach(polyline => map.hasLayer(polyline) && map.removeLayer(polyline));
    state.routePolylines = {};
    Object.values(state.destinationMarkers).forEach(marker => map.hasLayer(marker) && map.removeLayer(marker));
    state.destinationMarkers = {};
    state.selectedVehicleId = null;
}

function setupSidebarToggle() {
    const appShell = document.querySelector(".app-shell");
    const toggleBtn1 = document.getElementById("toggle-sidebar");
    const toggleBtn2 = document.getElementById("toggle-sidebar-top");

    function toggleSidebar() {
        appShell.classList.toggle("sidebar-collapsed");
        setTimeout(() => map.invalidateSize(), 350);
    }
    if (toggleBtn1) toggleBtn1.addEventListener("click", toggleSidebar);
    if (toggleBtn2) toggleBtn2.addEventListener("click", toggleSidebar);
}

function setupVehicleSearch() {
    const vehicleSearch = document.getElementById("vehicle-search");
    if (vehicleSearch) {
        vehicleSearch.addEventListener("input", (e) => {
            state.vehicleSearchTerm = e.target.value;
            applyFilters();
        });
    }
}

function setupHasRouteFilter() {
    const hasRouteFilter = document.getElementById("has-route-filter");
    if (hasRouteFilter) {
        hasRouteFilter.addEventListener("change", (e) => {
            state.hasRouteFilter = e.target.checked;
            applyFilters();
        });
    }
}

function setupLocationAutocomplete() {
    const locationSearch = document.getElementById("location-search");

    if (!locationSearch) return;

    // ── Portal dropdown to <body> so overflow:hidden on .app-shell doesn't clip it ──
    // Remove the existing in-header placeholder first (if any)
    const existingList = document.getElementById("location-autocomplete-list");
    if (existingList) existingList.remove();

    // Create a fresh dropdown attached to body
    const autocompleteList = document.createElement("div");
    autocompleteList.id = "location-autocomplete-list";
    autocompleteList.className = "autocomplete-list hidden";
    document.body.appendChild(autocompleteList);

    function positionDropdown() {
        const rect = locationSearch.getBoundingClientRect();
        autocompleteList.style.position = "fixed";
        autocompleteList.style.top = (rect.bottom + 4) + "px";
        autocompleteList.style.left = rect.left + "px";
        autocompleteList.style.width = rect.width + "px";
        autocompleteList.style.zIndex = "99999";
    }

    let debounceTimer;
    let currentAbortController = null;

    async function showAutocomplete(filter = "") {
        // Cancel any previous in-flight geocode request
        if (currentAbortController) {
            currentAbortController.abort();
            currentAbortController = null;
        }

        autocompleteList.innerHTML = "";
        positionDropdown();

        // 1. Saved locations — filter client-side instantly
        const locations = Object.keys(KNOWN_LOCATIONS).sort();
        const filteredKnown = filter
            ? locations.filter(name => normalizeText(name).includes(normalizeText(filter)))
            : locations;

        filteredKnown.forEach(name => {
            const item = document.createElement("div");
            item.className = "autocomplete-item";
            item.innerHTML = `<span class="autocomplete-icon">📍</span> <strong>${UI.escapeHtml(name)}</strong> <small class="autocomplete-type">(Saved)</small>`;
            item.addEventListener("mousedown", (e) => {
                e.preventDefault(); // prevent input blur before click fires
                locationSearch.value = name;
                state.selectedLocation = name;
                state.customLocation = null;
                if (state.customLocationMarker) {
                    map.removeLayer(state.customLocationMarker);
                    state.customLocationMarker = null;
                }
                autocompleteList.classList.add("hidden");
                updateProximityCircle();
                applyFilters();
                focusOnLocation(name);
            });
            autocompleteList.appendChild(item);
        });

        // Show saved results immediately
        if (autocompleteList.children.length > 0) {
            autocompleteList.classList.remove("hidden");
        }

        // 2. Geocoded (real geographic) results — only when filter >= 3 chars
        if (filter.trim().length >= 3) {
            const abortController = new AbortController();
            currentAbortController = abortController;

            try {
                const response = await fetch(
                    `/api/geocode?q=${encodeURIComponent(filter.trim())}`,
                    { signal: abortController.signal }
                );

                if (abortController.signal.aborted) return;
                currentAbortController = null;

                const data = await response.json();
                if (data.success && data.results && data.results.length > 0) {
                    data.results.forEach(result => {
                        const item = document.createElement("div");
                        item.className = "autocomplete-item";
                        item.innerHTML = `<span class="autocomplete-icon">🔍</span> <span>${UI.escapeHtml(result.name)}</span> <small class="autocomplete-type">(Address)</small>`;
                        item.addEventListener("mousedown", (e) => {
                            e.preventDefault();
                            locationSearch.value = result.name;
                            state.selectedLocation = "__custom__";
                            state.customLocation = {
                                lat: result.lat,
                                lng: result.lng,
                                name: result.name,
                                radius_km: state.radiusKm
                            };

                            if (state.customLocationMarker) {
                                state.customLocationMarker.setLatLng([result.lat, result.lng]);
                                state.customLocationMarker.setPopupContent(`<strong>Custom Location:</strong><br>${UI.escapeHtml(result.name)}`);
                            } else {
                                state.customLocationMarker = L.marker([result.lat, result.lng]).addTo(map);
                                state.customLocationMarker.bindPopup(`<strong>Custom Location:</strong><br>${UI.escapeHtml(result.name)}`);
                            }
                            state.customLocationMarker.openPopup();

                            autocompleteList.classList.add("hidden");
                            updateProximityCircle();
                            applyFilters();
                            map.setView([result.lat, result.lng], 13);
                        });
                        autocompleteList.appendChild(item);
                    });

                    autocompleteList.classList.remove("hidden");
                }
            } catch (err) {
                if (err.name !== "AbortError") {
                    console.error("Geocoding failed:", err);
                }
            }
        }

        // Final: hide if nothing to show
        if (autocompleteList.children.length === 0) {
            autocompleteList.classList.add("hidden");
        }
    }

    locationSearch.addEventListener("input", (e) => {
        const value = e.target.value;
        clearTimeout(debounceTimer);

        if (value.trim() === "") {
            if (currentAbortController) {
                currentAbortController.abort();
                currentAbortController = null;
            }
            state.selectedLocation = "all";
            state.customLocation = null;
            if (state.customLocationMarker) {
                map.removeLayer(state.customLocationMarker);
                state.customLocationMarker = null;
            }
            updateProximityCircle();
            applyFilters();
            autocompleteList.classList.add("hidden");
            return;
        }

        debounceTimer = setTimeout(() => showAutocomplete(value), 300);
    });

    locationSearch.addEventListener("focus", () => showAutocomplete(locationSearch.value));

    locationSearch.addEventListener("blur", () => {
        // Small delay so mousedown on an item fires before blur hides the list
        setTimeout(() => autocompleteList.classList.add("hidden"), 150);
    });

    // Close on outside click
    document.addEventListener("click", (e) => {
        if (e.target !== locationSearch && !autocompleteList.contains(e.target)) {
            autocompleteList.classList.add("hidden");
        }
    });

    // Reposition if window scrolls or resizes
    window.addEventListener("scroll", positionDropdown, true);
    window.addEventListener("resize", positionDropdown);
}


function setupLocationPinButton() {
    const pinBtn = document.getElementById("location-pin-btn");
    if (!pinBtn) return;
    
    pinBtn.addEventListener("click", () => {
        state.locationPinMode = !state.locationPinMode;
        if (state.locationPinMode) {
            pinBtn.classList.add("active");
            pinBtn.textContent = "Cancel Pinning";
            map.getContainer().style.cursor = "crosshair";
            UI.toast("Click on the map to set a custom location", "info");
        } else {
            pinBtn.classList.remove("active");
            pinBtn.textContent = "Pin on Map";
            map.getContainer().style.cursor = "";
        }
    });
}

function updateLoadingProgress(percent, text) {
    const progressBar = document.getElementById("progress-bar");
    const loadingText = document.getElementById("loading-text");
    if (progressBar) progressBar.style.width = `${percent}%`;
    if (loadingText) loadingText.textContent = text;
}

function hideLoadingScreen() {
    const loadingScreen = document.getElementById("loading-screen");
    if (loadingScreen) loadingScreen.classList.add("hidden");
}

function saveCacheToStorage(key, data) {
    try {
        localStorage.setItem(key, JSON.stringify(data));
    } catch (e) {
        console.warn("Failed to save to localStorage:", e);
    }
}

function loadCacheFromStorage(key) {
    try {
        const data = localStorage.getItem(key);
        if (data) return JSON.parse(data);
    } catch (e) {
        console.warn("Failed to load from localStorage:", e);
    }
    return null;
}

function getQueryParam(param) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(param);
}

function startPolling() {
    // Bind UI elements immediately on startup
    const refreshBtn = document.getElementById("refresh-button");
    if (refreshBtn) {
        refreshBtn.addEventListener("click", fetchVehicles);
    }
    setupVehicleSearch();
    setupHasRouteFilter();
    setupLocationAutocomplete();
    setupLocationPinButton();
    setupSidebarToggle();

    updateLoadingProgress(10, "Loading known locations...");

    const cachedVehicles = loadCacheFromStorage("cachedVehicles");
    const cachedRouteData = loadCacheFromStorage("cachedRouteData");
    const cachedKnownLocations = loadCacheFromStorage("cachedKnownLocations");

    if (cachedKnownLocations) {
        KNOWN_LOCATIONS = cachedKnownLocations;
        updateProximityCircle();
        renderAllLocations();
        updateLoadingProgress(20, "Loading cached locations...");
    }

    if (cachedVehicles && Array.isArray(cachedVehicles)) {
        updateLoadingProgress(40, "Loading cached vehicles...");
        state.lastVehicles = cachedVehicles;
        updateVehicleTypes(cachedVehicles);
        getMarkersFromVehicles(cachedVehicles);
        if (cachedRouteData && Array.isArray(cachedRouteData)) {
            const routeDataObj = {};
            cachedRouteData.forEach(trip => {
                routeDataObj[`${trip.vehicle_id}-${trip.trip_id}`] = trip;
            });
            updateRoutes(routeDataObj);
        }
        applyFilters();

        const focusVehicleId = getQueryParam("focusVehicle");
        if (focusVehicleId && !state.hasInitialFocused) {
            const vehicleToFocus = state.lastVehicles.find(v => v.id === focusVehicleId);
            if (vehicleToFocus) {
                state.hasInitialFocused = true;
                setTimeout(() => focusOnVehicle(vehicleToFocus), 100);
            }
        }
    }

    fetch("/api/known-locations")
        .then(response => {
            updateLoadingProgress(30, "Known locations loaded. Loading vehicles...");
            return response.json();
        })
        .then(locations => {
            KNOWN_LOCATIONS = locations;
            saveCacheToStorage("cachedKnownLocations", locations);
            updateProximityCircle();
            renderAllLocations();
            return Promise.all([
                fetch("/api/vehicles").then(res => res.json()),
                fetch("/api/route-data").then(res => res.json())
            ]);
        })
        .then(([vehiclesData, routeDataArray]) => {
            updateLoadingProgress(70, "Vehicles loaded. Setting up UI...");

            const vehicles = Array.isArray(vehiclesData) ? vehiclesData : vehiclesData.vehicles;
            if (Array.isArray(vehicles)) {
                updateSourceStatus(Array.isArray(vehiclesData) ? {} : vehiclesData);
                state.lastVehicles = vehicles;
                saveCacheToStorage("cachedVehicles", vehicles);
                updateVehicleTypes(vehicles);
                getMarkersFromVehicles(vehicles);
                
                const routeDataObj = {};
                routeDataArray.forEach(trip => {
                    routeDataObj[`${trip.vehicle_id}-${trip.trip_id}`] = trip;
                });
                updateRoutes(routeDataObj);
                
                saveCacheToStorage("cachedRouteData", routeDataArray);
                applyFilters();
                
                const focusVehicleId = getQueryParam("focusVehicle");
                if (focusVehicleId && !state.hasInitialFocused) {
                    const vehicleToFocus = state.lastVehicles.find(v => v.id === focusVehicleId);
                    if (vehicleToFocus) {
                        state.hasInitialFocused = true;
                        setTimeout(() => focusOnVehicle(vehicleToFocus), 100);
                    }
                }
            }

            updateLoadingProgress(100, "Ready!");
            setTimeout(hideLoadingScreen, 500);
            setInterval(fetchVehicles, POLLING_INTERVAL_MS);
        })
        .catch(error => {
            console.error("Failed to load data:", error);
            updateLoadingProgress(100, "Ready!");
            setTimeout(hideLoadingScreen, 500);
            setInterval(fetchVehicles, POLLING_INTERVAL_MS);
        });
}

startPolling();
