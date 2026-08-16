
// ── API_BASE & ApiClient ─────────────────────────────────────────
const API_BASE = '/api';

const ApiClient = {
    BASE: API_BASE,

    async fetch(url, opts = {}) {
        const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
        const resp = await fetch(this.BASE + url, { ...opts, headers });

        const data = await resp.json();
        if (!data.success) {
            // Carry the structured body on the Error so callers can act on it
            // (e.g. an `unknown_vehicle` rejection needs `redirect_to` and the
            // prefill fields, not just the message). Existing callers that
            // only read err.message are unaffected.
            const err = new Error(data.message || 'Unknown error');
            err.data = data;
            err.status = resp.status;
            throw err;
        }
        return data;
    },

    async get(path) { return this.fetch(path, { method: 'GET' }); },
    async post(path, body) { return this.fetch(path, { method: 'POST', body: JSON.stringify(body) }); },
    async put(path, body) { return this.fetch(path, { method: 'PUT', body: JSON.stringify(body) }); },
    async del(path) { return this.fetch(path, { method: 'DELETE' }); },
};

// ── UI namespace: toast notifications & HTML escaping ────────────
const UI = {
    /**
     * Show a toast notification. Reuses the page's `#toast-container`
     * element if present (adding the `.toast-container` class needed
     * for fixed positioning), otherwise creates one on first use.
     *
     * `options.actionLabel` + `options.onAction` add a single inline button
     * to the toast — used for undo, where the offer has to appear without
     * interrupting whatever the dispatcher does next. Clicking it dismisses
     * the toast immediately, and the toast still expires on its own if it is
     * ignored. Omitting them leaves the toast exactly as it was, so existing
     * three-argument callers are unaffected.
     */
    toast(message, type = 'info', duration = 3000, options = {}) {
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            document.body.appendChild(container);
        }
        // Only apply the shared positioning class if the page hasn't already
        // given this element its own fixed-position styling (e.g. a
        // page-specific `#toast-container` CSS rule) — avoids mixing a
        // `top` from the shared class with a page-specific `bottom`.
        if (getComputedStyle(container).position !== 'fixed') {
            container.classList.add('toast-container');
        }

        const el = document.createElement('div');
        el.className = `toast ${type}`;
        el.textContent = message;
        container.appendChild(el);

        let dismissTimer = null;
        const dismiss = () => {
            if (dismissTimer) clearTimeout(dismissTimer);
            // The node lingers for the fade. Without this an action button
            // stays clickable while invisible, so a second impatient tap on
            // Undo fires a second request at a stop that has already moved.
            el.style.pointerEvents = 'none';
            el.style.transition = 'opacity 0.35s ease, transform 0.35s ease';
            el.style.opacity = '0';
            el.style.transform = 'translateX(100%)';
            setTimeout(() => el.remove(), 350);
        };

        // textContent above already cleared the node, so the button is
        // appended rather than built into an innerHTML string — the message
        // never reaches an HTML parser.
        if (options && options.actionLabel && typeof options.onAction === 'function') {
            const btn = document.createElement('button');
            btn.className = 'toast-action';
            btn.type = 'button';
            btn.textContent = options.actionLabel;
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                dismiss();
                options.onAction();
            });
            el.appendChild(btn);
        }

        dismissTimer = setTimeout(dismiss, duration);
    },

    /**
     * Escape a value for safe insertion into HTML (text or attribute context).
     */
    escapeHtml(value) {
        const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
        return String(value == null ? '' : value).replace(/[&<>"']/g, (ch) => map[ch]);
    },

    /**
     * Clock time of arrival from a remaining duration in seconds — "14:35".
     *
     * Dispatchers work against the clock, not a stopwatch: "arrives 14:35" is
     * directly comparable to a delivery window, a site's closing time or a
     * driver's shift end, where "in 47 min" has to be added to the current
     * time first, and is wrong again by the time you look back at it.
     *
     * Returns null for anything that isn't a usable duration, so callers keep
     * showing a placeholder rather than a confident wrong time — a null ETA
     * once rendered as "0 min", i.e. "arriving now" (audit L-10).
     */
    etaClock(seconds, fromMs) {
        if (typeof seconds !== 'number' || !isFinite(seconds) || seconds < 0) return null;
        const now = new Date();
        // `seconds` is "from when the server answered", not "from now". Adding
        // it to the current time pushes the arrival later on every repaint,
        // which the 15s age ticker would otherwise do four times a minute.
        // Callers pass the moment the ETA landed; without one this falls back
        // to now, which is right on the first paint and drifts after.
        const base = typeof fromMs === 'number' && isFinite(fromMs) ? fromMs : now.getTime();
        const arrival = new Date(base + seconds * 1000);
        const time = arrival.toLocaleTimeString([], {
            hour: '2-digit', minute: '2-digit', hour12: false,
        });
        // A route running past midnight would otherwise show a time earlier
        // than now, which reads as "already late" rather than "tomorrow".
        const days = Math.round(
            (new Date(arrival).setHours(0, 0, 0, 0) - new Date(now).setHours(0, 0, 0, 0)) / 86400000
        );
        return days > 0 ? `${time} +${days}d` : time;
    },

    /**
     * The same duration as a span — "47 min", "2h 15m". Kept for tooltips
     * beside etaClock(), where "how long from now" is still the faster read.
     */
    etaRelative(seconds) {
        if (typeof seconds !== 'number' || !isFinite(seconds) || seconds < 0) return null;
        const mins = Math.round(seconds / 60);
        if (mins < 60) return `${mins} min`;
        const h = Math.floor(mins / 60);
        const m = mins % 60;
        return m ? `${h}h ${m}m` : `${h}h`;
    },
};

// ── Backward-compatible global aliases ────────────────────────────
// Kept for pages not yet migrated to the UI namespace. As of 2026-08-03 that
// is `locations.js` alone — trip-history.js and manage-trips.js were named
// here until they were deleted with the trip pages on 2026-07-31.
// `delivery-plan-builder.js` is not a caller: it defines its own local
// showToast() and so shadows this one rather than using it.
function showToast(message, type = 'info', duration = 3000) {
    UI.toast(message, type, duration);
}

// ── Shared date/number formatting utilities ───────────────────────
function todayISO() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function formatDate(iso) {
    if (!iso) return '—';
    const [y, m, d] = iso.split('-');
    return `${d}/${m}/${y}`;
}

function fmtNum(n) {
    return (n == null || isNaN(n)) ? '0' : Number(n).toLocaleString('en-US');
}

/**
 * Calculate centroid of a single polygon
 * @param {Array<Array<number>>} polygon - Array of [lat, lng] points
 * @returns {Array<number>|null} Centroid as [lat, lng], or null if invalid
 */
function calculatePolygonCentroid(polygon) {
    if (!polygon || polygon.length < 3) {
        return null;
    }

    // Ensure polygon is closed
    const closedPolygon = [...polygon, polygon[0]];
    let signedArea = 0;
    let sumLat = 0;
    let sumLng = 0;

    for (let i = 0; i < closedPolygon.length - 1; i++) {
        const [latI, lngI] = closedPolygon[i];
        const [latJ, lngJ] = closedPolygon[i + 1];
        const term = (latI * lngJ) - (latJ * lngI);
        signedArea += term;
        sumLat += (latI + latJ) * term;
        sumLng += (lngI + lngJ) * term;
    }

    signedArea /= 2;

    if (Math.abs(signedArea) < 1e-10) {
        // Degenerate polygon, return average of vertices
        const avgLat = polygon.reduce((sum, p) => sum + p[0], 0) / polygon.length;
        const avgLng = polygon.reduce((sum, p) => sum + p[1], 0) / polygon.length;
        return [avgLat, avgLng];
    }

    const centroidLat = sumLat / (6 * signedArea);
    const centroidLng = sumLng / (6 * signedArea);
    return [centroidLat, centroidLng];
}

/**
 * Calculate centroid of a multi-polygon (multiple polygons)
 * Returns weighted average of all polygon centroids
 * @param {Array<Array<Array<number>>>} polygons - Array of polygons, each is array of [lat, lng]
 * @returns {Array<number>|null} Centroid as [lat, lng], or null if invalid
 */
function calculateMultiPolygonCentroid(polygons) {
    if (!polygons || !Array.isArray(polygons) || polygons.length === 0) {
        return null;
    }

    const centroids = [];
    const areas = [];

    for (const polygon of polygons) {
        const centroid = calculatePolygonCentroid(polygon);
        if (centroid) {
            centroids.push(centroid);
            // Calculate area for weighting
            let area = 0;
            const closedPoly = [...polygon, polygon[0]];
            for (let i = 0; i < closedPoly.length - 1; i++) {
                const [latI, lngI] = closedPoly[i];
                const [latJ, lngJ] = closedPoly[i + 1];
                area += (latI * lngJ) - (latJ * lngI);
            }
            areas.push(Math.abs(area / 2));
        }
    }

    if (centroids.length === 0) {
        return null;
    }

    const totalArea = areas.reduce((sum, a) => sum + a, 0);
    if (totalArea === 0) {
        // All degenerate, just average centroids
        const avgLat = centroids.reduce((sum, c) => sum + c[0], 0) / centroids.length;
        const avgLng = centroids.reduce((sum, c) => sum + c[1], 0) / centroids.length;
        return [avgLat, avgLng];
    }

    let weightedLat = 0;
    let weightedLng = 0;
    for (let i = 0; i < centroids.length; i++) {
        const weight = areas[i] / totalArea;
        weightedLat += centroids[i][0] * weight;
        weightedLng += centroids[i][1] * weight;
    }

    return [weightedLat, weightedLng];
}

/**
 * Get centroid from a location object (handles single polygon, multi-polygon, or point)
 * @param {Object} location - Location object with polygons, corners, or lat/lng
 * @returns {Object|null} { lat: number, lng: number }
 */
function getLocationCentroid(location) {
    if (!location) return null;
    if (location.polygons && Array.isArray(location.polygons)) {
        const centroid = calculateMultiPolygonCentroid(location.polygons);
        if (centroid) return { lat: centroid[0], lng: centroid[1] };
    }
    if (location.corners && Array.isArray(location.corners)) {
        const centroid = calculatePolygonCentroid(location.corners);
        if (centroid) return { lat: centroid[0], lng: centroid[1] };
    }
    if (location.latitude !== undefined && location.longitude !== undefined) {
        return { lat: location.latitude, lng: location.longitude };
    }
    return null;
}

/**
 * Check if a point is inside a polygon or multi-polygon using Ray Casting algorithm
 * @param {number} lat - Point latitude
 * @param {number} lng - Point longitude
 * @param {Object} location - Location object with polygons or corners
 * @returns {boolean} True if point is inside the location's polygon(s)
 */
function isPointInLocation(lat, lng, location) {
    if (!location) return false;
    let polygonsToCheck = [];
    if (location.polygons && Array.isArray(location.polygons)) {
        polygonsToCheck = location.polygons;
    } else if (location.corners && Array.isArray(location.corners)) {
        polygonsToCheck = [location.corners];
    } else if (location.latitude !== undefined && location.longitude !== undefined) {
        const distance = getDistanceMeters(
            location.latitude, location.longitude,
            lat, lng
        );
        const locRadius = (location.radius_km || 3) * 1000;
        return distance <= locRadius;
    } else {
        return false;
    }
    
    for (const polygon of polygonsToCheck) {
        if (isPointInPolygon(lat, lng, polygon)) {
            return true;
        }
    }
    return false;
}

function getDistanceMeters(lat1, lon1, lat2, lon2) {
    const toRad = (deg) => (deg * Math.PI) / 180;
    const R = 6371000;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = Math.sin(dLat / 2) ** 2 +
        Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
}

/**
 * Check if a point is inside a single polygon using Ray Casting algorithm
 * @param {number} lat - Point latitude
 * @param {number} lng - Point longitude
 * @param {Array<Array<number>>} polygon - Polygon as array of [lat, lng]
 * @returns {boolean} True if point is inside polygon
 */
function isPointInPolygon(lat, lng, polygon) {
    if (!polygon || polygon.length < 3) {
        return false;
    }
    let inside = false;
    const n = polygon.length;
    let x = lng;
    let y = lat;
    for (let i = 0, j = n - 1; i < n; j = i++) {
        const xi = polygon[i][1];
        const yi = polygon[i][0];
        const xj = polygon[j][1];
        const yj = polygon[j][0];
        
        const intersect = ((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
        if (intersect) {
            inside = !inside;
        }
    }
    return inside;
}

/**
 * Normalize Vietnamese text to remove diacritics and convert to lowercase
 * @param {string} value - Text to normalize
 * @returns {string} Normalized text
 */
function normalizeText(value) {
    return String(value || "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/đ/g, "d")
        .replace(/Đ/g, "D")
        .toLowerCase();
}

