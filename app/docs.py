import base64

from fastapi.responses import HTMLResponse

_FAVICON_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="5" fill="#111827"/>
  <rect x="6" y="4" width="13" height="17" rx="1.5"
        fill="none" stroke="#c9a040" stroke-width="1.5"/>
  <line x1="9"  y1="9"  x2="16" y2="9"
        stroke="#c9a040" stroke-width="1.2" stroke-linecap="round" opacity=".75"/>
  <line x1="9"  y1="12.5" x2="16" y2="12.5"
        stroke="#c9a040" stroke-width="1.2" stroke-linecap="round" opacity=".75"/>
  <line x1="9"  y1="16" x2="13" y2="16"
        stroke="#c9a040" stroke-width="1.2" stroke-linecap="round" opacity=".75"/>
  <circle cx="21" cy="22.5" r="4.5"
          fill="none" stroke="#c9a040" stroke-width="1.6"/>
  <line x1="24.2" y1="25.8" x2="27" y2="28.5"
        stroke="#c9a040" stroke-width="2" stroke-linecap="round"/>
</svg>"""

_FAVICON_URI = (
    "data:image/svg+xml;base64,"
    + base64.b64encode(_FAVICON_SVG.encode()).decode()
)

_CSS = """
/* ── Variables ──────────────────────────────────────────────────── */
:root {
  --bg-base:      #0b1120;
  --bg-surface:   #111827;
  --bg-elevated:  #1a2535;
  --bg-deep:      #0d1626;
  --border:       #1e3a5f;
  --border-dim:   #162030;
  --text-primary: #e2e8f0;
  --text-muted:   #94a3b8;
  --text-dim:     #64748b;
  --gold:         #c9a040;
  --gold-dim:     rgba(201,160,64,.12);
  --gold-glow:    rgba(201,160,64,.18);
  --blue:         #3b82f6;
  --blue-dim:     rgba(59,130,246,.08);
  --green:        #10b981;
  --green-dim:    rgba(16,185,129,.08);
  --amber:        #f59e0b;
  --amber-dim:    rgba(245,158,11,.08);
  --red:          #ef4444;
  --red-dim:      rgba(239,68,68,.08);
  --purple:       #8b5cf6;
  --purple-dim:   rgba(139,92,246,.08);
  --mono:         'JetBrains Mono','Fira Code','Cascadia Code',monospace;
  --sans:         'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  --radius:       6px;
}

/* ── Reset ───────────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; }

html, body {
  margin: 0;
  background: var(--bg-base);
  font-family: var(--sans);
  -webkit-font-smoothing: antialiased;
}

/* ── Custom header ───────────────────────────────────────────────── */
.ldr-header {
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 200;
}
.ldr-header-inner {
  max-width: 1460px;
  margin: 0 auto;
  padding: 14px 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.ldr-brand {
  display: flex;
  align-items: center;
  gap: 14px;
}
.ldr-brand svg { flex-shrink: 0; }
.ldr-brand-name {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -.02em;
  line-height: 1.2;
}
.ldr-brand-sub {
  display: block;
  font-size: 10px;
  font-weight: 500;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: .09em;
  margin-top: 1px;
}
.ldr-badges { display: flex; gap: 8px; align-items: center; }
.ldr-badge {
  font-size: 11px;
  font-weight: 500;
  padding: 3px 10px;
  border-radius: 4px;
  letter-spacing: .02em;
  white-space: nowrap;
}
.ldr-badge-version {
  background: var(--gold-dim);
  color: var(--gold);
  border: 1px solid rgba(201,160,64,.25);
}
.ldr-badge-env-dev {
  background: rgba(16,185,129,.1);
  color: #34d399;
  border: 1px solid rgba(16,185,129,.2);
}
.ldr-badge-env-prod {
  background: rgba(239,68,68,.1);
  color: #fca5a5;
  border: 1px solid rgba(239,68,68,.2);
}

/* ── Hide default Swagger topbar ─────────────────────────────────── */
.swagger-ui .topbar { display: none !important; }

/* ── Main swagger container ──────────────────────────────────────── */
#swagger-ui {
  background: var(--bg-base);
  min-height: calc(100vh - 53px);
  padding-bottom: 80px;
}
.swagger-ui {
  font-family: var(--sans) !important;
  color: var(--text-primary) !important;
}
.swagger-ui .wrapper {
  max-width: 1460px !important;
  padding: 0 28px !important;
}

/* ── Info section ────────────────────────────────────────────────── */
.swagger-ui .info { margin: 36px 0 28px !important; }
.swagger-ui .info hgroup.main { margin: 0 0 16px !important; }
.swagger-ui .info h2.title {
  color: var(--text-primary) !important;
  font-size: 20px !important;
  font-weight: 600 !important;
  letter-spacing: -.025em !important;
  line-height: 1.3 !important;
}
.swagger-ui .info .title small pre {
  background: var(--gold-dim) !important;
  color: var(--gold) !important;
  border: 1px solid rgba(201,160,64,.25) !important;
  border-radius: 4px !important;
  padding: 2px 8px !important;
  font-size: 11px !important;
  font-family: var(--mono) !important;
}
.swagger-ui .info p,
.swagger-ui .info li {
  color: var(--text-muted) !important;
  font-size: 13.5px !important;
  line-height: 1.65 !important;
}
.swagger-ui .info strong { color: var(--text-primary) !important; }
.swagger-ui .info a { color: var(--gold) !important; }
.swagger-ui .info a:hover { color: #d4b04a !important; }
.swagger-ui .info h1,
.swagger-ui .info h2,
.swagger-ui .info h3 {
  color: var(--text-primary) !important;
  border-bottom: 1px solid var(--border-dim) !important;
  padding-bottom: 6px !important;
  margin-top: 20px !important;
}
.swagger-ui .info code {
  background: var(--bg-elevated) !important;
  color: var(--gold) !important;
  padding: 1px 6px !important;
  border-radius: 3px !important;
  font-family: var(--mono) !important;
  font-size: 12px !important;
}
.swagger-ui .info pre {
  background: var(--bg-deep) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius) !important;
  padding: 14px 18px !important;
  color: var(--text-muted) !important;
  font-family: var(--mono) !important;
  font-size: 12.5px !important;
  overflow-x: auto !important;
}
.swagger-ui .info table { width: 100% !important; border-collapse: collapse !important; }
.swagger-ui .info table th {
  background: var(--bg-elevated) !important;
  color: var(--text-dim) !important;
  font-size: 11px !important;
  font-weight: 600 !important;
  text-transform: uppercase !important;
  letter-spacing: .06em !important;
  border: 1px solid var(--border) !important;
  padding: 8px 14px !important;
  text-align: left !important;
}
.swagger-ui .info table td {
  background: var(--bg-surface) !important;
  color: var(--text-muted) !important;
  border: 1px solid var(--border-dim) !important;
  padding: 8px 14px !important;
  font-size: 13px !important;
}
.swagger-ui .info .contact, .swagger-ui .info .license {
  color: var(--text-dim) !important; font-size: 12px !important;
}
.swagger-ui .info .contact a, .swagger-ui .info .license a {
  color: var(--gold) !important;
}

/* ── Scheme container (server URL selector) ──────────────────────── */
.swagger-ui .scheme-container {
  background: var(--bg-surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius) !important;
  box-shadow: none !important;
  padding: 16px 22px !important;
  margin-bottom: 24px !important;
}
.swagger-ui .scheme-container .schemes > label {
  color: var(--text-muted) !important;
  font-size: 11px !important;
  font-weight: 600 !important;
  text-transform: uppercase !important;
  letter-spacing: .07em !important;
}
.swagger-ui .servers > label {
  color: var(--text-muted) !important;
  font-size: 12px !important;
}

/* ── Filter / search bar ─────────────────────────────────────────── */
.swagger-ui .filter .operation-filter-input {
  background: var(--bg-surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius) !important;
  color: var(--text-primary) !important;
  font-size: 13.5px !important;
  padding: 9px 14px !important;
  width: 100% !important;
  font-family: var(--sans) !important;
}
.swagger-ui .filter .operation-filter-input:focus {
  border-color: var(--gold) !important;
  box-shadow: 0 0 0 3px var(--gold-glow) !important;
  outline: none !important;
}
.swagger-ui .filter .operation-filter-input::placeholder { color: var(--text-dim) !important; }

/* ── Operation tags (group headers) ──────────────────────────────── */
.swagger-ui .opblock-tag-section { margin-bottom: 6px !important; }
.swagger-ui .opblock-tag {
  border-bottom: 1px solid var(--border-dim) !important;
  color: var(--text-primary) !important;
  font-size: 16px !important;
  font-weight: 600 !important;
  letter-spacing: -.015em !important;
  padding: 18px 0 12px !important;
  margin: 28px 0 4px !important;
  display: flex !important;
  align-items: center !important;
  gap: 10px !important;
}
.swagger-ui .opblock-tag:hover { background: transparent !important; color: var(--gold) !important; }
.swagger-ui .opblock-tag a { color: inherit !important; text-decoration: none !important; }
.swagger-ui .opblock-tag small {
  color: var(--text-dim) !important;
  font-size: 12.5px !important;
  font-weight: 400 !important;
  margin-left: 4px !important;
}
.swagger-ui .opblock-tag svg { fill: var(--text-dim) !important; }

/* ── Operation blocks ────────────────────────────────────────────── */
.swagger-ui .opblock {
  background: var(--bg-surface) !important;
  border: 1px solid var(--border-dim) !important;
  border-radius: var(--radius) !important;
  box-shadow: none !important;
  margin: 5px 0 !important;
  overflow: hidden !important;
}
.swagger-ui .opblock .opblock-summary {
  border-bottom: none !important;
  padding: 0 !important;
  align-items: stretch !important;
}
.swagger-ui .opblock .opblock-summary-control {
  padding: 10px 16px !important;
  display: flex !important;
  align-items: center !important;
  gap: 12px !important;
  width: 100% !important;
  cursor: pointer !important;
}
.swagger-ui .opblock .opblock-summary-control:hover {
  background: rgba(255,255,255,.02) !important;
}
.swagger-ui .opblock.is-open .opblock-summary {
  border-bottom: 1px solid var(--border-dim) !important;
}

/* GET */
.swagger-ui .opblock.opblock-get {
  border-left: 3px solid var(--blue) !important;
}
.swagger-ui .opblock.opblock-get .opblock-summary-control {
  background: var(--blue-dim) !important;
}
.swagger-ui .opblock.opblock-get .opblock-summary-method {
  background: var(--blue) !important;
}

/* POST */
.swagger-ui .opblock.opblock-post {
  border-left: 3px solid var(--green) !important;
}
.swagger-ui .opblock.opblock-post .opblock-summary-control {
  background: var(--green-dim) !important;
}
.swagger-ui .opblock.opblock-post .opblock-summary-method {
  background: var(--green) !important;
}

/* PUT */
.swagger-ui .opblock.opblock-put {
  border-left: 3px solid var(--amber) !important;
}
.swagger-ui .opblock.opblock-put .opblock-summary-control {
  background: var(--amber-dim) !important;
}
.swagger-ui .opblock.opblock-put .opblock-summary-method {
  background: var(--amber) !important;
}

/* DELETE */
.swagger-ui .opblock.opblock-delete {
  border-left: 3px solid var(--red) !important;
}
.swagger-ui .opblock.opblock-delete .opblock-summary-control {
  background: var(--red-dim) !important;
}
.swagger-ui .opblock.opblock-delete .opblock-summary-method {
  background: var(--red) !important;
}

/* PATCH */
.swagger-ui .opblock.opblock-patch {
  border-left: 3px solid var(--purple) !important;
}
.swagger-ui .opblock.opblock-patch .opblock-summary-control {
  background: var(--purple-dim) !important;
}
.swagger-ui .opblock.opblock-patch .opblock-summary-method {
  background: var(--purple) !important;
}

/* Method badge */
.swagger-ui .opblock-summary-method {
  border-radius: 4px !important;
  font-size: 10.5px !important;
  font-weight: 700 !important;
  letter-spacing: .06em !important;
  min-width: 64px !important;
  text-align: center !important;
  padding: 5px 8px !important;
  flex-shrink: 0 !important;
  font-family: var(--sans) !important;
}

/* Path */
.swagger-ui .opblock-summary-path {
  color: var(--text-primary) !important;
  font-size: 13.5px !important;
  font-weight: 500 !important;
  font-family: var(--mono) !important;
  flex: 1 !important;
}
.swagger-ui .opblock-summary-path__deprecated {
  color: var(--text-dim) !important;
  text-decoration: line-through !important;
}

/* Summary description */
.swagger-ui .opblock-summary-description {
  color: var(--text-dim) !important;
  font-size: 12.5px !important;
  text-align: right !important;
  flex-shrink: 0 !important;
}

/* Expand chevron */
.swagger-ui .opblock-summary-control svg { fill: var(--text-dim) !important; }
.swagger-ui .arrow { fill: var(--text-dim) !important; }

/* Expanded body */
.swagger-ui .opblock-body {
  background: var(--bg-deep) !important;
}

/* ── Section headers (Parameters, Request Body) ───────────────────── */
.swagger-ui .opblock-section-header {
  background: var(--bg-deep) !important;
  border-bottom: 1px solid var(--border-dim) !important;
  padding: 10px 20px !important;
  box-shadow: none !important;
}
.swagger-ui .opblock-section-header h4 {
  color: var(--text-dim) !important;
  font-size: 11px !important;
  font-weight: 600 !important;
  text-transform: uppercase !important;
  letter-spacing: .08em !important;
  margin: 0 !important;
}
.swagger-ui .opblock-section-header label {
  color: var(--text-muted) !important;
  font-size: 12px !important;
}

/* ── Parameter tables ────────────────────────────────────────────── */
.swagger-ui table { border-collapse: collapse !important; }
.swagger-ui table thead tr th,
.swagger-ui table thead tr td {
  background: var(--bg-surface) !important;
  color: var(--text-dim) !important;
  font-size: 10.5px !important;
  font-weight: 600 !important;
  text-transform: uppercase !important;
  letter-spacing: .07em !important;
  border: none !important;
  border-bottom: 1px solid var(--border-dim) !important;
  padding: 9px 16px !important;
}
.swagger-ui table tbody tr td {
  background: transparent !important;
  border-bottom: 1px solid var(--border-dim) !important;
  padding: 11px 16px !important;
  color: var(--text-muted) !important;
  font-size: 13px !important;
  vertical-align: top !important;
}
.swagger-ui .parameter__name {
  color: var(--text-primary) !important;
  font-family: var(--mono) !important;
  font-size: 13px !important;
  font-weight: 500 !important;
}
.swagger-ui .parameter__type { color: var(--text-dim) !important; font-size: 11.5px !important; }
.swagger-ui .parameter__in {
  color: var(--gold) !important;
  font-size: 10.5px !important;
  font-style: normal !important;
  background: var(--gold-dim) !important;
  padding: 1px 6px !important;
  border-radius: 3px !important;
  font-family: var(--sans) !important;
}
.swagger-ui .parameter__deprecated {
  color: var(--text-dim) !important;
  font-style: italic !important;
}
.swagger-ui .required-label { color: var(--red) !important; font-size: 10px !important; }
.swagger-ui .parameter__name.required > span {
  color: var(--red) !important;
  font-size: 10px !important;
}

/* ── Inputs, textareas, selects ──────────────────────────────────── */
.swagger-ui input[type=text],
.swagger-ui input[type=password],
.swagger-ui input[type=search],
.swagger-ui input[type=email],
.swagger-ui input[type=number],
.swagger-ui textarea,
.swagger-ui select {
  background: var(--bg-base) !important;
  border: 1px solid var(--border) !important;
  border-radius: 4px !important;
  color: var(--text-primary) !important;
  font-size: 13px !important;
  font-family: var(--mono) !important;
  padding: 7px 10px !important;
  transition: border-color .15s, box-shadow .15s !important;
}
.swagger-ui input[type=text]:focus,
.swagger-ui input[type=password]:focus,
.swagger-ui textarea:focus,
.swagger-ui select:focus {
  border-color: var(--gold) !important;
  box-shadow: 0 0 0 3px var(--gold-glow) !important;
  outline: none !important;
}
.swagger-ui input::placeholder,
.swagger-ui textarea::placeholder { color: var(--text-dim) !important; }
.swagger-ui select option { background: var(--bg-surface) !important; }

/* ── Buttons ─────────────────────────────────────────────────────── */
.swagger-ui .btn {
  border-radius: 5px !important;
  font-size: 12.5px !important;
  font-weight: 500 !important;
  padding: 7px 16px !important;
  box-shadow: none !important;
  letter-spacing: .01em !important;
  transition: background .15s, border-color .15s, color .15s !important;
  font-family: var(--sans) !important;
  cursor: pointer !important;
}
.swagger-ui .btn.authorize {
  background: transparent !important;
  border: 1px solid var(--gold) !important;
  color: var(--gold) !important;
}
.swagger-ui .btn.authorize:hover { background: var(--gold-dim) !important; }
.swagger-ui .btn.authorize svg { fill: var(--gold) !important; }
.swagger-ui .authorization__btn svg { fill: var(--gold) !important; }

.swagger-ui .btn.execute {
  background: #1c3a6e !important;
  border: 1px solid #2a5298 !important;
  color: #93c5fd !important;
}
.swagger-ui .btn.execute:hover { background: #22437e !important; }

.swagger-ui .btn.try-out__btn {
  background: transparent !important;
  border: 1px solid var(--border) !important;
  color: var(--text-muted) !important;
}
.swagger-ui .btn.try-out__btn:hover {
  border-color: var(--blue) !important;
  color: #93c5fd !important;
}
.swagger-ui .btn.try-out__btn.cancel {
  border-color: var(--red) !important;
  color: #fca5a5 !important;
}
.swagger-ui .btn.btn-clear, .swagger-ui .btn.btn-clear:hover {
  background: transparent !important;
  border: 1px solid var(--border) !important;
  color: var(--text-dim) !important;
}

/* ── Responses ───────────────────────────────────────────────────── */
.swagger-ui .responses-wrapper { padding: 0 !important; }
.swagger-ui .responses-inner {
  background: var(--bg-deep) !important;
  padding: 16px 20px !important;
}
.swagger-ui .response-col_status {
  color: var(--text-primary) !important;
  font-family: var(--mono) !important;
  font-size: 13.5px !important;
  font-weight: 600 !important;
}
.swagger-ui .response-col_description { color: var(--text-muted) !important; font-size: 13px !important; }
.swagger-ui .response-col_links { color: var(--text-dim) !important; }

/* ── Code / response body ────────────────────────────────────────── */
.swagger-ui .highlight-code,
.swagger-ui .microlight {
  background: var(--bg-base) !important;
  border: 1px solid var(--border-dim) !important;
  border-radius: 4px !important;
}
.swagger-ui .highlight-code pre,
.swagger-ui .microlight pre {
  color: var(--text-muted) !important;
  font-family: var(--mono) !important;
  font-size: 12.5px !important;
  line-height: 1.55 !important;
  margin: 0 !important;
  padding: 14px 16px !important;
}
.swagger-ui .copy-to-clipboard {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border) !important;
  border-radius: 4px !important;
}
.swagger-ui .copy-to-clipboard svg { fill: var(--text-dim) !important; }
.swagger-ui .copy-to-clipboard:hover { background: var(--border) !important; }

/* ── Models / Schemas ────────────────────────────────────────────── */
.swagger-ui section.models {
  background: var(--bg-surface) !important;
  border: 1px solid var(--border-dim) !important;
  border-radius: var(--radius) !important;
  margin-top: 40px !important;
}
.swagger-ui section.models.is-open { padding-bottom: 16px !important; }
.swagger-ui section.models h4 {
  color: var(--text-dim) !important;
  font-size: 11px !important;
  font-weight: 600 !important;
  text-transform: uppercase !important;
  letter-spacing: .08em !important;
  border-bottom: 1px solid var(--border-dim) !important;
  padding: 14px 20px !important;
  margin: 0 !important;
  display: flex !important;
  align-items: center !important;
  gap: 8px !important;
  cursor: pointer !important;
}
.swagger-ui section.models h4 svg { fill: var(--text-dim) !important; }
.swagger-ui section.models h4:hover { color: var(--text-muted) !important; }
.swagger-ui .model-container {
  background: var(--bg-deep) !important;
  border-radius: 5px !important;
  margin: 10px 16px !important;
  padding: 14px 18px !important;
  border: 1px solid var(--border-dim) !important;
}
.swagger-ui .model-box {
  background: transparent !important;
  padding: 0 !important;
}
.swagger-ui .model-title {
  color: var(--gold) !important;
  font-size: 13px !important;
  font-weight: 600 !important;
  font-family: var(--mono) !important;
}
.swagger-ui .model { color: var(--text-muted) !important; font-size: 12.5px !important; }
.swagger-ui .model .property,
.swagger-ui .model .primitive { color: var(--text-muted) !important; }
.swagger-ui .model .property.readonly .property-name,
.swagger-ui .model .property-name {
  color: var(--text-primary) !important;
  font-family: var(--mono) !important;
  font-size: 12.5px !important;
}
.swagger-ui .prop-type { color: var(--blue) !important; }
.swagger-ui .prop-format { color: var(--text-dim) !important; }
.swagger-ui .model-toggle {
  background: var(--bg-elevated) !important;
  border-color: var(--border) !important;
}
.swagger-ui .models-control svg { fill: var(--text-dim) !important; }

/* ── Authorization modal ─────────────────────────────────────────── */
.swagger-ui .dialog-ux .backdrop-ux { background: rgba(0,0,0,.7) !important; }
.swagger-ui .dialog-ux .modal-ux {
  background: var(--bg-surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: 8px !important;
  box-shadow: 0 24px 48px rgba(0,0,0,.5) !important;
}
.swagger-ui .dialog-ux .modal-ux-header {
  background: var(--bg-deep) !important;
  border-bottom: 1px solid var(--border) !important;
  border-radius: 8px 8px 0 0 !important;
  padding: 16px 20px !important;
}
.swagger-ui .dialog-ux .modal-ux-header h3 {
  color: var(--text-primary) !important;
  font-size: 15px !important;
  font-weight: 600 !important;
  margin: 0 !important;
}
.swagger-ui .dialog-ux .modal-ux-content { padding: 20px !important; }
.swagger-ui .dialog-ux .modal-ux-content p { color: var(--text-muted) !important; font-size: 13px !important; }
.swagger-ui .dialog-ux .modal-ux-content code {
  background: var(--bg-elevated) !important;
  color: var(--gold) !important;
  padding: 1px 5px !important;
  border-radius: 3px !important;
  font-family: var(--mono) !important;
  font-size: 12px !important;
}

/* ── Markdown prose ──────────────────────────────────────────────── */
.swagger-ui .renderedMarkdown p { color: var(--text-muted) !important; line-height: 1.65 !important; font-size: 13px !important; }
.swagger-ui .renderedMarkdown code {
  background: var(--bg-elevated) !important;
  color: var(--gold) !important;
  padding: 1px 5px !important;
  border-radius: 3px !important;
  font-family: var(--mono) !important;
  font-size: 11.5px !important;
}
.swagger-ui .renderedMarkdown a { color: var(--gold) !important; }
.swagger-ui .renderedMarkdown h1,
.swagger-ui .renderedMarkdown h2,
.swagger-ui .renderedMarkdown h3 { color: var(--text-primary) !important; }
.swagger-ui .renderedMarkdown pre {
  background: var(--bg-deep) !important;
  border: 1px solid var(--border-dim) !important;
  border-radius: 4px !important;
  padding: 12px 16px !important;
}
.swagger-ui .renderedMarkdown ul li { color: var(--text-muted) !important; }

/* ── Loading spinner ─────────────────────────────────────────────── */
.swagger-ui .loading-container .loading::after {
  border-color: var(--gold) var(--gold) transparent transparent !important;
}

/* ── Misc ────────────────────────────────────────────────────────── */
.swagger-ui .content-type {
  border: 1px solid var(--border) !important;
  border-radius: 4px !important;
  color: var(--text-muted) !important;
  background: var(--bg-surface) !important;
}
.swagger-ui .opblock-deprecated { opacity: .45 !important; }
.swagger-ui .expand-methods svg,
.swagger-ui .expand-operation svg { fill: var(--text-dim) !important; }

/* ── Scrollbars ──────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 7px; height: 7px; }
::-webkit-scrollbar-track { background: var(--bg-base); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #2d5280; }
"""

def get_docs_html(
    *,
    openapi_url: str,
    title: str,
    version: str,
    environment: str,
) -> HTMLResponse:
    env_badge_class = (
        "ldr-badge-env-prod" if environment == "production" else "ldr-badge-env-dev"
    )
    env_label = environment.capitalize()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta name="theme-color" content="#111827"/>
  <title>{title}</title>
  <link rel="icon" type="image/svg+xml" href="{_FAVICON_URI}"/>
  <link rel="stylesheet"
        href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"/>
  <style>{_CSS}</style>
</head>
<body>

<header class="ldr-header">
  <div class="ldr-header-inner">
    <div class="ldr-brand">
      <svg width="28" height="28" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg">
        <rect width="32" height="32" rx="5" fill="#0f1729"/>
        <rect x="6" y="4" width="13" height="17" rx="1.5"
              fill="none" stroke="#c9a040" stroke-width="1.5"/>
        <line x1="9"  y1="9"    x2="16" y2="9"
              stroke="#c9a040" stroke-width="1.2" stroke-linecap="round" opacity=".75"/>
        <line x1="9"  y1="12.5" x2="16" y2="12.5"
              stroke="#c9a040" stroke-width="1.2" stroke-linecap="round" opacity=".75"/>
        <line x1="9"  y1="16"   x2="13" y2="16"
              stroke="#c9a040" stroke-width="1.2" stroke-linecap="round" opacity=".75"/>
        <circle cx="21" cy="22.5" r="4.5"
                fill="none" stroke="#c9a040" stroke-width="1.6"/>
        <line x1="24.2" y1="25.8" x2="27" y2="28.5"
              stroke="#c9a040" stroke-width="2" stroke-linecap="round"/>
      </svg>
      <div>
        <span class="ldr-brand-name">{title}</span>
        <span class="ldr-brand-sub">API Reference</span>
      </div>
    </div>
    <div class="ldr-badges">
      <span class="ldr-badge ldr-badge-version">v{version}</span>
      <span class="ldr-badge {env_badge_class}">{env_label}</span>
    </div>
  </div>
</header>

<div id="swagger-ui"></div>

<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
  SwaggerUIBundle({{
    url:          "{openapi_url}",
    dom_id:       "#swagger-ui",
    presets:      [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
    layout:       "BaseLayout",
    deepLinking:              true,
    defaultModelsExpandDepth: 1,
    defaultModelExpandDepth:  2,
    docExpansion:             "list",
    filter:                   true,
    displayRequestDuration:   true,
    persistAuthorization:     true,
    tryItOutEnabled:          false,
    syntaxHighlight: {{
      activate: true,
      theme:    "arta"
    }}
  }});
</script>
</body>
</html>"""

    return HTMLResponse(html)
