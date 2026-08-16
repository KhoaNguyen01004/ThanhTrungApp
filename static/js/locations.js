
document.addEventListener("DOMContentLoaded", function () {
    const MAP_CENTER = [10.8231, 106.6297];
    let KNOWN_LOCATIONS = {};
    let selectedLocationName = null;
    let editingLocationName = null;
    let pendingCorners = [];
    let cornerMarkers = [];
    let previewPolygon = null;
    let isEditing = false;
    let previewPolygons = []; // All preview polygons for selected location
    let locationNameMarker = null; // Marker for location name label
    let allLocationPolygons = []; // All polygons for all locations (always shown)
    let allLocationLabels = []; // All location name labels (show/hide based on zoom)
    const MIN_ZOOM_FOR_LABELS = 14; // Minimum zoom level to show labels

    const map = L.map("location-map").setView(MAP_CENTER, 11);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors"
    }).addTo(map);

    // Zoom listener to update label visibility!
    map.on('zoomend', updateLabelsVisibility);

    function escapeHtml(value) {
        return String(value || "").replace(/[&<>"']/g, (char) => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            "\"": "&quot;",
            "'": "&#39;"
        })[char]);
    }
    
    function getDistanceMeters(lat1, lng1, lat2, lng2) {
        const toRad = (deg) => (deg * Math.PI) / 180;
        const R = 6371000; // Earth radius in meters
        const dLat = toRad(lat2 - lat1);
        const dLng = toRad(lng2 - lng1);
        const a = Math.sin(dLat / 2) ** 2 +
            Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return R * c;
    }

    function loadLocations() {
        return fetch("/api/manual-locations")
            .then(res => res.json())
            .then(data => {
                KNOWN_LOCATIONS = data;
                renderLocationList();
                renderAllLocations(); // Show all locations on the map by default!
            });
    }

    function renderAllLocations() {
        // Clear existing polygons and labels first
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

            // Add all polygons for this location
            polygonsToAdd.forEach(polygon => {
                const poly = L.polygon(polygon, {
                    color: "#2563eb",
                    weight: 3,
                    opacity: 0.7,
                    fillOpacity: 0.15
                }).addTo(map);
                allLocationPolygons.push(poly);
                // Make the polygon clickable to select the location!
                poly.on('click', () => selectLocation(name));
            });

            // Add label at centroid
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
                        ">${escapeHtml(name)}</div>`,
                        iconSize: [null, null],
                        iconAnchor: [0, 0]
                    })
                });
                // Only show label if zoom level is high enough
                if (map.getZoom() >= MIN_ZOOM_FOR_LABELS) {
                    label.addTo(map);
                }
                allLocationLabels.push(label);
            }
        });

        updateLabelsVisibility(); // Update initial label visibility
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

    function renderLocationList(filter = "") {
        const container = document.getElementById("location-list");
        if (!container) return;
        container.innerHTML = "";

        const locations = Object.keys(KNOWN_LOCATIONS).sort();
        const filtered = filter ?
            locations.filter(name => normalizeText(name).includes(normalizeText(filter))) :
            locations;

        if (filtered.length === 0) {
            const message = document.createElement("p");
            message.style.color = "#6b7280";
            message.style.padding = "16px";
            message.textContent = "No saved locations found.";
            container.appendChild(message);
            return;
        }

        filtered.forEach(name => {
            const item = document.createElement("div");
            item.className = "location-item" + (selectedLocationName === name ? " active" : "");
            const loc = KNOWN_LOCATIONS[name];
            const polygonCount = (loc.polygons ? loc.polygons.length : (loc.corners ? 1 : 0));

            item.innerHTML = `
                <div class="location-item-header">
                    <span class="location-item-name">${escapeHtml(name)}</span>
                    <div style="display: flex; gap: 8px;">
                        <button class="btn-edit" data-action="edit" data-name="${escapeHtml(name)}" style="
                            background: #2563eb;
                            color: white;
                            border: none;
                            padding: 6px 12px;
                            border-radius: 4px;
                            cursor: pointer;
                            font-size: 13px;
                            font-weight: 500;
                        ">Edit</button>
                        <button class="btn-danger" data-action="delete" data-name="${escapeHtml(name)}">Delete</button>
                    </div>
                </div>
                <div style="font-size: 12px; color: #6b7280; margin-top: 4px;">
                    ${polygonCount} polygon(s)
                </div>
            `;

            item.addEventListener("click", (e) => {
                if (e.target.tagName === "BUTTON") return;
                selectLocation(name);
            });

            container.appendChild(item);
        });

        container.querySelectorAll("[data-action='edit']").forEach(btn => {
            btn.addEventListener("click", () => startEditLocation(btn.dataset.name));
        });

        container.querySelectorAll("[data-action='delete']").forEach(btn => {
            btn.addEventListener("click", () => deleteLocation(btn.dataset.name));
        });
    }

    function clearAllLocations() {
        if (!confirm("Are you sure you want to clear ALL locations?")) return;

        fetch("/api/clear-all-locations", {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showToast("All locations cleared!", "success");
                    loadLocations();
                    clearMapLayers();
                } else {
                    showToast(data.message || "Error clearing locations", "error");
                }
            })
            .catch(err => {
                console.error(err);
                showToast("Error clearing locations", "error");
            });
    }

    function clearMapLayers() {
        if (previewPolygon) {
            map.removeLayer(previewPolygon);
            previewPolygon = null;
        }
        cornerMarkers.forEach(marker => map.removeLayer(marker));
        cornerMarkers = [];
        previewPolygons.forEach(p => map.removeLayer(p));
        previewPolygons = [];
        if (locationNameMarker) {
            map.removeLayer(locationNameMarker);
            locationNameMarker = null;
        }
        // We do NOT clear allLocationPolygons and allLocationLabels here, because we want them to stay visible!
    }

    function selectLocation(name) {
        selectedLocationName = name;
        const searchInput = document.getElementById("location-search");
        renderLocationList(searchInput ? searchInput.value : "");
        clearMapLayers();

        // Highlight the selected location's polygons!
        allLocationPolygons.forEach(poly => {
            poly.setStyle({ color: "#2563eb", weight: 3, fillOpacity: 0.15 }); // Default color
        });
        
        const loc = KNOWN_LOCATIONS[name];
        let allBounds = [];

        // Find the selected polygons in allLocationPolygons and highlight them!
        // We'll recreate the bounds for fitting the map
        let polygonsToCheck = [];
        if (loc.polygons && Array.isArray(loc.polygons)) {
            polygonsToCheck = loc.polygons;
        } else if (loc.corners) {
            polygonsToCheck = [loc.corners];
        }
        
        polygonsToCheck.forEach(polygon => {
            allBounds.push(L.latLngBounds(polygon));
            // Let's loop through allLocationPolygons to find which ones match this polygon and highlight them!
            allLocationPolygons.forEach(poly => {
                const polyLatLngs = poly.getLatLngs()[0];
                const isMatch = polygon.every(([lat, lng], i) => 
                    Math.abs(polyLatLngs[i]?.lat - lat) < 0.00001 && Math.abs(polyLatLngs[i]?.lng - lng) < 0.00001
                );
                if (isMatch) {
                    poly.setStyle({ color: "#ff6b6b", weight: 4, fillOpacity: 0.25 }); // Highlight color!
                }
            });
        });

        if (allBounds.length > 0) {
            const combinedBounds = allBounds.reduce((acc, b) => acc.extend(b), L.latLngBounds([]));
            map.fitBounds(combinedBounds, { padding: [30, 30] });
        }
    }

    function startAddLocation() {
        isEditing = false;
        editingLocationName = null;
        pendingCorners = [];
        clearMapLayers();
        const editTitle = document.getElementById("edit-title");
        const nameInput = document.getElementById("location-name-input");
        const saveBtn = document.getElementById("save-location-btn");
        const editPanel = document.getElementById("edit-panel");
        if (editTitle) editTitle.textContent = "Add New Location";
        if (nameInput) nameInput.value = "";
        if (saveBtn) saveBtn.disabled = true;
        if (editPanel) editPanel.classList.remove("hidden");
        map.off("click", handleMapClick);
        map.on("click", handleMapClick);
    }

    function startEditLocation(name) {
        isEditing = true;
        editingLocationName = name;
        pendingCorners = [];
        clearMapLayers();
        
        // Load existing corners
        const loc = KNOWN_LOCATIONS[name];
        if (loc) {
            // Use the first polygon for editing (or combine?) - let's use first polygon
            let cornersToLoad = [];
            let allBounds = [];
            if (loc.polygons && loc.polygons.length > 0) {
                loc.polygons.forEach(p => allBounds.push(L.latLngBounds(p)));
                cornersToLoad = loc.polygons[0]; // Load first polygon for editing
            } else if (loc.corners) {
                cornersToLoad = loc.corners;
                allBounds.push(L.latLngBounds(loc.corners));
            }
            
            if (cornersToLoad.length > 0) {
                pendingCorners = [...cornersToLoad];
                // Add markers for existing corners
                pendingCorners.forEach(([lat, lng]) => {
                    const marker = L.marker([lat, lng], {
                        icon: L.icon({
                            iconUrl: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23dc2626'%3E%3Cpath d='M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8z'/%3E%3C/svg%3E",
                            iconSize: [20, 20],
                            iconAnchor: [10, 10]
                        })
                    }).addTo(map);
                    cornerMarkers.push(marker);
                });
                
                // Draw preview polygon
                if (pendingCorners.length >= 3) {
                    previewPolygon = L.polygon(pendingCorners, {
                        color: "#2563eb",
                        weight: 3,
                        opacity: 0.7,
                        fillOpacity: 0.15
                    }).addTo(map);
                }
                
                // Pan/zoom to location bounds
                if (allBounds.length > 0) {
                    const combinedBounds = allBounds.reduce((acc, b) => acc.extend(b), L.latLngBounds([]));
                    map.fitBounds(combinedBounds, { padding: [30, 30] });
                }
            }
        }

        const editTitle = document.getElementById("edit-title");
        const nameInput = document.getElementById("location-name-input");
        const saveBtn = document.getElementById("save-location-btn");
        const editPanel = document.getElementById("edit-panel");
        if (editTitle) editTitle.textContent = `Edit ${name}`;
        if (nameInput) nameInput.value = name;
        updateSaveButton();
        if (editPanel) editPanel.classList.remove("hidden");
        map.off("click", handleMapClick);
        map.on("click", handleMapClick);
    }

    function handleMapClick(e) {
        const lat = e.latlng.lat;
        const lng = e.latlng.lng;
        
        // Check if we clicked near an existing pin to remove it
        let removedIndex = -1;
        for (let i = 0; i < pendingCorners.length; i++) {
            const [cornerLat, cornerLng] = pendingCorners[i];
            const distance = getDistanceMeters(lat, lng, cornerLat, cornerLng);
            if (distance < 50) { // Within 50 meters is considered clicking the same pin
                removedIndex = i;
                break;
            }
        }
        
        if (removedIndex !== -1) {
            // Remove the pin
            pendingCorners.splice(removedIndex, 1);
            map.removeLayer(cornerMarkers[removedIndex]);
            cornerMarkers.splice(removedIndex, 1);
        } else {
            // Add new pin
            pendingCorners.push([lat, lng]);

            const marker = L.marker([lat, lng], {
                icon: L.icon({
                    iconUrl: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23dc2626'%3E%3Cpath d='M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8z'/%3E%3C/svg%3E",
                    iconSize: [20, 20],
                    iconAnchor: [10, 10]
                })
            }).addTo(map);
            cornerMarkers.push(marker);
        }

        if (previewPolygon) map.removeLayer(previewPolygon);
        if (pendingCorners.length >= 3) {
            previewPolygon = L.polygon(pendingCorners, {
                color: "#2563eb",
                weight: 3,
                opacity: 0.7,
                fillOpacity: 0.15
            }).addTo(map);
        }

        updateSaveButton();
    }

    function clearPendingCorners() {
        pendingCorners = [];
        clearMapLayers();
        updateSaveButton();
    }

    function updateSaveButton() {
        const nameInput = document.getElementById("location-name-input");
        const saveBtn = document.getElementById("save-location-btn");
        if (!nameInput || !saveBtn) return;
        saveBtn.disabled = !nameInput.value.trim() || pendingCorners.length < 3;
    }

    function closeEditPanel() {
        map.off("click", handleMapClick);
        const editPanel = document.getElementById("edit-panel");
        if (editPanel) editPanel.classList.add("hidden");
        if (selectedLocationName) {
            selectLocation(selectedLocationName);
        } else {
            clearMapLayers();
        }
    }

    async function saveLocation() {
        const nameInput = document.getElementById("location-name-input");
        const name = nameInput ? nameInput.value.trim() : "";
        if (!name || pendingCorners.length < 3) {
            showToast("Please enter a location name and add at least 3 corners.", "warning");
            return;
        }

        try {
            let url = "/api/save-location";
            let body = { name, corners: pendingCorners };
            if (isEditing) {
                url = "/api/update-location";
                body = { original_name: editingLocationName, name, corners: pendingCorners };
            }

            const res = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body)
            });

            const data = await res.json();
            if (!data.success) throw new Error(data.message || "Failed to save location");

            await loadLocations();
            selectedLocationName = name;
            closeEditPanel();
            selectLocation(name);
            showToast(`Location '${name}' saved successfully!`, "success");
        } catch (err) {
            console.error(err);
            showToast(err.message || "Error saving location", "error");
        }
    }

    async function deleteLocation(name) {
        if (!confirm(`Are you sure you want to delete '${name}'?`)) return;

        try {
            const res = await fetch("/api/delete-location", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name })
            });

            const data = await res.json();
            if (!data.success) throw new Error(data.message || "Failed to delete location");

            await loadLocations();
            if (selectedLocationName === name) {
                selectedLocationName = null;
                clearMapLayers();
            }
            const searchInput = document.getElementById("location-search");
            renderLocationList(searchInput ? searchInput.value : "");
            showToast(`Location '${name}' deleted successfully!`, "success");
        } catch (err) {
            console.error(err);
            showToast(err.message || "Error deleting location", "error");
        }
    }

    function setupLocationAutocomplete() {
        const locationSearch = document.getElementById("location-search");
        const autocompleteList = document.getElementById("location-autocomplete-list");
        const nameInput = document.getElementById("location-name-input");
        const nameAutocompleteList = document.getElementById("location-name-autocomplete-list");

        function showAutocompleteForInput(inputEl, listEl, onSelect) {
            return function (filter = "") {
                listEl.innerHTML = "";
                const locations = Object.keys(KNOWN_LOCATIONS).sort();
                let filtered = filter ? locations.filter(name => normalizeText(name).includes(normalizeText(filter))) : locations;

                if (filtered.length === 0) {
                    listEl.classList.add("hidden");
                    return;
                }

                filtered.forEach(name => {
                    const item = document.createElement("div");
                    item.className = "location-autocomplete-item";
                    item.textContent = name;
                    item.addEventListener("click", () => {
                        inputEl.value = name;
                        onSelect(name);
                        listEl.classList.add("hidden");
                    });
                    listEl.appendChild(item);
                });

                listEl.classList.remove("hidden");
            }
        }

        if (locationSearch && autocompleteList) {
            const showFn = showAutocompleteForInput(
                locationSearch,
                autocompleteList,
                (name) => {
                    selectLocation(name);
                }
            );
            locationSearch.addEventListener("input", (e) => {
                renderLocationList(e.target.value);
                showFn(e.target.value);
            });
            locationSearch.addEventListener("focus", () => showFn(locationSearch.value));
        }

        if (nameInput && nameAutocompleteList) {
            const showFn = showAutocompleteForInput(
                nameInput,
                nameAutocompleteList,
                (name) => {
                    nameInput.value = name;
                    updateSaveButton();
                }
            );
            nameInput.addEventListener("input", (e) => {
                showFn(e.target.value);
                updateSaveButton();
            });
            nameInput.addEventListener("focus", () => showFn(nameInput.value));
        }

        document.addEventListener("click", (e) => {
            if (!e.target.closest(".location-list-header")) {
                if (autocompleteList) autocompleteList.classList.add("hidden");
            }
            if (!e.target.closest(".location-edit-panel")) {
                if (nameAutocompleteList) nameAutocompleteList.classList.add("hidden");
            }
        });
    }

    // Event listeners
    const addBtn = document.getElementById("add-location-btn");
    if (addBtn) addBtn.addEventListener("click", startAddLocation);

    const closeBtn = document.getElementById("close-edit-btn");
    if (closeBtn) closeBtn.addEventListener("click", closeEditPanel);

    const cancelBtn = document.getElementById("cancel-edit-btn");
    if (cancelBtn) cancelBtn.addEventListener("click", closeEditPanel);

    const saveBtn = document.getElementById("save-location-btn");
    if (saveBtn) saveBtn.addEventListener("click", saveLocation);

    const clearCornersBtn = document.getElementById("clear-corners-btn");
    if (clearCornersBtn) clearCornersBtn.addEventListener("click", clearPendingCorners);

    const clearAllBtn = document.getElementById("clear-all-locations-btn");
    if (clearAllBtn) clearAllBtn.addEventListener("click", clearAllLocations);

    const nameInput = document.getElementById("location-name-input");
    if (nameInput) nameInput.addEventListener("input", updateSaveButton);

    const searchInput = document.getElementById("location-search");
    if (searchInput) searchInput.addEventListener("input", (e) => {
        renderLocationList(e.target.value);
    });

    setupLocationAutocomplete();
    loadLocations();

    // Also, call map.invalidateSize() after a short delay to make sure it renders correctly!
    setTimeout(() => map.invalidateSize(), 100);
});
