# Türkiye'nin Sınıraşan Suları

> **Sınıraşan ve Ulusal Nehir Havzaları İnteraktif Coğrafi Bilgi Sistemi (CBS), Hidroloji ve Taşkın Erken Uyarı Platformu**

🌐 **Canlı Uygulama (GitHub Pages):** [https://mserman90.github.io/turkiyenin-sinirasan-sulari/](https://mserman90.github.io/turkiyenin-sinirasan-sulari/)

---

## 📌 Proje Genel Bakış

**Türkiye'nin Sınıraşan Suları**, Türkiye'nin komşu ülkelerle paylaştığı stratejik akarsu sistemlerini (Dicle-Fırat, Aras-Kura, Çoruh, Meriç-Ergene ve Asi) ve ulusal 25 su havzasını hidrolojik, kartografik, meteorolojik ve taşkın risk odaklarıyla haritalandıran açık kaynaklı, bağımsız bir Coğrafi Bilgi Sistemi (CBS) web uygulamasıdır.

Bu platform; gerçek zamanlı uydu meteorolojisini, küresel hidrolojik taşkın debisi modellerini, Taşkın Yönetim Planları (TYP) hidrodinamik simülasyon sonuçlarını ve içme suyu altyapı envanterlerini tek bir interaktif kartografik tuval üzerinde birleştirir.

---

## 🚀 Temel Özellikler

### 1. Kartografik ve CBS Harita Altyapısı
* **Esri ArcGIS Online Altlık Motoru (Sıfır API Key Maliyeti):**
  * *Esri World Topographic* (Varsayılan topoğrafik harita)
  * *Esri World Imagery* (Yüksek çözünürlüklü uydu görüntüsü)
  * *Esri World Street Map*
  * *Esri National Geographic*
  * *Esri Shaded Relief* (Kabartma / Vadi morfolojisi)
  * *Esri World Physical & Terrain Base*
* **Sınıraşan Havza Hızlı Filtreleri:**
  * 🌐 Tüm Sınıraşan Sular
  * 🇮🇶 Dicle - Fırat Havzası (21)
  * 🇦🇿 Aras - Kura Havzası (24)
  * 🇬🇪 Çoruh Havzası (23)
  * 🇧🇬 Meriç (1) & Asi (19) Havzaları

### 2. Canlı Meteoroloji ve Doğal Afet Erken Uyarı Sistemi (OpenWeather API)
* **5 Canlı Radar Katmanı (Leaflet TileLayers):**
  * 🌧️ **Canlı Yağış Radarı (`precipitation_new`):** Anlık yağmur ve kar fırtınası cepheleri.
  * ☁️ **Canlı Bulut Örtüsü (`clouds_new`):** Uydu bazlı bulut kapalılık oranı (%).
  * 🌡️ **Termal Sıcaklık Katmanı (`temp_new`):** Yüzey sıcaklığı ve kar erimesi koşulları.
  * 💨 **Rüzgar Şiddeti (`wind_new`):** Fırtına hatları.
  * 🌀 **Atmosferik Basınç (`pressure_new`):** İzobarlar ve siklon merkezleri.
* **Akıllı Tıklama Modu (`crosshair`):** Harita üzerinde herhangi bir nehir, baraj veya sınır noktasına tıklandığında anlık sıcaklık, nem, rüzgar, basınç ve afet risk seviyesini otomatik hesaplar.
* **24 Saatlik Tahmin Çizelgesi:** 3 saatlik adımlarla yağış ihtimali (`pop %`), sıcaklık ve rüzgar grafiği.

### 3. Küresel Akarsu Debisi ve Taşkın Erken Uyarısı (Open-Meteo Flood API)
* **Copernicus GloFAS v4.0 & ECMWF Hidrolojik Modeli:**
  * Koordinat bazlı anlık modellenen akarsu debisi ($m^3/s$).
  * 7 günlük ileriye dönük maksimum tepe (pik) debi ($Q_{max}$) tahmini.
  * Dinamik trend tespiti (↗ Yükseliş, ↘ Azalış, → Durgun/Stabil).
  * SVG/CSS mikro sparkline çubuk hidroğrafı ve günlük detaylı tahmin tablosu.

### 4. Taşkın Yönetim Planları (TYP) ve Hidrodinamik Risk Odakları
* **Dicle - Fırat:** Şanlıurfa (227P), Birecik (207P), Mardin Kızıltepe (193P), Ağrı (188P), Gaziantep (160P), Sivas Gürün (126P), Batman (112P), Bismil (107P), Yüksekova (103P) risk rozetleri ve önlemleri.
* **Doğu Karadeniz (22):** Rize (172P), Giresun (122P), Tirebolu (101P), Araklı (82P), Sürmene (75P), Hopa (65P), Çayeli (58P) taşkın odakları ve sel tırmığı/süzücü bent eylemleri.
* **Çoruh (23):** Bayburt (46P), Oltu (43P), Borçka (31P), Muratlı (18P) sınır kesiti.
* **Asi (19):** Reyhanlı (169P), Antakya (168P), Karasüleymanlı & Kumlu (147P), Amik Kurutma Kanalı, Afrin Çayı.
* **Seyhan (18):** Adana Metropolü (338P), Seyhan (190P), Yenice (88P), Pozantı (40P).
* **Ceyhan (20):** Kahramanmaraş, Türkoğlu ve Çukurova deltası.

### 5. USBS (Ulusal Su Bilgi Sistemi) Canlı CBS & Taşkın Modelleri
* **25 Havza Sınırları & Nehir Ağı:** Esri ArcGIS Server REST export motoru ve `no-referrer` mimarisiyle canlı çekilen dinamik havza poligonları ve Strahler nehir hiyerarşisi.
* **Sınıraşan Havzalar Vektör Sınırı (GeoJSON):** Dicle-Fırat, Aras-Kura, Çoruh, Meriç ve Asi havzalarının resmi 1:25.000 sayısallaştırma vektör sınırları ve anlık öznitelik sorgulaması (resmi alan km², havza kodu, havza no).
* **Taşkın Genel Risk Haritası Q100:** 100 yıllık tekerrür debisine göre modellenmiş taşkın yayılım alanları.
* **Taşkın Tehlike & Su Derinliği:** HEC-RAS 2D hidrodinamik modellerinden türetilmiş su derinliği haritaları.
* **TYP Yönetim Planı Tedbirleri:** Menfez, süzücü bent, sedde ve ıslah yapısal eylem tedbirleri.

### 6. Su Altyapısı ve Araçlar
* **İçme Suyu Kaynakları & Arıtma Tesisleri (TR-İAT):** Baraj, gölet, kuyu, dere ve arıtma tesisleri envanteri.
* **Mesafe Ölçüm Cetveli:** Akarsu yatakları ve sınır mesafelerini anlık hesaplama.
* **GeoJSON Dışa Aktarımı:** CBS katmanlarını doğrudan QGIS veya ArcGIS için indirme.
* **A0 / A1 Yüksek Çözünürlüklü Kartografik Baskı Modu.**

---

## 🛠️ Depo İçeriği ve Python Analiz Araçları

* `index.html`: Web GIS uygulamasının tek dosya, sıfır derleme gerektiren ana kaynak kodu.
* `leaflet.js` & `leaflet.css`: Leaflet kütüphanesi yerel kopyası (CDN kesintilerine karşı çevrimdışı yedekli).
* `open_meteo_flood_api.py`: Python standart kütüphaneleriyle yazılmış bağımsız CLI aracı. 7 günlük akarsu debisi çeker, terminalde ASCII çubuk hidroğrafı ve biçimlendirilmiş tablo basar.
* `gpm_imerg_download.py`: NASA CMR API üzerinden Türkiye sınırları için GPM IMERG (Early, Late, Final) yağış granule'larını arayan ve kalibrasyon kurallarını uygulayan CLI aracı.
* `usbs_data_extractor.py`: USBS ArcGIS Server REST servislerinden havza ve taşkın modellerini sorgulayan ve GeoJSON dışa aktaran Python aracı.
* `turkiye_sinirasan_havzalar_usbs.geojson`: Sınıraşan 5 havzamızın 10.97 MB optimize edilmiş yüksek çözünürlüklü vektör poligon sınırları.
* `turkiye_sinirasan_havzalar_web.geojson`: Web harita için 2.19 MB ultra hızlı yüklenen sınıraşan havza vektör sınırları.
* `iat_sorgulama.csv`: İçme Suyu Arıtma Tesisleri ve kaynak veritabanı.

---

## 💻 Python Araçlarını Çalıştırma

### Akarsu Debisi ve Taşkın Tahmini:
```bash
# Cizre / Dicle Nehri varsayılan tahmini
python open_meteo_flood_api.py

# Belirli bir istasyon seçimi (cizre, birecik, kars, rize, artvin, antakya, edirne, adana)
python open_meteo_flood_api.py --station rize --days 7

# Koordinat vererek CSV ve PNG grafik kaydetme
python open_meteo_flood_api.py --lat 41.0201 --lon 40.5234 --days 14 --csv rize_debi.csv --plot rize_hidrograf.png
```

### NASA GPM IMERG Granule Sorgulama:
```bash
# Son 24 saatin Early Run (ani sel) granule'larını arama
python gpm_imerg_download.py --mode early --limit 5

# Birim dönüşümü ve dağlık arazi kalibrasyon kurallarını görüntüleme
python gpm_imerg_download.py --info
```

---

## ⚖️ Yasal ve Bilgilendirme Notu

Bu harita ve yazılım paketi; Türkiye'nin sınıraşan ve ulusal nehir havzalarının bilimsel, hidrolojik ve kartografik analizi amacıyla açık kaynak verilerle hazırlanmış bağımsız bir akademik/teknik çalışmadır. Herhangi bir resmi kamu kurumunu temsil etmez; resmi sınır bağlayıcılığı taşımaz.
