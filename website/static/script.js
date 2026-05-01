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
    window.dispatchEvent(new CustomEvent('update-suggestions', { detail: [] }));
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

window.currentTableData = [];

window.loadTableData = async (tableName) => {
    const res = await fetch(`/api/db/data/${tableName}`);
    const { columns, data } = await res.json();
    window.currentTableData = data;
    
    document.getElementById('table-head').innerHTML = columns.map(c => `<th class="p-3 text-left border-b border-dark-border">${c}</th>`).join('') + '<th class="p-3 text-left border-b border-dark-border">Aksi</th>';
    
    document.getElementById('table-body').innerHTML = data.map((row, index) => `
        <tr>
            ${columns.map(c => `<td class="p-3 border-b border-dark-border">${row[c]}</td>`).join('')}
            <td class="p-3 border-b border-dark-border flex gap-2">
                <button class="text-accent-blue hover:underline font-medium" onclick="window.openCrudModal('edit', ${index})">Edit</button>
                <button class="text-accent-red hover:underline font-medium" onclick="window.deleteRow('${tableName}', '${row[columns[0]]}', '${columns[0]}')">Hapus</button>
            </td>
        </tr>
    `).join('');
};

window.openCrudModal = (mode, index = null) => {
    window.dispatchEvent(new CustomEvent('open-crud'));
    
    const rowData = index !== null ? window.currentTableData[index] : null;
    const title = document.getElementById('crud-title');
    const inputsDiv = document.getElementById('crud-inputs');
    const tableName = document.getElementById('table-selector').value;
    
    title.textContent = mode === 'add' ? `Tambah ${tableName}` : `Edit ${tableName}`;
    inputsDiv.innerHTML = '';
    
    // Ambil kolom dari header tabel
    const cols = Array.from(document.querySelectorAll('#table-head th')).map(th => th.textContent).filter(c => c !== 'Aksi');
    
    cols.forEach(col => {
        const val = rowData ? rowData[col] : '';
        const isId = col.toLowerCase() === 'id';
        const label = document.createElement('label');
        label.className = 'block mb-4';
        label.innerHTML = `
            <span class="block mb-1 capitalize text-gray-500 text-[0.75rem] font-bold">${col}</span>
            <input type="text" name="${col}" value="${val}" ${mode === 'edit' && isId ? 'readonly opacity-50' : ''} 
                   class="w-full bg-black border border-dark-border p-2.5 rounded-lg outline-none focus:border-accent-blue text-white" />
        `;
        inputsDiv.appendChild(label);
    });

    const form = document.getElementById('crud-form');
    form.onsubmit = async (e) => {
        e.preventDefault();
        const formData = new FormData(form);
        const payload = Object.fromEntries(formData.entries());
        
        const url = mode === 'add' ? `/api/db/add/${tableName}` : `/api/db/edit/${tableName}`;
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (res.ok) {
            window.dispatchEvent(new CustomEvent('close-crud'));
            window.loadTableData(tableName);
        } else {
            const err = await res.json();
            alert("Gagal: " + err.error);
        }
    };
};

window.deleteRow = async (tableName, id, idCol) => {
    if (!confirm(`Hapus baris dengan ${idCol} = ${id}?`)) return;
    const res = await fetch(`/api/db/delete/${tableName}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, id_col: idCol })
    });
    if (res.ok) window.loadTableData(tableName);
};

window.resetChat = async () => {
    if (!confirm("🧹 Bersihkan semua riwayat percakapan?")) return;
    const res = await fetch('/api/chat/reset', { method: 'POST' });
    if (res.ok) location.reload();
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

window.COMMAND_LIST = [
    { cmd: '/help', desc: 'Bantuan & List Perintah' },
    { cmd: '/buy', desc: 'Beli mobil baru' },
    { cmd: '/sell', desc: 'Jual unit dari stok' },
    { cmd: '/setprice', desc: 'Atur harga jual unit' },
    { cmd: '/move', desc: 'Pindah lokasi showroom' },
    { cmd: '/status', desc: 'Cek kondisi showroom' },
    { cmd: '/inspect', desc: 'Inspeksi detail unit' },
    { cmd: '/reset_chat', desc: 'Hapus riwayat pesan' }
];

window.handleCommandInput = (val) => {
    if (val.startsWith('/')) {
        const query = val.toLowerCase();
        const filtered = window.COMMAND_LIST.filter(c => c.cmd.startsWith(query)).slice(0, 5);
        window.dispatchEvent(new CustomEvent('update-suggestions', { detail: filtered }));
    } else {
        window.dispatchEvent(new CustomEvent('update-suggestions', { detail: [] }));
    }
};

window.selectSuggestion = (s) => {
    const input = document.getElementById('user-input');
    input.value = s.cmd + ' ';
    input.focus();
    window.dispatchEvent(new CustomEvent('update-suggestions', { detail: [] }));
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