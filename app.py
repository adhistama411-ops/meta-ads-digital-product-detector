
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
    "Sumber data: impor CSV/JSON, analisis landing page publik, dan Apify sebagai sumber tambahan. "
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
        "days_available": bool(start or getv(item, "daysActive", "days_active", default=None) is not None),
        "platforms": platforms,
        "ad_link": str(ad_link or ""),
        "destination": str(destination or ""),
        "cta": cta,
        "image": image,
        "category": detect_category(combined),
        "product": detect_product_name(title, body),
        "prices": detect_price(combined),
        "bonuses": detect_bonuses(combined),
        "source": clean_text(getv(item, "source", "data_source", default="Impor / sumber eksternal")),
        "raw": item
    }


# =====================================================
# 6. SKOR INDIKASI PEMASARAN
# =====================================================

def score_product(ad):
    score = 0
    reasons = []

    days = ad["days"]

    if not ad.get("days_available", False):
        reasons.append("Durasi iklan tidak tersedia; tidak diberi poin durasi")
    elif days >= 90:
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
# 6B. PRODUCT INTELLIGENCE ENGINE
# =====================================================

import unicodedata
from difflib import SequenceMatcher
from collections import defaultdict
from urllib.parse import urlparse, urljoin

STOPWORDS_PRODUCT = {
    "dan", "yang", "untuk", "dengan", "di", "ke", "dari", "the",
    "official", "resmi", "terbaru", "promo", "diskon", "murah",
    "limited", "edition", "produk", "digital", "beli", "sekarang"
}

def normalize_product_text(value):
    value = unicodedata.normalize("NFKD", clean_text(value).lower())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    tokens = [t for t in value.split() if t not in STOPWORDS_PRODUCT and len(t) > 1]
    return " ".join(tokens)

def product_domain(url):
    try:
        host = (urlparse(url).hostname or "").lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""

def extract_price_values(price_list):
    """Mengubah harga eksplisit menjadi angka IDR jika formatnya cukup jelas."""
    values = []
    for raw in price_list or []:
        s = clean_text(raw).lower().replace("rp", "").replace("idr", "").strip()
        s = s.replace(" ", "")
        multiplier = 1
        if s.endswith("rb"):
            multiplier, s = 1000, s[:-2]
        elif s.endswith("ribu"):
            multiplier, s = 1000, s[:-4]
        elif s.endswith("jt"):
            multiplier, s = 1000000, s[:-2]
        elif s.endswith("juta"):
            multiplier, s = 1000000, s[:-4]
        # Harga dengan pemisah ribuan: 99.000 / 99,000.
        if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", s):
            number = int(re.sub(r"[.,]", "", s))
        elif re.fullmatch(r"\d+(?:[.,]\d+)?", s):
            number = float(s.replace(",", "."))
        else:
            continue
        amount = int(number * multiplier)
        if 100 <= amount <= 2_000_000_000:
            values.append(amount)
    return sorted(set(values))

def build_product_groups(ad_list, similarity_threshold=0.84):
    """
    Mengelompokkan iklan yang kemungkinan mempromosikan produk sama.
    Pengelompokan berbasis nama/judul, domain tujuan, dan kategori.
    Ini indikasi kemiripan, bukan verifikasi identitas produk.
    """
    prepared = []
    for idx, ad in enumerate(ad_list):
        product = clean_text(ad.get("product", ""))
        title = clean_text(ad.get("title", ""))
        body = clean_text(ad.get("body", ""))
        # Judul produk mendapat prioritas; teks iklan menjadi cadangan.
        name_key = normalize_product_text(product if product and
                    product != "Nama produk belum teridentifikasi"
                    else title)
        if len(name_key) < 3:
            name_key = normalize_product_text(title + " " + body[:180])
        domain = product_domain(ad.get("destination", ""))
        prepared.append({
            "index": idx,
            "name": product or title or "Produk belum teridentifikasi",
            "key": name_key,
            "domain": domain,
            "category": ad.get("category", "Belum teridentifikasi"),
            "ad": ad
        })

    parent = list(range(len(prepared)))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(len(prepared)):
        a = prepared[i]
        if not a["key"]:
            continue
        for j in range(i + 1, len(prepared)):
            b = prepared[j]
            if not b["key"]:
                continue
            same_domain = bool(a["domain"] and a["domain"] == b["domain"])
            same_key = a["key"] == b["key"]
            similarity = SequenceMatcher(None, a["key"], b["key"]).ratio()
            token_a, token_b = set(a["key"].split()), set(b["key"].split())
            overlap = (len(token_a & token_b) / max(1, len(token_a | token_b)))
            same_category = (
                a["category"] == b["category"]
                and a["category"] != "Belum teridentifikasi"
            )
            # Domain sama + kategori sejalan merupakan sinyal kuat.
            match = same_key or (same_domain and (similarity >= 0.60 or overlap >= 0.50))
            if not match and same_category and similarity >= similarity_threshold:
                match = True
            if not match and similarity >= 0.93 and overlap >= 0.75:
                match = True
            if match:
                union(i, j)

    buckets = defaultdict(list)
    for i, item in enumerate(prepared):
        buckets[find(i)].append(item)

    groups = []
    for members in buckets.values():
        ads_in_group = [m["ad"] for m in members]
        names = [m["name"] for m in members
                 if m["name"] and m["name"] != "Nama produk belum teridentifikasi"]
        # Nama terpanjang sering lebih informatif, tetapi tidak dianggap pasti.
        display_name = max(names, key=len) if names else "Produk belum teridentifikasi"
        categories = [m["category"] for m in members
                      if m["category"] != "Belum teridentifikasi"]
        category = max(set(categories), key=categories.count) if categories else "Belum teridentifikasi"
        advertisers = sorted(set(
            a.get("advertiser", "") for a in ads_in_group
            if a.get("advertiser") and a.get("advertiser") != "Pengiklan tidak tersedia"
        ))
        domains = sorted(set(m["domain"] for m in members if m["domain"]))
        prices = sorted(set(
            price for a in ads_in_group
            for price in extract_price_values(a.get("prices", []))
        ))
        all_price_text = list(dict.fromkeys(
            p for a in ads_in_group for p in (a.get("prices") or [])
        ))
        scores = [int(a.get("score", 0) or 0) for a in ads_in_group]
        days = [int(a.get("days", 0) or 0) for a in ads_in_group
                if a.get("days_available", False)]
        ad_links = list(dict.fromkeys(a.get("ad_link", "") for a in ads_in_group if a.get("ad_link")))
        landing_pages = list(dict.fromkeys(a.get("destination", "") for a in ads_in_group if a.get("destination")))
        bonuses = list(dict.fromkeys(
            bonus for a in ads_in_group for bonus in (a.get("bonuses") or [])
        ))
        group_score = round(sum(scores) / len(scores)) if scores else 0
        # Confidence is confidence in grouping only, not product quality or sales.
        keys = [m["key"] for m in members if m["key"]]
        exact_keys = len(set(keys)) <= 1
        if len(members) == 1:
            match_confidence = "Belum dibandingkan"
        elif exact_keys:
            match_confidence = "Tinggi"
        else:
            match_confidence = "Perlu ditinjau"
        groups.append({
            "product": display_name,
            "category": category,
            "ad_count": len(ads_in_group),
            "advertiser_count": len(advertisers),
            "advertisers": advertisers,
            "domains": domains,
            "prices_numeric": prices,
            "prices_text": all_price_text,
            "price_min": min(prices) if prices else None,
            "price_max": max(prices) if prices else None,
            "bonuses": bonuses,
            "avg_signal_score": group_score,
            "max_signal_score": max(scores) if scores else 0,
            "max_observed_days": max(days) if days else None,
            "days_observed_count": len(days),
            "ad_links": ad_links,
            "landing_pages": landing_pages,
            "match_confidence": match_confidence,
            "ads": ads_in_group
        })

    return sorted(groups, key=lambda g: (g["avg_signal_score"], g["ad_count"]), reverse=True)

def format_idr(value):
    return "Rp" + f"{int(value):,}".replace(",", ".") if value is not None else "Tidak terdeteksi"


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

if "manual_page_result" not in st.session_state:
    st.session_state.manual_page_result = None


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
        st.warning(
            "Apify tidak dikonfigurasi. Anda tetap bisa melakukan riset melalui "
            "impor CSV/JSON dan Landing Page Analyzer di bawah."
        )

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
    "Unggah data iklan CSV atau JSON dari Apify, Meta Ads Library, atau sumber Anda sendiri",
    type=["csv", "json"]
)

if uploaded:

    try:
        if uploaded.name.lower().endswith(".json"):
            raw = json.load(uploaded)

            if isinstance(raw, dict):
                raw = raw.get(
                    "data",
                    raw.get("items", raw.get("ads", [raw]))
                )
                if isinstance(raw, dict):
                    raw = [raw]

        else:
            raw = list(csv.DictReader(
                io.StringIO(
                    uploaded.getvalue().decode("utf-8-sig")
                )
            ))

        if not isinstance(raw, list):
            raise ValueError("Data harus berupa daftar/baris iklan.")

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
# 11. ANALISIS LANDING PAGE MANDIRI (TANPA APIFY)
# =====================================================

st.divider()
st.subheader("🌐 Landing Page Analyzer — Mandiri")
st.caption(
    "Masukkan URL halaman penjualan publik untuk mendeteksi judul, deskripsi, "
    "kategori, harga, bonus, dan tautan checkout. Fitur ini tidak menggunakan Apify."
)
manual_url = st.text_input(
    "URL landing page", key="manual_landing_url",
    placeholder="https://contoh.com/halaman-penjualan"
)
if st.button("Analisis Landing Page", key="analyze_manual_page", type="primary"):
    if not manual_url.strip():
        st.warning("Masukkan URL landing page terlebih dahulu.")
    else:
        with st.spinner("Membaca halaman publik..."):
            st.session_state.manual_page_result = analyze_landing_page(manual_url.strip())

if st.session_state.get("manual_page_result"):
    result = st.session_state.manual_page_result
    if result.get("error"):
        st.error(result["error"])
    else:
        st.success("Halaman berhasil dianalisis.")
        st.write("**Judul:**", result.get("title") or "Tidak tersedia")
        st.write("**Deskripsi:**", result.get("description") or "Tidak tersedia")
        st.write("**Kategori:**", result.get("category") or "Belum teridentifikasi")
        st.write("**Harga terdeteksi:**", ", ".join(result.get("prices", [])) or "Tidak terdeteksi")
        st.write("**Bonus terdeteksi:**", ", ".join(result.get("bonuses", [])) or "Tidak terdeteksi")
        st.write("**Link checkout:**")
        if result.get("checkout_links"):
            for link in result["checkout_links"]:
                st.markdown(f"- [{link}]({link})")
        else:
            st.write("Belum ditemukan dari tautan HTML yang terbaca.")
        st.caption("Sumber: HTML halaman publik yang berhasil diakses; bukan verifikasi transaksi atau penjualan.")


# =====================================================
# 12. DASHBOARD HASIL
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

    # =================================================
    # PRODUCT INTELLIGENCE: PENGELOMPOKAN PRODUK
    # =================================================
    product_groups = build_product_groups(ads)
    st.divider()
    st.subheader("🧠 Product Intelligence")
    st.caption(
        "Iklan dikelompokkan berdasarkan kemiripan nama/judul, kategori, dan domain landing page. "
        "Pengelompokan adalah indikasi otomatis dan perlu pemeriksaan manual."
    )

    pi1, pi2, pi3, pi4 = st.columns(4)
    pi1.metric("Kelompok produk", len(product_groups))
    pi2.metric("Produk dengan >1 iklan", sum(1 for g in product_groups if g["ad_count"] > 1))
    pi3.metric("Pengiklan teridentifikasi", len(set(
        name for g in product_groups for name in g["advertisers"]
    )))
    pi4.metric("Kelompok perlu ditinjau", sum(
        1 for g in product_groups if g["match_confidence"] == "Perlu ditinjau"
    ))

    min_ads_filter = st.selectbox(
        "Filter jumlah iklan per kelompok",
        ["Semua", "Minimal 2 iklan", "Minimal 3 iklan"],
        key="pi_min_ads"
    )
    visible_groups = product_groups
    if min_ads_filter == "Minimal 2 iklan":
        visible_groups = [g for g in product_groups if g["ad_count"] >= 2]
    elif min_ads_filter == "Minimal 3 iklan":
        visible_groups = [g for g in product_groups if g["ad_count"] >= 3]

    for gi, group in enumerate(visible_groups):
        with st.container(border=True):
            header_cols = st.columns([4, 1, 1])
            header_cols[0].markdown(f"**{group['product']}**")
            header_cols[0].caption(
                f"{group['category']} · Pengelompokan: {group['match_confidence']}"
            )
            header_cols[1].metric("Jumlah iklan", group["ad_count"])
            header_cols[2].metric("Skor sinyal rata-rata", f"{group['avg_signal_score']}/100")

            details = st.columns(3)
            details[0].write("**Pengiklan**")
            details[0].write(", ".join(group["advertisers"]) or "Tidak tersedia")
            details[1].write("**Rentang harga terdeteksi**")
            if group["price_min"] is not None:
                details[1].write(
                    f"{format_idr(group['price_min'])} – {format_idr(group['price_max'])}"
                )
            else:
                details[1].write("Tidak ditemukan harga numerik yang dapat dibaca")
            details[2].write("**Durasi terlama teramati**")
            details[2].write(
                f"{group['max_observed_days']} hari"
                if group["max_observed_days"] is not None else "Tidak tersedia"
            )

            with st.expander("Rincian bukti dan iklan dalam kelompok"):
                st.write("**Teks harga yang ditemukan:**", ", ".join(group["prices_text"]) or "Tidak ada")
                st.write("**Bonus/penawaran yang terdeteksi:**", ", ".join(group["bonuses"]) or "Tidak ada")
                st.write("**Domain landing page:**", ", ".join(group["domains"]) or "Tidak tersedia")
                st.write("**Catatan:** skor sinyal adalah prioritas pemeriksaan berdasarkan data iklan, bukan estimasi penjualan atau profit.")
                for ad_no, member_ad in enumerate(group["ads"], start=1):
                    st.markdown(f"**Iklan {ad_no}:** {member_ad.get('advertiser', 'Pengiklan tidak tersedia')}")
                    st.caption(member_ad.get("title") or member_ad.get("body", "")[:240] or "Materi iklan tidak tersedia")
                    if member_ad.get("ad_link"):
                        st.markdown(f"[Lihat iklan]({member_ad['ad_link']})")
                    if member_ad.get("destination"):
                        st.markdown(f"[Landing page]({member_ad['destination']})")

    # Product-level CSV export
    product_export = []
    for group in product_groups:
        product_export.append({
            "product": group["product"],
            "category": group["category"],
            "ad_count": group["ad_count"],
            "advertiser_count": group["advertiser_count"],
            "advertisers": " | ".join(group["advertisers"]),
            "match_confidence": group["match_confidence"],
            "average_signal_score": group["avg_signal_score"],
            "max_observed_days": group["max_observed_days"],
            "price_min_idr": group["price_min"],
            "price_max_idr": group["price_max"],
            "observed_price_text": " | ".join(group["prices_text"]),
            "bonuses": " | ".join(group["bonuses"]),
            "landing_pages": " | ".join(group["landing_pages"]),
            "ad_links": " | ".join(group["ad_links"])
        })
    if product_export:
        pi_csv = io.StringIO()
        pi_writer = csv.DictWriter(pi_csv, fieldnames=list(product_export[0].keys()))
        pi_writer.writeheader()
        pi_writer.writerows(product_export)
        st.download_button(
            "⬇️ Ekspor Product Intelligence (CSV)",
            data=pi_csv.getvalue(),
            file_name="product_intelligence.csv",
            mime="text/csv",
            key="download_product_intelligence"
        )

    st.divider()
    st.subheader("🛍️ Detail iklan sumber")

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
            c.write(
                f"{ad['days']} hari" if ad.get("days_available", False)
                else "Tidak tersedia"
            )

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
    # 13. EKSPOR
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
            "days_active": ad["days"] if ad.get("days_available", False) else None,
        "source": ad.get("source", "Impor / sumber eksternal"),
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

    csv_buffer = io.StringIO()
    csv_writer = csv.DictWriter(
        csv_buffer,
        fieldnames=list(export[0].keys()) if export else []
    )
    if export:
        csv_writer.writeheader()
        for row in export:
            csv_writer.writerow({
                key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
                for key, value in row.items()
            })
    st.download_button(
        "⬇️ UNDUH HASIL RISET CSV",
        data=csv_buffer.getvalue(),
        file_name="product_research.csv",
        mime="text/csv"
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
# 14. INFORMASI DAN BATASAN
# =====================================================

with st.expander("ℹ️ Informasi dan keterbatasan aplikasi"):

    st.markdown("""
    1. Data iklan dapat berasal dari impor CSV/JSON milik pengguna; Apify hanya sumber tambahan.
    2. Hasil tergantung ketersediaan data dan kemampuan actor.
    3. Tidak semua iklan memiliki informasi harga atau landing page.
    4. Analisis landing page membaca HTML yang dapat diakses secara publik.
    5. Halaman yang menggunakan JavaScript kompleks mungkin tidak terbaca lengkap.
    6. Link checkout hanya dideteksi berdasarkan tautan yang terlihat.
    7. Skor merupakan prioritas riset berdasarkan indikator yang ditemukan.
    8. Skor bukan bukti penjualan, omzet, ROAS, atau keuntungan.
    9. Pastikan penggunaan Apify dan pengambilan data sesuai ketentuan penyedia.
    10. Landing Page Analyzer bekerja tanpa Apify, tetapi hanya membaca HTML publik yang dapat diakses.
    11. Harga dan bonus yang terdeteksi adalah teks yang ditemukan pada halaman, bukan konfirmasi harga checkout akhir.
    12. Product Intelligence mengelompokkan iklan berdasarkan kemiripan nama/judul, kategori, dan domain; hasilnya bukan kepastian bahwa produknya identik.
    13. Rentang harga hanya dihitung dari pola harga yang berhasil diparse sebagai angka; teks harga asli tetap disimpan sebagai bukti.
    14. Skor kelompok adalah rata-rata skor sinyal iklan dalam kelompok, bukan prediksi omzet, penjualan, ROAS, atau profit.
    """)