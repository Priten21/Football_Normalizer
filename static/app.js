// DOM Selections
const navItems = document.querySelectorAll('.nav-item');
const tabContents = document.querySelectorAll('.tab-content');

const mapBtn = document.getElementById('mapButton');
const loader = document.getElementById('loader');
const rawInput = document.getElementById('rawDataInput');
const outJson = document.getElementById('jsonOutput');
const copyBtn = document.getElementById('copyBtn');

// Quality Monitor & Accuracy Toggle
const qualityMonitor = document.getElementById('qualityMonitor');
const qualityStatus = document.getElementById('qualityStatus');
const showStatsBtn = document.getElementById('showStatsBtn');
const accScoreDetail = document.getElementById('accScoreDetail');
const accScoreCircle = document.getElementById('accScoreCircle');

// Bucket Lists
const bucketListCritical = document.getElementById('bucket-critical');
const bucketListOptimization = document.getElementById('bucket-optimization');
const bucketListPerfect = document.getElementById('bucket-perfect');

// Audit Selectors (System Integrity)
const auditBtn = document.getElementById('auditBtn');
const overallScore = document.getElementById('overallScore');
const overallProgress = document.getElementById('overallProgress');
const fieldGrid = document.getElementById('fieldGrid');

const chatStatus = document.getElementById('chatStatus');
const chatInput = document.getElementById('chatInput');
const chatBtn = document.getElementById('sendChat');
const chatHistory = document.getElementById('chatHistory');

let currentContext = null;

// TAB SWITCHING LOGIC
navItems.forEach(item => {
    item.addEventListener('click', () => {
        const targetTab = item.getAttribute('data-tab');
        if (!targetTab) return; // Audit button is handled separately

        navItems.forEach(nav => nav.classList.remove('active'));
        tabContents.forEach(tab => tab.classList.remove('active'));

        item.classList.add('active');
        document.getElementById(`tab-${targetTab}`).classList.add('active');
    });
});

// NORMALIZATION LOGIC
mapBtn.addEventListener('click', async () => {
    const rawVal = rawInput.value.trim();
    if (!rawVal) return alert('Please enter raw data first.');

    mapBtn.disabled = true;
    loader.classList.remove('hidden');
    outJson.textContent = "// Normalizing data via Qwen-1.5B...";
    qualityMonitor.classList.add('hidden');
    accScoreDetail.classList.add('hidden');
    showStatsBtn.textContent = "View Accuracy Report";

    try {
        const res = await fetch('/api/map', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ raw_data: rawVal })
        });

        if (!res.ok) throw new Error('API Error');
        
        const result = await res.json();
        currentContext = result;
        
        // 1. Render JSON
        outJson.textContent = JSON.stringify(result.data, null, 2);
        
        // 2. Render Quality Monitor
        renderQuality(result.quality);
        
        // 3. Unlock Chat
        chatInput.disabled = false;
        chatBtn.disabled = false;
        chatStatus.textContent = "Ready";
        chatStatus.classList.remove('idle');
        chatStatus.classList.add('ready');

        addMessage('System', `Data quality: ${result.quality.status}`, 'system-msg');

    } catch (err) {
        console.error(err);
        outJson.textContent = "// Error: " + err.message;
    } finally {
        mapBtn.disabled = false;
        loader.classList.add('hidden');
    }
});

function renderQuality(quality) {
    qualityMonitor.classList.remove('hidden', 'perfect', 'okayish', 'review');
    qualityMonitor.classList.add(quality.css_class);
    
    qualityStatus.textContent = quality.status;
    
    // Clear and Populate Buckets
    [bucketListCritical, bucketListOptimization, bucketListPerfect].forEach(el => el.innerHTML = '');
    
    quality.buckets.critical.forEach(field => {
        const li = document.createElement('li'); li.textContent = field;
        bucketListCritical.appendChild(li);
    });
    
    quality.buckets.optimization.forEach(field => {
        const li = document.createElement('li'); li.textContent = field;
        bucketListOptimization.appendChild(li);
    });
    
    quality.buckets.perfect.forEach(field => {
        const li = document.createElement('li'); li.textContent = field;
        bucketListPerfect.appendChild(li);
    });
    
    // Set Stats & GLOBAL INTEGRITY REPORT
    accScoreCircle.textContent = quality.confidence;
    
    // Update Integrity Tab with Live Data
    overallScore.textContent = `${quality.confidence}%`;
    overallProgress.style.width = `${quality.confidence}%`;
    
    fieldGrid.innerHTML = '';
    
    // Combine all buckets for the precision grid
    const allFields = [
        ...quality.buckets.perfect.map(f => ({ name: f, status: 'perfect' })),
        ...quality.buckets.optimization.map(f => ({ name: f, status: 'warn' })),
        ...quality.buckets.critical.map(f => ({ name: f, status: 'fail' }))
    ];
    
    allFields.sort((a,b) => a.name.localeCompare(b.name)).forEach(item => {
        const div = document.createElement('div');
        div.className = `field-stat-item ${item.status}`;
        div.innerHTML = `<label>${item.name}</label><span>${item.status.toUpperCase()}</span>`;
        fieldGrid.appendChild(div);
    });
}

showStatsBtn.addEventListener('click', () => {
    accScoreDetail.classList.toggle('hidden');
    showStatsBtn.textContent = accScoreDetail.classList.contains('hidden') ? "View Accuracy Report" : "Hide Accuracy Report";
});

// CHAT LOGIC
async function sendMsg() {
    const msg = chatInput.value.trim();
    if (!msg || !currentContext) return;

    addMessage('You', msg, 'user-msg');
    chatInput.value = '';
    chatStatus.textContent = "Thinking...";

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: msg,
                match_data: currentContext.data
            })
        });

        const data = await res.json();
        addMessage('AI', data.answer, 'bot-msg');
    } catch (err) {
        addMessage('Error', 'Failed to reach tactical engine.', 'bot-msg');
    } finally {
        chatStatus.textContent = "Ready";
    }
}

// AUDIT LOGIC (System Integrity)
async function runAudit() {
    // Switch to Integrity tab automatically
    navItems.forEach(n => n.classList.remove('active'));
    tabContents.forEach(t => t.classList.remove('active'));
    document.querySelector('[data-tab="integrity"]').classList.add('active');
    document.getElementById('tab-integrity').classList.add('active');

    auditBtn.disabled = true;
    auditBtn.innerHTML = '<span class="icon">⌛</span> Auditing...';
    
    try {
        const res = await fetch('/api/accuracy');
        const data = await res.json();
        
        overallScore.textContent = `${data.overall_accuracy.toFixed(1)}%`;
        overallProgress.style.width = `${data.overall_accuracy}%`;
        
        fieldGrid.innerHTML = '';
        Object.entries(data.field_accuracy).forEach(([field, acc]) => {
            const div = document.createElement('div');
            div.className = `field-stat-item ${acc < 100 ? 'fail' : ''}`;
            div.innerHTML = `<label>${field}</label><span>${acc.toFixed(0)}%</span>`;
            fieldGrid.appendChild(div);
        });

    } catch (err) {
        console.error("Audit failed:", err);
        overallScore.textContent = "ERR";
    } finally {
        auditBtn.disabled = false;
        auditBtn.innerHTML = '<span class="icon">📊</span> Run Full Audit';
    }
}

function addMessage(sender, text, className) {
    const d = document.createElement('div');
    d.className = `chat-msg ${className}`;
    d.textContent = text;
    chatHistory.appendChild(d);
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

auditBtn.addEventListener('click', runAudit);
chatBtn.addEventListener('click', sendMsg);
chatInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMsg(); });
copyBtn.addEventListener('click', () => {
    navigator.clipboard.writeText(outJson.textContent).then(() => {
        const originalText = copyBtn.textContent;
        copyBtn.textContent = '✅';
        setTimeout(() => copyBtn.textContent = originalText, 2000);
    });
});
