import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Bot, Send, CheckCircle2, XCircle, Loader2, ChevronDown, ChevronUp,
  Zap, ShoppingBag, Clock, Server, Terminal, ShieldCheck, KeyRound, Globe, ExternalLink
} from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import {
  listMerchants, createSession, getAuditTrail, AgentWebSocket, type Merchant,
  getRazorpayMcpStatus, getRazorpayMcpTools, callRazorpayMcpTool,
  type RazorpayMcpStatus, type RazorpayMcpTool
} from '../lib/api'
import { GlassCard } from '../components/ui/GlassCard'
import { Badge } from '../components/ui/Badge'
import { CodePill } from '../components/ui/CodePill'

type MsgRole = 'user' | 'agent' | 'system' | 'gate' | 'success' | 'error'
interface ChatMsg {
  id: string
  role: MsgRole
  content?: string
  gateData?: ConfirmData
  successData?: SuccessData
}

interface ConfirmData {
  product_id: string
  product_name: string
  price_inr: number
  merchant_name: string
  return_policy_days?: number
  shipping_info?: string
}

interface SuccessData {
  payment_id: string
  product_name: string
  amount_inr: number
  payment_method: string
}

let msgIdCounter = 0
const newId = () => `msg_${++msgIdCounter}`

export default function BuyerPage() {
  const [merchants, setMerchants] = useState<Merchant[]>([])
  const [selectedMerchant, setSelectedMerchant] = useState('')
  const [spendingLimit, setSpendingLimit] = useState(2000)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [connected, setConnected] = useState(false)
  const [loading, setLoading] = useState(false)
  const [thinking, setThinking] = useState(false)
  const [sessionDone, setSessionDone] = useState(false)
  const [auditTrail, setAuditTrail] = useState<any[] | null>(null)
  const [showAudit, setShowAudit] = useState(false)
  const [aiProvider, setAiProvider] = useState<string | null>(null)
  const wsRef = useRef<AgentWebSocket | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Razorpay Remote MCP State
  const [mcpStatus, setMcpStatus] = useState<RazorpayMcpStatus | null>(null)
  const [mcpTools, setMcpTools] = useState<RazorpayMcpTool[]>([])
  const [showMcpModal, setShowMcpModal] = useState(false)
  const [mcpSearch, setMcpSearch] = useState('')
  const [mcpTesting, setMcpTesting] = useState(false)
  const [mcpTestResult, setMcpTestResult] = useState<any | null>(null)

  // Load merchants & MCP status
  useEffect(() => {
    listMerchants()
      .then(ms => {
        const safe = Array.isArray(ms) ? ms : []
        setMerchants(safe)
        if (safe.length > 0) setSelectedMerchant(safe[0].merchant_id)
      })
      .catch(() => {
        setMerchants([])
      })

    getRazorpayMcpStatus().then(st => setMcpStatus(st)).catch(() => {})
    getRazorpayMcpTools().then(res => setMcpTools(res?.tools || [])).catch(() => {})
  }, [])

  const handleTestMcpCall = async () => {
    setMcpTesting(true)
    setMcpTestResult(null)
    try {
      const res = await callRazorpayMcpTool('create_payment_link', {
        amount: 25000,
        currency: 'INR',
        description: 'Frontend Live MCP Verification Link',
      })
      setMcpTestResult(res)
      toast.success('Live test payment link created via Razorpay Remote MCP!')
    } catch (err: any) {
      toast.error(err.message || 'MCP tool call failed')
    } finally {
      setMcpTesting(false)
    }
  }

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, thinking])

  const addMsg = useCallback((role: MsgRole, content?: string, extra?: Partial<ChatMsg>) => {
    setMessages(m => [...m, { id: newId(), role, content, ...extra }])
  }, [])

  const startSession = async () => {
    if (!selectedMerchant) { toast.error('Select a merchant'); return }
    if (!input.trim()) { toast.error('Enter a purchase intent'); return }

    const intent = input.trim()
    setInput('')
    setLoading(true)
    setSessionDone(false)
    setMessages([])
    setAuditTrail(null)

    try {
      const sess = await createSession(selectedMerchant, intent, spendingLimit)
      setSessionId(sess.session_id)
      addMsg('user', intent)
      addMsg('system', `Session started · ${sess.merchant_name} · Budget ₹${spendingLimit.toLocaleString()}`)

      // Connect WebSocket
      const ws = new AgentWebSocket(sess.session_id)
      wsRef.current = ws

      ws.connect(
        (event) => handleWsEvent(event, sess.session_id),
        () => {
          setConnected(true)
          setLoading(false)
          ws.sendMessage(intent)
        },
        () => {
          setConnected(false)
          setThinking(false)
        },
        () => {
          setConnected(false)
          setThinking(false)
          toast.error('Connection lost. Please start a new session.')
        }
      )
    } catch (e: any) {
      toast.error(e.message)
      setLoading(false)
    }
  }

  const handleWsEvent = useCallback((event: any, sid: string) => {
    switch (event.type) {
      case 'thinking':
        setThinking(true)
        break
      case 'message':
        setThinking(false)
        if (event.content) addMsg('agent', event.content)
        break
      case 'tool_call':
        // Silently process tool calls
        break
      case 'confirmation_gate':
        setThinking(false)
        addMsg('gate', undefined, { gateData: event.data })
        break
      case 'session_complete':
        setThinking(false)
        setSessionDone(true)
        if (event.data?.status === 'SUCCESS') {
          addMsg('success', undefined, { successData: {
            payment_id: event.data.payment_id,
            product_name: event.data.product_name,
            amount_inr: event.data.amount_inr,
            payment_method: event.data.payment_method,
          }})
          toast.success('Purchase complete!')
        } else if (event.data?.status === 'STOPPED') {
          addMsg('system', 'Purchase cancelled.')
        } else {
          addMsg('error', 'Payment failed. Please try directly on the merchant website.')
        }
        // Fetch audit trail
        setTimeout(() => getAuditTrail(sid).then(t => setAuditTrail(t.entries)).catch(() => {}), 500)
        break
      case 'error':
        setThinking(false)
        addMsg('error', event.content)
        break
      case 'session_info':
        setAiProvider(null)
        break
    }
  }, [addMsg])

  const sendMessage = () => {
    if (!input.trim() || !wsRef.current || sessionDone) return
    const msg = input.trim()
    setInput('')
    addMsg('user', msg)
    wsRef.current.sendMessage(msg)
    setThinking(true)
  }

  const handleConfirm = (confirmed: boolean, productId?: string) => {
    if (!wsRef.current) return
    wsRef.current.sendConfirm(confirmed, productId)
    addMsg('user', confirmed ? '✓ Confirmed — proceed with payment' : '✗ Cancelled')
    if (confirmed) setThinking(true)
    // Remove gate message
    setMessages(m => m.filter(msg => msg.role !== 'gate'))
  }

  const newSession = () => {
    wsRef.current?.close()
    wsRef.current = null
    setSessionId(null)
    setMessages([])
    setConnected(false)
    setSessionDone(false)
    setThinking(false)
    setAuditTrail(null)
    setShowAudit(false)
  }

  const merchant = merchants.find(m => m.merchant_id === selectedMerchant)

  return (
    <div className="max-w-5xl mx-auto">
      <div className="mb-8 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-gray-400 mb-2">Buyer Agent</p>
          <h1 className="text-3xl font-bold mb-2">Test AI-powered purchase</h1>
          <p className="text-gray-500">Simulates how an AI buyer discovers and purchases from a merchant catalog.</p>
        </div>
        <div>
          <button
            onClick={() => setShowMcpModal(true)}
            className="flex items-center gap-2.5 px-4 py-2.5 rounded-xl border border-emerald-200 bg-emerald-50/90 hover:bg-emerald-100 transition-all text-xs text-emerald-900 shadow-sm cursor-pointer"
          >
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <span className="font-semibold">Razorpay Remote MCP:</span>
            <span className="text-emerald-700 font-mono font-medium">
              {mcpStatus?.connected ? `Live (${mcpTools.length || 42} Tools)` : 'Connecting...'}
            </span>
          </button>
        </div>
      </div>

      <div className="grid lg:grid-cols-[320px,1fr] gap-6">
        {/* Left config panel */}
        <div className="space-y-4">
          <div className="border border-gray-200 rounded-2xl p-5">
            <h2 className="font-semibold mb-4 text-sm uppercase tracking-wide text-gray-500">Session Config</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1.5">Merchant</label>
                <select value={selectedMerchant} onChange={e => setSelectedMerchant(e.target.value)}
                  disabled={!!sessionId}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-black bg-white disabled:opacity-60">
                  {merchants.length === 0 && <option value="">No published merchants yet</option>}
                  {merchants.map(m => (
                    <option key={m.merchant_id} value={m.merchant_id}>{m.merchant_name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium mb-1.5">Budget Limit (₹)</label>
                <input type="number" value={spendingLimit} onChange={e => setSpendingLimit(Number(e.target.value))}
                  disabled={!!sessionId} min={100} max={100000}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-black disabled:opacity-60" />
              </div>
            </div>

            {merchant && (
              <div className="mt-4 p-3 bg-gray-50 rounded-xl">
                <div className="text-xs font-medium text-gray-500 mb-1">{merchant.merchant_name}</div>
                <div className="text-sm text-gray-700">{merchant.product_count} products</div>
                <div className="text-xs text-gray-400 mt-1 font-mono">/catalog/{merchant.merchant_id}</div>
              </div>
            )}
          </div>

          {/* Safety rules */}
          <div className="border border-gray-100 rounded-2xl p-5 bg-gray-50">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-3">Safety Rules</h3>
            {[
              'Confirmation gate always fires',
              'Max 2 payment attempts',
              'Budget limit enforced',
              'Full audit trail logged',
            ].map(r => (
              <div key={r} className="flex items-center gap-2 py-1.5 text-sm text-gray-600">
                <div className="w-1.5 h-1.5 bg-black rounded-full shrink-0" />
                {r}
              </div>
            ))}
          </div>

          {sessionId && (
            <button onClick={newSession}
              className="w-full border border-gray-200 text-sm font-medium py-2.5 rounded-full hover:bg-gray-50 transition-colors">
              New Session
            </button>
          )}
        </div>

        {/* Chat panel */}
        <div className="flex flex-col">
          {!sessionId ? (
            /* Start session */
            <div className="border border-gray-200 rounded-2xl p-6 flex flex-col gap-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-black rounded-xl flex items-center justify-center">
                  <Bot className="w-5 h-5 text-white" />
                </div>
                <div>
                  <div className="font-semibold">AI Buyer Agent</div>
                  <div className="text-xs text-gray-500">Powered by multi-LLM cascade</div>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Purchase Intent</label>
                <textarea value={input} onChange={e => setInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); startSession() }}}
                  placeholder={`Try: "find me a red kurta under ₹800"\n"something organic for under ₹400"\n"buy the cheapest product available"`}
                  rows={3}
                  className="w-full border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-black resize-none" />
              </div>

              <button onClick={startSession} disabled={loading || !selectedMerchant}
                className={clsx('bg-black text-white font-medium py-3 rounded-full flex items-center justify-center gap-2 transition-all',
                  loading || !selectedMerchant ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-900')}>
                {loading ? <><Loader2 className="w-4 h-4 animate-spin" /> Starting...</> : <><Send className="w-4 h-4" /> Start Session</>}
              </button>

              {merchants.length === 0 && (
                <p className="text-sm text-amber-600 text-center">
                  No merchants found. <a href="/merchant" className="underline">Onboard one first →</a>
                </p>
              )}
            </div>
          ) : (
            /* Active chat */
            <div className="border border-gray-200 rounded-2xl flex flex-col" style={{ height: '600px' }}>
              {/* Header */}
              <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className={clsx('w-2 h-2 rounded-full', connected ? 'bg-green-500' : 'bg-gray-300')} />
                  <span className="text-sm font-medium">{merchant?.merchant_name}</span>
                  <span className="text-xs text-gray-400">· Budget ₹{spendingLimit.toLocaleString()}</span>
                </div>
                {aiProvider && <span className="text-xs text-gray-400">via {aiProvider}</span>}
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
                {messages.map(msg => (
                  <MessageBubble key={msg.id} msg={msg} onConfirm={handleConfirm} />
                ))}
                {thinking && <TypingIndicator />}
                <div ref={bottomRef} />
              </div>

              {/* Input */}
              {!sessionDone && (
                <div className="px-4 py-3 border-t border-gray-100 flex gap-3">
                  <input value={input} onChange={e => setInput(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') sendMessage() }}
                    placeholder="Reply to the agent..."
                    disabled={thinking || !connected}
                    className="flex-1 border border-gray-200 rounded-full px-4 py-2 text-sm focus:outline-none focus:border-black disabled:opacity-50" />
                  <button onClick={sendMessage} disabled={thinking || !input.trim() || !connected}
                    className="bg-black text-white rounded-full p-2.5 hover:bg-gray-900 disabled:opacity-50 transition-colors">
                    <Send className="w-4 h-4" />
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Audit Trail */}
          {auditTrail && auditTrail.length > 0 && (
            <div className="mt-4 border border-gray-200 rounded-2xl overflow-hidden">
              <button onClick={() => setShowAudit(s => !s)}
                className="w-full px-5 py-3.5 flex items-center justify-between bg-gray-50 hover:bg-gray-100 transition-colors">
                <span className="text-sm font-medium">Decision Audit Trail ({auditTrail.length} steps)</span>
                {showAudit ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
              {showAudit && (
                <div className="divide-y divide-gray-100">
                  {auditTrail.map((entry: any, i: number) => (
                    <div key={i} className="px-5 py-3">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-mono font-semibold text-gray-800">{entry.step}</span>
                        <div className="flex items-center gap-2 text-xs text-gray-400">
                          {entry.latency_ms && <span>{entry.latency_ms}ms</span>}
                          {entry.model_used && <span className="bg-gray-100 px-2 py-0.5 rounded">{entry.model_used}</span>}
                        </div>
                      </div>
                      {entry.reasoning && <p className="text-xs text-gray-600">{entry.reasoning}</p>}
                      {entry.error && <p className="text-xs text-red-500">{entry.error}</p>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Razorpay Remote MCP Server Inspector Modal */}
      {showMcpModal && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-2xl w-full max-h-[85vh] flex flex-col shadow-2xl border border-gray-100 animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="p-5 border-b border-gray-100 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-700">
                  <Server className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-semibold text-gray-900 flex items-center gap-2">
                    Razorpay Remote MCP Server
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold tracking-wider uppercase bg-emerald-100 text-emerald-800">
                      Live Test Mode
                    </span>
                  </h3>
                  <p className="text-xs text-gray-500 font-mono">https://mcp.razorpay.com/mcp · Protocol: 2024-11-05</p>
                </div>
              </div>
              <button
                onClick={() => setShowMcpModal(false)}
                className="w-8 h-8 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-700 flex items-center justify-center text-lg cursor-pointer"
              >
                ×
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-5 overflow-y-auto space-y-4 text-sm flex-1">
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 bg-gray-50 rounded-xl border border-gray-100">
                  <div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-1">Active Credentials</div>
                  <div className="font-mono text-xs text-gray-800 font-medium">Key: rzp_test_TXvZCenSDbxllY</div>
                  <div className="text-[11px] text-emerald-600 font-medium mt-0.5">Dual-Engine: SDK + Hosted MCP</div>
                </div>
                <div className="p-3 bg-gray-50 rounded-xl border border-gray-100">
                  <div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-1">Connected Tools</div>
                  <div className="font-mono text-xs text-gray-800 font-medium">{mcpTools.length || 42} Remote MCP Tools</div>
                  <div className="text-[11px] text-gray-500 mt-0.5">Orders, Links, QR, Subscriptions, Refunds</div>
                </div>
              </div>

              {/* Live Test Action */}
              <div className="p-4 bg-emerald-50/70 border border-emerald-200/70 rounded-xl">
                <div className="flex items-center justify-between gap-3 mb-2">
                  <div>
                    <span className="font-semibold text-xs text-emerald-950">Verify Live MCP Tool Execution</span>
                    <p className="text-xs text-emerald-700">Calls create_payment_link directly on https://mcp.razorpay.com/mcp</p>
                  </div>
                  <button
                    onClick={handleTestMcpCall}
                    disabled={mcpTesting}
                    className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg text-xs font-semibold shrink-0 transition-colors flex items-center gap-1.5 cursor-pointer"
                  >
                    {mcpTesting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
                    <span>Run MCP Ping</span>
                  </button>
                </div>
                {mcpTestResult && (
                  <div className="mt-2 p-2.5 bg-white/90 rounded-lg border border-emerald-200 text-xs font-mono text-emerald-900 break-all">
                    <div>Status: {mcpTestResult.success ? '✓ SUCCESS' : 'FAILED'}</div>
                    {mcpTestResult.data?.id && <div>Link ID: {mcpTestResult.data.id}</div>}
                    {mcpTestResult.data?.short_url && (
                      <a href={mcpTestResult.data.short_url} target="_blank" rel="noreferrer" className="text-blue-600 underline flex items-center gap-1 mt-1">
                        {mcpTestResult.data.short_url} <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                )}
              </div>

              {/* Tool Search and List */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Available MCP Tools ({mcpTools.filter(t => t.name.toLowerCase().includes(mcpSearch.toLowerCase())).length})
                  </span>
                  <input
                    type="text"
                    placeholder="Filter tools..."
                    value={mcpSearch}
                    onChange={e => setMcpSearch(e.target.value)}
                    className="px-2.5 py-1 text-xs border border-gray-200 rounded-lg focus:outline-none focus:border-black w-44"
                  />
                </div>
                <div className="divide-y divide-gray-100 border border-gray-200 rounded-xl max-h-56 overflow-y-auto bg-gray-50/50">
                  {mcpTools
                    .filter(t => t.name.toLowerCase().includes(mcpSearch.toLowerCase()) || (t.description || '').toLowerCase().includes(mcpSearch.toLowerCase()))
                    .map((tool, idx) => (
                      <div key={idx} className="p-2.5 hover:bg-white transition-colors">
                        <div className="font-mono text-xs font-bold text-gray-900">{tool.name}</div>
                        <div className="text-xs text-gray-500 line-clamp-1 mt-0.5">{tool.description}</div>
                      </div>
                    ))}
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-gray-100 flex justify-end bg-gray-50/50 rounded-b-2xl">
              <button
                onClick={() => setShowMcpModal(false)}
                className="px-4 py-2 bg-black text-white text-xs font-semibold rounded-lg hover:bg-gray-800 transition-colors cursor-pointer"
              >
                Close Inspector
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function MessageBubble({ msg, onConfirm }: { msg: ChatMsg; onConfirm: (confirmed: boolean, id?: string) => void }) {
  if (msg.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="bg-neutral-900 text-white rounded-2xl rounded-br-sm px-4 py-2.5 max-w-[80%] text-xs sm:text-sm shadow-sm leading-relaxed">
          {msg.content}
        </div>
      </div>
    )
  }

  if (msg.role === 'system') {
    return (
      <div className="flex justify-center">
        <span className="text-[11px] text-neutral-500 bg-neutral-100 dark:bg-neutral-800 px-3 py-1 rounded-full border border-neutral-200/60 font-mono">
          {msg.content}
        </span>
      </div>
    )
  }

  if (msg.role === 'agent') {
    return (
      <div className="flex gap-3">
        <div className="w-8 h-8 bg-neutral-950 text-white rounded-xl flex items-center justify-center shrink-0 mt-0.5 shadow-sm">
          <Bot className="w-4 h-4 text-neutral-200" />
        </div>
        <div className="bg-neutral-50 dark:bg-neutral-900 border border-neutral-200/70 dark:border-neutral-800 rounded-2xl rounded-tl-sm px-4 py-3 max-w-[85%] text-xs sm:text-sm text-neutral-800 dark:text-neutral-200 whitespace-pre-wrap leading-relaxed shadow-xs">
          {msg.content}
        </div>
      </div>
    )
  }

  if (msg.role === 'gate' && msg.gateData) {
    const g = msg.gateData
    return (
      <div className="flex gap-3 w-full">
        <div className="w-8 h-8 bg-amber-500 rounded-xl flex items-center justify-center shrink-0 mt-0.5 shadow-sm">
          <ShieldCheck className="w-4 h-4 text-white" />
        </div>
        <div className="w-full max-w-[85%] animate-slide-up">
          <GlassCard glowColor="amber" className="p-5 border-2 border-amber-500/80 bg-amber-50/40 dark:bg-amber-950/20">
            <div className="flex items-center justify-between gap-2 mb-3">
              <Badge variant="warning" size="sm" pulsing>
                Non-Bypassable Safety Gate
              </Badge>
              <span className="text-[10px] font-mono text-amber-700 dark:text-amber-400">Explicit User Auth Required</span>
            </div>

            <div className="font-bold text-base sm:text-lg text-neutral-900 dark:text-neutral-100 mb-1">
              {g.product_name}
            </div>

            <div className="flex flex-wrap items-center gap-2.5 text-xs text-neutral-600 dark:text-neutral-400 mb-4">
              <span className="font-extrabold text-neutral-900 dark:text-white text-xl">
                ₹{g.price_inr.toLocaleString()}
              </span>
              <span>·</span>
              <span className="font-medium text-neutral-700 dark:text-neutral-300">{g.merchant_name}</span>
              {(g.return_policy_days ?? 0) > 0 && (
                <>
                  <span>·</span>
                  <Badge variant="outline" size="sm">
                    {g.return_policy_days}-Day Returns
                  </Badge>
                </>
              )}
            </div>

            <p className="text-[11px] text-neutral-500 dark:text-neutral-400 mb-4">
              By confirming, you authorize this test-mode transaction via the Razorpay Remote MCP pipeline. No real money will be charged.
            </p>

            <div className="flex gap-3">
              <button
                onClick={() => onConfirm(true, g.product_id)}
                className="flex-1 bg-neutral-950 hover:bg-neutral-800 text-white font-medium py-2.5 rounded-xl flex items-center justify-center gap-2 shadow-sm transition-all active:scale-[0.98] text-xs sm:text-sm cursor-pointer"
              >
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                Authorize & Pay
              </button>
              <button
                onClick={() => onConfirm(false)}
                className="px-4 border border-neutral-300 dark:border-neutral-700 hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-700 dark:text-neutral-300 font-medium py-2.5 rounded-xl transition-all active:scale-[0.98] text-xs sm:text-sm cursor-pointer"
              >
                Decline
              </button>
            </div>
          </GlassCard>
        </div>
      </div>
    )
  }

  if (msg.role === 'success' && msg.successData) {
    const s = msg.successData
    return (
      <div className="flex gap-3 w-full">
        <div className="w-8 h-8 bg-emerald-600 rounded-xl flex items-center justify-center shrink-0 mt-0.5 shadow-sm">
          <CheckCircle2 className="w-4 h-4 text-white" />
        </div>
        <div className="w-full max-w-[85%] animate-slide-up">
          <GlassCard glowColor="emerald" className="p-5 border-emerald-300 bg-emerald-50/40 dark:bg-emerald-950/20">
            <div className="flex items-center justify-between mb-2">
              <Badge variant="success" size="sm">
                Payment Captured (Test Mode)
              </Badge>
              <span className="text-[10px] font-mono text-emerald-700 dark:text-emerald-400">Method: {s.payment_method}</span>
            </div>

            <div className="font-semibold text-neutral-900 dark:text-neutral-100 text-sm sm:text-base mb-1">
              {s.product_name}
            </div>

            <div className="text-xl font-bold text-emerald-700 dark:text-emerald-400 mb-3">
              ₹{s.amount_inr.toLocaleString()}
            </div>

            <div className="flex items-center justify-between gap-2 pt-3 border-t border-emerald-200/60 dark:border-emerald-800/60 text-xs">
              <span className="text-neutral-500 font-mono text-[11px]">Payment Reference:</span>
              <CodePill code={s.payment_id} className="bg-white/80 dark:bg-neutral-900/80 border-emerald-200" />
            </div>
          </GlassCard>
        </div>
      </div>
    )
  }

  if (msg.role === 'error') {
    return (
      <div className="flex gap-3">
        <div className="w-8 h-8 bg-red-500 rounded-xl flex items-center justify-center shrink-0 mt-0.5 shadow-sm">
          <XCircle className="w-4 h-4 text-white" />
        </div>
        <div className="bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/50 rounded-2xl rounded-tl-sm px-4 py-3 max-w-[85%] text-xs sm:text-sm text-red-700 dark:text-red-300">
          {msg.content}
        </div>
      </div>
    )
  }

  return null
}

function TypingIndicator() {
  return (
    <div className="flex gap-3">
      <div className="w-7 h-7 bg-black rounded-lg flex items-center justify-center shrink-0">
        <Bot className="w-3.5 h-3.5 text-white" />
      </div>
      <div className="bg-gray-50 rounded-2xl rounded-tl-sm px-4 py-3 flex gap-1 items-center">
        <span className="typing-dot" />
        <span className="typing-dot" />
        <span className="typing-dot" />
      </div>
    </div>
  )
}
