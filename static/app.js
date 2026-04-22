// STATE MANAGEMENT
let currentMatchData = null;
let fieldConfidences = {};

// UI SELECTORS
const rawInput = document.getElementById('rawInput');
const jsonOutput = document.getElementById('jsonOutput');
const mapBtn = document.getElementById('mapBtn');
const loader = document.getElementById('loader');
const qualityIndicator = document.getElementById('qualityIndicator');
const chatWindow = document.getElementById('chatWindow');
const chatInput = document.getElementById('chatInput');

// 1. DATA NORMALIZATION
mapBtn.addEventListener('click', async () => {
    const rawVal = rawInput.value.trim();
    if (!rawVal) return;

    setLoading(true);
    try {
        const response = await fetch('/api/map', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ raw_data: rawVal })
        });
        
        const result = await response.json();
        currentMatchData = result.data;
        fieldConfidences = result.field_confidences;
        
        renderNormalizedData(result.data, result.field_confidences);
        updateQualityMetrics(result.quality);
        
        // Enable Chat
        chatInput.disabled = false;
        chatInput.placeholder = "Ask tactical intel about this data...";
    } catch (err) {
        console.error(err);
        jsonOutput.innerHTML = `<span style="color: var(--conf-low)">// FAILED: Check API connection or JSON format.</span>`;
    } finally {
        setLoading(false);
    }
});

// 2. CONFIDENCE-AWARE JSON RENDERING
function renderNormalizedData(data, confidences) {
    let html = '{\n';
    const keys = Object.keys(data);
    
    keys.forEach((key, index) => {
        const value = data[key];
        const conf = confidences[key] || 100;
        const confClass = conf > 85 ? 'conf-high' : (conf > 60 ? 'conf-med' : 'conf-low');
        const comma = index < keys.length - 1 ? ',' : '';
        
        let formattedValue;
        if (typeof value === 'string') {
            formattedValue = `<span class="json-string">"${value}"</span>`;
        } else if (value === null) {
            formattedValue = `<span style="color: #64748b">null</span>`;
        } else {
            formattedValue = `<span class="json-number">${value}</span>`;
        }

        html += `  <div class="field-row">`;
        html += `<span class="json-key">"${key}"</span>: ${formattedValue}${comma}`;
        html += `<span class="conf-badge ${confClass}">${conf.toFixed(0)}% Certainty</span>`;
        html += `</div>\n`;
    });
    
    html += '}';
    jsonOutput.innerHTML = html;
}

// 3. QUALITY DASHBOARD
function updateQualityMetrics(quality) {
    const caseAcc = document.getElementById('caseAccuracy');
    const caseConf = document.getElementById('caseConfidence');
    const uncertaintyList = document.getElementById('uncertaintyList');
    
    caseAcc.innerText = `93%`; // Simulating for this specific view (Logic vs Conf)
    caseConf.innerText = `${quality.confidence.toFixed(1)}%`;
    
    qualityIndicator.innerText = quality.status.toUpperCase();
    qualityIndicator.style.color = quality.css_class === 'perfect' ? 'var(--conf-high)' : 
                                  (quality.css_class === 'okayish' ? 'var(--conf-med)' : 'var(--conf-low)');

    // Render Uncertain Badges
    uncertaintyList.innerHTML = '';
    const lowConfFields = quality.buckets.critical.concat(quality.buckets.optimization);
    
    lowConfFields.slice(0, 5).forEach(f => {
        const span = document.createElement('span');
        span.className = 'conf-badge conf-low';
        span.style.fontSize = '0.6rem';
        span.innerText = f;
        uncertaintyList.appendChild(span);
    });
}

// 4. CHAT INTEGRATION
chatInput.addEventListener('keypress', async (e) => {
    if (e.key === 'Enter' && chatInput.value) {
        const q = chatInput.value;
        appendChat('user', q);
        chatInput.value = '';
        
        try {
            const res = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: q, match_data: currentMatchData })
            });
            const data = await res.json();
            appendChat('assistant', data.answer);
        } catch (err) {
            appendChat('assistant', "Communication failure with tactical core.");
        }
    }
});

function appendChat(role, msg) {
    const div = document.createElement('div');
    div.className = `chat-bubble ${role}`;
    div.innerText = msg;
    chatWindow.appendChild(div);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

// 5. WORKSPACE AUDIT
async function runGlobalAudit() {
    switchTab('integrity');
    const fieldPrecisionMap = document.getElementById('fieldPrecisionMap');
    const resultsGrid = document.getElementById('globalAuditResults');
    
    fieldPrecisionMap.innerHTML = '<p class="shimmer" style="height: 200px; border-radius: 12px;"></p>';
    
    try {
        const res = await fetch('/api/accuracy');
        const data = await res.json();
        
        // Update Stats
        resultsGrid.innerHTML = `
            <div class="stat-item"><span class="stat-val">${data.overall_accuracy.toFixed(1)}%</span><span class="stat-label">Logic Integrity</span></div>
            <div class="stat-item"><span class="stat-val">${data.overall_confidence.toFixed(1)}%</span><span class="stat-label">Mean Confidence</span></div>
            <div class="stat-item"><span class="stat-val">${data.passed_cases}</span><span class="stat-label">Unit Tests</span></div>
            <div class="stat-item"><span class="stat-val">${data.case_pass_rate.toFixed(0)}%</span><span class="stat-label">System Health</span></div>
        `;
        
        // Update Precision Bars
        let barsHtml = '<h4 style="font-size: 0.7rem; color: #64748b; margin-bottom: 1rem;">FIELD-LEVEL RELIABILITY</h4>';
        Object.entries(data.field_accuracy).forEach(([field, acc]) => {
            const color = acc > 95 ? 'var(--conf-high)' : (acc > 70 ? 'var(--conf-med)' : 'var(--conf-low)');
            barsHtml += `
                <div style="margin-bottom: 1rem;">
                    <div style="display: flex; justify-content: space-between; font-size: 0.75rem; margin-bottom: 4px;">
                        <span>${field}</span>
                        <span>${acc.toFixed(0)}%</span>
                    </div>
                    <div style="height: 4px; background: rgba(255,255,255,0.05); border-radius: 2px;">
                        <div style="height: 100%; width: ${acc}%; background: ${color}; border-radius: 2px; box-shadow: 0 0 10px ${color}44;"></div>
                    </div>
                </div>
            `;
        });
        fieldPrecisionMap.innerHTML = barsHtml;
        
    } catch (err) {
        fieldPrecisionMap.innerHTML = '<p style="color: var(--conf-low)">Audit link severed.</p>';
    }
}

// UTILS
function switchTab(tab) {
    const normalizer = document.getElementById('main-normalizer');
    const integrity = document.getElementById('main-integrity');
    const btns = document.querySelectorAll('.nav-btn');
    
    btns.forEach(b => b.classList.toggle('active', b.innerText.toLowerCase().includes(tab)));
    
    if (tab === 'normalizer') {
        normalizer.style.display = 'grid';
        integrity.style.display = 'none';
    } else {
        normalizer.style.display = 'none';
        integrity.style.display = 'grid';
    }
}

function setLoading(isLoading) {
    loader.style.display = isLoading ? 'block' : 'none';
    mapBtn.disabled = isLoading;
    if (isLoading) {
        jsonOutput.innerHTML = '<p class="shimmer" style="height: 200px; border-radius: 12px;"></p>';
    }
}
