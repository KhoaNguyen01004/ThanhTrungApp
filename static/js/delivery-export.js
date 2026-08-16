// ================================================================
// End of Day — collect the day's photos and download the handover ZIP
// ================================================================
//
// The photos already on the server are organised the way they were written
// (year/month/day/plate/station/category). This page gathers the two kinds
// that never pass through a stop — the loading shots from the evening
// before, and each driver's empty container — and then asks the server to
// rebuild everything into the folder shape the operator hands over.
//
// Uploads go one file per request. MAX_CONTENT_LENGTH is 25 MB for a whole
// request, so a day's loading photos could not be sent in one POST; sending
// them individually also means a failed download doesn't discard what was
// just handed over.
(function () {
  'use strict';

  const escapeHtml = UI.escapeHtml;

  // Not ApiClient: that helper prefixes /api itself and treats a response as
  // an error unless it carries `success: true`, an envelope the delivery API
  // has never used. The dispatch dashboard keeps its own fetch wrapper for
  // exactly this reason (static/js/dashboard/api.js); this follows it rather
  // than bending either contract.
  async function fetchJSON(url, opts) {
    const resp = await fetch(url, opts);
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new Error(body.error || body.message || `HTTP ${resp.status}`);
    }
    return resp.json();
  }

  const el = (id) => document.getElementById(id);
  const state = { summary: null };

  function todayISOLocal(offsetDays) {
    // Built from local parts rather than toISOString(), which converts to UTC
    // and in Vietnam (+7) hands back yesterday's date for most of the morning.
    const d = new Date();
    if (offsetDays) d.setDate(d.getDate() + offsetDays);
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  function ddmm(iso) {
    const parts = String(iso || '').slice(0, 10).split('-');
    return parts.length === 3 ? `${parts[2]}_${parts[1]}` : '00_00';
  }

  // ── Summary of the day ─────────────────────────────────────────
  async function loadSummary() {
    const date = el('exportDate').value;
    if (!date) return;
    el('proofSummary').innerHTML = '<span class="export-hint">Loading…</span>';
    try {
      const summary = await fetchJSON(`/api/export/summary?date=${encodeURIComponent(date)}`);
      state.summary = summary;
      renderSummary(summary);
      renderDrivers(summary);
      renderDayImages(summary);
      renderStructure();
    } catch (err) {
      el('proofSummary').innerHTML =
        `<span class="export-hint">Could not load this day: ${escapeHtml(err.message)}</span>`;
    }
  }

  function renderSummary(summary) {
    if (!summary.drivers.length) {
      el('dateSummary').textContent = 'No delivery plan on this date';
      el('proofSummary').innerHTML =
        '<span class="export-hint">Nothing planned for this date.</span>';
      return;
    }
    el('dateSummary').textContent =
      `${summary.drivers.length} vehicle(s), ${summary.stop_count} stop(s)`;

    el('proofSummary').innerHTML = summary.drivers.map((driver) => {
      const rows = driver.stops.map((stop) => {
        // Complete / incomplete is the only thing being asked here, so it
        // reads as a state rather than as two photo counts to compare.
        const ok = stop.missing.length === 0;
        const missing = ok ? 'complete' : `missing ${stop.missing.join(' + ')}`;
        const override = stop.override_reason
          ? `<span class="export-override" title="Completed without proof">waived: ${escapeHtml(stop.override_reason)}</span>`
          : '';
        return `<div class="export-stop ${ok ? 'is-ok' : 'is-missing'}">
                  <span class="export-station">${escapeHtml(stop.station_code || stop.station_name || 'Stop')}</span>
                  <span class="export-state">${escapeHtml(missing)}</span>
                  ${override}
                </div>`;
      }).join('');
      return `<div class="export-driver">
                <div class="export-driver-name">${escapeHtml(driver.folder)}</div>
                ${rows}
              </div>`;
    }).join('');
  }

  function renderDrivers(summary) {
    // Both pickers write the driver into `label`, but they store different
    // things and deliberately so. HinhThungTrong puts the label in the
    // *filename*, so it wants the human name. HinhNhanHang puts it in a
    // *folder* that has to match the driver's HinhGiaoHang folder exactly, so
    // it stores the already-built folder name — remapping a driver_name back
    // to a folder at export time is ambiguous the moment one driver runs two
    // trucks, which is two folders and one name.
    const fill = (id, valueOf) => {
      const select = el(id);
      const previous = select.value;
      select.innerHTML = summary.drivers
        .map((d) => `<option value="${escapeHtml(valueOf(d))}">${escapeHtml(d.folder)}</option>`)
        .join('');
      // Only restore a selection that still exists on this date; assigning an
      // absent value to a <select> silently leaves it on the first option.
      if (previous && summary.drivers.some((d) => valueOf(d) === previous)) {
        select.value = previous;
      }
    };
    fill('containerDriver', (d) => d.driver_name);
    fill('loadingDriver', (d) => d.folder);
  }

  function renderDayImages(summary) {
    const render = (containerId, images, withLabel) => {
      const container = el(containerId);
      // The loading list is capped and scrolls (.export-thumbs--scroll), and
      // every upload re-runs loadSummary() → this. Replacing innerHTML resets
      // scrollTop to 0, so without this the operator is thrown back to the top
      // of forty filenames after each photo — the state loss the dashboard
      // conventions in CLAUDE.md exist to prevent.
      const scrollTop = container.scrollTop;
      if (!images.length) {
        container.innerHTML = '<span class="export-hint">Nothing uploaded yet.</span>';
        return;
      }
      container.innerHTML = images.map((img) => `
        <div class="export-thumb">
          <span class="export-thumb-name">${escapeHtml(
            (withLabel && img.label ? img.label + ' — ' : '') + (img.original_filename || img.filename)
          )}</span>
          <button type="button" class="btn-nav export-thumb-remove" data-remove="${img.id}">&times;</button>
        </div>`).join('');
      container.scrollTop = scrollTop;
    };
    render('loadingList', summary.day_images.loading || [], true);
    render('containerList', summary.day_images.empty_container || [], true);
  }

  // ── Uploads ────────────────────────────────────────────────────
  async function uploadFiles(files, category, label, statusEl) {
    const date = el('exportDate').value;
    if (!date) {
      UI.toast('Pick a delivery date first', 'error');
      return;
    }
    let done = 0;
    let failed = 0;
    for (const file of files) {
      statusEl.textContent = `Uploading ${done + failed + 1} of ${files.length}…`;
      const form = new FormData();
      form.append('file', file);
      form.append('date', date);
      form.append('category', category);
      if (label) form.append('label', label);
      try {
        // Sequential, not Promise.all: production is a single synchronous
        // worker, so firing twenty uploads at once would queue them anyway
        // and starve every other request while they waited.
        await fetchJSON('/api/export/day-images', { method: 'POST', body: form });
        done += 1;
      } catch (err) {
        failed += 1;
        UI.toast(`${file.name}: ${err.message}`, 'error', 6000);
      }
    }
    statusEl.textContent = failed
      ? `${done} uploaded, ${failed} failed`
      : `${done} uploaded`;
    await loadSummary();
  }

  // ── What the ZIP will look like ────────────────────────────────
  // Shown because the folder name is typed and the structure is the thing
  // being handed over — seeing it before the download is cheaper than
  // unzipping to find out.
  function renderStructure() {
    const summary = state.summary;
    const name = el('folderName').value.trim() || `export_${ddmm(el('exportDate').value)}`;
    const lines = [`${name}/`];
    // Driver first, both photo folders inside it — the shape the operator
    // hands over. Every folder listed here is created in the ZIP even when
    // empty, so this preview doubles as the checklist of what is still unshot.
    (summary ? summary.drivers : []).forEach((driver) => {
      lines.push(`  ${driver.folder}/`);
      lines.push(`    HinhNhanHang_${ddmm(el('loadingDate').value)}/`);
      lines.push(`    HinhGiaoHang_${ddmm(el('exportDate').value)}/`);
      driver.stops.forEach((stop) => {
        lines.push(`      ${stop.station_code || 'KhongRoTram'}/`);
      });
    });
    lines.push(`  ${'HinhThungTrong'}/`);
    lines.push('  manifest.xlsx');
    el('structurePreview').textContent = lines.join('\n');
  }

  function download() {
    const date = el('exportDate').value;
    if (!date) {
      UI.toast('Pick a delivery date first', 'error');
      return;
    }
    const name = el('folderName').value.trim();
    if (!name) {
      UI.toast('Type a folder name — it carries the route names', 'error');
      el('folderName').focus();
      return;
    }
    const incomplete = state.summary ? state.summary.incomplete_count : 0;
    if (incomplete) {
      UI.toast(`${incomplete} stop(s) still missing a photo — they are listed in manifest.xlsx, `
               + 'and their folders will be empty', 'warning', 7000);
    }
    // Building the ZIP blocks the single production worker, so say something
    // rather than leaving a button that appears to have done nothing.
    el('downloadStatus').textContent = 'Building the ZIP — this can take a moment…';
    const params = new URLSearchParams({
      date, name, loading_date: el('loadingDate').value || '',
    });
    window.location.href = `/api/export/day.zip?${params.toString()}`;
    setTimeout(() => { el('downloadStatus').textContent = ''; }, 8000);
  }

  // ── Wiring ─────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    el('exportDate').value = todayISOLocal(0);
    el('loadingDate').value = todayISOLocal(-1);
    el('folderName').value = `${ddmm(el('exportDate').value).replace(/^0/, '').replace('_0', '_')}_`;

    el('exportDate').addEventListener('change', () => {
      el('loadingDate').value = todayISOLocal(0) === el('exportDate').value
        ? todayISOLocal(-1)
        : el('loadingDate').value;
      loadSummary();
    });
    el('loadingDate').addEventListener('change', renderStructure);
    el('folderName').addEventListener('input', renderStructure);

    el('loadingInput').addEventListener('change', async (e) => {
      const files = Array.from(e.target.files || []);
      if (files.length) {
        await uploadFiles(files, 'loading', el('loadingDriver').value,
                          el('loadingStatus'));
      }
      e.target.value = '';
    });

    el('containerInput').addEventListener('change', async (e) => {
      const files = Array.from(e.target.files || []);
      if (files.length) {
        await uploadFiles(files, 'empty_container', el('containerDriver').value,
                          el('containerStatus'));
      }
      e.target.value = '';
    });

    document.addEventListener('click', async (e) => {
      const remove = e.target.closest('[data-remove]');
      if (!remove) return;
      try {
        await fetchJSON(`/api/export/day-images/${remove.dataset.remove}`, { method: 'DELETE' });
        await loadSummary();
      } catch (err) {
        UI.toast(`Could not remove: ${err.message}`, 'error');
      }
    });

    el('downloadBtn').addEventListener('click', download);

    loadSummary();
  });
})();
