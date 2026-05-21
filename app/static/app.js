// GraphRAG Client Application Logic

document.addEventListener('DOMContentLoaded', () => {
    // UI Elements
    const navItems = document.querySelectorAll('.nav-item');
    const panels = document.querySelectorAll('.panel');
    const currentPanelTitle = document.getElementById('current-panel-title');
    const currentPanelSubtitle = document.getElementById('current-panel-subtitle');
    
    // Header Metrics
    const headerDocCount = document.getElementById('header-doc-count');
    const headerEntityCount = document.getElementById('header-entity-count');
    
    // Tab switching inside Query Panel
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');
    
    // Ingestion Drag-and-Drop
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const uploadProgressList = document.getElementById('upload-progress-list');
    const docTableBody = document.getElementById('document-table-body');
    
    // Query Workspace
    const queryForm = document.getElementById('query-form');
    const queryInput = document.getElementById('query-input');
    const chatMessages = document.getElementById('chat-messages');
    const querySubmitBtn = document.getElementById('query-submit-btn');
    
    const answerEmpty = document.getElementById('answer-empty');
    const answerDisplay = document.getElementById('answer-display');
    const sourcesEmpty = document.getElementById('sources-empty');
    const sourcesList = document.getElementById('sources-list');
    const graphEmpty = document.getElementById('graph-empty');
    const relationshipsList = document.getElementById('relationships-list');
    
    // Header Dropdowns
    const btnDocsDropdown = document.getElementById('btn-docs-dropdown');
    const docsDropdown = document.getElementById('docs-dropdown');
    const docsDropdownList = document.getElementById('docs-dropdown-list');
    const btnShareDropdown = document.getElementById('btn-share-dropdown');
    const shareDropdown = document.getElementById('share-dropdown');
    
    const btnCopyShareLink = document.getElementById('btn-copy-share-link');
    const btnExportSession = document.getElementById('btn-export-session');
    const btnExportGraph = document.getElementById('btn-export-graph');
    
    // Graph Explorer
    const graphViewport = document.getElementById('graph-viewport');
    const btnRefreshGraph = document.getElementById('btn-refresh-graph');
    const inspectorContent = document.getElementById('inspector-content');
    const graphSearchInput = document.getElementById('graph-search-input');
    const btnClearGraphSearch = document.getElementById('btn-clear-graph-search');
    const graphDocSelect = document.getElementById('graph-doc-select');
    
    // Analytics
    const statDocs = document.getElementById('stat-docs');
    const statChunks = document.getElementById('stat-chunks');
    const statEntities = document.getElementById('stat-entities');
    const statRels = document.getElementById('stat-rels');
    const entityBreakdown = document.getElementById('entity-type-breakdown');
    const relBreakdown = document.getElementById('relationship-type-breakdown');

    let graphInstance = null;
    let rawGraphData = null;
    let activeFilters = {}; // Keep active state of dynamic filter types

    // --- NAVIGATION LOGIC ---
    const panelMeta = {
        'nav-query': { title: 'Query Workspace', subtitle: 'Ask questions across unstructured docs using vector and graph intelligence' },
        'nav-ingestion': { title: 'Document Ingestion', subtitle: 'Upload and process documents to build your Knowledge Graph' },
        'nav-explorer': { title: 'Graph Explorer', subtitle: 'Visualize and inspect nodes and relationships extracted from text' },
        'nav-stats': { title: 'Platform Analytics', subtitle: 'Review system metrics, entity distributions, and graph schemas' }
    };

    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const targetId = item.getAttribute('href').substring(1);
            
            navItems.forEach(n => n.classList.remove('active'));
            panels.forEach(p => p.classList.remove('active'));
            
            item.classList.add('active');
            document.getElementById(`panel-${targetId}`).classList.add('active');
            
            // Update Headers
            const meta = panelMeta[item.id];
            currentPanelTitle.textContent = meta.title;
            currentPanelSubtitle.textContent = meta.subtitle;
            
            // Refresh views if specific panels are loaded
            if (targetId === 'ingestion') {
                loadDocuments();
            } else if (targetId === 'explorer') {
                initGraphExplorer();
            } else if (targetId === 'stats') {
                loadAnalytics();
            }
        });
    });

    // --- TOP-RIGHT HEADER DROPDOWNS & SHARE ACTIONS ---
    function showToast(message) {
        const existing = document.querySelector('.toast-notification');
        if (existing) existing.remove();
        
        const toast = document.createElement('div');
        toast.className = 'toast-notification';
        toast.innerHTML = message;
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.5s ease';
            setTimeout(() => toast.remove(), 500);
        }, 3000);
    }

    // Toggle dropdowns
    btnDocsDropdown.addEventListener('click', (e) => {
        e.stopPropagation();
        shareDropdown.classList.remove('active');
        btnShareDropdown.parentElement.classList.remove('active');
        
        const active = docsDropdown.classList.toggle('active');
        btnDocsDropdown.parentElement.classList.toggle('active', active);
        if (active) {
            loadDocuments();
        }
    });

    btnShareDropdown.addEventListener('click', (e) => {
        e.stopPropagation();
        docsDropdown.classList.remove('active');
        btnDocsDropdown.parentElement.classList.remove('active');
        
        const active = shareDropdown.classList.toggle('active');
        btnShareDropdown.parentElement.classList.toggle('active', active);
    });

    // Redirect "Manage Ingestion" button to active navigation click
    const btnGotoIngestion = document.getElementById('btn-goto-ingestion');
    if (btnGotoIngestion) {
        btnGotoIngestion.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            docsDropdown.classList.remove('active');
            btnDocsDropdown.parentElement.classList.remove('active');
            
            const navIngestion = document.getElementById('nav-ingestion');
            if (navIngestion) {
                navItems.forEach(n => n.classList.remove('active'));
                panels.forEach(p => p.classList.remove('active'));
                
                navIngestion.classList.add('active');
                const panelIngestion = document.getElementById('panel-ingestion');
                if (panelIngestion) {
                    panelIngestion.classList.add('active');
                }
                
                // Update Headers
                const meta = panelMeta['nav-ingestion'];
                if (meta) {
                    currentPanelTitle.textContent = meta.title;
                    currentPanelSubtitle.textContent = meta.subtitle;
                }
                
                loadDocuments();
            }
        });
    }

    // Filter dropdown toggle
    const btnFilterDropdown = document.getElementById('btn-filter-dropdown');
    const filterDropdownContent = document.getElementById('filter-dropdown-content');
    if (btnFilterDropdown && filterDropdownContent) {
        btnFilterDropdown.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            filterDropdownContent.classList.toggle('show');
        });
    }

    const btnSelectAll = document.getElementById('btn-filter-select-all');
    const btnClearFilters = document.getElementById('btn-filter-clear');
    
    if (btnSelectAll) {
        btnSelectAll.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const checkboxes = document.querySelectorAll('#filter-dropdown-list input[type="checkbox"]');
            checkboxes.forEach(cb => {
                cb.checked = true;
                const type = cb.dataset.type;
                activeFilters[type] = true;
            });
            renderFilteredGraph();
        });
    }
    
    if (btnClearFilters) {
        btnClearFilters.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const checkboxes = document.querySelectorAll('#filter-dropdown-list input[type="checkbox"]');
            checkboxes.forEach(cb => {
                cb.checked = false;
                const type = cb.dataset.type;
                activeFilters[type] = false;
            });
            renderFilteredGraph();
        });
    }

    // Close dropdowns on outside click
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.dropdown-wrapper')) {
            docsDropdown.classList.remove('active');
            btnDocsDropdown.parentElement.classList.remove('active');
            shareDropdown.classList.remove('active');
            btnShareDropdown.parentElement.classList.remove('active');
        }
        
        // Filter dropdown outside click handling
        const filterContainer = document.getElementById('filter-dropdown-container');
        const filterContent = document.getElementById('filter-dropdown-content');
        if (filterContainer && filterContent && !filterContainer.contains(e.target)) {
            filterContent.classList.remove('show');
        }
    });

    // Helper to copy text to clipboard with fallback for non-secure origins
    function copyTextToClipboard(text) {
        if (navigator.clipboard) {
            return navigator.clipboard.writeText(text);
        } else {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            document.body.appendChild(textarea);
            textarea.focus();
            textarea.select();
            try {
                const successful = document.execCommand('copy');
                textarea.remove();
                if (successful) return Promise.resolve();
                else return Promise.reject(new Error('Copy command failed'));
            } catch (err) {
                textarea.remove();
                return Promise.reject(err);
            }
        }
    }

    // Copy share link
    btnCopyShareLink.addEventListener('click', () => {
        copyTextToClipboard(window.location.href).then(() => {
            showToast('<i class="fa-solid fa-circle-check text-cyan"></i> Workspace link copied to clipboard!');
            shareDropdown.classList.remove('active');
            btnShareDropdown.parentElement.classList.remove('active');
        }).catch(err => {
            showToast('<i class="fa-solid fa-triangle-exclamation text-rose"></i> Copy failed.');
        });
    });

    // Export query session as Markdown (.md)
    btnExportSession.addEventListener('click', () => {
        const messages = [];
        document.querySelectorAll('#chat-messages .message').forEach(msg => {
            if (msg.classList.contains('welcome')) return;
            const isUser = msg.classList.contains('user');
            const sender = isUser ? 'User' : 'CypherDocs Agent';
            const text = msg.querySelector('.message-body').innerText.trim();
            messages.push(`### ${sender}\n\n${text}\n`);
        });
        
        if (messages.length === 0) {
            showToast('<i class="fa-solid fa-info-circle text-yellow"></i> No chat history to export.');
            return;
        }
        
        const markdownContent = `# CypherDocs Session Export\nExported on: ${new Date().toLocaleString()}\n\n---\n\n` + messages.join('\n---\n\n');
        
        const blob = new Blob([markdownContent], { type: 'text/markdown;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const downloadAnchor = document.createElement('a');
        downloadAnchor.setAttribute("href", url);
        downloadAnchor.setAttribute("download", `cypherdocs_session_${Date.now()}.md`);
        document.body.appendChild(downloadAnchor);
        downloadAnchor.click();
        downloadAnchor.remove();
        URL.revokeObjectURL(url);
        
        showToast('<i class="fa-solid fa-file-arrow-down text-emerald"></i> Session history exported as Markdown.');
        shareDropdown.classList.remove('active');
        btnShareDropdown.parentElement.classList.remove('active');
    });

    // Export graph subgraph (respected by active document filter)
    btnExportGraph.addEventListener('click', async () => {
        try {
            showToast('<i class="fa-solid fa-spinner fa-spin text-cyan"></i> Exporting graph data...');
            const selectedDocId = graphDocSelect ? graphDocSelect.value : '';
            let url = '/api/graph/subgraph?limit=1000';
            if (selectedDocId) {
                url += `&doc_id=${encodeURIComponent(selectedDocId)}`;
            }
            const res = await fetch(url);
            const graphData = await res.json();
            
            const blob = new Blob([JSON.stringify(graphData, null, 2)], { type: 'application/json;charset=utf-8;' });
            const urlBlob = URL.createObjectURL(blob);
            const downloadAnchor = document.createElement('a');
            downloadAnchor.setAttribute("href", urlBlob);
            downloadAnchor.setAttribute("download", `cypherdocs_graph_${selectedDocId ? 'filtered' : 'all'}_${Date.now()}.json`);
            document.body.appendChild(downloadAnchor);
            downloadAnchor.click();
            downloadAnchor.remove();
            URL.revokeObjectURL(urlBlob);
            
            showToast('<i class="fa-solid fa-file-arrow-down text-emerald"></i> Graph structure exported.');
        } catch (err) {
            showToast('<i class="fa-solid fa-triangle-exclamation text-rose"></i> Graph export failed.');
        }
        shareDropdown.classList.remove('active');
        btnShareDropdown.parentElement.classList.remove('active');
    });

    // --- QUERY TAB INSIDE WORKSPACE LOGIC ---
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.getAttribute('data-tab');
            
            tabBtns.forEach(b => b.classList.remove('active'));
            tabPanes.forEach(p => p.classList.remove('active'));
            
            btn.classList.add('active');
            document.getElementById(targetTab).classList.add('active');
        });
    });

    // --- UTILS: Markdown to HTML Parser ---
    function parseMarkdown(text) {
        if (!text) return "";
        let html = text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>');
            
        // Simple list parsers
        html = html.replace(/^\s*-\s+(.*?)$/gm, '<li>$1</li>');
        html = html.replace(/(<li>.*?<\/li>)/gs, '<ul>$1</ul>');
        // Clean double nested lists
        html = html.replace(/<\/ul>\s*<ul>/g, '');
        
        return `<p>${html}</p>`;
    }

    // --- SYSTEM HEADERS LOGIC ---
    async function updateHeaderStats() {
        try {
            const res = await fetch('/api/graph/stats');
            const data = await res.json();
            headerDocCount.textContent = data.document_count || 0;
            headerEntityCount.textContent = data.entity_count || 0;
        } catch (err) {
            console.error('Failed to update stats:', err);
        }
    }
    updateHeaderStats();
    setInterval(updateHeaderStats, 10000); // refresh metrics every 10s

    // --- CHAT & QUERY LOGIC ---
    queryForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const query = queryInput.value.trim();
        if (!query) return;

        // Add user bubble
        appendMessage('user', query);
        queryInput.value = '';
        
        // Show agent typing placeholder
        const placeholderId = appendMessage('assistant', '<i class="fa-solid fa-spinner fa-spin"></i> Synthesizing context and reasoning answer...');
        querySubmitBtn.disabled = true;

        try {
            const res = await fetch('/api/query', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query })
            });
            
            if (!res.ok) {
                throw new Error(`Server returned code ${res.status}`);
            }

            const data = await res.json();
            
            // Replace placeholder with final answer
            updateMessage(placeholderId, parseMarkdown(data.answer));
            
            // Populate right panel details
            renderQueryResultContext(data);

        } catch (err) {
            updateMessage(placeholderId, `<span style="color:var(--color-rose)"><i class="fa-solid fa-triangle-exclamation"></i> Error generating answer: ${err.message}</span>`);
        } finally {
            querySubmitBtn.disabled = false;
        }
    });

    function appendMessage(sender, text) {
        const id = 'msg-' + Date.now();
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${sender}`;
        msgDiv.id = id;
        
        const avatarIcon = sender === 'user' ? 'fa-user' : 'fa-circle-nodes';
        
        msgDiv.innerHTML = `
            <div class="message-avatar">
                <i class="fa-solid ${avatarIcon}"></i>
            </div>
            <div class="message-body">
                ${text}
            </div>
        `;
        chatMessages.appendChild(msgDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return id;
    }

    function updateMessage(id, text) {
        const msgDiv = document.getElementById(id);
        if (msgDiv) {
            const body = msgDiv.querySelector('.message-body');
            body.innerHTML = text;
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    }

    function renderQueryResultContext(data) {
        // 1. Reasoned Answer (duplicate in side view)
        answerEmpty.classList.add('hidden');
        answerDisplay.classList.remove('hidden');
        answerDisplay.innerHTML = parseMarkdown(data.answer);

        // 2. Vector Sources
        sourcesList.innerHTML = '';
        if (data.sources && data.sources.length > 0) {
            sourcesEmpty.classList.add('hidden');
            sourcesList.classList.remove('hidden');
            
            data.sources.forEach(src => {
                const item = document.createElement('div');
                item.className = 'source-item';
                item.innerHTML = `
                    <div class="source-meta">
                        <span class="source-doc"><i class="fa-solid fa-file-pdf text-cyan"></i> ${src.document_name}</span>
                        <span class="source-score">${Math.round(src.score * 100)}% Match</span>
                    </div>
                    <div class="source-text">${src.text}</div>
                `;
                sourcesList.appendChild(item);
            });
        } else {
            sourcesEmpty.classList.remove('hidden');
            sourcesList.classList.add('hidden');
        }

        // 3. Traversed Graph relationships
        relationshipsList.innerHTML = '';
        if (data.graph_relationships && data.graph_relationships.length > 0) {
            graphEmpty.classList.add('hidden');
            relationshipsList.classList.remove('hidden');
            
            data.graph_relationships.forEach(rel => {
                const item = document.createElement('div');
                item.className = 'relation-item';
                item.innerHTML = `
                    <div class="relation-path">
                        <span class="node-label ${rel.source_type}">${rel.source_name}</span>
                        <span class="edge-label">&mdash; [${rel.rel_type}] &rarr;</span>
                        <span class="node-label ${rel.target_type}">${rel.target_name}</span>
                    </div>
                    <div class="relation-desc">${rel.description || 'No relationship description provided.'}</div>
                `;
                relationshipsList.appendChild(item);
            });
        } else {
            graphEmpty.classList.remove('hidden');
            relationshipsList.classList.add('hidden');
        }
        
        // Auto switch tab to reasoned answer in the panel
        tabBtns[0].click();
    }


    // --- INGESTION & UPLOAD LOGIC ---
    dropZone.addEventListener('click', () => fileInput.click());
    
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    ['dragleave', 'dragend'].forEach(type => {
        dropZone.addEventListener(type, () => dropZone.classList.remove('dragover'));
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            handleFileUpload(e.dataTransfer.files);
        }
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            handleFileUpload(fileInput.files);
        }
    });

    async function handleFileUpload(files) {
        const formData = new FormData();
        for (let i = 0; i < files.length; i++) {
            formData.append('files', files[i]);
            
            // Add UI progress item
            const progressItem = document.createElement('div');
            progressItem.className = 'progress-item';
            progressItem.id = `upload-${files[i].name.replace(/[^a-zA-Z0-9]/g, '')}`;
            progressItem.innerHTML = `
                <span><i class="fa-solid fa-file text-cyan"></i> ${files[i].name}</span>
                <span class="upload-status"><i class="fa-solid fa-spinner fa-spin"></i> Queueing...</span>
            `;
            uploadProgressList.appendChild(progressItem);
        }

        try {
            const res = await fetch('/api/documents/upload', {
                method: 'POST',
                body: formData
            });
            const result = await res.json();
            
            // Mark items as queued
            result.files.forEach(f => {
                const item = document.getElementById(`upload-${f.filename.replace(/[^a-zA-Z0-9]/g, '')}`);
                if (item) {
                    if (f.status === 'queued') {
                        item.querySelector('.upload-status').innerHTML = '<span class="text-cyan"><i class="fa-solid fa-clock"></i> Queued for index</span>';
                    } else {
                        item.querySelector('.upload-status').innerHTML = `<span class="text-rose"><i class="fa-solid fa-xmark"></i> Failed</span>`;
                    }
                }
            });

            // Start polling documents to watch completion
            setTimeout(loadDocuments, 2000);
            pollIngestionStatus();

        } catch (err) {
            console.error('Upload failed:', err);
            uploadProgressList.innerHTML = `<span class="text-rose"><i class="fa-solid fa-triangle-exclamation"></i> Upload failed: ${err.message}</span>`;
        }
    }

    async function loadDocuments() {
        try {
            const res = await fetch('/api/documents');
            const data = await res.json();
            
            // 1. Populate the Main Ingestion Table
            docTableBody.innerHTML = '';
            if (!data.documents || data.documents.length === 0) {
                docTableBody.innerHTML = `
                    <tr>
                        <td colspan="5" class="table-empty">
                            <i class="fa-solid fa-box-open"></i> No documents indexed yet.
                        </td>
                    </tr>
                `;
            } else {
                data.documents.forEach(doc => {
                    const tr = document.createElement('tr');
                    const formattedDate = new Date(doc.created_at).toLocaleString();
                    
                    let badgeClass = 'badge-queued';
                    let statusLabel = doc.status;
                    if (doc.status === 'completed') badgeClass = 'badge-completed';
                    if (doc.status === 'processing') badgeClass = 'badge-processing';
                    if (doc.status === 'failed') badgeClass = 'badge-failed';
                    
                    tr.innerHTML = `
                        <td class="font-semibold">${doc.filename}</td>
                        <td><span class="badge ${badgeClass}">${statusLabel}</span></td>
                        <td>${doc.chunk_count} Chunks</td>
                        <td>${formattedDate}</td>
                        <td>
                            <div style="display:flex;gap:8px;align-items:center;">
                                ${doc.status === 'failed' ? `<button class="btn btn-secondary btn-sm" onclick="alert('${doc.error || 'Unknown Error'}')"><i class="fa-solid fa-circle-exclamation"></i> Show Error</button>` : `<span class="text-emerald" style="font-size:12px;font-weight:600;"><i class="fa-solid fa-circle-check"></i> Ready</span>`}
                                <button class="btn btn-secondary btn-sm btn-delete-doc text-rose" data-id="${doc.id}" title="Delete document from RAG"><i class="fa-solid fa-trash-can"></i></button>
                            </div>
                        </td>
                    `;
                    docTableBody.appendChild(tr);
                });
            }

            // 2. Populate the Top-Right Docs Dropdown
            docsDropdownList.innerHTML = '';
            if (!data.documents || data.documents.length === 0) {
                docsDropdownList.innerHTML = '<div class="dropdown-loading text-muted">No active documents.</div>';
            } else {
                data.documents.forEach(doc => {
                    let badgeClass = 'badge-queued';
                    if (doc.status === 'completed') badgeClass = 'badge-completed';
                    if (doc.status === 'processing') badgeClass = 'badge-processing';
                    if (doc.status === 'failed') badgeClass = 'badge-failed';
                    
                    const item = document.createElement('div');
                    item.className = 'dropdown-doc-item';
                    item.innerHTML = `
                        <div class="doc-info">
                            <div class="doc-name" title="${doc.filename}">${doc.filename}</div>
                            <div class="doc-subinfo">
                                <span class="badge ${badgeClass}" style="transform: scale(0.85); transform-origin: left; padding: 2px 6px;">${doc.status}</span>
                                <span>${doc.chunk_count} chunks</span>
                            </div>
                        </div>
                        <button class="btn-delete-icon btn-delete-doc" data-id="${doc.id}" title="Delete document"><i class="fa-solid fa-trash-can"></i></button>
                    `;
                    docsDropdownList.appendChild(item);
                });
            }

            // 3. Populate Graph Document Select dropdown
            if (graphDocSelect) {
                const currentSelection = graphDocSelect.value;
                graphDocSelect.innerHTML = '<option value="">All Documents</option>';
                
                if (data.documents && data.documents.length > 0) {
                    data.documents.forEach(doc => {
                        const opt = document.createElement('option');
                        opt.value = doc.id;
                        if (doc.status === 'completed') {
                            opt.textContent = doc.filename;
                        } else if (doc.status === 'processing' || doc.status === 'ingesting' || doc.status === 'pending') {
                            opt.textContent = `${doc.filename} (processing...)`;
                        } else if (doc.status === 'failed') {
                            opt.textContent = `${doc.filename} (failed)`;
                        } else {
                            opt.textContent = `${doc.filename} (${doc.status})`;
                        }
                        graphDocSelect.appendChild(opt);
                    });
                }
                
                if ([...graphDocSelect.options].some(o => o.value === currentSelection)) {
                    graphDocSelect.value = currentSelection;
                }
            }
        } catch (err) {
            console.error('Failed to load documents:', err);
            docTableBody.innerHTML = `
                <tr>
                    <td colspan="5" class="table-empty text-rose">
                        <i class="fa-solid fa-triangle-exclamation"></i> Failed to fetch documents.
                    </td>
                </tr>
            `;
            docsDropdownList.innerHTML = '<div class="dropdown-loading text-rose">Error loading documents.</div>';
        }
    }

    let pollInterval = null;
    function pollIngestionStatus() {
        if (pollInterval) clearInterval(pollInterval);
        
        pollInterval = setInterval(async () => {
            await loadDocuments();
            // Check if there are still processing or queued items
            const activeTasks = Array.from(docTableBody.querySelectorAll('.badge')).some(badge => {
                const txt = badge.textContent.toLowerCase();
                return txt === 'processing' || txt === 'queued';
            });
            
            if (!activeTasks) {
                clearInterval(pollInterval);
                pollInterval = null;
                // Clear the uploads list
                uploadProgressList.innerHTML = '';
                
                // Auto-refresh graph explorer if it is currently loaded/active
                if (document.getElementById('panel-explorer').classList.contains('active')) {
                    initGraphExplorer();
                } else {
                    // pre-load graph data so it's fresh when they switch
                    initGraphExplorer();
                }
                
                // Refresh analytics
                if (document.getElementById('panel-stats').classList.contains('active')) {
                    loadAnalytics();
                }
                
                showToast('<i class="fa-solid fa-circle-check text-cyan"></i> Document processing complete. Graph updated!');
            }
        }, 3000);
    }

    // --- DOCUMENT DELETION HANDLER ---
    document.addEventListener('click', async (e) => {
        const btn = e.target.closest('.btn-delete-doc');
        if (btn) {
            e.preventDefault();
            e.stopPropagation();
            const docId = btn.getAttribute('data-id');
            const container = btn.closest('.dropdown-doc-item, tr');
            const docNameEl = container ? (container.querySelector('.doc-name') || container.querySelector('.font-semibold')) : null;
            const docName = docNameEl ? docNameEl.textContent.trim() : 'this document';
            
            if (confirm(`Are you sure you want to permanently delete "${docName}"?\nThis will remove the file from RAG and delete all its extracted entities and relationships from the database.`)) {
                try {
                    btn.disabled = true;
                    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
                    
                    const res = await fetch(`/api/documents/${docId}`, { method: 'DELETE' });
                    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
                    
                    showToast(`<i class="fa-solid fa-trash-can text-cyan"></i> "${docName}" deleted successfully.`);
                    
                    // Reload documents list and header stats
                    await loadDocuments();
                    await updateHeaderStats();
                    
                    // Refresh current panel views
                    if (document.getElementById('panel-stats').classList.contains('active')) {
                        loadAnalytics();
                    }
                    if (document.getElementById('panel-explorer').classList.contains('active')) {
                        initGraphExplorer();
                    } else {
                        initGraphExplorer();
                    }
                } catch (err) {
                    showToast(`<span class="text-rose"><i class="fa-solid fa-triangle-exclamation"></i> Delete failed: ${err.message}</span>`);
                    await loadDocuments();
                }
            }
        }
    });


    // --- GRAPH EXPLORER LOGIC ---
    btnRefreshGraph.addEventListener('click', () => initGraphExplorer());

    function getEntityTypeColor(type) {
        if (!type) return '#90a4ae';
        switch (type.toUpperCase()) {
            case 'ORGANIZATION': return '#00e5ff';
            case 'PERSON': return '#a855f7';
            case 'LOCATION': return '#ff1744';
            case 'PRODUCT': return '#e040fb';
            case 'EVENT': return '#ffd700';
            case 'DATE': return '#29b6f6';
            case 'LAW_REGULATION': return '#00e676';
            case 'CONTRACT_AGREEMENT': return '#ff9100';
            case 'FINANCIAL_INSTRUMENT': return '#ff5722';
            case 'ASSET': return '#8d6e63';
            case 'TECHNOLOGY': return '#26a69a';
            case 'CONCEPT': return '#ab47bc';
            default: return '#90a4ae';
        }
    }

    function formatTypeName(type) {
        if (!type) return '';
        return type.split('_')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
            .join(' ');
    }

    function renderFilteredGraph() {
        if (!rawGraphData || !graphInstance) return;

        const filteredNodes = rawGraphData.nodes.filter(n => {
            const t = n.type || '';
            return activeFilters[t] !== false;
        });

        const nodeIds = new Set(filteredNodes.map(n => n.id));

        const filteredLinks = rawGraphData.links.filter(l => {
            const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
            const targetId = typeof l.target === 'object' ? l.target.id : l.target;
            return nodeIds.has(sourceId) && nodeIds.has(targetId);
        });

        graphInstance.graphData({ nodes: filteredNodes, links: filteredLinks });
    }

    function renderDynamicLegend(types) {
        const listContainer = document.getElementById('filter-dropdown-list');
        if (!listContainer) return;
        
        listContainer.innerHTML = '';
        
        if (types.length === 0) {
            listContainer.innerHTML = '<span class="text-muted" style="font-size:11px; padding: 4px 6px;">No entity types</span>';
            return;
        }

        types.forEach(type => {
            if (activeFilters[type] === undefined) {
                activeFilters[type] = true;
            }
            
            const label = document.createElement('label');
            label.className = 'filter-dropdown-item';
            
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.checked = activeFilters[type];
            checkbox.dataset.type = type;
            checkbox.addEventListener('change', (e) => {
                activeFilters[type] = e.target.checked;
                renderFilteredGraph();
            });
            
            const dot = document.createElement('span');
            dot.className = 'filter-dropdown-color-dot';
            dot.style.backgroundColor = getEntityTypeColor(type);

            const textSpan = document.createElement('span');
            textSpan.className = 'filter-dropdown-text';
            textSpan.textContent = formatTypeName(type);
            
            label.appendChild(checkbox);
            label.appendChild(dot);
            label.appendChild(textSpan);
            
            listContainer.appendChild(label);
        });
    }

    if (graphDocSelect) {
        graphDocSelect.addEventListener('change', () => {
            initGraphExplorer();
        });
    }

    graphSearchInput.addEventListener('input', () => {
        const query = (graphSearchInput.value || '').trim().toLowerCase();
        if (query) {
            btnClearGraphSearch.style.display = 'block';
            if (rawGraphData && graphInstance) {
                // Find node matching query in rawGraphData
                const match = rawGraphData.nodes.find(n => (n.name || '').toLowerCase().includes(query));
                if (match && typeof match.x === 'number') {
                    graphInstance.centerAt(match.x, match.y, 600);
                    graphInstance.zoom(2.5, 600);
                }
            }
        } else {
            btnClearGraphSearch.style.display = 'none';
        }
        if (graphInstance) {
            graphInstance.refresh();
        }
    });

    btnClearGraphSearch.addEventListener('click', () => {
        graphSearchInput.value = '';
        btnClearGraphSearch.style.display = 'none';
        if (graphInstance) {
            graphInstance.refresh();
        }
    });

    async function initGraphExplorer() {
        graphViewport.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted)"><i class="fa-solid fa-spinner fa-spin fa-2x"></i>&nbsp;Loading Knowledge Graph Visuals...</div>';
        
        try {
            const selectedDocId = graphDocSelect ? graphDocSelect.value : '';
            let url = '/api/graph/subgraph?limit=500';
            if (selectedDocId) {
                url += `&doc_id=${encodeURIComponent(selectedDocId)}`;
            }
            
            const res = await fetch(url);
            rawGraphData = await res.json();
            
            graphViewport.innerHTML = '';
            
            if (!rawGraphData.nodes || rawGraphData.nodes.length === 0) {
                graphViewport.innerHTML = `
                    <div class="empty-state">
                        <i class="fa-solid fa-network-wired"></i>
                        <p>Knowledge graph is empty. Ingest documents to populate the schema.</p>
                    </div>
                `;
                renderDynamicLegend([]);
                return;
            }

            // Calculate node degrees
            const degrees = {};
            rawGraphData.nodes.forEach(n => { degrees[n.id] = 0; });
            rawGraphData.links.forEach(l => {
                const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
                const targetId = typeof l.target === 'object' ? l.target.id : l.target;
                if (degrees[sourceId] !== undefined) degrees[sourceId]++;
                if (degrees[targetId] !== undefined) degrees[targetId]++;
            });
            rawGraphData.nodes.forEach(n => {
                n.degree = degrees[n.id] || 0;
            });

            // Dynamically build legend filters
            const nodeTypes = [...new Set(rawGraphData.nodes.map(n => n.type).filter(Boolean))];
            renderDynamicLegend(nodeTypes);

            // Filter initial nodes based on active dynamic filters
            const initialNodes = rawGraphData.nodes.filter(n => {
                const t = n.type || '';
                return activeFilters[t] !== false;
            });

            const initialNodeIds = new Set(initialNodes.map(n => n.id));
            const initialLinks = rawGraphData.links.filter(l => {
                const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
                const targetId = typeof l.target === 'object' ? l.target.id : l.target;
                return initialNodeIds.has(sourceId) && initialNodeIds.has(targetId);
            });

            const viewportRect = graphViewport.getBoundingClientRect();
            const width = viewportRect.width || 800;
            const height = viewportRect.height || 500;

            // Create Force Graph Canvas
            graphInstance = ForceGraph()(graphViewport)
                .width(width)
                .height(height)
                .graphData({ nodes: initialNodes, links: initialLinks })
                .nodeId('id')
                .nodeLabel('label')
                .nodeVal(node => 3 + Math.min((node.degree || 0) * 1.5, 9))
                .nodeColor(node => getEntityTypeColor(node.type))
                .linkWidth(1.5)
                .linkColor(() => '#1f2d48')
                .linkDirectionalParticles(2)
                .linkDirectionalParticleSpeed(d => 0.005)
                .linkDirectionalParticleWidth(1.5)
                .nodeCanvasObject((node, ctx, globalScale) => {
                    const label = node.name;
                    const deg = node.degree || 0;
                    const r = 3 + Math.min(deg * 1.5, 9);

                    const fontSize = 12 / globalScale;
                    ctx.font = `${fontSize}px Outfit`;
                    const textWidth = ctx.measureText(label).width;
                    const bckgDimensions = [textWidth, fontSize].map(n => n + fontSize * 0.2);

                    // Check if node is highlighted/searched
                    const query = (graphSearchInput.value || '').trim().toLowerCase();
                    const isMatched = query && label.toLowerCase().includes(query);

                    // Draw outer pulse/highlight ring if searched
                    if (isMatched) {
                        ctx.beginPath();
                        ctx.arc(node.x, node.y, r + 4, 0, 2 * Math.PI, false);
                        ctx.fillStyle = 'rgba(255, 235, 59, 0.4)'; // glowing yellow ring
                        ctx.fill();
                        
                        ctx.strokeStyle = '#ffeb3b';
                        ctx.lineWidth = 1.5;
                        ctx.stroke();
                    }

                    // Draw node dot
                    ctx.beginPath();
                    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI, false);
                    ctx.fillStyle = getEntityTypeColor(node.type);
                    ctx.fill();

                    // Draw node label background slightly below the node
                    ctx.fillStyle = 'rgba(7, 9, 19, 0.8)';
                    ctx.fillRect(node.x - bckgDimensions[0] / 2, node.y + r + 2 - bckgDimensions[1] / 2, bckgDimensions[0], bckgDimensions[1]);

                    // Draw node text
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    ctx.fillStyle = isMatched ? '#ffeb3b' : '#ffffff';
                    ctx.fillText(label, node.x, node.y + r + 2);
                })
                .onNodeClick(node => {
                    // Update element inspector side card
                    inspectorContent.innerHTML = `
                        <div class="inspector-details">
                            <div class="inspector-prop">
                                <label>Selected Node</label>
                                <span class="ins-name">${node.name}</span>
                            </div>
                            <div class="inspector-prop">
                                <label>Entity Type</label>
                                <span class="node-label ${node.type}">${node.type}</span>
                            </div>
                            <div class="inspector-prop">
                                <label>Description</label>
                                <span>${node.description || 'No description extracted.'}</span>
                            </div>
                        </div>
                    `;
                })
                .onLinkClick(link => {
                    inspectorContent.innerHTML = `
                        <div class="inspector-details">
                            <div class="inspector-prop">
                                <label>Selected Relationship</label>
                                <span class="ins-name">${link.source.name} &rarr; ${link.target.name}</span>
                            </div>
                            <div class="inspector-prop">
                                <label>Relationship Type</label>
                                <span class="edge-label" style="font-size:14px">${link.type}</span>
                            </div>
                            <div class="inspector-prop">
                                <label>Contextual Details</label>
                                <span>${link.description || 'No details stored.'}</span>
                            </div>
                        </div>
                    `;
                });

            // Center the graph after initial simulation engine stops
            let isFirstStop = true;
            graphInstance.onEngineStop(() => {
                if (isFirstStop) {
                    setTimeout(() => {
                        graphInstance.zoomToFit(400, 50);
                    }, 50);
                    isFirstStop = false;
                }
            });

            // Adjust viewport on window resize
            window.addEventListener('resize', () => {
                if (graphInstance) {
                    const rect = graphViewport.getBoundingClientRect();
                    graphInstance.width(rect.width).height(rect.height);
                    setTimeout(() => {
                        graphInstance.zoomToFit(200, 50);
                    }, 100);
                }
            });

        } catch (err) {
            console.error('Failed to init graph visualization:', err);
            graphViewport.innerHTML = `<span class="text-rose" style="padding: 24px"><i class="fa-solid fa-triangle-exclamation"></i> Graph Render Failed: ${err.message}</span>`;
        }
    }


    // --- ANALYTICS LOGIC ---
    async function loadAnalytics() {
        try {
            const res = await fetch('/api/graph/stats');
            const data = await res.json();
            
            // Set counts
            statDocs.textContent = data.document_count || 0;
            statChunks.textContent = data.chunk_count || 0;
            statEntities.textContent = data.entity_count || 0;
            statRels.textContent = data.relationship_count || 0;

            // Render Entity Breakdown
            entityBreakdown.innerHTML = '';
            const maxEntityCount = Math.max(...Object.values(data.entity_types || { 'Default': 1 }));
            if (data.entity_types && Object.keys(data.entity_types).length > 0) {
                Object.entries(data.entity_types).forEach(([type, val]) => {
                    const widthPct = Math.max(5, (val / maxEntityCount) * 100);
                    const row = document.createElement('div');
                    row.className = 'breakdown-row';
                    row.innerHTML = `
                        <div class="breakdown-meta">
                            <span class="breakdown-name">${type}</span>
                            <span class="breakdown-value">${val}</span>
                        </div>
                        <div class="breakdown-progress-container">
                            <div class="breakdown-progress" style="width: ${widthPct}%; background: ${getEntityTypeColor(type)}"></div>
                        </div>
                    `;
                    entityBreakdown.appendChild(row);
                });
            } else {
                entityBreakdown.innerHTML = '<span class="text-muted">No entities extracted.</span>';
            }

            // Render Relationship Breakdown
            relBreakdown.innerHTML = '';
            const maxRelCount = Math.max(...Object.values(data.relationship_types || { 'Default': 1 }));
            if (data.relationship_types && Object.keys(data.relationship_types).length > 0) {
                Object.entries(data.relationship_types).forEach(([type, val]) => {
                    const widthPct = Math.max(5, (val / maxRelCount) * 100);
                    const row = document.createElement('div');
                    row.className = 'breakdown-row';
                    row.innerHTML = `
                        <div class="breakdown-meta">
                            <span class="breakdown-name">${type}</span>
                            <span class="breakdown-value">${val}</span>
                        </div>
                        <div class="breakdown-progress-container">
                            <div class="breakdown-progress" style="width: ${widthPct}%; background: var(--color-purple)"></div>
                        </div>
                    `;
                    relBreakdown.appendChild(row);
                });
            } else {
                relBreakdown.innerHTML = '<span class="text-muted">No relationships extracted.</span>';
            }

        } catch (err) {
            console.error('Failed to load analytics:', err);
        }
    }
});
