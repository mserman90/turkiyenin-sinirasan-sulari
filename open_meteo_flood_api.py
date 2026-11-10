#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Open-Meteo Flood API - Akarsu Debisi ve Taşkın Tahmin Betiği
============================================================
Kaynak: Copernicus GloFAS (Global Flood Awareness System) & ECMWF
API Base URL: https://flood-api.open-meteo.com/v1/flood

Bu betik, belirtilen enlem ve boylam (veya seçilen sınıraşan havza istasyonu)
için 7 günlük (veya 1-92 günlük) akarsu debisi (river discharge), medyan debi
ve maksimum pik debi tahminlerini çeker, terminalde biçimlendirilmiş tablo ve
ASCII grafik olarak görselleştirir. İsteğe bağlı olarak CSV ve Matplotlib PNG
çıktısı üretir.

Sıfır ek kütüphane gereksinimi: Standart Python kütüphaneleri (urllib, json) ile çalışır.
"""

import sys
import json
import urllib.request
import urllib.error
from datetime import datetime

# Windows konsolunda Türkçe ve Unicode karakter desteği
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Sınıraşan ve Kritik Taşkın Havzaları İstasyon Kataloğu
PRESET_STATIONS = {
    "cizre": {
        "name": "Cizre / Dicle Nehri (Suriye-Irak Sınırı)",
        "lat": 37.3325,
        "lon": 42.1894,
        "basin": "Dicle Havzası (21)"
    },
    "birecik": {
        "name": "Birecik / Fırat Nehri (Suriye Sınırı Öncesi)",
        "lat": 37.0264,
        "lon": 37.9772,
        "basin": "Fırat Havzası (21)"
    },
    "kars": {
        "name": "Kars / Aras Havzası (Ermenistan/Azerbaycan Koridoru)",
        "lat": 40.6013,
        "lon": 43.0975,
        "basin": "Aras-Kura Havzası (24)"
    },
    "rize": {
        "name": "Rize İl Merkezi / Taşlıdere - İkizdere",
        "lat": 41.0201,
        "lon": 40.5234,
        "basin": "Doğu Karadeniz Havzası (22)"
    },
    "artvin": {
        "name": "Artvin / Çoruh Nehri (Gürcistan Sınır Çıkışı)",
        "lat": 41.1828,
        "lon": 41.8183,
        "basin": "Çoruh Havzası (23)"
    },
    "antakya": {
        "name": "Antakya / Asi Nehri (Suriye Girişi & Amik Ovası)",
        "lat": 36.2023,
        "lon": 36.1606,
        "basin": "Asi Havzası (19)"
    },
    "edirne": {
        "name": "Edirne / Meriç & Tunca Nehri (Yunanistan/Bulgaristan)",
        "lat": 41.6772,
        "lon": 26.5557,
        "basin": "Meriç-Ergene Havzası (1)"
    },
    "adana": {
        "name": "Adana / Seyhan Nehri (Çukurova Deltası)",
        "lat": 36.9914,
        "lon": 35.3308,
        "basin": "Seyhan Havzası (20)"
    }
}


def get_flood_forecast(lat, lon, forecast_days=7, past_days=0, timezone="auto"):
    """
    Open-Meteo Flood API üzerinden akarsu debisi verilerini çeker.
    
    Parametreler:
        lat (float): Enlem
        lon (float): Boylam
        forecast_days (int): Tahmin gün sayısı (1 - 92)
        past_days (int): Tarihsel gün sayısı (0 - 92)
        timezone (str): Zaman dilimi (örn. 'auto', 'Europe/Istanbul')
        
    Dönüş:
        dict: Parsed JSON yanıtı
    """
    daily_params = [
        "river_discharge",
        "river_discharge_median",
        "river_discharge_max",
        "river_discharge_p25",
        "river_discharge_p75"
    ]
    daily_str = ",".join(daily_params)
    
    url = (
        f"https://flood-api.open-meteo.com/v1/flood?"
        f"latitude={lat:.4f}&longitude={lon:.4f}&"
        f"daily={daily_str}&"
        f"forecast_days={forecast_days}&"
        f"past_days={past_days}&"
        f"timezone={timezone}"
    )
    
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Antigravity-Flood-Hydrology/1.0 (Copernicus GloFAS Client)"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            if response.status == 200:
                content = response.read().decode('utf-8')
                return json.loads(content)
            else:
                raise RuntimeError(f"HTTP Hata Kodu: {response.status}")
    except urllib.error.URLError as e:
        raise ConnectionError(f"Open-Meteo API bağlantı hatası: {e}")


def assess_flood_risk(q_curr, q_max, q_median):
    """
    Mevcut ve maksimum debiyi medyan değer ile oranlayarak taşkın risk seviyesini belirler.
    """
    if q_median is None or q_median <= 0:
        ref = max(q_curr, 1.0)
    else:
        ref = q_median
        
    ratio = q_max / ref
    
    if ratio >= 2.5 and q_max > 250:
        return "🔴 KRİTİK TAŞKIN ALARMI", "Çok Yüksek Debi / Yatak Aşma Riski"
    elif ratio >= 1.6 and q_max > 120:
        return "🟠 YÜKSEK RİSK / UYARI", "Medyan Debinin Belirgin Üzerinde"
    elif ratio >= 1.2:
        return "🟡 DİKKAT / İZLEME", "Akışta Yükselme Eğilimi"
    elif ratio <= 0.7:
        return "🔵 DÜŞÜK AKIŞ / KURAKLIK", "Mevsimsel Ortalamanın Altında"
    else:
        return "🟢 NORMAL / DENGELİ", "Mevsimsel Medyan Seviyesinde"


def print_flood_table(data, station_info=None):
    """
    API'den dönen JSON verisini düzenli bir terminal tablosu olarak basar.
    """
    daily = data.get("daily", {})
    times = daily.get("time", [])
    q_vals = daily.get("river_discharge", [])
    q_medians = daily.get("river_discharge_median", [])
    q_maxs = daily.get("river_discharge_max", [])
    q_p25s = daily.get("river_discharge_p25", [])
    q_p75s = daily.get("river_discharge_p75", [])
    
    lat = data.get("latitude", 0)
    lon = data.get("longitude", 0)
    elev = data.get("elevation", "N/A")
    tz = data.get("timezone", "UTC")
    
    print("\n" + "=" * 88)
    if station_info:
        print(f" 🌊 İSTASYON / NOKTA: {station_info.get('name', 'Bilinmeyen')} [{station_info.get('basin', '')}]")
    else:
        print(f" 🌊 NOKTA SORGUSU: Enlem {lat:.4f}°, Boylam {lon:.4f}°")
    print(f" 📍 Koordinatlar: Lat {lat:.4f}, Lon {lon:.4f} | Rakım: {elev} m | Zaman Dilimi: {tz}")
    print(f" 🛰️ Model: Copernicus GloFAS v4.0 (ECMWF Grid Çözünürlüğü: 0.05° ~ 5 km)")
    print("=" * 88)
    
    # Başlık Satırı
    header = (
        f"{'Tarih':<12} | {'Gün':<6} | {'Debi Q (m³/s)':<14} | "
        f"{'Medyan Q':<12} | {'Pik Qmax (m³/s)':<16} | {'Risk Durumu'}"
    )
    print(header)
    print("-" * 88)
    
    gunler = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
    
    for idx, t_str in enumerate(times):
        dt = datetime.strptime(t_str, "%Y-%m-%d")
        gun_adi = gunler[dt.weekday()]
        
        q = q_vals[idx] if idx < len(q_vals) and q_vals[idx] is not None else 0.0
        q_med = q_medians[idx] if idx < len(q_medians) and q_medians[idx] is not None else 0.0
        q_max = q_maxs[idx] if idx < len(q_maxs) and q_maxs[idx] is not None else q
        
        risk_badge, _ = assess_flood_risk(q, q_max, q_med)
        
        row = (
            f"{t_str:<12} | {gun_adi:<6} | {q:>12.2f}  | "
            f"{q_med:>10.2f}  | {q_max:>14.2f}  | {risk_badge}"
        )
        print(row)
        
    print("-" * 88)


def print_ascii_chart(data):
    """
    Maksimum debi tahminlerini gösteren yatay ASCII çubuk grafik çizer.
    """
    daily = data.get("daily", {})
    times = daily.get("time", [])
    q_maxs = daily.get("river_discharge_max", [])
    q_vals = daily.get("river_discharge", [])
    
    if not times:
        return
        
    max_val = max([v for v in q_maxs if v is not None] + [1.0])
    chart_width = 36
    
    print("\n📊 7 GÜNLÜK PİK DEBİ (Qmax) HİDROĞRAF ÇUBUK GRAFİĞİ:")
    print("-" * 65)
    
    for idx, t_str in enumerate(times):
        val = q_maxs[idx] if idx < len(q_maxs) and q_maxs[idx] is not None else (q_vals[idx] or 0.0)
        bar_len = int((val / max_val) * chart_width)
        bar_len = max(1, bar_len) if val > 0 else 0
        
        # Karakter stili
        if val == max_val and max_val > 10:
            bar_str = "█" * bar_len + " ⚠️ (Haftalık Pik)"
        elif val > max_val * 0.7:
            bar_str = "▓" * bar_len
        else:
            bar_str = "▒" * bar_len
            
        print(f" {t_str} | {val:>7.1f} m³/s | {bar_str}")
        
    print("-" * 65)
    print(f" ℹ️ Ölçeklendirme: En yüksek debi noktası = {max_val:.1f} m³/s (100%)\n")


def export_to_csv(data, filename="flood_forecast.csv"):
    """
    Tahmin verilerini CSV dosyasına kaydeder.
    """
    daily = data.get("daily", {})
    times = daily.get("time", [])
    q_vals = daily.get("river_discharge", [])
    q_medians = daily.get("river_discharge_median", [])
    q_maxs = daily.get("river_discharge_max", [])
    q_p25s = daily.get("river_discharge_p25", [])
    q_p75s = daily.get("river_discharge_p75", [])
    
    with open(filename, mode="w", encoding="utf-8-sig") as f:
        f.write("Tarih,Debi_m3_s,Medyan_Debi_m3_s,Pik_Debi_Max_m3_s,Debi_P25,Debi_P75\n")
        for idx, t in enumerate(times):
            v_q = q_vals[idx] if idx < len(q_vals) and q_vals[idx] is not None else ""
            v_med = q_medians[idx] if idx < len(q_medians) and q_medians[idx] is not None else ""
            v_max = q_maxs[idx] if idx < len(q_maxs) and q_maxs[idx] is not None else ""
            v_p25 = q_p25s[idx] if idx < len(q_p25s) and q_p25s[idx] is not None else ""
            v_p75 = q_p75s[idx] if idx < len(q_p75s) and q_p75s[idx] is not None else ""
            f.write(f"{t},{v_q},{v_med},{v_max},{v_p25},{v_p75}\n")
            
    print(f"💾 Tahmin verileri CSV dosyasına aktarıldı: {filename}")


def export_matplotlib_chart(data, filename="flood_forecast_chart.png", station_name="Akarsu Noktası"):
    """
    Matplotlib kurulu ise profesyonel hidroğraf grafiği üretir ve PNG kaydeder.
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        print("ℹ️ Not: Matplotlib kütüphanesi bulunamadı, PNG grafik atlandı (pip install matplotlib).")
        return

    daily = data.get("daily", {})
    times = [datetime.strptime(t, "%Y-%m-%d") for t in daily.get("time", [])]
    q_vals = [v if v is not None else 0 for v in daily.get("river_discharge", [])]
    q_maxs = [v if v is not None else 0 for v in daily.get("river_discharge_max", [])]
    q_meds = [v if v is not None else 0 for v in daily.get("river_discharge_median", [])]
    q_p25 = [v if v is not None else 0 for v in daily.get("river_discharge_p25", [])]
    q_p75 = [v if v is not None else 0 for v in daily.get("river_discharge_p75", [])]

    plt.figure(figsize=(10, 5), dpi=150)
    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')

    # p25 - p75 belirsizlik kuşağı
    plt.fill_between(times, q_p25, q_p75, color='#38BDF8', alpha=0.25, label='P25 - P75 Güven Kuşağı')
    # Medyan çizgisi
    plt.plot(times, q_meds, color='#94A3B8', linestyle='--', linewidth=1.5, label='Klimatolojik Medyan')
    # Günlük debi
    plt.plot(times, q_vals, color='#0284C7', marker='o', linewidth=2.2, label='Tahmin Edilen Debi (Q)')
    # Maksimum pik
    plt.plot(times, q_maxs, color='#EF4444', marker='s', linewidth=1.8, label='Pik Debi (Qmax)')

    plt.title(f"GloFAS Akarsu Debisi ve Taşkın Tahmini - {station_name}", fontsize=13, fontweight='bold', pad=12)
    plt.xlabel("Tarih", fontsize=10, labelpad=8)
    plt.ylabel("Akarsu Debisi (m³/s)", fontsize=10, labelpad=8)
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.legend(loc='upper right', frameon=True)
    plt.tight_layout()

    plt.savefig(filename, dpi=200)
    plt.close()
    print(f"📈 Matplotlib hidroğraf grafiği kaydedildi: {filename}")


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Open-Meteo Flood API ile Akarsu Debisi ve Taşkın Tahmin Aracı"
    )
    parser.add_argument("--lat", type=float, help="Enlem (Latitude), örn: 37.3325")
    parser.add_argument("--lon", type=float, help="Boylam (Longitude), örn: 42.1894")
    parser.add_argument("--station", type=str, choices=list(PRESET_STATIONS.keys()),
                        help="Önceden tanımlı sınıraşan istasyon kodu (cizre, birecik, kars, rize, artvin, antakya, edirne, adana)")
    parser.add_argument("--days", type=int, default=7, help="Tahmin gün sayısı (1-92, varsayılan 7)")
    parser.add_argument("--past-days", type=int, default=0, help="Geçmiş gün sayısı (varsayılan 0)")
    parser.add_argument("--csv", type=str, help="Sonuçları CSV formatında dışa aktar")
    parser.add_argument("--plot", type=str, help="Matplotlib ile PNG grafik kaydet (örn: grafik.png)")
    parser.add_argument("--list-stations", action="store_true", help="Kayıtlı istasyonları listele")
    
    args = parser.parse_args()
    
    if args.list_stations:
        print("\n📋 KAYITLI SINIRAŞAN VE KRİTİK HAVZA İSTASYONLARI:")
        print("-" * 75)
        for code, info in PRESET_STATIONS.items():
            print(f" • [{code:<8}] {info['name']:<48} (Lat: {info['lat']}, Lon: {info['lon']})")
        print("-" * 75)
        return
        
    station_info = None
    if args.station:
        station_info = PRESET_STATIONS[args.station]
        lat = station_info["lat"]
        lon = station_info["lon"]
    elif args.lat is not None and args.lon is not None:
        lat = args.lat
        lon = args.lon
    else:
        # Varsayılan demo istasyonu: Cizre / Dicle Nehri
        print("ℹ️ İstasyon veya koordinat belirtilmediği için varsayılan 'cizre' (Dicle Nehri) seçildi.")
        station_info = PRESET_STATIONS["cizre"]
        lat = station_info["lat"]
        lon = station_info["lon"]
        
    print(f"\n🚀 Open-Meteo Flood API sorgulanıyor... (Lat: {lat}, Lon: {lon}, Gün: {args.days})")
    
    try:
        data = get_flood_forecast(lat, lon, forecast_days=args.days, past_days=args.past_days)
        
        # 1. Tablo Çıktısı
        print_flood_table(data, station_info)
        
        # 2. ASCII Çubuk Grafik
        print_ascii_chart(data)
        
        # 3. CSV Dışa Aktarma
        if args.csv:
            export_to_csv(data, args.csv)
            
        # 4. Matplotlib PNG Çıktısı
        if args.plot:
            st_name = station_info["name"] if station_info else f"Lat {lat}, Lon {lon}"
            export_matplotlib_chart(data, args.plot, st_name)
            
    except Exception as err:
        print(f"\n❌ Hata oluştu: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
