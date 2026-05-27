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
} from '/ui/renderer.js'

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

function saveSession(firstQuestion) {
  if (!sessionId) return
  const existing = sessions[sessionId]
  sessions[sessionId] = {
    title:     existing?.title ?? firstQuestion.slice(0, 60),
    history:   conversationHistory,
    timestamp: Date.now(),
  }
  try {
    // Prune to 50 entries to keep localStorage manageable
    const ids = Object.keys(sessions).sort((a, b) => sessions[b].timestamp - sessions[a].timestamp)
    if (ids.length > 50) {
      ids.slice(50).forEach(id => delete sessions[id])
    }
    localStorage.setItem('tts_sessions', JSON.stringify(sessions))
  } catch {
    // storage quota exceeded — continue silently
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

  // Show a restore notice in the message area
  const notice = document.createElement('div')
  notice.className = 'flex justify-center py-2'
  notice.innerHTML = `
    <span class="text-xs text-slate-400 bg-slate-100 px-3 py-1.5 rounded-full">
      Sesi dipulihkan · ${conversationHistory.length} pesan dalam konteks
    </span>
  `
  $messages.appendChild(notice)
  renderHistory()
}

function renderHistory() {
  const ids = Object.keys(sessions)
    .sort((a, b) => sessions[b].timestamp - sessions[a].timestamp)
    .slice(0, 40)

  $historyEmpty.classList.toggle('hidden', ids.length > 0)

  $historyList.querySelectorAll('.history-item').forEach(el => el.remove())

  ids.forEach(id => {
    const s   = sessions[id]
    const btn = document.createElement('button')
    btn.className = [
      'history-item',
      'w-full text-left px-2.5 py-2 rounded-lg text-xs transition-colors truncate',
      id === sessionId ? 'is-active' : 'text-slate-600 hover:bg-slate-100',
    ].join(' ')
    btn.title       = s.title
    btn.textContent = s.title
    btn.addEventListener('click', () => restoreSession(id))
    $historyList.insertBefore(btn, $historyEmpty)
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
        saveSession(question)
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
