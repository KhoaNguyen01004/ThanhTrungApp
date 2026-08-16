/**
 * Truck Load Planner — Frontend Application
 * EasyCargo-inspired redesign with interactive Konva canvas,
 * drag-and-drop placement, real-time validation, and live measurements.
 */

const API = {
  vehicles: () => fetch("/api/tlp/vehicle-containers").then(r => r.json()),
  packages: () => fetch("/api/tlp/packages").then(r => r.json()),
  shipments: () => fetch("/api/tlp/shipments").then(r => r.json()),
  getShipment: (id) => fetch(`/api/tlp/shipments/${id}`).then(r => r.json()),
  saveShipment: (data) => fetch("/api/tlp/shipments", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }).then(r => r.json()),
  updateShipment: (id, data) => fetch(`/api/tlp/shipments/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }).then(r => r.json()),
  deleteShipment: (id) => fetch(`/api/tlp/shipments/${id}`, { method: "DELETE" }).then(r => r.json()),
  updateShipmentItem: (id, data) => fetch(`/api/tlp/shipment-items/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }).then(r => r.json()),
  deleteShipmentItem: (id) => fetch(`/api/tlp/shipment-items/${id}`, { method: "DELETE" }).then(r => r.json()),
  plans: () => fetch("/api/tlp/plans").then(r => r.json()),
  getPlan: (id) => fetch(`/api/tlp/plans/${id}`).then(r => r.json()),
  savePlan: (data) => fetch("/api/tlp/plans", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }).then(r => r.json()),
  updatePlan: (id, data) => fetch(`/api/tlp/plans/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }).then(r => r.json()),
  validate: (data) => fetch("/api/tlp/session/validate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }).then(r => r.json()),
  container: (id) => fetch(`/api/tlp/container-configs/${id}`).then(r => r.json()),
};

class LoadPlannerApp {
  constructor() {
    // Data
    this.vehicles = [];
    this.packages = [];
    this.shipments = [];
    // Shipment editing
    this._editingShipment = null;    // null = new, otherwise editing existing
    this._editItems = [];
    this._pkgTab = 'unplaced';

    // Inspector
    this.selectedIndex = -1;
    this._ignoreInspectorChange = false;

    // Canvas
    this.stage = null;
    this.gridLayer = null;
    this.containerLayer = null;
    this.packageLayer = null;
    this.previewLayer = null;
    this.rulerLayer = null;
    this.canvasW = 0;
    this.canvasH = 0;

    // View
    this.currentView = "top";
    this.viewScale = 1;
    this.viewOffsetX = 0;
    this.viewOffsetY = 0;
    this.baseScale = 1;
    this.gridEnabled = true;
    this.snapEnabled = true;
    this.gridSpacing = 25;

    // Preview state
    this.isDraggingFromPalette = false;
    this.dragPackageData = null;
    this.previewRect = null;
    this.previewText = null;
    this.previewNodes = [];
    this.lastValidResult = null;
    this.isPanning = false;
    this._panStart = null;
    this._panOffsetStart = null;

    // Undo/Redo
    this.undoStack = [];
    this.redoStack = [];
    this.maxUndo = 50;

    // Ruler display
    this.rulerTexts = [];

    // 3D Preview
    this._show3D = false;
    this._threeScene = null;
    this._threeCamera = null;
    this._threeRenderer = null;
    this._threeControls = null;
    this._threeAnimId = null;
    this._threeMeshes = [];
    this._threeInitAttempted = false;

    // Arrange results (multi-vehicle)
    this._arrangePlacements = [];
    this._arrangeResults = [];

    // Step animation
    this._stepMode = false;
    this._stepPlacements = [];
    this._stepIndex = 0;
    this._stepTotal = 0;
    this._stepAnimating = false;
    this._stepAnimState = null;
    this._stepAnimDuration = 500;
    this._stepAutoPlay = false;
    this._stepPermanentPkgs = [];  // {mesh, outline, placement}
  }

  /* ═══════════════════════ INIT ═══════════════════════ */

  async init() {
    try {
      await this.loadData();
    } catch (e) {
      console.error("Init error:", e);
    }
    this.initCanvas();
    this.setupEvents();
    this.populateVehicleList();
    this.populateShipmentList();
    this.populatePlanList();
    this.filterPackages();
    this.updateStatus();
  }

  async loadData() {
    try {
      const [vehicles, packages, shipments, plans] = await Promise.all([
        API.vehicles(), API.packages(), API.shipments(), API.plans()
      ]);
      this.vehicles = vehicles;
      this.packages = packages;
      this.shipments = shipments;
      this.plans = plans;
    } catch (e) {
      console.error("Failed to load data:", e);
      UI.toast("Failed to load data", "error");
    }
  }

  /* ═══════════════════════ CANVAS ═══════════════════════ */

  initCanvas() {
    const container = document.getElementById("tlp-canvas-container");
    this._resizeCanvas();

    this.stage = new Konva.Stage({
      container: "tlp-canvas-container",
      width: this.canvasW,
      height: this.canvasH,
    });
    this.stage.container().style.cursor = "grab";

    this.gridLayer = new Konva.Layer();
    this.containerLayer = new Konva.Layer();
    this.packageLayer = new Konva.Layer();
    this.previewLayer = new Konva.Layer();
    this.rulerLayer = new Konva.Layer();

    this.stage.add(this.gridLayer);
    this.stage.add(this.containerLayer);
    this.stage.add(this.packageLayer);
    this.stage.add(this.previewLayer);
    this.stage.add(this.rulerLayer);
  }

  _resizeCanvas() {
    const container = document.getElementById("tlp-canvas-container");
    this.canvasW = container.clientWidth || 600;
    this.canvasH = container.clientHeight || 400;
  }

  /* ═══════════════════════ EVENTS ═══════════════════════ */

  setupEvents() {
    window.addEventListener("resize", () => this._onResize());
    this.stage.on("wheel", (e) => this._onWheel(e));
    this.stage.on("mousedown", (e) => this._onMouseDown(e));
    this.stage.on("mousemove", (e) => this._onMouseMove(e));
    this.stage.on("mouseup", (e) => this._onMouseUp(e));
    this.stage.on("click", (e) => this._onCanvasClick(e));
    this.stage.on("dblclick", (e) => this._onDblClick(e));

    document.addEventListener("keydown", (e) => this._onKeyDown(e));

    const canvasContainer = document.getElementById("tlp-canvas-container");
    canvasContainer.addEventListener("dragover", (e) => this._onDragOver(e));
    canvasContainer.addEventListener("dragleave", (e) => this._onDragLeave(e));
    canvasContainer.addEventListener("drop", (e) => this._onDrop(e));
  }

  _onResize() {
    this._resizeCanvas();
    if (this.stage) {
      this.stage.width(this.canvasW);
      this.stage.height(this.canvasH);
      this.renderCanvas();
    }
  }

  _onWheel(e) {
    e.evt.preventDefault();
    const oldScale = this.viewScale;
    const factor = e.evt.deltaY > 0 ? 0.9 : 1.1;
    const newScale = Math.max(0.05, Math.min(10, oldScale * factor));
    if (newScale === oldScale) return;

    const pointer = this.stage.getPointerPosition();
    this.viewScale = newScale;
    this.viewOffsetX = pointer.x - (pointer.x - this.viewOffsetX) * (newScale / oldScale);
    this.viewOffsetY = pointer.y - (pointer.y - this.viewOffsetY) * (newScale / oldScale);

    this.renderCanvas();
    this._updateStatusBarZoom();
  }

  _onMouseDown(e) {
    // Start panning only when clicking on empty stage background (not a package)
    if (e.target === this.stage && !this.isDraggingFromPalette) {
      this._panStart = this.stage.getPointerPosition();
      this._panOffsetStart = { x: this.viewOffsetX, y: this.viewOffsetY };
      this.isPanning = true;
      this.stage.container().style.cursor = "grabbing";
    }
  }

  _onMouseUp(e) {
    if (this.isPanning) {
      this.isPanning = false;
      this.stage.container().style.cursor = "";
    }
  }

  _onMouseMove(e) {
    const pos = this.stage.getPointerPosition();
    if (!pos) return;
    const mm = this._stageToMm(pos.x, pos.y);
    const cursorEl = document.getElementById("sb-cursor");
    cursorEl.textContent = Math.round(mm.x) + ", " + Math.round(mm.y);

    if (this.isPanning && this._panStart) {
      this.viewOffsetX = this._panOffsetStart.x + (pos.x - this._panStart.x);
      this.viewOffsetY = this._panOffsetStart.y + (pos.y - this._panStart.y);
      this.renderCanvas();
      return;
    }

    if (this.isDraggingFromPalette && this.dragPackageData) {
      this._updatePreview(pos.x, pos.y);
    }
  }

  _onCanvasClick(e) {
    if (e.target === this.stage) {
      this._deselectPackage();
      this._syncPackageCardHighlight();
      return;
    }
    // Check if a package rect was clicked
    const name = e.target.name();
    if (name && name.startsWith("pkg-")) {
      const idx = parseInt(name.split("-")[1], 10);
      if (!isNaN(idx) && idx >= 0 && idx < this.placements.length) {
        this.selectedIndex = idx;
        this._deselectAllShapes();
        e.target.strokeWidth(2);
        e.target.stroke("#fff");
        this._showInspector(idx);
        this._syncPackageCardHighlight();
        this.renderCanvas();
      }
    }
  }

  _onDblClick(e) {
    // Reserved for future (e.g., edit package rotation)
  }

  _onKeyDown(e) {
    if (e.key === "Delete" || e.key === "Backspace") {
      if (this.selectedIndex >= 0) {
        this.deleteSelected();
        e.preventDefault();
      }
    }
    if (e.ctrlKey && e.key === "z") {
      if (e.shiftKey) this.redo();
      else this.undo();
      e.preventDefault();
    }
    if (e.key === "Escape") {
      this._deselectPackage();
      this._cancelPaletteDrag();
      // Exit 3D fullscreen
      const container = document.getElementById("tlp-3d-container");
      if (container && container.classList.contains("fullscreen")) {
        this.toggle3DFullscreen();
      }
    }
    if (e.key === "f" || e.key === "F") {
      if (this._show3D) {
        this.toggle3DFullscreen();
        e.preventDefault();
      }
    }
  }

  /* ═══════════════════════ COORDINATE SYSTEM ═══════════════════════ */

  _getContainerDims() {
    const v = this.currentVehicle;
    const cc = this.currentContainer;
    return {
      len: (cc && cc.cargo_length_mm) || (v && v.cargo_length_mm) || 0,
      wid: (cc && cc.cargo_width_mm) || (v && v.cargo_width_mm) || 0,
      hei: (cc && cc.cargo_height_mm) || (v && v.cargo_height_mm) || 0,
    };
  }

  _getViewDims(overrideView) {
    const view = overrideView || this.currentView;
    const d = this._getContainerDims();
    if (view === "top") return { dim1: d.len, dim2: d.wid };
    if (view === "side") return { dim1: d.len, dim2: d.hei };
    return { dim1: d.wid, dim2: d.hei };
  }

  _computeBaseScale() {
    const d = this._getViewDims();
    if (d.dim1 <= 0 || d.dim2 <= 0) return 1;
    const pad = 60;
    const drawW = this.canvasW - pad * 2;
    const drawH = this.canvasH - pad * 2;
    return Math.min(drawW / d.dim1, drawH / d.dim2, 2);
  }

  _mmToStage(xMm, yMm) {
    const d = this._getViewDims();
    const base = this._computeBaseScale();
    const scale = base * this.viewScale;
    const padX = (this.canvasW - d.dim1 * scale) / 2;
    const padY = (this.canvasH - d.dim2 * scale) / 2;
    const view = this.currentView;
    return {
      x: xMm * scale + padX + this.viewOffsetX,
      y: yMm * scale + padY + this.viewOffsetY,
    };
  }

  _stageToMm(stageX, stageY) {
    const d = this._getViewDims();
    const base = this._computeBaseScale();
    const scale = base * this.viewScale;
    if (scale === 0) return { x: 0, y: 0 };
    const padX = (this.canvasW - d.dim1 * scale) / 2;
    const padY = (this.canvasH - d.dim2 * scale) / 2;
    const view = this.currentView;
    const mmX = (stageX - padX - this.viewOffsetX) / scale;
    return {
      x: mmX,
      y: (stageY - padY - this.viewOffsetY) / scale,
    };
  }

  _getCurrentScale() {
    const base = this._computeBaseScale();
    return base * this.viewScale;
  }

  /* ═══════════════════════ RENDER ═══════════════════════ */

  renderCanvas() {
    if (!this.stage) return;
    this.gridLayer.destroyChildren();
    this.containerLayer.destroyChildren();
    this.packageLayer.destroyChildren();
    this.rulerLayer.destroyChildren();

    if (!this.currentVehicle) {
      const txt = new Konva.Text({
        text: "Select a vehicle to begin",
        x: this.canvasW / 2 - 100,
        y: this.canvasH / 2 - 10,
        fontSize: 14,
        fill: "#7c8fa3",
        fontFamily: "Inter",
      });
      this.containerLayer.add(txt);
      this.containerLayer.batchDraw();
      this._updateStatusBarScale();
      return;
    }

    this._drawGrid();
    this._drawContainer();
    this._drawRulers();
    this._drawPackages();
    this._drawOrigin();

    this.gridLayer.batchDraw();
    this.containerLayer.batchDraw();
    this.packageLayer.batchDraw();
    this.rulerLayer.batchDraw();
    this._updateStatusBarScale();
  }

  /* ─── Grid ─── */

  _drawGrid() {
    if (!this.gridEnabled) return;
    const d = this._getViewDims();
    const scale = this._getCurrentScale();
    const dView = this._getViewDims();
    const dim1 = dView.dim1;
    const dim2 = dView.dim2;
    if (dim1 <= 0 || dim2 <= 0) return;

    const _p1 = this._mmToStage(0, 0);
    const _p2 = this._mmToStage(dim1, dim2);
    const p1 = { x: Math.min(_p1.x, _p2.x), y: Math.min(_p1.y, _p2.y) };
    const p2 = { x: Math.max(_p1.x, _p2.x), y: Math.max(_p1.y, _p2.y) };

    // Adaptive grid spacing
    const pxPerMm = scale;
    let gridMm = this.gridSpacing;
    const pxStep = gridMm * pxPerMm;
    if (pxStep < 8) {
      gridMm = Math.ceil(8 / pxPerMm / 50) * 50;
    } else if (pxStep > 80) {
      gridMm = Math.max(this.gridSpacing, Math.floor(pxStep / 80) * this.gridSpacing);
    }

    const gridPx = gridMm * pxPerMm;
    const xStart = Math.ceil(p1.x / gridPx) * gridPx;
    const yStart = Math.ceil(p1.y / gridPx) * gridPx;
    const xEnd = p2.x;
    const yEnd = p2.y;

    const lines = [];
    for (let x = xStart; x <= xEnd; x += gridPx) {
      lines.push([x, p1.y, x, yEnd]);
    }
    for (let y = yStart; y <= yEnd; y += gridPx) {
      lines.push([p1.x, y, xEnd, y]);
    }

    const gridGroup = new Konva.Group({ listening: false });
    for (const l of lines) {
      gridGroup.add(new Konva.Line({
        points: l,
        stroke: "rgba(255,255,255,0.04)",
        strokeWidth: 0.5,
      }));
    }

    // Major grid lines every 500mm
    const majorMm = 500;
    const majorPx = majorMm * pxPerMm;
    const mxStart = Math.ceil(p1.x / majorPx) * majorPx;
    const myStart = Math.ceil(p1.y / majorPx) * majorPx;
    for (let x = mxStart; x <= xEnd; x += majorPx) {
      gridGroup.add(new Konva.Line({
        points: [x, p1.y, x, yEnd],
        stroke: "rgba(255,255,255,0.07)",
        strokeWidth: 0.5,
      }));
    }
    for (let y = myStart; y <= yEnd; y += majorPx) {
      gridGroup.add(new Konva.Line({
        points: [p1.x, y, xEnd, y],
        stroke: "rgba(255,255,255,0.07)",
        strokeWidth: 0.5,
      }));
    }

    this.gridLayer.add(gridGroup);
    document.getElementById("sb-grid").textContent = gridMm + " mm";
  }

  /* ─── Container ─── */

  _drawContainer() {
    const v = this.currentVehicle;
    const cc = this.currentContainer;
    const d = this._getViewDims();
    const dim1 = d.dim1;
    const dim2 = d.dim2;
    if (dim1 <= 0 || dim2 <= 0) return;

    const _p1 = this._mmToStage(0, 0);
    const _p2 = this._mmToStage(dim1, dim2);
    const p1 = { x: Math.min(_p1.x, _p2.x), y: Math.min(_p1.y, _p2.y) };
    const p2 = { x: Math.max(_p1.x, _p2.x), y: Math.max(_p1.y, _p2.y) };
    const w = p2.x - p1.x;
    const h = p2.y - p1.y;
    const view = this.currentView;

    // Container fill
    this.containerLayer.add(new Konva.Rect({
      x: p1.x, y: p1.y, width: w, height: h,
      fill: "rgba(255,255,255,0.015)",
      stroke: "#2f8ceb",
      strokeWidth: 1.5,
      cornerRadius: 2,
    }));

    // Vehicle info label
    const features = (cc && cc.features) || (v && v.features) || [];
    const featureTypes = features.map(f => f.feature_type || f);
    const hasRearDoor = featureTypes.includes("rear_door");
    const hasSideDoor = featureTypes.includes("side_door");

    const infoText = v.plate_number + "  |  " + d.len + "x" + d.wid + "x" + d.hei + " mm" +
      (hasRearDoor ? "  |  Rear Door" : "") +
      (hasSideDoor ? "  |  Side Door" : "");
    this.containerLayer.add(new Konva.Text({
      x: p1.x + 4, y: p1.y + 4,
      text: infoText,
      fontSize: 10,
      fill: "#7c8fa3",
      fontFamily: "Inter",
    }));

    // Draw doors
    for (const f of features) {
      this._drawFeature(f, view, p1, dim1, dim2);
    }

    // Dimension labels
    this.containerLayer.add(new Konva.Text({
      x: p1.x + w / 2 - 25, y: p2.y + 4,
      text: this._formatDim(dim1),
      fontSize: 10, fill: "#7c8fa3", fontFamily: "Inter", align: "center",
    }));
    this.containerLayer.add(new Konva.Text({
      x: p2.x + 4, y: p1.y + h / 2 - 6,
      text: this._formatDim(dim2),
      fontSize: 10, fill: "#7c8fa3", fontFamily: "Inter",
    }));
  }

  _drawFeature(f, view, origin, dim1, dim2) {
    let geo = f.geometry_json || f.geometry || {};
    if (typeof geo === "string") try { geo = JSON.parse(geo); } catch (e) { geo = {}; }
    const ftype = f.feature_type || f;
    const scale = this._getCurrentScale();
    const p = origin;

    if (ftype === "rear_door") {
      const doorW = geo.width_mm || Math.min(dim2, 1800);
      const doorH = geo.height_mm || 1900;
      if (view === "top") {
        const dw = Math.min(12 * scale, 24);
        const dh = Math.min(doorW * scale, dim2 * scale);
        const x = p.x + dim1 * scale - dw;
        const y = p.y;
        this.containerLayer.add(new Konva.Rect({
          x, y, width: dw, height: dh,
          fill: "rgba(47,140,235,0.08)",
          stroke: "rgba(47,140,235,0.25)",
          strokeWidth: 1, dash: [3, 3],
        }));
        this.containerLayer.add(new Konva.Text({
          x: x - 2, y: y + dh / 2 - 6,
          text: "Rear Door", fontSize: 8, fill: "#60a5fa",
          fontFamily: "Inter", rotation: -90,
        }));
      } else if (view === "side") {
        const dw = Math.min(12 * scale, 22);
        const dh = Math.min(doorH * scale, dim2 * scale);
        const x = p.x + dim1 * scale - dw;
        const y = p.y + dim2 * scale - dh;
        this.containerLayer.add(new Konva.Rect({
          x, y, width: dw, height: dh,
          fill: "rgba(47,140,235,0.08)",
          stroke: "rgba(47,140,235,0.25)",
          strokeWidth: 1, dash: [3, 3],
        }));
        this.containerLayer.add(new Konva.Text({
          x: x - 8, y: y + dh / 2 - 5,
          text: "Rear Door", fontSize: 8, fill: "#60a5fa",
          fontFamily: "Inter", rotation: -90,
        }));
      } else if (view === "back") {
        const dw = Math.min(doorW * scale, dim1 * scale);
        const dh = Math.min(doorH * scale, dim2 * scale);
        const x = p.x + (dim1 * scale - dw) / 2;
        const y = p.y + dim2 * scale - dh;
        this.containerLayer.add(new Konva.Rect({
          x, y, width: dw, height: dh,
          fill: "rgba(47,140,235,0.06)",
          stroke: "rgba(47,140,235,0.2)",
          strokeWidth: 1, dash: [3, 3],
        }));
      }
    } else if (ftype === "side_door") {
      const doorW = geo.width_mm || 1200;
      const doorH = geo.height_mm || 1800;
      const pos = geo.position_from_front_mm || 0;
      if (view === "top") {
        const dw = Math.min(doorW * scale, dim1 * scale);
        const dh = Math.min(12 * scale, 22);
        const x = p.x + pos * scale;
        const y = p.y + dim2 * scale - dh;
        this.containerLayer.add(new Konva.Rect({
          x, y, width: dw, height: dh,
          fill: "rgba(16,185,129,0.08)",
          stroke: "rgba(16,185,129,0.25)",
          strokeWidth: 1, dash: [3, 3],
        }));
        this.containerLayer.add(new Konva.Text({
          x: x + dw / 2 - 16, y: y - 9,
          text: "Side Door", fontSize: 8, fill: "#34d399",
          fontFamily: "Inter",
        }));
      } else if (view === "side") {
        const dw = Math.min(doorW * scale, dim1 * scale);
        const dh = Math.min(doorH * scale, dim2 * scale);
        const x = p.x + pos * scale;
        const y = p.y + dim2 * scale - dh;
        this.containerLayer.add(new Konva.Rect({
          x, y, width: dw, height: dh,
          fill: "rgba(16,185,129,0.06)",
          stroke: "rgba(16,185,129,0.2)",
          strokeWidth: 1, dash: [3, 3],
        }));
      }
    }
  }

  _drawOrigin() {
    const d = this._getViewDims();
    const p = this._mmToStage(0, 0);
    const size = Math.max(8, Math.min(16, 10 * this._getCurrentScale()));
    this.containerLayer.add(new Konva.Circle({
      x: p.x + size / 2, y: p.y + size / 2,
      radius: size / 2,
      fill: "rgba(47,140,235,0.3)",
      stroke: "#2f8ceb",
      strokeWidth: 1,
    }));
    this.containerLayer.add(new Konva.Text({
      x: p.x + size + 3, y: p.y - 1,
      text: "0,0",
      fontSize: 9, fill: "#60a5fa",
      fontFamily: "Inter", fontStyle: "bold",
    }));
  }

  /* ─── Rulers ─── */

  _drawRulers() {
    const d = this._getViewDims();
    const dim1 = d.dim1;
    const dim2 = d.dim2;
    if (dim1 <= 0 || dim2 <= 0) return;
    const _p1 = this._mmToStage(0, 0);
    const _p2 = this._mmToStage(dim1, dim2);
    const p1 = { x: Math.min(_p1.x, _p2.x), y: Math.min(_p1.y, _p2.y) };
    const p2 = { x: Math.max(_p1.x, _p2.x), y: Math.max(_p1.y, _p2.y) };
    const scale = this._getCurrentScale();

    // Ruler tick spacing
    let tickMm = 100;
    const tickPx = tickMm * scale;
    if (tickPx < 20) tickMm = 500;
    else if (tickPx > 80) tickMm = 50;

    const rulerGroup = new Konva.Group({ listening: false });
    const tickPx2 = tickMm * scale;

    // Top ruler
    for (let mm = 0; mm <= dim1; mm += tickMm) {
      const pos = this._mmToStage(mm, 0);
      const major = mm % 500 === 0 || mm === 0 || mm >= dim1 - 1;
      const tickH = major ? 6 : 3;
      rulerGroup.add(new Konva.Line({
        points: [pos.x, p1.y - tickH, pos.x, p1.y],
        stroke: "rgba(255,255,255,0.15)",
        strokeWidth: 0.5,
      }));
      if (major && mm > 0 && mm < dim1 - 1) {
        rulerGroup.add(new Konva.Text({
          x: pos.x - 12, y: p1.y - tickH - 10,
          text: this._formatDim(mm),
          fontSize: 8, fill: "#7c8fa3",
          fontFamily: "Inter",
        }));
      }
    }

    // Left ruler
    for (let mm = 0; mm <= dim2; mm += tickMm) {
      const pos = this._mmToStage(0, mm);
      const major = mm % 500 === 0 || mm === 0 || mm >= dim2 - 1;
      const tickW = major ? 6 : 3;
      rulerGroup.add(new Konva.Line({
        points: [p1.x - tickW, pos.y, p1.x, pos.y],
        stroke: "rgba(255,255,255,0.15)",
        strokeWidth: 0.5,
      }));
      if (major && mm > 0 && mm < dim2 - 1) {
        rulerGroup.add(new Konva.Text({
          x: p1.x - tickW - 28, y: pos.y - 5,
          text: this._formatDim(mm),
          fontSize: 8, fill: "#7c8fa3",
          fontFamily: "Inter",
        }));
      }
    }

    this.rulerLayer.add(rulerGroup);
  }

  _formatDim(mm) {
    if (mm >= 1000) return (mm / 1000).toFixed(1) + "m";
    return mm + "mm";
  }

  /* ─── Packages ─── */

  _drawPackages() {
    if (!this.currentVehicle || this.placements.length === 0) return;
    const d = this._getViewDims();
    const dim1 = d.dim1;
    const dim2 = d.dim2;
    const view = this.currentView;

    // ── Instrument: Representation 5 — canvas rendering coordinates ────
    const _renderedCoords = [];

    for (let i = 0; i < this.placements.length; i++) {
      const p = this.placements[i];
      const pkg = p._package || p;
      let dx, dy, dw, dh;

      if (view === "top") {
        dx = p.x || 0; dy = p.y || 0;
        dw = p._length || 0; dh = p._width || 0;
        if (p.rotation === 90 || p.rotation === 270) { let t = dw; dw = dh; dh = t; }
      } else if (view === "side") {
        dx = p.x || 0; dw = p._length || 0; dh = p._height || 0;
        if (p.rotation === 90 || p.rotation === 270) { let t = dw; dw = dh; dh = t; }
        dy = dim2 - (p.z || 0) - dh;
      } else {
        dw = p._width || 0; dh = p._height || 0;
        dx = dim1 - (p.y || 0) - dw;
        if (p.rotation === 90 || p.rotation === 270) { let t = dw; dw = dh; dh = t; }
        dy = dim2 - (p.z || 0) - dh;
      }

      _renderedCoords.push({
        package_id: p.package_id,
        name: p._name || "",
        x_mm: dx, y_mm: dy, w_mm: dw, h_mm: dh,
        z_mm: p.z || 0,
        view: view,
        canvas_x: this._mmToStage(dx, dy).x,
        canvas_y: this._mmToStage(dx, dy).y,
        canvas_w: Math.max(dw * this._getCurrentScale(), 2),
        canvas_h: Math.max(dh * this._getCurrentScale(), 2),
      });

      const color = p._color || (p._package && p._package.color) || "#3b82f6";
      const pos = this._mmToStage(dx, dy);
      const szW = Math.max(dw * this._getCurrentScale(), 2);
      const szH = Math.max(dh * this._getCurrentScale(), 2);

      const isSelected = (i === this.selectedIndex);
      const rect = new Konva.Rect({
        x: pos.x, y: pos.y,
        width: szW, height: szH,
        fill: color,
        stroke: isSelected ? "#fff" : "rgba(255,255,255,0.2)",
        strokeWidth: isSelected ? 2 : 0.5,
        cornerRadius: 1,
        opacity: 0.85,
        draggable: true,
        name: "pkg-" + i,
      });

      rect.on("dragstart", () => {
        this.selectedIndex = i;
        this._deselectAllShapes();
        rect.strokeWidth(2);
        rect.stroke("#fff");
        this._pushUndo();
      });

      rect.on("dragmove", () => {
        try {
          const mm = this._stageToMm(rect.x(), rect.y());
          let snappedX, snappedY;
          if (this.snapEnabled) {
            snappedX = Math.round(mm.x / this.gridSpacing) * this.gridSpacing;
            snappedY = Math.round(mm.y / this.gridSpacing) * this.gridSpacing;
          } else {
            snappedX = mm.x;
            snappedY = mm.y;
          }
          if (view !== "top") {
            let horiz = snappedX;
            const pkgH = pkg.height || pkg._height || 0;
            const desiredZ = dim2 - snappedY - pkgH;
            if (view === "back") {
              const pw = pkg.width || pkg._width || 0;
              horiz = dim1 - snappedX - pw;
            }
            const valid = this._findValidPosition(pkg, horiz, desiredZ);
            this._showMeasurement(view === "back" ? horiz : snappedX, valid != null ? valid.z : 0);
          } else {
            this._showMeasurement(snappedX, snappedY);
          }
        } catch (e) { console.error("dragmove error", e); }
      });

      rect.on("dragend", () => {
        try {
          const mm = this._stageToMm(rect.x(), rect.y());
          let newX = mm.x;
          let newY = mm.y;
          if (this.snapEnabled) {
            newX = Math.round(newX / this.gridSpacing) * this.gridSpacing;
            newY = Math.round(newY / this.gridSpacing) * this.gridSpacing;
          }
          const vd = this._getViewDims();
          if (newX < 0) newX = 0;
          if (newY < 0) newY = 0;

          // Clamp to container boundary accounting for package extent
          const pkgExtentX = (view === "back") ? (p._width || 0) : (p._length || 0);
          const maxX = vd.dim1 - pkgExtentX;
          if (newX > maxX) newX = Math.max(0, maxX);
          if (view === "top") {
            const maxY = vd.dim2 - (p._width || 0);
            if (newY > maxY) newY = Math.max(0, maxY);
          }

          if (view === "top") {
            this.placements[i].x = newX;
            this.placements[i].y = newY;
          } else if (view === "side") {
            const pkgH = p._height || 0;
            const valid = this._findValidPosition(pkg, newX, vd.dim2 - newY - pkgH);
            this.placements[i].x = newX;
            this.placements[i].z = valid != null ? valid.z : 0;
          } else {
            const pkgH = p._height || 0;
            const pkgW = p._width || 0;
            const containerY = vd.dim1 - newX - pkgW;
            const valid = this._findValidPosition(pkg, containerY, vd.dim2 - newY - pkgH);
            this.placements[i].y = containerY;
            this.placements[i].z = valid != null ? valid.z : 0;
          }
          this._hideMeasurement();

          // updateStatus() runs its own client-only updateValidationUI()
          // internally, so run it first — _validateAllPlacements' backend
          // result must land last or it would be immediately overwritten.
          this.renderCanvas();
          this.updateStatus();
          if (this._show3D) this.update3DScene();
          this._validateAllPlacements(i);
        } catch (e) { console.error("dragend error", e); }
      });

      this.packageLayer.add(rect);

      // Label when zoomed enough
      if (szW > 40 && szH > 16) {
        const label = (p._name || "Pkg") + "\n" + p._weight_kg + "kg";
        this.packageLayer.add(new Konva.Text({
          x: pos.x + 2, y: pos.y + 2,
          text: label,
          fontSize: Math.min(9, szH * 0.3),
          fill: "#fff",
          fontFamily: "Inter",
          fontStyle: "bold",
          listening: false,
        }));
      }

      // Sequence number
      if (p.load_sequence) {
        const seqSize = Math.min(14, Math.max(8, szW * 0.2));
        this.packageLayer.add(new Konva.Text({
          x: pos.x + szW - seqSize - 1,
          y: pos.y + 1,
          text: String(p.load_sequence),
          fontSize: seqSize * 0.6,
          fill: "rgba(255,255,255,0.6)",
          fontFamily: "Inter",
          fontStyle: "bold",
          listening: false,
        }));
      }
    }

    // ── Instrument: Representation 5 — canvas rendering coordinates ────
    console.log("=== INSTRUMENT REP 5: Canvas rendering coordinates ===");
    console.log(JSON.stringify({
      trace_id: "frontend-" + Date.now(),
      rep: 5,
      label: "canvas-rendered-coordinates",
      view: this.currentView,
      vehicle_id: this.currentVehicle ? this.currentVehicle.vehicle_id : null,
      container_mm: { dim1: d.dim1, dim2: d.dim2 },
      packages: _renderedCoords,
    }, null, 2));
  }

  /* ═══════════════════════ PREVIEW (drag from palette) ═══════════════════════ */

  _clearPreview() {
    this.previewLayer.destroyChildren();
    this.previewLayer.batchDraw();
    this.previewNodes = [];
  }

  _showPreview(stageX, stageY) {
    this._clearPreview();
    if (!this.dragPackageData) return;

    const mm = this._stageToMm(stageX, stageY);
    let snapX = mm.x;
    let snapY = mm.y;
    if (this.snapEnabled) {
      snapX = Math.round(snapX / this.gridSpacing) * this.gridSpacing;
      snapY = Math.round(snapY / this.gridSpacing) * this.gridSpacing;
    }
    const pkg = this.dragPackageData;
    const view = this.currentView;
    let dw = (view === "back") ? pkg.width : pkg.length;
    let dh = (view === "top") ? pkg.width : pkg.height;
    // Center the package under the cursor
    snapX -= dw / 2;
    snapY -= dh / 2;
    if (snapX < 0) snapX = 0;
    if (snapY < 0) snapY = 0;
    const pos = this._mmToStage(snapX, snapY);
    const scale = this._getCurrentScale();
    const sw = Math.max(dw * scale, 2);
    const sh = Math.max(dh * scale, 2);

    // Draw preview rect
    const rect = new Konva.Rect({
      x: pos.x, y: pos.y,
      width: sw, height: sh,
      fill: "rgba(16,185,129,0.2)",
      stroke: "rgba(16,185,129,0.6)",
      strokeWidth: 1.5,
      dash: [4, 3],
      cornerRadius: 1,
      listening: false,
    });
    this.previewLayer.add(rect);
    this.previewNodes.push(rect);

    // Label
    if (sw > 50 && sh > 20) {
      const label = new Konva.Text({
        x: pos.x + 2, y: pos.y + 2,
        text: pkg.name + "\n" + dw + "x" + dh + " mm",
        fontSize: 9, fill: "#34d399",
        fontFamily: "Inter", fontStyle: "bold",
        listening: false,
      });
      this.previewLayer.add(label);
      this.previewNodes.push(label);
    }

    // Measurement info
    const contDims = this._getContainerDims();
    const rearDoorDist = (view === "back") ? 0 : contDims.len - snapX - dw;
    const axX = view === "back" ? "W" : "X";
    const axY = view === "back" ? "Z" : (view === "side" ? "Z" : "Y");
    const rearTxt = view === "back" ? "" : "  |  To rear: " + Math.max(0, rearDoorDist) + " mm";
    let displayX = snapX;
    if (view === "back") displayX = contDims.wid - snapX - dw;
    const infoText = [
      axX + ": " + displayX + " mm",
      axY + ": " + snapY + " mm",
      rearTxt,
    ].filter(Boolean).join("  |  ");

    const info = new Konva.Text({
      x: 10, y: this.canvasH - 24,
      text: infoText,
      fontSize: 11, fill: "#b0bec9",
      fontFamily: "Inter",
      listening: false,
    });
    this.previewLayer.add(info);
    this.previewNodes.push(info);

    // Validation status
    if (this.lastValidResult) {
      const valid = this.lastValidResult.accepted;
      const statusText = valid ? "Valid placement" : "Invalid: " + (this.lastValidResult.errors || []).join(", ");
      const statusColor = valid ? "#10b981" : "#ef4444";
      const status = new Konva.Text({
        x: 10, y: this.canvasH - 40,
        text: statusText,
        fontSize: 11, fill: statusColor,
        fontFamily: "Inter", fontStyle: "bold",
        listening: false,
      });
      this.previewLayer.add(status);
      this.previewNodes.push(status);

      // Update preview color based on validation
      if (!valid) {
        rect.fill("rgba(239,68,68,0.15)");
        rect.stroke("rgba(239,68,68,0.5)");
      }
    }

    this.previewLayer.batchDraw();
  }

  _showMeasurement(xMm, yMm) {
    const d = this._getContainerDims();
    const view = this.currentView;
    const labelX = view === "back" ? "W" : "X";
    const labelY = view === "back" ? "Z" : (view === "side" ? "Z" : "Y");
    const rearDist = view === "back" ? "" : "  |  To rear: " + Math.max(0, d.len - xMm) + " mm";
    const el = document.getElementById("sb-cursor");
    el.textContent = labelX + ": " + xMm + ", " + labelY + ": " + yMm;
  }

  _hideMeasurement() {
    // cursor will update on next mousemove
  }

  /* ─── Drag from palette ─── */

  onPackageDragStart(e, pkg) {
    this.isDraggingFromPalette = true;
    this.dragPackageData = pkg;
    this._lastValidationTime = 0;
    this._lastSnapX = -1;
    this._lastSnapY = -1;
    this.lastValidResult = null;
    this._clearPreview();
  }

  _onDragOver(e) {
    e.preventDefault();
    if (!this.isDraggingFromPalette || !this.dragPackageData) return;
    const rect = this.stage.container().getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    this._showPreview(x, y);
    this._throttledValidate(x, y);
  }

  _onDragLeave(e) {
    this._clearPreview();
  }

  /* Find the nearest valid Z (height) for a package in side/back views.
     Returns an object { z, zTop } where z is the height and zTop is the
     visual-Y position from top for rendering. */
  _findValidPosition(pkg, horizMm, desiredZ) {
    const view = this.currentView;
    const dims = this._getViewDims();
    const pkgLen = pkg.length || pkg._length || 0;
    const pkgWid = pkg.width || pkg._width || 0;
    const pkgHei = pkg.height || pkg._height || 0;
    const pkgArea = pkgLen * pkgWid;
    const zMax = Math.max(0, dims.dim2 - pkgHei);
    const positions = [{ z: 0, dist: Math.abs(0 - desiredZ) }];

    for (const p of this.placements) {
      const pa = p._package || p;
      if (!pa || !pa.allow_stacking) continue;

      const belowTop = (p.z || 0) + (p._height || 0);
      if (belowTop > zMax) continue;
      const belowArea = (p._length || 0) * (p._width || 0);
      if (belowArea < pkgArea) continue;

      if (view === "side") {
        const belowX = p.x || 0;
        const belowW = p._length || 0;
        if (horizMm >= belowX && horizMm + pkgLen <= belowX + belowW) {
          positions.push({ z: belowTop, dist: Math.abs(belowTop - desiredZ) });
        }
      } else {
        const belowY = p.y || 0;
        const belowW = p._width || 0;
        if (horizMm >= belowY && horizMm + pkgWid <= belowY + belowW) {
          positions.push({ z: belowTop, dist: Math.abs(belowTop - desiredZ) });
        }
      }
    }

    positions.sort((a, b) => a.dist - b.dist);
    const best = positions[0];
    const z = Math.min(best.z, zMax);
    return { z, zTop: dims.dim2 - z - pkgHei };
  }

  /* Client-side quick validation for immediate preview feedback */
  _quickValidate(xMm, yMm, pkg) {
    const d = this._getViewDims();
    const view = this.currentView;
    const pl = (view === "back") ? pkg.width : pkg.length;
    const pw = (view === "top") ? pkg.width : pkg.height;
    if (pl <= 0 || pw <= 0) return { accepted: false, errors: ["Invalid dimensions"] };
    if (xMm < 0 || yMm < 0 || xMm + pl > d.dim1 || yMm + pw > d.dim2) {
      return { accepted: false, errors: ["Outside container boundary"] };
    }
    for (const p of this.placements) {
      let ex = p.x || 0, ey = p.y || 0;
      let ew = p._length || 0, eh = (view === "top") ? (p._width || 0) : (p._height || 0);
      if (view === "back") { ex = p.y || 0; ey = p.z || 0; ew = p._width || 0; }
      if (xMm < ex + ew && xMm + pl > ex && yMm < ey + eh && yMm + pw > ey) {
        return { accepted: false, errors: ["Collision with " + (p._name || "package")] };
      }
    }
    return { accepted: true, errors: [] };
  }

  _throttledValidate(stageX, stageY) {
    if (!this.dragPackageData || !this.currentVehicle) return;
    const mm = this._stageToMm(stageX, stageY);
    let snapX = mm.x;
    let snapY = mm.y;
    if (this.snapEnabled) {
      snapX = Math.round(snapX / this.gridSpacing) * this.gridSpacing;
      snapY = Math.round(snapY / this.gridSpacing) * this.gridSpacing;
    }
    const pkg = this.dragPackageData;
    const view = this.currentView;
    const pl = (view === "back") ? pkg.width : pkg.length;
    const pw = (view === "top") ? pkg.width : pkg.height;
    snapX -= pl / 2;
    snapY -= pw / 2;
    if (snapX < 0) snapX = 0;
    if (snapY < 0) snapY = 0;

    // Convert to container coordinates for back view
    if (view === "back") {
      const w = this._getViewDims().dim1;
      const containerY = w - snapX - pl;
      this.lastValidResult = this._quickValidate(containerY, snapY, pkg);
    } else {
      this.lastValidResult = this._quickValidate(snapX, snapY, pkg);
    }

    // Throttle API validation to avoid overwhelming server
    const now = Date.now();
    if (now - (this._lastValidationTime || 0) < 200) return;
    if (snapX === this._lastSnapX && snapY === this._lastSnapY) return;
    this._lastSnapX = snapX;
    this._lastSnapY = snapY;
    this._lastValidationTime = now;

    let px = snapX, py = snapY, pz = 0;
    if (view === "top") { px = snapX; py = snapY; }
    else if (view === "side") {
      px = snapX;
      const v = this._findValidPosition(pkg, snapX, snapY);
      pz = v.z;
    } else {
      const d2 = this._getViewDims();
      const containerY = d2.dim1 - snapX - pl;
      py = containerY;
      const v = this._findValidPosition(pkg, containerY, snapY);
      pz = v.z;
    }
    API.validate({
      vehicle_id: this.currentVehicle.vehicle_id,
      package_id: this.dragPackageData.id,
      x: px, y: py, z: pz, rotation: 0,
      existing_placements: this.placements.map(p => ({
        package_id: p.package_id,
        x: p.x, y: p.y, z: p.z || 0,
        rotation: p.rotation || 0,
        _name: p._name,
        _length: p._length,
        _width: p._width,
        _height: p._height,
        _weight_kg: p._weight_kg,
      })),
    }).then(result => {
      this.lastValidResult = result;
    }).catch(() => { });
  }

  async _onDrop(e) {
    e.preventDefault();
    if (!this.isDraggingFromPalette || !this.dragPackageData) return;
    if (!this.currentVehicle) {
      const first = this.vehicles.find(v => v.cc_id);
      if (first) {
        await this._selectVehicle(first.vehicle_id);
        UI.toast("Auto-selected vehicle: " + (first.plate_number || first.vehicle_id), "info");
      } else {
        UI.toast("No vehicle with a container config available", "warning");
        this._cancelPaletteDrag();
        return;
      }
    }

    const rect = this.stage.container().getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const mm = this._stageToMm(x, y);
    let snapX = mm.x;
    let snapY = mm.y;
    if (this.snapEnabled) {
      snapX = Math.round(snapX / this.gridSpacing) * this.gridSpacing;
      snapY = Math.round(snapY / this.gridSpacing) * this.gridSpacing;
    }
    const pkg = this.dragPackageData;
    const view = this.currentView;
    const pw = (view === "back") ? pkg.width : (view === "top") ? pkg.width : pkg.height;
    const pl = (view === "back") ? pkg.width : pkg.length;
    snapX -= pl / 2;
    snapY -= pw / 2;
    if (snapX < 0) snapX = 0;
    if (snapY < 0) snapY = 0;

    // Map canvas coordinates to container coordinates
    let placeX = snapX, placeY = snapY, placeZ = 0;
    if (view === "top") {
      placeX = snapX; placeY = snapY;
    } else if (view === "side") {
      placeX = snapX;
      const valid = this._findValidPosition(pkg, snapX, snapY);
      placeZ = valid.z;
    } else {
      const d2 = this._getViewDims();
      const containerY = d2.dim1 - snapX - pl;
      placeY = containerY;
      const valid = this._findValidPosition(pkg, containerY, snapY);
      placeZ = valid.z;
    }
    const payload = (this.currentContainer && this.currentContainer.payload_kg)
      || (this.currentVehicle && this.currentVehicle.payload_kg) || 0;
    const currentWeight = this.placements.reduce((s, p) => s + (p._weight_kg || 0), 0);
    if (payload > 0 && currentWeight + (pkg.weight_kg || 0) > payload) {
      UI.toast("Cannot place — adding " + pkg.name + " would exceed " + payload + " kg payload", "error");
      this._cancelPaletteDrag();
      return;
    }

    try {
      const result = await API.validate({
        vehicle_id: this.currentVehicle.vehicle_id,
        package_id: pkg.id,
        x: placeX, y: placeY, z: placeZ, rotation: 0,
        existing_placements: this.placements.map(p => ({
          package_id: p.package_id,
          x: p.x, y: p.y, z: p.z || 0,
          rotation: p.rotation || 0,
          _name: p._name,
          _length: p._length,
          _width: p._width,
          _height: p._height,
          _weight_kg: p._weight_kg,
        })),
      });

      if (result.accepted) {
        this._pushUndo();
        const seq = this.placements.length + 1;
        this.placements.push({
          package_id: pkg.id,
          x: placeX, y: placeY, z: placeZ, rotation: 0,
          load_sequence: seq,
          _name: pkg.name,
          _length: pkg.length,
          _width: pkg.width,
          _height: pkg.height,
          _weight_kg: pkg.weight_kg,
          _color: pkg.color,
          _package: { name: pkg.name, length: pkg.length, width: pkg.width, height: pkg.height, weight_kg: pkg.weight_kg, color: pkg.color, allow_stacking: !!pkg.allow_stacking },
        });
        this.renderCanvas();
        this.updateStatus();
        if (this._show3D) this.update3DScene();
        UI.toast(pkg.name + " placed", "success");
      } else {
        UI.toast((result.errors || []).join(", "), "error");
      }
    } catch (e) {
      UI.toast("Failed to validate placement", "error");
    }

    this._cancelPaletteDrag();
  }

  _cancelPaletteDrag() {
    this.isDraggingFromPalette = false;
    this.dragPackageData = null;
    this.lastValidResult = null;
    this._clearPreview();
  }

  /* ═══════════════════════ SELECTION ═══════════════════════ */

  _deselectPackage() {
    this.selectedIndex = -1;
    this._deselectAllShapes();
    this._hideInspector();
    this._syncPackageCardHighlight();
    this.renderCanvas();
  }

  _deselectAllShapes() {
    const shapes = this.packageLayer.find("Rect");
    for (const s of shapes) {
      s.strokeWidth(0.5);
      s.stroke("rgba(255,255,255,0.2)");
    }
    this.packageLayer.batchDraw();
  }

  deleteSelected() {
    if (this.selectedIndex < 0 || this.selectedIndex >= this.placements.length) return;
    this._pushUndo();
    const removed = this.placements[this.selectedIndex];
    this.placements.splice(this.selectedIndex, 1);
    this.selectedIndex = -1;

    // Re-sequence
    this.placements.forEach((p, i) => p.load_sequence = i + 1);

    this.renderCanvas();
    this.updateStatus();
    this._hideInspector();
    if (this._show3D) this.update3DScene();
    UI.toast("Package removed", "info");
  }

  rotateSelected(dir) {
    if (this.selectedIndex < 0 || this.selectedIndex >= this.placements.length) return;
    this._pushUndo();
    const p = this.placements[this.selectedIndex];
    let r = (p.rotation || 0) + dir * 90;
    if (r < 0) r += 360;
    if (r >= 360) r -= 360;
    p.rotation = r;
    document.getElementById("inspector-rotation").value = String(r);
    this.renderCanvas();
    this.updateStatus();
    if (this._show3D) this.update3DScene();
    UI.toast("Rotated to " + r + "&deg;", "info");
  }

  /* ═══════════════════════ AUTO ARRANGE ═══════════════════════ */

  async autoArrange() {
    // Gather packages from shipment items, or fall back to all packages
    let packages = [];
    if (this.currentShipment && this.currentShipment.items && this.currentShipment.items.length) {
      for (const item of this.currentShipment.items) {
        const qty = item.quantity || 1;
        for (let i = 0; i < qty; i++) {
          packages.push({
            package_id: item.package_id,
            name: item.package_name || "Package",
            length: item.length,
            width: item.width,
            height: item.height,
            weight_kg: item.weight_kg,
            color: item.color || "#3b82f6",
            allow_stacking: item.allow_stacking,
          });
        }
      }
    } else if (this.packages && this.packages.length) {
      for (const pkg of this.packages) {
        const qty = pkg.default_qty || 1;
        for (let i = 0; i < qty; i++) {
          packages.push({
            package_id: pkg.id,
            name: pkg.name,
            length: pkg.length,
            width: pkg.width,
            height: pkg.height,
            weight_kg: pkg.weight_kg,
            color: pkg.color || "#3b82f6",
            allow_stacking: pkg.allow_stacking,
          });
        }
      }
    }

    if (packages.length === 0) {
      UI.toast("No packages to arrange. Add packages or select a shipment first.", "warning");
      return;
    }

    // Read selected optimization profile
    const profileSelect = document.getElementById("profile-select");
    const profileName = profileSelect ? profileSelect.value : "balanced";

    const payload = {
      strategy: "optimized",
      profile: profileName,
    };

    if (this.currentShipment && this.currentShipment.id) {
      payload.shipment_id = this.currentShipment.id;
    } else {
      payload.packages = packages;
    }

    const btn = document.querySelector('[onclick*="autoArrange"]');
    if (btn) { btn.disabled = true; btn.textContent = "Arranging..."; }

    // Show optimization status
    const statusEl = document.getElementById("optimization-status");
    if (statusEl) {
      const labels = { fast: "\u26a1 Fast", balanced: "\u2696 Balanced", maximum_quality: "\ud83c\udfaf Maximum Quality" };
      statusEl.textContent = "Optimization: " + (labels[profileName] || profileName);
      statusEl.style.display = "";
    }

    const labels = { fast: "Fast", balanced: "Balanced", maximum_quality: "Maximum Quality" };
    this.showProgressModal("Arranging " + packages.length + " packages", labels[profileName] || profileName);

    try {
      const resp = await fetch("/api/tlp/auto-arrange", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await resp.json().catch(() => null);

      if (!resp.ok || !data || data.error) {
        this.hideProgressModal();
        UI.toast((data && data.error) || `Auto Arrange failed (HTTP ${resp.status})`, "error");
        return;
      }

      // ── Instrument: Representation 4 — JSON received by frontend ────
      console.log("=== INSTRUMENT REP 4: JSON received from auto-arrange ===");
      console.log(JSON.stringify({
        trace_id: "frontend-" + Date.now(),
        rep: 4,
        label: "json-received-by-frontend",
        multi_vehicle: data.multi_vehicle,
        placements: (data.placements || []).map(p => ({
          package_id: p.package_id,
          x: p.x, y: p.y, z: p.z,
          rotation: p.rotation,
          load_sequence: p.load_sequence,
          vehicle_id: p.vehicle_id,
          _name: p._name,
          _length: p._length, _width: p._width, _height: p._height,
          _color: p._color,
        })),
        per_vehicle: (data.per_vehicle || []).map(v => ({
          vehicle_id: v.vehicle_id,
          plate_number: v.plate_number,
          package_count: v.package_count,
        })),
      }, null, 2));

      this.selectedIndex = -1;
      this._arrangePlacements = data.placements || [];
      const s = data.summary || {};
      const perV = data.per_vehicle || [];

      // Store per-vehicle results
      this._arrangeResults = perV.map(v => ({
        vehicle_id: v.vehicle_id,
        plate_number: v.plate_number || "Veh#" + v.vehicle_id,
        package_count: v.package_count,
      }));
      this._updateTotalSorted();

      // Load first vehicle's placements into the viewer
      if (perV.length) {
        const firstVeh = this.vehicles.find(v => v.vehicle_id == perV[0].vehicle_id);
        if (firstVeh) {
          await this._selectVehicle(firstVeh.vehicle_id);
          this.placements = this._arrangePlacements.filter(p => p.vehicle_id == perV[0].vehicle_id) || [];
          this.renderCanvas();
          this.updateStatus();
          // Auto-enable 3D view for step animation (after vehicle is selected)
          if (!this._show3D) {
            this._show3D = true;
            const btn = document.getElementById("btn-3d-toggle");
            if (btn) btn.classList.add("active");
            const container = document.getElementById("tlp-3d-container");
            if (container) container.style.display = "";
            this._init3D();
          }
          this.update3DScene(true);
          this._startStepMode(this.placements);
          this._hideInspector();
        } else {
          this.placements = this._arrangePlacements;
        }
      } else {
        this.placements = this._arrangePlacements;
      }

      // Show arrange results in sidebar
      this._renderArrangeResults();

      this._pushUndo();
      const parts = perV.map(v => `${v.plate_number || "Veh#" + v.vehicle_id}: ${v.package_count} pkgs`);
      const msg = `Distributed: ${s.placed_packages} placed, ${s.failed_packages} failed — ${parts.join(", ")}`;
      UI.toast(msg, s.failed_packages > 0 ? "warning" : "success");

      // Show profile statistics if available
      if (data.profile_stats) {
        const ps = data.profile_stats;
        if (statusEl) {
          const labels = { fast: "\u26a1 Fast", balanced: "\u2696 Balanced", maximum_quality: "\ud83c\udfaf Maximum Quality" };
          statusEl.textContent = (labels[ps.profile] || ps.profile)
            + " \u2014 " + (ps.total_time_ms / 1000).toFixed(1) + "s"
            + (ps.repair_passes > 0 ? " \u00b7 " + ps.repair_passes + " repair passes" : "");
        }
      }

      if (data.debug_log && data.debug_log.length) {
        console.log("Auto Arrange debug log:", data.debug_log);
      }
    } catch (e) {
      console.error("Auto Arrange failed:", e);
      const msg = e instanceof TypeError ? "Network error — is the server running?" : "Auto Arrange request failed";
      UI.toast(msg, "error");
      if (statusEl) { statusEl.style.display = "none"; }
    } finally {
      this.hideProgressModal();
      if (btn) { btn.disabled = false; btn.textContent = "\u2728 Auto Arrange"; }
    }
  }

  /* ─── Arrange Results ──────────────────────────────────────────── */

  _renderArrangeResults() {
    const section = document.getElementById("arrange-results-section");
    const list = document.getElementById("arrange-results-list");
    if (!section || !list) return;
    if (!this._arrangeResults || !this._arrangeResults.length) {
      section.style.display = "none";
      return;
    }
    section.style.display = "";
    list.innerHTML = "";
    for (const r of this._arrangeResults) {
      const active = r.vehicle_id == (this.currentVehicle ? this.currentVehicle.vehicle_id : null);
      const row = document.createElement("div");
      row.className = "tlp-vehicle-row";
      row.style.cssText = "cursor:pointer;padding:4px 6px;border-radius:4px;" + (active ? "background:rgba(47,140,235,0.15);" : "");
      row.innerHTML = `
        <span class="tlp-vehicle-label">${UI.escapeHtml(r.plate_number)}</span>
        <span class="tlp-vehicle-value">${r.package_count} pkgs</span>
      `;
      row.onclick = async () => {
        if (this._stepMode) {
          this._stepClearPermanent();
          this._stepEndMode();
        }
        const veh = this.vehicles.find(v => v.vehicle_id == r.vehicle_id);
        if (!veh) return;
        await this._selectVehicle(r.vehicle_id);
        this.placements = (this._arrangePlacements || []).filter(p => p.vehicle_id == r.vehicle_id) || [];
        this.renderCanvas();
        this.updateStatus();
        if (this._show3D) {
          await new Promise(r2 => setTimeout(r2, 50));
          this.update3DScene(true);
          this._startStepMode(this.placements);
        }
        this._renderArrangeResults();
        this._hideInspector();
      };
      list.appendChild(row);
    }
  }

  /* ─── Inspector ─── */

  _showInspector(index) {
    if (index < 0 || index >= this.placements.length) { this._hideInspector(); return; }
    const p = this.placements[index];
    document.getElementById("inspector-panel").style.display = "";
    document.getElementById("inspector-name").textContent = p._name || "Package #" + (index + 1);
    this._ignoreInspectorChange = true;
    document.getElementById("inspector-x").value = Math.round(p.x || 0);
    document.getElementById("inspector-y").value = Math.round(p.y || 0);
    document.getElementById("inspector-z").value = Math.round(p.z || 0);
    document.getElementById("inspector-rotation").value = String(p.rotation || 0);
    document.getElementById("inspector-weight").textContent = (p._weight_kg || 0) + " kg";
    this._ignoreInspectorChange = false;
  }

  _hideInspector() {
    document.getElementById("inspector-panel").style.display = "none";
  }

  updateSelectedPosition() {
    if (this._ignoreInspectorChange || this.selectedIndex < 0) return;
    this._pushUndo();
    const p = this.placements[this.selectedIndex];
    p.x = parseFloat(document.getElementById("inspector-x").value) || 0;
    p.y = parseFloat(document.getElementById("inspector-y").value) || 0;
    p.z = parseFloat(document.getElementById("inspector-z").value) || 0;
    this.renderCanvas();
    this.updateStatus();
    if (this._show3D) this.update3DScene();
    this._showInspector(this.selectedIndex);
  }

  updateSelectedRotation() {
    if (this._ignoreInspectorChange || this.selectedIndex < 0) return;
    this._pushUndo();
    const p = this.placements[this.selectedIndex];
    p.rotation = parseInt(document.getElementById("inspector-rotation").value, 10) || 0;
    this.renderCanvas();
    this.updateStatus();
    if (this._show3D) this.update3DScene();
  }

  duplicateSelected() {
    if (this.selectedIndex < 0) return;
    const src = this.placements[this.selectedIndex];
    this._pushUndo();
    const seq = this.placements.length + 1;
    const dup = JSON.parse(JSON.stringify(src));
    dup.x = (dup.x || 0) + 50;
    dup.y = (dup.y || 0) + 50;
    dup.load_sequence = seq;
    this.placements.push(dup);
    this.selectedIndex = this.placements.length - 1;
    this.renderCanvas();
    this.updateStatus();
    this._showInspector(this.selectedIndex);
    if (this._show3D) this.update3DScene();
    UI.toast("Package duplicated", "success");
  }

  /* ═══════════════════════ UNDO / REDO ═══════════════════════ */

  _pushUndo() {
    this.undoStack.push(JSON.stringify(this.placements));
    if (this.undoStack.length > this.maxUndo) this.undoStack.shift();
    this.redoStack = [];
  }

  undo() {
    if (this.undoStack.length === 0) return;
    this.redoStack.push(JSON.stringify(this.placements));
    const state = JSON.parse(this.undoStack.pop());
    this.placements = state;
    this.selectedIndex = -1;
    this.renderCanvas();
    this.updateStatus();
    UI.toast("Undo", "info");
  }

  redo() {
    if (this.redoStack.length === 0) return;
    this.undoStack.push(JSON.stringify(this.placements));
    const state = JSON.parse(this.redoStack.pop());
    this.placements = state;
    this.selectedIndex = -1;
    this.renderCanvas();
    this.updateStatus();
    UI.toast("Redo", "info");
  }

  /* ═══════════════════════ VALIDATION ═══════════════════════ */

  /**
   * Re-validate a placement against the real backend rules (collision,
   * weight, support/stacking, door access) after a manual drag/rotate —
   * the client-side checklist in updateValidationUI() has no support
   * check at all, so a manually-created unsupported/unstable placement
   * would otherwise still show "All checks passed".
   * @param {number} [movedIndex] - index of the placement that just
   *   changed; omitted falls back to the client-only checklist.
   */
  async _validateAllPlacements(movedIndex) {
    if (!this.currentVehicle || this.placements.length === 0) return;
    if (movedIndex == null || movedIndex < 0 || movedIndex >= this.placements.length) {
      this.updateValidationUI();
      return;
    }
    const moved = this.placements[movedIndex];
    try {
      const result = await API.validate({
        vehicle_id: this.currentVehicle.vehicle_id,
        package_id: moved.package_id,
        x: moved.x, y: moved.y, z: moved.z || 0, rotation: moved.rotation || 0,
        existing_placements: this.placements
          .filter((_, idx) => idx !== movedIndex)
          .map(p => ({
            package_id: p.package_id,
            x: p.x, y: p.y, z: p.z || 0,
            rotation: p.rotation || 0,
            _name: p._name,
            _length: p._length,
            _width: p._width,
            _height: p._height,
            _weight_kg: p._weight_kg,
          })),
      });
      this.updateValidationUI(result);
    } catch (e) {
      console.error("_validateAllPlacements error", e);
      this.updateValidationUI();
    }
  }

  updateValidationUI(result) {
    const list = document.getElementById("tlp-validation-list");
    const items = list.querySelectorAll(".tlp-val-item");

    if (!this.currentVehicle) {
      items.forEach(el => { el.className = "tlp-val-item neutral"; el.querySelector(".icon").textContent = "\u25CB"; });
      return;
    }

    const d = this._getContainerDims();
    const payload = this.currentContainer
      ? this.currentContainer.payload_kg
      : (this.currentVehicle ? this.currentVehicle.payload_kg : 0);

    let totalWeight = 0;
    let totalVol = 0;
    let hasCollision = false;
    let hasOutside = false;
    for (let i = 0; i < this.placements.length; i++) {
      const p = this.placements[i];
      totalWeight += p._weight_kg || 0;
      totalVol += (p._length || 0) * (p._width || 0) * (p._height || 0) / 1e9;
      // Check boundary
      if ((p.x + (p._length || 0)) > d.len || (p.y + (p._width || 0)) > d.wid) {
        hasOutside = true;
      }
    }

    const volCap = d.len * d.wid * d.hei / 1e9;
    const weightOk = totalWeight <= payload;
    const volOk = totalVol <= volCap;
    const insideOk = !hasOutside;

    // Collision check (simple pairwise)
    let collisionOk = true;
    for (let i = 0; i < this.placements.length; i++) {
      for (let j = i + 1; j < this.placements.length; j++) {
        const a = this.placements[i];
        const b = this.placements[j];
        if (a.x < b.x + (b._length || 0) && a.x + (a._length || 0) > b.x &&
          a.y < b.y + (b._width || 0) && a.y + (a._width || 0) > b.y &&
          (a.z || 0) < (b.z || 0) + (b._height || 0) && (a.z || 0) + (a._height || 0) > (b.z || 0)) {
          collisionOk = false;
        }
      }
    }

    // Door check
    const features = (this.currentContainer && this.currentContainer.features)
      || (this.currentVehicle && this.currentVehicle.features) || [];
    const hasRearDoor = features.some(f => (f.feature_type || f) === "rear_door");
    const hasSideDoor = features.some(f => (f.feature_type || f) === "side_door");
    const rearBlocked = this.placements.some(p => (p.x + (p._length || 0)) > (d.len - 100));
    const sideBlocked = hasSideDoor
      ? this.placements.some(p => (p.y + (p._width || 0)) > (d.wid - 100))
      : false;
    const doorOk = !rearBlocked && !sideBlocked;

    const checks = [
      { el: items[0], pass: insideOk, label: "Inside container" },
      { el: items[1], pass: collisionOk, label: "No collision" },
      { el: items[2], pass: weightOk, label: "Weight OK" },
      { el: items[3], pass: volOk, label: "Volume OK" },
      { el: items[4], pass: doorOk, label: "Doors accessible" },
    ];

    let allValid = true;
    for (const c of checks) {
      if (!c.el) continue;
      if (this.placements.length === 0) {
        c.el.className = "tlp-val-item neutral";
        c.el.querySelector(".icon").textContent = "\u25CB";
        c.el.childNodes[1].textContent = " " + c.label;
      } else if (c.pass) {
        c.el.className = "tlp-val-item valid";
        c.el.querySelector(".icon").textContent = "\u2713";
      } else {
        c.el.className = "tlp-val-item invalid";
        c.el.querySelector(".icon").textContent = "\u2717";
        allValid = false;
      }
    }

    // Backend validation result (from _validateAllPlacements, run after a
    // manual drag/rotate) can override the pass verdict even when every
    // client-side check above looks fine \u2014 the checklist has no support/
    // stacking check at all, so this is the only way a manually-created
    // unsupported placement gets flagged instead of silently reading as
    // "All checks passed".
    let backendReason = null;
    if (result && result.accepted === false) {
      allValid = false;
      backendReason = (result.errors && result.errors[0]) || "Backend validation failed";
    }

    const sbVal = document.getElementById("sb-validation");
    if (this.placements.length === 0) {
      sbVal.textContent = "Ready";
      sbVal.style.color = "var(--success)";
    } else if (allValid) {
      sbVal.textContent = "All checks passed";
      sbVal.style.color = "var(--success)";
    } else {
      sbVal.textContent = backendReason ? ("Issues detected: " + backendReason) : "Issues detected";
      sbVal.style.color = "var(--danger)";
    }
  }

  /* ═══════════════════════ STATUS PANEL ═══════════════════════ */

  updateStatus() {
    const count = this.placements.length;
    const totalItems = this._getTotalPackageCount();
    document.getElementById("status-count-now").textContent = count;
    document.getElementById("status-count-total").textContent = totalItems;

    // Weight
    let totalKg = 0;
    for (const p of this.placements) totalKg += p._weight_kg || 0;
    const payload = (this.currentContainer && this.currentContainer.payload_kg)
      || (this.currentVehicle && this.currentVehicle.payload_kg) || 0;
    document.getElementById("status-weight-now").textContent = totalKg.toFixed(1) + " kg";
    document.getElementById("status-weight-max").textContent = payload + " kg";

    const wPct = payload > 0 ? Math.min(100, (totalKg / payload) * 100) : 0;
    const wBar = document.getElementById("status-weight-bar");
    wBar.style.width = wPct + "%";
    wBar.className = "tlp-progress-fill " + (wPct > 90 ? "red" : wPct > 70 ? "yellow" : "green");

    // Volume
    let totalM3 = 0;
    for (const p of this.placements) {
      totalM3 += (p._length * p._width * p._height) / 1_000_000_000;
    }
    const d = this._getContainerDims();
    const capacityM3 = (d.len * d.wid * d.hei) / 1_000_000_000;
    document.getElementById("status-vol-now").textContent = totalM3.toFixed(2) + " m\u00B3";
    document.getElementById("status-vol-max").textContent = capacityM3.toFixed(2) + " m\u00B3";

    const vPct = capacityM3 > 0 ? Math.min(100, (totalM3 / capacityM3) * 100) : 0;
    const vBar = document.getElementById("status-vol-bar");
    vBar.style.width = vPct + "%";
    vBar.className = "tlp-progress-fill " + (vPct > 90 ? "red" : vPct > 70 ? "yellow" : "green");

    // Floor utilization — only z===0 placements occupy floor area; a
    // stacked package sits on top of another one, not on new floor space
    // (matches the backend's floor_used_pct, engine/statistics.py).
    const floorArea = d.len * d.wid;
    let usedArea = 0;
    for (const p of this.placements) {
      if (p.z === 0) usedArea += (p._length || 0) * (p._width || 0);
    }
    const floorPct = floorArea > 0 ? Math.min(100, (usedArea / floorArea) * 100) : 0;
    document.getElementById("status-floor").textContent = Math.round(floorPct) + "%";

    // Doors
    this._updateDoorStatus();

    // Validation
    this.updateValidationUI();

    // Placement order
    this._updateSequence();

    // Package cards (update placed counts)
    this.filterPackages();

    // Vehicle remaining
    this._updateVehicleInfo();

    // Total sorted across all vehicles
    this._updateTotalSorted();
  }

  _getTotalPackageCount() {
    if (this.currentShipment) {
      let total = 0;
      for (const item of this.currentShipment.items || []) {
        total += item.quantity || 0;
      }
      return total;
    }
    return this.placements.length;
  }

  _updateDoorStatus() {
    const features = (this.currentContainer && this.currentContainer.features)
      || (this.currentVehicle && this.currentVehicle.features) || [];
    const d = this._getContainerDims();
    const hasRearDoor = features.some(f => (f.feature_type || f) === "rear_door");
    const hasSideDoor = features.some(f => (f.feature_type || f) === "side_door");

    const rearBlocked = this.placements.some(p => (p.x + (p._length || 0)) > (d.len - 100));
    const sideBlocked = hasSideDoor
      ? this.placements.some(p => (p.y + (p._width || 0)) > (d.wid - 100))
      : false;

    const setDoor = (id, has, blocked) => {
      const el = document.getElementById(id);
      if (!has) { el.textContent = "—"; el.className = "tlp-door-badge na"; return; }
      el.textContent = blocked ? "Blocked" : "Accessible";
      el.className = "tlp-door-badge " + (blocked ? "blocked" : "accessible");
    };

    setDoor("door-rear", true, rearBlocked);
    setDoor("door-side", hasSideDoor, sideBlocked);
  }

  _updateSequence() {
    const el = document.getElementById("tlp-sequence-list");
    if (this.placements.length === 0) {
      el.innerHTML = '<div class="tlp-empty-hint">No packages placed</div>';
      return;
    }
    const sorted = [...this.placements].sort((a, b) => (a.load_sequence || 0) - (b.load_sequence || 0));
    el.innerHTML = sorted.map(p => `
      <div class="tlp-seq-item">
        <span class="tlp-seq-num">${p.load_sequence || "?"}</span>
        <span>${UI.escapeHtml(p._name || "Unknown")}</span>
      </div>
    `).join("");
  }

  _updateVehicleInfo() {
    if (!this.currentVehicle) {
      document.getElementById("v-name").textContent = "—";
      document.getElementById("v-plate").textContent = "—";
      document.getElementById("v-driver").textContent = "—";
      document.getElementById("v-dims").textContent = "—";
      document.getElementById("v-payload").textContent = "—";
      document.getElementById("v-remaining").textContent = "—";
      document.getElementById("tb-vehicle-name").textContent = "—";
      return;
    }
    const v = this.currentVehicle;
    const cc = this.currentContainer;
    document.getElementById("v-name").textContent = (cc && cc.name) || v.vehicle_type || "—";
    document.getElementById("v-plate").textContent = v.plate_number || "—";
    document.getElementById("v-driver").textContent = v.current_driver || "—";
    document.getElementById("v-dims").textContent = (cc && cc.cargo_length_mm) || (v && v.cargo_length_mm) || "—";
    document.getElementById("v-payload").textContent = ((cc && cc.payload_kg) || (v && v.payload_kg) || "—") + " kg";

    const payload = (cc && cc.payload_kg) || (v && v.payload_kg) || 0;
    let totalKg = 0;
    for (const p of this.placements) totalKg += p._weight_kg || 0;
    const remaining = payload - totalKg;
    document.getElementById("v-remaining").textContent = Math.max(0, remaining).toFixed(1) + " kg";
    document.getElementById("tb-vehicle-name").textContent = v.plate_number || "—";

    // Format dims
    const len = (cc && cc.cargo_length_mm) || v.cargo_length_mm || 0;
    const wid = (cc && cc.cargo_width_mm) || v.cargo_width_mm || 0;
    const hei = (cc && cc.cargo_height_mm) || v.cargo_height_mm || 0;
    const dimsStr = len + "\u00D7" + wid + "\u00D7" + hei + " mm";
    const dimsEl = document.getElementById("v-dims");
    dimsEl.textContent = dimsStr;
    dimsEl.title = len + " x " + wid + " x " + hei + " mm";
  }

  _updateTotalSorted() {
    try {
      const total = (this._arrangePlacements || []).length;
      const totalEl = document.getElementById("status-sorted-total");
      if (totalEl) totalEl.textContent = total;

      const perVehCounts = {};
      for (const p of this._arrangePlacements || []) {
        const vid = p.vehicle_id;
        if (!perVehCounts[vid]) perVehCounts[vid] = 0;
        perVehCounts[vid]++;
      }
      const parts = [];
      for (const [vid, count] of Object.entries(perVehCounts)) {
        const veh = this.vehicles.find(v => v.vehicle_id == vid);
        const label = veh ? veh.plate_number : "Veh#" + vid;
        parts.push(label + ": " + count);
      }
      const vehEl = document.getElementById("status-sorted-vehicles");
      if (vehEl) vehEl.textContent = parts.length ? parts.join(", ") : "—";
    } catch (e) {
      console.warn("Error updating total sorted:", e);
    }
  }

  _updateStatusBarScale() {
    const scale = this._getCurrentScale();
    document.getElementById("sb-scale").textContent = scale > 0
      ? "1 px = " + (1 / scale).toFixed(1) + " mm"
      : "—";
  }

  _updateStatusBarZoom() {
    document.getElementById("sb-zoom").textContent = Math.round(this.viewScale * 100) + "%";
  }

  /* ═══════════════════════ VIEW CONTROLS ═══════════════════════ */

  switchView(view) {
    if (!this.currentVehicle) return;
    document.querySelectorAll("#view-controls .view-btn[data-view]").forEach(b =>
      b.classList.toggle("active", b.dataset.view === view)
    );
    this.currentView = view;
    this.viewOffsetX = 0;
    this.viewOffsetY = 0;
    this.viewScale = 1;
    this.renderCanvas();
  }

  resetView() {
    this.viewOffsetX = 0;
    this.viewOffsetY = 0;
    this.viewScale = 1;
    this.renderCanvas();
    this._updateStatusBarZoom();
  }

  zoomIn() {
    this.viewScale = Math.min(10, this.viewScale * 1.25);
    this.renderCanvas();
    this._updateStatusBarZoom();
  }

  zoomOut() {
    this.viewScale = Math.max(0.05, this.viewScale * 0.8);
    this.renderCanvas();
    this._updateStatusBarZoom();
  }

  fitToScreen() {
    this.viewOffsetX = 0;
    this.viewOffsetY = 0;
    this.viewScale = 1;
    this.renderCanvas();
    this._updateStatusBarZoom();
  }

  toggleGrid() {
    this.gridEnabled = !this.gridEnabled;
    document.getElementById("btn-toggle-grid").style.opacity = this.gridEnabled ? "1" : "0.4";
    document.getElementById("btn-grid-toggle").classList.toggle("active", this.gridEnabled);
    this.renderCanvas();
  }

  toggleSnap() {
    this.snapEnabled = !this.snapEnabled;
    document.getElementById("btn-toggle-snap").style.opacity = this.snapEnabled ? "1" : "0.4";
    UI.toast("Snap " + (this.snapEnabled ? "ON" : "OFF"), "info");
  }

  /* ═══════════════════════ PACKAGE LIST ═══════════════════════ */

  setPkgTab(tab) {
    this._pkgTab = tab;
    document.getElementById("pkg-tab-unplaced").classList.toggle("active", tab === "unplaced");
    document.getElementById("pkg-tab-placed").classList.toggle("active", tab === "placed");
    this.filterPackages();
  }

  filterPackages() {
    const search = document.getElementById("pkg-search-input").value.toLowerCase().trim();
    const tab = this._pkgTab || "unplaced";

    const placedCounts = {};
    for (const p of this.placements) {
      placedCounts[p.package_id] = (placedCounts[p.package_id] || 0) + 1;
    }

    // If a shipment is selected, only show its packages
    let pool = this.packages;
    if (this.currentShipment) {
      const shipmentPkgIds = new Set((this.currentShipment.items || []).map(i => i.package_id));
      pool = pool.filter(p => shipmentPkgIds.has(p.id));
    }
    if (search) {
      pool = pool.filter(p => p.name.toLowerCase().includes(search));
    }

    const sortByWeightAndSize = (a, b) => {
      const volA = (a.length || 0) * (a.width || 0) * (a.height || 0);
      const volB = (b.length || 0) * (b.width || 0) * (b.height || 0);
      if (b.weight_kg !== a.weight_kg) return b.weight_kg - a.weight_kg;
      return volB - volA;
    };

    const unplaced = pool.filter(p => !placedCounts[p.id] || placedCounts[p.id] < this._getMaxQty(p.id)).sort(sortByWeightAndSize);
    const placed = pool.filter(p => placedCounts[p.id] > 0 && placedCounts[p.id] >= this._getMaxQty(p.id)).sort(sortByWeightAndSize);

    if (tab === "unplaced") this._populatePackageList(unplaced, placedCounts);
    else this._populatePackageList(placed, placedCounts);
  }

  _getMaxQty(pkgId) {
    if (this.currentShipment) {
      const item = (this.currentShipment.items || []).find(i => i.package_id === pkgId);
      return item ? item.quantity : Infinity;
    }
    const pkg = this.packages.find(p => p.id === pkgId);
    return pkg && pkg.default_qty ? pkg.default_qty : Infinity;
  }

  _getPackageVehicleMap() {
    const map = {};
    // From auto-arrange results (multi-vehicle)
    for (const p of this._arrangePlacements || []) {
      const key = p.package_id || p._name;
      if (!key) continue;
      if (!map[key]) map[key] = new Set();
      const veh = this.vehicles.find(v => v.vehicle_id == p.vehicle_id);
      if (veh) map[key].add(veh.plate_number || "Veh#" + p.vehicle_id);
    }
    // From current manual placements
    for (const p of this.placements || []) {
      const key = p.package_id || p._name;
      if (!key) continue;
      if (!map[key]) map[key] = new Set();
      if (this.currentVehicle) {
        map[key].add(this.currentVehicle.plate_number || "Veh#" + this.currentVehicle.vehicle_id);
      }
    }
    return map;
  }

  _syncPackageCardHighlight() {
    const cards = document.querySelectorAll("#tlp-package-list .tlp-pkg-card");
    for (const card of cards) {
      const pid = parseInt(card.dataset.packageId, 10);
      const pname = card.dataset.packageName;
      const isSelected = this.placements[this.selectedIndex] &&
        (this.placements[this.selectedIndex].package_id == pid ||
          this.placements[this.selectedIndex]._name === pname);
      card.classList.toggle("selected", isSelected);
    }
  }

  _onPackageCardClick(e, pkg) {
    // Stop if clicked on edit/delete button
    if (e.target.closest("button")) return;
    if (e.target.closest('[onclick]')) return;

    // Find first matching placement in current vehicle
    let match = null;
    let matchIdx = -1;
    for (let i = 0; i < this.placements.length; i++) {
      const p = this.placements[i];
      if (p.package_id == pkg.id || p._name === pkg.name) {
        match = p;
        matchIdx = i;
        break;
      }
    }

    const doSelect = (placements, idx) => {
      this.placements = placements;
      this.selectedIndex = idx;
      this.renderCanvas();
      this.updateStatus();
      this._syncPackageCardHighlight();
      this._showInspector(idx);
      this._focusOnPackage(placements[idx]);
      if (this._show3D) this.update3DScene();
    };

    if (matchIdx >= 0) {
      doSelect(this.placements, matchIdx);
      return;
    }

    // Not in current vehicle — search across all auto-arrange placements
    if (this._arrangePlacements && this._arrangePlacements.length) {
      let found = null;
      for (const p of this._arrangePlacements) {
        if (p.package_id == pkg.id || p._name === pkg.name) {
          found = p;
          break;
        }
      }
      if (found) {
        const veh = this.vehicles.find(v => v.vehicle_id == found.vehicle_id);
        if (veh) {
          this._selectVehicle(veh.vehicle_id).then(() => {
            const vPlacements = this._arrangePlacements.filter(p => p.vehicle_id == veh.vehicle_id) || [];
            const idx = vPlacements.findIndex(p => p.package_id == pkg.id || p._name === pkg.name);
            if (idx >= 0) {
              doSelect(vPlacements, idx);
            }
          });
          return;
        }
      }
    }

    UI.toast("Package not found in any vehicle", "warning");
  }

  _focusOnPackage(placement) {
    const view = this.currentView;
    const d = this._getViewDims();
    if (!d || d.dim1 <= 0 || d.dim2 <= 0) return;

    // Get package position in mm
    let px, py, pw, ph;
    if (view === "top") {
      px = placement.x || 0; py = placement.y || 0;
      pw = placement._length || 0; ph = placement._width || 0;
      if (placement.rotation === 90 || placement.rotation === 270) {
        let t = pw; pw = ph; ph = t;
      }
    } else if (view === "side") {
      px = placement.x || 0; py = d.dim2 - (placement.z || 0) - (placement._height || 0);
      pw = placement._length || 0; ph = placement._height || 0;
    } else {
      px = d.dim1 - (placement.y || 0) - (placement._width || 0); py = d.dim2 - (placement.z || 0) - (placement._height || 0);
      pw = placement._width || 0; ph = placement._height || 0;
    }

    const centerX = px + pw / 2;
    const centerY = py + ph / 2;

    const base = this._computeBaseScale();
    if (base <= 0) return;
    const padX = (this.canvasW - d.dim1 * base) / 2;
    const padY = (this.canvasH - d.dim2 * base) / 2;

    // Center the package in the viewport
    this.viewOffsetX = this.canvasW / 2 - (centerX * base + padX);
    this.viewOffsetY = this.canvasH / 2 - (centerY * base + padY);
    this.viewScale = 1;
    this.renderCanvas();
    this._updateStatusBarZoom();
  }

  _populatePackageList(packages, placedCounts) {
    const container = document.getElementById("tlp-package-list");
    container.innerHTML = "";
    if (!packages || packages.length === 0) {
      const hint = this._pkgTab === "unplaced" ? "All packages placed" : "No packages placed yet";
      container.innerHTML = '<div class="tlp-empty-hint" style="padding:12px;text-align:center;">' + hint + '</div>';
      return;
    }

    const pkgVehicleMap = this._getPackageVehicleMap();

    for (const pkg of packages) {
      const placed = placedCounts ? (placedCounts[pkg.id] || 0) : 0;
      const total = this._getMaxQty(pkg.id);
      const allPlaced = placed >= total;

      const card = document.createElement("div");
      card.className = "tlp-pkg-card" + (allPlaced ? " placed-all" : "");
      card.draggable = !allPlaced;
      card.dataset.packageId = pkg.id;
      card.dataset.packageName = pkg.name;

      const swatch = document.createElement("div");
      swatch.className = "tlp-pkg-swatch";
      swatch.style.background = pkg.color || "#3b82f6";

      const info = document.createElement("div");
      info.className = "tlp-pkg-info";

      // Show vehicle info for placed packages
      const vehiclePlates = pkgVehicleMap[pkg.id] || pkgVehicleMap[pkg.name];
      const vehicleStr = vehiclePlates && vehiclePlates.size > 0
        ? '<span style="font-size:9px;color:var(--accent);display:block;">\u26FD ' + [...vehiclePlates].join(", ") + '</span>'
        : "";

      const stackingLabel = pkg.allow_stacking ? '<span class="tlp-stack-badge stackable">Stackable</span>' : '<span class="tlp-stack-badge non-stackable">Non-stackable</span>';

      info.innerHTML = `
        <div class="tlp-pkg-name">${UI.escapeHtml(pkg.name)} ${stackingLabel}</div>
        <div class="tlp-pkg-dims">${pkg.length}\u00D7${pkg.width}\u00D7${pkg.height} mm &middot; ${pkg.weight_kg} kg</div>
        ${vehicleStr}
      `;

      const actions = document.createElement("div");
      actions.style.cssText = "display:flex;align-items:center;gap:2px;flex-shrink:0;";
      const editBtn = document.createElement("button");
      editBtn.innerHTML = "&#9998;";
      editBtn.title = "Edit dimensions";
      editBtn.style.cssText = "background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:10px;padding:2px;";
      editBtn.onclick = (e) => { e.stopPropagation(); this.openPackageEditor(pkg); };
      actions.appendChild(editBtn);
      const delBtn = document.createElement("button");
      delBtn.innerHTML = "&#128465;";
      delBtn.title = "Delete package";
      delBtn.style.cssText = "background:none;border:none;color:var(--danger);cursor:pointer;font-size:10px;padding:2px;";
      delBtn.onclick = (e) => { e.stopPropagation(); this.deletePackage(pkg.id, pkg.name); };
      actions.appendChild(delBtn);

      const totalStr = Number.isFinite(total) ? total : "&infin;";
      const qty = document.createElement("div");
      qty.className = "tlp-pkg-qty";
      qty.innerHTML = (allPlaced || placed > 0)
        ? "Placed <strong>" + placed + "</strong> / " + totalStr
        : "Qty <strong>" + totalStr + "</strong>";

      card.appendChild(swatch);
      card.appendChild(info);
      card.appendChild(actions);
      card.appendChild(qty);

      if (!allPlaced) {
        card.addEventListener("dragstart", (e) => this.onPackageDragStart(e, pkg));
      }

      card.addEventListener("click", (e) => this._onPackageCardClick(e, pkg));

      container.appendChild(card);
    }
    this._syncPackageCardHighlight();
  }

  /* ─── Inline Package Editor ─── */

  _nextPackageColor() {
    const used = new Set((this.packages || []).map(p => p.color).filter(Boolean));
    const palette = [
      "#3b82f6", "#ef4444", "#10b981", "#f59e0b", "#8b5cf6",
      "#ec4899", "#06b6d4", "#f97316", "#14b8a6", "#84cc16",
      "#6366f1", "#d946ef", "#0ea5e9", "#eab308", "#a855f7",
    ];
    for (const c of palette) {
      if (!used.has(c)) return c;
    }
    let c;
    do { c = '#' + Math.floor(Math.random() * 0x1000000).toString(16).padStart(6, '0'); }
    while (used.has(c));
    return c;
  }

  openPackageEditor(pkg) {
    document.getElementById("pkg-editor").style.display = "";
    document.getElementById("pkg-edit-stackable").checked = false;
    document.getElementById("pkg-edit-qty").value = 1;
    if (pkg) {
      document.getElementById("pkg-edit-name").value = pkg.name || "";
      document.getElementById("pkg-edit-l").value = pkg.length || "";
      document.getElementById("pkg-edit-w").value = pkg.width || "";
      document.getElementById("pkg-edit-h").value = pkg.height || "";
      document.getElementById("pkg-edit-weight").value = pkg.weight_kg || "";
      document.getElementById("pkg-edit-color").value = pkg.color || "#3b82f6";
      document.getElementById("pkg-edit-stackable").checked = !!pkg.allow_stacking;
      document.getElementById("pkg-edit-qty").value = pkg.default_qty || 1;
      document.getElementById("pkg-save-btn").textContent = "Update";
      document.getElementById("pkg-save-btn").dataset.editId = pkg.id;
    } else {
      document.getElementById("pkg-edit-name").value = "";
      document.getElementById("pkg-edit-l").value = "";
      document.getElementById("pkg-edit-w").value = "";
      document.getElementById("pkg-edit-h").value = "";
      document.getElementById("pkg-edit-weight").value = "";
      document.getElementById("pkg-edit-color").value = this._nextPackageColor();
      document.getElementById("pkg-edit-stackable").checked = false;
      document.getElementById("pkg-edit-qty").value = 1;
      document.getElementById("pkg-save-btn").textContent = "Create";
      document.getElementById("pkg-save-btn").dataset.editId = "";
    }
  }

  cancelPackageEditor() {
    document.getElementById("pkg-editor").style.display = "none";
  }

  async savePackage() {
    const name = document.getElementById("pkg-edit-name").value.trim();
    const l = parseFloat(document.getElementById("pkg-edit-l").value);
    const w = parseFloat(document.getElementById("pkg-edit-w").value);
    const h = parseFloat(document.getElementById("pkg-edit-h").value);
    const weight = parseFloat(document.getElementById("pkg-edit-weight").value);
    const color = document.getElementById("pkg-edit-color").value;
    const stackable = document.getElementById("pkg-edit-stackable").checked;
    const qty = parseInt(document.getElementById("pkg-edit-qty").value, 10) || 1;

    if (!name) { UI.toast("Package name required", "warning"); return; }
    if (!l || !w || !h) { UI.toast("Length, width, height required", "warning"); return; }
    if (!weight) { UI.toast("Weight required", "warning"); return; }

    const editId = document.getElementById("pkg-save-btn").dataset.editId;
    const payload = { name, length: l, width: w, height: h, weight_kg: weight, color, allow_rotation: 1, allow_stacking: stackable ? 1 : 0, default_qty: qty };

    try {
      if (editId) {
        const res = await fetch(`/api/tlp/packages/${editId}`, {
          method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          UI.toast(err.error || "Failed to update package", "error");
          return;
        }
        UI.toast("Package updated", "success");
      } else {
        const res = await fetch("/api/tlp/packages", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          UI.toast(err.error || "Failed to create package", "error");
          return;
        }
        const created = await res.json();
        UI.toast("Package created: " + (created.name || name), "success");
      }
      // Reload packages and refresh UI
      this.packages = await API.packages();
      this.cancelPackageEditor();
      this.filterPackages();
    } catch (e) {
      console.error("Save package failed:", e);
      UI.toast("Failed to save package", "error");
    }
  }

  async deletePackage(id, name) {
    if (!confirm(`Delete package "${name}"? This will also remove all its placements.`)) return;
    try {
      const res = await fetch(`/api/tlp/packages/${id}`, { method: "DELETE" });
      if (!res.ok) { const err = await res.json().catch(() => ({})); UI.toast(err.error || "Failed to delete", "error"); return; }
      this.packages = await API.packages();
      this.filterPackages();
      UI.toast(`Package "${name}" deleted`, "success");
    } catch (e) {
      console.error("Delete package failed:", e);
      UI.toast("Failed to delete package", "error");
    }
  }

  async clearAllPackages() {
    if (!confirm("Delete ALL packages? This will also remove all placements and shipment items.")) return;
    try {
      const res = await fetch("/api/tlp/packages/clear", { method: "DELETE" });
      if (!res.ok) { const err = await res.json().catch(() => ({})); UI.toast(err.error || "Failed to clear", "error"); return; }
      this.packages = await API.packages();
      this.placements = [];
      this.filterPackages();
      this.renderCanvas();
      this.updateStatus();
      UI.toast("All packages cleared", "success");
    } catch (e) {
      console.error("Clear packages failed:", e);
      UI.toast("Failed to clear packages", "error");
    }
  }

  /* ═══════════════════════ VEHICLE SELECTOR ═══════════════════════ */

  populateVehicleList() {
    const list = document.getElementById("vehicle-select-list");
    list.innerHTML = "";
    const noneItem = document.createElement("div");
    noneItem.className = "modal-select-item";
    noneItem.style.cssText = "opacity:0.6;border-style:dashed;";
    noneItem.innerHTML = `<div class="name" style="text-align:center;">— None (multi-vehicle mode) —</div>`;
    noneItem.onclick = () => { this._deselectVehicle(); this.closeModal("vehicle-modal"); };
    list.appendChild(noneItem);
    for (const v of this.vehicles) {
      const item = document.createElement("div");
      item.className = "modal-select-item";
      item.innerHTML = `
        <div class="name">${UI.escapeHtml(v.plate_number)}</div>
        <div class="desc">${UI.escapeHtml(v.vehicle_type || "")} &middot; ${UI.escapeHtml(v.container_name || "")} &middot; ${UI.escapeHtml(v.current_driver || "No driver")}</div>
      `;
      item.onclick = () => { this._selectVehicle(v.vehicle_id); this.closeModal("vehicle-modal"); };
      list.appendChild(item);
    }
  }

  async _deselectVehicle() {
    this.currentVehicle = null;
    this.currentContainer = null;
    this.placements = [];
    this.planId = null;
    this.selectedIndex = -1;
    this.undoStack = [];
    this.redoStack = [];
    this.viewOffsetX = 0;
    this.viewOffsetY = 0;
    this.viewScale = 1;
    document.getElementById("btn-deselect-vehicle").style.display = "none";
    this.renderCanvas();
    this.updateStatus();
    if (this._show3D) this.update3DScene();
    UI.toast("Vehicle deselected — Auto Arrange will distribute across all vehicles", "info");
  }

  deselectVehicle() { this._deselectVehicle(); }

  openVehicleSelector() {
    this.populateVehicleList();
    document.getElementById("vehicle-modal").classList.add("open");
  }

  async _selectVehicle(vehicleId) {
    this.currentVehicle = this.vehicles.find(v => v.vehicle_id == vehicleId);
    this.placements = [];
    this.planId = null;
    this.selectedIndex = -1;
    this.undoStack = [];
    this.redoStack = [];

    if (this.currentVehicle && this.currentVehicle.cc_id) {
      try {
        this.currentContainer = await API.container(this.currentVehicle.cc_id);
      } catch (e) {
        console.error("Failed to load container config:", e);
        this.currentContainer = null;
      }
    } else {
      this.currentContainer = null;
    }

    this.viewOffsetX = 0;
    this.viewOffsetY = 0;
    this.viewScale = 1;
    this.renderCanvas();
    this.updateStatus();
    if (this._show3D) this.update3DScene();
    UI.toast("Vehicle selected: " + (this.currentVehicle ? this.currentVehicle.plate_number : ""), "success");
  }

  /* ═══════════════════════ SHIPMENT SELECTOR ═══════════════════════ */

  populateShipmentList() {
    const list = document.getElementById("shipment-select-list");
    list.innerHTML = "";
    if (!this.shipments.length) {
      list.innerHTML = '<div class="tlp-empty-hint" style="padding:12px;">No shipments available</div>';
      return;
    }
    for (const s of this.shipments) {
      const item = document.createElement("div");
      item.className = "modal-select-item";
      const itemCount = (s.items || []).length;
      item.innerHTML = `
        <div class="name">${UI.escapeHtml(s.customer_name)}</div>
        <div class="desc">${UI.escapeHtml(s.reference_number || "No ref")} &middot; ${itemCount} package types</div>
      `;
      item.onclick = () => { this._selectShipment(s.id); this.closeModal("shipment-modal"); };
      list.appendChild(item);
    }
  }

  openShipmentSelector() {
    this.populateShipmentList();
    document.getElementById("shipment-modal").classList.add("open");
  }

  _selectShipment(shipmentId) {
    this.currentShipment = this.shipments.find(s => s.id == shipmentId);
    if (this.currentShipment) {
      document.getElementById("s-name").textContent = this.currentShipment.reference_number || "—";
      document.getElementById("s-customer").textContent = this.currentShipment.customer_name || "—";
      document.getElementById("s-ref").textContent = this.currentShipment.reference_number || "—";
      document.getElementById("tb-shipment-name").textContent = this.currentShipment.customer_name || "—";
      document.getElementById("toolbar-shipment").style.display = "";

      // Sync package list
      this.filterPackages();
      UI.toast("Shipment loaded: " + this.currentShipment.customer_name, "success");
    }
  }

  /* ─── Shipment Builder ─── */

  createShipment() {
    this._editingShipment = null;
    this._editItems = [];
    this._showShipmentEditForm();
    document.getElementById("s-edit-customer").value = "";
    document.getElementById("s-edit-ref").value = "";
    document.getElementById("s-edit-notes").value = "";
    this._renderEditItems();
    this._populateAddPackageSelect();
  }

  editShipment() {
    if (!this.currentShipment) return;
    this._editingShipment = this.currentShipment;
    this._editItems = (this.currentShipment.items || []).map(i => ({
      _tempId: Math.random(),
      package_id: i.package_id,
      package_name: i.package_name || "Package",
      quantity: i.quantity || 1,
    }));
    this._showShipmentEditForm();
    document.getElementById("s-edit-customer").value = this.currentShipment.customer_name || "";
    document.getElementById("s-edit-ref").value = this.currentShipment.reference_number || "";
    document.getElementById("s-edit-notes").value = this.currentShipment.notes || "";
    this._renderEditItems();
    this._populateAddPackageSelect();
  }

  cancelEditShipment() {
    this._editingShipment = null;
    this._editItems = [];
    document.getElementById("shipment-section-edit").style.display = "none";
    document.getElementById("shipment-section-view").style.display = "";
  }

  _showShipmentEditForm() {
    document.getElementById("shipment-section-view").style.display = "none";
    document.getElementById("shipment-section-edit").style.display = "";
  }

  _populateAddPackageSelect() {
    const sel = document.getElementById("s-edit-add-pkg");
    sel.innerHTML = '<option value="">+ Add package...</option>';
    for (const pkg of this.packages) {
      const opt = document.createElement("option");
      opt.value = pkg.id;
      opt.textContent = pkg.name + " (" + pkg.length + "x" + pkg.width + "x" + pkg.height + ")";
      sel.appendChild(opt);
    }
  }

  addShipmentItem() {
    const sel = document.getElementById("s-edit-add-pkg");
    const qtyInput = document.getElementById("s-edit-add-qty");
    const pkgId = parseInt(sel.value, 10);
    if (!pkgId) return;
    const pkg = this.packages.find(p => p.id === pkgId);
    if (!pkg) return;
    const qty = parseInt(qtyInput.value, 10) || 1;
    // Add or increment
    const existing = this._editItems.find(i => i.package_id === pkgId);
    if (existing) {
      existing.quantity += qty;
    } else {
      this._editItems.push({ _tempId: Math.random(), package_id: pkgId, package_name: pkg.name, quantity: qty });
    }
    this._renderEditItems();
    sel.value = "";
    qtyInput.value = "1";
  }

  removeShipmentItem(tempId) {
    this._editItems = this._editItems.filter(i => i._tempId !== tempId);
    this._renderEditItems();
  }

  _renderEditItems() {
    const container = document.getElementById("s-edit-items");
    if (this._editItems.length === 0) {
      container.innerHTML = '<div style="font-size:10px;color:var(--text-muted);padding:4px 0;">No items added yet</div>';
      return;
    }
    container.innerHTML = this._editItems.map((item, idx) => {
      const pkg = this.packages.find(p => p.id === item.package_id);
      const color = (pkg && pkg.color) || "#3b82f6";
      return `
        <div style="display:flex;align-items:center;gap:4px;padding:3px 0;border-bottom:1px solid var(--border);font-size:11px;">
          <span style="width:10px;height:10px;border-radius:2px;background:${color};flex-shrink:0;"></span>
          <span style="flex:1;color:var(--text-secondary);">${UI.escapeHtml(item.package_name)}</span>
          <span style="color:var(--text-muted);">x${item.quantity}</span>
          <button onclick="app.removeShipmentItem(${item._tempId})" style="background:none;border:none;color:var(--danger);cursor:pointer;font-size:12px;">&times;</button>
        </div>
      `;
    }).join("");
  }

  async saveShipment() {
    const customer = document.getElementById("s-edit-customer").value.trim();
    if (!customer) { UI.toast("Customer name is required", "warning"); return; }
    const ref = document.getElementById("s-edit-ref").value.trim();
    const notes = document.getElementById("s-edit-notes").value.trim();
    const items = this._editItems.map(i => ({ package_id: i.package_id, quantity: i.quantity }));

    try {
      if (this._editingShipment && this._editingShipment.id) {
        await API.updateShipment(this._editingShipment.id, { customer_name: customer, reference_number: ref, notes, items });
        UI.toast("Shipment updated", "success");
      } else {
        const result = await API.saveShipment({ customer_name: customer, reference_number: ref, notes, items });
        UI.toast("Shipment created", "success");
      }
      this._editingShipment = null;
      this._editItems = [];
      document.getElementById("shipment-section-edit").style.display = "none";
      document.getElementById("shipment-section-view").style.display = "";
      // Reload shipments and select the new/updated one
      this.shipments = await API.shipments();
      this.populateShipmentList();
      const match = this.shipments.find(s => s.customer_name === customer);
      if (match) this._selectShipment(match.id);
    } catch (e) {
      console.error("Save shipment failed:", e);
      UI.toast("Failed to save shipment", "error");
    }
  }

  /* ═══════════════════════ PLAN LIST ═══════════════════════ */

  populatePlanList() {
    const list = document.getElementById("plan-select-list");
    list.innerHTML = "";
    if (!this.plans.length) {
      list.innerHTML = '<div class="tlp-empty-hint" style="padding:12px;">No saved plans</div>';
      return;
    }
    for (const p of this.plans) {
      const item = document.createElement("div");
      item.className = "modal-select-item";
      const pkgCount = (p.placements || []).length;
      item.innerHTML = `
        <div class="name">${UI.escapeHtml(p.name || "Unnamed")}</div>
        <div class="desc">${UI.escapeHtml(p.plate_number || "?")} &middot; ${pkgCount} packages &middot; ${UI.escapeHtml(p.status || "draft")}</div>
      `;
      item.onclick = () => { this._loadPlan(p.id); this.closeModal("load-modal"); };
      list.appendChild(item);
    }
  }

  openLoadDialog() {
    API.plans().then(plans => {
      this.plans = plans;
      this.populatePlanList();
      document.getElementById("load-modal").classList.add("open");
    });
  }

  async _loadPlan(planId) {
    try {
      const plan = await API.getPlan(planId);
      this.planId = plan.id;

      // Find and select vehicle
      const vehicle = this.vehicles.find(v => v.vehicle_id == plan.vehicle_id);
      if (vehicle) {
        this.currentVehicle = vehicle;
        if (vehicle.cc_id) {
          this.currentContainer = await API.container(vehicle.cc_id);
        }
      }

      // Build placements
      this.placements = (plan.placements || []).map(p => ({
        id: p.id,
        package_id: p.package_id,
        x: p.x, y: p.y, z: p.z || 0,
        rotation: p.rotation || 0,
        load_sequence: p.load_sequence,
        _name: p.package_name || "",
        _length: p.length || 0,
        _width: p.width || 0,
        _height: p.height || 0,
        _weight_kg: p.weight_kg || 0,
        _color: p.color,
        _package: { name: p.package_name, length: p.length, width: p.width, height: p.height, weight_kg: p.weight_kg, color: p.color, allow_stacking: !!p.allow_stacking },
      }));
      this.undoStack = [];
      this.redoStack = [];
      this.selectedIndex = -1;

      document.getElementById("btn-deselect-vehicle").style.display = "";
      this.viewOffsetX = 0;
      this.viewOffsetY = 0;
      this.viewScale = 1;
      this.renderCanvas();
      this.updateStatus();
      if (this._show3D) this.update3DScene();
      UI.toast("Plan loaded: " + (plan.name || "Unnamed"), "success");
    } catch (e) {
      console.error("Failed to load plan:", e);
      UI.toast("Failed to load plan", "error");
    }
  }

  /* ═══════════════════════ SAVE / EXPORT ═══════════════════════ */

  savePlan() {
    if (!this.currentVehicle) {
      UI.toast("Select a vehicle first", "warning");
      return;
    }
    if (this.planId) {
      this._doSave();
    } else {
      this.saveAsPlan();
    }
  }

  saveAsPlan() {
    if (!this.currentVehicle) {
      UI.toast("Select a vehicle first", "warning");
      return;
    }
    document.getElementById("save-modal-title").textContent = "Save Plan";
    document.getElementById("field-plan-name").value = "";
    document.getElementById("field-planner").value = "";
    document.getElementById("field-notes").value = "";
    document.getElementById("save-modal").classList.add("open");
  }

  async confirmSave() {
    const name = document.getElementById("field-plan-name").value || "Untitled Plan";
    const planner = document.getElementById("field-planner").value || "";
    const notes = document.getElementById("field-notes").value || "";

    const payload = {
      name, planner, notes,
      status: "draft",
      vehicle_id: this.currentVehicle.vehicle_id,
      placements: this.placements.map((p, i) => ({
        package_id: p.package_id,
        x: p.x, y: p.y, z: p.z || 0,
        rotation: p.rotation || 0,
        load_sequence: p.load_sequence || (i + 1),
      })),
    };

    // ── Instrument: placements being sent to DB save ────
    console.log("=== INSTRUMENT: Placements sent to save/create_plan ===");
    console.log(JSON.stringify({
      trace_id: "frontend-" + Date.now(),
      label: "placements-sent-for-save",
      planId: this.planId,
      is_update: !!(this.planId && document.getElementById("save-modal-title").textContent !== "Save Plan As"),
      payload_placements: payload.placements,
    }, null, 2));

    try {
      let result;
      if (this.planId && document.getElementById("save-modal-title").textContent !== "Save Plan As") {
        result = await API.updatePlan(this.planId, payload);
        UI.toast("Plan updated", "success");
      } else {
        result = await API.savePlan(payload);
        this.planId = result.id;
        UI.toast("Plan saved", "success");
      }
      this.closeModal("save-modal");
      this.plans = await API.plans();
    } catch (e) {
      console.error("Save failed:", e);
      UI.toast("Failed to save plan", "error");
    }
  }

  closeModal(id) {
    document.getElementById(id).classList.remove("open");
  }

  showProgressModal(title, subtitle) {
    const el = document.getElementById("arrange-progress-modal");
    if (!el) return;
    const titleEl = el.querySelector(".modal-body > div:nth-child(2)");
    const modeEl = document.getElementById("arrange-progress-mode");
    const timeEl = document.getElementById("arrange-progress-time");
    if (titleEl) titleEl.textContent = title || "Arranging packages...";
    if (modeEl) modeEl.textContent = subtitle || "Optimizing placement";
    el.classList.add("open");
    this._progressStart = Date.now();
    if (this._progressTimer) clearInterval(this._progressTimer);
    this._progressTimer = setInterval(() => {
      const s = Math.floor((Date.now() - this._progressStart) / 1000);
      const m = Math.floor(s / 60);
      const sec = s % 60;
      if (timeEl) timeEl.textContent = "Elapsed: " + (m > 0 ? m + "m " : "") + sec + "s";
    }, 200);
  }

  hideProgressModal() {
    const el = document.getElementById("arrange-progress-modal");
    if (el) el.classList.remove("open");
    if (this._progressTimer) { clearInterval(this._progressTimer); this._progressTimer = null; }
  }

  exportPlan() {
    if (!this.currentVehicle) {
      UI.toast("Select a vehicle first", "warning");
      return;
    }
    const data = {
      plan_name: "Export",
      vehicle: this.currentVehicle.plate_number,
      container: (this.currentContainer && this.currentContainer.name) || "",
      dimensions: this._getContainerDims(),
      placements: this.placements.map(p => ({
        name: p._name,
        position: { x: p.x, y: p.y, z: p.z || 0 },
        dimensions: { length: p._length, width: p._width, height: p._height },
        weight: p._weight_kg,
        sequence: p.load_sequence,
      })),
      timestamp: new Date().toISOString(),
    };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "load-plan-export.json";
    a.click();
    URL.revokeObjectURL(url);
    UI.toast("Plan exported", "success");
  }

  /* ═══════════════════════ HELP ═══════════════════════ */

  openHelp() {
    UI.toast("Shortcuts: Del=Remove, Ctrl+Z=Undo, Ctrl+Shift+Z=Redo, Esc=Cancel", "info");
  }

  /* ═══════════════════════ THREE.JS 3D PREVIEW ═══════════════════════ */

  toggle3D() {
    this._show3D = !this._show3D;
    const container = document.getElementById("tlp-3d-container");
    const btn = document.getElementById("btn-3d-toggle");
    btn.classList.toggle("active", this._show3D);
    container.style.display = this._show3D ? "" : "none";
    if (this._show3D) {
      this._init3D();
      this.update3DScene();
      this._sync3DToolbar();
    } else {
      this._destroy3D();
    }
  }

  toggle3DFullscreen() {
    const container = document.getElementById("tlp-3d-container");
    const isFS = container.classList.toggle("fullscreen");
    const btn = document.getElementById("tlp-3d-btn-fullscreen");
    if (btn) btn.textContent = isFS ? "\u274C" : "\u2316";
    this._sync3DToolbar();
    setTimeout(() => this._update3DOnResize(), 50);
  }

  _makeTextSprite(text, color) {
    const canvas = document.createElement("canvas");
    const w = 512, h = 96;
    canvas.width = w; canvas.height = h;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "rgba(0,0,0,0.55)";
    const r = 8;
    ctx.beginPath(); ctx.moveTo(r, 0);
    ctx.lineTo(w - r, 0); ctx.quadraticCurveTo(w, 0, w, r);
    ctx.lineTo(w, h - r); ctx.quadraticCurveTo(w, h, w - r, h);
    ctx.lineTo(r, h); ctx.quadraticCurveTo(0, h, 0, h - r);
    ctx.lineTo(0, r); ctx.quadraticCurveTo(0, 0, r, 0);
    ctx.closePath(); ctx.fill();
    ctx.font = "Bold 28px Arial, sans-serif";
    ctx.fillStyle = color || "#ffffff";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(text, w / 2, h / 2);
    const texture = new THREE.CanvasTexture(canvas);
    texture.needsUpdate = true;
    const mat = new THREE.SpriteMaterial({ map: texture, depthTest: false, depthWrite: false, transparent: true });
    const sprite = new THREE.Sprite(mat);
    sprite.scale.set(300, 56, 1);
    return sprite;
  }

  _init3D() {
    if (this._threeInitAttempted && this._threeRenderer) return;
    this._threeInitAttempted = true;
    const container = document.getElementById("tlp-3d-container");
    if (!container) return;

    const w = container.clientWidth || 360;
    const h = container.clientHeight || 280;

    // Scene
    this._threeScene = new THREE.Scene();
    this._threeScene.background = new THREE.Color(0x0d1117);

    // Camera
    this._threeCamera = new THREE.PerspectiveCamera(40, w / h, 1, 100000);
    this._threeCamera.position.set(8000, 6000, 8000);
    this._threeCamera.lookAt(0, 0, 0);

    // Renderer
    this._threeRenderer = new THREE.WebGLRenderer({ antialias: true });
    this._threeRenderer.setSize(w, h);
    this._threeRenderer.setPixelRatio(window.devicePixelRatio);
    this._threeRenderer.shadowMap.enabled = true;
    container.appendChild(this._threeRenderer.domElement);

    // Controls
    this._threeControls = new THREE.OrbitControls(this._threeCamera, this._threeRenderer.domElement);
    this._threeControls.enableDamping = true;
    this._threeControls.dampingFactor = 0.15;
    this._threeControls.target.set(0, 0, 0);
    this._threeControls.update();

    // Lights
    const ambient = new THREE.AmbientLight(0x404060, 0.5);
    this._threeScene.add(ambient);
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(10000, 15000, 10000);
    this._threeScene.add(dirLight);
    const dirLight2 = new THREE.DirectionalLight(0xffffff, 0.3);
    dirLight2.position.set(-5000, 5000, -5000);
    this._threeScene.add(dirLight2);

    // Grid floor
    const gridHelper = new THREE.GridHelper(10000, 20, 0x2f8ceb, 0x1a3a5c);
    gridHelper.position.y = 0;
    this._threeScene.add(gridHelper);

    // Start animation
    this._animate3D();
  }

  _destroy3D() {
    if (this._threeAnimId) {
      cancelAnimationFrame(this._threeAnimId);
      this._threeAnimId = null;
    }
    if (this._threeRenderer) {
      this._threeRenderer.domElement.remove();
      this._threeRenderer.dispose();
      this._threeRenderer = null;
    }
    this._threeScene = null;
    this._threeCamera = null;
    this._threeControls = null;
    this._threeMeshes = [];
  }

  _animate3D() {
    if (!this._threeRenderer || !this._show3D) return;
    this._threeAnimId = requestAnimationFrame(() => this._animate3D());
    if (this._threeControls) this._threeControls.update();
    if (this._stepAnimState) {
      const elapsed = performance.now() - this._stepAnimState.startTime;
      const t = Math.min(elapsed / this._stepAnimState.duration, 1);
      const ease = 1 - Math.pow(1 - t, 3);
      const m = this._stepAnimState.mesh;
      const o = this._stepAnimState.outline;
      if (m) {
        m.position.lerpVectors(this._stepAnimState.startPos, this._stepAnimState.endPos, ease);
      }
      if (o) {
        o.position.lerpVectors(this._stepAnimState.startPos, this._stepAnimState.endPos, ease);
      }
      if (t >= 1) {
        this._stepCompletePackage();
      }
    }
    this._threeRenderer.render(this._threeScene, this._threeCamera);
  }

  // ── Step Animation ──────────────────────────────────────────────────

  _startStepMode(placements) {
    const sorted = [...placements].sort((a, b) => (a.load_sequence || 0) - (b.load_sequence || 0));
    this._stepPlacements = sorted;
    this._stepIndex = 0;
    this._stepTotal = sorted.length;
    this._stepMode = true;
    this._stepAnimating = false;
    this._stepAnimState = null;
    this._stepAutoPlay = false;
    this._stepPermanentPkgs = [];

    document.getElementById("btn-step-prev").style.display = "";
    document.getElementById("step-counter").style.display = "";
    document.getElementById("btn-step-next").style.display = "";
    document.getElementById("btn-step-play").style.display = "";
    document.getElementById("btn-step-end").style.display = "";
    document.getElementById("btn-step-play").textContent = "\u25B6";

    this._stepUpdateCounter();
    this._stepClearPermanent();
    this._sync3DToolbar();
  }

  _stepEndMode(resetStep = true) {
    if (resetStep) this._stepMode = false;
    this._stepAnimating = false;
    this._stepAnimState = null;
    this._stepAutoPlay = false;
    this._stepPermanentPkgs = [];
    if (resetStep) {
      document.getElementById("btn-step-prev").style.display = "none";
      document.getElementById("step-counter").style.display = "none";
      document.getElementById("btn-step-next").style.display = "none";
      document.getElementById("btn-step-play").style.display = "none";
      document.getElementById("btn-step-end").style.display = "none";
    }
    this._sync3DToolbar();
  }

  _stepUpdateCounter() {
    let text = this._stepIndex + "/" + this._stepTotal;
    const el = document.getElementById("step-counter");
    if (el) el.textContent = text;
    const el3d = document.getElementById("tlp-3d-step-counter");
    if (el3d) el3d.textContent = text;
  }

  _sync3DToolbar() {
    const show = this._stepMode;
    ["tlp-3d-btn-prev", "tlp-3d-btn-next", "tlp-3d-btn-play", "tlp-3d-btn-end", "tlp-3d-step-counter"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = show ? "" : "none";
    });
    const playBtn = document.getElementById("tlp-3d-btn-play");
    if (playBtn) playBtn.textContent = (this._stepAutoPlay ? "\u23F8" : "\u25B6\u25B6");
  }

  _stepClearPermanent() {
    const scene = this._threeScene;
    for (const pkg of this._stepPermanentPkgs) {
      if (scene && pkg.mesh) { scene.remove(pkg.mesh); if (pkg.mesh.geometry) pkg.mesh.geometry.dispose(); if (pkg.mesh.material) pkg.mesh.material.dispose(); }
      if (scene && pkg.outline) { scene.remove(pkg.outline); if (pkg.outline.geometry) pkg.outline.geometry.dispose(); if (pkg.outline.material) pkg.outline.material.dispose(); }
      if (scene && pkg.label) { scene.remove(pkg.label); if (pkg.label.material) pkg.label.material.dispose(); if (pkg.label.material.map) pkg.label.material.map.dispose(); }
    }
    this._stepPermanentPkgs = [];
    if (this._stepAnimState) {
      const s = this._stepAnimState;
      if (scene && s.mesh) { scene.remove(s.mesh); if (s.mesh.geometry) s.mesh.geometry.dispose(); if (s.mesh.material) s.mesh.material.dispose(); }
      if (scene && s.outline) { scene.remove(s.outline); if (s.outline.geometry) s.outline.geometry.dispose(); if (s.outline.material) s.outline.material.dispose(); }
      if (scene && s.label) { scene.remove(s.label); if (s.label.material) s.label.material.dispose(); if (s.label.material.map) s.label.material.map.dispose(); }
      this._stepAnimState = null;
    }
  }

  _stepShowPermanent(placement) {
    const d = this._getContainerDims();
    if (!d || d.len <= 0) return;
    const color = placement._color || (placement._package && placement._package.color) || "#3b82f6";
    const pl = placement._length || 100;
    const pw = placement._width || 100;
    const ph = placement._height || 100;
    const pkgGeo = new THREE.BoxGeometry(pl, ph, pw);
    const pkgMat = new THREE.MeshPhongMaterial({ color: new THREE.Color(color), transparent: true, opacity: 0.75, depthWrite: false });
    const mesh = new THREE.Mesh(pkgGeo, pkgMat);
    mesh.position.set(
      (placement.x || 0) + pl / 2,
      (placement.z || 0) + ph / 2,
      (placement.y || 0) + pw / 2,
    );
    this._threeScene.add(mesh);
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(pkgGeo),
      new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.2 }),
    );
    edges.position.copy(mesh.position);
    this._threeScene.add(edges);
    // Label
    const name = placement._name || (placement._package && placement._package.name) || "";
    let label = null;
    if (name) {
      label = this._makeTextSprite(name, "#ffffff");
      label.position.set(
        (placement.x || 0) + pl / 2,
        (placement.z || 0) + ph + 30,
        (placement.y || 0) + pw / 2,
      );
      this._threeScene.add(label);
    }
    this._stepPermanentPkgs.push({ mesh, outline: edges, label, placement });
  }

  _stepCreateAnimMesh(placement, startPos, endPos) {
    const d = this._getContainerDims();
    if (!d) return null;
    const color = placement._color || (placement._package && placement._package.color) || "#3b82f6";
    const pl = placement._length || 100;
    const pw = placement._width || 100;
    const ph = placement._height || 100;
    const pkgGeo = new THREE.BoxGeometry(pl, ph, pw);
    const pkgMat = new THREE.MeshPhongMaterial({ color: new THREE.Color(color), transparent: true, opacity: 0.85, depthWrite: false });
    const mesh = new THREE.Mesh(pkgGeo, pkgMat);
    mesh.position.copy(startPos);
    this._threeScene.add(mesh);
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(pkgGeo),
      new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.3 }),
    );
    edges.position.copy(startPos);
    this._threeScene.add(edges);
    return { mesh, outline: edges, startPos: startPos.clone(), endPos: endPos.clone(), placement };
  }

  _stepCompletePackage() {
    if (!this._stepAnimState) return;
    const s = this._stepAnimState;
    if (s.mesh) { this._threeScene.remove(s.mesh); if (s.mesh.geometry) s.mesh.geometry.dispose(); if (s.mesh.material) s.mesh.material.dispose(); }
    if (s.outline) { this._threeScene.remove(s.outline); if (s.outline.geometry) s.outline.geometry.dispose(); if (s.outline.material) s.outline.material.dispose(); }
    this._stepShowPermanent(s.placement);
    this._stepAnimState = null;
    this._stepAnimating = false;
    this._stepIndex++;
    this._stepUpdateCounter();
    if (this._stepAutoPlay && this._stepIndex < this._stepTotal) {
      setTimeout(() => this._stepNext(), 200);
    } else if (this._stepIndex >= this._stepTotal) {
      this._stepAutoPlay = false;
      const btn = document.getElementById("btn-step-play");
      if (btn) btn.textContent = "\u25B6";
      this._stepClearPermanent();
      this._stepEndMode(false);
      this.update3DScene();
    }
  }

  _stepNext() {
    if (!this._stepMode || this._stepAnimating) return;
    if (this._stepIndex >= this._stepTotal) return;
    const placement = this._stepPlacements[this._stepIndex];
    const d = this._getContainerDims();
    if (!d || d.len <= 0) return;
    const pl = placement._length || 100;
    const pw = placement._width || 100;
    const ph = placement._height || 100;

    const endPos = new THREE.Vector3(
      (placement.x || 0) + pl / 2,
      (placement.z || 0) + ph / 2,
      (placement.y || 0) + pw / 2,
    );
    let startPos;
    const door = placement.door_used || "rear";
    if (door === "rear") {
      startPos = new THREE.Vector3(d.len + pl, endPos.y, endPos.z);
    } else if (door === "side_right") {
      // Enter at raised height so package clears any packages blocking
      // the lower part of the side door opening, then lower to final Z.
      startPos = new THREE.Vector3(endPos.x, d.hei, d.wid + pw);
    } else if (door === "side_left") {
      startPos = new THREE.Vector3(endPos.x, d.hei, -pw);
    } else {
      startPos = new THREE.Vector3(d.len + pl, endPos.y, endPos.z);
    }

    this._stepAnimState = this._stepCreateAnimMesh(placement, startPos, endPos);
    if (this._stepAnimState) {
      this._stepAnimating = true;
      this._stepAnimState.startTime = performance.now();
      this._stepAnimState.duration = this._stepAnimDuration;
    } else {
      // fallback: show immediately
      this._stepShowPermanent(placement);
      this._stepIndex++;
      this._stepUpdateCounter();
      if (this._stepAutoPlay && this._stepIndex < this._stepTotal) {
        setTimeout(() => this._stepNext(), 200);
      } else if (this._stepIndex >= this._stepTotal) {
        this._stepAutoPlay = false;
        document.getElementById("btn-step-play").textContent = "\u25B6";
        this._stepClearPermanent();
        this._stepEndMode(false);
        this.update3DScene();
      }
    }
  }

  stepNext() {
    if (!this._stepMode) return;
    if (this._stepAnimating) return;
    this._stepNext();
  }

  stepPrev() {
    if (!this._stepMode || this._stepAnimating) return;
    if (this._stepIndex <= 0) return;
    this._stepIndex--;
    this._stepClearPermanent();
    for (let i = 0; i < this._stepIndex; i++) {
      this._stepShowPermanent(this._stepPlacements[i]);
    }
    this._stepUpdateCounter();
  }

  stepPlay() {
    if (!this._stepMode) return;
    if (this._stepAnimating && this._stepAutoPlay) {
      this._stepAutoPlay = false;
      document.getElementById("btn-step-play").textContent = "\u25B6";
      this._sync3DToolbar();
      return;
    }
    if (this._stepIndex >= this._stepTotal) return;
    this._stepAutoPlay = true;
    document.getElementById("btn-step-play").textContent = "\u23F8";
    this._sync3DToolbar();
    if (!this._stepAnimating) {
      this._stepNext();
    }
  }

  stepEnd() {
    if (!this._stepMode || this._stepAnimating) return;
    this._stepClearPermanent();
    this._stepIndex = this._stepTotal;
    this._stepUpdateCounter();
    this._stepEndMode(false);
    this.update3DScene();
  }

  /** @param {boolean} [skipPackages=false] - If true, don't draw packages (e.g. for step animation). */
  update3DScene(skipPackages) {
    if (!this._show3D || !this._threeScene || !this.currentVehicle) return;

    // Clear step animation if rendering normally
    if (!skipPackages && this._stepMode) {
      this._stepClearPermanent();
      this._stepEndMode(false);
    }

    // Remove old meshes
    for (const m of this._threeMeshes) {
      this._threeScene.remove(m);
      if (m.geometry) m.geometry.dispose();
      if (m.material) m.material.dispose();
    }
    this._threeMeshes = [];

    const d = this._getContainerDims();
    if (d.len <= 0 || d.wid <= 0 || d.hei <= 0) return;

    // Container
    const cx = d.len / 2;
    const cy = d.hei / 2;
    const cz = d.wid / 2;

    const boxGeo = new THREE.BoxGeometry(d.len, d.hei, d.wid);
    const boxMat = new THREE.MeshPhongMaterial({
      color: 0x1a2332, transparent: true, opacity: 0.15, side: THREE.DoubleSide, depthWrite: false,
    });
    const containerMesh = new THREE.Mesh(boxGeo, boxMat);
    containerMesh.position.set(cx, cy, cz);
    this._threeScene.add(containerMesh);
    this._threeMeshes.push(containerMesh);

    // Container edges
    const edgesGeo = new THREE.EdgesGeometry(boxGeo);
    const edgesMat = new THREE.LineBasicMaterial({ color: 0x2f8ceb, linewidth: 1 });
    const edgesMesh = new THREE.LineSegments(edgesGeo, edgesMat);
    edgesMesh.position.copy(containerMesh.position);
    this._threeScene.add(edgesMesh);
    this._threeMeshes.push(edgesMesh);

    // Floor
    const floorGeo = new THREE.PlaneGeometry(d.len, d.wid);
    const floorMat = new THREE.MeshBasicMaterial({
      color: 0x1a2332, side: THREE.DoubleSide, transparent: true, opacity: 0.3, depthWrite: false,
    });
    const floorMesh = new THREE.Mesh(floorGeo, floorMat);
    floorMesh.rotation.x = -Math.PI / 2;
    floorMesh.position.set(cx, 0, cz);
    this._threeScene.add(floorMesh);
    this._threeMeshes.push(floorMesh);

    // Doors
    const features = (this.currentContainer && this.currentContainer.features)
      || (this.currentVehicle && this.currentVehicle.features) || [];
    for (const f of features) {
      const ftype = f.feature_type || f;
      let geo = f.geometry_json || f.geometry || {};
      if (typeof geo === "string") try { geo = JSON.parse(geo); } catch (e) { geo = {}; }
      if (ftype === "rear_door") {
        const dw = geo.width_mm || d.wid;
        const dh = geo.height_mm || d.hei;
        const doorGeo = new THREE.PlaneGeometry(dw, dh);
        const doorMat = new THREE.MeshBasicMaterial({ color: 0x2f8ceb, transparent: true, opacity: 0.25, side: THREE.DoubleSide, depthWrite: false });
        const doorMesh = new THREE.Mesh(doorGeo, doorMat);
        doorMesh.position.set(d.len, dh / 2, cz);
        doorMesh.rotation.y = Math.PI / 2;
        this._threeScene.add(doorMesh);
        this._threeMeshes.push(doorMesh);
        const doorOutline = new THREE.LineSegments(
          new THREE.EdgesGeometry(doorGeo),
          new THREE.LineBasicMaterial({ color: 0x2f8ceb, transparent: true, opacity: 0.5 })
        );
        doorOutline.position.copy(doorMesh.position);
        doorOutline.rotation.copy(doorMesh.rotation);
        this._threeScene.add(doorOutline);
        this._threeMeshes.push(doorOutline);
      }
      if (ftype === "side_door") {
        const dw = geo.width_mm || d.len * 0.3;
        const dh = geo.height_mm || d.hei;
        const pos = geo.position_from_front_mm || 0;
        const doorX = pos + dw / 2;
        const doorY = dh / 2;
        const sideMat = new THREE.MeshBasicMaterial({ color: 0x10b981, transparent: true, opacity: 0.25, side: THREE.DoubleSide, depthWrite: false });
        const outMat = new THREE.LineBasicMaterial({ color: 0x10b981, transparent: true, opacity: 0.5 });
        // Right side
        const rGeo = new THREE.BoxGeometry(dw, dh, 0.04);
        const rDoor = new THREE.Mesh(rGeo, sideMat);
        rDoor.position.set(doorX, doorY, d.wid);
        this._threeScene.add(rDoor);
        this._threeMeshes.push(rDoor);
        const rOut = new THREE.LineSegments(new THREE.EdgesGeometry(rGeo), outMat);
        rOut.position.copy(rDoor.position);
        this._threeScene.add(rOut);
        this._threeMeshes.push(rOut);
        // Left side
        const lGeo = new THREE.BoxGeometry(dw, dh, 0.04);
        const lDoor = new THREE.Mesh(lGeo, sideMat);
        lDoor.position.set(doorX, doorY, 0);
        this._threeScene.add(lDoor);
        this._threeMeshes.push(lDoor);
        const lOut = new THREE.LineSegments(new THREE.EdgesGeometry(lGeo), outMat);
        lOut.position.copy(lDoor.position);
        this._threeScene.add(lOut);
        this._threeMeshes.push(lOut);
      }
    }

    // Packages (skip in step mode — step animation controls them)
    if (skipPackages) {
      // Still update camera target to container center
      if (this._threeControls) {
        this._threeControls.target.set(d.len / 2, d.hei / 2, d.wid / 2);
        this._threeControls.update();
      }
      return;
    }
    for (const p of this.placements) {
      let pl = p._length || 100;
      let pw = p._width || 100;
      // Match the 2D renderer (_drawPackages): rotation 90/270 swaps
      // which axis length/width occupy (AABB.from_dimensions on the
      // backend), otherwise a rotated package renders with the wrong
      // box extents even though its backend placement is valid.
      if (p.rotation === 90 || p.rotation === 270) {
        const t = pl; pl = pw; pw = t;
      }
      const ph = p._height || 100;
      const color = p._color || (p._package && p._package.color) || "#3b82f6";

      const pkgGeo = new THREE.BoxGeometry(pl, ph, pw);
      const pkgMat = new THREE.MeshPhongMaterial({
        color: new THREE.Color(color),
        transparent: true, opacity: 0.75, depthWrite: false,
      });
      const pkgMesh = new THREE.Mesh(pkgGeo, pkgMat);
      pkgMesh.position.set(
        (p.x || 0) + pl / 2,
        (p.z || 0) + ph / 2,
        (p.y || 0) + pw / 2
      );
      this._threeScene.add(pkgMesh);
      this._threeMeshes.push(pkgMesh);

      // Edges
      const pkgEdges = new THREE.LineSegments(
        new THREE.EdgesGeometry(pkgGeo),
        new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.2 })
      );
      pkgEdges.position.copy(pkgMesh.position);
      this._threeScene.add(pkgEdges);
      this._threeMeshes.push(pkgEdges);

      // Name label
      const name = p._name || (p._package && p._package.name) || "";
      if (name) {
        const label = this._makeTextSprite(name, "#ffffff");
        label.position.set(
          (p.x || 0) + pl / 2,
          (p.z || 0) + ph + 30,
          (p.y || 0) + pw / 2
        );
        this._threeScene.add(label);
        this._threeMeshes.push(label);
      }
    }

    // ── Instrument: Representation 5 — 3D scene positions ────
    const _3dPositions = [];
    for (const p of this.placements) {
      _3dPositions.push({
        package_id: p.package_id,
        name: p._name || "",
        x_mm: p.x || 0,
        y_mm: p.y || 0,
        z_mm: p.z || 0,
        length_mm: p._length || (p._package && p._package.length) || 0,
        width_mm: p._width || (p._package && p._package.width) || 0,
        height_mm: p._height || (p._package && p._package.height) || 0,
        rotation: p.rotation || 0,
        three_x: (p.x || 0) + (p._length || 100) / 2,
        three_y: (p.z || 0) + (p._height || 100) / 2,
        three_z: (p.y || 0) + (p._width || 100) / 2,
      });
    }
    console.log("=== INSTRUMENT REP 5: 3D scene positions ===");
    console.log(JSON.stringify({
      trace_id: "frontend-" + Date.now(),
      rep: 5,
      label: "3d-scene-positions",
      vehicle_id: this.currentVehicle ? this.currentVehicle.vehicle_id : null,
      packages: _3dPositions,
    }, null, 2));

    // Adjust camera target to container center
    if (this._threeControls) {
      this._threeControls.target.set(d.len / 2, d.hei / 2, d.wid / 2);
      this._threeControls.update();
    }
  }

  _update3DOnResize() {
    if (!this._threeRenderer || !this._threeCamera) return;
    const container = document.getElementById("tlp-3d-container");
    if (!container) return;
    const isFS = container.classList.contains("fullscreen");
    const w = isFS ? window.innerWidth : (container.clientWidth || 360);
    const h = isFS ? window.innerHeight : (container.clientHeight || 280);
    this._threeCamera.aspect = w / h;
    this._threeCamera.updateProjectionMatrix();
    this._threeRenderer.setSize(w, h);
  }

  /* ═══════════════════════ RESIZE OVERRIDE ═══════════════════════ */

  _onResize() {
    this._resizeCanvas();
    if (this.stage) {
      this.stage.width(this.canvasW);
      this.stage.height(this.canvasH);
      this.renderCanvas();
    }
    this._update3DOnResize();
  }
}

/* ═══════════════════════ BOOT ═══════════════════════ */

let app;
document.addEventListener("DOMContentLoaded", () => {
  app = new LoadPlannerApp();
  app.init();
});
