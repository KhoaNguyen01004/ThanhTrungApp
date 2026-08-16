// ================================================================
// Dispatch Dashboard — Street View Module
// ================================================================
// A walkable street-level view of the road network, not just a photo of a
// stop. Most of this fleet's stops are down lanes and yards no Mapillary
// driver ever entered, so a lookup pinned to the stop coordinate usually finds
// nothing — the useful imagery is on the arterial road the lane comes off,
// which is how a driver actually approaches. So the viewer opens wherever
// there IS coverage and lets the dispatcher walk from there to the gate.
//
// Reached three ways:
//   - Street view button on a timeline stop
//   - shift+right-click anywhere on the map
//   - clicking the green coverage overlay (map.js owns that layer)
//
// Navigation is MapillaryJS's own: on-screen arrows, arrow keys, and clicking
// into the distance. This module adds the piece MapillaryJS cannot know about
// — a marker on the Leaflet map showing where the viewer currently stands and
// which way it faces, so walking down a street is legible on the map at the
// same time.
//
// MapillaryJS is optional at runtime. If the CDN is unreachable the module
// falls back to Mapillary's embed iframe, which still shows the image and
// still allows some navigation, rather than the panel failing outright.
//
// Owns its own DOM and its own map layer, and never moves the map view except
// through followViewer(), which is opt-in and off by default. Opening street
// view for a stop must not drag the view off a truck being watched elsewhere.
window.DASH = window.DASH || {};

(function () {
  'use strict';

  const escapeHtml = UI.escapeHtml;

  let panelEl = null;
  let viewerEl = null;
  let overlayEl = null;
  let titleEl = null;
  let metaEl = null;

  let viewer = null;        // MapillaryJS Viewer, built lazily on first open
  let viewerFailed = false; // CDN missing or construction threw — use the iframe
  let open = false;
  let follow = false;       // map re-centres on the viewer as it walks
  let expanded = false;

  let mapInstance = null;
  let positionLayer = null;
  let positionMarker = null;

  // Incremented on every open and close. A lookup that resolves after the
  // dispatcher has moved on would otherwise repaint a panel showing somewhere
  // else, so every async continuation checks its token first.
  let requestToken = 0;

  function token() {
    return (window.DASH_CONFIG && window.DASH_CONFIG.mapillaryToken) || '';
  }

  function mapillaryAvailable() {
    return !viewerFailed && typeof window.mapillary !== 'undefined'
      && window.mapillary && typeof window.mapillary.Viewer === 'function'
      && !!token();
  }

  // ── Formatting ─────────────────────────────────────────────────
  function formatCaptured(ms) {
    if (ms == null) return null;
    const date = new Date(ms);
    if (isNaN(date.getTime())) return null;
    return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short' });
  }

  function ageYears(ms) {
    if (ms == null) return null;
    const years = (Date.now() - ms) / (365.25 * 24 * 3600 * 1000);
    return years < 0 ? null : years;
  }

  function formatDistance(m) {
    if (m == null) return null;
    return m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(1)} km`;
  }

  // ── Overlay messages ───────────────────────────────────────────
  // Layered over the viewer rather than replacing it: rebuilding the container
  // would destroy MapillaryJS's WebGL context on every miss.
  function showOverlay(text, kind) {
    if (!overlayEl) return;
    overlayEl.innerHTML =
      `<div class="sv-message${kind ? ' sv-' + kind : ''}">${escapeHtml(text)}</div>`;
    overlayEl.style.display = '';
  }

  function hideOverlay() {
    if (!overlayEl) return;
    overlayEl.style.display = 'none';
    overlayEl.innerHTML = '';
  }

  function setMeta(html) {
    if (metaEl) metaEl.innerHTML = html || '';
  }

  // ── Position marker on the Leaflet map ─────────────────────────
  // The half of "walking around" that a viewer alone cannot give: without it
  // the dispatcher is looking at a street with no idea which street it is.
  function ensurePositionLayer() {
    if (positionLayer || !DASH.map || typeof DASH.map.getMap !== 'function') return;
    mapInstance = DASH.map.getMap();
    if (!mapInstance) return;
    // Its own layer group, so the 12-second poll never touches it — the same
    // arrangement measure.js uses for the ruler.
    positionLayer = L.layerGroup().addTo(mapInstance);
  }

  function updatePositionMarker(lat, lng, bearing) {
    ensurePositionLayer();
    if (!positionLayer) return;

    const rotation = typeof bearing === 'number' && isFinite(bearing) ? bearing : 0;
    // Two rings, per the dashboard marker convention: the basemap is
    // switchable between satellite and a near-white street map, and a
    // single-colour marker disappears on one of them whichever colour is used.
    const icon = L.divIcon({
      className: '',
      html: `<div class="sv-position" style="transform:rotate(${rotation}deg);">
               <div class="sv-position-cone"></div>
               <div class="sv-position-dot"></div>
             </div>`,
      iconSize: [30, 30],
      iconAnchor: [15, 15],
    });

    if (!positionMarker) {
      positionMarker = L.marker([lat, lng], { icon, zIndexOffset: 900 }).addTo(positionLayer);
    } else {
      positionMarker.setLatLng([lat, lng]);
      positionMarker.setIcon(icon);
    }

    // Follow is opt-in and defaults off, for the same reason the vehicle
    // Follow mode is: an automatic pan the dispatcher did not ask for is how
    // you lose the truck you were watching.
    if (follow && mapInstance) mapInstance.panTo([lat, lng]);
  }

  function clearPositionMarker() {
    if (positionMarker && positionLayer) positionLayer.removeLayer(positionMarker);
    positionMarker = null;
  }

  // ── Meta line ──────────────────────────────────────────────────
  function renderMeta(info) {
    const bits = [];
    const captured = formatCaptured(info.captured_at);

    if (captured) {
      // Three years is roughly where a Vietnamese street frontage has turned
      // over at least once. Flagged rather than hidden: an old photo still
      // shows the turning, it just no longer identifies the shop.
      const age = ageYears(info.captured_at);
      const stale = age != null && age >= 3;
      bits.push(
        `<span class="sv-captured${stale ? ' stale' : ''}"` +
        `${stale ? ' title="Old imagery — the frontage may have changed"' : ''}>` +
        `${escapeHtml(captured)}</span>`
      );
    }

    // Only shown for the initial lookup. Once the dispatcher walks, distance
    // from the original point stops meaning anything.
    if (info.distance_m != null) {
      const far = info.distance_m > 150;
      bits.push(
        `<span class="sv-distance${far ? ' far' : ''}"` +
        `${far ? ' title="Nearest imagery is some way from the point you asked about"' : ''}>` +
        `${escapeHtml(formatDistance(info.distance_m))} away</span>`
      );
    }

    if (info.is_pano) bits.push('360°');

    bits.push(
      `<label class="sv-follow"><input type="checkbox" data-sv-follow${follow ? ' checked' : ''}> Follow on map</label>`
    );

    if (info.page_url) {
      bits.push(
        `<a href="${escapeHtml(info.page_url)}" target="_blank" rel="noopener noreferrer">Mapillary ↗</a>`
      );
    }

    setMeta(bits.join(' <span class="sv-dot">·</span> '));

    const followBox = metaEl && metaEl.querySelector('[data-sv-follow]');
    if (followBox) {
      followBox.addEventListener('change', (e) => { follow = !!e.target.checked; });
    }
  }

  // ── The viewer ─────────────────────────────────────────────────
  function buildViewer() {
    if (viewer || !mapillaryAvailable() || !viewerEl) return viewer;
    try {
      viewer = new window.mapillary.Viewer({
        accessToken: token(),
        container: viewerEl,
        component: {
          // The in-viewer minimap is off: this page already has a map, and two
          // maps disagreeing about where you are is worse than one.
          cover: false,
        },
      });

      // Fired on every move, including each step the dispatcher walks. This is
      // what keeps the map marker in step with the viewer.
      viewer.on('image', async (event) => {
        try {
          const image = event.image;
          const lngLat = image.lngLat || image.computedLngLat;
          if (lngLat) {
            updatePositionMarker(lngLat.lat, lngLat.lng, image.compassAngle);
          }
          renderMeta({
            captured_at: image.capturedAt,
            is_pano: image.cameraType === 'spherical' || image.cameraType === 'equirectangular',
            page_url: `https://www.mapillary.com/app/?pKey=${encodeURIComponent(image.id)}&focus=photo`,
            distance_m: null,
          });
        } catch (e) {
          // A metadata shape change must not break navigation itself.
          if (window.console) console.warn('street view: image event', e);
        }
      });

      // Turning in place should swing the map cone too, otherwise the marker
      // lies about which way the dispatcher is looking.
      viewer.on('bearing', (event) => {
        if (!positionMarker) return;
        const el = positionMarker.getElement();
        const inner = el && el.querySelector('.sv-position');
        if (inner) inner.style.transform = `rotate(${event.bearing}deg)`;
      });
    } catch (e) {
      viewerFailed = true;
      viewer = null;
      if (window.console) console.warn('street view: MapillaryJS unavailable', e);
    }
    return viewer;
  }

  // Fallback when MapillaryJS did not load. Still navigable, just not as
  // smoothly, and with no position marker — the iframe cannot report where it
  // has walked to.
  function renderIframe(image) {
    if (!viewerEl) return;
    viewerEl.innerHTML =
      `<iframe class="sv-frame"
               src="${escapeHtml(image.embed_url)}"
               loading="lazy"
               referrerpolicy="no-referrer"
               sandbox="allow-scripts"
               title="Street-level imagery"></iframe>`;
    hideOverlay();
    renderMeta(image);
  }

  function showImage(image) {
    if (mapillaryAvailable() && buildViewer()) {
      hideOverlay();
      renderMeta(image);
      if (image.lat != null && image.lng != null) {
        updatePositionMarker(image.lat, image.lng, image.compass_angle);
      }
      viewer.moveTo(image.image_id).catch((e) => {
        showOverlay(`Could not open that image — ${e && e.message ? e.message : e}`, 'error');
      });
      // MapillaryJS sizes itself to its container at construction; the panel
      // was display:none then, so the first open needs a nudge.
      if (viewer.resize) setTimeout(() => viewer.resize(), 60);
      return;
    }
    renderIframe(image);
  }

  DASH.streetview = {
    init() {
      panelEl = document.getElementById('streetViewPanel');
      if (!panelEl) return;
      viewerEl = panelEl.querySelector('[data-sv-viewer]');
      overlayEl = panelEl.querySelector('[data-sv-overlay]');
      titleEl = panelEl.querySelector('[data-sv-title]');
      metaEl = panelEl.querySelector('[data-sv-meta]');

      const closeBtn = panelEl.querySelector('[data-sv-close]');
      if (closeBtn) closeBtn.addEventListener('click', () => this.close());

      const expandBtn = panelEl.querySelector('[data-sv-expand]');
      if (expandBtn) expandBtn.addEventListener('click', () => this.toggleExpand());

      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && open) this.close();
      });
    },

    isOpen() { return open; },

    isFollowing() { return follow; },

    toggleExpand() {
      expanded = !expanded;
      if (panelEl) panelEl.classList.toggle('expanded', expanded);
      // The viewer has to be told; it does not watch its container's size.
      if (viewer && viewer.resize) setTimeout(() => viewer.resize(), 60);
    },

    // Opens at a specific Mapillary image, skipping the lookup entirely. This
    // is what the coverage overlay uses — the dispatcher clicked an image, so
    // there is nothing to search for.
    openImage(imageId, label) {
      if (!panelEl || !imageId) return;
      open = true;
      requestToken++;
      panelEl.style.display = '';
      if (titleEl) titleEl.textContent = label || 'Street view';
      hideOverlay();
      showImage({ image_id: String(imageId), embed_url:
        `https://www.mapillary.com/embed?image_key=${encodeURIComponent(imageId)}&style=photo` });
    },

    // label is user-supplied (a station_name straight out of the manager's
    // Google Sheet), so it is escaped on the way in rather than trusted.
    openAt(lat, lng, label) {
      if (!panelEl) return;

      const latNum = parseFloat(lat);
      const lngNum = parseFloat(lng);
      if (isNaN(latNum) || isNaN(lngNum)) {
        UI.toast('That point has no coordinates, so there is nothing to look at', 'error', 4000);
        return;
      }

      open = true;
      const requestId = ++requestToken;
      panelEl.style.display = '';
      if (titleEl) {
        titleEl.textContent = label || `${latNum.toFixed(5)}, ${lngNum.toFixed(5)}`;
      }
      showOverlay('Looking for street-level imagery…');
      setMeta('');

      DASH.api.streetview(latNum, lngNum)
        .then((body) => {
          if (requestId !== requestToken) return;
          if (body && body.found && body.image && body.image.image_id) {
            showImage(body.image);
            return;
          }
          // Mapillary answered and there is nothing within reach. Stated
          // plainly and separately from a failure — if the two read the same,
          // an expired token looks like an uncovered city on every stop at
          // once and nobody notices anything is wrong.
          showOverlay(
            'No street-level imagery within 600 m. Try a main road nearby — the green coverage layer shows where imagery exists.',
            'empty'
          );
        })
        .catch((err) => {
          if (requestId !== requestToken) return;
          showOverlay(`Street view is unavailable right now — ${err.message}`, 'error');
        });
    },

    close() {
      open = false;
      // Bumped so an in-flight lookup cannot repaint a closed panel, nor the
      // next place it is reopened at.
      requestToken++;
      clearPositionMarker();
      if (!panelEl) return;
      panelEl.style.display = 'none';
      setMeta('');
      hideOverlay();
      // The iframe fallback keeps running while it is in the DOM, and it is
      // third-party. MapillaryJS is deliberately left alive: rebuilding its
      // WebGL context on every open is slow, and it renders nothing while its
      // container is hidden.
      if (viewerEl && !viewer) viewerEl.innerHTML = '';
    },
  };
})();
