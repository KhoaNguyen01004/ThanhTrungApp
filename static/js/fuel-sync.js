/**
 * fuel-sync.js
 * Google Sheet sync button, result display, and auto-refresh.
 */

(function () {
  var SYNC_URL = "/api/fuel/sync";
  var HISTORY_URL = "/api/fuel/sync/last";

  // ── Format duration ──────────────────────────────────────────────
  function fmtDuration(sec) {
    if (sec < 1) return Math.round(sec * 1000) + " ms";
    return sec.toFixed(2) + " s";
  }

  // ── Update the last-sync badge ───────────────────────────────────
  function updateSyncBadge(data) {
    var badge = document.getElementById("sync-badge");
    var indicator = document.getElementById("sync-indicator");
    if (!badge) return;

    if (!data) {
      badge.textContent = "Never";
      badge.style.color = "#94a3b8";
      if (indicator) indicator.style.background = "#94a3b8";
      return;
    }

    var ts = data.created_at || "";
    var label = "";
    if (data.status === "error") {
      label = "Failed";
      badge.style.color = "#f87171";
      if (indicator) indicator.style.background = "#f87171";
    } else if (data.inserted_rows > 0) {
      label = data.inserted_rows + " new";
      badge.style.color = "#10b981";
      if (indicator) indicator.style.background = "#10b981";
    } else {
      label = "Up-to-date";
      badge.style.color = "#60a5fa";
      if (indicator) indicator.style.background = "#60a5fa";
    }
    if (ts) {
      var d = new Date(ts.replace(" ", "T") + "Z");
      var timeStr = d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
      badge.textContent = label + " \u00b7 " + timeStr;
    } else {
      badge.textContent = label;
    }
  }

  // ── Full dashboard refresh ───────────────────────────────────────
  // Refreshes the month dropdown (to pick up newly synced months),
  // reselects "All time", then reloads the data table/chart/stats.
  function refreshDashboard() {
    // Refresh month dropdown if the function is available
    if (typeof populateMonthSelect === "function") {
      populateMonthSelect().then(function () {
        var sel = document.getElementById("month-select");
        if (sel) sel.selectedIndex = 0; // "All time"
        if (typeof onMonthChange === "function") onMonthChange();
      }).catch(function () {
        // fallback: just reload data
        if (typeof onMonthChange === "function") onMonthChange();
      });
    } else {
      if (typeof onMonthChange === "function") onMonthChange();
    }
    if (typeof loadVehicles === "function") loadVehicles();
    if (typeof loadProfiles === "function") loadProfiles();
  }

  // ── Fetch last sync and update badge ─────────────────────────────
  function loadLastSync() {
    fetch(HISTORY_URL)
      .then(function (r) { return r.json(); })
      .then(function (resp) {
        if (resp.success && resp.data) updateSyncBadge(resp.data);
      })
      .catch(function () {});
  }

  // ── Main sync trigger ────────────────────────────────────────────
  function triggerSync() {
    var btn = document.getElementById("btn-sync-sheet");
    if (!btn) return;
    btn.disabled = true;
    btn.innerHTML =
      '<span class="spin" style="width:14px;height:14px;border-width:2px;"></span> Syncing\u2026';

    fetch(SYNC_URL, { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function (resp) {
        if (!resp.success) {
          UI.toast("Sync failed: " + (resp.message || "Unknown error"), "error", 6000);
          updateSyncBadge({ status: "error", created_at: new Date().toISOString() });
          return;
        }
        var d = resp.data;
        var lines = [];
        lines.push("Fetched: " + d.fetched);
        lines.push("Inserted: " + d.inserted);
        lines.push("Duplicates: " + d.duplicate);
        if (d.failed > 0) lines.push("Failed: " + d.failed);
        lines.push("Duration: " + fmtDuration(d.duration_sec));

        if (d.inserted > 0) {
          UI.toast(lines.join("  \u2022  "), "success", 8000);
        } else if (d.failed > 0) {
          UI.toast(lines.join("  \u2022  "), "warning", 8000);
        } else {
          UI.toast("Already up to date  \u2022  " + fmtDuration(d.duration_sec), "success", 4000);
        }

        updateSyncBadge(d);

        // Full dashboard refresh: repopulate months, reselect "All time", reload data
        refreshDashboard();
      })
      .catch(function (err) {
        UI.toast("Sync request failed: " + err.message, "error", 6000);
      })
      .finally(function () {
        btn.disabled = false;
        btn.innerHTML =
          '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg> Sync Google Sheet';
      });
  }

  // ── Expose and init ──────────────────────────────────────────────
  window.triggerSync = triggerSync;
  window.updateSyncBadge = updateSyncBadge;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadLastSync);
  } else {
    loadLastSync();
  }
})();
