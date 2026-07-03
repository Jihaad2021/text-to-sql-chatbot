/**
 * renderer.js — DOM rendering for Settlement AI chat interface. v8
 * Telkomsel warm beige design: KPI cards, horizontal bars, insight callout, table, quick replies.
 */

export {
  appendUserMessage,
  appendLoadingMessage,
  appendAssistantMessage,
  appendErrorMessage,
  appendClarificationMessage,
  removeElement,
}

const _chartConfigs = new Map()

// ─────────────────────────────────────────────────────────────
// User message
// ─────────────────────────────────────────────────────────────

function appendUserMessage(container, text) {
  const el = make(`
    <div class="msg-enter" style="display:flex;justify-content:flex-end;">
      <div style="max-width:62%;padding:11px 16px;background:#2A2724;color:#fff;
        font-size:13.5px;line-height:1.5;border-radius:14px 14px 3px 14px;
        word-break:break-word;">
        ${esc(text)}
      </div>
    </div>
  `)
  container.appendChild(el)
}

// ─────────────────────────────────────────────────────────────
// Loading message
// ─────────────────────────────────────────────────────────────

function appendLoadingMessage(container) {
  const el = make(`
    <div class="msg-enter" style="display:flex;gap:12px;align-items:flex-start;">
      ${aiAvatar()}
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:14px 18px;display:inline-flex;align-items:center;gap:7px;">
        <span class="loading-dot"></span>
        <span class="loading-dot"></span>
        <span class="loading-dot"></span>
      </div>
    </div>
  `)
  container.appendChild(el)
  return el
}

function removeElement(el) { el?.remove() }

// ─────────────────────────────────────────────────────────────
// Error message
// ─────────────────────────────────────────────────────────────

function appendErrorMessage(container, message) {
  const el = make(`
    <div class="msg-enter" style="display:flex;gap:12px;align-items:flex-start;">
      ${aiAvatar()}
      <div style="background:var(--danger-soft);border:1px solid #F0C1CA;border-radius:var(--radius);padding:14px 18px;max-width:560px;">
        <p style="font-size:13px;font-weight:600;color:var(--danger);margin:0 0 4px;">Terjadi kesalahan</p>
        <p style="font-size:13px;color:#5B1524;margin:0;line-height:1.5;">${esc(message)}</p>
      </div>
    </div>
  `)
  container.appendChild(el)
}

// ─────────────────────────────────────────────────────────────
// Clarification message
// ─────────────────────────────────────────────────────────────

function appendClarificationMessage(container, reason) {
  const el = make(`
    <div class="msg-enter" style="display:flex;gap:12px;align-items:flex-start;">
      ${aiAvatar()}
      <div style="background:var(--warn-soft);border:1px solid #F0D9A0;border-radius:var(--radius);padding:14px 18px;max-width:520px;">
        <p style="font-size:13px;font-weight:600;color:var(--warn);margin:0 0 4px;">Pertanyaan perlu diperjelas</p>
        <p style="font-size:13px;color:#5B3A00;margin:0;line-height:1.5;">${esc(reason || 'Mohon berikan detail yang lebih spesifik.')}</p>
      </div>
    </div>
  `)
  container.appendChild(el)
}

// ─────────────────────────────────────────────────────────────
// Main assistant message
// ─────────────────────────────────────────────────────────────

function appendAssistantMessage(container, result) {
  const gid       = 'g' + Date.now() + Math.random().toString(36).slice(2, 6)
  const isMulti   = result.is_multi_step && result.step_results?.length > 0
  const hasData   = result.data?.length > 0
  const hasSql    = Boolean(result.sql)
  const chartList = result.chart_configs?.length ? result.chart_configs : (result.chart_config ? [result.chart_config] : [])
  const hasCharts = chartList.length > 0
  const toolCalls = result.tool_calls ?? []
  const intent    = result.metadata?.intent?.category ?? result.intent?.category ?? ''
  const errors    = result.metadata?.errors ?? []
  const rowCount  = result.row_count ?? 0

  // Auto-detect display format
  const showKpi  = !isMulti && hasData && _isKpiData(result.data)
  const showBars = !isMulti && hasData && !showKpi && _isBarsData(result.data)

  let body = ''

  // ── 1. Insight text
  body += `<div class="md-content ai-text">${renderMd(result.insights || '–')}</div>`

  // ── 2. KPI cards
  if (showKpi) body += _buildKpiGrid(result.data)

  // ── 3. Horizontal bar chart (auto-detected from data shape)
  if (showBars) body += _buildHbarSection(result.data)

  // ── 4. Chart.js panels (one per config in chart_configs)
  if (hasCharts && !showBars) {
    chartList.forEach((cfg, i) => {
      body += _buildChartPanel(`${gid}_c${i}`, cfg.title ?? '')
    })
  }

  // ── 5. Anomaly callout (when intent is anomaly-related and data has anomalous rows)
  const isAnomalyIntent = intent.includes('anomal') || intent.includes('root_cause')
  if (isAnomalyIntent && result.insights) body += _buildAnomalyCallout(result.insights, result.data)

  // ── 6. Data table (always show when there's data and not KPI-mode)
  if (hasData && !showKpi) body += _buildTableSection(result.data, rowCount)

  // ── 7. Multi-step accordion
  if (isMulti) body += _buildMultiAccordion(result.step_results, gid)

  // ── 8. Bottom tabs (SQL / Tools / Detail) — collapsed by default
  const hasTabs = hasSql || toolCalls.length > 0
  if (hasTabs) body += _buildBottomTabs(result, gid, hasSql, toolCalls)

  // ── 9. Quick replies
  body += _buildQuickReplies(intent)

  // ── 10. Meta line
  const metaParts = []
  if (rowCount > 0) metaParts.push(`${fmtNum(rowCount)} baris`)
  if (intent) metaParts.push(intent.replace(/_/g, ' '))
  if (errors.length > 0) metaParts.push(`${errors.length} peringatan`)
  if (result.execution_time_ms) metaParts.push(fmtMs(result.execution_time_ms))
  body += `<div class="meta-line">${metaParts.join(' · ')}</div>`

  const el = make(`
    <div class="msg-enter" style="display:flex;flex-direction:column;gap:4px;">
      ${isMulti ? _multiBadge(result.step_results.length) : ''}
      <div style="display:flex;gap:12px;align-items:flex-start;">
        ${aiAvatar()}
        <div class="ai-card">${body}</div>
      </div>
    </div>
  `)

  container.appendChild(el)

  if (hasCharts && !showBars) {
    chartList.forEach((cfg, i) => {
      const cgid = `${gid}_c${i}`
      _chartConfigs.set(cgid, cfg)
      _initChart(el, cgid, cfg)
    })
  }

  _initBottomTabs(el, gid)
  _initAccordion(el, gid)
  _initSortable(el)
  _initCopyBtns(el)
  _initQuickReplies(el)

  // Animate bar fills after DOM paint
  requestAnimationFrame(() => {
    el.querySelectorAll('.hbar-fill[data-w]').forEach(bar => {
      bar.style.width = bar.dataset.w + '%'
    })
  })
}

// ─────────────────────────────────────────────────────────────
// KPI grid
// ─────────────────────────────────────────────────────────────

function _isNumericVal(v) {
  if (typeof v === 'number') return true
  if (typeof v === 'string' && v.trim() !== '') return !isNaN(Number(v.replace(/,/g, '')))
  return false
}

function _toNum(v) {
  if (typeof v === 'number') return v
  if (typeof v === 'string') { const n = Number(v.replace(/,/g, '')); return isNaN(n) ? null : n }
  return null
}

function _isKpiData(data) {
  if (!data?.length || data.length > 6) return false
  const cols = Object.keys(data[0])
  return cols.length >= 1 && cols.length <= 4 &&
    cols.some(c => _isNumericVal(data[0][c]))
}

function _isNegativeCol(c) {
  const n = c.toLowerCase()
  return n.includes('gap') || n.includes('selisih') || n.includes('fail') ||
         n.includes('error') || n.includes('anomal') || n.includes('mater')
}

function _buildKpiGrid(data) {
  const cols     = Object.keys(data[0])
  const labelCol = cols.find(c => !_isNumericVal(data[0][c])) ?? null
  const numCols  = cols.filter(c => _isNumericVal(data[0][c]))
  if (!numCols.length) return ''

  let cards = []
  if (data.length === 1 && numCols.length > 1) {
    cards = numCols.map(c => ({
      label: c.replace(/_/g, ' '), value: data[0][c], delta: null, isWarning: _isNegativeCol(c),
    }))
  } else {
    const valCol   = numCols[0]
    const deltaCol = numCols[1] ?? null
    cards = data.map(row => ({
      label:     labelCol ? String(row[labelCol] ?? '') : valCol.replace(/_/g, ' '),
      value:     row[valCol],
      delta:     deltaCol ? row[deltaCol] : null,
      isWarning: _isNegativeCol(valCol),
    }))
  }
  if (!cards.length) return ''

  const cardHtml = cards.map(({ label, value, delta, isWarning }) => {
    const n  = _toNum(value)
    const bg = isWarning ? '#FCEEDD' : '#FFFFFF'
    const bd = isWarning ? '#F2D3A8' : '#EBE8E3'
    const vc = isWarning ? '#B45309' : '#1C1B1A'
    const lc = isWarning ? '#B45309' : '#8B867E'
    let deltaHtml = ''
    if (delta != null) {
      const dn = _toNum(delta)
      if (dn != null && dn !== 0) {
        const up = dn > 0
        deltaHtml = `<div style="font-size:11.5px;font-weight:600;font-family:'IBM Plex Mono',monospace;font-feature-settings:'tnum' 1;color:${up ? '#0E8A55' : '#B57400'};margin-top:5px;">${up ? '▲' : '▼'} ${fmtBig(Math.abs(dn))}</div>`
      }
    } else if (isWarning) {
      deltaHtml = `<div style="font-size:11.5px;font-weight:600;font-family:'IBM Plex Mono',monospace;color:#B45309;margin-top:5px;">⚑ Perlu tindak lanjut</div>`
    }
    return `<div style="padding:15px;border-radius:14px;border:1px solid ${bd};background:${bg};">
      <div style="font-size:11px;font-weight:600;color:${lc};text-transform:uppercase;letter-spacing:.05em;">${esc(label)}</div>
      <div style="font-size:23px;font-weight:800;letter-spacing:-.6px;font-family:'IBM Plex Mono',monospace;font-feature-settings:'tnum' 1;color:${vc};margin-top:6px;line-height:1.15;">${n != null ? fmtBig(n) : esc(String(value ?? '–'))}</div>
      ${deltaHtml}
    </div>`
  }).join('')

  return `<div style="display:grid;grid-template-columns:repeat(${Math.min(cards.length, 4)},1fr);gap:12px;">${cardHtml}</div>`
}

// ─────────────────────────────────────────────────────────────
// Horizontal bar chart
// ─────────────────────────────────────────────────────────────

function _isDateVal(v) {
  if (typeof v !== 'string') return false
  return /^\d{4}-\d{2}-\d{2}/.test(v.trim())
}

function _isDateCol(colName, firstVal) {
  const n = colName.toLowerCase()
  if (n.includes('date') || n.includes('tanggal') || n.includes('periode') ||
      n.includes('time') || n.includes('bulan') || n.includes('tahun') ||
      n === 'period' || n === 'hari' || n === 'dt' || n === 'month' || n === 'week')
    return true
  return _isDateVal(firstVal)
}

function _isBarsData(data) {
  if (!data?.length || data.length < 2 || data.length > 15) return false
  const cols = Object.keys(data[0])
  if (cols.length < 2) return false
  const labelCol = cols.find(c => !_isNumericVal(data[0][c]))
  if (!labelCol) return false
  // Never use bars for time-series / date data
  if (_isDateCol(labelCol, data[0][labelCol])) return false
  return cols.some(c => _isNumericVal(data[0][c]))
}

function _buildHbarSection(data) {
  const cols     = Object.keys(data[0])
  const labelCol = cols.find(c => !_isNumericVal(data[0][c])) ?? cols[0]
  const valCol   = cols.find(c => c !== labelCol && _isNumericVal(data[0][c]))
  if (!valCol) return ''

  const sorted = [...data].sort((a, b) => (_toNum(b[valCol]) ?? 0) - (_toNum(a[valCol]) ?? 0))
  const maxVal = Math.max(...sorted.map(r => Math.abs(_toNum(r[valCol]) ?? 0)), 1)
  const top    = sorted.slice(0, 12)
  const rest   = sorted.length - top.length

  const vals    = top.map(r => _toNum(r[valCol]) ?? 0)
  const mean    = vals.reduce((s, v) => s + v, 0) / (vals.length || 1)
  const anomIdx = vals.reduce((bi, v, i) => Math.abs(v - mean) > Math.abs(vals[bi] - mean) ? i : bi, 0)

  const rows = top.map((row, idx) => {
    const label  = String(row[labelCol] ?? '–')
    const val    = _toNum(row[valCol]) ?? 0
    const pct    = Math.round((Math.abs(val) / maxVal) * 100)
    const isAnom = idx === anomIdx && vals.length > 2 && Math.abs(vals[anomIdx] - mean) / (mean || 1) > 0.3
    return `<div style="display:flex;align-items:center;gap:12px;">
      <div style="width:118px;flex-shrink:0;text-align:right;font-size:12.5px;font-weight:500;color:#3A3733;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${esc(label)}">${esc(label)}</div>
      <div style="flex:1;height:22px;background:#F2F0EC;border-radius:6px;overflow:hidden;">
        <div class="hbar-fill" data-w="${pct}" style="height:100%;width:0;background:${isAnom ? '#D97706' : '#C7C3BC'};border-radius:6px;transition:width 0.6s cubic-bezier(.34,1.2,.64,1);"></div>
      </div>
      <div style="width:66px;flex-shrink:0;text-align:right;font-size:13px;font-weight:700;font-family:'IBM Plex Mono',monospace;font-feature-settings:'tnum' 1;color:#1C1B1A;">${fmtBig(val)}</div>
    </div>`
  }).join('')

  const more = rest > 0
    ? `<div style="font-size:11.5px;color:#8B867E;margin-top:10px;padding-top:10px;border-top:1px dashed #EBE8E3;">+ ${rest} entitas lainnya</div>`
    : ''
  const title = valCol.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())

  return `<div style="background:#FFFFFF;border:1px solid #EBE8E3;border-radius:16px;padding:20px;">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
      <span style="font-size:13.5px;font-weight:700;color:#1C1B1A;">${esc(title)}</span>
      <span style="font-size:11px;color:#8B867E;">${top.length} dari ${data.length} entitas</span>
    </div>
    <div style="display:flex;flex-direction:column;gap:10px;">${rows}${more}</div>
  </div>`
}

// ─────────────────────────────────────────────────────────────
// Chart.js panel
// ─────────────────────────────────────────────────────────────

function _buildChartPanel(gid, title = '') {
  const header = title
    ? `<div style="font-size:13px;font-weight:600;color:#1C1B1A;margin-bottom:12px;">${esc(title)}</div>`
    : ''
  return `
    <div style="background:#FFFFFF;border:1px solid #EBE8E3;border-radius:16px;padding:16px 20px;">
      ${header}
      <div style="position:relative;height:220px;">
        <canvas data-chart-gid="${gid}"></canvas>
      </div>
    </div>
  `
}

function _initChart(container, gid, config) {
  const canvas = container.querySelector(`[data-chart-gid="${gid}"]`)
  if (!canvas || canvas._chartInstance || !config) return
  if (typeof Chart === 'undefined') {
    canvas.parentElement.innerHTML =
      '<p style="font-size:12px;color:#9B9693;padding:16px;text-align:center;">Chart.js belum termuat.</p>'
    return
  }
  const isDoughnut    = config.type === 'doughnut' || config.type === 'pie'
  const isDual        = config.dual_axis === true
  const isDivergingBar = config.index_axis === 'y'

  let scales
  if (isDoughnut) {
    scales = {}
  } else if (isDual) {
    scales = {
      x: { grid: { display: false } },
      y: {
        type: 'linear', position: 'left',
        grid: { color: '#F5F3F0' },
        ticks: { callback: v => _shortNum(v) },
      },
      y1: {
        type: 'linear', position: 'right',
        grid: { drawOnChartArea: false },
        ticks: { callback: v => v + '%' },
        min: 0,
      },
    }
  } else if (isDivergingBar) {
    // Horizontal bar: x = value axis, y = category axis
    scales = {
      x: { grid: { color: '#F5F3F0' }, ticks: { callback: v => v + '%' } },
      y: { grid: { display: false } },
    }
  } else {
    scales = {
      x: { grid: { display: false } },
      y: {
        grid: { color: '#F5F3F0' },
        ticks: { callback: v => _shortNum(v) },
      },
    }
  }

  try {
    canvas._chartInstance = new Chart(canvas, {
      type: config.type,
      data: { labels: config.labels, datasets: config.datasets },
      options: {
        ...(isDivergingBar ? { indexAxis: 'y' } : {}),
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: isDoughnut || config.datasets.length > 1 } },
        scales,
      },
    })
  } catch (err) {
    console.error('Chart error:', err)
  }
}

// ─────────────────────────────────────────────────────────────
// Status badge helpers
// ─────────────────────────────────────────────────────────────

function _isStatusCol(colName) {
  const n = colName.toLowerCase()
  return n === 'status' || n === 'kondisi' || n === 'state' || n === 'kategori' || n === 'flag'
}

function _statusBadge(v) {
  const s = String(v).trim()
  const l = s.toLowerCase()
  let cls
  if (l.includes('anomal') || l.includes('kritis') || l.includes('gagal') || l.includes('error')) {
    cls = 'badge-anomaly'
  } else if (l.includes('normal') || l === 'ok' || l === 'oke' || l.includes('baik') || l.includes('sehat')) {
    cls = 'badge-normal'
  } else if (l.includes('review') || l.includes('perlu') || l.includes('waspada') || l.includes('warning')) {
    cls = 'badge-review'
  } else {
    return null
  }
  return `<span class="badge ${cls}">${esc(s)}</span>`
}

// ─────────────────────────────────────────────────────────────
// Data table
// ─────────────────────────────────────────────────────────────

function _isDeltaCol(colName) {
  const n = colName.toLowerCase()
  return n === 'selisih' || n === 'delta' || n === 'difference' || n === 'diff' || n === 'gap'
}

function _deltaCell(v) {
  const n = _toNum(v)
  if (n === null) return `<td class="num">${fmtCell(v)}</td>`
  const abs    = Math.abs(n)
  const pct    = Math.min(100, Math.round((abs / (abs || 1)) * 100))
  const isNeg  = n < 0
  const isPos  = n > 0
  const cls    = isNeg ? 'neg' : isPos ? 'pos' : 'zero'
  const color  = isNeg ? 'var(--danger)' : isPos ? 'var(--warn)' : 'var(--text-faint)'
  const barW   = Math.min(52, Math.round((abs / (abs + 1)) * 52)) || 3
  return `
    <td class="num">
      <div class="delta-cell">
        <div class="delta-bar-track">
          <div class="delta-bar-fill" style="background:${color};left:0;width:${barW}px;"></div>
        </div>
        <span class="delta-val ${cls}">${isNeg ? '−' : isPos ? '+' : ''}${fmtBig(abs)}</span>
      </div>
    </td>
  `
}

function _statusPill(v) {
  const s = String(v).trim(), l = s.toLowerCase()
  let bg, tc, bd
  if (l.includes('normal') || l === 'ok' || l === 'oke' || l.includes('baik') || l.includes('aktif')) {
    bg = '#E6F4EC'; tc = '#0E8A55'; bd = '#A8D5BE'
  } else if (l.includes('anomal') || l.includes('kritis') || l.includes('gagal')) {
    bg = '#FCEEDD'; tc = '#B45309'; bd = '#F2D3A8'
  } else if (l.includes('review') || l.includes('perlu') || l.includes('waspada')) {
    bg = '#EFEDE9'; tc = '#6B6864'; bd = '#EFEDE9'
  } else { return null }
  return `<span style="display:inline-flex;align-items:center;font-size:11px;font-weight:600;padding:3px 10px;border-radius:20px;background:${bg};color:${tc};border:1px solid ${bd};">${esc(s)}</span>`
}

function _buildTableSection(data, totalRows) {
  if (!data?.length) return ''
  const cols    = Object.keys(data[0])
  const visible = data.slice(0, 200)
  const deltaCol = cols.find(_isDeltaCol)
  const deltaMax = deltaCol ? Math.max(...data.map(r => Math.abs(_toNum(r[deltaCol]) ?? 0)), 1) : 1

  const ths = cols.map(c => {
    const isR = _isCellNumeric(data[0]?.[c]) || _isStatusCol(c) || _isDeltaCol(c)
    return `<th class="sort-th${isR ? ' num-col' : ''}" data-col="${esc(c)}" style="padding:10px 20px;font-size:10.5px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:#8B867E;text-align:${isR ? 'right' : 'left'};background:#FAF8F6;border-bottom:1px solid #EBE8E3;white-space:nowrap;cursor:pointer;user-select:none;">
      ${esc(c.replace(/_/g, ' '))}<span class="sort-icon" style="font-size:9px;color:#CCC7C1;margin-left:3px;">↕</span>
    </th>`
  }).join('')

  const trs = visible.map(row => {
    const cells = cols.map((c, ci) => {
      const v = row[c]
      if (_isStatusCol(c) && v != null) {
        const pill = _statusPill(v)
        return `<td style="padding:12px 20px;border-bottom:1px solid #F2F0EC;text-align:right;">${pill || esc(String(v))}</td>`
      }
      if (_isDeltaCol(c)) {
        const n = _toNum(v), abs = Math.abs(n ?? 0)
        const pct = Math.round((abs / deltaMax) * 48)
        const isNeg = (n ?? 0) < 0, isPos = (n ?? 0) > 0
        const dc = isNeg ? '#E4002B' : isPos ? '#B45309' : '#A6A29B'
        return `<td style="padding:12px 20px;border-bottom:1px solid #F2F0EC;">
          <div style="display:flex;align-items:center;justify-content:flex-end;gap:10px;">
            <div style="width:48px;height:4px;background:#EFEDE9;border-radius:2px;overflow:hidden;flex-shrink:0;">
              <div style="height:100%;width:${Math.max(2,pct)}px;background:${dc};border-radius:2px;"></div>
            </div>
            <span style="font-family:'IBM Plex Mono',monospace;font-feature-settings:'tnum' 1;font-size:12px;font-weight:600;min-width:60px;text-align:right;color:${dc};">${isNeg?'−':isPos?'+':''}${fmtBig(abs)}</span>
          </div>
        </td>`
      }
      const isFirst = ci === 0, isN = _isCellNumeric(v)
      return `<td style="padding:12px 20px;border-bottom:1px solid #F2F0EC;font-size:13px;text-align:${isN ? 'right' : 'left'};${isN ? "font-family:'IBM Plex Mono',monospace;font-feature-settings:'tnum' 1;" : ''}color:${isFirst ? '#1C1B1A' : '#26231F'};${isFirst ? 'font-weight:600;' : ''}">${fmtCell(v)}</td>`
    }).join('')
    return `<tr onmouseenter="this.style.background='#FAF8F6'" onmouseleave="this.style.background=''">${cells}</tr>`
  }).join('')

  const firstCol = cols[0]
  const isTimeSeries = _isDateCol(firstCol, data[0]?.[firstCol])
  const note = totalRows > 200
    ? `<div style="padding:8px 20px;font-size:11px;color:#8B867E;background:#FAF8F6;border-top:1px solid #EBE8E3;">Menampilkan 200 dari ${fmtNum(totalRows)} baris</div>`
    : ''

  return `<div style="background:#FFFFFF;border:1px solid #EBE8E3;border-radius:16px;overflow:hidden;">
    <div style="padding:16px 20px;border-bottom:1px solid #EBE8E3;display:flex;align-items:center;justify-content:space-between;">
      <span style="font-size:13.5px;font-weight:700;color:#1C1B1A;">${isTimeSeries ? 'Tren harian' : 'Rincian data'}</span>
      <span style="font-size:11px;color:#8B867E;font-family:'IBM Plex Mono',monospace;">${fmtNum(Math.min(visible.length, 200))} baris</span>
    </div>
    <div style="overflow:auto;max-height:320px;">
      <table class="sort-table" style="width:100%;border-collapse:collapse;">
        <thead><tr>${ths}</tr></thead>
        <tbody>${trs}</tbody>
      </table>
    </div>
    ${note}
  </div>`
}

// ─────────────────────────────────────────────────────────────
// Anomaly callout
// ─────────────────────────────────────────────────────────────

function _buildAnomalyCallout(insights, data) {
  if (!insights?.toLowerCase().includes('anomal')) return ''
  const sentences      = insights.split(/(?<=[.!?])\s+/)
  const anomSentence   = sentences.find(s => s.toLowerCase().includes('anomal')) ?? ''
  const summary        = anomSentence.slice(0, 280).trim()
  let anomalyEntity    = null
  if (data?.length) {
    const sc = Object.keys(data[0]).find(_isStatusCol)
    if (sc) {
      const row = data.find(r => String(r[sc]).toLowerCase().includes('anomal'))
      if (row) {
        const lc = Object.keys(row).find(c => c !== sc && !_isNumericVal(row[c]))
        if (lc) anomalyEntity = String(row[lc])
      }
    }
  }
  const title = anomalyEntity ? `Anomali terdeteksi — ${anomalyEntity}` : 'Anomali terdeteksi'
  const summaryHtml = summary
    ? summary.replace(/(\d[\d.,]*\s*(?:juta|miliar|ribu|trx|rb|jt|M|k|%)?)/g,
        m => `<span style="font-family:'IBM Plex Mono',monospace;font-feature-settings:'tnum' 1;font-weight:600;">${m}</span>`)
    : ''
  return `<div style="background:#FCEEDD;border:1px solid #F2D3A8;border-left:3px solid #D97706;border-radius:12px;padding:15px;">
    <div style="display:flex;align-items:center;gap:7px;${summary ? 'margin-bottom:8px;' : ''}">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" style="flex-shrink:0;"><path d="M12 9V13M12 17H12.01M10.29 3.86L1.82 18A2 2 0 003.54 21H20.46A2 2 0 0022.18 18L13.71 3.86A2 2 0 0010.29 3.86Z" stroke="#B45309" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <span style="font-size:12px;font-weight:700;color:#B45309;">${esc(title)}</span>
    </div>
    ${summaryHtml ? `<p style="font-size:13.5px;line-height:1.6;color:#5A3D18;margin:0;">${summaryHtml}</p>` : ''}
  </div>`
}

// ─────────────────────────────────────────────────────────────
// Bottom tabs: SQL / Tools / Detail (collapsed by default)
// ─────────────────────────────────────────────────────────────

function _buildBottomTabs(result, gid, hasSql, toolCalls) {
  const defs = []
  if (hasSql)               defs.push({ key: 'sql',    label: 'SQL' })
  if (toolCalls.length > 0) defs.push({ key: 'tools',  label: `Tools (${toolCalls.length})` })
  defs.push(                { key: 'detail', label: 'Detail' })

  const btns = defs.map(d =>
    `<button class="tab-btn" data-tab="${d.key}" data-gid="${gid}">${esc(d.label)}</button>`
  ).join('')

  const panels = defs.map(d => `
    <div class="hidden" data-panel="${d.key}" data-gid="${gid}">
      ${_tabContent(d.key, result, toolCalls)}
    </div>
  `).join('')

  // Wrap in a collapsible "detail teknis" disclosure
  return `
    <div data-tech-wrapper="${gid}" style="border-top:1px solid #F0EDE9;">
      <button data-tech-toggle="${gid}"
        style="width:100%;display:flex;align-items:center;justify-content:space-between;padding:7px 18px;background:none;border:none;cursor:pointer;font-size:11px;color:#B3ADA6;font-family:inherit;">
        <span>Detail teknis</span>
        <svg data-tech-chevron style="display:inline-block;transition:transform 0.2s;" width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/></svg>
      </button>
      <div data-tech-body="${gid}" class="hidden">
        <div class="tab-bar">${btns}</div>
        <div>${panels}</div>
      </div>
    </div>
  `
}

function _tabContent(key, result, toolCalls) {
  switch (key) {
    case 'sql':    return _buildSqlBlock(result.sql)
    case 'tools':  return _buildToolCalls(toolCalls)
    case 'detail': return _buildDetail(result)
    default:       return ''
  }
}

function _initBottomTabs(container, gid) {
  // Wire disclosure toggle
  const techToggle = container.querySelector(`[data-tech-toggle="${gid}"]`)
  const techBody   = container.querySelector(`[data-tech-body="${gid}"]`)
  const techChevron = techToggle?.querySelector('[data-tech-chevron]')
  if (techToggle && techBody) {
    techToggle.addEventListener('click', () => {
      const isHidden = techBody.classList.toggle('hidden')
      if (techChevron) techChevron.style.transform = isHidden ? '' : 'rotate(180deg)'
    })
  }

  // Wire individual SQL/Tools/Detail tabs
  container.querySelectorAll(`[data-tab][data-gid="${gid}"]`).forEach(btn => {
    btn.addEventListener('click', () => {
      const key    = btn.dataset.tab
      const panel  = container.querySelector(`[data-panel="${key}"][data-gid="${gid}"]`)
      const isOpen = !panel.classList.contains('hidden')

      container.querySelectorAll(`[data-tab][data-gid="${gid}"]`).forEach(b => b.classList.remove('is-active'))
      container.querySelectorAll(`[data-panel][data-gid="${gid}"]`).forEach(p => p.classList.add('hidden'))

      if (!isOpen) {
        btn.classList.add('is-active')
        panel.classList.remove('hidden')
        panel.querySelectorAll('code.language-sql').forEach(b => {
          if (!b.dataset.highlighted && typeof hljs !== 'undefined') hljs.highlightElement(b)
        })
      }
    })
  })
}

// ─────────────────────────────────────────────────────────────
// SQL block
// ─────────────────────────────────────────────────────────────

function _buildSqlBlock(sql) {
  if (!sql) return '<p style="padding:14px 18px;font-size:13px;color:#9B9693;">Tidak ada SQL</p>'
  return `
    <div class="sql-wrap">
      <pre class="sql-pre"><code class="language-sql">${esc(sql)}</code></pre>
      <button class="copy-btn" data-copy="${escAttr(sql)}">Salin</button>
    </div>
  `
}

// ─────────────────────────────────────────────────────────────
// Tool calls
// ─────────────────────────────────────────────────────────────

function _buildToolCalls(toolCalls) {
  if (!toolCalls?.length) return '<p style="padding:14px 18px;font-size:13px;color:#9B9693;">Tidak ada tool call</p>'
  const rows = toolCalls.map((tc, i) => `
    <div style="padding:10px 18px;border-bottom:1px solid #EBE8E3;">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:3px;">
        <span style="font-size:9px;font-weight:700;background:#E4002B;color:white;border-radius:20px;padding:2px 7px;">${i+1}</span>
        <span style="font-size:12px;font-weight:600;color:#2A2724;font-family:monospace;">${esc(tc.tool)}</span>
        <span style="font-size:11px;color:#9B9693;margin-left:auto;">${fmtNum(tc.row_count)} baris</span>
      </div>
      ${tc.arguments && Object.keys(tc.arguments).length
        ? `<p style="font-size:11px;color:#9B9693;margin:0;padding-left:22px;font-family:monospace;">${esc(JSON.stringify(tc.arguments))}</p>`
        : ''}
    </div>
  `).join('')
  return `<div>${rows}</div>`
}

// ─────────────────────────────────────────────────────────────
// Detail panel
// ─────────────────────────────────────────────────────────────

function _buildDetail(result) {
  const timing = result.metadata?.timing ?? {}
  const errors = result.metadata?.errors ?? []
  const meta   = result.metadata ?? {}
  const maxMs  = Math.max(...Object.values(timing).map(v => v * 1000), 1)

  const timingHtml = Object.entries(timing)
    .sort(([, a], [, b]) => b - a)
    .map(([name, sec]) => {
      const ms  = Math.round(sec * 1000)
      const pct = Math.round((ms / maxMs) * 100)
      return `
        <div style="display:flex;align-items:center;gap:10px;padding:5px 0;">
          <span style="width:136px;font-size:11px;color:#9B9693;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(name)}</span>
          <div style="flex:1;height:5px;background:#F5F3F0;border-radius:3px;overflow:hidden;">
            <div class="timing-bar" style="width:${pct}%;"></div>
          </div>
          <span style="width:52px;text-align:right;font-size:11px;font-family:monospace;color:#9B9693;flex-shrink:0;">${ms}ms</span>
        </div>
      `
    }).join('')

  const infoItems = [
    ['Database',      meta.database],
    ['Tables used',   meta.tables_used],
    ['Stage',         meta.pipeline_stage],
    ['Request ID',    meta.request_id ? meta.request_id.slice(0, 8) + '…' : null],
  ].filter(([, v]) => v != null)

  const infoHtml = infoItems.map(([label, val]) => `
    <div>
      <p style="font-size:10px;color:#9B9693;margin:0 0 2px;">${label}</p>
      <p style="font-size:13px;font-weight:500;color:#2A2724;margin:0;">${esc(String(val))}</p>
    </div>
  `).join('')

  return `
    <div style="padding:14px 18px;">
      ${timingHtml ? `
        <p style="font-size:10px;font-weight:600;color:#9B9693;text-transform:uppercase;letter-spacing:0.04em;margin:0 0 8px;">Timing per agent</p>
        ${timingHtml}
      ` : ''}
      ${infoItems.length ? `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px 24px;margin-top:14px;">${infoHtml}</div>
      ` : ''}
      ${errors.length ? `
        <p style="font-size:10px;font-weight:600;color:#9B9693;text-transform:uppercase;letter-spacing:0.04em;margin:14px 0 6px;">Peringatan</p>
        ${errors.map(e => `<p style="font-size:12px;color:#F59E0B;margin:0 0 3px;">${esc(String(e))}</p>`).join('')}
      ` : ''}
    </div>
  `
}

// ─────────────────────────────────────────────────────────────
// Quick replies
// ─────────────────────────────────────────────────────────────

const _QR = {
  ranking_analysis:    ['Bandingkan dengan bulan lalu?', 'Siapa yang paling menurun?', 'Tampilkan tren?'],
  anomaly_detection:   ['Apa penyebabnya?', 'Kapan mulai terjadi?', 'Partner mana terdampak?'],
  root_cause_analysis: ['Detail per channel?', 'Bandingkan baseline?', 'Distribusi kontributor?'],
  complex_analytics:   ['Breakdown per partner?', 'Tren bulan ini?', 'Bandingkan periode?'],
  trend_analysis:      ['Mana yang tumbuh paling cepat?', 'Breakdown per channel?'],
  comparison:          ['Lihat detail perbedaan?', 'Faktor apa yang mempengaruhi?'],
  data_query:          ['Tampilkan tren?', 'Breakdown per partner?', 'Top 5 partner?'],
}

function _buildQuickReplies(intent) {
  const list = _QR[intent] ?? _QR['data_query']
  const pills = list.map(s =>
    `<button data-qr="${escAttr(s)}" style="display:inline-flex;align-items:center;gap:6px;padding:9px 14px;background:#FFFFFF;border:1px solid #E3E0DB;border-radius:22px;font-size:13px;font-weight:600;color:#1C1B1A;cursor:pointer;font-family:'Plus Jakarta Sans',sans-serif;transition:border-color .15s,color .15s;" onmouseenter="this.style.borderColor='#E4002B';this.style.color='#E4002B'" onmouseleave="this.style.borderColor='#E3E0DB';this.style.color='#1C1B1A'"><span style="color:#E4002B;">↳</span>${esc(s)}</button>`
  ).join('')
  return `<div>
    <div style="font-size:11px;font-weight:700;color:#A6A29B;letter-spacing:.06em;text-transform:uppercase;margin-bottom:8px;">LANJUTKAN ANALISIS</div>
    <div style="display:flex;flex-wrap:wrap;gap:8px;">${pills}</div>
  </div>`
}

function _initQuickReplies(container) {
  container.querySelectorAll('[data-qr]').forEach(btn => {
    btn.addEventListener('click', () => {
      const input = document.getElementById('query-input')
      if (input) {
        input.value = btn.dataset.qr
        input.dispatchEvent(new Event('input'))
        input.focus()
      }
    })
  })
}

// ─────────────────────────────────────────────────────────────
// Multi-step accordion
// ─────────────────────────────────────────────────────────────

function _multiBadge(n) {
  const dots = Array.from({ length: n }, (_, i) =>
    `<span style="display:inline-block;width:18px;height:4px;border-radius:2px;background:${i === 0 ? '#E4002B' : '#EBE8E3'};"></span>`
  ).join('')
  return `
    <div class="multistep-badge">
      <span style="display:flex;gap:3px;">${dots}</span>
      Query multi-step · ${n} tahap
    </div>
  `
}

function _buildMultiAccordion(steps, gid) {
  const items = steps.map((step, i) => {
    const failed = !step.sql && !step.data?.length
    return `
      <div style="border-bottom:1px solid #EBE8E3;">
        <button data-accordion="${i}" data-gid="${gid}"
          style="width:100%;display:flex;align-items:center;justify-content:space-between;gap:12px;
            padding:13px 20px;background:none;border:none;cursor:pointer;font-family:inherit;
            text-align:left;transition:background 0.12s;"
          onmouseenter="this.style.background='#FAFAF8'" onmouseleave="this.style.background=''">
          <div style="display:flex;align-items:center;gap:10px;min-width:0;">
            <span style="flex-shrink:0;width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;background:${failed ? '#FEE2E2' : '#FFF0F2'};color:#E4002B;">
              ${step.step_number}
            </span>
            <span style="font-size:13px;font-weight:500;color:#2A2724;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(step.description)}</span>
            <span style="font-size:11px;color:#9B9693;flex-shrink:0;">${fmtNum(step.row_count)} baris</span>
          </div>
          <svg data-chevron="${i}" style="flex-shrink:0;width:15px;height:15px;color:#9B9693;transition:transform 0.2s;"
            fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
          </svg>
        </button>
        <div class="hidden" data-accordion-panel="${i}" data-gid="${gid}" style="border-top:1px solid #EBE8E3;">
          ${step.sql ? _buildSqlBlock(step.sql) : ''}
          ${step.data?.length ? _buildTableSection(step.data, step.row_count) : ''}
          ${failed ? '<p style="padding:12px 18px;font-size:13px;color:#9B9693;">Tahap ini gagal dieksekusi.</p>' : ''}
        </div>
      </div>
    `
  }).join('')
  return `<div>${items}</div>`
}

function _initAccordion(container, gid) {
  container.querySelectorAll(`[data-accordion][data-gid="${gid}"]`).forEach(btn => {
    btn.addEventListener('click', () => {
      const idx     = btn.dataset.accordion
      const panel   = container.querySelector(`[data-accordion-panel="${idx}"][data-gid="${gid}"]`)
      const chevron = btn.querySelector(`[data-chevron="${idx}"]`)
      const opening = panel.classList.contains('hidden')

      panel.classList.toggle('hidden', !opening)
      if (chevron) chevron.style.transform = opening ? 'rotate(180deg)' : ''

      if (opening) {
        panel.querySelectorAll('code.language-sql').forEach(b => {
          if (!b.dataset.highlighted && typeof hljs !== 'undefined') hljs.highlightElement(b)
        })
      }
    })
  })
}

// ─────────────────────────────────────────────────────────────
// Sortable table
// ─────────────────────────────────────────────────────────────

function _initSortable(container) {
  container.querySelectorAll('.sort-th').forEach(th => {
    let dir = 'asc'
    th.addEventListener('click', () => {
      const table  = th.closest('.sort-table')
      if (!table) return
      const colIdx = Array.from(th.parentElement.children).indexOf(th)
      const tbody  = table.querySelector('tbody')
      const rows   = Array.from(tbody.querySelectorAll('tr'))

      table.querySelectorAll('.sort-icon').forEach(i => { i.textContent = '↕'; i.style.color = '#CCC7C1' })
      const icon = th.querySelector('.sort-icon')
      if (icon) { icon.textContent = dir === 'asc' ? '↑' : '↓'; icon.style.color = '#E4002B' }

      rows.sort((a, b) => {
        const av = a.cells[colIdx]?.textContent.trim() ?? ''
        const bv = b.cells[colIdx]?.textContent.trim() ?? ''
        const an = parseFloat(av.replace(/[^0-9.-]/g, ''))
        const bn = parseFloat(bv.replace(/[^0-9.-]/g, ''))
        const cmp = !isNaN(an) && !isNaN(bn) ? an - bn : av.localeCompare(bv, 'id')
        return dir === 'asc' ? cmp : -cmp
      })
      rows.forEach(r => tbody.appendChild(r))
      dir = dir === 'asc' ? 'desc' : 'asc'
    })
  })
}

// ─────────────────────────────────────────────────────────────
// Copy buttons
// ─────────────────────────────────────────────────────────────

function _initCopyBtns(container) {
  container.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      navigator.clipboard.writeText(btn.dataset.copy)
        .then(() => { btn.textContent = 'Tersalin!'; setTimeout(() => { btn.textContent = 'Salin' }, 2000) })
        .catch(() => { btn.textContent = 'Gagal'; setTimeout(() => { btn.textContent = 'Salin' }, 2000) })
    })
  })
}

// ─────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────

function aiAvatar() {
  return `<div style="width:28px;height:28px;border-radius:8px;flex-shrink:0;margin-top:2px;background:linear-gradient(155deg,var(--accent),#7A0A20);display:flex;align-items:center;justify-content:center;">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M4 15L9 8L13 12L20 4" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
  </div>`
}

function renderMd(text) {
  if (!text) return ''
  try {
    return typeof marked !== 'undefined' ? marked.parse(text, { breaks: true, gfm: true }) : `<p>${esc(text)}</p>`
  } catch { return `<p>${esc(text)}</p>` }
}

function make(html) {
  const t = document.createElement('template')
  t.innerHTML = html.trim()
  return t.content.firstElementChild
}

function esc(s) {
  if (s == null) return ''
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function escAttr(s) { return esc(String(s ?? '')) }

function fmtCell(v) {
  if (v === null || v === undefined) return '<span style="color:#CCC7C1;font-size:11px;font-style:italic;">null</span>'
  if (typeof v === 'object') return `<span style="font-size:11px;color:#9B9693;">${esc(JSON.stringify(v))}</span>`
  if (typeof v === 'number') {
    if (Math.abs(v) >= 1e9) return fmtBig(v)
    return Number.isInteger(v)
      ? v.toLocaleString('id-ID')
      : v.toLocaleString('id-ID', { maximumFractionDigits: 4 })
  }
  if (typeof v === 'string') {
    // Clean up datetime strings — strip " 00:00:00" or "T00:00:00" suffix
    const dateClean = v.replace(/\s00:00:00$/, '').replace(/T00:00:00.*$/, '')
    if (_isDateVal(dateClean)) return esc(dateClean)
    // Format numeric strings
    if (_isNumericVal(v)) {
      const n = _toNum(v)
      if (n !== null) {
        // Abbreviate very large numbers (≥ 1 miliar) for readability
        if (Math.abs(n) >= 1e9) return fmtBig(n)
        return Number.isInteger(n)
          ? n.toLocaleString('id-ID')
          : n.toLocaleString('id-ID', { maximumFractionDigits: 4 })
      }
    }
    return esc(v)
  }
  return esc(String(v))
}

function _isCellNumeric(v) {
  return typeof v === 'number' || (typeof v === 'string' && !_isDateVal(v) && _isNumericVal(v))
}

function fmtNum(n) { return Number(n ?? 0).toLocaleString('id-ID') }

function fmtBig(raw) {
  const n = typeof raw === 'number' ? raw : _toNum(raw)
  if (n === null || isNaN(n)) return esc(String(raw ?? '–'))
  if (Math.abs(n) >= 1e12) return (n/1e12).toFixed(1) + 'T'
  if (Math.abs(n) >= 1e9)  return (n/1e9).toFixed(1) + 'M'
  if (Math.abs(n) >= 1e6)  return (n/1e6).toFixed(1) + 'jt'
  if (Math.abs(n) >= 1e3)  return (n/1e3).toFixed(0) + 'k'
  return n.toLocaleString('id-ID', { maximumFractionDigits: 2 })
}

function fmtMs(ms) {
  if (!ms) return ''
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms/1000).toFixed(1)} s`
}

function _shortNum(v) {
  if (Math.abs(v) >= 1e9)  return (v/1e9).toFixed(1)+'M'
  if (Math.abs(v) >= 1e6)  return (v/1e6).toFixed(1)+'jt'
  if (Math.abs(v) >= 1e3)  return (v/1e3).toFixed(0)+'k'
  return v.toLocaleString('id-ID')
}
