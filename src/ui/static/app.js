/**
 * app.js — Settlement AI main logic.
 * Settings panel overlays main area only (sidebar always visible).
 */

import {
  appendUserMessage,
  appendLoadingMessage,
  appendAssistantMessage,
  appendErrorMessage,
  appendClarificationMessage,
  removeElement,
} from '/ui/renderer.js?v=20'

// ── Config ────────────────────────────────────────────────────
const API = window.location.origin

// ── DOM refs ──────────────────────────────────────────────────
const $messages       = document.getElementById('messages')
const $welcome        = document.getElementById('welcome')
const $input          = document.getElementById('query-input')
const $submitBtn      = document.getElementById('submit-btn')
const $newChatBtn     = document.getElementById('new-chat-btn')
const $healthDot      = document.getElementById('health-dot')
const $healthText     = document.getElementById('health-text')
const $historyList    = document.getElementById('history-list')
const $historyEmpty   = document.getElementById('history-empty')
const $convTitle      = document.getElementById('conv-title')
const $convMeta       = document.getElementById('conv-meta')

// Settings
const $settingsPanel   = document.getElementById('settings-panel')
const $settingsBackBtn = document.getElementById('settings-back-btn')
const $userProfileBtn  = document.getElementById('user-profile-btn')

// Tier dropdown
const $tierBtn           = document.getElementById('tier-btn')
const $tierPopup         = document.getElementById('tier-popup')
const $tierLabel         = document.getElementById('tier-label')
const $tierCheckStandard = document.getElementById('tier-check-standard')
const $tierCheckDeep     = document.getElementById('tier-check-deep')

// ── State ─────────────────────────────────────────────────────
let conversationHistory = []
let sessionId           = null
let sessions            = {}
// quality_tier is per-conversation; resets to "standard" on new session
let qualityTier         = 'standard'

try {
  sessions = JSON.parse(localStorage.getItem('tts_sessions') ?? '{}')
} catch { sessions = {} }

// ── Health ────────────────────────────────────────────────────
async function checkHealth() {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 5000)
  try {
    const res  = await fetch(`${API}/health`, { signal: controller.signal })
    clearTimeout(timer)
    const data = await res.json()
    setHealth(res.ok && data.status === 'healthy' ? 'green' : 'yellow')
  } catch {
    clearTimeout(timer)
    setHealth('red')
  }
}

function setHealth(level) {
  const colors = { green: '#22C55E', yellow: '#EAB308', red: '#E4002B' }
  const labels = { green: 'Daring', yellow: 'Degraded', red: 'Luring' }
  $healthDot.style.background = colors[level]
  $healthText.textContent     = labels[level]
}

// ── Settings ──────────────────────────────────────────────────
function openSettings() {
  $settingsPanel.style.display   = 'flex'
  $settingsPanel.style.animation = 'msg-in 0.18s ease both'
}

function closeSettings() {
  $settingsPanel.style.display = 'none'
}

$userProfileBtn.addEventListener('click', openSettings)
$settingsBackBtn.addEventListener('click', closeSettings)

document.querySelectorAll('.snav-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.snav-btn').forEach(b => b.classList.remove('snav-active'))
    document.querySelectorAll('.spage').forEach(p => { p.style.display = 'none' })
    btn.classList.add('snav-active')
    const page = document.getElementById(`spage-${btn.dataset.page}`)
    if (page) page.style.display = 'block'
    if (btn.dataset.page === 'usage') loadUsagePage()
  })
})

// ── Token Usage Page ──────────────────────────────────────────
const _MONTH_ID = ['Januari','Februari','Maret','April','Mei','Juni','Juli','Agustus','September','Oktober','November','Desember']
const _AGENT_LABELS = {
  query_rewriter: 'Query Rewriter', intent_classifier: 'Intent Classifier',
  query_planner: 'Query Planner', schema_retriever: 'Schema Retriever',
  retrieval_evaluator: 'Retrieval Evaluator', sql_generator: 'SQL Generator',
  sql_validator: 'SQL Validator', query_executor: 'Query Executor',
  insight_generator: 'Insight Generator', analytics_agent: 'Analytics Agent',
  response_planner: 'Response Planner',
}
const _TIER_LABELS = { standard: 'Standar', deep: 'Lebih Mendalam' }

function _fmt(n) {
  return Math.round(n).toLocaleString('id-ID')
}

let _usageLoaded = false

async function loadUsagePage() {
  if (_usageLoaded) return
  const $loading = document.getElementById('usage-loading')
  const $content = document.getElementById('usage-content')

  try {
    const res  = await fetch('/usage/summary?period=current_month')
    const data = await res.json()

    // Period label
    const now = new Date()
    document.getElementById('usage-period-label').textContent =
      `Kuota bulan ini — ${_MONTH_ID[now.getMonth()]} ${now.getFullYear()}`

    // Big numbers
    const total = data.total_tokens || 0
    const quota = data.quota || 5000000
    const pct   = data.quota_used_pct ?? ((total / quota) * 100)
    document.getElementById('usage-total-num').textContent = _fmt(total)
    document.getElementById('usage-quota-num').textContent = _fmt(quota)
    document.getElementById('usage-bar').style.width = Math.min(pct, 100) + '%'
    document.getElementById('usage-pct-text').textContent = `${pct.toFixed(1)}% terpakai`

    // Stat cards
    document.getElementById('usage-prompt').textContent     = _fmt(data.prompt_tokens || 0)
    document.getElementById('usage-completion').textContent = _fmt(data.completion_tokens || 0)
    const calls = data.llm_calls || 1
    document.getElementById('usage-per-query').textContent = _fmt(total / calls)

    // Per-mode table
    const tierTbody = document.getElementById('usage-tier-tbody')
    tierTbody.innerHTML = ''
    ;(data.by_tier || []).forEach((row, i) => {
      const pctRow = total > 0 ? ((row.total_tokens / total) * 100).toFixed(0) : 0
      const bg     = i % 2 === 1 ? 'background:#FAFAF9;' : ''
      tierTbody.insertAdjacentHTML('beforeend', `
        <tr style="border-top:1px solid #EBE8E3;${bg}">
          <td style="padding:11px 16px;font-size:13px;color:#2A2724;">${_TIER_LABELS[row.quality_tier] || row.quality_tier}</td>
          <td style="padding:11px 16px;font-size:13px;color:#2A2724;text-align:right;font-family:var(--font-mono);">${_fmt(row.total_tokens)}</td>
          <td style="padding:11px 16px;font-size:13px;color:#2A2724;text-align:right;">${pctRow}%</td>
        </tr>`)
    })

    // Per-agent table
    const agentTbody = document.getElementById('usage-agent-tbody')
    agentTbody.innerHTML = ''
    ;(data.by_agent || []).sort((a, b) => b.total_tokens - a.total_tokens).forEach((row, i) => {
      const bg = i % 2 === 1 ? 'background:#FAFAF9;' : ''
      agentTbody.insertAdjacentHTML('beforeend', `
        <tr style="border-top:1px solid #EBE8E3;${bg}">
          <td style="padding:11px 16px;font-size:13px;color:#2A2724;">${_AGENT_LABELS[row.agent_name] || row.agent_name}</td>
          <td style="padding:11px 16px;font-size:13px;color:#2A2724;text-align:right;font-family:var(--font-mono);">${_fmt(row.total_tokens)}</td>
          <td style="padding:11px 16px;font-size:13px;color:#9B9693;text-align:right;">${row.llm_calls}</td>
        </tr>`)
    })

    $loading.style.display = 'none'
    $content.style.display = 'block'
    _usageLoaded = true
  } catch (e) {
    $loading.innerHTML = '<span style="color:#E4002B;">Gagal memuat data penggunaan.</span>'
  }
}

// ── Quality tier ──────────────────────────────────────────────
function setQualityTier(tier) {
  qualityTier = tier
  const isDeep = tier === 'deep'

  $tierLabel.textContent = isDeep ? 'Lebih Mendalam' : 'Standar'
  $tierBtn.classList.toggle('is-deep', isDeep)

  // Update checkmarks
  document.querySelectorAll('.tier-opt').forEach(opt => {
    const active = opt.dataset.tier === tier
    opt.classList.toggle('is-active', active)
    opt.querySelector('svg').style.display = active ? '' : 'none'
    opt.setAttribute('aria-selected', active ? 'true' : 'false')
  })
}

function openTierPopup() {
  $tierPopup.style.display = ''
  $tierBtn.classList.add('is-open')
  $tierBtn.setAttribute('aria-expanded', 'true')
}

function closeTierPopup() {
  $tierPopup.style.display = 'none'
  $tierBtn.classList.remove('is-open')
  $tierBtn.setAttribute('aria-expanded', 'false')
}

$tierBtn.addEventListener('click', e => {
  e.stopPropagation()
  $tierPopup.style.display === 'none' ? openTierPopup() : closeTierPopup()
})

document.querySelectorAll('.tier-opt').forEach(opt => {
  opt.addEventListener('click', () => {
    setQualityTier(opt.dataset.tier)
    closeTierPopup()
  })
})

// Close popup when clicking outside
document.addEventListener('click', e => {
  if (!$tierBtn.contains(e.target) && !$tierPopup.contains(e.target)) {
    closeTierPopup()
  }
})

// ── Session helpers ───────────────────────────────────────────
function newSession() {
  sessionId           = null
  conversationHistory = []
  $messages.innerHTML     = ''
  $messages.style.display = 'none'
  $welcome.style.display  = 'flex'
  $convTitle.textContent  = 'Settlement AI'
  $convMeta.textContent   = ''
  setQualityTier('standard')   // reset to default on new conversation
  renderHistory()
}

function trimResponse(data) {
  return {
    insights:          data.insights,
    sql:               data.sql,
    data:              data.data?.slice(0, 50) ?? [],
    row_count:         data.row_count,
    is_multi_step:     data.is_multi_step,
    execution_time_ms: data.execution_time_ms,
    chart_config:      data.chart_config ?? null,
    chart_configs:     data.chart_configs ?? [],
    tool_calls:        data.tool_calls ?? null,
    intent:            data.intent,
    step_results:      data.step_results?.map(s => ({
      step_number: s.step_number,
      description: s.description,
      sql:         s.sql,
      row_count:   s.row_count,
      summary:     s.summary,
      data:        s.data?.slice(0, 20) ?? [],
    })),
    metadata: {
      request_id:       data.metadata?.request_id,
      intent:           data.metadata?.intent,
      errors:           data.metadata?.errors,
      database:         data.metadata?.database,
      tables_retrieved: data.metadata?.tables_retrieved,
      tables_used:      data.metadata?.tables_used,
      pipeline_stage:   data.metadata?.pipeline_stage,
      timing:           data.metadata?.timing,
    },
  }
}

function saveSession(question, responseData) {
  if (!sessionId) return
  const existing = sessions[sessionId]
  const turns    = existing?.turns ?? []
  sessions[sessionId] = {
    title:       existing?.title ?? question.slice(0, 58),
    history:     conversationHistory,
    qualityTier: qualityTier,
    turns:       [...turns, { question, response: trimResponse(responseData), qualityTier }],
    timestamp:   Date.now(),
  }
  try {
    const ids = Object.keys(sessions).sort((a, b) => sessions[b].timestamp - sessions[a].timestamp)
    if (ids.length > 50) ids.slice(50).forEach(id => delete sessions[id])
    localStorage.setItem('tts_sessions', JSON.stringify(sessions))
  } catch {
    try {
      const ids = Object.keys(sessions).sort((a, b) => sessions[b].timestamp - sessions[a].timestamp)
      ids.slice(10).forEach(id => delete sessions[id])
      localStorage.setItem('tts_sessions', JSON.stringify(sessions))
    } catch { /* ignore */ }
  }
  renderHistory()
}

function restoreSession(id) {
  const s = sessions[id]
  if (!s) return

  sessionId           = id
  conversationHistory = s.history ?? []

  $messages.innerHTML     = ''
  $messages.style.display = 'flex'
  $welcome.style.display  = 'none'

  // Restore tier for this conversation (defaults to standard for old sessions)
  setQualityTier(s.qualityTier ?? 'standard')

  // Update header
  $convTitle.textContent = s.title ?? 'Settlement AI'
  $convMeta.textContent  = _relTime(s.timestamp)

  const turns = s.turns ?? []
  if (turns.length === 0) {
    const notice = document.createElement('div')
    notice.style.cssText = 'display:flex;justify-content:flex-start;'
    notice.innerHTML = `<div style="padding:12px 16px;background:#FFFBEB;border:1px solid #FDE68A;border-radius:14px;font-size:13px;color:#92400E;max-width:460px;line-height:1.5;">
      Percakapan ini tidak dapat dipulihkan. Mulai percakapan baru.
    </div>`
    $messages.appendChild(notice)
  } else {
    turns.forEach(turn => {
      try {
        appendUserMessage($messages, turn.question)
        appendAssistantMessage($messages, turn.response, turn.qualityTier ?? 'standard')
      } catch (err) {
        console.error('restoreSession render error:', err)
        appendErrorMessage($messages, 'Gagal memuat pesan ini.')
      }
    })
  }
  scrollDown()
  renderHistory()
}

function deleteSession(id) {
  delete sessions[id]
  try { localStorage.setItem('tts_sessions', JSON.stringify(sessions)) } catch { /* ignore */ }
  if (id === sessionId) newSession()
  else renderHistory()
}

// Group sessions by date
function _groupSessions(ids) {
  const now   = Date.now()
  const DAY   = 86_400_000
  const groups = [
    { key: 'today',   label: 'HARI INI',             ids: [] },
    { key: 'yest',    label: 'KEMARIN',               ids: [] },
    { key: 'week',    label: 'TIGA HARI TERAKHIR',    ids: [] },
    { key: 'older',   label: 'LEBIH LAMA',            ids: [] },
  ]
  ids.forEach(id => {
    const age = now - (sessions[id]?.timestamp ?? 0)
    if (age < DAY)       groups[0].ids.push(id)
    else if (age < 2*DAY) groups[1].ids.push(id)
    else if (age < 7*DAY) groups[2].ids.push(id)
    else                  groups[3].ids.push(id)
  })
  return groups.filter(g => g.ids.length > 0)
}

function _relTime(ts) {
  if (!ts) return ''
  const diff = Date.now() - ts
  const m = Math.floor(diff / 60_000)
  const h = Math.floor(diff / 3_600_000)
  const d = Math.floor(diff / 86_400_000)
  if (m < 1)   return 'baru saja'
  if (m < 60)  return `${m} menit lalu`
  if (h < 24)  return `${h} jam lalu`
  if (d < 7)   return `${d} hari lalu`
  return new Date(ts).toLocaleDateString('id-ID', { day: 'numeric', month: 'short' })
}

function renderHistory(filter = '') {
  const ids = Object.keys(sessions)
    .sort((a, b) => sessions[b].timestamp - sessions[a].timestamp)
    .slice(0, 50)
    .filter(id => !filter || sessions[id]?.title?.toLowerCase().includes(filter.toLowerCase()))

  // Clear existing items & group labels
  $historyList.querySelectorAll('.hist-item, .hist-group-label').forEach(el => el.remove())
  $historyEmpty.style.display = ids.length === 0 ? '' : 'none'

  const groups = _groupSessions(ids)
  groups.forEach(group => {
    // Group label
    const label = document.createElement('p')
    label.className   = 'hist-group-label'
    label.textContent = group.label
    $historyList.appendChild(label)

    // Session items
    group.ids.forEach(id => {
      const s    = sessions[id]
      const wrap = document.createElement('div')
      wrap.className = 'hist-item' + (id === sessionId ? ' is-active' : '')

      const btn = document.createElement('button')
      btn.className   = 'hist-btn'
      btn.title       = s.title
      btn.textContent = s.title
      btn.addEventListener('click', () => restoreSession(id))

      const del = document.createElement('button')
      del.className = 'hist-del'
      del.title     = 'Hapus'
      del.innerHTML = '<svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>'
      del.addEventListener('click', e => { e.stopPropagation(); deleteSession(id) })

      wrap.appendChild(btn)
      wrap.appendChild(del)
      $historyList.appendChild(wrap)
    })
  })
}

// Global for search filter
window.filterHistory = function(val) { renderHistory(val) }

// ── Submit ────────────────────────────────────────────────────
async function submit() {
  const question = $input.value.trim()
  if (question.length < 3 || $submitBtn.disabled) return

  if (!sessionId) {
    sessionId = `s${Date.now()}`
    // Update header title for new session
    $convTitle.textContent = question.slice(0, 58)
    $convMeta.textContent  = 'baru saja'
  }

  $welcome.style.display  = 'none'
  $messages.style.display = 'flex'

  $input.value         = ''
  $input.style.height  = 'auto'
  _setSubmitEnabled(false)
  $input.disabled      = true

  appendUserMessage($messages, question)
  const loader = appendLoadingMessage($messages)
  scrollDown()

  // Capture tier at submit time so the badge matches even if user changes it mid-flight
  const tierAtSubmit = qualityTier

  try {
    const res = await fetch(`${API}/query`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        database:             'financial_db',
        conversation_history: conversationHistory,
        quality_tier:         tierAtSubmit,
        session_id:           sessionId,
      }),
    })

    removeElement(loader)

    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      const msg = err.detail?.error ?? err.error ?? `HTTP ${res.status}`
      appendErrorMessage($messages, msg)
    } else {
      const data = await res.json()
      if (data.metadata?.needs_clarification) {
        appendClarificationMessage($messages, data.metadata.clarification_reason)
      } else {
        appendAssistantMessage($messages, data, tierAtSubmit)
        conversationHistory = data.conversation_history ?? conversationHistory
        saveSession(question, data)
      }
    }
  } catch {
    removeElement(loader)
    appendErrorMessage($messages, 'Tidak dapat terhubung ke server. Pastikan API berjalan di port 8000.')
  }

  $input.disabled = false
  _setSubmitEnabled($input.value.trim().length >= 3)
  $input.focus()
  scrollDown()
}

function _setSubmitEnabled(enabled) {
  $submitBtn.disabled       = !enabled
  $submitBtn.style.opacity  = enabled ? '1' : '0.4'
  $submitBtn.style.cursor   = enabled ? 'pointer' : 'not-allowed'
}

function scrollDown() {
  requestAnimationFrame(() => { $messages.scrollTop = $messages.scrollHeight })
}

// ── Event listeners ───────────────────────────────────────────
$input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey) {
    e.preventDefault()
    submit()
  }
})

$input.addEventListener('input', () => {
  $input.style.height = 'auto'
  $input.style.height = Math.min($input.scrollHeight, 120) + 'px'
  _setSubmitEnabled($input.value.trim().length >= 3)
})

$submitBtn.addEventListener('click', submit)
$newChatBtn.addEventListener('click', newSession)

document.querySelectorAll('.suggestion-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    $input.value = btn.textContent.trim()
    $input.dispatchEvent(new Event('input'))
    $input.focus()
  })
})

// ── Init ──────────────────────────────────────────────────────
checkHealth()
setInterval(checkHealth, 30_000)
renderHistory()
