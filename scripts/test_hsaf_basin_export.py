#!/usr/bin/env python3
import csv
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hsaf_basin_export as hbe  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parent.parent
GEOJSON_PATH = REPO_ROOT / "turkiye_sinirasan_havzalar_web.geojson"


class TestHsafBasinExport(unittest.TestCase):
    def test_load_geojson_meric_polygon(self):
        filt = hbe.load_spatial_filter("meric", geojson_path=GEOJSON_PATH)
        self.assertEqual(filt.code, "TR01")
        self.assertTrue(len(filt.polygons) >= 1)
        # Edirne-Ergene iç kesiti (Lüleburgaz/Babaeski civarı) içeride olmalı
        self.assertTrue(filt.contains(27.25, 41.35))
        # Diyarbakır dışı olmalı
        self.assertFalse(filt.contains(40.23, 37.91))

    def test_calendar_exact_lag2_skips_gap_day(self):
        # 2026-11-02 var ama 2026-11-03 eksik; 2026-11-05 için t-2=2026-11-03 yok -> boş olmalı,
        # 2026-11-04 için t-2=2026-11-02 var -> 12.0 olmalı!
        records = [
            hbe.GridRecord("2026-11-02", 41.6, 26.5, 10.0),
            hbe.GridRecord("2026-11-02", 41.7, 26.6, 14.0),
            hbe.GridRecord("2026-11-04", 41.6, 26.5, 20.0),
            hbe.GridRecord("2026-11-05", 41.6, 26.5, 5.0),
        ]
        rows = hbe.build_anfis_daily_summary(records, "TR01", "Meriç-Ergene", "h64")
        by_date = {r["date"]: r for r in rows}
        self.assertEqual(by_date["2026-11-04"]["mean_precip_mm"], 20.0)
        self.assertEqual(by_date["2026-11-04"]["p_lag2_mm"], 12.0)
        self.assertEqual(by_date["2026-11-04"]["p_lag1_mm"], "")
        self.assertEqual(by_date["2026-11-05"]["p_lag1_mm"], 20.0)
        self.assertEqual(by_date["2026-11-05"]["p_lag2_mm"], "")

    def test_sample_pipeline_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = hbe.run_sample_pipeline("meric", "h64", GEOJSON_PATH, Path(tmp))
            self.assertEqual(summary["basin_code"], "TR01")
            self.assertEqual(summary["days"], 6)
            self.assertGreater(summary["grid_points"], 50)
            grid_path = Path(summary["out_grid_csv"])
            anfis_path = Path(summary["out_anfis_csv"])
            self.assertTrue(grid_path.exists())
            self.assertTrue(anfis_path.exists())

            with open(grid_path, encoding="utf-8") as f:
                header = next(csv.reader(f))
                self.assertEqual(header, ["x", "time", "lat", "lon", "Rainfall"])

    def test_netcdf_h64_roundtrip_if_available(self):
        try:
            import netCDF4 as nc  # noqa: F401
            import numpy as np
        except ImportError:
            self.skipTest("netCDF4/numpy yüklü değil")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            # 3 gün sentetik H64 NetCDF4 (acc_rr) + rastgele NaN/fill
            for idx, ymd in enumerate(("20261108", "20261109", "20261110")):
                nc_path = tmp_dir / f"h64_{ymd}_0000_24_hea.nc"
                with nc.Dataset(str(nc_path), "w") as ds:
                    ds.end_of_accumulation_time = f"{ymd}T00:00Z"
                    ds.createDimension("latitude", 3)
                    ds.createDimension("longitude", 3)
                    lat = ds.createVariable("latitude", "f4", ("latitude",))
                    lon = ds.createVariable("longitude", "f4", ("longitude",))
                    acc = ds.createVariable("acc_rr", "f4", ("latitude", "longitude"), fill_value=-9999.0)
                    lat[:] = np.array([41.25, 41.40, 37.9], dtype="f4")  # 37.9 Meriç dışı!
                    lon[:] = np.array([27.15, 27.35, 40.2], dtype="f4")  # 40.2 Meriç dışı!
                    grid = np.full((3, 3), -9999.0, dtype="f4")
                    grid[0:2, 0:2] = float((idx + 1) * 6.0)
                    acc[:] = grid

            out_dir = tmp_dir / "out"
            rc = hbe.main(
                [
                    "--product",
                    "h64",
                    "--basin",
                    "meric",
                    "--geojson",
                    str(GEOJSON_PATH),
                    "--input-dir",
                    str(tmp_dir),
                    "--out-dir",
                    str(out_dir),
                ]
            )
            self.assertEqual(rc, 0)
            anfis_csv = out_dir / "hsaf_h64_meric_anfis.csv"
            self.assertTrue(anfis_csv.exists())
            with open(anfis_csv, encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[-1]["date"], "2026-11-10")
            self.assertEqual(float(rows[-1]["mean_precip_mm"]), 18.0)
            self.assertEqual(float(rows[-1]["p_lag2_mm"]), 6.0)


if __name__ == "__main__":
    unittest.main()
