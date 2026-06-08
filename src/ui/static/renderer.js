/**
 * renderer.js — All DOM rendering for the chat interface.
 * Pure functions that receive data and return / mutate DOM elements.
 * No API calls, no app state.
 */

// ── Public API ────────────────────────────────────────────────
export {
  appendUserMessage,
  appendLoadingMessage,
  appendAssistantMessage,
  appendErrorMessage,
  appendClarificationMessage,
  removeElement,
}

// Stores chart_config keyed by gid so initChart can be called lazily on tab open
const _chartConfigs = new Map()

// ─────────────────────────────────────────────────────────────
// Message types
// ─────────────────────────────────────────────────────────────

function appendUserMessage(container, text) {
  const el = make(`
    <div class="flex justify-end msg-enter">
      <div class="max-w-xl px-4 py-3 bg-blue-600 text-white text-sm rounded-2xl rounded-tr-sm leading-relaxed">
        ${esc(text)}
      </div>
    </div>
  `)
  container.appendChild(el)
}

function appendLoadingMessage(container) {
  const el = make(`
    <div class="flex justify-start msg-enter">
      <div class="px-5 py-4 bg-white border border-slate-200 rounded-2xl rounded-tl-sm
        flex items-center gap-1.5 result-card">
        <span class="loading-dot w-2 h-2 rounded-full bg-slate-400"></span>
        <span class="loading-dot w-2 h-2 rounded-full bg-slate-400"></span>
        <span class="loading-dot w-2 h-2 rounded-full bg-slate-400"></span>
      </div>
    </div>
  `)
  container.appendChild(el)
  return el
}

function removeElement(el) {
  el?.remove()
}

function appendErrorMessage(container, message) {
  const el = make(`
    <div class="flex justify-start msg-enter">
      <div class="max-w-xl px-4 py-3 bg-red-50 border border-red-200
        rounded-2xl rounded-tl-sm result-card">
        <p class="text-sm font-semibold text-red-700 mb-0.5">Terjadi kesalahan</p>
        <p class="text-sm text-red-600">${esc(message)}</p>
      </div>
    </div>
  `)
  container.appendChild(el)
}

function appendClarificationMessage(container, reason) {
  const el = make(`
    <div class="flex justify-start msg-enter">
      <div class="max-w-xl px-4 py-3 bg-amber-50 border border-amber-200
        rounded-2xl rounded-tl-sm result-card">
        <p class="text-sm font-semibold text-amber-800 mb-0.5">Pertanyaan perlu diperjelas</p>
        <p class="text-sm text-amber-700">${esc(reason || 'Mohon berikan detail yang lebih spesifik.')}</p>
      </div>
    </div>
  `)
  container.appendChild(el)
}

function appendAssistantMessage(container, result) {
  const gid     = 'g' + Date.now() + Math.random().toString(36).slice(2, 6)
  const isMulti = result.is_multi_step && result.step_results?.length > 0
  const hasData = result.data?.length > 0
  const hasSql  = Boolean(result.sql)

  const intent   = result.metadata?.intent?.category ?? ''
  const errors   = result.metadata?.errors ?? []
  const rowCount = result.row_count ?? 0

  const el = make(`
    <div class="flex justify-start msg-enter">
      <div class="w-full max-w-3xl space-y-2">

        ${isMulti ? multiBadge(result.step_results.length) : ''}

        <div class="bg-white border border-slate-200 rounded-2xl rounded-tl-sm overflow-hidden result-card">

          <!-- Insight -->
          <div class="px-5 py-4 ${(hasData || hasSql || isMulti) ? 'border-b border-slate-100' : ''}">
            <div class="md-content text-sm text-slate-700 leading-relaxed">${renderMd(result.insights || '–')}</div>
          </div>

          ${isMulti
            ? buildMultiAccordion(result.step_results, gid)
            : buildTabs(result, gid, hasData, hasSql)
          }

          <!-- Footer -->
          <div class="px-5 py-2 bg-slate-50 border-t border-slate-100 flex items-center justify-between">
            <div class="flex items-center gap-3 text-xs text-slate-400">
              ${rowCount > 0 ? `<span>${fmtNum(rowCount)} baris</span>` : ''}
              ${intent ? `<span class="capitalize">${esc(intent)}</span>` : ''}
              ${errors.length > 0
                ? `<span class="text-amber-500">${errors.length} peringatan</span>`
                : ''}
            </div>
            <span class="text-xs text-slate-400 font-mono">${fmtMs(result.execution_time_ms)}</span>
          </div>

        </div>
      </div>
    </div>
  `)

  container.appendChild(el)

  if (result.chart_config) _chartConfigs.set(gid, result.chart_config)

  if (!isMulti) initTabs(el, gid)
  else          initAccordion(el, gid)

  initSortable(el)
  initCopyBtns(el)

  el.querySelectorAll('code.language-sql').forEach(b => {
    if (!b.dataset.highlighted) hljs.highlightElement(b)
  })
}

// ─────────────────────────────────────────────────────────────
// Tabs
// ─────────────────────────────────────────────────────────────

function buildTabs(result, gid, hasData, hasSql) {
  const defs = []
  if (result.chart_config) defs.push({ key: 'chart',  label: 'Grafik' })
  if (hasData)             defs.push({ key: 'data',   label: `Data (${fmtNum(result.row_count ?? 0)})` })
  if (hasSql)              defs.push({ key: 'sql',    label: 'SQL' })
  defs.push(                          { key: 'detail', label: 'Detail' })

  // All tabs start collapsed — user clicks to open/toggle
  const btns = defs.map(d => `
    <button class="tab-btn shrink-0 px-4 py-2.5 text-sm font-medium border-b-2 whitespace-nowrap
      border-transparent text-slate-400 hover:text-slate-700 transition-colors"
      data-tab="${d.key}" data-gid="${gid}">
      ${d.label}
    </button>
  `).join('')

  const panels = defs.map(d => `
    <div class="hidden" data-panel="${d.key}" data-gid="${gid}">
      ${tabContent(d.key, result, gid)}
    </div>
  `).join('')

  return `
    <div class="flex gap-0 px-2 border-b border-slate-100 overflow-x-auto">${btns}</div>
    <div>${panels}</div>
  `
}

function tabContent(key, result, gid) {
  switch (key) {
    case 'chart':  return buildChartPanel(result.chart_config, gid)
    case 'data':   return buildTable(result.data)
    case 'sql':    return buildSqlBlock(result.sql)
    case 'detail': return buildDetail(result)
    default:       return ''
  }
}

function initTabs(container, gid) {
  container.querySelectorAll(`[data-tab][data-gid="${gid}"]`).forEach(btn => {
    btn.addEventListener('click', () => {
      const key    = btn.dataset.tab
      const panel  = container.querySelector(`[data-panel="${key}"][data-gid="${gid}"]`)
      const isOpen = !panel.classList.contains('hidden')

      // Collapse everything first
      container.querySelectorAll(`[data-tab][data-gid="${gid}"]`).forEach(b => {
        b.classList.remove('border-blue-600', 'text-blue-600')
        b.classList.add('border-transparent', 'text-slate-400')
      })
      container.querySelectorAll(`[data-panel][data-gid="${gid}"]`).forEach(p => {
        p.classList.add('hidden')
      })

      // Toggle: re-open only if it was closed
      if (!isOpen) {
        btn.classList.remove('border-transparent', 'text-slate-400')
        btn.classList.add('border-blue-600', 'text-blue-600')
        panel.classList.remove('hidden')
        panel.querySelectorAll('code.language-sql').forEach(b => {
          if (!b.dataset.highlighted) hljs.highlightElement(b)
        })
        // Init chart lazily when panel first becomes visible
        if (key === 'chart') initChart(container, gid, _chartConfigs.get(gid))
      }
    })
  })
}

// ─────────────────────────────────────────────────────────────
// Chart
// ─────────────────────────────────────────────────────────────

function buildChartPanel(config, gid) {
  if (!config) return ''
  return `
    <div class="px-5 py-4">
      <div class="relative" style="max-height:300px">
        <canvas data-chart-gid="${gid}"></canvas>
      </div>
    </div>
  `
}

function initChart(container, gid, config) {
  const canvas = container.querySelector(`[data-chart-gid="${gid}"]`)
  if (!canvas || canvas._chartInstance || !config) return

  if (typeof Chart === 'undefined') {
    canvas.parentElement.innerHTML =
      '<p class="text-xs text-slate-400 py-4 text-center">Chart.js belum termuat. Refresh halaman.</p>'
    return
  }

  const isDoughnut = config.type === 'doughnut' || config.type === 'pie'

  try {
    canvas._chartInstance = new Chart(canvas, {
      type: config.type,
      data: {
        labels:   config.labels,
        datasets: config.datasets,
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: isDoughnut || config.datasets.length > 1 },
          tooltip: {
            callbacks: {
              label: ctx => {
                const v = ctx.parsed.y ?? ctx.parsed
                if (typeof v === 'number') {
                  return ` ${ctx.dataset.label}: ${v.toLocaleString('id-ID')}`
                }
                return ` ${ctx.dataset.label}: ${v}`
              },
            },
          },
        },
        scales: isDoughnut ? {} : {
          x: { grid: { display: false } },
          y: {
            grid: { color: '#f1f5f9' },
            ticks: {
              callback: v => {
                if (Math.abs(v) >= 1_000_000_000) return (v / 1_000_000_000).toFixed(1) + 'M'
                if (Math.abs(v) >= 1_000_000)     return (v / 1_000_000).toFixed(1) + 'jt'
                if (Math.abs(v) >= 1_000)         return (v / 1_000).toFixed(0) + 'k'
                return v.toLocaleString('id-ID')
              },
            },
          },
        },
      },
    })
  } catch (err) {
    console.error('Chart render error:', err)
    canvas.parentElement.innerHTML =
      `<p class="text-xs text-red-400 py-4 text-center">Gagal render chart: ${err.message}</p>`
  }
}

// ─────────────────────────────────────────────────────────────
// Data table
// ─────────────────────────────────────────────────────────────

function buildTable(data) {
  if (!data?.length) {
    return '<p class="px-5 py-4 text-sm text-slate-400">Tidak ada data</p>'
  }

  const cols    = Object.keys(data[0])
  const maxRows = 200
  const visible = data.slice(0, maxRows)

  const headers = cols.map(c => `
    <th class="sort-th px-4 py-2.5 text-left text-xs font-semibold text-slate-500
      uppercase tracking-wide whitespace-nowrap cursor-pointer select-none
      hover:bg-slate-100 transition-colors" data-col="${esc(c)}">
      <span class="inline-flex items-center gap-1">
        ${esc(c)}<span class="sort-icon text-slate-300 text-xs">↕</span>
      </span>
    </th>
  `).join('')

  const bodyRows = visible.map(row => {
    const cells = cols.map(c => {
      const v = row[c]
      const isNum = typeof v === 'number'
      return `<td class="px-4 py-2.5 text-sm text-slate-700 whitespace-nowrap
        ${isNum ? 'text-right font-mono tabular-nums' : ''}">${fmtCell(v)}</td>`
    }).join('')
    return `<tr class="border-b border-slate-100 hover:bg-slate-50 last:border-0">${cells}</tr>`
  }).join('')

  const note = data.length > maxRows
    ? `<div class="px-4 py-2 text-xs text-slate-400 bg-slate-50 border-t border-slate-100">
         Menampilkan ${fmtNum(maxRows)} dari ${fmtNum(data.length)} baris
       </div>`
    : ''

  return `
    <div class="overflow-auto max-h-72">
      <table class="sort-table data-table min-w-max">
        <thead class="bg-slate-50 sticky top-0 shadow-[0_1px_0_#e2e8f0]">
          <tr>${headers}</tr>
        </thead>
        <tbody>${bodyRows}</tbody>
      </table>
    </div>
    ${note}
  `
}

function initSortable(container) {
  container.querySelectorAll('.sort-th').forEach(th => {
    let dir = 'asc'
    th.addEventListener('click', () => {
      const table  = th.closest('.sort-table')
      const colIdx = Array.from(th.parentElement.children).indexOf(th)
      const tbody  = table.querySelector('tbody')
      const rows   = Array.from(tbody.querySelectorAll('tr'))

      // Reset all icons
      table.querySelectorAll('.sort-icon').forEach(i => {
        i.textContent  = '↕'
        i.className    = 'sort-icon text-slate-300 text-xs'
      })
      const icon       = th.querySelector('.sort-icon')
      icon.textContent  = dir === 'asc' ? '↑' : '↓'
      icon.className    = 'sort-icon text-blue-500 text-xs'

      rows.sort((a, b) => {
        const av = a.cells[colIdx]?.textContent.trim() ?? ''
        const bv = b.cells[colIdx]?.textContent.trim() ?? ''
        const an = parseFloat(av.replace(/[^0-9.-]/g, ''))
        const bn = parseFloat(bv.replace(/[^0-9.-]/g, ''))
        const cmp = (!isNaN(an) && !isNaN(bn))
          ? an - bn
          : av.localeCompare(bv, 'id')
        return dir === 'asc' ? cmp : -cmp
      })

      rows.forEach(r => tbody.appendChild(r))
      dir = dir === 'asc' ? 'desc' : 'asc'
    })
  })
}

// ─────────────────────────────────────────────────────────────
// SQL block
// ─────────────────────────────────────────────────────────────

function buildSqlBlock(sql) {
  if (!sql) return '<p class="px-5 py-4 text-sm text-slate-400">Tidak ada SQL</p>'

  return `
    <div class="relative group">
      <div class="overflow-x-auto">
        <pre class="px-5 py-4"><code class="language-sql">${esc(sql)}</code></pre>
      </div>
      <button class="copy-btn absolute top-3 right-3 px-2.5 py-1 text-xs rounded-md
        bg-white border border-slate-200 text-slate-500 hover:bg-slate-50 hover:border-slate-300
        opacity-0 group-hover:opacity-100 transition-opacity"
        data-copy="${escAttr(sql)}">
        Salin
      </button>
    </div>
  `
}

function initCopyBtns(container) {
  container.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      navigator.clipboard.writeText(btn.dataset.copy)
        .then(() => {
          btn.textContent = 'Tersalin!'
          setTimeout(() => { btn.textContent = 'Salin' }, 2000)
        })
        .catch(() => {
          btn.textContent = 'Gagal'
          setTimeout(() => { btn.textContent = 'Salin' }, 2000)
        })
    })
  })
}

// ─────────────────────────────────────────────────────────────
// Detail panel
// ─────────────────────────────────────────────────────────────

function buildDetail(result) {
  const timing = result.metadata?.timing ?? {}
  const errors = result.metadata?.errors ?? []
  const meta   = result.metadata ?? {}

  const maxMs = Math.max(...Object.values(timing).map(v => v * 1000), 1)

  const timingRows = Object.entries(timing)
    .sort(([, a], [, b]) => b - a)
    .map(([name, sec]) => {
      const ms  = Math.round(sec * 1000)
      const pct = Math.round((ms / maxMs) * 100)
      return `
        <div class="flex items-center gap-3 py-1.5">
          <span class="w-40 text-xs text-slate-500 shrink-0 truncate">${esc(name)}</span>
          <div class="flex-1 bg-slate-100 rounded-full h-1.5">
            <div class="timing-bar h-1.5 rounded-full" style="width:${pct}%"></div>
          </div>
          <span class="w-14 text-right text-xs font-mono text-slate-500 shrink-0">${ms} ms</span>
        </div>
      `
    }).join('')

  const infoItems = [
    ['Database',          meta.database],
    ['Tables retrieved',  meta.tables_retrieved],
    ['Tables used',       meta.tables_used],
    ['Stage',             meta.pipeline_stage],
    ['Request ID',        meta.request_id ? meta.request_id.slice(0, 8) + '…' : null],
  ].filter(([, v]) => v != null)

  const infoGrid = infoItems.map(([label, value]) => `
    <div>
      <p class="text-xs text-slate-400 mb-0.5">${label}</p>
      <p class="text-sm font-medium text-slate-700">${esc(String(value))}</p>
    </div>
  `).join('')

  return `
    <div class="px-5 py-4 space-y-4">
      ${timingRows ? `
        <div>
          <p class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Timing per agent</p>
          ${timingRows}
        </div>
      ` : ''}
      ${infoItems.length ? `
        <div class="grid grid-cols-2 gap-x-8 gap-y-3">
          ${infoGrid}
        </div>
      ` : ''}
      ${errors.length ? `
        <div>
          <p class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Peringatan</p>
          ${errors.map(e => `<p class="text-xs text-amber-600 leading-relaxed">${esc(String(e))}</p>`).join('')}
        </div>
      ` : ''}
    </div>
  `
}

// ─────────────────────────────────────────────────────────────
// Multi-step
// ─────────────────────────────────────────────────────────────

function multiBadge(n) {
  const dots = Array.from({ length: n }, (_, i) =>
    `<span class="inline-block w-5 h-1.5 rounded-full ${i === 0 ? 'bg-blue-500' : 'bg-blue-200'}"></span>`
  ).join('')
  return `
    <div class="flex items-center gap-2 px-1 text-xs text-slate-500">
      <span class="flex items-center gap-1">${dots}</span>
      Query multi-step · ${n} tahap
    </div>
  `
}

function buildMultiAccordion(steps, gid) {
  const items = steps.map((step, i) => {
    const failed = !step.sql && !step.data?.length
    return `
      <div class="border-b border-slate-100 last:border-0">
        <button class="w-full flex items-center justify-between gap-3 px-5 py-3.5
          text-sm hover:bg-slate-50 transition-colors text-left"
          data-accordion="${i}" data-gid="${gid}">
          <div class="flex items-center gap-3 min-w-0">
            <span class="shrink-0 w-5 h-5 rounded-full flex items-center justify-center
              text-xs font-semibold
              ${failed ? 'bg-red-100 text-red-600' : 'bg-blue-100 text-blue-700'}">
              ${step.step_number}
            </span>
            <span class="font-medium text-slate-700 truncate">${esc(step.description)}</span>
            <span class="shrink-0 text-slate-400 text-xs">${fmtNum(step.row_count)} baris</span>
          </div>
          <svg class="shrink-0 w-4 h-4 text-slate-400 transition-transform duration-200"
            data-chevron="${i}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
          </svg>
        </button>
        <div class="hidden border-t border-slate-100"
          data-accordion-panel="${i}" data-gid="${gid}">
          ${step.sql     ? buildSqlBlock(step.sql)    : ''}
          ${step.data?.length ? buildTable(step.data) : ''}
          ${failed ? '<p class="px-5 py-3 text-sm text-slate-400">Tahap ini gagal dieksekusi.</p>' : ''}
        </div>
      </div>
    `
  }).join('')

  return `<div>${items}</div>`
}

function initAccordion(container, gid) {
  container.querySelectorAll(`[data-accordion][data-gid="${gid}"]`).forEach(btn => {
    btn.addEventListener('click', () => {
      const idx     = btn.dataset.accordion
      const panel   = container.querySelector(`[data-accordion-panel="${idx}"][data-gid="${gid}"]`)
      const chevron = btn.querySelector(`[data-chevron="${idx}"]`)
      const opening = panel.classList.contains('hidden')

      panel.classList.toggle('hidden', !opening)
      chevron.style.transform = opening ? 'rotate(180deg)' : ''

      if (opening) {
        panel.querySelectorAll('code.language-sql').forEach(b => {
          if (!b.dataset.highlighted) hljs.highlightElement(b)
        })
        initCopyBtns(panel)
        initSortable(panel)
      }
    })
  })
}

// ─────────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────────

function renderMd(text) {
  if (!text) return ''
  try {
    return marked.parse(text, { breaks: true, gfm: true })
  } catch {
    return `<p>${esc(text)}</p>`
  }
}

function make(html) {
  const t = document.createElement('template')
  t.innerHTML = html.trim()
  return t.content.firstElementChild
}

function esc(s) {
  if (s == null) return ''
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

// For HTML attribute values (encodes same chars, used in data-* attributes)
function escAttr(s) {
  return esc(String(s ?? ''))
}

function fmtCell(v) {
  if (v === null || v === undefined) {
    return '<span class="text-slate-300 text-xs italic">null</span>'
  }
  if (typeof v === 'object') {
    return `<span class="text-xs text-slate-400">${esc(JSON.stringify(v))}</span>`
  }
  if (typeof v === 'number') {
    return Number.isInteger(v)
      ? v.toLocaleString('id-ID')
      : v.toLocaleString('id-ID', { maximumFractionDigits: 2 })
  }
  return esc(String(v))
}

function fmtNum(n) {
  return Number(n ?? 0).toLocaleString('id-ID')
}

function fmtMs(ms) {
  if (!ms) return ''
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`
}
