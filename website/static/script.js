const form = document.getElementById('chat-form');
const input = document.getElementById('user-input');
const chatBox = document.getElementById('chat-box');

marked.setOptions({ breaks: true, gfm: true });

// Alpine access
const getAlpine = () => document.body._x_data_stack[0];

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const msg = input.value.trim();
    if (!msg) return;
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

        if (!cleanText) cleanText = "Sistem menunggu konfirmasi Anda:";
        const msgId = createAiBubble();
        document.getElementById(msgId).innerHTML = marked.parse(cleanText);
        
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
        buttonEl.className = `bg-transparent border border-dark-border px-4 py-2 rounded-full text-sm font-medium transition-all flex items-center gap-1.5 ${isConfirm ? 'text-accent-red hover:bg-accent-red/10 border-accent-red' : 'text-accent-blue hover:bg-accent-blue/10 border-accent-blue'}`;
        buttonEl.innerHTML = `${isConfirm ? '⚠️' : '⚡'} ${btn.label}`;
        
        buttonEl.onclick = () => {
            if (isConfirm) {
                const alpine = getAlpine();
                alpine.confirmLabel = `Konfirmasi Tindakan: ${btn.label}`;
                alpine.confirmCmd = btn.command.replace('/confirm_', '/execute_');
                alpine.showConfirm = true;
                document.getElementById('btn-confirm-exec').onclick = () => {
                    alpine.showConfirm = false;
                    addMessage("✅ Menyetujui perubahan...", 'user');
                    sendMessageToServer(alpine.confirmCmd);
                };
            } else {
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

// --- DATABASE ---
let currentTable = "", tableColumns = [];
window.loadTablesList = async () => {
    const res = await fetch('/api/db/tables');
    const tables = await res.json();
    document.getElementById('table-selector').innerHTML = '<option value="">-- Pilih Tabel --</option>' + tables.map(t => `<option value="${t}">${t}</option>`).join('');
};

window.loadTableData = async (tableName) => {
    currentTable = tableName; if (!tableName) return;
    const res = await fetch(`/api/db/data/${tableName}`);
    const { columns, data } = await res.json();
    tableColumns = columns;
    document.getElementById('table-head').innerHTML = columns.map(c => `<th class="p-3 text-left border-b border-dark-border">${c}</th>`).join('') + '<th class="p-3 text-left border-b border-dark-border">Aksi</th>';
    document.getElementById('table-body').innerHTML = data.map(row => `<tr>${columns.map(c => `<td class="p-3 border-b border-dark-border">${row[c]}</td>`).join('')}<td class="p-3 border-b border-dark-border flex gap-2"><span class="text-accent-blue cursor-pointer underline" onclick='window.openCrudModal("edit", ${JSON.stringify(row)})'>Edit</span><span class="text-accent-red cursor-pointer underline" onclick="window.deleteRow('${tableName}', '${row[columns[0]]}', '${columns[0]}')">Hapus</span></td></tr>`).join('');
};

window.openCrudModal = (mode, rowData = null) => {
    if (!currentTable) return alert("Pilih tabel dulu!");
    getAlpine().showCrud = true;
    document.getElementById('crud-title').textContent = mode === 'add' ? `Tambah ${currentTable}` : `Edit ${currentTable}`;
    document.getElementById('crud-inputs').innerHTML = tableColumns.map(col => `<div class="mb-4"><label class="block mb-1 text-xs text-gray-500">${col}</label><input type="text" name="${col}" class="w-full bg-black border border-dark-border text-white p-2.5 rounded-lg outline-none focus:border-accent-blue" value="${rowData ? rowData[col] : ''}" ${mode === 'edit' && col === tableColumns[0] ? 'readonly' : ''}></div>`).join('');
};

document.getElementById('crud-form').onsubmit = async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target).entries());
    const res = await fetch(`/api/db/upsert/${currentTable}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ data, id_column: tableColumns[0] })
    });
    if (res.ok) { getAlpine().showCrud = false; window.loadTableData(currentTable); }
};

window.deleteRow = async (t, id, col) => {
    if (!confirm("Hapus?")) return;
    await fetch(`/api/db/delete/${t}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, id_column: col }) });
    window.loadTableData(t);
};

window.resetDatabase = async () => {
    if (!confirm("⚠️ PERINGATAN: Ini akan menghapus SELURUH data (Inventory, Keuangan, Log) dan meriset ke default. Lanjutkan?")) return;
    
    const res = await fetch('/api/db/reset', { method: 'POST' });
    const data = await res.json();
    
    if (res.ok) {
        alert("✅ " + data.message);
        location.reload(); // Reload untuk meriset state AI juga
    } else {
        alert("❌ Gagal reset: " + data.error);
    }
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