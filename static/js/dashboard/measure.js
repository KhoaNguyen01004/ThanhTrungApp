// ================================================================
// Dispatch Dashboard — Distance Measure Module
// ================================================================
// Google-Maps-style ruler: right-click drops the first pin and arms the tool,
// left-click extends the path, pins can be dragged, Backspace undoes the last
// one, Escape (or the toolbar button, or another right-click) clears.
//
// Straight-line geodesic only, computed in the browser. Deliberately NOT road
// distance: a road figure means one OpenRouteService call per measurement,
// and the ETA panel already answers "how far along the actual route" for the
// selected vehicle. This tool answers a different question — "how far apart
// are those two points" — which is the one a dispatcher asks about a yard, a
// detour or a customer who hasn't been added to a plan yet.
//
// Owns its own layer group and never touches the map view, so a measurement
// survives the 12-second poll and nothing here can fight Follow mode.
window.DASH = window.DASH || {};

(function () {
  'use strict';

  const EARTH_RADIUS_M = 6371000; // matches app/utils/geo.py:get_distance_meters

  let mapInstance = null;
  let layer = null;          // everything this module draws, in one group
  let line = null;           // the dashed path itself
  let casing = null;         // white under-stroke, see the styling note below
  let points = [];           // [{ lat, lng, marker }] in click order
  let active = false;
  let readoutEl = null;
  let buttonEl = null;

  // ── Geometry ───────────────────────────────────────────────────
  // Haversine, same constant and same formula as the Python side, so a figure
  // read off the map and a figure computed server-side agree.
  function distanceMeters(a, b) {
    const phi1 = (a.lat * Math.PI) / 180;
    const phi2 = (b.lat * Math.PI) / 180;
    const dPhi = ((b.lat - a.lat) * Math.PI) / 180;
    const dLambda = ((b.lng - a.lng) * Math.PI) / 180;

    const h = Math.sin(dPhi / 2) ** 2
      + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
    return 2 * EARTH_RADIUS_M * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
  }

  // Whole metres below a kilometre — a 400 m yard-to-gate hop reads as "400 m",
  // not "0.4 km". Two decimals from 1 km up, because at one decimal the step
  // between 1.0 and 1.1 km hides 100 m, which is the difference between two
  // adjacent depots. One decimal past 10 km, where that precision is noise.
  function formatDistance(meters) {
    if (!isFinite(meters) || meters < 0) return '';
    if (meters < 1000) return `${Math.round(meters)} m`;
    const km = meters / 1000;
    return `${km < 10 ? km.toFixed(2) : km.toFixed(1)} km`;
  }

  // Cumulative distance from the first pin to each pin, index-aligned with
  // `points`. cumulative[0] is always 0.
  function cumulativeMeters() {
    const out = [0];
    for (let i = 1; i < points.length; i++) {
      out.push(out[i - 1] + distanceMeters(points[i - 1], points[i]));
    }
    return out;
  }

  function totalMeters() {
    const c = cumulativeMeters();
    return c.length ? c[c.length - 1] : 0;
  }

  // ── Rendering ──────────────────────────────────────────────────
  function pinIcon(index) {
    // Two rings, per the dashboard marker convention: the basemap is
    // user-switchable between satellite and a near-white street map, and a
    // single-colour dot vanishes on one of them whichever colour is picked.
    return L.divIcon({
      className: '',
      html: `<div class="measure-pin${index === 0 ? ' start' : ''}"></div>`,
      iconSize: [12, 12],
      iconAnchor: [6, 6],
    });
  }

  function labelFor(index, cumulative) {
    return index === 0 ? 'Start' : formatDistance(cumulative[index]);
  }

  function redraw() {
    if (!layer) return;

    const cumulative = cumulativeMeters();
    const coords = points.map((p) => [p.lat, p.lng]);

    points.forEach((p, i) => {
      if (p.marker.setIcon) p.marker.setIcon(pinIcon(i));
      if (p.marker.setTooltipContent) p.marker.setTooltipContent(labelFor(i, cumulative));
    });

    if (casing) { layer.removeLayer(casing); casing = null; }
    if (line) { layer.removeLayer(line); line = null; }

    if (coords.length >= 2) {
      casing = L.polyline(coords, { color: '#ffffff', weight: 6, opacity: 0.8 }).addTo(layer);
      line = L.polyline(coords, {
        color: '#fb923c',
        weight: 3,
        opacity: 0.95,
        dashArray: '6, 6',
      }).addTo(layer);
    }

    updateReadout();
  }

  function updateReadout() {
    if (!readoutEl) return;
    if (!active) {
      readoutEl.style.display = 'none';
      readoutEl.textContent = '';
      return;
    }
    readoutEl.style.display = '';
    if (points.length < 2) {
      readoutEl.textContent = 'Click to add points · Esc to finish';
      return;
    }
    const legs = points.length - 1;
    readoutEl.textContent =
      `${formatDistance(totalMeters())} · ${legs} leg${legs === 1 ? '' : 's'} · Esc to finish`;
  }

  function syncButton() {
    if (buttonEl) buttonEl.classList.toggle('active', active);
    const container = mapInstance && mapInstance.getContainer && mapInstance.getContainer();
    if (container && container.classList) container.classList.toggle('measuring', active);
  }

  // ── Points ─────────────────────────────────────────────────────
  function addPoint(latlng) {
    const lat = parseFloat(latlng.lat);
    const lng = parseFloat(latlng.lng);
    if (isNaN(lat) || isNaN(lng)) return;

    const index = points.length;
    const marker = L.marker([lat, lng], {
      icon: pinIcon(index),
      draggable: true,
      // Above the dashed line, below nothing else that matters — the pins are
      // what the dispatcher grabs, so they must win the hit test against the
      // path they sit on.
      zIndexOffset: 1000,
    }).addTo(layer);

    if (marker.bindTooltip) {
      marker.bindTooltip(labelFor(index, [0]), {
        permanent: true,
        direction: 'right',
        offset: [8, 0],
        className: 'measure-label',
      });
    }

    const entry = { lat, lng, marker };

    // Live feedback while dragging rather than on release: the point of
    // dragging a pin is to watch the number settle onto the spot you want.
    if (marker.on) {
      marker.on('drag', (e) => {
        const pos = (e && e.latlng) || (marker.getLatLng && marker.getLatLng());
        if (!pos) return;
        entry.lat = pos.lat;
        entry.lng = pos.lng;
        redraw();
      });
    }

    points.push(entry);
    redraw();
  }

  function removeLastPoint() {
    const entry = points.pop();
    if (entry && layer) layer.removeLayer(entry.marker);
    redraw();
  }

  // ── Keyboard ───────────────────────────────────────────────────
  // Backspace is a global key here, so it has to keep its normal meaning
  // inside the filter box and any other field on the page.
  function typingInField(e) {
    const el = (e && e.target) || null;
    if (!el) return false;
    if (el.isContentEditable) return true;
    const tag = (el.tagName || '').toUpperCase();
    return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
  }

  DASH.measure = {
    init() {
      if (!DASH.map || typeof DASH.map.getMap !== 'function') return;
      mapInstance = DASH.map.getMap();
      if (!mapInstance || layer) return;

      layer = L.layerGroup().addTo(mapInstance);
      readoutEl = document.getElementById('measureReadout');
      buttonEl = document.getElementById('measureBtn');

      mapInstance.on('contextmenu', (e) => {
        // Leaflet suppresses the browser menu itself once a contextmenu
        // listener exists, but only for events it routes; doing it here too
        // costs nothing and keeps the behaviour independent of that detail.
        if (e && e.originalEvent && L.DomEvent) L.DomEvent.preventDefault(e.originalEvent);
        // Shift+right-click belongs to street view (map.js). Without this
        // guard both handlers fire on the same event: the panel opens AND the
        // ruler arms, so the dispatcher's next click drops a measuring pin
        // they never asked for. Checked before the `active` branch on purpose
        // — a shift+right-click during an active measurement must open street
        // view without discarding the measurement.
        if (e && e.originalEvent && e.originalEvent.shiftKey) return;
        if (active) {
          this.clear();
          return;
        }
        active = true;
        syncButton();
        addPoint(e.latlng);
      });

      // map.js's imagery-identify handler returns early while this is active,
      // so a measuring click doesn't also open an Esri popup.
      mapInstance.on('click', (e) => {
        if (!active) return;
        addPoint(e.latlng);
      });

      if (buttonEl) {
        buttonEl.addEventListener('click', () => this.toggle());
      }

      document.addEventListener('keydown', (e) => {
        if (!active) return;
        if (e.key === 'Backspace' && !typingInField(e)) {
          e.preventDefault();
          if (points.length <= 1) this.clear();
          else removeLastPoint();
        }
      });

      updateReadout();
    },

    isActive() { return active; },

    pointCount() { return points.length; },

    toggle() {
      if (active) {
        this.clear();
        return;
      }
      // Armed with no pins yet: the next left-click starts the path, which is
      // what a touch user gets instead of the right-click gesture.
      active = true;
      syncButton();
      updateReadout();
    },

    // Exits measure mode and removes everything. The one teardown path —
    // Escape, the button, a second right-click and a vehicle change all end
    // up here, so there is no state where pins outlive the mode.
    clear() {
      points.forEach((p) => { if (layer) layer.removeLayer(p.marker); });
      points = [];
      if (casing && layer) layer.removeLayer(casing);
      if (line && layer) layer.removeLayer(line);
      casing = null;
      line = null;
      active = false;
      syncButton();
      updateReadout();
    },

    // Called by main.js when the dispatcher selects a *different* vehicle.
    // Re-selecting the same one leaves the measurement alone: clicking a truck
    // icon on the map is easy to do by accident while measuring, and losing
    // the path to a click that changed nothing else would be infuriating.
    onVehicleChange() {
      if (active || points.length) this.clear();
    },

    // Exposed for the test suite and for any future caller that needs the
    // same geodesic the pins are measured with.
    distanceMeters,
    formatDistance,
    totalMeters,
  };
})();
