// Global state
let currentCall = null;
let allCalls = [];

// Load calls on page load
document.addEventListener('DOMContentLoaded', () => {
    refreshCalls();
    setInterval(refreshCalls, 10000); // Refresh every 10 seconds
});

// Refresh calls list
async function refreshCalls() {
    try {
        const response = await fetch('/api/calls');
        const data = await response.json();
        allCalls = data.calls;
        
        // Update statistics
        updateStatistics();
        
        // Render calls
        renderCalls();
    } catch (error) {
        console.error('Error fetching calls:', error);
    }
}

// Update statistics
function updateStatistics() {
    const total = allCalls.length;
    const transcribed = allCalls.filter(c => c.has_transcription).length;
    const analyzed = allCalls.filter(c => c.has_quality).length;
    
    let avgQuality = '-';
    const scores = allCalls.filter(c => c.quality_score).map(c => c.quality_score);
    if (scores.length > 0) {
        avgQuality = (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1);
    }
    
    document.getElementById('totalCalls').textContent = total;
    document.getElementById('transcribedCalls').textContent = transcribed;
    document.getElementById('analyzedCalls').textContent = analyzed;
    document.getElementById('avgQuality').textContent = avgQuality;
}

// Render calls grid
function renderCalls() {
    const callsList = document.getElementById('callsList');
    
    if (allCalls.length === 0) {
        callsList.innerHTML = '<p class="loading">No calls uploaded yet. Upload an audio file to get started.</p>';
        return;
    }
    
    callsList.innerHTML = allCalls.map(call => `
        <div class="call-card" onclick="viewCallDetails('${call.base_name}')">
            <div class="call-card-title">${call.name}</div>
            <div class="call-card-info">
                <span>📅 ${new Date(call.uploaded_at).toLocaleDateString()}</span>
                <span>📦 ${formatFileSize(call.file_size)}</span>
            </div>
            <div class="call-card-status ${getStatusClass(call.status)}">${call.status}</div>
            
            ${call.quality_score ? `
                <div class="call-card-score">
                    <div class="score-item">
                        <div class="score-label">Quality Score</div>
                        <div class="score-value">${call.quality_score}/10</div>
                    </div>
                </div>
            ` : ''}
            
            <div class="call-card-actions">
                ${call.has_quality ? `<button class="btn-small" onclick="event.stopPropagation(); viewQuality('${call.base_name}')">📊 Report</button>` : ''}
                ${call.has_transcription ? `<button class="btn-small" onclick="event.stopPropagation(); viewTranscription('${call.base_name}')">📝 Text</button>` : ''}
                <button class="btn-small btn-delete" onclick="event.stopPropagation(); deleteCall('${call.base_name}')">🗑️ Delete</button>
            </div>
        </div>
    `).join('');
}

// Get status class
function getStatusClass(status) {
    if (status === 'Complete') return 'status-complete';
    if (status === 'Transcribed') return 'status-transcribed';
    return 'status-uploaded';
}

// Format file size
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// Upload file
function triggerFileUpload() {
    document.getElementById('fileInput').click();
}

async function handleFileUpload() {
    const files = document.getElementById('fileInput').files;
    
    for (let file of files) {
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            showModal(`Uploading ${file.name}...`);
            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            
            if (response.ok) {
                showModal(`✓ ${file.name} uploaded successfully!`);
                setTimeout(refreshCalls, 1000);
            } else {
                showModal(`✗ Error uploading ${file.name}`);
            }
        } catch (error) {
            showModal(`✗ Error: ${error.message}`);
        }
    }
    
    document.getElementById('fileInput').value = '';
}

// Process all calls
async function processAll() {
    if (allCalls.length === 0) {
        showModal('No calls to process. Upload audio files first.');
        return;
    }
    
    showModal('Starting process... This may take a while depending on the number of calls.');
    
    try {
        const response = await fetch('/api/process', { method: 'POST' });
        const data = await response.json();
        
        showModal('✓ Processing complete! Check your calls for updated results.');
        setTimeout(refreshCalls, 2000);
    } catch (error) {
        showModal(`✗ Error: ${error.message}`);
    }
}

// View call details
async function viewCallDetails(baseName) {
    currentCall = allCalls.find(c => c.base_name === baseName);
    
    if (!currentCall) return;
    
    document.getElementById('detailsTitle').textContent = `Call: ${currentCall.name}`;
    document.getElementById('detailsSection').style.display = 'block';
    
    // Show overview
    showTab('overview');
    renderOverview();
}

// Close details
function closeDetails() {
    document.getElementById('detailsSection').style.display = 'none';
    currentCall = null;
}

// Show tab
function showTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Show selected tab
    document.getElementById(tabName).classList.add('active');
    event.target.classList.add('active');
    
    // Load content
    if (tabName === 'overview') {
        renderOverview();
    } else if (tabName === 'transcription') {
        renderTranscription();
    } else if (tabName === 'quality') {
        renderQuality();
    }
}

// Render overview
function renderOverview() {
    const content = document.getElementById('overviewContent');
    
    content.innerHTML = `
        <div style="padding: 20px;">
            <p><strong>File:</strong> ${currentCall.name}</p>
            <p><strong>Size:</strong> ${formatFileSize(currentCall.file_size)}</p>
            <p><strong>Uploaded:</strong> ${new Date(currentCall.uploaded_at).toLocaleString()}</p>
            <p><strong>Status:</strong> ${currentCall.status}</p>
            
            ${currentCall.has_quality ? `
                <div style="margin-top: 20px;">
                    <h4>Quality Metrics</h4>
                    <div style="margin-top: 10px;">
                        <strong>Overall Score: ${currentCall.quality_score}/10</strong>
                    </div>
                </div>
            ` : '<p style="margin-top: 20px; color: #999;">Quality analysis not available yet. Process the call to generate reports.</p>'}
        </div>
    `;
}

// Render transcription
async function renderTranscription() {
    const content = document.getElementById('transcriptionContent');
    
    if (!currentCall.has_transcription) {
        content.innerHTML = '<p style="padding: 20px; color: #999;">Transcription not available. Process the call first.</p>';
        return;
    }
    
    try {
        const response = await fetch(`/api/call/${currentCall.base_name}/transcription`);
        const data = await response.json();
        
        let html = '<div class="transcription-view">';
        
        if (data.diarized_transcript && data.diarized_transcript.entries) {
            data.diarized_transcript.entries.forEach(entry => {
                const speakerId = entry.speaker_id;
                const className = `speaker-${speakerId}`;
                const speakerLabel = speakerId === "0" ? "Agent" : "Client";
                
                html += `
                    <div class="${className}">
                        <div class="speaker-label">[${speakerLabel}] ${entry.start_time_seconds.toFixed(1)}s</div>
                        <div>${entry.transcript}</div>
                    </div>
                `;
            });
        }
        
        html += '</div>';
        content.innerHTML = html;
    } catch (error) {
        content.innerHTML = `<p style="padding: 20px; color: red;">Error loading transcription: ${error.message}</p>`;
    }
}

// Render quality report
async function renderQuality() {
    const content = document.getElementById('qualityContent');
    
    if (!currentCall.has_quality) {
        content.innerHTML = '<p style="padding: 20px; color: #999;">Quality report not available. Process the call first.</p>';
        return;
    }
    
    try {
        const response = await fetch(`/api/call/${currentCall.base_name}/quality`);
        const data = await response.json();
        
        // Extract scores
        const scores = {
            'Clarity': data.clarity_score,
            'Advice Quality': data.advice_quality_score,
            'Professionalism': data.professionalism_score,
            'Risk Awareness': data.risk_awareness_score,
            'Question Handling': data.question_handling_score,
            'Opportunity ID': data.opportunity_identification_score,
            'Relationship': data.relationship_score,
            'Compliance': data.compliance_score
        };
        
        let html = `
            <div style="padding: 20px;">
                <div class="quality-scores">
        `;
        
        Object.entries(scores).forEach(([label, score]) => {
            const fillPercent = (score / 10) * 100;
            html += `
                <div class="score-card">
                    <div class="score-card-label">${label}</div>
                    <div class="score-card-value">${score}</div>
                    <div class="score-card-bar">
                        <div class="score-card-fill" style="width: ${fillPercent}%"></div>
                    </div>
                </div>
            `;
        });
        
        html += '</div>';
        
        // Agent identity
        if (data.agent_identity) {
            html += `
                <div style="margin-top: 20px; padding: 15px; background: #f5f5f5; border-radius: 5px;">
                    <strong>Agent Identity:</strong> ${data.agent_identity}
                </div>
            `;
        }
        
        // Client sentiment
        if (data.client_sentiment) {
            html += `
                <div style="margin-top: 15px; padding: 15px; background: #f5f5f5; border-radius: 5px;">
                    <strong>Client Sentiment:</strong> ${data.client_sentiment}
                </div>
            `;
        }
        
        // Strengths
        if (data.agent_strengths) {
            html += `
                <div style="margin-top: 15px;">
                    <strong>Agent Strengths:</strong>
                    <ul style="margin-top: 10px; margin-left: 20px;">
                        ${Array.isArray(data.agent_strengths) ? 
                            data.agent_strengths.map(s => `<li>${s}</li>`).join('') :
                            `<li>${data.agent_strengths}</li>`
                        }
                    </ul>
                </div>
            `;
        }
        
        // Improvements
        if (data.improvements) {
            html += `
                <div style="margin-top: 15px;">
                    <strong>Areas for Improvement:</strong>
                    <ul style="margin-top: 10px; margin-left: 20px;">
                        ${Array.isArray(data.improvements) ? 
                            data.improvements.map(i => `<li>${i}</li>`).join('') :
                            `<li>${data.improvements}</li>`
                        }
                    </ul>
                </div>
            `;
        }
        
        html += '</div>';
        content.innerHTML = html;
    } catch (error) {
        content.innerHTML = `<p style="padding: 20px; color: red;">Error loading quality report: ${error.message}</p>`;
    }
}

// Quick view functions
async function viewQuality(baseName) {
    currentCall = allCalls.find(c => c.base_name === baseName);
    document.getElementById('detailsTitle').textContent = `Quality: ${currentCall.name}`;
    document.getElementById('detailsSection').style.display = 'block';
    showTab('quality');
}

async function viewTranscription(baseName) {
    currentCall = allCalls.find(c => c.base_name === baseName);
    document.getElementById('detailsTitle').textContent = `Transcription: ${currentCall.name}`;
    document.getElementById('detailsSection').style.display = 'block';
    showTab('transcription');
}

// Delete call
async function deleteCall(baseName) {
    if (!confirm('Are you sure you want to delete this call and all associated data?')) {
        return;
    }
    
    try {
        showModal('Deleting call...');
        const response = await fetch(`/api/call/${baseName}`, { method: 'DELETE' });
        
        if (response.ok) {
            showModal('✓ Call deleted successfully!');
            setTimeout(() => {
                refreshCalls();
                closeDetails();
            }, 1000);
        } else {
            showModal('✗ Error deleting call');
        }
    } catch (error) {
        showModal(`✗ Error: ${error.message}`);
    }
}

// Modal
function showModal(message) {
    document.getElementById('modalMessage').textContent = message;
    document.getElementById('modal').style.display = 'block';
}

function closeModal() {
    document.getElementById('modal').style.display = 'none';
}

window.onclick = function(event) {
    const modal = document.getElementById('modal');
    if (event.target === modal) {
        modal.style.display = 'none';
    }
}
