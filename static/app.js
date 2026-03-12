/* ═══════════════════════════════════════════════════════════
   Intelli-Credit — Frontend Application Logic (v2)
   All 15 improvements implemented
   ═══════════════════════════════════════════════════════════ */

// ─── Navigation ────────────────────────────────────────
// Sidebar icon buttons
document.querySelectorAll('.sidebar-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        e.preventDefault();
        const view = btn.dataset.view;
        openTab(view);
    });
});

// Header tab links
document.querySelectorAll('.tab-link').forEach(link => {
    link.addEventListener('click', (e) => {
        e.preventDefault();
        const view = link.dataset.view;
        openTab(view);
    });
});

// ═══ TAB NAVIGATION ════════════════════════════════════
function openTab(viewId) {
    // Sync sidebar buttons
    document.querySelectorAll('.sidebar-btn').forEach(b => b.classList.remove('active'));
    const sidebarBtn = document.querySelector(`.sidebar-btn[data-view="${viewId}"]`);
    if (sidebarBtn) sidebarBtn.classList.add('active');

    // Sync header tab links
    document.querySelectorAll('.tab-link').forEach(l => l.classList.remove('active'));
    const tabLink = document.querySelector(`.tab-link[data-view="${viewId}"]`);
    if (tabLink) tabLink.classList.add('active');

    // Switch views
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.getElementById(`view-${viewId}`).classList.add('active');

    // UX: Carry entity context to Analysis tab
    if (viewId === 'analysis' && currentEntityId) {
        const analyzeInput = document.getElementById('analysis-entity-id'); // Corrected ID
        if (analyzeInput && !analyzeInput.value) {
            analyzeInput.value = currentEntityId;
        }
    } else if (viewId === 'notes') {
        initOfficerNotesTab();
    }
}

function initOfficerNotesTab() {
    const entityIdField = document.getElementById('note-entity-id');
    if (window.intelliCreditState && window.intelliCreditState.currentEntityId) {
        entityIdField.value = window.intelliCreditState.currentEntityId;
        loadNotesHistory(window.intelliCreditState.currentEntityId);
    }
    attachNoteDetection();
}

window.intelliCreditState = {
    currentEntityId: null,
    currentCompanyName: null,
    currentDecision: null
};

// ─── State ─────────────────────────────────────────────
let currentEntityId = '';
let allEntities = [];
let fiveCsChart = null;
let shapChart = null;
let loadingInterval; // Added for loading progress bar

// ─── Init ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    checkHealth();
    loadEntities();
    setupFileDrop();

    // BUG 1: Read ?entity= from URL or localStorage
    const urlParams = new URLSearchParams(window.location.search);
    const entityParam = urlParams.get('entity');
    const lastAnalyzed = localStorage.getItem('last_analyzed_entity');

    const targetEntity = entityParam || lastAnalyzed;

    if (targetEntity) {
        localStorage.removeItem('last_analyzed_entity');
        document.getElementById('entity-search').value = targetEntity;
        currentEntityId = targetEntity;

        // Update headers immediately
        document.getElementById('entity-header-id').textContent = targetEntity;
        document.getElementById('entity-header-name').textContent = targetEntity;

        // Clean up URL without reloading
        window.history.replaceState({}, document.title, window.location.pathname);
        loadCompany();
    }
});

// ═══ HEALTH CHECK ══════════════════════════════════════
async function checkHealth() {
    try {
        const res = await fetch('/api/health');
        const data = await res.json();
        const dot = document.getElementById('status-dot');
        const text = document.getElementById('status-text');
        dot.classList.add('online');
        if (data.databricks && data.databricks.includes('offline')) {
            text.textContent = 'In-Memory Mode';
            dot.classList.add('warning');
        } else if (data.databricks_read === 'connected' && data.databricks_write === 'connected') {
            text.textContent = 'DB Read/Write OK';
        } else if (data.databricks_read === 'connected') {
            text.textContent = 'DB Read Only';
            dot.classList.add('warning');
        } else {
            text.textContent = 'Connected';
        }
    } catch {
        document.getElementById('status-dot').classList.add('offline');
        document.getElementById('status-text').textContent = 'Offline';
    }
}

// ═══ ENTITY LISTING & SEARCH AUTOCOMPLETE (#5) ════════
async function loadEntities() {
    try {
        const res = await fetch('/api/entities');
        const data = await res.json();
        allEntities = data.entities || [];
    } catch {
        allEntities = [];
    }
}

function handleSearchInput(val) {
    const container = document.getElementById('search-suggestions');
    if (!val || val.length < 1) {
        container.classList.add('hidden');
        return;
    }
    const q = val.toLowerCase();
    const matches = allEntities.filter(e =>
        e.entity_id.toLowerCase().includes(q) ||
        (e.company_name || '').toLowerCase().includes(q)
    ).slice(0, 8);

    if (matches.length === 0) {
        container.classList.add('hidden');
        return;
    }

    container.innerHTML = matches.map(e => `
        <div class="suggestion" onclick="selectEntity('${e.entity_id}')">
            <strong>${e.entity_id}</strong>
            <span class="suggestion-name">${e.company_name || ''}</span>
        </div>
    `).join('');
    container.classList.remove('hidden');
}

function selectEntity(id) {
    document.getElementById('entity-search').value = id;
    document.getElementById('search-suggestions').classList.add('hidden');
    loadCompany();
}

// ═══ KEYBOARD SHORTCUTS (#18) ═════════════════════════
document.getElementById('entity-search')?.addEventListener('keypress', function (e) {
    if (e.key === 'Enter') {
        loadCompany();
        document.getElementById('search-suggestions').classList.add('hidden');
    }
});

// ═══ SEED DEMO DATA (#3) ══════════════════════════════
async function seedDemo() {
    showLoading('Seeding demo data...');
    try {
        const res = await fetch('/api/seed-demo', { method: 'POST' });
        const data = await res.json();
        hideLoading();
        if (data.status === 'success') {
            showToast(`Seeded ${data.count} demo entities`, 'success');
            await loadEntities();
        } else {
            showToast('Seed failed: ' + (data.message || 'Unknown error'), 'error');
        }
    } catch (e) {
        hideLoading();
        showToast('Seed error: ' + e.message, 'error');
    }
}

// ═══ LOAD COMPANY ══════════════════════════════════════
let isLoadingData = false;
let flagsController = null;

async function loadCompany() {
    const id = document.getElementById('entity-search').value.trim();
    if (!id) { showToast('Please enter an Entity ID', 'warning'); return; }

    // FIX REGRESSION D (Root Cause): Immediately sync global state before any awaits
    window.currentLoadedEntity = id;

    if (isLoadingData) return;

    isLoadingData = true;
    currentEntityId = id;
    showLoading('Loading company data...');

    // BUG 1 FIX: 10-second timeout so spinner never hangs forever
    const loadController = new AbortController();
    const loadTimeout = setTimeout(() => loadController.abort(), 10000);

    try {
        // PERFORMANCE BOOST: Fetch lightweight summary first for instant UI
        const res = await fetch(`/api/company/summary/${id}`, { signal: loadController.signal });
        clearTimeout(loadTimeout);
        if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
        const summaryData = await res.json();
        hideLoading();

        // Update global state
        window.intelliCreditState.currentEntityId = summaryData.entity_id;
        window.intelliCreditState.currentCompanyName = summaryData.financials?.[0]?.company_name;

        // Render dashboard immediately with summary data
        renderDashboard(summaryData);
        loadProgress(id);

        // Show the summary toast
        showToast(`Loaded: ${summaryData.financials?.[0]?.company_name || id}`, 'success');

        // Show Re-Run button
        const rerunBtn = document.getElementById('btn-rerun-analysis');
        if (rerunBtn) {
            rerunBtn.classList.remove('hidden');
            rerunBtn.onclick = () => runAnalysis(id);
        }

        // UX Polish: Auto-load notes history
        loadNotesHistory(id);

        // Fetch full payload in background to backfill flags, research, and notes
        fetchRiskFlags(id);

    } catch (e) {
        clearTimeout(loadTimeout);
        hideLoading();
        const msg = e.name === 'AbortError'
            ? 'Request timed out — server may be busy. Please try again.'
            : 'Failed to load: ' + e.message;
        showToast(msg, 'error');
    } finally {
        isLoadingData = false;
    }
}

async function fetchRiskFlags(id) {
    if (flagsController) flagsController.abort();
    flagsController = new AbortController();

    try {
        const res = await fetch(`/api/company/${id}`, { signal: flagsController.signal });
        const fullData = await res.json();

        // Only render if still on same entity
        if (window.currentLoadedEntity !== id) return;

        renderFlags(fullData.flags || []);
        renderResearchInDashboard(fullData.research_findings || []);
        if (fullData.decision && fullData.decision.decision_reasons) {
            let reasons = fullData.decision.decision_reasons;
            if (typeof reasons === 'string') {
                try { reasons = JSON.parse(reasons); } catch { reasons = []; }
            }
            renderReasons(reasons || []);
        }
    } catch (err) {
        if (err.name !== 'AbortError') {
            console.error("Background full-data fetch failed:", err);
        }
    }
}

// ═══ WORKFLOW PROGRESS (#14) ══════════════════════════
async function loadProgress(entityId) {
    try {
        const res = await fetch(`/api/progress/${entityId}`);
        const data = await res.json();
        const container = document.getElementById('progress-bar-container');
        container.classList.remove('hidden');

        // Always show, calculate highest linear step achieved
        const highestStep = data.steps.report_ready ? 6 :
            data.steps.analyzed ? 5 :
                data.steps.notes_added ? 4 :
                    data.steps.research_done ? 3 :
                        data.steps.gst_analyzed ? 2 : 1;

        const ids = ['step-data', 'step-gst', 'step-research', 'step-notes', 'step-analyzed', 'step-report'];

        ids.forEach((id, index) => {
            const el = document.getElementById(id);
            if (el) el.classList.toggle('completed', (index + 1) <= highestStep);
        });

        document.getElementById('progress-fill').style.width = ((highestStep / 6) * 100) + '%';
    } catch { /* ignore */ }
}

// ═══ RENDER DASHBOARD ══════════════════════════════════
function renderDashboard(data) {
    document.getElementById('dashboard-content').classList.remove('hidden');

    // Company Info
    const fin = data.financials?.[0] || {};
    const gst = data.gst_analysis?.[0] || {};
    const cibil = data.cibil_data || {};

    document.getElementById('company-info').innerHTML = `
        <div class="info-grid">
            <div class="info-item"><span class="info-label">Company</span><span class="info-value">${fin.company_name || data.entity_id}</span></div>
            <div class="info-item"><span class="info-label">Entity ID</span><span class="info-value">${data.entity_id}</span></div>
            <div class="info-item"><span class="info-label">Revenue</span><span class="info-value">${formatAmount(fin.revenue)}</span></div>
            <div class="info-item"><span class="info-label">EBITDA</span><span class="info-value">${formatAmount(fin.ebitda)}</span></div>
            <div class="info-item"><span class="info-label">Net Profit</span><span class="info-value">${formatAmount(fin.net_profit)}</span></div>
            <div class="info-item"><span class="info-label">Total Debt</span><span class="info-value">${formatAmount(fin.total_debt)}</span></div>
            <div class="info-item"><span class="info-label">Net Worth</span><span class="info-value">${formatAmount(fin.net_worth)}</span></div>
            <div class="info-item"><span class="info-label">D/E Ratio</span><span class="info-value">${fin.net_worth ? (fin.total_debt / fin.net_worth).toFixed(2) + 'x' : '--'}</span></div>
            <div class="info-item"><span class="info-label">CIBIL Score</span><span class="info-value score-${cibil.cibil_score >= 750 ? 'green' : cibil.cibil_score >= 600 ? 'amber' : 'red'}">${cibil.cibil_score || '--'}</span></div>
            <div class="info-item"><span class="info-label">Operating Margin</span><span class="info-value">${fin.operating_margin ? fin.operating_margin.toFixed(1) + '%' : '--'}</span></div>
            <div class="info-item"><span class="info-label">GST Mismatch</span><span class="info-value ${gst.mismatch_pct > 10 ? 'score-red' : ''}">${gst.mismatch_pct ? gst.mismatch_pct.toFixed(1) + '%' : '--'}</span></div>
            <div class="info-item"><span class="info-label">Revenue Growth</span><span class="info-value">${fin.revenue_growth_yoy ? fin.revenue_growth_yoy.toFixed(1) + '%' : '--'}</span></div>
        </div>
    `;

    // Decision banner
    if (data.decision) {
        renderDecisionBanner(data.decision);
    } else {
        document.getElementById('decision-banner').classList.add('hidden');
    }

    // Five Cs Chart
    if (data.decision?.five_cs || data.decision?.character_score) {
        const fiveCs = data.decision.five_cs || {
            character: data.decision.character_score,
            capacity: data.decision.capacity_score,
            capital: data.decision.capital_score,
            collateral: data.decision.collateral_score,
            conditions: data.decision.conditions_score,
        };
        renderFiveCsChart(fiveCs);
    }

    // SHAP chart
    if (data.decision?.shap_explanations) {
        let shap = data.decision.shap_explanations;
        if (typeof shap === 'string') {
            try { shap = JSON.parse(shap); } catch { shap = {}; }
        }
        if (shap && typeof shap === 'object') {
            try { renderShapChart(shap); } catch (err) { console.error("SHAP visualizer error:", err); }
        }
    }

    // Flags
    renderFlags(data.flags || []);

    // Decision reasons
    if (data.decision) {
        let reasons = data.decision.decision_reasons;
        if (typeof reasons === 'string') {
            try { reasons = JSON.parse(reasons); } catch { reasons = []; }
        }
        renderReasons(reasons || []);
    }

    // GSTR Alert (#8)
    if (gst.mismatch_pct && gst.mismatch_pct > 10) {
        renderGSTRAlert(gst);
    }

    // Research findings with source URLs (#9)
    renderResearchInDashboard(data.research_findings || []);
}

function formatLoanAmount(amount, decision) {
    if (decision === 'REJECTED' || !amount || amount === 0) return '₹0';
    const amountInCr = amount / 10000000;
    if (amountInCr >= 1) return `₹${amountInCr.toFixed(2)} Cr`;
    return `₹${(amountInCr * 100).toFixed(0)} L`;
}

// ═══ THREE-TIER DECISION BANNER (#7) ══════════════════
function renderDecisionBanner(dec) {
    const banner = document.getElementById('decision-banner');
    let decision = dec.decision;
    let cls = 'decision-reject';
    let label = 'REJECTED';
    let icon = '&#10060;';

    if (decision === 'APPROVED') {
        cls = 'decision-approve';
        label = 'APPROVED';
        icon = '&#9989;';
    } else if (decision === 'CONDITIONAL') {
        cls = 'decision-conditional';
        label = 'CONDITIONAL APPROVAL';
        icon = '&#9888;';
    }

    const riskScore = dec.risk_score ? dec.risk_score.toFixed(1) : '--';
    const confidence = dec.confidence ? (dec.confidence * 100).toFixed(0) : '--';
    const rate = dec.recommended_interest_rate ? dec.recommended_interest_rate.toFixed(2) + '%' : '--';

    // Loan display with requested context (#1)
    const requested = dec.requested_loan_amount ? formatAmount(dec.requested_loan_amount) : null;
    let loanLabel = formatLoanAmount(dec.recommended_loan_amount, decision);

    if (decision === 'APPROVED' || decision === 'CONDITIONAL') {
        loanLabel = `Sanctioned ${loanLabel}`;
        if (requested && dec.requested_loan_amount > 0) {
            loanLabel += `<br><small style="font-weight:400;font-size:0.7rem;color:var(--text-secondary)">(of ${requested} requested)</small>`;
        }
    }

    banner.className = `decision-banner ${cls}`;
    banner.innerHTML = `
        <div class="decision-main">
            <span class="decision-icon">${icon}</span>
            <span class="decision-label">${label}</span>
            <span class="decision-confidence">Confidence: ${confidence}%</span>
        </div>
        <div class="decision-details">
            <div class="decision-metric"><span>Risk Score</span><strong>${riskScore}/100</strong></div>
            <div class="decision-metric"><span>Loan Amount</span><strong>${loanLabel}</strong></div>
            <div class="decision-metric"><span>Interest Rate</span><strong>${rate}</strong></div>
        </div>
    `;
    banner.classList.remove('hidden');
}

// ═══ FIVE Cs RADAR CHART (#4) ════════════════════════
function renderFiveCsChart(fiveCs) {
    const ctx = document.getElementById('fivecs-chart');
    if (!ctx) return;

    if (fiveCsChart) fiveCsChart.destroy();

    fiveCsChart = new Chart(ctx, {
        type: 'radar',
        data: {
            labels: ['Character', 'Capacity', 'Capital', 'Collateral', 'Conditions'],
            datasets: [{
                label: 'Five Cs Score',
                data: [fiveCs.character, fiveCs.capacity, fiveCs.capital,
                fiveCs.collateral, fiveCs.conditions],
                backgroundColor: 'rgba(138, 43, 226, 0.2)',
                borderColor: 'rgba(138, 43, 226, 0.8)',
                pointBackgroundColor: 'rgba(138, 43, 226, 1)',
                pointBorderColor: '#fff',
                pointRadius: 5,
                borderWidth: 2,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                r: {
                    beginAtZero: true,
                    max: 100,
                    ticks: { stepSize: 20, color: '#999', backdropColor: 'transparent' },
                    grid: { color: 'rgba(255,255,255,0.1)' },
                    pointLabels: { color: '#ddd', font: { size: 12, weight: '600' } },
                    angleLines: { color: 'rgba(255,255,255,0.1)' },
                }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });
}

// ═══ SHAP WATERFALL CHART (#6) ════════════════════════
function renderShapChart(shapData) {
    const ctx = document.getElementById('shap-chart');
    if (!ctx) return;
    if (shapChart) shapChart.destroy();

    if (!shapData || typeof shapData !== 'object' || Array.isArray(shapData)) {
        document.getElementById('shap-card').querySelector('h3').textContent = 'SHAP Contributions (Not Available)';
        return;
    }

    // Sort by absolute value, take top 12, filter out bad/NaN values
    const entries = Object.entries(shapData)
        .filter(([k, v]) => typeof v === 'number' && !isNaN(v))
        .map(([k, v]) => ({ label: formatLabel(k), value: v }))
        .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
        .slice(0, 12);

    if (entries.length === 0) {
        document.getElementById('shap-card').querySelector('h3').textContent =
            'SHAP Feature Contributions (Run analysis first)';
        return;
    }

    const colors = entries.map(e => e.value >= 0 ? 'rgba(239, 68, 68, 0.8)' : 'rgba(34, 197, 94, 0.8)');
    const borderColors = entries.map(e => e.value >= 0 ? 'rgba(239, 68, 68, 1)' : 'rgba(34, 197, 94, 1)');

    shapChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: entries.map(e => e.label),
            datasets: [{
                label: 'SHAP Value',
                data: entries.map(e => e.value),
                backgroundColor: colors,
                borderColor: borderColors,
                borderWidth: 1,
                borderRadius: 4,
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.05)', drawZero: true, zeroLineColor: 'rgba(255,255,255,0.2)' },
                    ticks: { color: '#999' },
                    title: { display: true, text: '← Reduces Risk    |    Increases Risk →', color: '#999' },
                    suggestedMin: -Math.max(...entries.map(e => Math.abs(e.value))) * 1.1,
                    suggestedMax: Math.max(...entries.map(e => Math.abs(e.value))) * 1.1
                },
                y: {
                    grid: { display: false },
                    ticks: { color: '#ddd', font: { size: 11 } },
                }
            },
            plugins: {
                legend: { display: false },
                title: { display: true, text: 'Impact on Risk Score', color: '#999' },
                tooltip: {
                    callbacks: {
                        label: (ctx) => {
                            const v = ctx.raw;
                            return `${v >= 0 ? 'Increases' : 'Decreases'} risk by ${Math.abs(v).toFixed(3)}`;
                        }
                    }
                }
            }
        }
    });
}

// ═══ RENDER FLAGS ══════════════════════════════════════
function renderFlags(flags) {
    const container = document.getElementById('flags-container');
    if (!flags || flags.length === 0) {
        container.innerHTML = '<p class="empty-state">No flags detected yet.</p>';
        return;
    }

    const grouped = { red: [], green: [], blue: [] };
    flags.forEach(f => {
        if (!f) return;
        let c = (f.color || 'blue').toLowerCase();
        // Defensive check against backend Pydantic enum leaks (e.g. 'flagcolor.green')
        if (c.includes('red')) c = 'red';
        else if (c.includes('green')) c = 'green';
        else c = 'blue';
        grouped[c].push(f);
    });

    const allFlags = [...grouped.red, ...grouped.green, ...grouped.blue];
    if (allFlags.length === 0) {
        container.innerHTML = '<p class="empty-state">No flags detected yet.</p>';
        return;
    }

    let html = '<div class="flags-summary">';
    html += `<span class="flag-count flag-red">${grouped.red.length} Red</span>`;
    html += `<span class="flag-count flag-green">${grouped.green.length} Green</span>`;
    html += `<span class="flag-count flag-blue">${grouped.blue.length} Blue</span>`;
    html += '</div><div class="flags-list">';

    [...grouped.red, ...grouped.blue, ...grouped.green].forEach(f => {
        const icon = f.color === 'red' ? '&#128308;' : f.color === 'green' ? '&#128994;' : '&#128309;';
        html += `
            <div class="flag-item flag-${f.color}">
                <span class="flag-icon">${icon}</span>
                <div class="flag-content">
                    <strong>${f.title || f.category}</strong>
                    <span class="flag-desc">${f.description || ''}</span>
                    <span class="flag-meta">${f.category || ''} | ${f.source || ''}</span>
                </div>
            </div>
        `;
    });
    html += '</div>';
    container.innerHTML = html;
}

// ═══ RENDER REASONS ════════════════════════════════════
function renderReasons(reasons) {
    const container = document.getElementById('reasons-container');
    if (!reasons || reasons.length === 0) {
        container.innerHTML = '<p class="empty-state">Run analysis to see decision rationale.</p>';
        return;
    }
    container.innerHTML = '<ul class="reasons-list">' +
        reasons.map(r => `<li>${r}</li>`).join('') + '</ul>';
}

// ═══ GSTR DISCREPANCY ALERT (#8) ═════════════════════
function renderGSTRAlert(gst) {
    const card = document.getElementById('gstr-alert-card');
    card.classList.remove('hidden');
    const severity = gst.mismatch_pct > 20 ? 'critical' : 'warning';
    document.getElementById('gstr-alert-content').innerHTML = `
        <div class="alert-box alert-${severity}">
            <div class="alert-header">
                <strong>${severity === 'critical' ? '&#128308; CRITICAL' : '&#9888; WARNING'}: GSTR-3B vs GSTR-2A Discrepancy</strong>
            </div>
            <div class="alert-body">
                <div class="alert-metric">
                    <span>GSTR-3B Turnover</span>
                    <strong>${formatAmount(gst.gstr_3b_turnover)}</strong>
                </div>
                <div class="alert-metric">
                    <span>GSTR-2A Turnover</span>
                    <strong>${formatAmount(gst.gstr_2a_turnover)}</strong>
                </div>
                <div class="alert-metric">
                    <span>Mismatch</span>
                    <strong class="score-red">${gst.mismatch_pct.toFixed(1)}%</strong>
                </div>
            </div>
            <p class="alert-note">A variance exceeding 10% between GSTR-3B and GSTR-2A may indicate revenue inflation or circular trading. This has been flagged as a Red Risk.</p>
        </div>
    `;
}

// ═══ RESEARCH IN DASHBOARD (#9) ═══════════════════════
function renderResearchInDashboard(findings) {
    if (!findings || findings.length === 0) return;
    const card = document.getElementById('reasons-card');
    let html = card.innerHTML;
    html += '<h4 style="margin-top:1rem;">Research Findings</h4><div class="research-list">';
    findings.forEach(f => {
        const sentimentClass = f.sentiment === 'positive' ? 'sentiment-positive' :
            f.sentiment === 'negative' ? 'sentiment-negative' : 'sentiment-neutral';
        const url = f.url || f.link || '#';
        html += `
            <div class="research-item ${sentimentClass}">
                <div class="research-source">${f.source || 'Web'}</div>
                <div class="research-title">${f.title || ''}</div>
                <div class="research-snippet">${f.snippet || ''}</div>
                ${url !== '#' ? `<a href="${url}" target="_blank" class="research-link">View Source &#8599;</a>` : ''}
            </div>
        `;
    });
    html += '</div>';
    card.innerHTML = html;
}

// ═══ FILE DROP SETUP ═══════════════════════════════════
function setupFileDrop() {
    ['file-drop-zone', 'csv-drop-zone'].forEach(id => {
        const zone = document.getElementById(id);
        if (!zone) return;
        const input = zone.querySelector('input[type=file]');

        zone.addEventListener('click', () => input.click());
        zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
        zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
        zone.addEventListener('drop', e => {
            e.preventDefault();
            zone.classList.remove('dragover');
            input.files = e.dataTransfer.files;
            zone.querySelector('.drop-icon').textContent = '✓';
            zone.childNodes.forEach(n => {
                if (n.nodeType === 3) n.textContent = ` ${input.files[0].name}`;
            });
        });

        input.addEventListener('change', () => {
            if (input.files.length) {
                zone.querySelector('.drop-icon').textContent = '✓';
            }
        });
    });
}

// ═══ DOCUMENT UPLOAD ═══════════════════════════════════
async function uploadDocument() {
    const entityId = document.getElementById('upload-entity-id').value.trim();
    const companyName = document.getElementById('upload-company-name').value.trim();
    const docType = document.getElementById('upload-doc-type').value;
    const loanAmount = document.getElementById('upload-loan-amount').value || 0;
    const file = document.getElementById('upload-file').files[0];

    if (!entityId) { showToast('Entity ID is required', 'warning'); return; }
    if (!file) { showToast('Please select a PDF file', 'warning'); return; }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('entity_id', entityId);
    formData.append('company_name', companyName);
    formData.append('doc_type', docType);
    formData.append('requested_loan_amount', loanAmount);

    showLoading('Parsing document...');
    try {
        const res = await fetch('/api/upload', { method: 'POST', body: formData });
        const data = await res.json();
        hideLoading();
        if (res.ok && data.status === 'success') {
            showToast(`Document parsed: ${data.flags?.length || 0} flags detected`, 'success');
            renderUploadResult(data);
            loadEntities();
        } else {
            showToast('Upload failed: ' + (data.detail || data.message || 'Unknown'), 'error');
        }
    } catch (e) {
        hideLoading();
        showToast('Upload error: ' + e.message, 'error');
    }
}

function renderUploadResult(data) {
    const container = document.getElementById('upload-result');
    container.innerHTML = `
        <div class="result-card success">
            <h4>&#9989; Document Parsed Successfully</h4>
            <p>Entity: <strong>${data.entity_id}</strong> | Type: <strong>${data.doc_type}</strong></p>
            <p>File: ${data.filename}</p>
            ${data.flags?.length ? `<p>Flags detected: ${data.flags.length}</p>` : ''}
        </div>
    `;
}

// ═══ MANUAL ENTRY (#10 Auto-populate, #12 Live Ratios) ═
async function autoPopulateEntity(entityId) {
    const hint = document.getElementById('manual-entity-hint');
    if (!entityId || entityId.length < 3) { hint.textContent = ''; return; }

    try {
        const res = await fetch(`/api/company/${entityId}`);
        if (!res.ok) { hint.textContent = ''; return; }
        const data = await res.json();
        if (data.financials && data.financials.length > 0) {
            const fin = data.financials[0];
            hint.textContent = `Found: ${fin.company_name || entityId} — auto-populating...`;
            hint.classList.add('hint-found');

            // Auto-fill fields
            const fieldMap = {
                'manual-company-name': 'company_name',
                'manual-revenue': 'revenue',
                'manual-ebitda': 'ebitda',
                'manual-net-profit': 'net_profit',
                'manual-total-debt': 'total_debt',
                'manual-total-assets': 'total_assets',
                'manual-net-worth': 'net_worth',
                'manual-current-assets': 'current_assets',
                'manual-current-liabilities': 'current_liabilities',
                'manual-collateral-value': 'collateral_value',
                'manual-interest-expense': 'interest_expense',
                'manual-operating-margin': 'operating_margin',
                'manual-revenue-growth': 'revenue_growth_yoy',
                'manual-requested-loan': 'requested_loan_amount',
            };
            Object.entries(fieldMap).forEach(([elId, field]) => {
                const el = document.getElementById(elId);
                if (el && fin[field] != null) el.value = fin[field];
            });

            // GST
            if (data.gst_analysis?.[0]) {
                const gst = data.gst_analysis[0];
                document.getElementById('manual-gstr3b').value = gst.gstr_3b_turnover || '';
                document.getElementById('manual-gstr2a').value = gst.gstr_2a_turnover || '';
                checkGSTRDiscrepancy();
            }

            // CIBIL with color indicator (#9)
            if (data.cibil_data) {
                const c = data.cibil_data;
                if (c.cibil_score) {
                    document.getElementById('manual-cibil-score').value = c.cibil_score;
                    updateCibilIndicator(c.cibil_score);
                }
                if (c.overdue_accounts != null) document.getElementById('manual-overdue').value = c.overdue_accounts;
                if (c.suit_filed_accounts != null) document.getElementById('manual-suit-filed').value = c.suit_filed_accounts;
                if (c.dpd_90_plus != null) document.getElementById('manual-dpd90').value = c.dpd_90_plus;
                if (c.credit_utilization_pct != null) document.getElementById('manual-credit-util').value = c.credit_utilization_pct;
            }

            computeLiveRatios();
        } else {
            hint.textContent = '';
            hint.classList.remove('hint-found');
        }
    } catch {
        hint.textContent = '';
    }
}

// CIBIL score color indicator (#9)
function updateCibilIndicator(score) {
    score = parseInt(score) || 0;
    let indicator = document.getElementById('cibil-color-indicator');
    if (!indicator) {
        const cibilInput = document.getElementById('manual-cibil-score');
        if (!cibilInput) return;
        indicator = document.createElement('div');
        indicator.id = 'cibil-color-indicator';
        indicator.className = 'cibil-indicator';
        cibilInput.parentNode.appendChild(indicator);
    }
    indicator.classList.remove('hidden');
    if (score >= 750) {
        indicator.className = 'cibil-indicator cibil-green';
        indicator.textContent = `${score} — Excellent`;
    } else if (score >= 650) {
        indicator.className = 'cibil-indicator cibil-amber';
        indicator.textContent = `${score} — Fair`;
    } else if (score > 0) {
        indicator.className = 'cibil-indicator cibil-red';
        indicator.textContent = `${score} — Poor`;
    } else {
        indicator.classList.add('hidden');
    }
}

function onCibilScoreChange() {
    const val = document.getElementById('manual-cibil-score')?.value;
    if (val) updateCibilIndicator(val);
}

function computeLiveRatios() {
    const debt = parseFloat(document.getElementById('manual-total-debt')?.value) || 0;
    const equity = parseFloat(document.getElementById('manual-net-worth')?.value) || 0;
    const ca = parseFloat(document.getElementById('manual-current-assets')?.value) || 0;
    const cl = parseFloat(document.getElementById('manual-current-liabilities')?.value) || 0;
    const ebitda = parseFloat(document.getElementById('manual-ebitda')?.value) || 0;
    const interest = parseFloat(document.getElementById('manual-interest-expense')?.value) || 0;

    const container = document.getElementById('live-ratios');
    if (debt || equity || ca || cl || ebitda) {
        container.classList.remove('hidden');
    }

    // D/E Ratio
    const de = equity > 0 ? (debt / equity).toFixed(2) : '--';
    setRatioChip('ratio-de', de, de !== '--' ? (de > 3 ? 'red' : de > 1.5 ? 'amber' : 'green') : '');

    // Current Ratio
    const cr = cl > 0 ? (ca / cl).toFixed(2) : '--';
    setRatioChip('ratio-cr', cr, cr !== '--' ? (cr < 1 ? 'red' : cr < 1.5 ? 'amber' : 'green') : '');

    // DSCR
    const dscr = interest > 0 ? (ebitda / interest).toFixed(2) : '--';
    setRatioChip('ratio-dscr', dscr, dscr !== '--' ? (dscr < 1 ? 'red' : dscr < 2 ? 'amber' : 'green') : '');

    // Interest Coverage
    const icr = interest > 0 ? (ebitda / interest).toFixed(2) : '--';
    setRatioChip('ratio-icr', icr, icr !== '--' ? (icr < 1.5 ? 'red' : icr < 3 ? 'amber' : 'green') : '');
}

function setRatioChip(id, value, color) {
    const chip = document.getElementById(id);
    if (!chip) return;
    chip.querySelector('.ratio-value').textContent = value + (value !== '--' ? 'x' : '');
    chip.className = `ratio-chip ${color ? 'ratio-' + color : ''}`;
}

// ═══ GSTR DISCREPANCY CHECK (#8) ═════════════════════
function checkGSTRDiscrepancy() {
    const gstr3b = parseFloat(document.getElementById('manual-gstr3b')?.value) || 0;
    const gstr2a = parseFloat(document.getElementById('manual-gstr2a')?.value) || 0;
    const alert = document.getElementById('gstr-inline-alert');

    if (!gstr3b || !gstr2a) { alert.classList.add('hidden'); return; }

    const mismatch = Math.abs(gstr3b - gstr2a) / gstr3b * 100;

    if (mismatch > 10) {
        alert.classList.remove('hidden');
        const severity = mismatch > 20 ? 'critical' : 'warning';
        alert.className = `alert-box alert-${severity}`;
        alert.innerHTML = `
            <strong>${severity === 'critical' ? '&#128308; CRITICAL' : '&#9888; WARNING'}:</strong>
            GSTR-3B vs GSTR-2A variance is <strong>${mismatch.toFixed(1)}%</strong>
            ${mismatch > 20 ? ' — Possible circular trading or revenue inflation detected!' :
                ' — Exceeds 10% threshold, flagged for review.'}
        `;
    } else {
        alert.classList.add('hidden');
    }
}

// ═══ SUBMIT MANUAL ENTRY ═══════════════════════════════
async function submitManualEntry() {
    const data = {
        entity_id: document.getElementById('manual-entity-id').value.trim(),
        company_name: document.getElementById('manual-company-name').value.trim(),
        revenue: parseFloat(document.getElementById('manual-revenue').value) || 0,
        ebitda: parseFloat(document.getElementById('manual-ebitda').value) || 0,
        net_profit: parseFloat(document.getElementById('manual-net-profit').value) || 0,
        total_debt: parseFloat(document.getElementById('manual-total-debt').value) || 0,
        total_assets: parseFloat(document.getElementById('manual-total-assets').value) || 0,
        net_worth: parseFloat(document.getElementById('manual-net-worth').value) || 0,
        current_assets: parseFloat(document.getElementById('manual-current-assets').value) || 0,
        current_liabilities: parseFloat(document.getElementById('manual-current-liabilities').value) || 0,
        collateral_value: parseFloat(document.getElementById('manual-collateral-value').value) || 0,
        interest_expense: parseFloat(document.getElementById('manual-interest-expense').value) || 0,
        operating_margin: parseFloat(document.getElementById('manual-operating-margin').value) || 0,
        revenue_growth_yoy: parseFloat(document.getElementById('manual-revenue-growth').value) || 0,
        requested_loan_amount: parseFloat(document.getElementById('manual-requested-loan').value) || 0,
        gstr_3b_turnover: parseFloat(document.getElementById('manual-gstr3b').value) || 0,
        gstr_2a_turnover: parseFloat(document.getElementById('manual-gstr2a').value) || 0,
        cibil_score: parseInt(document.getElementById('manual-cibil-score').value) || 0,
        overdue_accounts: parseInt(document.getElementById('manual-overdue').value) || 0,
        suit_filed_accounts: parseInt(document.getElementById('manual-suit-filed').value) || 0,
        dpd_90_plus: parseInt(document.getElementById('manual-dpd90').value) || 0,
        credit_utilization_pct: parseFloat(document.getElementById('manual-credit-util').value) || 0,
    };

    if (!data.entity_id) { showToast('Entity ID is required', 'warning'); return; }

    showLoading('Saving financial data...');
    try {
        const res = await fetch('/api/manual-entry', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await res.json();
        hideLoading();
        if (res.ok && result.status === 'success') {
            showToast(`Data saved for ${result.company_name || data.entity_id}`, 'success');
            renderManualResult(result);
            loadEntities();
            // Form reset after successful save (#2)
            resetManualEntryForm();
        } else {
            showToast('Save failed: ' + (result.detail || result.message || 'Unknown'), 'error');
        }
    } catch (e) {
        hideLoading();
        showToast('Error: ' + e.message, 'error');
    }
}

function renderManualResult(result) {
    const flags = result.analysis?.flags || [];
    document.getElementById('manual-result').innerHTML = `
        <div class="result-card success">
            <h4>&#9989; Data Saved Successfully</h4>
            <p>Entity: <strong>${result.entity_id}</strong> | Company: <strong>${result.company_name}</strong></p>
            ${flags.length ? `<p>Flags generated: ${flags.length}</p>` : ''}
        </div>
    `;
}

// Form reset after submission (#2)
function resetManualEntryForm() {
    const fields = ['manual-entity-id', 'manual-company-name', 'manual-revenue', 'manual-ebitda',
        'manual-net-profit', 'manual-total-debt', 'manual-total-assets', 'manual-net-worth',
        'manual-current-assets', 'manual-current-liabilities', 'manual-collateral-value',
        'manual-interest-expense', 'manual-operating-margin', 'manual-revenue-growth',
        'manual-requested-loan', 'manual-gstr3b', 'manual-gstr2a', 'manual-cibil-score',
        'manual-overdue', 'manual-suit-filed', 'manual-dpd90', 'manual-credit-util'];
    fields.forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
    const hint = document.getElementById('manual-entity-hint');
    if (hint) { hint.textContent = ''; hint.classList.remove('hint-found'); }
    const ratios = document.getElementById('live-ratios');
    if (ratios) ratios.classList.add('hidden');
    const alert = document.getElementById('gstr-inline-alert');
    if (alert) alert.classList.add('hidden');
    const cibil = document.getElementById('cibil-color-indicator');
    if (cibil) cibil.classList.add('hidden');
}

// ═══ BATCH CSV UPLOAD (#15) ═══════════════════════════
async function uploadBatchCSV() {
    const file = document.getElementById('batch-file').files[0];
    if (!file) { showToast('Please select a CSV file', 'warning'); return; }

    const formData = new FormData();
    formData.append('file', file);

    showLoading('Processing batch CSV...');
    try {
        const res = await fetch('/api/batch-upload', { method: 'POST', body: formData });
        const data = await res.json();
        hideLoading();
        if (res.ok && data.status === 'success') {
            const errors = data.results.filter(r => r.status === 'error');
            const loaded = data.results.filter(r => r.status === 'loaded');
            showToast(`Loaded ${loaded.length} entities from CSV` +
                (errors.length ? ` (${errors.length} row errors)` : ''), errors.length ? 'warning' : 'success');
            let batchHtml = `
                <div class="result-card ${errors.length ? 'warning' : 'success'}">
                    <h4>&#9989; Batch Upload Complete</h4>
                    <p>${loaded.length} entities loaded` + (errors.length ? `, ${errors.length} errors` : '') + `</p>
                    <div class="batch-list">
                        ${loaded.map(r => `<div class="batch-item">${r.entity_id} &mdash; ${r.company_name}</div>`).join('')}
                    </div>`;
            if (errors.length) {
                batchHtml += `<h4 style="margin-top:1rem; color:#ef4444;">&#10060; Row Errors</h4>
                    <div class="batch-list">
                        ${errors.map(r => `<div class="batch-item batch-error">${r.entity_id}: ${r.error}</div>`).join('')}
                    </div>`;
            }
            batchHtml += '</div>';
            document.getElementById('batch-result').innerHTML = batchHtml;
            loadEntities();
        } else {
            showToast('Batch failed: ' + (data.detail || data.message || 'Unknown'), 'error');
        }
    } catch (e) {
        hideLoading();
        showToast('Batch error: ' + e.message, 'error');
    }
}

// CSV Template Download (#11)
function downloadCSVTemplate() {
    window.location.href = '/api/csv-template';
    showToast('CSV template downloading...', 'success');
}

// ═══ RESEARCH ══════════════════════════════════════════
async function runResearch() {
    const id = document.getElementById('research-entity-id').value.trim();
    const name = document.getElementById('research-company-name').value.trim();
    const rawPromoters = document.getElementById('research-promoters').value.trim();

    // Default sector/location extraction logic (can be expanded later if added to UI)
    const sector = localStorage.getItem(`sector_${id}`) || null;
    const location = localStorage.getItem(`location_${id}`) || null;

    if (!id) { showToast('Entity ID required for research', 'warning'); return; }

    const promoters = rawPromoters ? rawPromoters.split(',').map(s => s.trim()) : [];

    showLoading('Running web research using SerpAPI...');

    try {
        const res = await fetch(`/api/research/${id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ company_name: name || id, promoters, sector, location })
        });
        const data = await res.json();
        hideLoading();
        if (res.ok && data.status === 'success') {
            showToast(`Found ${data.findings_count} research findings`, 'success');
            renderResearchResults(data);
        } else {
            showToast('Research failed: ' + (data.detail || data.message || 'Unknown'), 'error');
        }
    } catch (e) {
        hideLoading();
        showToast('Research error: ' + e.message, 'error');
    }
}

function renderResearchResults(data) {
    const container = document.getElementById('research-results');
    let html = `<div class="card"><h3>Research Results (${data.findings_count} findings)</h3>`;

    (data.findings || []).forEach(f => {
        const sentimentClass = f.sentiment === 'positive' ? 'sentiment-positive' :
            f.sentiment === 'negative' ? 'sentiment-negative' : 'sentiment-neutral';
        const url = f.url || f.link || '#';
        html += `
            <div class="research-item ${sentimentClass}">
                <div class="research-source">${f.source || 'Web'}</div>
                <div class="research-title">${f.title || ''}</div>
                <div class="research-snippet">${f.snippet || ''}</div>
                ${url !== '#' ? `<a href="${url}" target="_blank" class="research-link">View Source &#8599;</a>` : ''}
            </div>
        `;
    });
    html += '</div>';
    container.innerHTML = html;
}

// ═══ OFFICER NOTES + HISTORY (#1 Fix) ════════════════
let detectTimer = null;

function attachNoteDetection() {
    const noteTextarea = document.getElementById('note-text');
    if (!noteTextarea) return;
    noteTextarea.removeEventListener('input', handleNoteInput);
    noteTextarea.addEventListener('input', handleNoteInput);
}

async function handleNoteInput() {
    clearTimeout(detectTimer);
    const text = this.value.trim();
    if (text.length < 15) {
        document.getElementById('note-preview-category').textContent = 'None';
        document.getElementById('note-preview-severity').textContent = 'None';
        document.getElementById('note-preview-container').classList.add('hidden');
        return;
    }
    detectTimer = setTimeout(async () => {
        try {
            const res = await fetch('/api/notes/preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ note: text })
            });
            if (res.ok) {
                const data = await res.json();
                document.getElementById('note-preview-container').classList.remove('hidden');
                document.getElementById('note-preview-category').textContent = data.category || 'None';
                document.getElementById('note-preview-severity').textContent = data.severity || 'None';
            }
        } catch (e) {
            console.warn("Preview failed", e);
        }
    }, 600);
}

async function addNote() {
    const entityId = document.getElementById('note-entity-id').value.trim();
    const officerName = document.getElementById('note-officer-name').value.trim();
    const noteText = document.getElementById('note-text').value.trim();
    const category = document.getElementById('note-category').value;

    if (!entityId || !noteText) {
        showToast('Entity ID and note text are required', 'warning'); return;
    }

    showLoading('Processing note...');
    try {
        const res = await fetch(`/api/notes/${entityId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ note: noteText, officer_name: officerName, category })
        });
        const data = await res.json();
        hideLoading();
        if (res.ok) {
            showToast(`Note saved — Severity: ${data.severity || 'low'}`, 'success');
            document.getElementById('note-text').value = '';
            // Auto-append note to History panel immediately (#1)
            if (data.saved_note) {
                appendNoteToHistory(data.saved_note);
            } else {
                loadNotesHistory(entityId);
            }
        } else {
            showToast('Note failed: ' + (data.detail || data.message || 'Unknown'), 'error');
        }
    } catch (e) {
        hideLoading();
        showToast('Note error: ' + e.message, 'error');
    }
}

function appendNoteToHistory(note) {
    const container = document.getElementById('notes-history');
    // Remove empty-state if present
    const empty = container.querySelector('.empty-state');
    if (empty) empty.remove();

    const div = document.createElement('div');
    div.className = `note-item note-${note.severity || 'low'}`;
    div.innerHTML = `
        <div class="note-header">
            <strong>${note.officer_name || 'Officer'}</strong>
            <span class="note-severity badge-${note.severity || 'low'}">${(note.severity || 'low').toUpperCase()}</span>
            <span class="note-date">${note.created_at ? new Date(note.created_at).toLocaleDateString() : 'Just now'}</span>
        </div>
        <p class="note-text">${note.note || ''}</p>
        <span class="note-category">${note.category || ''}</span>
    `;
    container.prepend(div);
}

async function loadNotesHistory(entityId) {
    if (!entityId || entityId.length < 3) return;
    try {
        const res = await fetch(`/api/notes/${entityId}`);
        const data = await res.json();
        const container = document.getElementById('notes-history');

        if (!data.notes || data.notes.length === 0) {
            container.innerHTML = '<p class="empty-state">No notes found for this entity.</p>';
            return;
        }

        container.innerHTML = data.notes.map((n, i) => `
            <div class="note-item ${n.severity === 'critical' ? 'note-critical' :
                n.severity === 'high' ? 'note-high' :
                    n.severity === 'medium' ? 'note-medium' : 'note-low'}">
                <div class="note-header">
                    <strong>${n.officer_name || 'Officer'}</strong>
                    <span class="note-severity badge-${n.severity || 'low'}">${(n.severity || 'low').toUpperCase()}</span>
                    <span class="note-date">${n.created_at ? new Date(n.created_at).toLocaleDateString() : ''}</span>
                </div>
                <p class="note-text">${n.note || ''}</p>
                <span class="note-category">${n.category || ''}</span>
            </div>
        `).join('');
    } catch { /* ignore */ }
}

// ═══ ANALYSIS ══════════════════════════════════════════
// Auto-clear old results when new Entity ID is typed (#3)
function onAnalysisEntityInput() {
    const container = document.getElementById('analysis-result');
    if (container) container.innerHTML = '';
}

async function runAnalysis(forceId = null) {
    const entityId = forceId || document.getElementById('analysis-entity-id').value.trim();
    if (!entityId) { showToast('Entity ID is required', 'warning'); return; }

    const TIMEOUT_MS = 25000; // 25 second timeout
    showLoading('Running XGBoost analysis with SHAP...');

    const controller = new AbortController();
    const timeoutId = setTimeout(() => { controller.abort(); }, TIMEOUT_MS);

    try {
        const res = await fetch(`/api/analyze/${entityId}`, {
            method: 'GET',
            signal: controller.signal
        });
        clearTimeout(timeoutId);

        const data = await res.json();
        hideLoading();
        if (res.ok && data.status === 'success') {
            showToast(`Analysis complete: ${data.decision}`, data.decision === 'APPROVED' ? 'success' :
                data.decision === 'CONDITIONAL' ? 'warning' : 'error');
            renderAnalysisResult(data);
            // BUG 1: Store analyzed entity and redirect to dashboard with fresh data
            currentEntityId = data.entity_id;
            localStorage.setItem('last_analyzed_entity', data.entity_id);
            setTimeout(() => {
                document.getElementById('entity-header-id').textContent = data.entity_id;
                document.getElementById('entity-header-name').textContent = data.company_name || data.entity_id;
                openTab('dashboard');
            }, 2000);
        } else {
            const errMsg = data.detail || data.message || 'Unknown error';
            showToast('Analysis failed: ' + errMsg, 'error');
            // Show error banner in analysis result area (#3)
            document.getElementById('analysis-result').innerHTML = `
                <div class="card result-reject">
                    <div class="analysis-header">
                        <span class="analysis-icon">&#10060;</span>
                        <h3>Analysis Failed</h3>
                    </div>
                    <p style="margin-top:0.75rem; color: var(--text-secondary);">${errMsg}</p>
                    <p style="margin-top:0.5rem; font-size:0.8rem; color: var(--text-muted);">Please check that financial data has been entered for this entity, or review server logs.</p>
                </div>
            `;
        }
    } catch (e) {
        clearTimeout(timeoutId);
        hideLoading();
        if (e.name === 'AbortError') {
            showToast('Analysis timed out after 25s. The model may take longer to load on first run. Please retry.', 'error');
        } else {
            showToast('Analysis error: ' + e.message, 'error');
        }
        document.getElementById('analysis-result').innerHTML = `
            <div class="card result-reject">
                <div class="analysis-header">
                    <span class="analysis-icon">&#10060;</span>
                    <h3>Connection Error</h3>
                </div>
                <p style="margin-top:0.75rem; color: var(--text-secondary);">${e.message}</p>
            </div>
        `;
    }
}

// ═══ COMPARE ENTITIES ══════════════════════════════════
async function runComparison() {
    const idA = document.getElementById('compare-entity-a').value.trim();
    const idB = document.getElementById('compare-entity-b').value.trim();

    if (!idA || !idB) { showToast('Please enter both Entity IDs', 'warning'); return; }

    showLoading('Fetching comparison data...');

    try {
        const [resA, resB] = await Promise.all([
            fetch(`/api/company/summary/${idA}`),
            fetch(`/api/company/summary/${idB}`)
        ]);

        if (!resA.ok || !resB.ok) throw new Error("Could not fetch data for both entities.");

        const dataA = await resA.json();
        const dataB = await resB.json();
        hideLoading();

        renderComparisonTable(dataA, dataB);
    } catch (e) {
        hideLoading();
        showToast('Comparison failed: ' + e.message, 'error');
    }
}

function formatDSCR(val) {
    if (val === null || val === undefined || val === '') return '--';
    const num = parseFloat(val);
    if (isNaN(num)) return '--';
    const color = num >= 1.25 ? '#4ade80' : num >= 1.0 ? '#facc15' : '#f87171';
    return `<span style="color:${color}">${num.toFixed(2)}x</span>`;
}

function renderComparisonTable(dataA, dataB) {
    const container = document.getElementById('compare-results');
    const finA = dataA.financials?.[0] || {};
    const finB = dataB.financials?.[0] || {};
    const cibilA = dataA.cibil_data || {};
    const cibilB = dataB.cibil_data || {};
    const decA = dataA.decision || {};
    const decB = dataB.decision || {};

    container.innerHTML = `
        <div class="compare-table-wrapper">
        <table class="data-table" style="width: 100%; border-collapse: collapse; margin-top: 1rem;">
            <thead>
                <tr style="background: rgba(255,255,255,0.05);">
                    <th style="padding: 1rem; text-align: left; border-bottom: 2px solid var(--border);">Metric</th>
                    <th style="padding: 1rem; text-align: left; border-bottom: 2px solid var(--border);">${finA.company_name || dataA.entity_id}</th>
                    <th style="padding: 1rem; text-align: left; border-bottom: 2px solid var(--border);">${finB.company_name || dataB.entity_id}</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td style="padding: 1rem; border-bottom: 1px solid var(--border);"><strong>Credit Decision</strong></td>
                    <td style="padding: 1rem; border-bottom: 1px solid var(--border);">
                        <span class="badge-${decA.decision === 'APPROVED' ? 'green' : decA.decision === 'CONDITIONAL' ? 'amber' : 'red'}">${decA.decision === 'CONDITIONAL' ? 'CONDITIONAL APPROVAL' : (decA.decision || 'N/A')}</span>
                    </td>
                    <td style="padding: 1rem; border-bottom: 1px solid var(--border);">
                        <span class="badge-${decB.decision === 'APPROVED' ? 'green' : decB.decision === 'CONDITIONAL' ? 'amber' : 'red'}">${decB.decision === 'CONDITIONAL' ? 'CONDITIONAL APPROVAL' : (decB.decision || 'N/A')}</span>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 1rem; border-bottom: 1px solid var(--border);"><strong>Risk Score</strong></td>
                    <td style="padding: 1rem; border-bottom: 1px solid var(--border);">${decA.risk_score || '--'}/100</td>
                    <td style="padding: 1rem; border-bottom: 1px solid var(--border);">${decB.risk_score || '--'}/100</td>
                </tr>
                <tr>
                    <td style="padding: 1rem; border-bottom: 1px solid var(--border);"><strong>Revenue</strong></td>
                    <td style="padding: 1rem; border-bottom: 1px solid var(--border);">${formatAmount(finA.revenue)}</td>
                    <td style="padding: 1rem; border-bottom: 1px solid var(--border);">${formatAmount(finB.revenue)}</td>
                </tr>
                <tr>
                    <td style="padding: 1rem; border-bottom: 1px solid var(--border);"><strong>EBITDA Margin</strong></td>
                    <td style="padding: 1rem; border-bottom: 1px solid var(--border);">${finA.operating_margin ? finA.operating_margin.toFixed(1) + '%' : '--'}</td>
                    <td style="padding: 1rem; border-bottom: 1px solid var(--border);">${finB.operating_margin ? finB.operating_margin.toFixed(1) + '%' : '--'}</td>
                </tr>
                <tr>
                    <td style="padding: 1rem; border-bottom: 1px solid var(--border);"><strong>Net Worth</strong></td>
                    <td style="padding: 1rem; border-bottom: 1px solid var(--border);">${formatAmount(finA.net_worth)}</td>
                    <td style="padding: 1rem; border-bottom: 1px solid var(--border);">${formatAmount(finB.net_worth)}</td>
                </tr>
                <tr>
                    <td style="padding: 1rem; border-bottom: 1px solid var(--border);"><strong>DSCR</strong></td>
                    <td style="padding: 1rem; border-bottom: 1px solid var(--border);">${formatDSCR(finA.dscr)}</td>
                    <td style="padding: 1rem; border-bottom: 1px solid var(--border);">${formatDSCR(finB.dscr)}</td>
                </tr>
                <tr>
                    <td style="padding: 1rem; border-bottom: 1px solid var(--border);"><strong>CIBIL Score</strong></td>
                    <td style="padding: 1rem; border-bottom: 1px solid var(--border);"><span class="score-${cibilA.cibil_score >= 750 ? 'green' : cibilA.cibil_score >= 600 ? 'amber' : 'red'}">${cibilA.cibil_score || '--'}</span></td>
                    <td style="padding: 1rem; border-bottom: 1px solid var(--border);"><span class="score-${cibilB.cibil_score >= 750 ? 'green' : cibilB.cibil_score >= 600 ? 'amber' : 'red'}">${cibilB.cibil_score || '--'}</span></td>
                </tr>
            </tbody>
        </table>
        </div>
    `;
    container.classList.remove('hidden');
}

function renderAnalysisResult(data) {
    const container = document.getElementById('analysis-result');

    let decisionClass = 'result-reject';
    let decisionIcon = '&#10060;';
    if (data.decision === 'APPROVED') { decisionClass = 'result-approve'; decisionIcon = '&#9989;'; }
    else if (data.decision === 'CONDITIONAL') { decisionClass = 'result-conditional'; decisionIcon = '&#9888;'; }

    let html = `
        <div class="card ${decisionClass}">
            <div class="analysis-header">
                <span class="analysis-icon">${decisionIcon}</span>
                <h3>${data.decision === 'CONDITIONAL' ? 'CONDITIONAL APPROVAL' : data.decision}</h3>
                <span class="analysis-company">${data.company_name || data.entity_id}</span>
            </div>
            <div class="analysis-metrics">
                <div class="metric"><span class="metric-label">Risk Score</span><span class="metric-value">${data.risk_score?.toFixed(1) || '--'}/100</span></div>
                <div class="metric"><span class="metric-label">Confidence</span><span class="metric-value">${data.confidence ? (data.confidence * 100).toFixed(0) + '%' : '--'}</span></div>
                <div class="metric"><span class="metric-label">Loan Amount</span><span class="metric-value">${formatAmount(data.recommended_loan_amount)}</span></div>
                <div class="metric"><span class="metric-label">Interest Rate</span><span class="metric-value">${data.recommended_interest_rate?.toFixed(2) || '--'}%</span></div>
            </div>
        </div>
    `;

    // Conditional Approval conditions (#4)
    if (data.decision === 'CONDITIONAL' && data.conditions && data.conditions.length > 0) {
        html += `<div class="card conditional-conditions">
            <h3>&#9888; Conditions for Approval</h3>
            <ul class="conditions-list">`;
        data.conditions.forEach(c => html += `<li>${c}</li>`);
        html += '</ul></div>';
    }

    // Five Cs in analysis result
    if (data.five_cs) {
        html += `<div class="card"><h3>Five Cs Assessment</h3><div class="five-cs-bars">`;
        Object.entries(data.five_cs).forEach(([key, val]) => {
            const color = val >= 70 ? '#22c55e' : val >= 40 ? '#f59e0b' : '#ef4444';
            html += `
                <div class="cs-bar">
                    <span class="cs-label">${key.charAt(0).toUpperCase() + key.slice(1)}</span>
                    <div class="cs-track"><div class="cs-fill" style="width:${val}%; background:${color}"></div></div>
                    <span class="cs-value">${val.toFixed(0)}</span>
                </div>
            `;
        });
        html += '</div></div>';
    }

    // SHAP in analysis result
    if (data.shap_explanations && Object.keys(data.shap_explanations).length > 0) {
        const entries = Object.entries(data.shap_explanations)
            .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
            .slice(0, 10);

        // SHAP legend (#6)
        html += `<div class="card"><h3>SHAP Feature Impact</h3>
            <div class="shap-legend">
                <span class="shap-legend-item"><span class="legend-dot legend-red"></span> Increases risk (pushes toward rejection)</span>
                <span class="shap-legend-item"><span class="legend-dot legend-green"></span> Reduces risk (pushes toward approval)</span>
                <span class="shap-legend-item">|&nbsp; Baseline (zero impact)</span>
            </div>
            <div class="shap-bars">`;
        entries.forEach(([key, val]) => {
            const isPositive = val >= 0;
            const absVal = Math.abs(val);
            const maxVal = Math.max(...entries.map(e => Math.abs(e[1])));
            const width = maxVal > 0 ? (absVal / maxVal * 100) : 0;
            html += `
                <div class="shap-row">
                    <span class="shap-label">${formatLabel(key)}</span>
                    <div class="shap-bar-track">
                        <div class="shap-baseline"></div>
                        <div class="shap-bar-fill ${isPositive ? 'shap-risk' : 'shap-safe'}"
                             style="width:${width}%"></div>
                    </div>
                    <span class="shap-val ${isPositive ? 'score-red' : 'score-green'}">${val.toFixed(3)}</span>
                </div>
            `;
        });
        html += '</div></div>';
    }

    // Flags
    if (data.all_flags && data.all_flags.length > 0) {
        html += '<div class="card"><h3>All Risk Flags</h3>';
        const grouped = { red: [], green: [], blue: [] };
        data.all_flags.forEach(f => {
            const c = (f.color || 'blue').toLowerCase();
            if (grouped[c]) grouped[c].push(f);
        });
        html += `<div class="flags-summary">
            <span class="flag-count flag-red">${grouped.red.length} Red</span>
            <span class="flag-count flag-green">${grouped.green.length} Green</span>
            <span class="flag-count flag-blue">${grouped.blue.length} Blue</span>
        </div><div class="flags-list">`;
        [...grouped.red, ...grouped.blue, ...grouped.green].forEach(f => {
            const icon = f.color === 'red' ? '&#128308;' : f.color === 'green' ? '&#128994;' : '&#128309;';
            html += `<div class="flag-item flag-${f.color}">
                <span class="flag-icon">${icon}</span>
                <div class="flag-content"><strong>${f.title || f.category}</strong>
                <span class="flag-desc">${f.description || ''}</span></div>
            </div>`;
        });
        html += '</div></div>';
    }

    // Reasons
    if (data.decision_reasons && data.decision_reasons.length > 0) {
        html += '<div class="card"><h3>Decision Rationale</h3><ul class="reasons-list">';
        data.decision_reasons.forEach(r => html += `<li>${r}</li>`);
        html += '</ul></div>';
    }

    // CAM button
    html += `
        <div class="card">
            <div class="form-grid">
                <button class="btn btn-primary btn-full" onclick="currentEntityId='${data.entity_id}'; downloadCAM()">
                    Download Credit Appraisal Memo (.docx)
                </button>
                <button class="btn btn-outline btn-full" onclick="currentEntityId='${data.entity_id}'; downloadCAMPDF()">
                    Download Credit Appraisal Memo (.pdf)
                </button>
            </div>
        </div>
    `;

    container.innerHTML = html;
}

// ═══ CAM DOWNLOAD ══════════════════════════════════════
async function downloadCAM() {
    const id = currentEntityId || document.getElementById('analysis-entity-id')?.value?.trim();
    if (!id) { showToast('No entity selected', 'warning'); return; }

    showLoading('Generating CAM report...');
    try {
        const res = await fetch(`/api/cam/${id}`);
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
            hideLoading();
            showToast('CAM failed: ' + (err.detail || 'Unknown'), 'error');
            return;
        }
        const blob = await res.blob();
        hideLoading();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `CAM_${id}.docx`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch (e) {
        hideLoading();
        showToast('CAM error: ' + e.message, 'error');
    }
}

async function downloadCAMPDF() {
    const id = currentEntityId || document.getElementById('analysis-entity-id')?.value?.trim();
    if (!id) { showToast('No entity selected', 'warning'); return; }

    showLoading('Generating CAM PDF report...');
    try {
        const res = await fetch(`/api/cam/pdf/${id}`);
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
            hideLoading();
            showToast('CAM PDF failed: ' + (err.detail || 'Unknown'), 'error');
            return;
        }
        const blob = await res.blob();
        hideLoading();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `CAM_${id}.pdf`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch (e) {
        hideLoading();
        showToast('CAM PDF error: ' + e.message, 'error');
    }
}

// ═══ NOTES HISTORY (#12) ══════════════════════════════════════════════
function switchIngestTab(tab) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.getElementById(`ingest-${tab}`).classList.add('active');
    event.target.classList.add('active');
}

// ═══ UTILITIES ═════════════════════════════════════════
function formatAmount(num) {
    if (!num && num !== 0) return '--';
    num = parseFloat(num);
    if (Math.abs(num) >= 10000000) return '\u20B9' + (num / 10000000).toFixed(2) + ' Cr';
    if (Math.abs(num) >= 100000) return '\u20B9' + (num / 100000).toFixed(2) + ' L';
    return '\u20B9' + num.toLocaleString('en-IN');
}

function formatLabel(key) {
    return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    const icon = type === 'success' ? '&#9989;' : type === 'error' ? '&#10060;' :
        type === 'warning' ? '&#9888;' : '&#8505;';
    toast.innerHTML = `<span>${icon}</span> ${message}`;
    container.appendChild(toast);
    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ═══ UTILITIES ═════════════════════════════════════════
function showLoading(msg) {
    document.getElementById('loading-overlay').classList.remove('hidden');
    document.getElementById('loading-text').textContent = msg; // Changed from loading-msg to loading-text

    // UX Polish: Simulated progress bar
    const bar = document.getElementById('loading-progress-bar');
    if (bar) {
        bar.style.width = '0%';
        let progress = 0;
        clearInterval(loadingInterval);
        loadingInterval = setInterval(() => {
            progress += Math.random() * 15;
            if (progress > 90) progress = 90;
            bar.style.width = `${progress}%`;
        }, 500);
    }
}

function hideLoading() {
    document.getElementById('loading-overlay').classList.add('hidden');
    clearInterval(loadingInterval);
    const bar = document.getElementById('loading-progress-bar');
    if (bar) bar.style.width = '100%';
}
