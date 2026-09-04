import { useState, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  Clock, Bot, CheckCircle2, XCircle, ArrowRight, Shield, Sparkles,
  Layers, ChevronRight, FileText, Activity, AlertTriangle, RefreshCw, Search, ArrowUpRight
} from 'lucide-react'
import clsx from 'clsx'
import { listSessions, getAuditTrail } from '../lib/api'
import { GlassCard } from '../components/ui/GlassCard'
import { Badge } from '../components/ui/Badge'
import { CodePill } from '../components/ui/CodePill'
import { StatusIndicator } from '../components/ui/StatusIndicator'

const STEP_COLORS: Record<string, { variant: 'emerald' | 'amber' | 'indigo' | 'rose' | 'neutral'; label: string }> = {
  session_started: { variant: 'neutral', label: 'Session Started' },
  search_catalog: { variant: 'indigo', label: 'Vector Search' },
  options_presented: { variant: 'indigo', label: 'Options Presented' },
  product_selected: { variant: 'indigo', label: 'Product Selected' },
  availability_checked: { variant: 'neutral', label: 'Inventory Checked' },
  permission_checked: { variant: 'amber', label: 'Guardrails Verified' },
  confirmation_gate: { variant: 'amber', label: 'Human Confirmation Gate' },
  payment_initiated: { variant: 'indigo', label: 'Razorpay Payment Link' },
  payment_status_polled: { variant: 'indigo', label: 'Webhook / Status Polled' },
  payment_confirmed: { variant: 'emerald', label: 'Payment Captured' },
  payment_failed: { variant: 'rose', label: 'Payment Failed' },
  retry_initiated: { variant: 'amber', label: 'Retry Attempt' },
  session_complete: { variant: 'emerald', label: 'Session Complete' },
  error: { variant: 'rose', label: 'Runtime Error' },
  fallback_used: { variant: 'amber', label: 'Provider Fallback' },
}

export default function AuditPage() {
  const { sessionId } = useParams()
  const [sessions, setSessions] = useState<any[]>([])
  const [selected, setSelected] = useState<string | null>(sessionId || null)
  const [trail, setTrail] = useState<any | null>(null)
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'SUCCESS' | 'FAILED' | 'ACTIVE'>('ALL')
  const [searchQuery, setSearchQuery] = useState('')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const fetchSessions = useCallback(async (selectFirst = false) => {
    setRefreshing(true)
    setErrorMsg(null)
    try {
      const s = await listSessions()
      const safeSessions = Array.isArray(s) ? s : []
      setSessions(safeSessions)
      if (safeSessions.length > 0 && (selectFirst || !selected)) {
        setSelected(safeSessions[0].session_id)
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to load session list')
    } finally {
      setRefreshing(false)
    }
  }, [selected])

  useEffect(() => {
    fetchSessions(true)
  }, [])

  useEffect(() => {
    if (selected) {
      setLoading(true)
      getAuditTrail(selected)
        .then(t => {
          setTrail(t)
          setLoading(false)
        })
        .catch(err => {
          setLoading(false)
        })
    }
  }, [selected])

  const filteredSessions = sessions.filter(s => {
    const matchesFilter = statusFilter === 'ALL' || s.status === statusFilter
    const q = searchQuery.toLowerCase().trim()
    const matchesQuery = !q ||
      (s.session_id && s.session_id.toLowerCase().includes(q)) ||
      (s.purchase_intent && s.purchase_intent.toLowerCase().includes(q)) ||
      (s.merchant_id && s.merchant_id.toLowerCase().includes(q))
    return matchesFilter && matchesQuery
  })

  return (
    <div className="max-w-6xl mx-auto space-y-6 pb-12">
      {/* Header */}
      <div className="pb-4 border-b border-black/[0.06] flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="text-[11px] font-bold uppercase tracking-widest text-zinc-400 bg-black/[0.04] px-2.5 py-0.5 rounded-full border border-black/[0.06]">
              Compliance & Audit
            </span>
            <Badge variant="emerald" size="sm">Immutable Trace</Badge>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-zinc-900">
            Autonomous Session Audit Logs
          </h1>
          <p className="text-xs sm:text-sm text-zinc-500 mt-0.5">
            Cryptographic decision trail for every tool invocation, guardrail check, and Razorpay payment.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => fetchSessions(false)}
            disabled={refreshing}
            className="flex items-center gap-1.5 text-xs font-semibold text-zinc-700 bg-white hover:bg-zinc-50 border border-black/10 px-3 py-1.5 rounded-xl shadow-xs transition-all disabled:opacity-50"
          >
            <RefreshCw className={clsx('w-3.5 h-3.5', refreshing && 'animate-spin text-blue-600')} />
            <span>{refreshing ? 'Refreshing...' : 'Refresh Logs'}</span>
          </button>
          {selected && (
            <CodePill label="Session" code={selected} copyable />
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6 min-h-[600px]">
        {/* Session list sidebar */}
        <div className="space-y-3">
          <div className="flex items-center justify-between px-1">
            <span className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
              Recorded Sessions ({filteredSessions.length})
            </span>
            <Link
              to="/buyer"
              className="text-xs text-blue-600 hover:text-blue-700 font-semibold flex items-center gap-1 hover:underline"
            >
              Simulate Purchase <ArrowRight className="w-3 h-3" />
            </Link>
          </div>

          {/* Search Bar */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-zinc-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              placeholder="Search by intent or session ID..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-full bg-white border border-black/10 rounded-xl pl-8 pr-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-black/10 transition-all placeholder:text-zinc-400"
            />
          </div>

          {/* Status Filter Tabs */}
          <div className="flex items-center gap-1 bg-zinc-100/80 p-1 rounded-xl border border-black/[0.04] text-[11px] font-medium text-zinc-600">
            {(['ALL', 'SUCCESS', 'FAILED', 'ACTIVE'] as const).map(tab => {
              const count = sessions.filter(s => tab === 'ALL' || s.status === tab).length
              const isActive = statusFilter === tab
              return (
                <button
                  key={tab}
                  onClick={() => setStatusFilter(tab)}
                  className={clsx(
                    'flex-1 py-1 rounded-lg text-center font-semibold transition-all',
                    isActive
                      ? 'bg-white text-zinc-900 shadow-xs'
                      : 'hover:text-zinc-900 text-zinc-500'
                  )}
                >
                  {tab === 'ALL' ? 'All' : tab.charAt(0) + tab.slice(1).toLowerCase()} ({count})
                </button>
              )
            })}
          </div>

          {errorMsg && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-600">
              {errorMsg}
            </div>
          )}

          <GlassCard variant="default" padding="none" className="overflow-hidden">
            <div className="divide-y divide-black/[0.04] max-h-[580px] overflow-y-auto">
              {filteredSessions.length === 0 && (
                <div className="px-6 py-12 text-xs text-zinc-400 text-center space-y-2">
                  <Activity className="w-6 h-6 mx-auto opacity-30" />
                  <p>No agent sessions matching filter.</p>
                  <Link
                    to="/buyer"
                    className="inline-block text-xs font-semibold text-zinc-900 underline mt-2"
                  >
                    Launch Buyer Agent →
                  </Link>
                </div>
              )}
              {filteredSessions.map((s: any) => {
                const isSelected = selected === s.session_id
                return (
                  <button
                    key={s.session_id}
                    onClick={() => setSelected(s.session_id)}
                    className={clsx(
                      'w-full text-left px-4 py-3.5 transition-all flex flex-col gap-1 border-l-4',
                      isSelected
                        ? 'bg-zinc-900 text-white border-blue-500 shadow-sm'
                        : 'hover:bg-zinc-50/80 text-zinc-900 border-transparent'
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <span className={clsx('text-[11px] font-mono', isSelected ? 'text-zinc-400' : 'text-zinc-500')}>
                        {s.session_id.slice(0, 14)}...
                      </span>
                      <Badge
                        variant={s.status === 'SUCCESS' ? 'emerald' : s.status === 'ACTIVE' ? 'amber' : 'rose'}
                        size="sm"
                      >
                        {s.status}
                      </Badge>
                    </div>
                    <div className={clsx('text-xs font-semibold truncate', isSelected ? 'text-white' : 'text-zinc-800')}>
                      {s.purchase_intent || 'No intent provided'}
                    </div>
                    <div className="flex items-center justify-between text-[11px] pt-1">
                      <span className={isSelected ? 'text-zinc-400' : 'text-zinc-500'}>
                        {s.amount_inr ? `₹${Number(s.amount_inr).toLocaleString('en-IN')}` : '—'}
                      </span>
                      <span className={isSelected ? 'text-zinc-400 font-mono' : 'text-zinc-400 font-mono'}>
                        {s.total_session_ms ? `${s.total_session_ms}ms` : ''}
                      </span>
                    </div>
                  </button>
                )
              })}
            </div>
          </GlassCard>
        </div>

        {/* Audit trail detail */}
        <div>
          {loading && (
            <GlassCard variant="subtle" padding="lg" className="flex items-center justify-center h-80">
              <div className="flex flex-col items-center gap-3">
                <div className="w-6 h-6 border-2 border-zinc-900 border-t-transparent rounded-full animate-spin" />
                <span className="text-xs text-zinc-500">Loading audit trail entries…</span>
              </div>
            </GlassCard>
          )}

          {!loading && !trail && (
            <GlassCard variant="subtle" padding="lg" className="flex flex-col items-center justify-center h-80 text-center text-zinc-400">
              <Bot className="w-10 h-10 mb-3 opacity-30" />
              <p className="text-sm font-medium">Select a session on the left to inspect step trace</p>
            </GlassCard>
          )}

          {trail && !loading && (
            <div className="space-y-6 animate-fade-in">
              {/* Session Overview Card */}
              <GlassCard variant="default" padding="lg" className="space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                  <div>
                    <h2 className="font-bold text-lg text-zinc-900">{trail.purchase_intent}</h2>
                    <p className="text-xs text-zinc-500 mt-0.5">
                      Store: <strong className="text-zinc-800">{trail.merchant_name}</strong> · Session ID: <span className="font-mono">{trail.session_id}</span>
                    </p>
                  </div>
                  {trail.outcome && (
                    <Badge
                      variant={trail.outcome.status === 'SUCCESS' ? 'emerald' : trail.outcome.status === 'FAILED' ? 'rose' : 'neutral'}
                      size="md"
                    >
                      {trail.outcome.status}
                    </Badge>
                  )}
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-3 border-t border-black/[0.06]">
                  <div className="bg-zinc-50/80 rounded-xl p-3 border border-black/[0.04]">
                    <span className="text-[11px] text-zinc-400 uppercase tracking-wider block">Total Amount</span>
                    <strong className="text-sm font-semibold text-zinc-900">
                      {trail.outcome?.amount_inr ? `₹${Number(trail.outcome.amount_inr).toLocaleString('en-IN')}` : '—'}
                    </strong>
                  </div>
                  <div className="bg-zinc-50/80 rounded-xl p-3 border border-black/[0.04]">
                    <span className="text-[11px] text-zinc-400 uppercase tracking-wider block">AI Provider</span>
                    <strong className="text-sm font-semibold text-zinc-900 truncate block">
                      {trail.outcome?.ai_provider_used || 'Hybrid Cascade'}
                    </strong>
                  </div>
                  <div className="bg-zinc-50/80 rounded-xl p-3 border border-black/[0.04]">
                    <span className="text-[11px] text-zinc-400 uppercase tracking-wider block">Latency</span>
                    <strong className="text-sm font-semibold text-zinc-900">
                      {trail.outcome?.total_session_ms ? `${(trail.outcome.total_session_ms / 1000).toFixed(2)}s` : '—'}
                    </strong>
                  </div>
                  <div className="bg-zinc-50/80 rounded-xl p-3 border border-black/[0.04]">
                    <span className="text-[11px] text-zinc-400 uppercase tracking-wider block">Payment ID</span>
                    <strong className="text-xs font-mono font-semibold text-zinc-900 truncate block">
                      {trail.outcome?.payment_id || '—'}
                    </strong>
                  </div>
                </div>
              </GlassCard>

              {/* Timeline of Steps */}
              <div className="space-y-4">
                <h3 className="font-bold text-sm text-zinc-800 uppercase tracking-wider px-1">
                  Chronological Step Trace ({trail.entries?.length || 0} Events)
                </h3>

                <div className="relative pl-6 space-y-4 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-zinc-200">
                  {trail.entries?.map((e: any, i: number) => {
                    const stepMeta = STEP_COLORS[e.step] || { variant: 'neutral', label: e.step }
                    const isGate = e.step === 'confirmation_gate'
                    const isPaymentSuccess = e.step === 'payment_confirmed'
                    const isPaymentFail = e.step === 'payment_failed'

                    return (
                      <div key={i} className="relative animate-fade-in">
                        {/* Timeline Node Icon */}
                        <div className={clsx(
                          'absolute -left-6 top-3 w-4 h-4 rounded-full border-2 flex items-center justify-center shadow-sm',
                          isPaymentSuccess ? 'bg-emerald-500 border-emerald-200' :
                          isGate ? 'bg-amber-500 border-amber-200' :
                          isPaymentFail ? 'bg-rose-500 border-rose-200' :
                          'bg-white border-zinc-400'
                        )}>
                          <div className={clsx(
                            'w-1.5 h-1.5 rounded-full',
                            isPaymentSuccess || isGate || isPaymentFail ? 'bg-white' : 'bg-zinc-600'
                          )} />
                        </div>

                        <GlassCard
                          variant={isGate ? 'glow' : isPaymentSuccess ? 'default' : 'subtle'}
                          padding="md"
                          className={clsx(
                            'transition-all',
                            isGate && 'border-amber-300 bg-amber-50/30'
                          )}
                        >
                          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
                            <div className="flex items-center gap-2">
                              <Badge variant={stepMeta.variant} size="sm">
                                {stepMeta.label}
                              </Badge>
                              <span className="font-mono text-[11px] text-zinc-400">Step #{i + 1}</span>
                            </div>

                            <div className="flex items-center gap-2 text-[11px] text-zinc-500">
                              {e.model_used && (
                                <span className="bg-black/[0.04] px-2 py-0.5 rounded-md font-mono text-zinc-700">
                                  {e.model_used}
                                </span>
                              )}
                              {e.latency_ms && (
                                <span className="flex items-center gap-1 font-mono">
                                  <Clock className="w-3 h-3 text-zinc-400" />
                                  {e.latency_ms}ms
                                </span>
                              )}
                              {e.confidence !== null && e.confidence !== undefined && (
                                <span className="text-zinc-600 font-semibold">
                                  {Math.round(e.confidence * 100)}% conf
                                </span>
                              )}
                            </div>
                          </div>

                          {e.reasoning && (
                            <p className="text-xs text-zinc-700 font-medium leading-relaxed mb-2">
                              {e.reasoning}
                            </p>
                          )}

                          {e.output_data && Object.keys(e.output_data).length > 0 && (
                            <div className="mt-2 text-[11px] font-mono text-zinc-600 bg-zinc-900/[0.03] border border-black/[0.04] rounded-xl p-3 overflow-x-auto">
                              <pre className="whitespace-pre-wrap break-all">
                                {JSON.stringify(e.output_data, null, 2)}
                              </pre>
                            </div>
                          )}

                          {e.error && (
                            <div className="flex items-start gap-2 text-xs text-rose-700 bg-rose-50 border border-rose-200/80 rounded-xl p-3 mt-2">
                              <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                              <span>{e.error}</span>
                            </div>
                          )}
                        </GlassCard>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
