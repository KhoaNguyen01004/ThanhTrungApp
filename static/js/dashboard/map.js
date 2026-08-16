// ================================================================
// Dispatch Dashboard — Map Module (Center Panel)
// ================================================================
window.DASH = window.DASH || {};

(function () {
  'use strict';

  let mapInstance = null;
  let vehicleMarkerLayer = null;
  let stopMarkerLayer = null;
  let routeLayer = null;
  let vehicleMarkers = {}; // assignment_id → { marker, labelEl, label, borderColor, lat, lng, popupHtml }
  let currentZoomAssignment = null;

  let stopMarkers = new Map(); // stop_id → { marker, iconEl, cssClass, popupHtml }
  let stopsSetKey = null; // join of stop ids currently rendered — detects assignment switch vs. same-set poll
  let lastRouteKey = null; // join of route coords — skips redundant polyline rebuilds

  // Canonical escaper from utils.js (loaded before this file). The private
  // copy this replaces built a text node and read back .innerHTML, which per
  // the HTML fragment-serialization algorithm escapes only & < > and NBSP —
  // NOT quotes. It was used inside a title="..." attribute below, so a
  // station_name containing a double quote broke out of the attribute
  // (audit S-02). UI.escapeHtml escapes " and ' as well.
  const escapeHtml = UI.escapeHtml;

  // Leaflet drags the map to keep an open popup in view, from
  // Popup._adjustPan(). That is reached by two separate paths, and a selected
  // vehicle has its popup open (zoomToVehicle opens it), so on a moving truck
  // BOTH fired on every 12-second poll:
  //
  //   1. popup.setContent()  -> DivOverlay.update()   -> _adjustPan()
  //   2. marker.setLatLng()  -> fires 'move'          -> Layer._movePopup()
  //                          -> popup.setLatLng()     -> _adjustPan()
  //
  // The result was the map yanking itself back onto the vehicle every poll,
  // which made it impossible to pan off and study a street for more than a few
  // seconds. Suppressed for background updates only: opening a popup still
  // auto-pans (Popup.onAdd -> update -> _adjustPan), which is what keeps a
  // popup usable when its marker sits near the edge of the map.
  function withoutAutoPan(marker, fn) {
    const popup = marker.getPopup();
    if (!popup) { fn(); return; }
    const previous = popup.options.autoPan;
    popup.options.autoPan = false;
    try {
      fn();
    } finally {
      popup.options.autoPan = previous;
    }
  }

  // ── Basemaps ───────────────────────────────────────────────────
  // Satellite by default, with Streets and Muted available from the layer
  // control. The choice is a matter of taste and lighting conditions rather
  // than something one default gets right for everyone, so it is the
  // dispatcher's to make and it persists.
  const BASEMAP_STORAGE_KEY = 'dashboard_basemap';

  function readSavedBasemap() {
    // Private-browsing mode throws on access, not just on write.
    try { return localStorage.getItem(BASEMAP_STORAGE_KEY); } catch { return null; }
  }

  function saveBasemap(name) {
    try { localStorage.setItem(BASEMAP_STORAGE_KEY, name); } catch { /* not fatal */ }
  }

  let activeBasemap = null;

  function addBasemaps(map) {
    const CARTO_ATTR = '&copy; OpenStreetMap contributors &copy; CARTO';

    const layers = {
      // Imagery carries no street names at all, so it is paired with CARTO's
      // transparent label tiles — the "dark" variant is light type meant to sit
      // on a dark background, which is what imagery is. Without the overlay a
      // dispatcher can see the depot roof but can't tell which road it is on.
      Satellite: L.layerGroup([
        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
          maxZoom: 19,
          attribution: 'Imagery &copy; Esri, Maxar, Earthstar Geographics',
        }),
        L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/dark_only_labels/{z}/{x}/{y}{r}.png', {
          maxZoom: 19,
          subdomains: 'abcd',
          attribution: CARTO_ATTR,
        }),
      ]),
      Streets: L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
        maxZoom: 19,
        subdomains: 'abcd',
        attribution: CARTO_ATTR,
      }),
      Muted: L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
        maxZoom: 19,
        subdomains: 'abcd',
        attribution: CARTO_ATTR,
      }),
    };

    const saved = readSavedBasemap();
    activeBasemap = layers[saved] ? saved : 'Satellite';
    layers[activeBasemap].addTo(map);

    // topleft, stacking under the zoom buttons — .map-controls owns the top
    // right corner and the vehicle info bar owns the bottom.
    L.control.layers(layers, buildOverlays(map), { position: 'topleft' }).addTo(map);
    map.on('baselayerchange', (e) => {
      activeBasemap = e.name;
      saveBasemap(e.name);
    });
  }

  // ── Street view coverage overlay ───────────────────────────────
  // Mapillary's coverage as green lines, the way Street View draws its blue
  // ones. Without it a dispatcher clicking for street view is guessing: a road
  // with imagery and a road without look identical on any basemap, and most of
  // this fleet's stops are down lanes that have none.
  //
  // Vector tiles rather than the search API because coverage is a whole-city
  // question and the search endpoint's bbox is capped at 0.01 degrees square —
  // about 1 km, which cannot answer "which roads around here are covered".
  //
  // Off by default and remembered, like the basemap. It is dense in central
  // HCMC and would otherwise clutter a view whose job is watching trucks.
  const COVERAGE_STORAGE_KEY = 'dashboard_coverage_on';
  const COVERAGE_TILE_URL =
    'https://tiles.mapillary.com/maps/vtp/mly1_public/2/{z}/{x}/{y}?access_token={token}';

  let coverageLayer = null;

  function mapillaryToken() {
    return (window.DASH_CONFIG && window.DASH_CONFIG.mapillaryToken) || '';
  }

  function buildOverlays(map) {
    // Both are optional at runtime: no token configured, or the VectorGrid CDN
    // unreachable, and the dashboard simply has no coverage layer rather than
    // failing to build a map.
    if (!mapillaryToken() || !L.vectorGrid || !L.vectorGrid.protobuf) return null;

    coverageLayer = L.vectorGrid.protobuf(
      COVERAGE_TILE_URL.replace('{token}', encodeURIComponent(mapillaryToken())),
      {
        rendererFactory: L.canvas.tile,
        interactive: true,
        maxNativeZoom: 14, // the tileset stops here; Leaflet overzooms past it
        vectorTileLayerStyles: {
          // Sequences (z6-14) are the "walkable road" lines.
          sequence: { color: '#22c55e', weight: 2, opacity: 0.75 },
          // Individual images (z14) — the dots you actually click into.
          image: { radius: 2.5, color: '#22c55e', fillColor: '#22c55e', fillOpacity: 0.9, weight: 0 },
          // Low-zoom clusters. Faint: at z<6 this is continent-scale and
          // means nothing operationally.
          overview: { radius: 1.5, color: '#22c55e', fillOpacity: 0.4, weight: 0 },
        },
      }
    );

    // Clicking coverage opens that exact image — no lookup, no nearest-match
    // guessing, because the dispatcher has already pointed at one.
    coverageLayer.on('click', (e) => {
      const props = (e && e.layer && e.layer.properties) || {};
      // The image layer carries `id`; a sequence line carries `image_id` for
      // its representative image. Either is enough to enter the viewer.
      const imageId = props.id || props.image_id;
      if (imageId && DASH.streetview) {
        DASH.streetview.openImage(imageId, 'Street view');
      }
      if (L.DomEvent && e.originalEvent) L.DomEvent.stop(e.originalEvent);
    });

    let on = false;
    try { on = localStorage.getItem(COVERAGE_STORAGE_KEY) === '1'; } catch { /* private mode */ }
    if (on) coverageLayer.addTo(map);

    map.on('overlayadd', (e) => {
      if (e.layer !== coverageLayer) return;
      try { localStorage.setItem(COVERAGE_STORAGE_KEY, '1'); } catch { /* not fatal */ }
    });
    map.on('overlayremove', (e) => {
      if (e.layer !== coverageLayer) return;
      try { localStorage.setItem(COVERAGE_STORAGE_KEY, '0'); } catch { /* not fatal */ }
    });

    return { 'Street view coverage': coverageLayer };
  }

  // ── Imagery capture date ───────────────────────────────────────
  // Clicking the satellite basemap asks Esri when the imagery under that point
  // was actually taken. It matters operationally: a warehouse yard photographed
  // in 2016 may not be the yard a driver is looking at, and the dashboard
  // otherwise gives no clue how old what you're seeing is.
  //
  // Only wired up while Satellite is the active basemap — on the street layers
  // there is no imagery to date, and a stray click should do nothing.
  const IMAGERY_IDENTIFY_URL =
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/identify';
  const IMAGERY_TIMEOUT_MS = 10000;

  function toNumber(value) {
    if (value == null) return null;
    const n = parseFloat(value);
    return isNaN(n) ? null : n;
  }

  // Every attribute comes back as a *string*, and a missing value as the
  // literal "Null" — not JSON null, not an empty string. Two schemas are in
  // play across the layers this returns: the footprint layers (0-4) use
  // "DATE (YYYYMMDD)" / "RESOLUTION (M)" / "SOURCE_INFO", the per-zoom metadata
  // layers (5-18) use SRC_DATE / SRC_RES / NICE_NAME. Read both.
  function attr(attrs, ...names) {
    for (const name of names) {
      const value = attrs[name];
      if (value != null && value !== '' && value !== 'Null') return value;
    }
    return null;
  }

  // Returns ISO yyyy-mm-dd. The compact "20241229" form is unambiguous and
  // preferred; SRC_DATE2 arrives as US "12/29/2024", which is parsed by hand
  // because new Date() on that string is locale-dependent — in a d/m/y locale
  // it silently yields a different day, or an invalid date for 12/29.
  function parseImageryDate(attrs) {
    const compact = attr(attrs, 'DATE (YYYYMMDD)', 'SRC_DATE');
    if (compact && /^\d{8}$/.test(String(compact))) {
      const s = String(compact);
      return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
    }
    const slashed = attr(attrs, 'SRC_DATE2', 'DATE');
    const m = slashed && String(slashed).match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (m) return `${m[3]}-${m[1].padStart(2, '0')}-${m[2].padStart(2, '0')}`;
    return null;
  }

  function pickBestImageryResult(results, zoom) {
    const candidates = (results || []).map((r) => {
      const a = r.attributes || {};
      return {
        date: parseImageryDate(a),
        product: attr(a, 'SOURCE_INFO', 'NICE_NAME'),
        source: attr(a, 'SOURCE', 'NICE_DESC'),
        sensor: attr(a, 'DESCRIPTION', 'SRC_DESC'),
        resolution: toNumber(attr(a, 'RESOLUTION (M)', 'SRC_RES')),
        accuracy: toNumber(attr(a, 'ACCURACY (M)', 'SRC_ACC')),
        minLevel: toNumber(attr(a, 'MinMapLevel', 'FROM_CACHE_LEVEL')),
        maxLevel: toNumber(attr(a, 'MaxMapLevel', 'TO_CACHE_LEVEL')),
      };
      // A record with no capture date can't answer the question that was asked.
    }).filter((c) => c.date);

    if (candidates.length === 0) return null;

    // A point is covered by several overlapping footprints at different zoom
    // ranges. Prefer one whose cache-level range actually covers the zoom being
    // looked at, then the sharpest, then the most recent.
    const covering = candidates.filter(
      (c) => c.minLevel != null && c.maxLevel != null && zoom >= c.minLevel && zoom <= c.maxLevel
    );
    const pool = covering.length > 0 ? covering : candidates;
    pool.sort((a, b) => {
      const ra = a.resolution == null ? Infinity : a.resolution;
      const rb = b.resolution == null ? Infinity : b.resolution;
      if (ra !== rb) return ra - rb;
      return b.date.localeCompare(a.date);
    });
    return pool[0];
  }

  function identifyImagery(latlng) {
    const bounds = mapInstance.getBounds();
    const size = mapInstance.getSize();
    const params = new URLSearchParams({
      f: 'json',
      geometry: `${latlng.lng},${latlng.lat}`,
      geometryType: 'esriGeometryPoint',
      sr: '4326',
      // 'visible' makes the service scale-filter to the layers actually drawn
      // at this zoom. 'all' returns every overlapping footprint — measured at
      // 100 records with exceededTransferLimit:true on a single click.
      layers: 'visible',
      tolerance: '3',
      mapExtent: [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()].join(','),
      imageDisplay: `${size.x},${size.y},96`,
      // Not cosmetic. Each footprint is a detailed polygon; leaving geometry on
      // turned a single-result response into ~75 KB.
      returnGeometry: 'false',
    });

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), IMAGERY_TIMEOUT_MS);

    return fetch(`${IMAGERY_IDENTIFY_URL}?${params.toString()}`, { signal: controller.signal })
      .then((resp) => {
        if (!resp.ok) throw new Error(`Esri returned HTTP ${resp.status}`);
        return resp.json();
      })
      .then((body) => {
        // ArcGIS reports its own failures with HTTP 200 and an `error` object,
        // so resp.ok is not enough.
        if (body.error) throw new Error(body.error.message || 'Esri rejected the query');
        const best = pickBestImageryResult(body.results, mapInstance.getZoom());
        if (!best) throw new Error('Esri publishes no capture date for this point');
        return best;
      })
      .catch((e) => {
        if (e.name === 'AbortError') throw new Error('Esri did not respond within 10s');
        throw e;
      })
      .then(
        (v) => { clearTimeout(timeout); return v; },
        (e) => { clearTimeout(timeout); throw e; }
      );
  }

  function imageryInfoHtml(info, latlng) {
    const rows = [
      ['Captured', info.date],
      ['Source', [info.product, info.source].filter(Boolean).join(' · ') || null],
      ['Sensor', info.sensor],
      ['Resolution', info.resolution != null ? `${info.resolution} m/pixel` : null],
      ['Accuracy', info.accuracy != null ? `± ${info.accuracy} m` : null],
    ].filter((row) => row[1]);

    return `
          <div class="imagery-info">
            <strong>Satellite imagery</strong>
            <table>${rows.map((row) =>
              `<tr><th>${escapeHtml(row[0])}</th><td>${escapeHtml(String(row[1]))}</td></tr>`).join('')}</table>
            <span class="imagery-coords">${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)}</span>
          </div>`;
  }

  function showImageryInfo(latlng) {
    const popup = L.popup({ className: 'imagery-popup', maxWidth: 280 })
      .setLatLng(latlng)
      .setContent('<div class="imagery-info">Checking imagery date…</div>')
      .openOn(mapInstance);

    identifyImagery(latlng)
      .then((info) => {
        // The dispatcher may have clicked elsewhere or closed this while the
        // request was out; writing into a dead popup would reopen nothing but
        // could resurrect stale content if Leaflet is mid-teardown.
        if (popup.isOpen()) popup.setContent(imageryInfoHtml(info, latlng));
      })
      .catch((err) => {
        if (!popup.isOpen()) return;
        popup.setContent(
          `<div class="imagery-info"><strong>Imagery date unavailable</strong>` +
          `<span class="imagery-error">${escapeHtml(err.message)}</span></div>`
        );
      });
  }

  function statusColor(status) {
    const map = {
      completed: '#2ea043',
      current: '#fb923c',
      arrived: '#fb923c',
      planned: '#9ca3af',
      skipped: '#eab308',
      cancelled: '#ef4444',
    };
    return map[status] || '#9ca3af';
  }

  function vehiclePopupHtml(a, label, status, lat, lng) {
    const stopName = a.current_stop ? (a.current_stop.station_name || a.current_stop.station_code || 'Stop #' + a.current_stop.planned_sequence) : 'No active stop';
    const progress = a.progress || {};
    const speedKmh = a.gps && a.gps.speed_kmh != null ? a.gps.speed_kmh : null;
    return `
          <div style="font-size:12px;min-width:160px;">
            <strong>${escapeHtml(label)}</strong><br/>
            Driver: ${escapeHtml(a.current_driver || 'N/A')}<br/>
            Status: <span style="color:${statusColor(status)};font-weight:600;">${escapeHtml(status)}</span><br/>
            Stop: ${escapeHtml(stopName)}<br/>
            Progress: ${progress.completed || 0}/${progress.total || 0}<br/>
            ${speedKmh != null ? 'Speed: ' + Math.round(speedKmh) + ' km/h<br/>' : ''}
            GPS: ${lat.toFixed(5)}, ${lng.toFixed(5)}
          </div>`;
  }

  function stopPopupHtml(s, execStatus) {
    return `
          <div style="font-size:12px;min-width:160px;">
            <strong>#${s.execution_sequence || s.planned_sequence} ${escapeHtml(s.station_name || '')}</strong><br/>
            ${s.station_code ? 'Code: ' + escapeHtml(s.station_code) + '<br/>' : ''}
            Status: <span style="font-weight:600;">${escapeHtml(execStatus)}</span><br/>
            ${s.product_description ? 'Product: ' + escapeHtml(s.product_description) + '<br/>' : ''}
            ${s.manager_name ? 'Contact: ' + escapeHtml(s.manager_name) + '<br/>' : ''}
          </div>`;
  }

  DASH.map = {
    init() {
      if (mapInstance) return;

      mapInstance = L.map('dashboardMap', {
        zoomControl: true,
        center: [10.8231, 106.6297],
        zoom: 11,
      });

      addBasemaps(mapInstance);

      // Marker clicks don't reach the map in Leaflet, so this can't fire from
      // clicking a vehicle or a stop.
      mapInstance.on('click', (e) => {
        if (activeBasemap !== 'Satellite') return;
        // While the ruler is armed a click means "drop a pin"; without this
        // every measuring click on satellite would also fire an Esri identify
        // and open an imagery popup over the point just measured.
        if (DASH.measure && DASH.measure.isActive()) return;
        showImageryInfo(e.latlng);
      });

      // Shift+right-click asks "what does this place look like?" of any point,
      // not just a stop. Plain right-click still arms the measure ruler;
      // measure.js returns early on shiftKey so exactly one of the two fires.
      //
      // Unlike the imagery-identify click above this is not gated on the
      // active basemap — street-level coverage has nothing to do with which
      // tiles are drawn underneath.
      mapInstance.on('contextmenu', (e) => {
        if (!e || !e.originalEvent || !e.originalEvent.shiftKey) return;
        if (L.DomEvent) L.DomEvent.preventDefault(e.originalEvent);
        if (DASH.streetview) DASH.streetview.openAt(e.latlng.lat, e.latlng.lng);
      });

      vehicleMarkerLayer = L.layerGroup().addTo(mapInstance);
      stopMarkerLayer = L.layerGroup().addTo(mapInstance);
      routeLayer = L.layerGroup().addTo(mapInstance);
    },

    // Diffs against the previously-rendered vehicle markers instead of
    // clearLayers()+recreate every poll — preserves marker identity, any
    // open popup, and avoids rebinding click handlers every 12s.
    updateVehicles(assignments) {
      if (!mapInstance) return;
      const seen = new Set();

      (assignments || []).forEach((a) => {
        const gps = a.gps;
        if (!gps || gps.lat == null || gps.lng == null) return;
        const lat = parseFloat(gps.lat);
        const lng = parseFloat(gps.lng);
        if (isNaN(lat) || isNaN(lng)) return;

        seen.add(a.assignment_id);

        const isSelected = a.assignment_id === DASH.state.selectedAssignmentId;
        const label = a.plate_number || 'V' + a.assignment_id;
        const status = a.plan_status || 'confirmed';
        const borderColor = isSelected ? '#fb923c' : statusColor(status);
        const popupHtml = vehiclePopupHtml(a, label, status, lat, lng);

        let entry = vehicleMarkers[a.assignment_id];
        if (!entry) {
          const icon = L.divIcon({
            className: '',
            html: `<div class="vehicle-marker-label" style="border-color:${borderColor};">${escapeHtml(label)}</div>`,
            iconSize: [0, 0],
            iconAnchor: [0, 0],
          });
          const marker = L.marker([lat, lng], { icon }).addTo(vehicleMarkerLayer);
          marker.bindPopup(popupHtml);
          marker.on('click', () => {
            DASH.state.selectAssignment(a.assignment_id);
          });
          const el = marker.getElement();
          const labelEl = el ? el.querySelector('.vehicle-marker-label') : null;
          vehicleMarkers[a.assignment_id] = { marker, labelEl, label, borderColor, lat, lng, popupHtml };
          return;
        }

        if (entry.lat !== lat || entry.lng !== lng) {
          withoutAutoPan(entry.marker, () => entry.marker.setLatLng([lat, lng]));
          entry.lat = lat;
          entry.lng = lng;
        }

        if (entry.label !== label || entry.borderColor !== borderColor) {
          if (entry.labelEl) {
            entry.labelEl.textContent = label;
            entry.labelEl.style.borderColor = borderColor;
          }
          entry.label = label;
          entry.borderColor = borderColor;
        }

        if (entry.popupHtml !== popupHtml) {
          withoutAutoPan(entry.marker, () => {
            const popup = entry.marker.getPopup();
            if (popup) popup.setContent(popupHtml);
          });
          entry.popupHtml = popupHtml;
        }
      });

      // Remove markers for assignments no longer in the list (filtered out, completed, etc.)
      Object.keys(vehicleMarkers).forEach((key) => {
        if (!seen.has(Number(key))) {
          vehicleMarkerLayer.removeLayer(vehicleMarkers[key].marker);
          delete vehicleMarkers[key];
        }
      });
    },

    // Full rebuild only when the set of stop ids changes (assignment
    // switched, or a stop was inserted/removed); a same-assignment poll
    // only patches status/current-marker/popup on existing markers.
    updateStops(stops, currentStopId) {
      if (!mapInstance) return;
      const list = stops || [];
      const key = list.map((s) => s.id).join(',');

      if (key !== stopsSetKey) {
        stopMarkerLayer.clearLayers();
        stopMarkers.clear();
        stopsSetKey = key;

        list.forEach((s) => {
          if (!s.lat || !s.lng) return;
          const lat = parseFloat(s.lat);
          const lng = parseFloat(s.lng);
          if (isNaN(lat) || isNaN(lng)) return;

          const execStatus = s.execution_status || 'planned';
          const isCurrent = currentStopId && s.id === currentStopId;
          const cssClass = isCurrent ? 'stop-marker-icon current' : 'stop-marker-icon ' + execStatus;
          const popupHtml = stopPopupHtml(s, execStatus);

          const icon = L.divIcon({
            className: '',
            html: `<div class="${cssClass}" title="${escapeHtml(s.station_name || 'Stop')}"></div>`,
            iconSize: [14, 14],
            iconAnchor: [7, 7],
          });
          const marker = L.marker([lat, lng], { icon }).addTo(stopMarkerLayer);
          marker.bindPopup(popupHtml);
          const el = marker.getElement();
          const iconEl = el ? el.querySelector('.stop-marker-icon') : null;
          stopMarkers.set(s.id, { marker, iconEl, cssClass, popupHtml });
        });
        return;
      }

      list.forEach((s) => {
        const entry = stopMarkers.get(s.id);
        if (!entry) return; // stop had no coords originally, nothing to patch

        const execStatus = s.execution_status || 'planned';
        const isCurrent = currentStopId && s.id === currentStopId;
        const cssClass = isCurrent ? 'stop-marker-icon current' : 'stop-marker-icon ' + execStatus;
        const popupHtml = stopPopupHtml(s, execStatus);

        if (entry.cssClass !== cssClass) {
          if (entry.iconEl) entry.iconEl.className = cssClass;
          entry.cssClass = cssClass;
        }
        if (entry.popupHtml !== popupHtml) {
          withoutAutoPan(entry.marker, () => {
            const popup = entry.marker.getPopup();
            if (popup) popup.setContent(popupHtml);
          });
          entry.popupHtml = popupHtml;
        }
      });
    },

    // Draws the actual road route from /api/eta's per-leg ORS geometry
    // instead of a straight line through stop coordinates. Falls back to a
    // straight segment only for legs where road geometry wasn't available
    // (no ORS key, or that leg fell back to haversine), and to the old
    // all-stops straight line only when there's no live ETA/GPS at all.
    // Skips the rebuild entirely when the resulting path hasn't changed.
    updateRoute(eta, stops) {
      if (!mapInstance) return;

      const legs = (eta && eta.etas) || [];
      let coords = [];
      let usedRoadGeometry = false;

      // One entry per leg rather than a single joined polyline, because a leg
      // routed in violation of the vehicle's limits has to be drawn
      // differently from the rest of the same route.
      const segments = [];

      if (legs.length > 0) {
        let prevLat = eta.gps ? eta.gps.lat : null;
        let prevLng = eta.gps ? eta.gps.lng : null;

        legs.forEach((leg) => {
          let legCoords = null;
          if (leg.geometry && leg.geometry.length > 0) {
            legCoords = leg.geometry;
            coords = coords.concat(leg.geometry);
            usedRoadGeometry = true;
          } else if (prevLat != null && prevLng != null && leg.lat != null && leg.lng != null) {
            legCoords = [[prevLat, prevLng], [parseFloat(leg.lat), parseFloat(leg.lng)]];
            coords.push(legCoords[0], legCoords[1]);
          }
          if (legCoords) {
            segments.push({
              coords: legCoords,
              violated: leg.restriction_status === 'violated',
              road: !!(leg.geometry && leg.geometry.length > 0),
            });
          }
          if (leg.lat != null && leg.lng != null) {
            prevLat = parseFloat(leg.lat);
            prevLng = parseFloat(leg.lng);
          }
        });
      } else {
        // No live ETA available (GPS offline, etc.) — preserve the old
        // straight-line-through-all-stops behavior rather than showing nothing.
        (stops || []).forEach((s) => {
          if (s.lat && s.lng) {
            const lat = parseFloat(s.lat);
            const lng = parseFloat(s.lng);
            if (!isNaN(lat) && !isNaN(lng)) coords.push([lat, lng]);
          }
        });
      }

      // Status is part of the key: the same geometry can flip between
      // compliant and violated when a vehicle's specs are edited, and a
      // geometry-only key would leave the old colour on screen.
      const statusKey = segments.map((s) => (s.violated ? '1' : '0')).join('');
      const key = coords.map((c) => c[0] + ',' + c[1]).join('|') + '#' + statusKey;
      if (key === lastRouteKey) return;
      lastRouteKey = key;

      routeLayer.clearLayers();
      if (coords.length < 2) return;

      if (segments.length === 0) {
        L.polyline(coords, {
          color: '#388bfd',
          weight: 3,
          opacity: 0.7,
          dashArray: usedRoadGeometry ? '' : '8, 8',
        }).addTo(routeLayer);
        return;
      }

      segments.forEach((seg) => {
        if (seg.coords.length < 2) return;
        if (seg.violated) {
          // A white casing under the red keeps it legible on both the
          // satellite and the near-white street basemaps — the same reason
          // the vehicle markers carry two rings.
          L.polyline(seg.coords, {
            color: '#ffffff', weight: 7, opacity: 0.85,
          }).addTo(routeLayer);
          L.polyline(seg.coords, {
            color: '#f85149',
            weight: 4,
            opacity: 0.95,
            dashArray: seg.road ? '' : '8, 8',
          }).addTo(routeLayer);
        } else {
          L.polyline(seg.coords, {
            color: '#388bfd',
            weight: 3,
            opacity: 0.7,
            dashArray: seg.road ? '' : '8, 8',
          }).addTo(routeLayer);
        }
      });
    },

    zoomToVehicle(assignmentId) {
      const entry = vehicleMarkers[assignmentId];
      if (entry && mapInstance) {
        mapInstance.setView(entry.marker.getLatLng(), 14);
        entry.marker.openPopup();
        currentZoomAssignment = assignmentId;
      }
    },

    // Centres the map on one stop and opens its popup. Returns false when the
    // stop has no marker — a stop with no coordinates never got one — so the
    // caller can say so rather than leaving a click that silently did nothing.
    //
    // Zooms in only if the view is currently further out than 15. A dispatcher
    // who has deliberately zoomed to street level keeps that level; one looking
    // at the whole city gets pulled in close enough for the stop to mean
    // something.
    focusStop(stopId) {
      const entry = stopMarkers.get(stopId);
      if (!entry || !mapInstance) return false;
      mapInstance.setView(entry.marker.getLatLng(), Math.max(mapInstance.getZoom(), 15));
      entry.marker.openPopup();
      return true;
    },

    // Re-centers on the vehicle without forcing zoom or popping its popup
    // open — used every poll while "Follow" is active, so it stays gentle
    // rather than fighting a dispatcher who's manually zoomed/panned.
    followVehicle(assignmentId) {
      const entry = vehicleMarkers[assignmentId];
      if (entry && mapInstance) {
        mapInstance.panTo(entry.marker.getLatLng());
      }
    },

    zoomToAll() {
      if (!mapInstance) return;
      const allMarkers = Object.values(vehicleMarkers).map((e) => e.marker);
      if (allMarkers.length === 0) return;
      const group = L.featureGroup(allMarkers);
      mapInstance.fitBounds(group.getBounds().pad(0.1));
    },

    openGoogleMaps(assignmentId, stops) {
      const entry = vehicleMarkers[assignmentId];
      if (!entry) return;
      const latlng = entry.marker.getLatLng();
      const query = stops && stops.length > 0
        ? stops.map(s => `${s.lat},${s.lng}`).join('/')
        : `${latlng.lat},${latlng.lng}`;
      window.open(`https://www.google.com/maps/dir/${latlng.lat},${latlng.lng}/${query}`, '_blank');
    },

    getMap() { return mapInstance; },

    invalidateSize() {
      if (mapInstance) setTimeout(() => mapInstance.invalidateSize(), 100);
    },
  };
})();
