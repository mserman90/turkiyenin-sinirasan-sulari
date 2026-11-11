<#
.SYNOPSIS
  DSİ 11. Bölge Müdürlüğü (https://edirnenehir.dsi.gov.tr/) Meriç–Tunca–Ergene
  günlük nehir debisi çekicisi (Windows yerel / Türkiye IP, Node.js gerektirmez).

.DESCRIPTION
  GitHub barındırılan ABD runner'ları DSİ (212.174.165.59) tarafından ağ düzeyinde
  düşürüldüğü için bu betik yerleşik curl.exe + PowerShell kullanarak doğrudan
  Türkiye üzerinden güncel debi tablosunu çeker ve data/edirne_debi.json dosyasını günceller.

.PARAMETER Push
  data/edirne_debi.json dosyasında değişiklik varsa otomatik git commit + push yapar.

.PARAMETER InstallSchedule
  Windows Görev Zamanlayıcı üzerinde TSİ 08:35, 14:35 ve 20:35 için günlük otomatik
  güncelleme görevi tanımlar (yalnızca kullanıcı istediğinde çalıştırılır).
#>
param(
  [switch]$Push,
  [switch]$InstallSchedule
)

$ErrorActionPreference = 'Stop'

$RepoDir = Split-Path -Parent $PSScriptRoot
$OutFile = Join-Path $RepoDir 'data\edirne_debi.json'
$SourceUrl = 'https://edirnenehir.dsi.gov.tr/'
$MaxHistoryDays = 120

if ($InstallSchedule) {
  $scriptPath = $PSCommandPath
  $cmd = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`" -Push"
  $slots = @(
    @{ Name = 'DSIEdirneDebi_0835'; Time = '08:35' },
    @{ Name = 'DSIEdirneDebi_1435'; Time = '14:35' },
    @{ Name = 'DSIEdirneDebi_2035'; Time = '20:35' }
  )
  foreach ($s in $slots) {
    schtasks /Create /TN $s.Name /TR $cmd /SC DAILY /ST $s.Time /F | Out-Null
    Write-Output "Zamanlanmış görev kuruldu: $($s.Name) ($($s.Time))"
  }
  exit 0
}

function ConvertTo-NormKey([string]$Text) {
  if ([string]::IsNullOrEmpty($Text)) { return '' }
  $s = $Text `
    -replace 'İ', 'I' `
    -replace 'I', 'i' `
    -replace 'ı', 'i' `
    -replace '[Şş]', 's' `
    -replace '[Ğğ]', 'g' `
    -replace '[Üü]', 'u' `
    -replace '[Öö]', 'o' `
    -replace '[Çç]', 'c'
  return ($s.ToLowerInvariant() -replace '[^a-z0-9]+', '')
}

function ConvertFrom-HtmlText([string]$HtmlFragment) {
  if ([string]::IsNullOrEmpty($HtmlFragment)) { return '' }
  $noTags = $HtmlFragment -replace '<[^>]+>', ''
  $decoded = [System.Net.WebUtility]::HtmlDecode($noTags)
  return (($decoded -replace '\s+', ' ').Trim())
}

$StationMeta = @{
  'tunca_elhova'           = @{ id = 'tunca_elhova'; river = 'TUNCA'; name = 'Elhova'; country = 'BG'; lat = 42.1724; lon = 26.5676 }
  'tunca_suakacagi'        = @{ id = 'tunca_suakacagi'; river = 'TUNCA'; name = 'Suakacağı'; country = 'TR'; lat = 41.8478; lon = 26.5794 }
  'tunca_degirmenyeni'     = @{ id = 'tunca_degirmenyeni'; river = 'TUNCA'; name = 'Değirmenyeni'; country = 'TR'; lat = 41.7350; lon = 26.5480 }
  'meric_harmanli'         = @{ id = 'meric_harmanli'; river = 'MERİÇ'; name = 'Harmanlı'; country = 'BG'; lat = 41.9303; lon = 25.9015 }
  'meric_svilengrad'       = @{ id = 'meric_svilengrad'; river = 'MERİÇ'; name = 'Svilengrad'; country = 'BG'; lat = 41.7682; lon = 26.1979 }
  'meric_kirishane'        = @{ id = 'meric_kirishane'; river = 'MERİÇ'; name = 'Kirişhane'; country = 'TR'; dsi_code = 'D01A003'; lat = 41.6472; lon = 26.5722 }
  'meric_ipsala'           = @{ id = 'meric_ipsala'; river = 'MERİÇ'; name = 'İpsala'; country = 'TR'; lat = 40.9217; lon = 26.3840 }
  'ergene_inanli'          = @{ id = 'ergene_inanli'; river = 'ERGENE'; name = 'İnanlı'; country = 'TR'; lat = 41.2029; lon = 27.4727 }
  'ergene_luleburgaz'      = @{ id = 'ergene_luleburgaz'; river = 'ERGENE'; name = 'Lüleburgaz'; country = 'TR'; lat = 41.4041; lon = 27.3555 }
  'ergene_yenicegorece'    = @{ id = 'ergene_yenicegorece'; river = 'ERGENE'; name = 'Yenicegörece'; country = 'TR'; lat = 41.0840; lon = 26.5350 }
  'ardanehri_ivoylovgrad'  = @{ id = 'arda_ivoylovgrad'; river = 'ARDA'; name = 'Ivoylovgrad'; country = 'BG'; lat = 41.5290; lon = 26.1250 }
}

$tmpHtml = Join-Path $env:TEMP ("edirne_dsi_" + [guid]::NewGuid().ToString('N') + '.html')
try {
  $ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
  $httpCode = $null
  for ($attempt = 1; $attempt -le 3; $attempt++) {
    $httpCode = & curl.exe -sS -L -m 20 -A $ua -o $tmpHtml -w '%{http_code}' $SourceUrl
    if ($LASTEXITCODE -eq 0 -and $httpCode -eq '200' -and (Test-Path $tmpHtml) -and (Get-Item $tmpHtml).Length -gt 20000) {
      break
    }
    Start-Sleep -Seconds ($attempt * 2)
  }

  if (-not (Test-Path $tmpHtml) -or $httpCode -ne '200') {
    throw "DSİ 11. Bölge sitesine erişilemedi (HTTP=$httpCode, exit=$LASTEXITCODE)"
  }

  $html = [System.IO.File]::ReadAllText($tmpHtml, [System.Text.Encoding]::UTF8)
} finally {
  if (Test-Path $tmpHtml) { Remove-Item $tmpHtml -Force -ErrorAction SilentlyContinue }
}

$h5Match = [regex]::Match($html, '<h5[^>]*>([\s\S]*?)</h5>', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
$headingText = if ($h5Match.Success) { ConvertFrom-HtmlText $h5Match.Groups[1].Value } else { '' }
$dateMatch = [regex]::Match($headingText, '(\d{2})\.(\d{2})\.(\d{4})')
if (-not $dateMatch.Success) {
  throw "Sayfa başlığından ölçüm tarihi okunamadı: '$headingText'"
}
$displayDate = "$($dateMatch.Groups[1].Value).$($dateMatch.Groups[2].Value).$($dateMatch.Groups[3].Value)"
$isoDate = "$($dateMatch.Groups[3].Value)-$($dateMatch.Groups[2].Value)-$($dateMatch.Groups[1].Value)"

$pivotIdx = $html.IndexOf('id="ASPxPivotGrid2"')
if ($pivotIdx -lt 0) {
  throw 'Sayfada #ASPxPivotGrid2 tablosu bulunamadı.'
}
$slice = $html.Substring($pivotIdx)

$rows = New-Object System.Collections.Generic.List[object]
$currentRiver = ''
$trMatches = [regex]::Matches($slice, '<tr[^>]*>([\s\S]*?)</tr>', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
foreach ($tr in $trMatches) {
  $trHtml = $tr.Groups[1].Value
  $rfMatches = [regex]::Matches($trHtml, '<td[^>]*class="[^"]*dxpgRowFieldValue_Youthful[^"]*"[^>]*>([\s\S]*?)</td>', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
  $dcMatches = [regex]::Matches($trHtml, '<td[^>]*class="[^"]*dxpgCell_Youthful[^"]*"[^>]*>([\s\S]*?)</td>', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
  if ($rfMatches.Count -eq 0 -or $dcMatches.Count -eq 0) { continue }

  $rf = @($rfMatches | ForEach-Object { ConvertFrom-HtmlText $_.Groups[1].Value })
  $dc = @($dcMatches | ForEach-Object { ConvertFrom-HtmlText $_.Groups[1].Value })

  $river = $currentRiver
  $station = ''
  $hour = ''
  if ($rf.Count -ge 3) {
    $river = $rf[0]
    $station = $rf[1]
    $hour = $rf[2]
    $currentRiver = $river
  } elseif ($rf.Count -eq 2) {
    $station = $rf[0]
    $hour = $rf[1]
  } else {
    continue
  }

  if ($station -match '(?i)toplam|total' -or $river -match '(?i)toplam|total') { continue }

  $rawVal = $dc[$dc.Count - 1]
  $normNum = ($rawVal -replace '\s+', '') -replace ',', '.'
  [double]$parsedNum = 0.0
  $hasNum = [double]::TryParse($normNum, [System.Globalization.NumberStyles]::Float, [System.Globalization.CultureInfo]::InvariantCulture, [ref]$parsedNum)

  $rows.Add([pscustomobject]@{
    river         = $river.Trim()
    name          = $station.Trim()
    time          = if ($hour.Trim()) { $hour.Trim() } else { '08:00' }
    discharge_m3s = if ($hasNum) { $parsedNum } else { $null }
  })
}

if ($rows.Count -eq 0) {
  throw "ASPxPivotGrid2 tablosundan hiç istasyon satırı okunamadı (tarih=$isoDate)."
}

$nowUtc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$latestStations = New-Object System.Collections.Generic.List[object]
$stationDict = [ordered]@{}

foreach ($r in $rows) {
  $key = "$(ConvertTo-NormKey $r.river)_$(ConvertTo-NormKey $r.name)"
  $meta = $StationMeta[$key]
  $item = [ordered]@{
    id      = if ($meta) { $meta.id } else { $key }
    river   = if ($meta) { $meta.river } else { $r.river }
    name    = if ($meta) { $meta.name } else { $r.name }
    country = if ($meta) { $meta.country } else { 'TR' }
  }
  if ($meta -and $meta.ContainsKey('dsi_code')) {
    $item['dsi_code'] = $meta.dsi_code
  }
  $item['time'] = $r.time
  $item['discharge_m3s'] = $r.discharge_m3s
  $item['lat'] = if ($meta) { $meta.lat } else { $null }
  $item['lon'] = if ($meta) { $meta.lon } else { $null }
  $latestStations.Add([pscustomobject]$item)

  if ($null -ne $r.discharge_m3s) {
    $stationDict[$item['id']] = $r.discharge_m3s
  }
}

$historyByDate = @{}
if (Test-Path $OutFile) {
  try {
    $existing = Get-Content -Raw -Encoding UTF8 $OutFile | ConvertFrom-Json
    if ($existing.history) {
      foreach ($h in $existing.history) {
        if ($h.date -and $h.stations) {
          $historyByDate[$h.date] = [pscustomobject]@{
            date           = $h.date
            display_date   = $h.display_date
            fetched_at_utc = $h.fetched_at_utc
            stations       = $h.stations
          }
        }
      }
    }
  } catch {
    Write-Warning "Mevcut JSON arşivi okunamadı, temiz arşiv oluşturuluyor: $($_.Exception.Message)"
  }
}

$historyByDate[$isoDate] = [pscustomobject]@{
  date           = $isoDate
  display_date   = $displayDate
  fetched_at_utc = $nowUtc
  stations       = [pscustomobject]$stationDict
}

$sortedDates = @($historyByDate.Keys | Sort-Object)
if ($sortedDates.Count -gt $MaxHistoryDays) {
  $sortedDates = @($sortedDates | Select-Object -Last $MaxHistoryDays)
}
$historyList = New-Object System.Collections.Generic.List[object]
foreach ($d in $sortedDates) {
  $historyList.Add($historyByDate[$d])
}

$payload = [pscustomobject]@{
  source_url     = $SourceUrl
  source_title   = 'DSİ 11. Bölge Müdürlüğü — Nehir Debileri'
  date           = $isoDate
  display_date   = $displayDate
  fetched_at_utc = $nowUtc
  status         = 'ok'
  stations       = $latestStations.ToArray()
  history        = $historyList.ToArray()
}

$outDir = Split-Path -Parent $OutFile
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
$jsonText = ($payload | ConvertTo-Json -Depth 6) -replace "`r`n", "`n"
[System.IO.File]::WriteAllText($OutFile, "$jsonText`n", [System.Text.UTF8Encoding]::new($false))
Write-Output "OK: $OutFile güncellendi (date=$isoDate, stations=$($latestStations.Count), history=$($historyList.Count), kirishane=$($stationDict['meric_kirishane']))"

if ($Push) {
  Push-Location $RepoDir
  try {
    git diff --quiet -- data/edirne_debi.json
    if ($LASTEXITCODE -eq 0) {
      Write-Output 'Değişiklik yok, git push atlandı.'
    } else {
      git add data/edirne_debi.json
      git commit -m "chore: update Edirne Meric-Tunca-Ergene river discharge ($isoDate) [skip ci]"
      git push origin main
      Write-Output 'GitHub Pages deposuna push tamamlandı.'
    }
  } finally {
    Pop-Location
  }
}
