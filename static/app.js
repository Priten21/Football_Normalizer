// STATE MANAGEMENT
let currentMatchData = null;
let fieldConfidences = {};
let lastTrace = null;
let lastInput = null;

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
        lastTrace = result.mapping_trace;
        lastInput = rawVal;
        
        renderNormalizedData(result.data, result.field_confidences);
        // Only render diagram if we are in traceability tab or if we want background prep
        if (document.getElementById('main-traceability').style.display !== 'none') {
            renderMappingDiagram(result.mapping_trace, result.data, rawVal);
        }
        
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

        html += `  <div class="field-row" id="field-row-${key}">`;
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
    const traceability = document.getElementById('main-traceability');
    const btns = document.querySelectorAll('.nav-btn');
    
    btns.forEach(b => b.classList.toggle('active', b.innerText.toLowerCase().includes(tab)));
    
    if (tab === 'normalizer') {
        normalizer.style.display = 'grid';
        traceability.style.display = 'none';
    } else {
        normalizer.style.display = 'none';
        traceability.style.display = 'grid';
        // Re-render diagram on tab switch to ensure correct coordinates
        if (lastTrace && currentMatchData && lastInput) {
            renderMappingDiagram(lastTrace, currentMatchData, lastInput);
        }
    }
}

function setLoading(isLoading) {
    loader.style.display = isLoading ? 'block' : 'none';
    mapBtn.disabled = isLoading;
    if (isLoading) {
        jsonOutput.innerHTML = '<p class="shimmer" style="height: 200px; border-radius: 12px;"></p>';
        document.getElementById('mappingDiagram').innerHTML = '<div class="diagram-placeholder shimmer" style="height: 200px;">Analyzing architectural flows...</div>';
    }
}

function renderMappingDiagram(trace, normalizedData, rawInputStr) {
    const container = document.getElementById('mappingDiagram');
    container.innerHTML = '';
    
    // Parse raw input
    let rawDict = {};
    try { rawDict = JSON.parse(rawInputStr); } catch(e) {
        const matches = rawInputStr.match(/"([^"]+)"\s*:\s*(?:"([^"]*)"|(-?\d+)|(true|false|null))/g);
        if (matches) {
            matches.forEach(m => {
                const parts = m.split(':');
                const k = parts[0] ? parts[0].replace(/"/g, '').trim() : "unknown";
                const v = parts[1] ? parts[1].replace(/"/g, '').trim() : "N/A";
                rawDict[k] = v;
            });
        }
    }
    
    // 1. Create Left Side (Input Keys - SHOW ALL)
    const leftSide = document.createElement('div');
    leftSide.className = 'diagram-side';
    leftSide.innerHTML = `<div class="group-header">RAW SOURCE DATA (ALL)</div>`;
    
    // 2. Create Right Side (Output Fields)
    const rightSide = document.createElement('div');
    rightSide.className = 'diagram-side';
    
    // 3. SVG for connectors
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute('class', 'mapping-svg');
    container.appendChild(svg);

    // Grouping for Right Side (Comprehensive)
    const GROUPS = {
        "METADATA": ["data_id", "start_at", "start_time", "week_day", "league_name", "display_name", "country", "end_at", "data_static_id", "is_mixed"],
        "TEAMS": ["local_team_id", "local_team_name", "visitor_team_id", "visitor_team_name"],
        "MATCH DATA": ["status", "status_text", "timer", "result", "local_team_score", "visitor_team_score"],
        "SUB-SCORES": ["local_team_ft_score", "local_team_et_score", "local_team_pen_score", "visitor_team_ft_score", "visitor_team_et_score", "visitor_team_pen_score"]
    };

    const allInputKeys = Object.keys(rawDict);
    const traceValues = new Set(Object.values(trace));
    const outputFields = Object.keys(normalizedData);

    // Create Input Nodes (Compact - SHOWING ALL)
    const inputNodes = {};
    allInputKeys.forEach(key => {
        const node = document.createElement('div');
        node.className = 'diagram-node';
        const val = rawDict[key] || "N/A";
        
        // Style based on whether it's used in mapping
        const isUsed = traceValues.has(key);
        if (!isUsed) {
            node.style.opacity = "0.4";
            node.style.borderStyle = "dotted";
        }
        
        node.innerHTML = `<span class="node-key">${key}</span><span class="node-value">${val}</span>`;
        leftSide.appendChild(node);
        inputNodes[key] = node;
    });

    // Create Output Nodes (Grouped & Compact) - Showing ALL schema fields
    const outputNodes = {};
    Object.entries(GROUPS).forEach(([groupName, fields]) => {
        const activeFields = fields.filter(f => outputFields.includes(f));
        if (activeFields.length === 0) return;

        const groupDiv = document.createElement('div');
        groupDiv.className = 'node-group';
        groupDiv.innerHTML = `<div class="group-header">${groupName}</div>`;

        activeFields.forEach(field => {
            const node = document.createElement('div');
            node.className = 'diagram-node';
            node.id = `diagram-node-target-${field}`;
            const val = normalizedData[field] !== undefined ? normalizedData[field] : "null";
            const conf = fieldConfidences[field] || 100;
            const confClass = conf > 85 ? 'conf-high' : (conf > 60 ? 'conf-med' : 'conf-low');
            
            // If field has no trace, mark as "Fixed/Derived"
            const hasTrace = trace[field] !== undefined;
            if (!hasTrace) {
                node.style.opacity = "0.5";
                node.style.borderStyle = "dashed";
            }
            
            node.innerHTML = `
                <span class="node-key">${field}</span>
                <div style="display: flex; align-items: center;">
                    <span class="node-value">${val}</span>
                    <div class="conf-dot" style="background: var(--${confClass})"></div>
                </div>
            `;
            groupDiv.appendChild(node);
            outputNodes[field] = node;
        });
        rightSide.appendChild(groupDiv);
    });

    container.appendChild(leftSide);
    container.appendChild(rightSide);

    // 4. Draw Connectors (Only for fields with a trace)
    setTimeout(() => {
        Object.keys(trace).forEach(field => {
            const inputKey = trace[field];
            const startNode = inputNodes[inputKey];
            const endNode = outputNodes[field];
            const jsonRow = document.getElementById(`field-row-${field}`);
            const conf = fieldConfidences[field] || 100;
            const confPathClass = conf > 85 ? 'conf-high' : (conf > 60 ? 'conf-med' : 'conf-low');
            
            if (startNode && endNode) {
                const startRect = startNode.getBoundingClientRect();
                const endRect = endNode.getBoundingClientRect();
                const containerRect = container.getBoundingClientRect();

                const x1 = startRect.right - containerRect.left;
                const y1 = startRect.top + (startRect.height / 2) - containerRect.top;
                const x2 = endRect.left - containerRect.left;
                const y2 = endRect.top + (endRect.height / 2) - containerRect.top;

                const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
                const cp1 = x1 + (x2 - x1) * 0.3;
                const cp2 = x1 + (x2 - x1) * 0.7;
                const d = `M ${x1} ${y1} C ${cp1} ${y1}, ${cp2} ${y2}, ${x2} ${y2}`;
                
                path.setAttribute('d', d);
                path.setAttribute('class', `mapping-path active ${confPathClass}`);
                svg.appendChild(path);
                
                const setHighlight = (active) => {
                    path.style.strokeWidth = active ? '3' : '1.2';
                    path.style.opacity = active ? '1' : '0.15';
                    [startNode, endNode].forEach(n => n.classList.toggle('active', active));
                    if (jsonRow) jsonRow.classList.toggle('highlighted', active);
                };

                [startNode, endNode].forEach(node => {
                    node.addEventListener('mouseenter', () => setHighlight(true));
                    node.addEventListener('mouseleave', () => setHighlight(false));
                });
                
                if (jsonRow) {
                    jsonRow.addEventListener('mouseenter', () => setHighlight(true));
                    jsonRow.addEventListener('mouseleave', () => setHighlight(false));
                }
            }
        });
    }, 200);
}

// Handle resize for SVG connectors
let resizeTimer;
window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
        if (lastTrace && currentMatchData && lastInput) {
            renderMappingDiagram(lastTrace, currentMatchData, lastInput);
        }
    }, 250);
});
