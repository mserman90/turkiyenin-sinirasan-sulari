/**
 * DSİ 11. Bölge Müdürlüğü (https://edirnenehir.dsi.gov.tr/) Meriç–Tunca–Ergene
 * günlük nehir debisi çekicisi (Headless Chromium / Playwright).
 * GitHub Actions tarafından çalıştırılıp data/edirne_debi.json dosyasını günceller.
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import dns from 'node:dns/promises';
import net from 'node:net';
import https from 'node:https';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
function loadChromium() {
  for (const modPath of ['playwright', '/tmp/pw/node_modules/playwright']) {
    try {
      return require(modPath).chromium;
    } catch {
      // try next path
    }
  }
  return null;
}

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

const DESKTOP_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';

function decodeHtmlEntities(str) {
  return String(str || '')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/&#(\d+);/g, (_, dec) => String.fromCodePoint(Number.parseInt(dec, 10)))
    .replace(/&#x([0-9a-f]+);/gi, (_, hex) => String.fromCodePoint(Number.parseInt(hex, 16)));
}

function stripTags(html) {
  return decodeHtmlEntities(String(html || '').replace(/<[^>]+>/g, ''))
    .replace(/\s+/g, ' ')
    .trim();
}

function parsePivotFromHtml(html) {
  const h5Match = html.match(/<h5[^>]*>([\s\S]*?)<\/h5>/i);
  const headingText = h5Match ? stripTags(h5Match[1]) : '';
  const dateMatch = headingText.match(/(\d{2})\.(\d{2})\.(\d{4})/);
  const displayDate = dateMatch ? `${dateMatch[1]}.${dateMatch[2]}.${dateMatch[3]}` : null;
  const isoDate = dateMatch ? `${dateMatch[3]}-${dateMatch[2]}-${dateMatch[1]}` : null;

  const pivotStart = html.indexOf('id="ASPxPivotGrid2"');
  if (pivotStart < 0) {
    return { headingText, displayDate, isoDate, rows: [] };
  }

  const slice = html.slice(pivotStart);
  const rows = [];
  let currentRiver = '';
  const trRegex = /<tr[^>]*>([\s\S]*?)<\/tr>/gi;
  let trMatch;

  while ((trMatch = trRegex.exec(slice)) !== null) {
    const trHtml = trMatch[1];
    const rowFieldCells = Array.from(
      trHtml.matchAll(/<td[^>]*class="[^"]*dxpgRowFieldValue_Youthful[^"]*"[^>]*>([\s\S]*?)<\/td>/gi),
      (m) => stripTags(m[1])
    );
    const dataCells = Array.from(
      trHtml.matchAll(/<td[^>]*class="[^"]*dxpgCell_Youthful[^"]*"[^>]*>([\s\S]*?)<\/td>/gi),
      (m) => stripTags(m[1])
    );

    if (rowFieldCells.length === 0 || dataCells.length === 0) continue;

    let river = currentRiver;
    let station = '';
    let hour = '';

    if (rowFieldCells.length >= 3) {
      [river, station, hour] = rowFieldCells;
      currentRiver = river;
    } else if (rowFieldCells.length === 2) {
      [station, hour] = rowFieldCells;
    } else {
      continue;
    }

    if (/toplam|total/i.test(station) || /toplam|total/i.test(river)) continue;

    const rawVal = dataCells[dataCells.length - 1];
    const parsedVal = Number.parseFloat(rawVal.replace(/\s+/g, '').replace(',', '.'));
    rows.push({
      river: river.trim(),
      name: station.trim(),
      time: hour.trim() || '08:00',
      raw_value: rawVal,
      discharge_m3s: Number.isFinite(parsedVal) ? parsedVal : null
    });
  }

  return { headingText, displayDate, isoDate, rows };
}

async function probeTcp443(host, timeoutMs = 6000) {
  const started = Date.now();
  return new Promise((resolve) => {
    const sock = net.connect({ host, port: 443 });
    let done = false;
    const finish = (status) => {
      if (done) return;
      done = true;
      sock.destroy();
      resolve({ status, ms: Date.now() - started });
    };
    sock.setTimeout(timeoutMs);
    sock.on('connect', () => finish('ok'));
    sock.on('timeout', () => finish(`timeout_${timeoutMs}ms`));
    sock.on('error', (err) => finish(`err:${err.code || err.message}`));
  });
}

async function fetchHttpsHtml(urlStr, timeoutMs = 12000) {
  return new Promise((resolve) => {
    const req = https.get(
      urlStr,
      {
        rejectUnauthorized: false,
        timeout: timeoutMs,
        headers: {
          'User-Agent': DESKTOP_UA,
          'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
          'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8'
        }
      },
      (res) => {
        const chunks = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => {
          const html = Buffer.concat(chunks).toString('utf8');
          resolve({ status: res.statusCode || 0, html, error: null });
        });
      }
    );
    req.on('timeout', () => {
      req.destroy(new Error(`https_timeout_${timeoutMs}ms`));
    });
    req.on('error', (err) => {
      resolve({ status: 0, html: '', error: err.code || err.message });
    });
  });
}

async function probeAndFetchHtml(urlStr) {
  const hostname = new URL(urlStr).hostname;
  let ip = null;
  let dnsErr = null;
  try {
    const res = await dns.lookup(hostname);
    ip = res.address;
  } catch (err) {
    dnsErr = err.code || err.message;
  }

  const tcp = ip ? await probeTcp443(ip, 6000) : { status: `dns_failed:${dnsErr}`, ms: 0 };
  const httpRes = tcp.status === 'ok'
    ? await fetchHttpsHtml(urlStr, 12000)
    : { status: 0, html: '', error: `skipped_due_to_${tcp.status}` };

  return {
    ip,
    dnsErr,
    tcpStatus: tcp.status,
    tcpMs: tcp.ms,
    httpStatus: httpRes.status,
    httpError: httpRes.error,
    html: httpRes.html
  };
}

async function main() {
  const existing = await readExistingJson();
  const diag = await probeAndFetchHtml(SOURCE_URL);
  const ssrLatest = diag.html ? parsePivotFromHtml(diag.html) : null;
  const ssrOk = Boolean(ssrLatest?.rows?.length && ssrLatest?.isoDate);

  console.log(
    `::notice::PROBE ip=${diag.ip || 'none'} tcp=${diag.tcpStatus}(${diag.tcpMs}ms) https=${diag.httpStatus || diag.httpError} bytes=${diag.html?.length || 0} ssr_rows=${ssrLatest?.rows?.length || 0}`
  );

  let latest = ssrOk ? ssrLatest : null;
  let pwError = null;
  const chromium = loadChromium();

  const browser = chromium
    ? await chromium.launch({
        headless: true,
        args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-http2', '--disable-blink-features=AutomationControlled']
      })
    : null;

  try {
    let page = null;
    let loaded = false;

    if (browser) {
      const context = await browser.newContext({
        ignoreHTTPSErrors: true,
        userAgent: DESKTOP_UA,
        locale: 'tr-TR',
        viewport: { width: 1280, height: 900 }
      });
      page = await context.newPage();

      const maxAttempts = diag.tcpStatus === 'ok' ? 2 : 1;
      for (let attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
          await page.goto(SOURCE_URL, { waitUntil: 'domcontentloaded', timeout: 15000 });
          await page.waitForSelector('#ASPxPivotGrid2', { timeout: 10000 });
          loaded = true;
          break;
        } catch (err) {
          pwError = err.message.split('\n')[0];
          console.warn(`Attempt ${attempt} failed: ${pwError}`);
          await page.waitForTimeout(1500);
        }
      }
    } else {
      pwError = 'playwright_not_installed';
    }

    if (loaded && page) {
      const domLatest = await extractCurrentPivot(page);
      if (domLatest.rows.length > 0 && domLatest.isoDate) {
        latest = domLatest;
      }
    } else if (ssrOk) {
      console.log(`::warning::Playwright navigation failed (${pwError}); proceeding with direct HTTPS SSR HTML (${latest.rows.length} rows).`);
    }

    if (!latest || !latest.rows.length || !latest.isoDate) {
      const reason = `Fetch failed: ip=${diag.ip || diag.dnsErr} tcp=${diag.tcpStatus} https=${diag.httpStatus || diag.httpError} ssr_rows=${ssrLatest?.rows?.length || 0} pw=${pwError || 'n/a'}`;
      console.log(`::error::${reason}`);
      throw new Error(reason);
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

    // Geçmiş gün sayısı yetersizse eksik son günleri nazikçe sorgula (Playwright sayfası yüklendiyse)
    if (loaded && page && historyMap.size < BACKFILL_TARGET_DAYS) {
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
            page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 20000 }).catch(() => null),
            page.click('#Button2')
          ]);
          await page.waitForSelector('#ASPxPivotGrid2', { timeout: 15000 });
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
          await page.waitForTimeout(1000);
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
    console.log(`::notice::Updated data/edirne_debi.json: date=${payload.date}, stations=${latestStations.length}, history=${sortedHistory.length}`);
  } finally {
    if (browser) await browser.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
