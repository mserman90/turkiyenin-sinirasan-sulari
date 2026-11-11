/**
 * DSİ 11. Bölge Müdürlüğü (https://edirnenehir.dsi.gov.tr/) Meriç–Tunca–Ergene
 * günlük nehir debisi çekicisi (Headless Chromium / Playwright).
 * GitHub Actions tarafından çalıştırılıp data/edirne_debi.json dosyasını günceller.
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
let playwrightMod;
try {
  playwrightMod = require('playwright');
} catch {
  playwrightMod = require('/tmp/pw/node_modules/playwright');
}
const { chromium } = playwrightMod;

const SOURCE_URL = 'https://edirnenehir.dsi.gov.tr/';
const OUT_FILE = path.resolve(process.cwd(), 'data', 'edirne_debi.json');
const MAX_HISTORY_DAYS = 120;
const BACKFILL_TARGET_DAYS = 7;

const STATION_META = {
  tunca_elhova: { id: 'tunca_elhova', river: 'TUNCA', name: 'Elhova', country: 'BG', lat: 42.1724, lon: 26.5676 },
  tunca_suakacagi: { id: 'tunca_suakacagi', river: 'TUNCA', name: 'Suakacağı', country: 'TR', lat: 41.8478, lon: 26.5794 },
  tunca_degirmenyeni: { id: 'tunca_degirmenyeni', river: 'TUNCA', name: 'Değirmenyeni', country: 'TR', lat: 41.7350, lon: 26.5480 },
  meric_harmanli: { id: 'meric_harmanli', river: 'MERİÇ', name: 'Harmanlı', country: 'BG', lat: 41.9303, lon: 25.9015 },
  meric_svilengrad: { id: 'meric_svilengrad', river: 'MERİÇ', name: 'Svilengrad', country: 'BG', lat: 41.7682, lon: 26.1979 },
  meric_kirishane: { id: 'meric_kirishane', river: 'MERİÇ', name: 'Kirişhane', country: 'TR', dsi_code: 'D01A003', lat: 41.6472, lon: 26.5722 },
  meric_ipsala: { id: 'meric_ipsala', river: 'MERİÇ', name: 'İpsala', country: 'TR', lat: 40.9217, lon: 26.3840 },
  ergene_inanli: { id: 'ergene_inanli', river: 'ERGENE', name: 'İnanlı', country: 'TR', lat: 41.2029, lon: 27.4727 },
  ergene_luleburgaz: { id: 'ergene_luleburgaz', river: 'ERGENE', name: 'Lüleburgaz', country: 'TR', lat: 41.4041, lon: 27.3555 },
  ergene_yenicegorece: { id: 'ergene_yenicegorece', river: 'ERGENE', name: 'Yenicegörece', country: 'TR', lat: 41.0840, lon: 26.5350 },
  ardanehri_ivoylovgrad: { id: 'arda_ivoylovgrad', river: 'ARDA', name: 'Ivoylovgrad', country: 'BG', lat: 41.5290, lon: 26.1250 }
};

function normKey(str) {
  return String(str || '')
    .replace(/İ/g, 'I')
    .replace(/I/g, 'i')
    .replace(/ı/g, 'i')
    .replace(/[Şş]/g, 's')
    .replace(/[Ğğ]/g, 'g')
    .replace(/[Üü]/g, 'u')
    .replace(/[Öö]/g, 'o')
    .replace(/[Çç]/g, 'c')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '');
}

function formatIsoToDisplay(isoDate) {
  const [y, m, d] = isoDate.split('-');
  return `${d}.${m}.${y}`;
}

function shiftIsoDate(isoDate, deltaDays) {
  const d = new Date(`${isoDate}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + deltaDays);
  return d.toISOString().slice(0, 10);
}

async function extractCurrentPivot(page) {
  return page.evaluate(() => {
    const h5 = document.querySelector('#about h5');
    const headingText = h5 ? h5.textContent.trim() : '';
    const dateMatch = headingText.match(/(\d{2})\.(\d{2})\.(\d{4})/);
    const displayDate = dateMatch ? `${dateMatch[1]}.${dateMatch[2]}.${dateMatch[3]}` : null;
    const isoDate = dateMatch ? `${dateMatch[3]}-${dateMatch[2]}-${dateMatch[1]}` : null;

    const table = document.querySelector('#ASPxPivotGrid2');
    if (!table) {
      return { headingText, displayDate, isoDate, rows: [] };
    }

    const rows = [];
    let currentRiver = '';
    const trList = Array.from(table.querySelectorAll('tr'));

    for (const tr of trList) {
      const rowFieldCells = Array.from(tr.querySelectorAll('td.dxpgRowFieldValue_Youthful'))
        .map(td => td.textContent.replace(/\s+/g, ' ').trim());
      const dataCells = Array.from(tr.querySelectorAll('td.dxpgCell_Youthful'))
        .map(td => td.textContent.replace(/\s+/g, ' ').trim());

      if (rowFieldCells.length === 0 || dataCells.length === 0) continue;

      let river = currentRiver;
      let station = '';
      let hour = '';

      if (rowFieldCells.length >= 3) {
        river = rowFieldCells[0];
        station = rowFieldCells[1];
        hour = rowFieldCells[2];
        currentRiver = river;
      } else if (rowFieldCells.length === 2) {
        station = rowFieldCells[0];
        hour = rowFieldCells[1];
      } else {
        continue;
      }

      if (/toplam|total/i.test(station) || /toplam|total/i.test(river)) continue;

      const rawVal = dataCells[dataCells.length - 1];
      const normalized = rawVal.replace(/\s+/g, '').replace(',', '.');
      const parsedVal = Number.parseFloat(normalized);

      rows.push({
        river: river.trim(),
        name: station.trim(),
        time: hour.trim() || '08:00',
        raw_value: rawVal,
        discharge_m3s: Number.isFinite(parsedVal) ? parsedVal : null
      });
    }

    return { headingText, displayDate, isoDate, rows };
  });
}

function enrichStations(rows) {
  return rows.map((row) => {
    const key = `${normKey(row.river)}_${normKey(row.name)}`;
    const meta = STATION_META[key];
    return {
      id: meta?.id || key,
      river: meta?.river || row.river,
      name: meta?.name || row.name,
      country: meta?.country || 'TR',
      ...(meta?.dsi_code ? { dsi_code: meta.dsi_code } : {}),
      time: row.time,
      discharge_m3s: row.discharge_m3s,
      lat: meta?.lat ?? null,
      lon: meta?.lon ?? null
    };
  });
}

async function readExistingJson() {
  try {
    const raw = await fs.readFile(OUT_FILE, 'utf8');
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

async function main() {
  const existing = await readExistingJson();
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage']
  });

  try {
    const context = await browser.newContext({
      ignoreHTTPSErrors: true,
      locale: 'tr-TR',
      viewport: { width: 1280, height: 900 }
    });
    const page = await context.newPage();

    let loaded = false;
    let lastErr = null;
    for (let attempt = 1; attempt <= 3; attempt++) {
      try {
        await page.goto(SOURCE_URL, { waitUntil: 'domcontentloaded', timeout: 45000 });
        await page.waitForSelector('#ASPxPivotGrid2', { timeout: 30000 });
        loaded = true;
        break;
      } catch (err) {
        lastErr = err;
        console.warn(`Attempt ${attempt} failed: ${err.message}`);
        await page.waitForTimeout(2000 * attempt);
      }
    }

    if (!loaded) {
      throw new Error(`Could not load ${SOURCE_URL}: ${lastErr?.message || 'unknown error'}`);
    }

    const latest = await extractCurrentPivot(page);
    if (!latest.rows.length || !latest.isoDate) {
      throw new Error(`Pivot table yielded no rows (heading="${latest.headingText}")`);
    }

    const nowUtc = new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
    const latestStations = enrichStations(latest.rows);

    const historyMap = new Map();
    if (Array.isArray(existing?.history)) {
      for (const h of existing.history) {
        if (h?.date && h?.stations && typeof h.stations === 'object') {
          historyMap.set(h.date, h);
        }
      }
    }

    const toStationDict = (stations) => {
      const obj = {};
      for (const s of stations) {
        if (typeof s.discharge_m3s === 'number' && Number.isFinite(s.discharge_m3s)) {
          obj[s.id] = s.discharge_m3s;
        }
      }
      return obj;
    };

    historyMap.set(latest.isoDate, {
      date: latest.isoDate,
      display_date: latest.displayDate,
      fetched_at_utc: nowUtc,
      stations: toStationDict(latestStations)
    });

    // Geçmiş gün sayısı yetersizse eksik son günleri nazikçe sorgula
    if (historyMap.size < BACKFILL_TARGET_DAYS) {
      for (let d = 1; d < BACKFILL_TARGET_DAYS; d++) {
        const targetIso = shiftIsoDate(latest.isoDate, -d);
        if (historyMap.has(targetIso)) continue;
        const targetDisplay = formatIsoToDisplay(targetIso);
        try {
          const prevHeading = await page.locator('#about h5').textContent().catch(() => '');
          await page.evaluate((dateText) => {
            if (window.ASPxDateEdit1 && typeof window.ASPxDateEdit1.SetText === 'function') {
              window.ASPxDateEdit1.SetText(dateText);
            }
          }, targetDisplay);
          await page.fill('#ASPxDateEdit1_I', targetDisplay);
          await page.locator('#ASPxDateEdit1_I').press('Tab');
          await Promise.all([
            page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 25000 }).catch(() => null),
            page.click('#Button2')
          ]);
          await page.waitForSelector('#ASPxPivotGrid2', { timeout: 20000 });
          const afterHeading = await page.locator('#about h5').textContent().catch(() => '');
          if (afterHeading && afterHeading !== prevHeading) {
            const snap = await extractCurrentPivot(page);
            if (snap.isoDate === targetIso && snap.rows.length > 0) {
              const enriched = enrichStations(snap.rows);
              historyMap.set(snap.isoDate, {
                date: snap.isoDate,
                display_date: snap.displayDate,
                fetched_at_utc: nowUtc,
                stations: toStationDict(enriched)
              });
              console.log(`Backfilled ${snap.isoDate}: ${enriched.length} stations`);
            }
          }
          await page.waitForTimeout(1200);
        } catch (bfErr) {
          console.warn(`Backfill skipped for ${targetIso}: ${bfErr.message}`);
        }
      }
    }

    const sortedHistory = Array.from(historyMap.values())
      .sort((a, b) => a.date.localeCompare(b.date))
      .slice(-MAX_HISTORY_DAYS);

    const payload = {
      source_url: SOURCE_URL,
      source_title: 'DSİ 11. Bölge Müdürlüğü — Nehir Debileri',
      date: latest.isoDate,
      display_date: latest.displayDate,
      fetched_at_utc: nowUtc,
      status: 'ok',
      stations: latestStations,
      history: sortedHistory
    };

    await fs.mkdir(path.dirname(OUT_FILE), { recursive: true });
    await fs.writeFile(OUT_FILE, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
    console.log(`Updated ${OUT_FILE}: date=${payload.date}, stations=${latestStations.length}, history=${sortedHistory.length}`);
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
