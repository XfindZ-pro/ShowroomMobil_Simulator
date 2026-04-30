const form = document.getElementById('chat-form');
const input = document.getElementById('user-input');
const chatBox = document.getElementById('chat-box');

marked.setOptions({ breaks: true, gfm: true });

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const msg = input.value.trim();
    if (!msg) return;

    // Deteksi manual confirm
    const manualConfirm = ["konfirmasi", "setuju", "oke", "deal", "beli"].some(word => msg.toLowerCase().includes(word));
    if (manualConfirm && msg.length < 25) {
        addMessage(msg, 'user');
        addSystemMessage("⚠️ **Harap klik tombol konfirmasi** yang ada di atas pesan ini (warna merah/biru). Mengetik manual tidak akan memproses database.");
        input.value = '';
        return;
    }

    addMessage(msg, 'user');
    input.value = '';
    await sendMessageToServer(msg);
});

async function sendMessageToServer(messageText) {
    const loadingId = addLoading();
    try {
        const res = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: messageText })
        });
        const data = await res.json();
        removeMessage(loadingId);
        
        let buttons = [];
        let cleanText = data.response.replace(/\[UI:(.*?)\|(.*?)\]/g, (m, label, command) => {
            buttons.push({ label, command });
            return ""; 
        }).trim();

        if (!cleanText && buttons.length > 0) cleanText = "Sistem memerlukan tindakan:";
        const msgId = createAiBubble();
        document.getElementById(msgId).innerHTML = marked.parse(cleanText || "...");
        
        if (buttons.length > 0) addButtonsToBubble(buttons, msgId);
        if (data.system_msg) addSystemMessage(data.system_msg);
        scrollToBottom();
    } catch (err) {
        removeMessage(loadingId);
        console.error(err);
    }
}

function addButtonsToBubble(buttons, parentId) {
    const wrapper = document.createElement('div');
    wrapper.className = 'flex flex-wrap gap-2 mt-2';
    
    buttons.forEach(btn => {
        const isConfirm = btn.command.startsWith('/confirm_');
        const buttonEl = document.createElement('button');
        
        let colorClass = 'text-accent-blue hover:bg-accent-blue/10 border-accent-blue';
        if (isConfirm) colorClass = 'text-accent-red hover:bg-accent-red/10 border-accent-red';
        
        buttonEl.className = `bg-transparent border px-4 py-2 rounded-full text-sm font-medium transition-all flex items-center gap-1.5 ${colorClass}`;
        buttonEl.innerHTML = `${isConfirm ? '⚠️' : '⚡'} ${btn.label}`;
        
        buttonEl.onclick = () => {
            if (isConfirm) {
                // Update modal info & tampilkan
                window.dispatchEvent(new CustomEvent('open-confirm', { 
                    detail: { 
                        label: `Konfirmasi Tindakan: ${btn.label}`, 
                        cmd: btn.command.replace('/confirm_', '/execute_') 
                    } 
                }));
                
                // Gunakan listener satu kali agar tidak menumpuk
                const execBtn = document.getElementById('btn-confirm-exec');
                const newExecBtn = execBtn.cloneNode(true); // Hapus semua listener lama
                execBtn.parentNode.replaceChild(newExecBtn, execBtn);
                
                newExecBtn.onclick = () => {
                    window.dispatchEvent(new CustomEvent('close-confirm'));
                    addMessage("✅ Menyetujui perubahan...", 'user');
                    sendMessageToServer(btn.command.replace('/confirm_', '/execute_'));
                };
            } else {
                const label = btn.label.toLowerCase();
                if (label.includes("stok")) window.dispatchEvent(new CustomEvent('open-db'));
                else if (label.includes("pasar")) window.dispatchEvent(new CustomEvent('open-market'));
                
                addMessage(btn.label, 'user');
                sendMessageToServer(btn.command);
            }
        };
        wrapper.appendChild(buttonEl);
    });
    document.getElementById(parentId).parentElement.appendChild(wrapper);
}

// --- HELPERS ---
function addMessage(text, sender) {
    const div = document.createElement('div');
    div.className = `flex flex-col max-w-[85%] animate-fadeIn ${sender === 'user' ? 'self-end items-end' : 'self-start'}`;
    div.innerHTML = `<div class="p-3 rounded-2xl text-[0.95rem] leading-relaxed break-words ${sender === 'user' ? 'bubble-user' : 'bubble-ai'}">${marked.parse(text)}</div>`;
    chatBox.appendChild(div);
    scrollToBottom();
}

function createAiBubble() {
    const id = 'ai-' + Date.now();
    const div = document.createElement('div');
    div.className = 'flex flex-col max-w-[85%] self-start animate-fadeIn';
    div.innerHTML = `<div id="${id}" class="p-3 rounded-2xl text-[0.95rem] leading-relaxed break-words bubble-ai"></div>`;
    chatBox.appendChild(div);
    return id;
}

function addSystemMessage(text) {
    const div = document.createElement('div');
    div.className = 'terminal-note animate-fadeIn';
    div.innerHTML = marked.parse(text);
    chatBox.appendChild(div);
    scrollToBottom();
}

function addLoading() {
    const id = 'load-' + Date.now();
    const div = document.createElement('div');
    div.id = id; div.className = 'flex flex-col max-w-[85%] self-start animate-fadeIn';
    div.innerHTML = '<div class="p-3 rounded-2xl text-[0.95rem] bubble-ai animate-pulse">...</div>';
    chatBox.appendChild(div);
    scrollToBottom();
    return id;
}

function removeMessage(id) { document.getElementById(id)?.remove(); }
function scrollToBottom() { chatBox.scrollTop = chatBox.scrollHeight; }

// --- DATABASE API ---
window.loadTablesList = async () => {
    try {
        const res = await fetch('/api/db/tables');
        const tables = await res.json();
        const sel = document.getElementById('table-selector');
        if (sel) sel.innerHTML = '<option value="">-- Pilih Tabel --</option>' + tables.map(t => `<option value="${t}">${t}</option>`).join('');
    } catch(e) {}
};

window.loadTableData = async (tableName) => {
    const res = await fetch(`/api/db/data/${tableName}`);
    const { columns, data } = await res.json();
    document.getElementById('table-head').innerHTML = columns.map(c => `<th class="p-3 text-left border-b border-dark-border">${c}</th>`).join('') + '<th class="p-3 text-left border-b border-dark-border">Aksi</th>';
    document.getElementById('table-body').innerHTML = data.map(row => `<tr>${columns.map(c => `<td class="p-3 border-b border-dark-border">${row[c]}</td>`).join('')}<td class="p-3 border-b border-dark-border flex gap-2"><span class="text-accent-blue cursor-pointer underline" onclick='window.openCrudModal("edit", ${JSON.stringify(row)})'>Edit</span><span class="text-accent-red cursor-pointer underline" onclick="window.deleteRow('${tableName}', '${row[columns[0]]}', '${columns[0]}')">Hapus</span></td></tr>`).join('');
};

window.openCrudModal = (mode, rowData = null) => {
    const alp = document.body.__x ? document.body.__x.$data : document.body._x_data_stack[0];
    if(alp) alp.showCrud = true;
    document.getElementById('crud-title').textContent = mode === 'add' ? 'Tambah Data' : 'Edit Data';
    // Logic form dynamic (singkat)
};

window.resetDatabase = async () => {
    if (!confirm("⚠️ Hapus semua data?")) return;
    const res = await fetch('/api/db/reset', { method: 'POST' });
    if (res.ok) location.reload();
};

window.doMarketSearch = async () => {
    const query = document.getElementById('market-query').value.trim();
    if (!query) return;
    const btn = document.getElementById('market-search-btn');
    const loadingId = addLoading();
    btn.disabled = true; btn.textContent = '...';
    addMessage(`🔍 Cari pasar: **${query}**`, 'user');
    const res = await fetch('/api/search_market', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query, force_refresh: document.getElementById('market-force').checked }) });
    const data = await res.json();
    removeMessage(loadingId);
    addMessage(data.summary || 'Tidak ada hasil.', 'ai');
    btn.disabled = false; btn.textContent = 'Cari';
};

// Load history on startup
window.addEventListener('DOMContentLoaded', async () => {
    const res = await fetch('/api/chat/history');
    const history = await res.json();
    history.forEach(msg => {
        if (msg.role === 'user') addMessage(msg.content, 'user');
        else if (msg.role === 'assistant') {
            // Re-render AI message with buttons if needed
            let buttons = [];
            let cleanText = msg.content.replace(/\[UI:(.*?)\|(.*?)\]/g, (m, label, command) => {
                buttons.push({ label, command });
                return ""; 
            }).trim();
            const msgId = createAiBubble();
            document.getElementById(msgId).innerHTML = marked.parse(cleanText || "...");
            if (buttons.length > 0) addButtonsToBubble(buttons, msgId);
        }
    });
});