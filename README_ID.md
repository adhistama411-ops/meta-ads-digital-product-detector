# Meta Ads Digital Product Detector

Aplikasi Streamlit untuk riset iklan produk digital/ebook di Meta Ads Library Indonesia.

## Cara paling aman untuk aplikasi online
1. Unggah folder proyek ini ke repository GitHub pribadi.
2. Deploy repository melalui Streamlit Community Cloud.
3. Di pengaturan aplikasi Streamlit Cloud, buka **Settings → Secrets**.
4. Tempel konfigurasi berikut di kolom Secrets (ganti teks contoh dengan token Anda):

   ```toml
   APIFY_API_TOKEN = "TOKEN_APIFY_ANDA"
   # Opsional untuk analisis AI:
   # OPENAI_API_KEY = "OPENAI_API_KEY_ANDA"
   ```
5. Simpan dan restart aplikasi. Aplikasi akan membaca token dari server secret; token tidak perlu dimasukkan ke halaman web.

**Jangan** mengirim token ke chat, memasukkannya ke source code, atau mengunggah file `secrets.toml` ke GitHub. File `secrets.toml.example` hanya contoh dan aman karena berisi placeholder.

## Koneksi data
- Actor pihak ketiga: https://apify.com/apidojo/facebook-ads-scraper
- Token Apify: https://console.apify.com/account/integrations
- Aplikasi memanggil actor dan mengambil hasil dataset. Ketersediaan, biaya, kuota, serta format data mengikuti actor Apify yang digunakan.

## Catatan hasil
Skor adalah pemeringkatan sinyal yang terlihat (misalnya lama tayang, variasi, dan materi iklan), bukan bukti penjualan, omzet, ROAS, atau viralitas. Meta Ads Library tidak menampilkan metrik penjualan komersial tersebut.

## Jalankan lokal (opsional)
```bash
pip install -r requirements.txt
streamlit run app.py
```
