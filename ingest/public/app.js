/* GPSA Census — ingest form client logic.
   Staged flow: choose a file → Preview (dry run) → Commit (write).
   Commit stays locked until a preview of the current selection succeeds. */

const ALLOWED_EXTENSIONS = ['.sd3', '.hy3', '.zip'];

const form = document.getElementById('ingest-form');
const fileInput = document.getElementById('file-upload');
const meetType = document.getElementById('meet-type');
const whoInput = document.getElementById('who');
const fileNameLabel = document.getElementById('file-name');
const filePrompt = document.getElementById('file-prompt');
const fileDropzone = document.getElementById('file-dropzone');
const fileIconEmpty = document.getElementById('file-icon-empty');
const fileIconSelected = document.getElementById('file-icon-selected');
const fileError = document.getElementById('file-error');
const previewButton = document.getElementById('preview-button');
const commitButton = document.getElementById('commit-button');
const commitHint = document.getElementById('commit-hint');
const result = document.getElementById('result');

const DROPZONE_EMPTY = ['border-gray-300', 'bg-gray-50', 'hover:bg-gray-100'];
const DROPZONE_SELECTED = ['border-green-500', 'bg-green-50', 'hover:bg-green-100'];

// True only after a successful preview of the *current* file + meet type.
let previewOk = false;

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
}

function extOf(name) {
    return name.toLowerCase().slice(name.lastIndexOf('.'));
}

function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function showFieldError(el, msg) {
    el.textContent = msg;
    el.classList.toggle('hidden', !msg);
}

// ── button state ─────────────────────────────────────────────────────────────
function syncButtons() {
    const hasFile = !!fileInput.files[0];
    previewButton.disabled = !hasFile;
    commitButton.disabled = !(hasFile && previewOk);
    commitHint.classList.toggle('hidden', previewOk);
}

// Any change to the selection invalidates a prior preview.
function invalidatePreview() {
    previewOk = false;
    syncButtons();
}

// ── dropzone states ──────────────────────────────────────────────────────────
function setFileSelected(file) {
    fileDropzone.classList.remove(...DROPZONE_EMPTY);
    fileDropzone.classList.add(...DROPZONE_SELECTED);
    fileDropzone.classList.replace('border-dashed', 'border-solid');
    fileIconEmpty.classList.add('hidden');
    fileIconSelected.classList.remove('hidden');
    filePrompt.innerHTML = '<span class="font-semibold text-green-700">File attached</span> — click to choose a different file';
    fileNameLabel.textContent = `${file.name} (${formatBytes(file.size)})`;
    fileNameLabel.classList.remove('text-gray-500');
    fileNameLabel.classList.add('text-green-700', 'font-medium');
}

function setFileEmpty() {
    fileDropzone.classList.remove(...DROPZONE_SELECTED);
    fileDropzone.classList.add(...DROPZONE_EMPTY);
    fileDropzone.classList.replace('border-solid', 'border-dashed');
    fileIconSelected.classList.add('hidden');
    fileIconEmpty.classList.remove('hidden');
    filePrompt.innerHTML = '<span class="font-semibold">Click to choose a file</span> or drag it here';
    fileNameLabel.textContent = 'Accepted: .sd3, .hy3, or .zip';
    fileNameLabel.classList.remove('text-green-700', 'font-medium');
    fileNameLabel.classList.add('text-gray-500');
}

// ── result rendering ─────────────────────────────────────────────────────────
function showError(msg) {
    result.className = 'mt-6 p-4 rounded-lg text-sm border bg-red-50 text-red-800 border-red-200';
    result.innerHTML = escapeHtml(msg);
    result.classList.remove('hidden');
}

// Renders the parse/commit summary as a titled key/value card.
function showSummary(data, { committed } = {}) {
    const scores = data.teamScores || {};
    const teams = (data.teams || [])
        .map((code) => `${escapeHtml(code)} <span class="font-semibold">${escapeHtml(scores[code] ?? 0)}</span>`)
        .join(' &middot; ');

    // Plain text → escaped; blank → dash.
    const cell = (v) => (v == null || v === '') ? '—' : escapeHtml(v);

    // Each value is trusted HTML with dynamic parts already escaped, so the row
    // template interpolates it raw (no second escaping pass).
    const rows = [
        ['Meet', cell(data.name)],
        ['Date', cell(data.date)],
        ['Season', cell(data.season)],
        ['Format', cell(data.format)],
        ['Teams &amp; scores', teams || '—'],
        ['Events', cell(data.numEvents)],
        ['Results', cell(data.numResults)],
        ['Swimmers', cell(data.numSwimmers)],
        ['Age profile', cell(data.ageProfile)],
        ['Meet key', `<code>${escapeHtml(data.meet_key)}</code>`],
    ].map(([k, v]) => `<div class="flex justify-between gap-4 py-1 border-b border-black/5 last:border-0">
            <span class="text-gray-500">${k}</span>
            <span class="text-gray-900 text-right">${v}</span>
        </div>`).join('');

    let banner, tone;
    if (committed) {
        const verb = data.status === 'updated' ? 'Updated' : 'Committed';
        banner = `✓ ${verb} — written to the census.`;
        tone = 'bg-green-50 text-green-900 border-green-200';
    } else {
        banner = '✓ Preview OK — nothing written yet. Review below, then Commit.';
        tone = 'bg-blue-50 text-blue-900 border-blue-200';
    }

    result.className = `mt-6 p-4 rounded-lg text-sm border ${tone}`;
    result.innerHTML = `<p class="font-semibold mb-3">${banner}</p>
        <div class="bg-white/60 rounded-md p-3">${rows}</div>`;
    result.classList.remove('hidden');
}

// ── validation ───────────────────────────────────────────────────────────────
function validFile() {
    const file = fileInput.files[0];
    if (!file) {
        showFieldError(fileError, 'Please choose a results file.');
        return false;
    }
    if (!ALLOWED_EXTENSIONS.includes(extOf(file.name))) {
        showFieldError(fileError, 'File must be a .sd3, .hy3, or .zip.');
        return false;
    }
    showFieldError(fileError, '');
    return true;
}

function buildFormData(includeMeta) {
    const data = new FormData();
    data.append('file', fileInput.files[0]);
    if (includeMeta) {
        if (meetType.value) data.append('meet_type', meetType.value);
        if (whoInput.value.trim()) data.append('imported_by', whoInput.value.trim());
    }
    return data;
}

async function send(path, includeMeta, button) {
    if (!validFile()) return { ok: false };
    result.classList.add('hidden');

    const original = button.textContent;
    previewButton.disabled = commitButton.disabled = true;
    button.textContent = path === '/api/commit' ? 'Committing…' : 'Previewing…';

    try {
        const res = await fetch(path, { method: 'POST', body: buildFormData(includeMeta) });
        let payload = {};
        try { payload = await res.json(); } catch { /* non-JSON */ }
        if (!res.ok) {
            showError(payload.detail || `Request failed (status ${res.status}).`);
            return { ok: false };
        }
        return { ok: true, payload };
    } catch {
        showError('Network error — could not reach the ingest service.');
        return { ok: false };
    } finally {
        button.textContent = original;
        syncButtons();
    }
}

// ── wiring ───────────────────────────────────────────────────────────────────
fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    if (file) { setFileSelected(file); showFieldError(fileError, ''); }
    else { setFileEmpty(); }
    invalidatePreview();
});

// Meet type is part of what's committed, so changing it invalidates the preview.
meetType.addEventListener('change', invalidatePreview);

// Drag-and-drop onto the dropzone.
['dragenter', 'dragover'].forEach((evt) =>
    fileDropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        fileDropzone.classList.add('ring-2', 'ring-blue-400');
    })
);
['dragleave', 'drop'].forEach((evt) =>
    fileDropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        fileDropzone.classList.remove('ring-2', 'ring-blue-400');
    })
);
fileDropzone.addEventListener('drop', (e) => {
    const file = e.dataTransfer?.files?.[0];
    if (file) {
        fileInput.files = e.dataTransfer.files;
        fileInput.dispatchEvent(new Event('change'));
    }
});

previewButton.addEventListener('click', async () => {
    const { ok, payload } = await send('/api/preview', false, previewButton);
    if (ok) {
        previewOk = true;
        showSummary(payload, { committed: false });
    }
    syncButtons();
});

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!previewOk) return;
    const { ok, payload } = await send('/api/commit', true, commitButton);
    if (ok) {
        showSummary(payload, { committed: true });
        previewOk = false; // require a fresh preview before another commit
        syncButtons();
    }
});

// Initial state.
setFileEmpty();
syncButtons();
