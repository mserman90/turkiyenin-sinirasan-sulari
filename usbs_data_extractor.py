#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
USBS (Ulusal Su Bilgi Sistemi) Veri Çekme ve GIS Katman Entegrasyon Aracı
========================================================================
Kaynak: https://usbs.tarimorman.gov.tr/usbs/VatandasGirisi/
Proxy API: https://usbs.tarimorman.gov.tr/usbs/proxy.ashx?http://usbsgissrv:6080/arcgis/rest/services/

Bu betik:
1. USBS ArcGIS Server servislerinden Türkiye'nin 25 Havzası ve Sınıraşan Havzaların
   vektör GeoJSON sınırlarını çeker.
2. Taşkın Risk (Q50, Q100, Q500) ve Taşkın Tehlike katmanlarını sorgular.
3. TYP (Taşkın Yönetim Planı) nokta, çizgi ve alan eylem tedbirlerini dışa aktarır.
4. Leaflet ve QGIS/ArcGIS uyumlu WMS/WFS/REST bağlantı şablonları üretir.
"""

import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime

# Windows konsolunda Türkçe desteği
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# USBS Açık Proxy ve REST Servis Temel URL'leri
USBS_PROXY = "https://usbs.tarimorman.gov.tr/usbs/proxy.ashx?http://usbsgissrv:6080/arcgis/rest/services/"
USBS_WMS_PROXY = "https://usbs.tarimorman.gov.tr/usbs/proxy.ashx?http://usbsgissrv:6080/arcgis/services/"

# Temel Servis Katalogları
SERVICES = {
    "hidroloji": "SAYISALLASTIRMA_2/SAYISALLASTIRMA_SERVIS_2/MapServer",
    "taskin": "PUBLIC/TASKIN/MapServer",
    "yonetim_planlari": "YONETIM_PLANLARI_VIEW/YONETIM_PLANLARI/MapServer"
}

# Sınıraşan Havza Kodları
SINIRASAN_HAVZALAR = {
    "TR01": "Meriç-Ergene Havzası (Bulgaristan/Yunanistan)",
    "TR19": "Asi Havzası (Suriye/Lübnan)",
    "TR21": "Fırat-Dicle Havzası (Suriye/Irak)",
    "TR23": "Çoruh Havzası (Gürcistan)",
    "TR24": "Aras-Kura Havzası (Ermenistan/Azerbaycan)"
}


def query_basins(basin_codes=None, return_geometry=False, output_file=None):
    """
    USBS Sayısallaştırma servisinden havza özniteliklerini veya GeoJSON geometrilerini çeker.
    """
    layer_url = f"{USBS_PROXY}{SERVICES['hidroloji']}/0/query"
    
    if basin_codes:
        formatted_codes = ",".join([f"'{c}'" for c in basin_codes])
        where_clause = f"KODU IN ({formatted_codes})"
    else:
        where_clause = "1=1"
        
    fmt = "geojson" if return_geometry else "pjson"
    params = {
        "where": where_clause,
        "outFields": "OBJECTID,KODU,ADI,ALAN_KM2,HAVZA_NUFUSU_2022_TUIK",
        "returnGeometry": "true" if return_geometry else "false",
        "f": fmt
    }
    
    full_url = f"{layer_url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        full_url,
        headers={"User-Agent": "Antigravity-USBS-Client/1.0"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode('utf-8')
            data = json.loads(content)
            
            if output_file:
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"💾 Veri kaydedildi: {output_file}")
                
            return data
    except Exception as e:
        raise RuntimeError(f"USBS Havza sorgulanamadı: {e}")


def print_basin_table(data):
    """Havza özniteliklerini terminalde biçimlendirilmiş tablo olarak basar."""
    features = data.get("features", [])
    print("\n" + "=" * 90)
    print(" 🌊 USBS RESMİ HAVZA ENVANTERİ VE SINIRAŞAN HAVZALAR (ArcGIS Server REST)")
    print("=" * 90)
    print(f"{'No':<4} | {'Kod':<6} | {'Havza Adı':<28} | {'Alan (km²)':<14} | {'Nüfus (2022 TÜİK)'}")
    print("-" * 90)
    
    for f in features:
        attrs = f.get("attributes", {})
        oid = attrs.get("OBJECTID", "-")
        kodu = attrs.get("KODU", "-")
        adi = attrs.get("ADI", "-")
        alan = attrs.get("ALAN_KM2", 0.0)
        nufus = attrs.get("HAVZA_NUFUSU_2022_TUIK", "Bilinmiyor")
        
        # Sınıraşan vurgusu
        badge = " 🌐 [Sınıraşan]" if kodu in SINIRASAN_HAVZALAR else ""
        print(f"{oid:<4} | {kodu:<6} | {adi:<28} | {alan:>12.2f} | {str(nufus):>12} {badge}")
        
    print("-" * 90)


def print_wms_catalog():
    """Leaflet ve CBS için kullanılabilir USBS WMS/WFS katman listesini basar."""
    print("\n" + "=" * 90)
    print(" 🗺️ USBS ENTEGRE EDİLEBİLİR WMS / MAPSERVER KATMAN REHBERİ (Leaflet & QGIS)")
    print("=" * 90)
    
    wms_list = [
        ("PUBLIC/TASKIN", "GenelRiskQ100", "Taşkın Genel Risk Haritası (100 Yıllık Q100)"),
        ("PUBLIC/TASKIN", "GenelRiskQ50", "Taşkın Genel Risk Haritası (50 Yıllık Q50)"),
        ("PUBLIC/TASKIN", "GenelRiskQ500", "Taşkın Genel Risk Haritası (500 Yıllık Q500)"),
        ("PUBLIC/TASKIN", "TehlikeDereceQ100", "Taşkın Tehlike Derecelendirmesi (Q100)"),
        ("PUBLIC/TASKIN", "SuDerinliğiQ100", "Taşkın Su Derinliği Haritası (Q100)"),
        ("PUBLIC/TASKIN", "Tahliye Noktaları", "Taşkın Tahliye Noktaları"),
        ("SAYISALLASTIRMA_2", "41", "25 Su Havzası Poligon Sınırları (Havza)"),
        ("SAYISALLASTIRMA_2", "40", "Alt Havza Sınırları"),
        ("SAYISALLASTIRMA_2", "0,1,2", "Nehirler ve Akarsu Ağı (Strahler Seviyeleri)"),
        ("YONETIM_PLANLARI_VIEW", "TYP_NOKTA_VT", "Taşkın Yönetim Planı Nokta Tedbirleri (Menfez, Bent vb.)"),
        ("YONETIM_PLANLARI_VIEW", "TYP_CIZGI_VT", "Taşkın Yönetim Planı Çizgi Tedbirleri (Sedde, Islah Duvarı)")
    ]
    
    for srv, lyr, desc in wms_list:
        print(f" • [{srv:<20}] Katman: {lyr:<18} -> {desc}")
        
    print("\n 💡 Leaflet Entegrasyon Kodu Örneği:")
    print("""
    const taskinRiskQ100Layer = L.tileLayer.wms(
      'https://usbs.tarimorman.gov.tr/usbs/proxy.ashx?http://usbsgissrv:6080/arcgis/services/PUBLIC/TASKIN/MapServer/WMSServer',
      {
        layers: 'GenelRiskQ100',
        format: 'image/png32',
        transparent: true,
        version: '1.3.0',
        crs: L.CRS.EPSG3857,
        attribution: 'USBS Taşkın Modeli (Q100)'
      }
    );
    """)
    print("=" * 90 + "\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="USBS ArcGIS Server Veri Çekme ve Entegrasyon Aracı")
    parser.add_argument("--sinirasan", action="store_true", help="Yalnızca sınıraşan 5 havzayı listele")
    parser.add_argument("--geojson", type=str, help="Havza poligonlarını GeoJSON dosyası olarak kaydet")
    parser.add_argument("--wms-info", action="store_true", help="Kullanılabilir WMS katmanlarını ve Leaflet kodunu listele")
    
    args = parser.parse_args()
    
    if args.wms_info:
        print_wms_catalog()
        return
        
    codes = list(SINIRASAN_HAVZALAR.keys()) if args.sinirasan else None
    print(f"🚀 USBS ArcGIS Server REST proxy sorgulanıyor...")
    
    data = query_basins(
        basin_codes=codes,
        return_geometry=bool(args.geojson),
        output_file=args.geojson
    )
    print_basin_table(data)
    print_wms_catalog()


if __name__ == "__main__":
    main()
