
import streamlit as st
import requests
import json
import re
import csv
import io
import ipaddress
import socket
from html.parser import HTMLParser
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse

st.set_page_config(
    page_title="Meta Ads Product Detector",
    page_icon="🔎",
    layout="wide"
)

# =====================================================
# 1. TAMPILAN
# =====================================================

st.markdown("""
<style>
.main {background:#f5f7fb}
.block-container {padding-top:1.5rem;max-width:1450px}
.hero {
    padding:28px;
    border-radius:18px;
    background:linear-gradient(120deg,#111827,#244879);
    color:white;
}
.metric {
    background:white;
    border:1px solid #e5e7eb;
    border-radius:14px;
    padding:14px;
}
div[data-testid="stMetric"] {
    background:white;
    padding:14px;
    border-radius:12px;
    border:1px solid #e5e7eb;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
<h1>🔎 META ADS PRODUCT DETECTOR</h1>
<p>DIGITAL PRODUCT RESEARCH DASHBOARD</p>
<p>Temukan produk digital yang aktif dipasarkan dan analisis indikasi potensi pasarnya.</p>
</div>
""", unsafe_allow_html=True)

st.caption(
    "Sumber: Meta Ads Library publik melalui Apify. "
    "Data penjualan aktual kompetitor tidak tersedia."
)

# =====================================================
# 2. KONEKSI DAN PENGATURAN
# =====================================================

with st.sidebar:
    st.header("⚙️ Pengaturan koneksi")

    try:
        apify_secret = st.secrets.get("APIFY_API_TOKEN", "")
    except Exception:
        apify_secret = ""

    if apify_secret:
        apify_token = apify_secret
        st.success("Apify terhubung melalui Secrets.")
    else:
        apify_token = st.text_input(
            "Apify API Token",
            type="password"
        )

    st.markdown(
        "[Pengaturan token Apify](https://console.apify.com/account/integrations)"
    )

    st.divider()
    st.subheader("Pengaturan pencarian")

    country = st.selectbox(
        "Negara iklan",
        ["Indonesia", "United States", "Malaysia", "Singapore"],
        index=0
    )

    country_codes = {
        "Indonesia": "ID",
        "United States": "US",
        "Malaysia": "MY",
        "Singapore": "SG"
    }

    st.caption("Analisis landing page menggunakan pembacaan HTML dasar.")
    st.caption("Tidak membutuhkan OpenAI API.")

# =====================================================
# 3. FORM PENCARIAN
# =====================================================

st.subheader("🔍 Product Research")

col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    keyword = st.text_input(
        "Kata kunci produk",
        value="ebook bisnis"
    )

with col2:
    active = st.selectbox(
        "Status iklan",
        ["Aktif saja", "Semua status"]
    )

with col3:
    limit = st.select_slider(
        "Jumlah iklan",
        options=[10, 20, 30, 50, 100],
        value=30
    )

c1, c2, c3 = st.columns(3)

with c1:
    niche = st.selectbox(
        "Kategori produk",
        [
            "Semua produk digital",
            "E-book",
            "Kursus online",
            "Template",
            "Aplikasi / Software",
            "Membership",
            "Tools digital"
        ]
    )

with c2:
    media = st.selectbox(
        "Format iklan",
        ["Semua format", "Video", "Gambar"]
    )

with c3:
    sort_mode = st.selectbox(
        "Urutan hasil",
        [
            "Skor potensi tertinggi",
            "Iklan terlama aktif",
            "Nama pengiklan"
        ]
    )

# =====================================================
# 4. FUNGSI DASAR
# =====================================================

def getv(item, *keys, default=""):
    if not isinstance(item, dict):
        return default

    for key in keys:
        value = item.get(key)
        if value not in (None, "", [], {}):
            return value

    return default


def make_meta_url(query, active_only=True, media_type="all"):
    params = {
        "active_status": "active" if active_only else "all",
        "ad_type": "all",
        "country": country_codes[country],
        "q": query,
        "search_type": "keyword_unordered",
        "media_type": media_type
    }

    return (
        "https://www.facebook.com/ads/library/?"
        + urlencode(params)
    )


def clean_text(value):
    if isinstance(value, list):
        value = " ".join(map(str, value))

    if not isinstance(value, str):
        value = str(value or "")

    return re.sub(r"\s+", " ", value).strip()


def detect_category(text):
    text = text.lower()

    categories = {
        "E-book": [
            "ebook", "e-book", "buku digital", "pdf", "buku elektronik"
        ],
        "Kursus online": [
            "kursus", "kelas online", "webinar",
            "pelatihan", "training", "bootcamp"
        ],
        "Template": [
            "template", "worksheet", "canva",
            "spreadsheet", "notion template"
        ],
        "Aplikasi / Software": [
            "software", "aplikasi", "saas",
            "tools", "tool digital"
        ],
        "Membership": [
            "membership", "komunitas berbayar",
            "akses member", "langganan"
        ]
    }

    for category, words in categories.items():
        if any(word in text for word in words):
            return category

    return "Belum teridentifikasi"


def detect_price(text):
    patterns = [
        r"Rp\.?\s?[\d.,]+",
        r"IDR\s?[\d.,]+",
        r"\b\d{1,3}(?:[.,]\d{3})+\s?(?:ribu)?\b",
        r"\b\d+\s?rb\b"
    ]

    found = []

    for pattern in patterns:
        matches = re.findall(pattern, text, re.I)
        found.extend(matches)

    return list(dict.fromkeys(found))[:5]


def detect_bonuses(text):
    words = [
        "bonus", "gratis", "free",
        "ebook bonus", "template bonus",
        "akses gratis", "materi tambahan",
        "video tutorial"
    ]

    text = text.lower()

    return [
        word for word in words if word in text
    ]


def detect_product_name(title, body):
    title = clean_text(title)
    body = clean_text(body)

    if title and len(title) > 3:
        return title[:120]

    if body:
        sentences = re.split(r"[.!?\n]", body)

        for sentence in sentences:
            sentence = sentence.strip()

            if 8 < len(sentence) < 100:
                return sentence[:120]

    return "Nama produk belum teridentifikasi"


# =====================================================
# 5. MEMBACA DATA IKLAN
# =====================================================

def normalize(item):
    body = clean_text(getv(
        item,
        "bodyText",
        "ad_creative_bodies",
        "body",
        "text",
        "adText"
    ))

    title = clean_text(getv(
        item,
        "title",
        "headline",
        "ad_creative_link_titles"
    ))

    advertiser = clean_text(getv(
        item,
        "pageName",
        "page_name",
        "advertiserName",
        "name",
        default="Pengiklan tidak tersedia"
    ))

    start = getv(
        item,
        "startDate",
        "ad_delivery_start_time",
        "startedAt",
        "start_date"
    )

    days = getv(
        item,
        "daysActive",
        "days_active",
        default=None
    )

    try:
        if days is None and start:
            dt = datetime.fromisoformat(
                str(start).replace("Z", "+00:00")
            )

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            days = (
                datetime.now(timezone.utc) - dt
            ).days

        days = max(0, int(days or 0))

    except (ValueError, TypeError, OverflowError):
        days = 0

    platforms = getv(
        item,
        "publisherPlatforms",
        "publisher_platforms",
        "platforms",
        default=[]
    )

    if isinstance(platforms, str):
        platforms = [platforms]

    ad_id = getv(
        item,
        "adArchiveId",
        "id",
        "adId"
    )

    ad_link = getv(
        item,
        "adLibraryUrl",
        "ad_library_url",
        "ad_snapshot_url"
    )

    if not ad_link and ad_id:
        ad_link = (
            "https://www.facebook.com/ads/library/?id="
            + str(ad_id)
        )

    destination = getv(
        item,
        "landingPageUrl",
        "landing_page_url",
        "websiteUrl",
        "website_url",
        "destinationUrl",
        "destination_url",
        "linkUrl",
        "link_url"
    )

    # Jangan menganggap link Meta Ads Library sebagai landing page.
    if not destination:
        possible_link = getv(item, "link", "url")
        if (
            isinstance(possible_link, str)
            and possible_link.startswith("http")
            and "facebook.com/ads/library" not in possible_link
        ):
            destination = possible_link

    images = getv(
        item,
        "images",
        "imageUrls",
        "image_urls",
        default=[]
    )

    image = ""

    if isinstance(images, list) and images:
        first = images[0]
        image = (
            first if isinstance(first, str)
            else getv(first, "url", "src")
        )

    cta = clean_text(getv(
        item,
        "ctaText",
        "cta_type",
        "ctaType",
        "callToAction"
    ))

    if isinstance(item.get("callToAction"), dict):
        cta = str(item["callToAction"])

    combined = title + " " + body

    return {
        "id": str(ad_id or ""),
        "advertiser": advertiser,
        "title": title,
        "body": body,
        "start": str(start or ""),
        "days": days,
        "platforms": platforms,
        "ad_link": str(ad_link or ""),
        "destination": str(destination or ""),
        "cta": cta,
        "image": image,
        "category": detect_category(combined),
        "product": detect_product_name(title, body),
        "prices": detect_price(combined),
        "bonuses": detect_bonuses(combined),
        "raw": item
    }


# =====================================================
# 6. SKOR INDIKASI PEMASARAN
# =====================================================

def score_product(ad):
    score = 0
    reasons = []

    days = ad["days"]

    if days >= 90:
        score += 30
        reasons.append("Iklan terdeteksi aktif ≥90 hari")
    elif days >= 45:
        score += 23
        reasons.append("Iklan terdeteksi aktif 45–89 hari")
    elif days >= 14:
        score += 15
        reasons.append("Iklan terdeteksi aktif 14–44 hari")
    elif days >= 7:
        score += 8
        reasons.append("Iklan terdeteksi aktif 7–13 hari")

    raw = ad["raw"]

    variants = getv(
        raw,
        "collationCount",
        "variantCount",
        "creativeCount",
        default=0
    )

    try:
        variants = int(variants)
    except (ValueError, TypeError):
        variants = 0

    if variants >= 5:
        score += 20
        reasons.append("Banyak variasi kreatif terdeteksi")
    elif variants >= 2:
        score += 12
        reasons.append("Ada beberapa variasi kreatif")

    if ad["destination"]:
        score += 15
        reasons.append("Landing page terdeteksi")

    if ad["prices"]:
        score += 10
        reasons.append("Informasi harga terdeteksi")

    if ad["category"] != "Belum teridentifikasi":
        score += 10
        reasons.append("Kategori produk teridentifikasi")

    if ad["bonuses"]:
        score += 5
        reasons.append("Ada indikasi bonus atau insentif")

    if ad["cta"]:
        score += 5
        reasons.append("CTA tersedia")

    if ad["body"] and len(ad["body"]) > 100:
        score += 5
        reasons.append("Materi iklan cukup lengkap")

    return min(score, 100), reasons


# =====================================================
# 7. ANALISIS LANDING PAGE
# =====================================================

class PageParser(HTMLParser):

    def __init__(self):
        super().__init__()
        self.title = False
        self.in_title = False
        self.title_text = []
        self.text = []
        self.meta = {}
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "title":
            self.in_title = True

        if tag == "meta":
            key = attrs.get("property") or attrs.get("name")
            value = attrs.get("content")

            if key and value:
                self.meta[key.lower()] = value

        if tag == "a":
            href = attrs.get("href", "")
            text = attrs.get("aria-label", "")

            if href:
                self.links.append((href, text))

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        data = data.strip()

        if data:
            self.text.append(data)

            if self.in_title:
                self.title_text.append(data)


def safe_public_url(url):
    try:
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            return False

        if not parsed.hostname:
            return False

        hostname = parsed.hostname.lower()

        if hostname in ("localhost", "localhost.localdomain"):
            return False

        try:
            addresses = socket.getaddrinfo(
                hostname, None
            )

            for address in addresses:
                ip = ipaddress.ip_address(address[4][0])

                if not ip.is_global:
                    return False

        except socket.gaierror:
            return False

        return True

    except Exception:
        return False


def analyze_landing_page(url):
    if not safe_public_url(url):
        return {
            "error": "URL tidak valid atau bukan alamat publik."
        }

    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; ProductResearch/1.0)"
                )
            },
            timeout=20,
            allow_redirects=True
        )

        if not safe_public_url(response.url):
            return {"error": "Alamat tujuan redirect tidak diizinkan."}

        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type", ""
        ).lower()

        if "html" not in content_type:
            return {
                "error": "Halaman tujuan bukan dokumen HTML."
            }

        parser = PageParser()
        parser.feed(response.text[:1500000])

        page_title = (
            parser.meta.get("og:title")
            or " ".join(parser.title_text)
            or "Judul tidak ditemukan"
        )

        description = (
            parser.meta.get("og:description")
            or parser.meta.get("description")
            or ""
        )

        text = " ".join(parser.text)
        combined = page_title + " " + description + " " + text

        prices = detect_price(combined)
        bonuses = detect_bonuses(combined)
        category = detect_category(combined)

        checkout_words = [
            "checkout", "order", "pesan",
            "beli", "payment", "pembayaran",
            "cart", "keranjang"
        ]

        checkout_links = []

        for href, label in parser.links:
            target = (href + " " + label).lower()

            if any(word in target for word in checkout_words):
                checkout_links.append(href)

        return {
            "url": response.url,
            "title": page_title[:200],
            "description": description[:500],
            "category": category,
            "prices": prices,
            "bonuses": bonuses,
            "checkout_links": list(dict.fromkeys(
                checkout_links
            ))[:10],
            "text_length": len(text),
            "error": ""
        }

    except requests.RequestException as e:
        return {"error": "Gagal membaca halaman: " + str(e)}
    except Exception as e:
        return {"error": "Analisis gagal: " + str(e)}


# =====================================================
# 8. SESSION STATE
# =====================================================

if "ads" not in st.session_state:
    st.session_state.ads = []

if "query_url" not in st.session_state:
    st.session_state.query_url = ""

if "page_results" not in st.session_state:
    st.session_state.page_results = {}


# =====================================================
# 9. PENCARIAN APIFY
# =====================================================

left, right = st.columns(2)

with left:
    search_btn = st.button(
        "🔎 CARI IKLAN NYATA",
        type="primary",
        use_container_width=True
    )

with right:
    st.link_button(
        "Buka Meta Ads Library",
        make_meta_url(
            keyword,
            active == "Aktif saja",
            "video" if media == "Video"
            else "image" if media == "Gambar"
            else "all"
        ),
        use_container_width=True
    )

if search_btn:

    if not keyword.strip():
        st.error("Masukkan kata kunci.")

    elif not apify_token:
        st.warning("Masukkan Apify API Token terlebih dahulu.")

    else:
        url = make_meta_url(
            keyword.strip(),
            active == "Aktif saja",
            "video" if media == "Video"
            else "image" if media == "Gambar"
            else "all"
        )

        st.session_state.query_url = url

        payload = {
            "startUrls": [{"url": url}],
            "maxItems": int(limit)
        }

        endpoint = (
            "https://api.apify.com/v2/acts/"
            "apidojo~facebook-ads-scraper/"
            "run-sync-get-dataset-items"
        )

        with st.spinner("Mengambil data iklan dari Apify..."):

            try:
                response = requests.post(
                    endpoint,
                    params={"token": apify_token},
                    json=payload,
                    timeout=180
                )

                response.raise_for_status()
                data = response.json()

                if isinstance(data, dict):
                    data = data.get(
                        "data",
                        data.get("items", [])
                    )

                if not isinstance(data, list):
                    raise ValueError(
                        "Format hasil Apify tidak dikenali: "
                        + str(data)[:300]
                    )

                normalized = [
                    normalize(item)
                    for item in data
                    if isinstance(item, dict)
                ]

                if niche != "Semua produk digital":

                    category_map = {
                        "E-book": "E-book",
                        "Kursus online": "Kursus online",
                        "Template": "Template",
                        "Aplikasi / Software": "Aplikasi / Software",
                        "Membership": "Membership",
                        "Tools digital": "Aplikasi / Software"
                    }

                    target = category_map[niche]

                    normalized = [
                        ad for ad in normalized
                        if ad["category"] == target
                    ]

                for ad in normalized:
                    ad["score"], ad["reasons"] = score_product(ad)

                st.session_state.ads = normalized
                st.session_state.page_results = {}

                st.success(
                    f"Berhasil menerima {len(normalized)} iklan."
                )

            except requests.RequestException as e:
                st.error("Koneksi Apify gagal: " + str(e))

            except Exception as e:
                st.error("Terjadi kesalahan: " + str(e))


# =====================================================
# 10. IMPOR DATA
# =====================================================

st.divider()
st.subheader("📥 Impor hasil riset")

uploaded = st.file_uploader(
    "Unggah hasil CSV atau JSON dari Apify",
    type=["csv", "json"]
)

if uploaded:

    try:
        if uploaded.name.lower().endswith(".json"):
            raw = json.load(uploaded)

            if isinstance(raw, dict):
                raw = raw.get(
                    "data",
                    raw.get("items", [raw])
                )

        else:
            raw = list(csv.DictReader(
                io.StringIO(
                    uploaded.getvalue().decode("utf-8-sig")
                )
            ))

        imported = [
            normalize(item)
            for item in raw
            if isinstance(item, dict)
        ]

        for ad in imported:
            ad["score"], ad["reasons"] = score_product(ad)

        st.session_state.ads = imported
        st.session_state.page_results = {}

        st.success(
            f"{len(imported)} iklan berhasil diimpor."
        )

    except Exception as e:
        st.error("Gagal mengimpor data: " + str(e))


# =====================================================
# 11. DASHBOARD HASIL
# =====================================================

ads = st.session_state.ads

if ads:

    if sort_mode == "Skor potensi tertinggi":
        ads = sorted(
            ads,
            key=lambda x: x["score"],
            reverse=True
        )

    elif sort_mode == "Iklan terlama aktif":
        ads = sorted(
            ads,
            key=lambda x: x["days"],
            reverse=True
        )

    else:
        ads = sorted(
            ads,
            key=lambda x: x["advertiser"].lower()
        )

    products = set(
        ad["product"].lower()
        for ad in ads
        if ad["product"] != "Nama produk belum teridentifikasi"
    )

    priced = sum(1 for ad in ads if ad["prices"])
    landing = sum(1 for ad in ads if ad["destination"])
    long_ads = sum(1 for ad in ads if ad["days"] >= 30)

    st.divider()
    st.subheader("📊 Ringkasan penelitian")

    m1, m2, m3, m4 = st.columns(4)

    m1.metric("Iklan ditemukan", len(ads))
    m2.metric("Nama produk terdeteksi", len(products))
    m3.metric("Harga terdeteksi", priced)
    m4.metric("Landing page ditemukan", landing)

    st.caption(
        f"{long_ads} iklan memiliki durasi terhitung minimal 30 hari. "
        "Ini merupakan indikator aktivitas, bukan bukti penjualan."
    )

    st.divider()
    st.subheader("🛍️ Hasil riset produk")

    for index, ad in enumerate(ads):

        with st.container(border=True):

            top = st.columns([4, 1])

            top[0].markdown(
                f"**{ad['product']}**"
            )

            top[0].caption(
                f"Pengiklan: {ad['advertiser']}"
            )

            top[1].metric(
                "Skor riset",
                f"{ad['score']}/100"
            )

            st.write(
                ad["body"][:700]
                if ad["body"]
                else "Teks iklan tidak tersedia."
            )

            a, b, c = st.columns(3)

            a.write("**Kategori**")
            a.write(ad["category"])

            b.write("**Harga terdeteksi**")
            b.write(
                ", ".join(ad["prices"])
                if ad["prices"]
                else "Belum ditemukan"
            )

            c.write("**Durasi iklan**")
            c.write(f"{ad['days']} hari")

            st.write("**Bonus / penawaran**")

            st.write(
                ", ".join(ad["bonuses"])
                if ad["bonuses"]
                else "Belum terdeteksi"
            )

            st.write("**Landing page**")

            if ad["destination"]:
                st.markdown(
                    f"[Buka halaman tujuan]({ad['destination']})"
                )
            else:
                st.write("Belum ditemukan pada data iklan.")

            st.caption(
                "Alasan skor: " + " · ".join(ad["reasons"])
            )

            if ad["ad_link"]:
                st.markdown(
                    f"[Lihat iklan di Meta Ads Library]({ad['ad_link']})"
                )

            if ad["destination"]:

                button_key = f"analyze_{index}_{ad['id']}"

                if st.button(
                    "🌐 Analisis landing page",
                    key=button_key
                ):

                    with st.spinner("Membaca landing page..."):

                        result = analyze_landing_page(
                            ad["destination"]
                        )

                        st.session_state.page_results[
                            ad["id"] or str(index)
                        ] = result

                result = st.session_state.page_results.get(
                    ad["id"] or str(index)
                )

                if result:

                    if result.get("error"):
                        st.warning(result["error"])

                    else:
                        st.markdown("**Hasil analisis halaman**")

                        st.write(
                            "Nama halaman:",
                            result["title"]
                        )

                        st.write(
                            "Deskripsi:",
                            result["description"] or "Tidak tersedia"
                        )

                        st.write(
                            "Kategori:",
                            result["category"]
                        )

                        st.write(
                            "Harga:",
                            ", ".join(result["prices"])
                            if result["prices"]
                            else "Tidak terdeteksi"
                        )

                        st.write(
                            "Bonus:",
                            ", ".join(result["bonuses"])
                            if result["bonuses"]
                            else "Tidak terdeteksi"
                        )

                        st.write("**Link checkout yang terdeteksi**")

                        if result["checkout_links"]:
                            for link in result["checkout_links"]:
                                st.markdown(f"[Buka link]({link})")
                        else:
                            st.write(
                                "Belum ditemukan link checkout."
                            )

    # =================================================
    # 12. EKSPOR
    # =================================================

    export = []

    for ad in ads:
        export.append({
            "id": ad["id"],
            "advertiser": ad["advertiser"],
            "product": ad["product"],
            "category": ad["category"],
            "prices": ad["prices"],
            "bonuses": ad["bonuses"],
            "days_active": ad["days"],
            "score": ad["score"],
            "landing_page": ad["destination"],
            "ad_library": ad["ad_link"],
            "cta": ad["cta"]
        })

    st.divider()

    st.download_button(
        "⬇️ UNDUH HASIL RISET JSON",
        data=json.dumps(
            export,
            ensure_ascii=False,
            indent=2
        ),
        file_name="product_research.json",
        mime="application/json"
    )

else:

    st.info(
        "Belum ada hasil penelitian. "
        "Masukkan kata kunci lalu klik Cari Iklan Nyata."
    )

    st.markdown("""
    **Contoh kata kunci untuk memulai:**

    - ebook bisnis
    - template Canva
    - kelas digital marketing
    - worksheet anak
    - aplikasi kasir
    - prompt AI
    - panduan jualan online
    """)

# =====================================================
# 13. INFORMASI DAN BATASAN
# =====================================================

with st.expander("ℹ️ Informasi dan keterbatasan aplikasi"):

    st.markdown("""
    1. Data iklan berasal dari Meta Ads Library melalui actor pihak ketiga Apify.
    2. Hasil tergantung ketersediaan data dan kemampuan actor.
    3. Tidak semua iklan memiliki informasi harga atau landing page.
    4. Analisis landing page membaca HTML yang dapat diakses secara publik.
    5. Halaman yang menggunakan JavaScript kompleks mungkin tidak terbaca lengkap.
    6. Link checkout hanya dideteksi berdasarkan tautan yang terlihat.
    7. Skor merupakan prioritas riset berdasarkan indikator yang ditemukan.
    8. Skor bukan bukti penjualan, omzet, ROAS, atau keuntungan.
    9. Pastikan penggunaan Apify dan pengambilan data sesuai ketentuan penyedia.
    """)
