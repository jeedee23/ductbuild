const state = {
  catalog: [],
  filtered: [],
  reviews: {},
  currentFile: null,
  saveTimer: null,
  serverAvailable: false,
};

const elements = {
  pngImage: document.querySelector("#pngImage"),
  pngMissing: document.querySelector("#pngMissing"),
  image: document.querySelector("#svgImage"),
  svgPathGroup: document.querySelector("#svgPathGroup"),
  svgPath: document.querySelector("#svgPath"),
  copySvgPath: document.querySelector("#copySvgPathButton"),
  name: document.querySelector("#drawingName"),
  position: document.querySelector("#positionLabel"),
  previous: document.querySelector("#previousButton"),
  next: document.querySelector("#nextButton"),
  search: document.querySelector("#searchInput"),
  filter: document.querySelector("#filterSelect"),
  drawing: document.querySelector("#drawingSelect"),
  remark: document.querySelector("#remarkInput"),
  approve: document.querySelector("#approveButton"),
  changes: document.querySelector("#changesButton"),
  pending: document.querySelector("#pendingButton"),
  save: document.querySelector("#saveButton"),
  saveStatus: document.querySelector("#saveStatus"),
  importButton: document.querySelector("#importButton"),
  importInput: document.querySelector("#importInput"),
  exportButton: document.querySelector("#exportButton"),
  progressBar: document.querySelector("#progressBar"),
  reviewedCount: document.querySelector("#reviewedCount"),
  progressPercent: document.querySelector("#progressPercent"),
  approvedCount: document.querySelector("#approvedCount"),
  changesCount: document.querySelector("#changesCount"),
  pendingCount: document.querySelector("#pendingCount"),
};

function defaultReview() {
  return {
    status: "pending",
    remark: "",
    updatedAt: null,
  };
}

function normalizePayload(payload) {
  const reviews = payload?.reviews && typeof payload.reviews === "object"
    ? payload.reviews
    : {};

  return Object.fromEntries(
    Object.entries(reviews).map(([file, review]) => [
      file,
      {
        status: ["pending", "approved", "changes-requested"].includes(review?.status)
          ? review.status
          : "pending",
        remark: typeof review?.remark === "string" ? review.remark : "",
        updatedAt: typeof review?.updatedAt === "string" ? review.updatedAt : null,
      },
    ]),
  );
}

function reviewFor(file) {
  return state.reviews[file] ?? defaultReview();
}

async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function loadData() {
  const catalogPayload = await fetchJson("svg-catalog.json");
  state.catalog = Array.isArray(catalogPayload?.items) ? catalogPayload.items : [];

  try {
    const reviewPayload = await fetchJson("/api/reviews");
    state.reviews = normalizePayload(reviewPayload);
    state.serverAvailable = true;
    elements.saveStatus.textContent = "Direct JSON saving is available.";
  } catch {
    try {
      state.reviews = normalizePayload(await fetchJson("reviews.json"));
      elements.saveStatus.textContent = "Reviews loaded. Use Download JSON to save a copy.";
    } catch {
      state.reviews = {};
      elements.saveStatus.textContent = "Starting with an empty review file.";
    }
  }

  const locallySaved = localStorage.getItem("airkan-svg-reviews");
  if (locallySaved) {
    try {
      state.reviews = {
        ...state.reviews,
        ...normalizePayload(JSON.parse(locallySaved)),
      };
      elements.saveStatus.textContent = "Restored browser-local review changes.";
    } catch {
      // Keep the valid JSON data already loaded.
    }
  }

  applyFilters(state.catalog[0]?.file);
}

function applyFilters(preferredFile = state.currentFile) {
  const query = elements.search.value.trim().toLocaleLowerCase();
  const status = elements.filter.value;

  state.filtered = state.catalog.filter((item) => {
    const matchesText = !query || item.name.toLocaleLowerCase().includes(query);
    const matchesStatus = status === "all" || reviewFor(item.file).status === status;
    return matchesText && matchesStatus;
  });

  populateDrawingSelect();

  if (!state.filtered.length) {
    state.currentFile = null;
    renderEmpty();
    return;
  }

  const nextFile = state.filtered.some((item) => item.file === preferredFile)
    ? preferredFile
    : state.filtered[0].file;
  showFile(nextFile);
}

function populateDrawingSelect() {
  elements.drawing.replaceChildren(
    ...state.filtered.map((item) => {
      const option = document.createElement("option");
      option.value = item.file;
      option.textContent = `${statusGlyph(reviewFor(item.file).status)} ${item.name}`;
      return option;
    }),
  );
}

function statusGlyph(status) {
  if (status === "approved") return "✓";
  if (status === "changes-requested") return "!";
  return "○";
}

function renderEmpty() {
  elements.pngImage.removeAttribute("src");
  elements.pngImage.alt = "";
  elements.pngImage.hidden = true;
  elements.pngMissing.hidden = false;
  elements.image.removeAttribute("src");
  elements.image.alt = "";
  elements.svgPath.textContent = "";
  elements.svgPathGroup.hidden = true;
  elements.name.textContent = "No drawings match this filter";
  elements.position.textContent = "0 / 0";
  elements.remark.value = "";
  elements.remark.disabled = true;
  elements.previous.disabled = true;
  elements.next.disabled = true;
  updateDecisionButtons("pending");
  updateProgress();
}

function showFile(file) {
  const item = state.catalog.find((entry) => entry.file === file);
  const filteredIndex = state.filtered.findIndex((entry) => entry.file === file);
  if (!item || filteredIndex < 0) return;

  state.currentFile = file;
  const review = reviewFor(file);

  if (item.png) {
    elements.pngImage.src = encodeURI(item.png);
    elements.pngImage.alt = `Original drawing ${item.name}`;
    elements.pngImage.hidden = false;
    elements.pngMissing.hidden = true;
  } else {
    elements.pngImage.removeAttribute("src");
    elements.pngImage.alt = "";
    elements.pngImage.hidden = true;
    elements.pngMissing.hidden = false;
  }
  elements.image.src = encodeURI(item.file);
  elements.image.alt = `Technical drawing ${item.name}`;
  elements.svgPath.textContent = item.path;
  elements.svgPathGroup.hidden = false;
  elements.name.textContent = item.name;
  elements.position.textContent = `${filteredIndex + 1} / ${state.filtered.length}`;
  elements.drawing.value = file;
  elements.remark.disabled = false;
  elements.remark.value = review.remark;
  elements.previous.disabled = state.filtered.length < 2;
  elements.next.disabled = state.filtered.length < 2;
  updateDecisionButtons(review.status);
  updateProgress();
}

function move(offset) {
  if (!state.currentFile || state.filtered.length < 2) return;
  persistRemark(false);
  const index = state.filtered.findIndex((item) => item.file === state.currentFile);
  const nextIndex = (index + offset + state.filtered.length) % state.filtered.length;
  showFile(state.filtered[nextIndex].file);
}

function updateDecisionButtons(status) {
  elements.approve.classList.toggle("active", status === "approved");
  elements.changes.classList.toggle("active", status === "changes-requested");
  elements.pending.classList.toggle("active", status === "pending");
}

function setStatus(status) {
  if (!state.currentFile) return;
  state.reviews[state.currentFile] = {
    ...reviewFor(state.currentFile),
    status,
    remark: elements.remark.value,
    updatedAt: new Date().toISOString(),
  };
  markDirty();
  applyFilters(state.currentFile);
}

function persistRemark(scheduleSave = true) {
  if (!state.currentFile) return;
  const existing = reviewFor(state.currentFile);
  if (existing.remark === elements.remark.value) return;

  state.reviews[state.currentFile] = {
    ...existing,
    remark: elements.remark.value,
    updatedAt: new Date().toISOString(),
  };
  markDirty(scheduleSave);
  updateProgress();
}

function markDirty(scheduleSave = true) {
  localStorage.setItem("airkan-svg-reviews", JSON.stringify(reviewPayload()));
  elements.saveStatus.textContent = state.serverAvailable
    ? "Unsaved changes…"
    : "Saved in this browser. Download JSON to share or commit.";

  if (scheduleSave && state.serverAvailable) {
    clearTimeout(state.saveTimer);
    state.saveTimer = setTimeout(saveReviews, 500);
  }
}

function reviewPayload() {
  const reviews = {};
  for (const item of state.catalog) {
    reviews[item.file] = reviewFor(item.file);
  }
  return {
    version: 1,
    updatedAt: new Date().toISOString(),
    reviews,
  };
}

async function saveReviews() {
  persistRemark(false);
  if (!state.serverAvailable) {
    downloadReviews();
    return;
  }

  elements.save.disabled = true;
  elements.saveStatus.textContent = "Saving reviews.json…";
  try {
    const response = await fetch("/api/reviews", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(reviewPayload(), null, 2),
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    localStorage.removeItem("airkan-svg-reviews");
    elements.saveStatus.textContent = `Saved reviews.json at ${new Date().toLocaleTimeString()}.`;
  } catch (error) {
    elements.saveStatus.textContent = `Direct save failed: ${error.message}. Downloading JSON instead.`;
    downloadReviews();
  } finally {
    elements.save.disabled = false;
  }
}

function downloadReviews() {
  persistRemark(false);
  const blob = new Blob([`${JSON.stringify(reviewPayload(), null, 2)}\n`], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "reviews.json";
  anchor.click();
  URL.revokeObjectURL(url);
  elements.saveStatus.textContent = "Downloaded reviews.json.";
}

async function importReviews(file) {
  try {
    const payload = JSON.parse(await file.text());
    state.reviews = {
      ...state.reviews,
      ...normalizePayload(payload),
    };
    markDirty(false);
    applyFilters(state.currentFile);
    elements.saveStatus.textContent = `Imported ${file.name}.`;
  } catch (error) {
    elements.saveStatus.textContent = `Could not import JSON: ${error.message}`;
  } finally {
    elements.importInput.value = "";
  }
}

function updateProgress() {
  const statuses = state.catalog.map((item) => reviewFor(item.file).status);
  const approved = statuses.filter((status) => status === "approved").length;
  const changes = statuses.filter((status) => status === "changes-requested").length;
  const pending = statuses.length - approved - changes;
  const reviewed = approved + changes;
  const percent = statuses.length ? Math.round((reviewed / statuses.length) * 100) : 0;

  elements.approvedCount.textContent = approved;
  elements.changesCount.textContent = changes;
  elements.pendingCount.textContent = pending;
  elements.reviewedCount.textContent = `${reviewed} of ${statuses.length} reviewed`;
  elements.progressPercent.textContent = `${percent}%`;
  elements.progressBar.style.width = `${percent}%`;
}

async function copySvgPath() {
  const path = elements.svgPath.textContent;
  if (!path) return;

  try {
    await navigator.clipboard.writeText(path);
    elements.copySvgPath.textContent = "Copied";
    setTimeout(() => {
      elements.copySvgPath.textContent = "Copy path";
    }, 1_500);
  } catch (error) {
    elements.saveStatus.textContent = `Could not copy the SVG path: ${error.message}`;
  }
}

elements.previous.addEventListener("click", () => move(-1));
elements.next.addEventListener("click", () => move(1));
elements.search.addEventListener("input", () => applyFilters());
elements.filter.addEventListener("change", () => applyFilters());
elements.drawing.addEventListener("change", () => showFile(elements.drawing.value));
elements.approve.addEventListener("click", () => setStatus("approved"));
elements.changes.addEventListener("click", () => setStatus("changes-requested"));
elements.pending.addEventListener("click", () => setStatus("pending"));
elements.remark.addEventListener("input", () => persistRemark());
elements.save.addEventListener("click", saveReviews);
elements.exportButton.addEventListener("click", downloadReviews);
elements.copySvgPath.addEventListener("click", copySvgPath);
elements.importButton.addEventListener("click", () => elements.importInput.click());
elements.importInput.addEventListener("change", () => {
  if (elements.importInput.files[0]) importReviews(elements.importInput.files[0]);
});

document.addEventListener("keydown", (event) => {
  if (event.target.matches("input, textarea, select")) return;
  if (event.key === "ArrowLeft") move(-1);
  if (event.key === "ArrowRight") move(1);
  if (event.key.toLocaleLowerCase() === "a") setStatus("approved");
  if (event.key.toLocaleLowerCase() === "x") setStatus("changes-requested");
  if (event.key.toLocaleLowerCase() === "r") elements.remark.focus();
});

loadData().catch((error) => {
  elements.name.textContent = "Could not load the SVG catalog";
  elements.saveStatus.textContent = error.message;
  console.error(error);
});
