import streamlit as st
import requests, json, re, csv, io
from datetime import datetime, timezone
from urllib.parse import urlencode

st.set_page_config(page_title="Meta Ads Digital Product Detector", page_icon="🔎", layout="wide")

st.markdown("""
<style>
.main {background:#f6f7fb}
.block-container {padding-top:1.5rem;max-width:1400px}
.hero {padding:24px;border-radius:18px;background:linear-gradient(120deg,#111827,#243b63);color:white}
.metric {background:white;border:1px solid #e5e7eb;border-radius:14px;padding:16px}
.small {color:#64748b;font-size:12px}
.adcard {background:white;border:1px solid #e5e7eb;border-radius:16px;padding:16px;margin-bottom:12px}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="hero"><h1>🔎 Meta Ads Digital Product Detector</h1><p>Riset iklan produk digital & ebook di Meta Ads Library Indonesia — pencarian data, ranking sinyal, dan analisis kreatif.</p></div>', unsafe_allow_html=True)
st.caption("Sumber data: Meta Ads Library publik melalui konektor Apify. Bukan API resmi Meta. Gunakan sesuai ketentuan Meta dan penyedia konektor.")

with st.sidebar:
    st.header("⚙️ Pengaturan koneksi")
    # Prefer server-side Streamlit secrets. The browser input is only a local-session fallback.
    try:
        apify_secret = st.secrets.get("APIFY_API_TOKEN", "")
        ai_secret = st.secrets.get("OPENAI_API_KEY", "")
    except Exception:
        apify_secret, ai_secret = "", ""
    if apify_secret:
        apify_token = apify_secret
        st.success("Apify terhubung melalui server secret.")
    else:
        apify_token = st.text_input("Apify API token", type="password", help="Untuk penggunaan pribadi sementara. Untuk aplikasi online, simpan token di Streamlit Secrets agar tidak ditanam di browser.")
    st.markdown("[Buka pengaturan token Apify](https://console.apify.com/account/integrations)")
    st.markdown("[Lihat konektor Facebook Ads Scraper](https://apify.com/apidojo/facebook-ads-scraper)")
    st.divider()
    st.subheader("Analisis AI (opsional)")
    if ai_secret:
        ai_key = ai_secret
        st.caption("OpenAI key terbaca dari server secret.")
    else:
        ai_key = st.text_input("OpenAI API key", type="password", help="Opsional. Tanpa key, aplikasi tetap memberi analisis pola berbasis aturan.")
    ai_model = st.text_input("Model", value="gpt-4o-mini")
    st.caption("Untuk deployment online, simpan API key di Secrets/Environment Variables server.")

col1, col2, col3 = st.columns([2,1,1])
with col1:
    keyword = st.text_input("Kata kunci / niche", value="ebook bisnis")
with col2:
    active = st.selectbox("Status iklan", ["Aktif saja", "Semua status"], index=0)
with col3:
    limit = st.select_slider("Maksimum iklan", options=[10, 20, 30, 50, 100], value=30)

c1,c2,c3 = st.columns(3)
with c1:
    niche = st.selectbox("Fokus produk", ["Semua produk digital", "Ebook", "Kursus online", "Template & worksheet", "Membership / komunitas", "Software / tools"])
with c2:
    media = st.selectbox("Format kreatif", ["Semua format", "Video", "Gambar"])
with c3:
    sort_mode = st.selectbox("Urutkan hasil", ["Skor sinyal tertinggi", "Iklan terlama aktif", "Advertiser"])

def make_meta_url(q, active_only=True, media_type="all"):
    params = {
        "active_status": "active" if active_only else "all",
        "ad_type": "all",
        "country": "ID",
        "q": q,
        "search_type": "keyword_unordered",
        "media_type": media_type
    }
    return "https://www.facebook.com/ads/library/?" + urlencode(params)

def getv(item, *keys, default=""):
    for k in keys:
        v=item.get(k)
        if v not in (None, "", [], {}):
            return v
    return default

def normalize(item):
    body = getv(item,"bodyText","ad_creative_bodies","body","text","adText")
    if isinstance(body,list): body=" ".join(map(str,body))
    title = getv(item,"title","headline","ad_creative_link_titles")
    if isinstance(title,list): title=" ".join(map(str,title))
    advertiser = getv(item,"pageName","page_name","advertiserName","name",default="Pengiklan tidak tersedia")
    start = getv(item,"startDate","ad_delivery_start_time","startedAt","start_date")
    days = getv(item,"daysActive","days_active",default=None)
    try:
        if days is None and start:
            dt=datetime.fromisoformat(str(start).replace("Z","+00:00"))
            if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
            days=max(0,(datetime.now(timezone.utc)-dt).days)
        days=int(days or 0)
    except: days=0
    platforms=getv(item,"publisherPlatforms","publisher_platforms","platforms",default=[])
    if isinstance(platforms,str): platforms=[platforms]
    link=getv(item,"adLibraryUrl","ad_library_url","ad_snapshot_url","url")
    if not link:
        aid=getv(item,"adArchiveId","id","adId")
        link=("https://www.facebook.com/ads/library/?id="+str(aid)) if aid else make_meta_url(keyword)
    image=""
    imgs=getv(item,"images","imageUrls","image_urls",default=[])
    if isinstance(imgs,list) and imgs:
        x=imgs[0]
        image=x if isinstance(x,str) else getv(x,"url","src")
    cta=getv(item,"ctaText","cta_type","ctaType","callToAction")
    if isinstance(cta,dict): cta=str(cta)
    return {"id":str(getv(item,"adArchiveId","id","adId",default="")),
            "advertiser":str(advertiser),"body":str(body),"title":str(title),
            "start":str(start),"days":days,"platforms":platforms,"link":str(link),
            "cta":str(cta),"image":image,"raw":item}

def score_ad(a):
    # Sinyal observasional, bukan estimasi penjualan.
    s=0; reasons=[]
    d=a["days"]
    if d>=90: s+=35; reasons.append("Aktif ≥90 hari")
    elif d>=45: s+=27; reasons.append("Aktif 45–89 hari")
    elif d>=14: s+=18; reasons.append("Aktif 14–44 hari")
    elif d>=7: s+=10; reasons.append("Aktif 7–13 hari")
    else: reasons.append("Durasi tayang masih pendek / tidak tersedia")
    raw=a["raw"]
    variants=getv(raw,"collationCount","variantCount","creativeCount",default=0)
    try: variants=int(variants)
    except: variants=0
    if variants>=5: s+=25; reasons.append(f"{variants} variasi kreatif terdeteksi")
    elif variants>=2: s+=15; reasons.append(f"{variants} variasi kreatif terdeteksi")
    text=(a["body"]+" "+a["title"]).lower()
    signals=["bonus","gratis","diskon","hemat","rahasia","terbukti","langsung","template","ebook","panduan","kelas","akses","download","praktis","tanpa"]
    hits=[w for w in signals if w in text]
    if len(hits)>=4: s+=15; reasons.append("Copy memiliki beberapa elemen penawaran")
    elif len(hits)>=1: s+=8; reasons.append("Ada kata pemicu penawaran")
    if a["cta"]: s+=8; reasons.append("CTA tersedia")
    if a["link"]: s+=5; reasons.append("Tautan iklan tersedia")
    if a["body"] and len(a["body"])>100: s+=7; reasons.append("Materi copy cukup lengkap")
    return min(s,100), reasons

def heuristic_analysis(a):
    text=(a["body"]+" "+a["title"]).strip()
    low=text.lower()
    hooks=[]
    for pattern,label in [(r"\b(jangan|stop|berhenti)\b","Pola larangan/peringatan"),
                          (r"\b(cara|rahasia|strategi|tips)\b","Pola rasa ingin tahu/edukasi"),
                          (r"\b(gratis|bonus|diskon|promo)\b","Pola insentif"),
                          (r"\b(tanpa|hanya|cukup)\b","Pola kemudahan/keberatan"),
                          (r"\b(hasil|omzet|penghasilan|cuan)\b","Pola hasil yang dijanjikan")]:
        if re.search(pattern,low): hooks.append(label)
    if not text: hook="Copy iklan tidak tersedia pada data yang diterima."
    else: hook=text[:180]+("…" if len(text)>180 else "")
    offer=[]
    for w in ["bonus","gratis","diskon","promo","template","ebook","kelas","akses"]:
        if w in low: offer.append(w)
    cta=a["cta"] or "CTA tidak terdeteksi"
    return {"hook":hook,"pola":hooks or ["Belum ada pola hook yang cukup kuat terdeteksi"],
            "penawaran":", ".join(offer) if offer else "Penawaran spesifik belum terbaca",
            "cta":cta,
            "saran":"Uji angle masalah → solusi, tampilkan isi/preview produk, bukti yang dapat diverifikasi, dan CTA yang spesifik. Jangan menyalin materi kreatif kompetitor."}

def ai_analysis(a, key, model):
    if not key: return None
    prompt=f"""Analisis iklan produk digital berikut dalam Bahasa Indonesia. Bedakan fakta dari hipotesis. Jangan mengklaim penjualan/ROAS karena data itu tidak tersedia. Beri: hook, target audiens yang mungkin, pain point, mekanisme penawaran, CTA, kekuatan, kelemahan, 3 ide eksperimen kreatif orisinal.\\nAdvertiser: {a['advertiser']}\\nTitle: {a['title']}\\nCopy: {a['body']}\\nCTA: {a['cta']}\\nDays active: {a['days']}"""
    try:
        r=requests.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
            json={"model":model,"messages":[{"role":"user","content":prompt}],"temperature":0.3},timeout=60)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return "Analisis AI eksternal gagal: "+str(e)

if "ads" not in st.session_state: st.session_state.ads=[]
if "query_url" not in st.session_state: st.session_state.query_url=""

left,right=st.columns([1,1])
with left:
    search_btn=st.button("🔎 Cari iklan nyata", type="primary", use_container_width=True)
with right:
    st.link_button("Buka pencarian di Meta Ads Library", make_meta_url(keyword, active=="Aktif saja", "video" if media=="Video" else "image" if media=="Gambar" else "all"), use_container_width=True)

if search_btn:
    if not keyword.strip():
        st.error("Masukkan kata kunci terlebih dahulu.")
    elif not apify_token:
        st.warning("Masukkan Apify API token di sidebar untuk mengambil data iklan secara otomatis. Anda tetap dapat membuka pencarian Meta atau mengimpor CSV/JSON.")
    else:
        url=make_meta_url(keyword.strip(), active=="Aktif saja", "video" if media=="Video" else "image" if media=="Gambar" else "all")
        st.session_state.query_url=url
        payload={"startUrls":[{"url":url}],"maxItems":int(limit)}
        endpoint="https://api.apify.com/v2/acts/apidojo~facebook-ads-scraper/run-sync-get-dataset-items"
        with st.spinner("Mengambil data dari Meta Ads Library melalui Apify. Proses dapat memerlukan waktu dan biaya sesuai tarif actor."):
            try:
                resp=requests.post(endpoint,params={"token":apify_token},json=payload,timeout=180)
                resp.raise_for_status()
                data=resp.json()
                if isinstance(data,dict) and "data" in data: data=data["data"]
                if not isinstance(data,list): raise ValueError("Format respons tidak dikenali: "+str(data)[:500])
                normalized=[normalize(x) for x in data if isinstance(x,dict)]
                # Focus filter
                if niche!="Semua produk digital":
                    terms={"Ebook":["ebook","e-book","buku digital","pdf"],"Kursus online":["kursus","kelas online","webinar","pelatihan"],"Template & worksheet":["template","worksheet","spreadsheet","canva"],"Membership / komunitas":["membership","komunitas","member"],"Software / tools":["software","aplikasi","tool","tools","saas"]}
                    keys=terms.get(niche,[])
                    normalized=[a for a in normalized if any(k in (a["body"]+" "+a["title"]).lower() for k in keys)]
                for a in normalized:
                    a["score"],a["reasons"]=score_ad(a)
                st.session_state.ads=normalized
                st.success(f"Data diterima: {len(normalized)} iklan. Hasil berasal dari konektor pihak ketiga; periksa tautan sumber setiap iklan.")
            except Exception as e:
                st.error(f"Pencarian gagal: {e}")
                st.info("Periksa token, kuota actor, koneksi internet, serta format input actor. Anda juga dapat mengimpor hasil JSON/CSV.")

st.divider()
st.subheader("📥 Impor hasil data")
uploaded=st.file_uploader("Unggah CSV atau JSON hasil riset iklan (opsional)", type=["csv","json"])
if uploaded:
    try:
        if uploaded.name.lower().endswith(".json"):
            raw=json.load(uploaded)
            if isinstance(raw,dict): raw=raw.get("data",raw.get("items",[raw]))
        else:
            raw=list(csv.DictReader(io.StringIO(uploaded.getvalue().decode("utf-8-sig"))))
        st.session_state.ads=[normalize(x) for x in raw if isinstance(x,dict)]
        for a in st.session_state.ads: a["score"],a["reasons"]=score_ad(a)
        st.success(f"{len(st.session_state.ads)} baris berhasil diimpor.")
    except Exception as e: st.error(f"Gagal membaca file: {e}")

ads=st.session_state.ads
if ads:
    if sort_mode=="Skor sinyal tertinggi": ads=sorted(ads,key=lambda x:x["score"],reverse=True)
    elif sort_mode=="Iklan terlama aktif": ads=sorted(ads,key=lambda x:x["days"],reverse=True)
    else: ads=sorted(ads,key=lambda x:x["advertiser"].lower())
    avg=round(sum(a["score"] for a in ads)/len(ads))
    long=sum(1 for a in ads if a["days"]>=30)
    m1,m2,m3,m4=st.columns(4)
    m1.metric("Iklan ditemukan",len(ads))
    m2.metric("Rata-rata skor sinyal",f"{avg}/100")
    m3.metric("Aktif ≥30 hari",long)
    m4.metric("Advertiser",len(set(a["advertiser"] for a in ads)))
    st.caption("Skor adalah prioritas riset berbasis sinyal yang terlihat, bukan skor viral resmi Meta dan bukan bukti iklan menghasilkan penjualan.")
    for idx,a in enumerate(ads):
        with st.container(border=True):
            top=st.columns([5,1])
            top[0].markdown(f"**{a['advertiser']}**  ·  `{a['id'] or 'ID tidak tersedia'}`")
            top[1].metric("Skor sinyal",f"{a['score']}/100")
            if a["title"]: st.markdown("**"+a["title"]+"**")
            st.write(a["body"][:900] if a["body"] else "_Teks iklan tidak tersedia pada respons._")
            st.caption(f"Mulai tayang: {a['start'] or 'Tidak tersedia'} · Durasi: {a['days']} hari (jika dapat dihitung) · Platform: {', '.join(map(str,a['platforms'])) or 'Tidak tersedia'}")
            st.markdown("**Alasan skor:** "+ " · ".join(a.get("reasons",[])))
            st.markdown(f"[Lihat iklan di Meta Ads Library]({a['link']})")
            with st.expander("Analisis kreatif"):
                h=heuristic_analysis(a)
                st.markdown("**Hook / pembuka terdeteksi**")
                st.write(h["hook"])
                st.markdown("**Pola copy**")
                st.write(", ".join(h["pola"]))
                st.markdown("**Sinyal penawaran:** "+h["penawaran"])
                st.markdown("**CTA:** "+h["cta"])
                st.info(h["saran"])
                if ai_key:
                    if st.button("✨ Analisis AI lebih mendalam",key=f"ai_{idx}"):
                        with st.spinner("AI sedang menganalisis..."):
                            st.write(ai_analysis(a,ai_key,ai_model))
    export=[{"id":a["id"],"advertiser":a["advertiser"],"title":a["title"],"body":a["body"],"start":a["start"],"days":a["days"],"score":a["score"],"url":a["link"]} for a in ads]
    st.download_button("⬇️ Unduh hasil sebagai JSON",json.dumps(export,ensure_ascii=False,indent=2),file_name="meta_ads_research.json",mime="application/json")
else:
    st.info("Belum ada data. Masukkan Apify token lalu klik Cari iklan nyata, atau impor file hasil pencarian.")
    st.markdown("**Kata kunci awal yang bisa dicoba:** `ebook`, `e-book`, `template canva`, `kelas online`, `jualan digital`, `prompt chatgpt`, `worksheet`, `digital product`.")

with st.expander("Tentang data, biaya, dan keterbatasan"):
    st.markdown("""
- Pencarian otomatis menggunakan actor pihak ketiga di Apify (`apidojo/facebook-ads-scraper`), bukan endpoint resmi Meta.
- Anda memerlukan akun/token Apify. Biaya, batas penggunaan, ketersediaan, dan ketentuan actor ditentukan penyedianya; periksa halaman actor sebelum menjalankan pencarian.
- Hasil yang dapat diambil bergantung pada apa yang tersedia di Meta Ads Library dan kemampuan actor. Tidak semua iklan/field pasti muncul.
- Durasi tayang panjang, variasi kreatif, dan copy yang kuat hanya sinyal untuk dipelajari. Data ini tidak membuktikan penjualan, omzet, ROAS, atau profit.
- Analisis lokal berjalan tanpa AI key. Analisis AI eksternal memerlukan OpenAI API key dan dapat dikenakan biaya API. Jangan masukkan data rahasia.
- Hindari menyalin iklan kompetitor secara langsung; gunakan temuan untuk mengembangkan materi orisinal.
""")
