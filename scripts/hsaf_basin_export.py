#!/usr/bin/env python3
"""
H-SAF (EUMETSAT Hydrology SAF) Havza Bazlı Uydu Yağış/Kar İndirici & ANFIS CSV Aktarıcı

mserman90/data_access (ftphsaf.meteoam.it) ile uyumlu çalışır:
  - H64: h64/h64_cur_mon_data/ (acc_rr, günlük birikimli yağış)
  - H60: h60/h60_cur_mon_data/ + utilities/matlab_code/lat_lon_0.nc.gz (rr)
  - H26: h26/h26_cur_mon_nc/ (.nc kar eşdeğeri / örtüsü)

Çıktılar:
  1) Izgara CSV (mserman90/data_access output.csv uyumlu): x,time,lat,lon,Rainfall
  2) Günlük Havza & ANFIS CSV: date,basin_code,basin_name,product,points,mean_precip_mm,max_precip_mm,p_lag1_mm,p_lag2_mm
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from ftplib import FTP
import gzip
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


DEFAULT_GEOJSON = Path(__file__).resolve().parent.parent / "turkiye_sinirasan_havzalar_web.geojson"
HSAF_FTP_HOST = "ftphsaf.meteoam.it"

BASIN_PRESETS: Dict[str, Dict[str, object]] = {
    "all": {"code": "TR_ALL", "name": "Tüm Sınıraşan Havzalar", "geojson_codes": None, "bbox": (25.95, 35.75, 44.95, 42.15)},
    "meric": {"code": "TR01", "name": "Meriç-Ergene", "geojson_codes": ["TR01"], "bbox": (26.00, 40.60, 28.25, 42.15)},
    "tr01": {"code": "TR01", "name": "Meriç-Ergene", "geojson_codes": ["TR01"], "bbox": (26.00, 40.60, 28.25, 42.15)},
    "asi": {"code": "TR19", "name": "Asi", "geojson_codes": ["TR19"], "bbox": (35.75, 35.78, 37.28, 37.26)},
    "tr19": {"code": "TR19", "name": "Asi", "geojson_codes": ["TR19"], "bbox": (35.75, 35.78, 37.28, 37.26)},
    "firat-dicle": {"code": "TR21", "name": "Fırat-Dicle", "geojson_codes": ["TR21"], "bbox": (36.75, 36.60, 44.88, 40.40)},
    "tr21": {"code": "TR21", "name": "Fırat-Dicle", "geojson_codes": ["TR21"], "bbox": (36.75, 36.60, 44.88, 40.40)},
    "firat": {"code": "TR21_FIRAT", "name": "Fırat Alt Havzası", "geojson_codes": ["TR21"], "bbox": (36.75, 36.60, 42.85, 40.40)},
    "dicle": {"code": "TR21_DICLE", "name": "Dicle Alt Havzası", "geojson_codes": ["TR21"], "bbox": (39.50, 36.65, 44.88, 38.95)},
    "coruh": {"code": "TR23", "name": "Çoruh", "geojson_codes": ["TR23"], "bbox": (39.62, 39.88, 42.68, 41.56)},
    "tr23": {"code": "TR23", "name": "Çoruh", "geojson_codes": ["TR23"], "bbox": (39.62, 39.88, 42.68, 41.56)},
    "aras": {"code": "TR24", "name": "Aras", "geojson_codes": ["TR24"], "bbox": (41.12, 39.28, 44.86, 41.64)},
    "tr24": {"code": "TR24", "name": "Aras", "geojson_codes": ["TR24"], "bbox": (41.12, 39.28, 44.86, 41.64)},
}


@dataclass
class GridRecord:
    obs_date: str
    lat: float
    lon: float
    value: float


def parse_iso_date(text: str) -> date:
    return datetime.strptime(text.strip(), "%Y-%m-%d").date()


def parse_bbox(text: str) -> Tuple[float, float, float, float]:
    parts = [float(p.strip()) for p in text.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox 4 değer içermelidir: minlon,minlat,maxlon,maxlat")
    minlon, minlat, maxlon, maxlat = parts
    if minlon >= maxlon or minlat >= maxlat:
        raise ValueError("bbox sınırları geçersiz: minlon < maxlon ve minlat < maxlat olmalıdır")
    return minlon, minlat, maxlon, maxlat


def point_in_ring(x: float, y: float, ring: Sequence[Sequence[float]]) -> bool:
    """Ray-casting algoritması ile nokta-poligon halkası testi."""
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-15) + xi):
            inside = not inside
        j = i
    return inside


def point_in_polygon_rings(x: float, y: float, rings: Sequence[Sequence[Sequence[float]]]) -> bool:
    """GeoJSON Polygon koordinat dizisi (dış halka + opsiyonel iç boşluklar) kontrolü."""
    if not rings or not point_in_ring(x, y, rings[0]):
        return False
    for hole in rings[1:]:
        if point_in_ring(x, y, hole):
            return False
    return True


@dataclass
class PolygonFilter:
    code: str
    name: str
    polygons: List[Tuple[Tuple[float, float, float, float], List[List[List[float]]]]]
    bbox: Optional[Tuple[float, float, float, float]] = None

    def contains(self, lon: float, lat: float) -> bool:
        if self.bbox is not None:
            minlon, minlat, maxlon, maxlat = self.bbox
            if lon < minlon or lon > maxlon or lat < minlat or lat > maxlat:
                return False
        if not self.polygons:
            return self.bbox is not None
        for pbbox, rings in self.polygons:
            if pbbox[0] <= lon <= pbbox[2] and pbbox[1] <= lat <= pbbox[3]:
                if point_in_polygon_rings(lon, lat, rings):
                    return True
        return False


def _rings_bbox(rings: Sequence[Sequence[Sequence[float]]]) -> Tuple[float, float, float, float]:
    xs: List[float] = []
    ys: List[float] = []
    for ring in rings:
        for pt in ring:
            xs.append(float(pt[0]))
            ys.append(float(pt[1]))
    return min(xs), min(ys), max(xs), max(ys)


def load_spatial_filter(
    basin: str,
    geojson_path: Optional[Path] = None,
    bbox_override: Optional[Tuple[float, float, float, float]] = None,
) -> PolygonFilter:
    basin_key = basin.strip().lower()
    preset = BASIN_PRESETS.get(basin_key)
    code = str(preset["code"]) if preset else basin_key.upper()
    name = str(preset["name"]) if preset else basin
    target_codes = preset["geojson_codes"] if preset else None
    preset_bbox = preset["bbox"] if preset else None
    effective_bbox = bbox_override or (preset_bbox if isinstance(preset_bbox, tuple) else None)

    polygons: List[Tuple[Tuple[float, float, float, float], List[List[List[float]]]]] = []
    if geojson_path and geojson_path.exists():
        data = json.loads(geojson_path.read_text(encoding="utf-8"))
        for feat in data.get("features", []):
            props = feat.get("properties") or {}
            kodu = str(props.get("KODU") or props.get("code") or "").strip()
            adi = str(props.get("ADI") or props.get("name") or "").strip()
            if target_codes is not None and kodu not in target_codes:
                if basin_key not in adi.lower():
                    continue
            geom = feat.get("geometry") or {}
            gtype = geom.get("type")
            coords = geom.get("coordinates") or []
            if gtype == "Polygon":
                polygons.append((_rings_bbox(coords), coords))
            elif gtype == "MultiPolygon":
                for poly in coords:
                    polygons.append((_rings_bbox(poly), poly))

    if effective_bbox is None and polygons:
        all_boxes = [p[0] for p in polygons]
        effective_bbox = (
            min(b[0] for b in all_boxes),
            min(b[1] for b in all_boxes),
            max(b[2] for b in all_boxes),
            max(b[3] for b in all_boxes),
        )

    return PolygonFilter(code=code, name=name, polygons=polygons, bbox=effective_bbox)


def date_list_inclusive(start: date, end: date) -> List[date]:
    if end < start:
        raise ValueError("Başlangıç tarihi bitiş tarihinden sonra olamaz")
    days = (end - start).days + 1
    return [start + timedelta(days=i) for i in range(days)]


def extract_gz_in_dir(raw_dir: Path) -> List[Path]:
    """Dizin içindeki .gz dosyalarını açar ve mevcut .nc dosyalarını sıralı döndürür."""
    for gz_path in sorted(raw_dir.glob("*.gz")):
        out_path = gz_path.with_suffix("")
        if not out_path.exists() or out_path.stat().st_size == 0:
            with gzip.open(gz_path, "rb") as fin, open(out_path, "wb") as fout:
                shutil.copyfileobj(fin, fout)
    return sorted(p for p in raw_dir.glob("*.nc") if p.stat().st_size > 0)


def ftp_download_hsaf(
    product: str,
    start: date,
    end: date,
    raw_dir: Path,
    username: str,
    password: str,
) -> Tuple[List[Path], Optional[Path]]:
    """mserman90/data_access ile aynı FTP yollarından H64/H60/H26 dosyalarını indirir."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    dates = date_list_inclusive(start, end)
    downloaded: List[Path] = []
    latlon_nc: Optional[Path] = None

    with FTP(HSAF_FTP_HOST, timeout=60) as ftp:
        ftp.login(user=username, passwd=password)

        if product == "h60":
            latlon_local = raw_dir / "lat_lon.nc"
            if not latlon_local.exists():
                ftp.cwd("/utilities/matlab_code")
                nlst = ftp.nlst()
                target = "lat_lon_0.nc.gz"
                if target in nlst:
                    gz_local = raw_dir / target
                    with open(gz_local, "wb") as f:
                        ftp.retrbinary(f"RETR {target}", f.write)
                    with gzip.open(gz_local, "rb") as fin, open(latlon_local, "wb") as fout:
                        shutil.copyfileobj(fin, fout)
            if latlon_local.exists():
                latlon_nc = latlon_local

        remote_dir = {
            "h64": "/h64/h64_cur_mon_data",
            "h60": "/h60/h60_cur_mon_data",
            "h26": "/h26/h26_cur_mon_nc",
        }[product]

        ftp.cwd(remote_dir)
        remote_files = ftp.nlst()

        for d in dates:
            ymd = d.strftime("%Y%m%d")
            if product == "h26":
                prefix = f"h26_{ymd}00_R01.nc"
                matches = [fn for fn in remote_files if prefix in fn]
            else:
                prefix = f"{product}_{ymd}"
                matches = [fn for fn in remote_files if fn.startswith(prefix)]

            if not matches:
                print(f"[UYARI] {d.isoformat()} için {product.upper()} dosyası FTP'de bulunamadı.", file=sys.stderr)
                continue

            for remote_name in matches:
                local_path = raw_dir / Path(remote_name).name
                if not local_path.exists() or local_path.stat().st_size == 0:
                    with open(local_path, "wb") as f:
                        ftp.retrbinary(f"RETR {remote_name}", f.write)
                downloaded.append(local_path)
                print(f"[İNDİRİLDİ] {remote_name} -> {local_path}")

    return extract_gz_in_dir(raw_dir), latlon_nc


def _infer_date_from_nc(ds, nc_path: Path) -> str:
    end_attr = getattr(ds, "end_of_accumulation_time", None)
    if end_attr:
        try:
            return datetime.strptime(str(end_attr).strip(), "%Y%m%dT%H:%MZ").strftime("%Y-%m-%d")
        except ValueError:
            pass
    m = re.search(r"(\d{8})", nc_path.name)
    if m:
        s = m.group(1)
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    raise ValueError(f"NetCDF dosyasından tarih okunamadı: {nc_path}")


def _extract_array(var) -> "np.ndarray":
    import numpy as np

    arr = var[:]
    if np.ma.isMaskedArray(arr):
        arr = np.ma.filled(arr.astype(np.float64), np.nan)
    else:
        arr = np.asarray(arr, dtype=np.float64)
    fill = getattr(var, "_FillValue", None)
    if fill is not None:
        arr = np.where(arr == float(fill), np.nan, arr)
    return arr


def _pick_variable_name(ds, product: str) -> str:
    preferred = {
        "h64": ["acc_rr", "Rainfall", "rr", "precip"],
        "h60": ["rr", "acc_rr", "Rainfall", "precip"],
        "h26": ["swe", "sd", "snow", "snow_depth", "sc", "H26", "Snow"],
    }[product]
    for name in preferred:
        if name in ds.variables:
            return name
    coord_names = {"lat", "lon", "latitude", "longitude", "long", "latg", "time", "x", "y"}
    for name, var in ds.variables.items():
        if name.lower() not in coord_names and getattr(var, "ndim", 0) >= 1:
            return name
    raise KeyError(f"{product.upper()} için uygun veri değişkeni bulunamadı: {list(ds.variables.keys())}")


def read_hsaf_netcdf_records(
    nc_files: Sequence[Path],
    product: str,
    spatial_filter: PolygonFilter,
    latlon_nc: Optional[Path] = None,
) -> List[GridRecord]:
    try:
        import netCDF4 as nc
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "NetCDF dosyalarını okumak için 'netCDF4' ve 'numpy' gereklidir "
            "(pip install -r scripts/requirements-hsaf.txt)."
        ) from exc

    ext_lats = ext_lons = None
    if latlon_nc and latlon_nc.exists():
        with nc.Dataset(str(latlon_nc), mode="r") as dlatlon:
            lon_key = next((k for k in ("long", "lon", "longitude") if k in dlatlon.variables), None)
            lat_key = next((k for k in ("latg", "lat", "latitude") if k in dlatlon.variables), None)
            if lon_key and lat_key:
                ext_lons = np.asarray(dlatlon.variables[lon_key][:], dtype=np.float64).ravel()
                ext_lats = np.asarray(dlatlon.variables[lat_key][:], dtype=np.float64).ravel()

    records: List[GridRecord] = []
    for nc_path in sorted(nc_files):
        if nc_path.name == "lat_lon.nc":
            continue
        with nc.Dataset(str(nc_path), mode="r") as ds:
            obs_date = _infer_date_from_nc(ds, nc_path)
            vname = _pick_variable_name(ds, product)
            vals = _extract_array(ds.variables[vname])
            while vals.ndim > 2 and vals.shape[0] == 1:
                vals = vals[0]

            lat_var = next((k for k in ("latitude", "lat", "latg") if k in ds.variables), None)
            lon_var = next((k for k in ("longitude", "lon", "long") if k in ds.variables), None)

            if lat_var and lon_var:
                lats = np.asarray(ds.variables[lat_var][:], dtype=np.float64)
                lons = np.asarray(ds.variables[lon_var][:], dtype=np.float64)
            elif ext_lats is not None and ext_lons is not None:
                lats = ext_lats
                lons = ext_lons
            else:
                raise KeyError(f"{nc_path.name} koordinat değişkenleri bulunamadı (--latlon-nc belirtin)")

            if vals.ndim == 2 and lats.ndim == 1 and lons.ndim == 1:
                if vals.shape == (lats.size, lons.size):
                    lon_grid, lat_grid = np.meshgrid(lons, lats)
                elif vals.shape == (lons.size, lats.size):
                    lat_grid, lon_grid = np.meshgrid(lats, lons)
                else:
                    raise ValueError(f"Boyut uyumsuzluğu {nc_path.name}: vals={vals.shape}, lat={lats.size}, lon={lons.size}")
                flat_lats = lat_grid.ravel()
                flat_lons = lon_grid.ravel()
                flat_vals = vals.ravel()
            elif vals.shape == lats.shape == lons.shape:
                flat_lats = lats.ravel()
                flat_lons = lons.ravel()
                flat_vals = vals.ravel()
            elif vals.ndim == 1 and lats.ndim == 1 and lons.ndim == 1 and vals.size == lats.size * lons.size:
                lat_grid, lon_grid = np.meshgrid(lats, lons, indexing="ij")
                flat_lats = lat_grid.ravel()
                flat_lons = lon_grid.ravel()
                flat_vals = vals
            else:
                raise ValueError(f"Desteklenmeyen dizi şekli {nc_path.name}: {vals.shape}")

            # Bbox ile hızlı ön eleme
            mask = np.isfinite(flat_vals) & (flat_vals >= 0.0)
            if spatial_filter.bbox is not None:
                minlon, minlat, maxlon, maxlat = spatial_filter.bbox
                mask &= (
                    (flat_lons >= minlon)
                    & (flat_lons <= maxlon)
                    & (flat_lats >= minlat)
                    & (flat_lats <= maxlat)
                )

            cand_idx = np.where(mask)[0]
            for idx in cand_idx:
                lon_v = float(flat_lons[idx])
                lat_v = float(flat_lats[idx])
                val_v = float(flat_vals[idx])
                if spatial_filter.contains(lon_v, lat_v):
                    records.append(GridRecord(obs_date=obs_date, lat=lat_v, lon=lon_v, value=val_v))

    return records


def build_anfis_daily_summary(
    records: Sequence[GridRecord],
    basin_code: str,
    basin_name: str,
    product: str,
) -> List[Dict[str, object]]:
    by_date: Dict[str, List[float]] = {}
    for rec in records:
        if math.isfinite(rec.value) and rec.value >= 0.0:
            by_date.setdefault(rec.obs_date, []).append(rec.value)

    daily_means: Dict[str, float] = {
        d: sum(vals) / len(vals) for d, vals in by_date.items() if vals
    }

    rows: List[Dict[str, object]] = []
    for d in sorted(by_date.keys()):
        vals = by_date[d]
        d_obj = parse_iso_date(d)
        lag1_key = (d_obj - timedelta(days=1)).isoformat()
        lag2_key = (d_obj - timedelta(days=2)).isoformat()
        rows.append(
            {
                "date": d,
                "basin_code": basin_code,
                "basin_name": basin_name,
                "product": product.upper(),
                "points": len(vals),
                "mean_precip_mm": round(daily_means[d], 3),
                "max_precip_mm": round(max(vals), 3),
                "p_lag1_mm": round(daily_means[lag1_key], 3) if lag1_key in daily_means else "",
                "p_lag2_mm": round(daily_means[lag2_key], 3) if lag2_key in daily_means else "",
            }
        )
    return rows


def write_outputs(
    records: Sequence[GridRecord],
    anfis_rows: Sequence[Dict[str, object]],
    out_grid_csv: Path,
    out_anfis_csv: Path,
    value_col: str = "Rainfall",
) -> None:
    out_grid_csv.parent.mkdir(parents=True, exist_ok=True)
    out_anfis_csv.parent.mkdir(parents=True, exist_ok=True)

    sorted_records = sorted(records, key=lambda r: (r.obs_date, r.lat, r.lon))
    with open(out_grid_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["x", "time", "lat", "lon", value_col])
        for idx, rec in enumerate(sorted_records):
            writer.writerow([idx, rec.obs_date, round(rec.lat, 5), round(rec.lon, 5), round(rec.value, 4)])

    fields = [
        "date",
        "basin_code",
        "basin_name",
        "product",
        "points",
        "mean_precip_mm",
        "max_precip_mm",
        "p_lag1_mm",
        "p_lag2_mm",
    ]
    with open(out_anfis_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in anfis_rows:
            writer.writerow(row)


def run_sample_pipeline(
    basin: str,
    product: str,
    geojson_path: Optional[Path],
    out_dir: Path,
) -> Dict[str, object]:
    """FTP kimlik bilgisi olmadan sentetik havza gridi üretir ve GeoJSON kırpma + ANFIS (t-2) çıktısını doğrular."""
    spatial_filter = load_spatial_filter(basin, geojson_path=geojson_path)
    minlon, minlat, maxlon, maxlat = spatial_filter.bbox or (26.0, 40.7, 27.6, 42.0)

    # Bbox içinde düzenli 10x10 aday ızgara oluştur; GeoJSON poligonu dışı otomatik elenir
    lats = [minlat + (maxlat - minlat) * (i + 0.5) / 10.0 for i in range(10)]
    lons = [minlon + (maxlon - minlon) * (j + 0.5) / 10.0 for j in range(10)]

    start_d = date(2026, 11, 5)
    day_profile = [2.4, 8.6, 24.8, 31.2, 11.4, 3.1]
    records: List[GridRecord] = []

    for day_idx, base_rain in enumerate(day_profile):
        cur_date = (start_d + timedelta(days=day_idx)).isoformat()
        for i, lat_v in enumerate(lats):
            for j, lon_v in enumerate(lons):
                if not spatial_filter.contains(lon_v, lat_v):
                    continue
                grad = 0.65 + 0.7 * ((i + j) / 18.0)
                records.append(GridRecord(obs_date=cur_date, lat=lat_v, lon=lon_v, value=base_rain * grad))

    if not records:
        raise RuntimeError(f"Sentetik testte havza poligonu içinde nokta kalmadı: {basin}")

    anfis_rows = build_anfis_daily_summary(records, spatial_filter.code, spatial_filter.name, product)
    safe_basin = re.sub(r"[^a-z0-9_-]+", "_", basin.lower()).strip("_") or "basin"
    out_grid_csv = out_dir / f"hsaf_{product}_{safe_basin}_sample_grid.csv"
    out_anfis_csv = out_dir / f"hsaf_{product}_{safe_basin}_sample_anfis.csv"
    val_col = "Snow_SWE" if product == "h26" else "Rainfall"
    write_outputs(records, anfis_rows, out_grid_csv, out_anfis_csv, value_col=val_col)

    return {
        "basin_code": spatial_filter.code,
        "basin_name": spatial_filter.name,
        "grid_points": len(records),
        "days": len(anfis_rows),
        "latest_p_lag2_mm": anfis_rows[-1]["p_lag2_mm"] if anfis_rows else "",
        "out_grid_csv": str(out_grid_csv),
        "out_anfis_csv": str(out_anfis_csv),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="H-SAF (H64/H60/H26) havza bazlı uydu yağış/kar indirici ve ANFIS P(t-2) CSV dışa aktarıcı."
    )
    parser.add_argument("--product", choices=["h64", "h60", "h26"], default="h64", help="H-SAF ürün kodu (varsayılan: h64)")
    parser.add_argument("--basin", default="meric", help="Havza anahtarı: meric, asi, firat-dicle, firat, dicle, coruh, aras, all")
    parser.add_argument("--bbox", default=None, help="Özel sınır kutusu: minlon,minlat,maxlon,maxlat")
    parser.add_argument("--geojson", default=str(DEFAULT_GEOJSON), help="Havza sınırları GeoJSON dosya yolu")
    parser.add_argument("--start", default=None, help="Başlangıç tarihi (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="Bitiş tarihi (YYYY-MM-DD)")
    parser.add_argument("--user", default=os.environ.get("HSAF_USER", ""), help="H-SAF FTP kullanıcı adı (veya HSAF_USER)")
    parser.add_argument("--password", default=os.environ.get("HSAF_PASS", ""), help="H-SAF FTP parolası (veya HSAF_PASS)")
    parser.add_argument("--input-dir", default=None, help="Yerel .nc/.nc.gz klasörü (FTP indirmeden çevrimdışı işleme)")
    parser.add_argument("--latlon-nc", default=None, help="H60 için opsiyonel lat_lon.nc yolu")
    parser.add_argument("--raw-dir", default="output/hsaf_raw", help="Ham NetCDF indirme klasörü")
    parser.add_argument("--out-dir", default="output", help="Çıktı CSV klasörü")
    parser.add_argument("--sample-test", action="store_true", help="FTP kimlik bilgisi olmadan örnek havza boru hattı testi çalıştır")

    args = parser.parse_args(argv)
    geojson_path = Path(args.geojson) if args.geojson else None
    out_dir = Path(args.out_dir)

    if args.sample_test:
        summary = run_sample_pipeline(args.basin, args.product, geojson_path, out_dir)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    bbox_override = parse_bbox(args.bbox) if args.bbox else None
    spatial_filter = load_spatial_filter(args.basin, geojson_path=geojson_path, bbox_override=bbox_override)

    if args.input_dir:
        nc_files = extract_gz_in_dir(Path(args.input_dir))
        latlon_nc = Path(args.latlon_nc) if args.latlon_nc else (Path(args.input_dir) / "lat_lon.nc")
    else:
        if not args.start or not args.end:
            parser.error("FTP indirmesi için --start YYYY-MM-DD ve --end YYYY-MM-DD (veya çevrimdışı --input-dir / --sample-test) gereklidir.")
        if not args.user or not args.password:
            parser.error("H-SAF FTP kimlik bilgileri eksik: --user / --password verin veya HSAF_USER / HSAF_PASS ortam değişkenlerini ayarlayın.")
        start_d = parse_iso_date(args.start)
        end_d = parse_iso_date(args.end)
        nc_files, downloaded_latlon = ftp_download_hsaf(args.product, start_d, end_d, Path(args.raw_dir), args.user, args.password)
        latlon_nc = Path(args.latlon_nc) if args.latlon_nc else downloaded_latlon

    if not nc_files:
        print("[HATA] İşlenecek geçerli .nc dosyası bulunamadı.", file=sys.stderr)
        return 2

    records = read_hsaf_netcdf_records(nc_files, args.product, spatial_filter, latlon_nc=latlon_nc)
    if not records:
        print(f"[UYARI] {spatial_filter.name} alanı içinde geçerli hücre bulunamadı.", file=sys.stderr)
        return 3

    anfis_rows = build_anfis_daily_summary(records, spatial_filter.code, spatial_filter.name, args.product)
    safe_basin = re.sub(r"[^a-z0-9_-]+", "_", args.basin.lower()).strip("_") or "basin"
    out_grid_csv = out_dir / f"hsaf_{args.product}_{safe_basin}_grid.csv"
    out_anfis_csv = out_dir / f"hsaf_{args.product}_{safe_basin}_anfis.csv"
    val_col = "Snow_SWE" if args.product == "h26" else "Rainfall"
    write_outputs(records, anfis_rows, out_grid_csv, out_anfis_csv, value_col=val_col)

    print(
        json.dumps(
            {
                "basin_code": spatial_filter.code,
                "basin_name": spatial_filter.name,
                "grid_points": len(records),
                "days": len(anfis_rows),
                "latest_p_lag2_mm": anfis_rows[-1]["p_lag2_mm"] if anfis_rows else "",
                "out_grid_csv": str(out_grid_csv),
                "out_anfis_csv": str(out_anfis_csv),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
