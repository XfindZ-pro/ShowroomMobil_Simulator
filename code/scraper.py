"""
scraper.py — Modul Pencarian Pasar Mobil Online
Strategi: DuckDuckGo Search (via ddgs) + Ekstraksi Data dari Snippet
Cache hasil ke SQLite (tabel: cache_pasar) dengan key = query+tanggal
"""

import re
import json
import sqlite3
import datetime
from config import DB_FILE

try:
    from ddgs import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    DDGS_AVAILABLE = False

# ============================================================
# SITES TO SEARCH
# ============================================================
TARGET_SITES = [
    "olx.co.id",
    "mobil123.com",
    "carmudi.co.id",
    "oto.com",
    "zigwheels.co.id",
]

# ============================================================
# DATABASE – tabel cache
# ============================================================
def _ensure_cache_table():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cache_pasar (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            query      TEXT,
            tanggal    TEXT,
            results    TEXT,
            fetched_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def _save_cache(query: str, results: list):
    tanggal = datetime.date.today().isoformat()
    conn = sqlite3.connect(DB_FILE)
    conn.execute("DELETE FROM cache_pasar WHERE query = ? AND tanggal != ?",
                 (query.lower(), tanggal))
    conn.execute(
        "INSERT INTO cache_pasar (query, tanggal, results, fetched_at) VALUES (?, ?, ?, ?)",
        (query.lower(), tanggal, json.dumps(results, ensure_ascii=False),
         datetime.datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def _load_cache(query: str):
    tanggal = datetime.date.today().isoformat()
    conn = sqlite3.connect(DB_FILE)
    row = conn.execute(
        "SELECT results FROM cache_pasar WHERE query = ? AND tanggal = ? ORDER BY id DESC LIMIT 1",
        (query.lower(), tanggal)
    ).fetchone()
    conn.close()
    return json.loads(row[0]) if row else None

# ============================================================
# EXTRACTOR LOGIC
# ============================================================
def _extract_price(text: str) -> int:
    """Ekstrak harga rupiah dari teks snippet."""
    text = text.replace(",", ".")
    
    # Pola: Rp 120.000.000 atau Rp 120000000
    m = re.search(r"Rp\.?\s*([\d]{2,3}(?:[.,]\d{3})+)", text)
    if m:
        try:
            raw = m.group(1).replace(".", "").replace(",", "")
            return int(raw)
        except ValueError:
            pass

    # Pola: Rp 120 juta / 120 jt / 120jt
    m = re.search(r"(?:Rp\.?\s*)?([\d]+(?:[.,]\d+)?)\s*(?:juta|jt)", text, re.IGNORECASE)
    if m:
        try:
            val = float(m.group(1).replace(",", "."))
            return int(val * 1_000_000)
        except ValueError:
            pass
    
    return 0

def _extract_year(text: str) -> str:
    """Ekstrak tahun (2010-2025)."""
    m = re.search(r"\b(201[0-9]|202[0-5])\b", text)
    return m.group(1) if m else ""

def _extract_km(text: str) -> str:
    """Ekstrak informasi kilometer."""
    # Pola: 50.000 km, 50rb km, 50.000-55.000 km
    m = re.search(r"([\d.,-]+)\s*(?:km|ribu km|\.000 km|rb km)", text, re.IGNORECASE)
    return m.group(0) if m else ""

def _extract_location(text: str, url: str) -> str:
    """Coba tebak lokasi dari snippet atau URL."""
    # Pola umum lokasi di OLX/Mobil123 biasanya di akhir snippet atau ada nama kota
    cities = ["Jakarta", "Surabaya", "Bandung", "Sidoarjo", "Malang", "Bekasi", "Tangerang", "Depok", "Semarang", "Yogyakarta", "Medan"]
    for city in cities:
        if city.lower() in text.lower():
            return city
    return "Indonesia"

def _clean_domain(url: str) -> str:
    m = re.search(r"(?:https?://)?(?:www\.)?([^/]+)", url)
    return m.group(1) if m else url

# ============================================================
# SEARCH VIA OLX DIRECT (WITH FALLBACK TO DDGS)
# ============================================================
def _search_olx_direct(query: str, max_results: int = 15) -> list:
    """
    Mencoba masuk langsung ke OLX dan memfungsikan search bar (via URL).
    Jika diblokir (timeout), akan mengembalikan list kosong agar diproses DDGS.
    """
    import requests
    from bs4 import BeautifulSoup
    
    # URL OLX Mobil Bekas dengan query search
    # Contoh: https://www.olx.co.id/mobil-bekas_c198/q-avanza
    clean_query = query.lower().replace(" ", "-")
    url = f"https://www.olx.co.id/mobil-bekas_c198/q-{clean_query}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    
    try:
        # Timeout pendek agar tidak hang jika diblokir datacenter
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200:
            return []
            
        soup = BeautifulSoup(response.text, 'html.parser')
        results = []
        
        # Selector berdasarkan pengamatan struktur OLX (data-aut-id)
        items = soup.find_all(attrs={"data-aut-id": "itemBox"})
        for item in items[:max_results]:
            try:
                title_el = item.find(attrs={"data-aut-id": "itemTitle"})
                price_el = item.find(attrs={"data-aut-id": "itemPrice"})
                details_el = item.find(attrs={"data-aut-id": "itemDetails"})
                loc_el = item.find(attrs={"data-aut-id": "itemSubTitle"})
                link_el = item.find('a')
                
                title = title_el.get_text() if title_el else "Unit Mobil"
                price_text = price_el.get_text() if price_el else ""
                details_text = details_el.get_text() if details_el else ""
                loc_text = loc_el.get_text() if loc_el else "Indonesia"
                link = "https://www.olx.co.id" + link_el['href'] if link_el else url
                
                results.append({
                    "judul": title,
                    "deskripsi": f"{details_text} | {loc_text}",
                    "harga": _extract_price(price_text),
                    "tahun": _extract_year(details_text),
                    "kilometer": _extract_km(details_text),
                    "lokasi": loc_text,
                    "sumber": "olx.co.id",
                    "url": link,
                    "relevan": True,
                    "tanggal_fetch": datetime.date.today().isoformat()
                })
            except:
                continue
        return results
    except:
        return []

def _search_ddgs(query: str, max_results: int = 20) -> list:
    if not DDGS_AVAILABLE: return []
    
    # Coba Direct OLX dulu (jika tidak diblokir di environment user)
    direct_results = _search_olx_direct(query, max_results)
    if direct_results:
        print(f"[Scraper] Sukses mengambil data langsung dari OLX.")
        return direct_results
    
    # Fallback ke DDGS jika direct diblokir
    print(f"[Scraper] Direct OLX diblokir/timeout. Menggunakan fallback Search Engine...")
    results = []
    with DDGS() as ddgs:
        # Search Query yang lebih spesifik untuk memicu data harga/tahun di snippet
        # Menambahkan keyword "harga" dan "tahun" membantu memicu snippet yang lebih lengkap
        search_query = f"{query} harga tahun km site:olx.co.id"
        raw = list(ddgs.text(search_query, max_results=max_results))
        
        # Tambahan pencarian umum jika hasil OLX sedikit
        if len(raw) < 5:
            raw += list(ddgs.text(f"{query} jual mobil bekas harga", max_results=10))

        seen_urls = set()
        for r in raw:
            url = r.get("href", r.get("url", ""))
            if url in seen_urls: continue
            seen_urls.add(url)

            title = r.get("title", "")
            body = r.get("body", "")
            full_text = f"{title} {body}"
            
            domain = _clean_domain(url)
            is_relevant = any(site in url for site in TARGET_SITES)
            
            harga = _extract_price(full_text)
            tahun = _extract_year(full_text)
            km = _extract_km(full_text)
            lokasi = _extract_location(full_text, url)
            
            results.append({
                "judul": title[:100],
                "deskripsi": body,
                "harga": harga,
                "tahun": tahun,
                "kilometer": km,
                "lokasi": lokasi,
                "sumber": domain,
                "url": url,
                "relevan": is_relevant,
                "tanggal_fetch": datetime.date.today().isoformat()
            })
    
    # Sort: Relevan dulu, lalu yang ada harga, lalu harga termurah (untuk restock)
    results.sort(key=lambda x: (not x["relevan"], x["harga"] == 0, x["harga"]))
    return results

# ============================================================
# FORMAT OUTPUT
# ============================================================
def _format_summary(query: str, results: list, from_cache: bool = False) -> str:
    now = datetime.datetime.now().strftime("%d %B %Y, %H:%M:%S")
    cache_note = " *(Data Cache)*" if from_cache else ""

    if not results:
        return f"## [Katalog Pasar]: '{query}'\n*Maaf Bos, data tidak ditemukan di internet saat ini.*"

    valid_prices = [r["harga"] for r in results if r["harga"] > 5_000_000]

    lines = [
        f"## [KATALOG PASAR ONLINE]: `{query}`{cache_note}",
        f"*Ditemukan {len(results)} listing di pasaran.*",
        ""
    ]

    if valid_prices:
        p_min = min(valid_prices)
        p_max = max(valid_prices)
        import random
        # Pick a random "Recommended Price" based on the range (RNG Game feel)
        p_rng = random.randint(p_min, p_max)
        
        lines.append(f"> [Harga Pasar (MIN)]: Rp {p_min:,}")
        lines.append(f"> [Harga Pasar (MAX)]: Rp {p_max:,}")
        lines.append(f"> [🔥 HARGA REKOMENDASI AI (RNG)]: **Rp {p_rng:,}**")
        lines.append("")

    lines.append("### [DAFTAR UNIT TERSEDIA]:")
    for i, r in enumerate(results[:12], 1):
        harga_str = f"**Rp {r['harga']:,}**" if r["harga"] > 0 else "*Harga Hubungi Penjual*"
        tahun = f" ({r['tahun']})" if r['tahun'] else ""
        km = f" | {r['kilometer']}" if r['kilometer'] else ""
        lokasi = f" | [Lokasi]: {r['lokasi']}" if r['lokasi'] else ""
        
        lines.append(f"{i}. **{r['judul']}**{tahun}")
        lines.append(f"   - {harga_str}{km}{lokasi}")
        lines.append(f"   - [Buka Katalog]({r['url']})")
        
        # Ambil sedikit deskripsi jika relevan
        desc = r['deskripsi'].strip()
        if desc:
            # Bersihkan deskripsi dari teks yang terlalu panjang
            desc_preview = (desc[:120] + '...') if len(desc) > 120 else desc
            lines.append(f"   *\"{desc_preview}\"*")
        lines.append("")

    return "\n".join(lines)

# ============================================================
# FUNGSI UTAMA
# ============================================================
def search_pasar_online(query: str, force_refresh: bool = False) -> dict:
    _ensure_cache_table()
    timestamp = datetime.datetime.now().isoformat()

    if not force_refresh:
        cached = _load_cache(query)
        if cached:
            return {
                "query": query, "timestamp": timestamp,
                "from_cache": True, "results": cached,
                "summary": _format_summary(query, cached, from_cache=True)
            }

    results = _search_ddgs(query)
    if results: _save_cache(query, results)

    return {
        "query": query, "timestamp": timestamp,
        "from_cache": False, "results": results,
        "summary": _format_summary(query, results, from_cache=False)
    }

if __name__ == "__main__":
    print("=== TEST KATALOG SCRAPER ===\n")
    hasil = search_pasar_online("Toyota Avanza bekas", force_refresh=True)
    # Gunakan encode-ignore untuk terminal windows yang rewel
    print(hasil["summary"].encode("ascii", "ignore").decode())
