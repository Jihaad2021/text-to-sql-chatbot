/**
 * app.js — Main application logic.
 * Manages state, API calls, session history, and event wiring.
 */

import {
  appendUserMessage,
  appendLoadingMessage,
  appendAssistantMessage,
  appendErrorMessage,
  appendClarificationMessage,
  removeElement,
} from '/ui/renderer.js?v=5'

// ── Config ────────────────────────────────────────────────────
const API = window.location.origin

// ── DOM refs ──────────────────────────────────────────────────
const $messages     = document.getElementById('messages')
const $welcome      = document.getElementById('welcome')
const $input        = document.getElementById('query-input')
const $submitBtn    = document.getElementById('submit-btn')
const $newChatBtn   = document.getElementById('new-chat-btn')
const $healthDot    = document.getElementById('health-dot')
const $healthText   = document.getElementById('health-text')
const $historyList  = document.getElementById('history-list')
const $historyEmpty = document.getElementById('history-empty')

// ── State ─────────────────────────────────────────────────────
let conversationHistory = []   // API conversation_history payload
let sessionId           = null // current session key
let sessions            = {}   // { [id]: { title, history, timestamp } }

try {
  sessions = JSON.parse(localStorage.getItem('tts_sessions') ?? '{}')
} catch {
  sessions = {}
}

// ── Health check ──────────────────────────────────────────────
async function checkHealth() {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 5000)

  try {
    const res  = await fetch(`${API}/health`, { signal: controller.signal })
    clearTimeout(timer)
    const data = await res.json()

    if (res.ok && data.status === 'healthy') {
      setHealth('green', 'Terhubung')
    } else {
      setHealth('yellow', 'Degraded')
    }
  } catch {
    clearTimeout(timer)
    setHealth('red', 'Tidak terhubung')
  }
}

function setHealth(level, label) {
  const colors = {
    green:  'bg-green-400',
    yellow: 'bg-yellow-400',
    red:    'bg-red-400',
  }
  $healthDot.className  = `w-2 h-2 rounded-full ${colors[level]}`
  $healthText.textContent = label
}

// ── Sessions ──────────────────────────────────────────────────
function newSession() {
  sessionId = null
  conversationHistory = []
  $messages.innerHTML = ''
  $messages.classList.add('hidden')
  $welcome.classList.remove('hidden')
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
    step_results:      data.step_results?.map(s => ({
      step_number:  s.step_number,
      description:  s.description,
      sql:          s.sql,
      row_count:    s.row_count,
      summary:      s.summary,
      data:         s.data?.slice(0, 20) ?? [],
    })),
    metadata: {
      intent:           data.metadata?.intent,
      errors:           data.metadata?.errors,
      database:         data.metadata?.database,
      tables_retrieved: data.metadata?.tables_retrieved,
      tables_used:      data.metadata?.tables_used,
      pipeline_stage:   data.metadata?.pipeline_stage,
    },
  }
}

function saveSession(question, responseData) {
  if (!sessionId) return
  const existing = sessions[sessionId]
  const turns    = existing?.turns ?? []
  sessions[sessionId] = {
    title:     existing?.title ?? question.slice(0, 60),
    history:   conversationHistory,
    turns:     [...turns, { question, response: trimResponse(responseData) }],
    timestamp: Date.now(),
  }
  try {
    const ids = Object.keys(sessions).sort((a, b) => sessions[b].timestamp - sessions[a].timestamp)
    if (ids.length > 50) ids.slice(50).forEach(id => delete sessions[id])
    localStorage.setItem('tts_sessions', JSON.stringify(sessions))
  } catch {
    // kuota penuh — coba hapus session terlama lalu simpan lagi
    try {
      const ids = Object.keys(sessions).sort((a, b) => sessions[b].timestamp - sessions[a].timestamp)
      ids.slice(10).forEach(id => delete sessions[id])
      localStorage.setItem('tts_sessions', JSON.stringify(sessions))
    } catch {
      // tetap gagal — session hanya ada di memory, tidak persisten
    }
  }
  renderHistory()
}

function restoreSession(id) {
  const s = sessions[id]
  if (!s) return

  sessionId           = id
  conversationHistory = s.history ?? []

  $messages.innerHTML = ''
  $messages.classList.remove('hidden')
  $welcome.classList.add('hidden')

  const turns = s.turns ?? []

  if (turns.length === 0) {
    // Session lama tanpa data turns — tampilkan pesan informatif
    const notice = document.createElement('div')
    notice.className = 'flex justify-start msg-enter'
    notice.innerHTML = `<div class="px-4 py-3 bg-amber-50 border border-amber-200 rounded-2xl text-sm text-amber-700">
      Percakapan ini tidak dapat dipulihkan (disimpan sebelum versi terbaru). Mulai percakapan baru.
    </div>`
    $messages.appendChild(notice)
  } else {
    turns.forEach(turn => {
      try {
        appendUserMessage($messages, turn.question)
        appendAssistantMessage($messages, turn.response)
      } catch (err) {
        console.error('restoreSession render error:', err, turn)
        appendErrorMessage($messages, 'Gagal memuat pesan ini.')
      }
    })
  }

  scrollDown()
  renderHistory()
}

function deleteSession(id) {
  delete sessions[id]
  try {
    localStorage.setItem('tts_sessions', JSON.stringify(sessions))
  } catch { /* ignore */ }
  if (id === sessionId) {
    newSession()
  } else {
    renderHistory()
  }
}

function renderHistory() {
  const ids = Object.keys(sessions)
    .sort((a, b) => sessions[b].timestamp - sessions[a].timestamp)
    .slice(0, 40)

  $historyEmpty.classList.toggle('hidden', ids.length > 0)
  $historyList.querySelectorAll('.history-item').forEach(el => el.remove())

  ids.forEach(id => {
    const s    = sessions[id]
    const wrap = document.createElement('div')
    wrap.className = 'history-item group flex items-center rounded-lg ' +
      (id === sessionId ? 'is-active' : 'hover:bg-slate-100')

    const btn = document.createElement('button')
    btn.className = 'flex-1 min-w-0 text-left px-2.5 py-2 text-xs transition-colors truncate ' +
      (id === sessionId ? 'text-blue-700 font-medium' : 'text-slate-600')
    btn.title       = s.title
    btn.textContent = s.title
    btn.addEventListener('click', () => restoreSession(id))

    const del = document.createElement('button')
    del.className = 'shrink-0 p-1.5 mr-1 rounded text-slate-300 hover:text-red-500 ' +
      'opacity-0 group-hover:opacity-100 transition-opacity'
    del.title     = 'Hapus percakapan'
    del.innerHTML = '<svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">' +
      '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>' +
      '</svg>'
    del.addEventListener('click', e => {
      e.stopPropagation()
      deleteSession(id)
    })

    wrap.appendChild(btn)
    wrap.appendChild(del)
    $historyList.insertBefore(wrap, $historyEmpty)
  })
}

// ── Submit ────────────────────────────────────────────────────
async function submit() {
  const question = $input.value.trim()
  if (question.length < 3 || $submitBtn.disabled) return

  // Start session on first message
  if (!sessionId) sessionId = `s${Date.now()}`

  // Show chat area
  $welcome.classList.add('hidden')
  $messages.classList.remove('hidden')

  // Clear input
  $input.value         = ''
  $input.style.height  = 'auto'
  $submitBtn.disabled  = true
  $input.disabled      = true

  appendUserMessage($messages, question)
  const loader = appendLoadingMessage($messages)
  scrollDown()

  try {
    const res = await fetch(`${API}/query`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        database:             'financial_db',
        conversation_history: conversationHistory,
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
        appendAssistantMessage($messages, data)
        conversationHistory = data.conversation_history ?? conversationHistory
        saveSession(question, data)
      }
    }

  } catch {
    removeElement(loader)
    appendErrorMessage($messages, 'Tidak dapat terhubung ke server. Pastikan API berjalan di port 8000.')
  }

  $input.disabled     = false
  $submitBtn.disabled = $input.value.trim().length < 3
  $input.focus()
  scrollDown()
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
  // Auto-resize textarea
  $input.style.height = 'auto'
  $input.style.height = Math.min($input.scrollHeight, 128) + 'px'
  $submitBtn.disabled = $input.value.trim().length < 3
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
