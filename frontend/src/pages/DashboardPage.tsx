import { useState, useEffect, useCallback } from 'react'
import {
  listMerchants, getMerchant, listProducts, addProduct, updateProduct,
  deleteProduct, updatePermissions, getMerchantStatus, getCatalogVersions,
  searchCatalog, AgentPermissions, Product, Merchant,
} from '../lib/api'
import {
  LayoutDashboard, Plus, Trash2, Edit3, Save, X, RefreshCw, Zap,
  ChevronLeft, ChevronRight, Shield, History, Package, Sparkles, CheckCircle2, ShoppingBag,
  Layers, ArrowUpRight, Search, Check
} from 'lucide-react'
import clsx from 'clsx'
import { GlassCard } from '../components/ui/GlassCard'
import { MetricCard } from '../components/ui/MetricCard'
import { Badge } from '../components/ui/Badge'
import { StatusIndicator } from '../components/ui/StatusIndicator'
import { CodePill } from '../components/ui/CodePill'

// ── Types ─────────────────────────────────────────────────────────────────────

interface ProductsPage {
  total: number
  page: number
  page_size: number
  products: Product[]
}

interface MerchantStatus {
  merchant_id: string
  status: string
  product_count: number
  embedded_products: number
  embedding_progress: number
  updated_at: string
}

interface EditingProduct {
  product_id: string
  field: 'price_inr' | 'stock_count' | 'availability' | 'description'
  value: string | number | boolean
}

// ── Sub-components ────────────────────────────────────────────────────────────

function MerchantStatusBadge({ status }: { status: string }) {
  if (status === 'PUBLISHED') {
    return <Badge variant="emerald" size="sm">Published</Badge>
  }
  if (status === 'PUBLISHING') {
    return <Badge variant="amber" size="sm" pulse>Indexing Vectors</Badge>
  }
  if (status === 'ARCHIVED') {
    return <Badge variant="rose" size="sm">Archived</Badge>
  }
  return <Badge variant="neutral" size="sm">{status}</Badge>
}

function ProgressBar({ pct }: { pct: number }) {
  return (
    <div className="w-full bg-black/5 rounded-full h-2 overflow-hidden">
      <div
        className="bg-gradient-to-r from-amber-500 to-emerald-500 h-2 rounded-full transition-all duration-500"
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

// ── Add Product Slide-Over ─────────────────────────────────────────────────────

function AddProductSlideOver({
  merchantId,
  onClose,
  onAdded,
}: {
  merchantId: string
  onClose: () => void
  onAdded: () => void
}) {
  const [form, setForm] = useState({ name: '', price_inr: '', description: '', stock_count: '0', category: 'Clothing' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await addProduct(merchantId, {
        ...form,
        price_inr: parseFloat(form.price_inr),
        stock_count: parseInt(form.stock_count),
      })
      onAdded()
      onClose()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="flex-1 bg-black/40 backdrop-blur-sm transition-opacity" onClick={onClose} />
      <div className="w-full max-w-md bg-white shadow-2xl flex flex-col animate-[slideInRight_0.2s_ease] border-l border-black/10">
        <div className="p-6 border-b border-black/[0.08] flex items-center justify-between bg-zinc-50/70">
          <div>
            <h3 className="font-semibold text-base text-zinc-900">Add New Product</h3>
            <p className="text-xs text-zinc-500 mt-0.5">Direct manual entry to merchant vector catalog</p>
          </div>
          <button onClick={onClose} className="w-8 h-8 rounded-full hover:bg-black/5 flex items-center justify-center text-zinc-400 hover:text-zinc-700 transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-4">
          <div>
            <label className="block text-xs font-semibold text-zinc-700 mb-1.5">Product Name *</label>
            <input
              required
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              className="w-full border border-black/10 rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-black/10 transition-all"
              placeholder="e.g. Handcrafted Brass Diya Set"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-zinc-700 mb-1.5">Price (₹) *</label>
              <input
                required
                type="number"
                min="1"
                step="0.01"
                value={form.price_inr}
                onChange={e => setForm(f => ({ ...f, price_inr: e.target.value }))}
                className="w-full border border-black/10 rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-black/10 transition-all"
                placeholder="499.00"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-zinc-700 mb-1.5">Initial Stock</label>
              <input
                type="number"
                min="0"
                value={form.stock_count}
                onChange={e => setForm(f => ({ ...f, stock_count: e.target.value }))}
                className="w-full border border-black/10 rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-black/10 transition-all"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-semibold text-zinc-700 mb-1.5">Category</label>
            <select
              value={form.category}
              onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
              className="w-full border border-black/10 rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-black/10 transition-all bg-white"
            >
              {['Clothing', 'Accessories', 'Home Decor', 'Handicrafts', 'Textiles', 'Jewelry', 'Art & Craft', 'Other'].map(c => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-zinc-700 mb-1.5">Product Description</label>
            <textarea
              rows={4}
              value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              className="w-full border border-black/10 rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-black/10 transition-all resize-none"
              placeholder="Detailed description used by AI buyer agents for semantic similarity matching..."
            />
          </div>
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-600">
              {error}
            </div>
          )}
        </form>
        <div className="p-6 border-t border-black/[0.08] bg-zinc-50/50">
          <button
            onClick={handleSubmit as any}
            disabled={loading}
            className="w-full bg-zinc-900 text-white rounded-full py-3 text-sm font-semibold hover:bg-black disabled:opacity-50 transition-all shadow-sm"
          >
            {loading ? 'Adding & Indexing...' : 'Save & Publish Product'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Permission Editor ─────────────────────────────────────────────────────────

function PermissionEditor({
  merchantId,
  initialPermissions,
  onSaved,
}: {
  merchantId: string
  initialPermissions?: AgentPermissions
  onSaved: () => void
}) {
  const defaultPerms: AgentPermissions = {
    max_transaction_inr: 10000,
    requires_confirmation_above_inr: 0,
    auto_approve_below_inr: 0,
    excluded_product_ids: [],
  }
  const [perms, setPerms] = useState<AgentPermissions>(initialPermissions || defaultPerms)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (initialPermissions) {
      setPerms(initialPermissions)
    }
  }, [initialPermissions])

  const handleSave = async () => {
    setSaving(true)
    try {
      await updatePermissions(merchantId, perms)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      onSaved()
    } finally {
      setSaving(false)
    }
  }

  return (
    <GlassCard variant="default" padding="lg" className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-black/[0.04] border border-black/[0.06] flex items-center justify-center">
            <Shield className="w-4 h-4 text-zinc-800" />
          </div>
          <div>
            <h3 className="font-semibold text-sm text-zinc-900">Agent Guardrails & Spending Boundaries</h3>
            <p className="text-xs text-zinc-500">Autonomous limits enforced before any AI agent checkout</p>
          </div>
        </div>
        <Badge variant="emerald" size="sm">Active Enforcement</Badge>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
        <div className="bg-zinc-50/70 border border-black/[0.05] rounded-xl p-3.5">
          <label className="block text-xs font-semibold text-zinc-700 mb-1.5">Max Single Transaction Limit (₹)</label>
          <input
            type="number"
            value={perms?.max_transaction_inr ?? 10000}
            onChange={e => setPerms(p => ({ ...p, max_transaction_inr: parseFloat(e.target.value) || 0 }))}
            className="w-full bg-white border border-black/10 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black/10 font-medium"
          />
          <p className="text-[11px] text-zinc-400 mt-1">Transactions exceeding this limit are hard-blocked by the agent runtime.</p>
        </div>
        <div className="bg-zinc-50/70 border border-black/[0.05] rounded-xl p-3.5">
          <label className="block text-xs font-semibold text-zinc-700 mb-1.5">Mandatory Human Confirmation Above (₹)</label>
          <input
            type="number"
            value={perms?.requires_confirmation_above_inr ?? 0}
            onChange={e => setPerms(p => ({ ...p, requires_confirmation_above_inr: parseFloat(e.target.value) || 0 }))}
            className="w-full bg-white border border-black/10 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black/10 font-medium"
          />
          <p className="text-[11px] text-zinc-400 mt-1">Set to 0 to require non-bypassable confirmation for every transaction.</p>
        </div>
      </div>

      <div className="flex items-center justify-between pt-2 border-t border-black/[0.06]">
        <div className="flex items-center gap-2 text-xs text-amber-700 bg-amber-50/80 border border-amber-200/60 rounded-lg px-3 py-1.5">
          <Shield className="w-3.5 h-3.5 shrink-0" />
          <span>Confirmation gate is strictly non-bypassable under all Buildathon test tracks.</span>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="bg-zinc-900 text-white rounded-full px-5 py-2 text-xs font-semibold hover:bg-black disabled:opacity-50 transition-all shadow-sm flex items-center gap-1.5"
        >
          {saving ? 'Saving...' : saved ? '✓ Saved Successfully' : 'Save Boundaries'}
        </button>
      </div>
    </GlassCard>
  )
}

// ── Main Dashboard Page ───────────────────────────────────────────────────────

export default function DashboardPage() {
  const [merchants, setMerchants] = useState<Merchant[]>([])
  const [selectedMerchant, setSelectedMerchant] = useState<Merchant | null>(null)
  const [status, setStatus] = useState<MerchantStatus | null>(null)
  const [productsPage, setProductsPage] = useState<ProductsPage | null>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [editing, setEditing] = useState<EditingProduct | null>(null)
  const [showAddProduct, setShowAddProduct] = useState(false)
  const [loading, setLoading] = useState(false)
  const [versions, setVersions] = useState<any>(null)
  const [showVersions, setShowVersions] = useState(false)
  const [activeSection, setActiveSection] = useState<'inventory' | 'guardrails' | 'vectors' | 'history'>('inventory')
  const [vectorSearchQuery, setVectorSearchQuery] = useState('')
  const [vectorSearchResults, setVectorSearchResults] = useState<any[] | null>(null)
  const [vectorSearching, setVectorSearching] = useState(false)

  // Poll status while PUBLISHING
  useEffect(() => {
    if (!selectedMerchant || status?.status !== 'PUBLISHING') return
    const interval = setInterval(async () => {
      const s = await getMerchantStatus(selectedMerchant.merchant_id)
      setStatus(s)
      if (s.status === 'PUBLISHED') {
        loadProducts(selectedMerchant.merchant_id, 1)
      }
    }, 3000)
    return () => clearInterval(interval)
  }, [selectedMerchant, status?.status])

  useEffect(() => {
    listMerchants().then(ms => {
      const safe = Array.isArray(ms) ? ms : []
      setMerchants(safe)
      if (safe.length > 0 && !selectedMerchant) {
        selectMerchant(safe[0])
      }
    }).catch(() => {
      setMerchants([])
    })
  }, [])

  const selectMerchant = async (m: Merchant) => {
    if (!m) return
    setSelectedMerchant(m)
    setCurrentPage(1)
    setVersions(null)
    setShowVersions(false)
    setLoading(true)
    try {
      const [fullMerchant, s, p] = await Promise.all([
        getMerchant(m.merchant_id).catch(() => m),
        getMerchantStatus(m.merchant_id).catch(() => null),
        listProducts(m.merchant_id, 1, 20).catch(() => ({ total: 0, page: 1, page_size: 20, products: [] })),
      ])
      if (fullMerchant) {
        setSelectedMerchant(fullMerchant)
      }
      setStatus(s)
      setProductsPage(p || { total: 0, page: 1, page_size: 20, products: [] })
    } finally {
      setLoading(false)
    }
  }

  const loadProducts = useCallback(async (merchantId: string, page: number) => {
    try {
      const p = await listProducts(merchantId, page, 20)
      setProductsPage(p || { total: 0, page: 1, page_size: 20, products: [] })
      setCurrentPage(page)
    } catch {
      setProductsPage({ total: 0, page: 1, page_size: 20, products: [] })
    }
  }, [])

  const handleDelete = async (productId: string) => {
    if (!selectedMerchant) return
    if (!confirm('Delete this product? This will remove it from the vector catalog.')) return
    await deleteProduct(selectedMerchant.merchant_id, productId)
    loadProducts(selectedMerchant.merchant_id, currentPage)
  }

  const handleSaveEdit = async () => {
    if (!editing || !selectedMerchant) return
    await updateProduct(selectedMerchant.merchant_id, editing.product_id, {
      [editing.field]: editing.value,
    })
    setEditing(null)
    loadProducts(selectedMerchant.merchant_id, currentPage)
  }

  const handleToggleAvailability = async (p: Product) => {
    if (!selectedMerchant) return
    await updateProduct(selectedMerchant.merchant_id, p.product_id, {
      availability: !p.availability,
    })
    loadProducts(selectedMerchant.merchant_id, currentPage)
  }

  const loadVersions = async () => {
    if (!selectedMerchant) return
    const v = await getCatalogVersions(selectedMerchant.merchant_id)
    setVersions(v)
    setShowVersions(true)
  }

  const handleVectorSearch = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedMerchant || !vectorSearchQuery.trim()) return
    setVectorSearching(true)
    try {
      const res = await searchCatalog(selectedMerchant.merchant_id, vectorSearchQuery.trim(), 5)
      setVectorSearchResults(res.results || [])
    } catch (err) {
      console.error('Vector search failed', err)
    } finally {
      setVectorSearching(false)
    }
  }

  const totalPages = productsPage ? Math.ceil(productsPage.total / productsPage.page_size) : 1

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-black/[0.06]">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-zinc-900 text-white rounded-2xl flex items-center justify-center shadow-sm">
            <LayoutDashboard className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-bold text-xl text-zinc-900 tracking-tight">Merchant Catalog Dashboard</h1>
              <Badge variant="emerald" size="sm">Live Vector Store</Badge>
            </div>
            <p className="text-xs text-zinc-500">Manage published inventories, inspect AI embeddings, and tune agent guardrails</p>
          </div>
        </div>

        {selectedMerchant && (
          <div className="flex items-center gap-2">
            <CodePill label="API Endpoint" code={`/api/catalog/${selectedMerchant.merchant_id}`} copyable />
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[290px_1fr] gap-6 min-h-[600px]">
        {/* Merchant list sidebar */}
        <div className="space-y-3">
          <div className="flex items-center justify-between px-1">
            <span className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
              Onboarded Stores ({merchants.length})
            </span>
            <a
              href="/merchant"
              className="text-xs text-zinc-800 hover:text-black font-semibold flex items-center gap-1 hover:underline"
            >
              <Plus className="w-3 h-3" /> New
            </a>
          </div>

          {merchants.length === 0 && (
            <GlassCard variant="subtle" padding="lg" className="text-center py-10 text-zinc-400 text-sm">
              <Package className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p>No merchants onboarded yet.</p>
              <a href="/merchant" className="text-zinc-900 font-semibold underline text-xs mt-2 inline-block">
                Onboard your first store →
              </a>
            </GlassCard>
          )}

          <div className="space-y-2">
            {merchants.map(m => {
              const isSelected = selectedMerchant?.merchant_id === m.merchant_id
              return (
                <button
                  key={m.merchant_id}
                  onClick={() => selectMerchant(m)}
                  className={`w-full text-left rounded-2xl p-4 transition-all border ${
                    isSelected
                      ? 'bg-zinc-900 text-white border-zinc-900 shadow-md ring-2 ring-zinc-900/20 scale-[1.01]'
                      : 'bg-white/80 hover:bg-white border-black/[0.06] hover:border-black/20 text-zinc-900'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className={`text-sm font-semibold truncate ${isSelected ? 'text-white' : 'text-zinc-900'}`}>
                      {m.merchant_name}
                    </p>
                    <div className="flex items-center gap-1.5">
                      {isSelected && (
                        <span className="text-[9px] font-bold uppercase tracking-wider bg-emerald-500/20 text-emerald-300 px-1.5 py-0.5 rounded-md border border-emerald-500/30">
                          Active
                        </span>
                      )}
                      <StatusIndicator
                        status={m.status === 'PUBLISHED' ? 'online' : m.status === 'PUBLISHING' ? 'busy' : 'offline'}
                        pulse={m.status === 'PUBLISHING'}
                      />
                    </div>
                  </div>
                  <div className={`flex items-center justify-between mt-2 pt-2 border-t text-xs ${
                    isSelected ? 'border-white/10 text-zinc-400' : 'border-black/[0.04] text-zinc-500'
                  }`}>
                    <span>{m.product_count} products</span>
                    <span className="font-mono text-[10px]">{m.merchant_id.slice(0, 10)}...</span>
                  </div>
                </button>
              )
            })}
          </div>
        </div>

        {/* Main content */}
        <div className="space-y-6">
          {!selectedMerchant ? (
            <GlassCard variant="subtle" padding="lg" className="flex flex-col items-center justify-center h-96 text-zinc-400">
              <Package className="w-10 h-10 mb-3 opacity-30" />
              <p className="text-sm font-medium">Select a merchant from the left to inspect catalog</p>
            </GlassCard>
          ) : (
            <>
              {/* Status & Stats cards */}
              {status && (
                <div className="space-y-4">
                  {/* Top info card */}
                  <GlassCard variant="default" padding="md" className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-2xl bg-zinc-100 flex items-center justify-center font-bold text-zinc-800">
                        {selectedMerchant.merchant_name.charAt(0)}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h2 className="font-bold text-base text-zinc-900">{selectedMerchant.merchant_name}</h2>
                          <MerchantStatusBadge status={status.status} />
                        </div>
                        <p className="text-xs font-mono text-zinc-400 mt-0.5">{selectedMerchant.merchant_id}</p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={loadVersions}
                        className="flex items-center gap-1.5 text-xs text-zinc-700 hover:text-black bg-zinc-100/80 hover:bg-zinc-200/80 rounded-xl px-3 py-1.5 transition-colors font-medium"
                      >
                        <History className="w-3.5 h-3.5" /> Version History
                      </button>
                    </div>
                  </GlassCard>

                  {/* Publishing progress */}
                  {status.status === 'PUBLISHING' && (
                    <GlassCard variant="glow" padding="md" className="space-y-2">
                      <div className="flex items-center justify-between text-xs text-zinc-600 font-medium">
                        <span className="flex items-center gap-1.5">
                          <Sparkles className="w-3.5 h-3.5 text-amber-500 animate-spin" />
                          Generating all-MiniLM-L6-v2 vector embeddings...
                        </span>
                        <span>{status.embedded_products} of {status.product_count} products ({status.embedding_progress}%)</span>
                      </div>
                      <ProgressBar pct={status.embedding_progress} />
                    </GlassCard>
                  )}

                  {/* 3 Metric Cards */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <MetricCard
                      label="Catalog Size"
                      value={status.product_count}
                      subtext="Total items registered"
                      icon={ShoppingBag}
                      variant="default"
                    />
                    <MetricCard
                      label="Vector Embeddings"
                      value={status.embedded_products}
                      subtext="Dense search indices"
                      icon={Sparkles}
                      variant="indigo"
                    />
                    <MetricCard
                      label="Agent Discovery"
                      value={`${status.embedding_progress}%`}
                      subtext="Ready for AI Buyer Agents"
                      icon={CheckCircle2}
                      variant="emerald"
                    />
                  </div>
                </div>
              )}

              {/* Section Tabs Switcher */}
              <div className="flex items-center gap-2 p-1.5 rounded-2xl bg-zinc-100/90 border border-black/[0.06] shadow-inner overflow-x-auto">
                {[
                  { id: 'inventory', label: 'Product Inventory', icon: Package, badge: productsPage?.total },
                  { id: 'guardrails', label: 'Agent Guardrails & Limits', icon: Shield, badge: 'Enforced' },
                  { id: 'vectors', label: 'Vector Engine & Semantic Search', icon: Sparkles, badge: `${status?.embedding_progress ?? 100}%` },
                  { id: 'history', label: 'Version History', icon: History, badge: versions?.versions?.length },
                ].map(tab => {
                  const isActive = activeSection === tab.id
                  const Icon = tab.icon
                  return (
                    <button
                      key={tab.id}
                      onClick={() => {
                        setActiveSection(tab.id as any)
                        if (tab.id === 'history' && !versions) loadVersions()
                      }}
                      className={clsx(
                        'relative flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold transition-all select-none whitespace-nowrap',
                        isActive
                          ? 'bg-zinc-900 text-white shadow-md ring-2 ring-black/10 scale-[1.01]'
                          : 'text-zinc-600 hover:text-zinc-950 hover:bg-white/60'
                      )}
                    >
                      {isActive && (
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shrink-0" />
                      )}
                      <Icon className={clsx('w-3.5 h-3.5', isActive ? 'text-white' : 'text-zinc-500')} />
                      <span>{tab.label}</span>
                      {tab.badge !== undefined && (
                        <span className={clsx(
                          'ml-1 px-1.5 py-0.5 rounded-full text-[10px] font-mono',
                          isActive ? 'bg-white/20 text-white' : 'bg-black/[0.06] text-zinc-600'
                        )}>
                          {tab.badge}
                        </span>
                      )}
                    </button>
                  )
                })}
              </div>

              {/* Tab 1: Products Inventory */}
              {activeSection === 'inventory' && (
                <GlassCard variant="default" padding="none" className="overflow-hidden animate-fade-in">
                  <div className="flex items-center justify-between px-6 py-4 border-b border-black/[0.06] bg-zinc-50/50">
                    <div>
                      <h3 className="font-semibold text-sm text-zinc-900">
                        Product Inventory
                      </h3>
                      <p className="text-xs text-zinc-500 mt-0.5">
                        {productsPage ? `${productsPage.total} products registered in store` : 'Loading inventory...'}
                      </p>
                    </div>
                    <button
                      onClick={() => setShowAddProduct(true)}
                      className="flex items-center gap-1.5 bg-zinc-900 text-white rounded-full px-4 py-2 text-xs font-semibold hover:bg-black transition-all shadow-sm"
                    >
                      <Plus className="w-3.5 h-3.5" /> Add Product
                    </button>
                  </div>

                  {loading ? (
                    <div className="p-12 text-center text-zinc-400 text-sm">Loading products catalog…</div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-black/[0.06] bg-zinc-50/70 text-[11px] text-zinc-500 font-semibold uppercase tracking-wider">
                            <th className="text-left px-6 py-3.5">Product</th>
                            <th className="text-left px-4 py-3.5">Category</th>
                            <th className="text-right px-4 py-3.5">Price (₹)</th>
                            <th className="text-right px-4 py-3.5">Stock</th>
                            <th className="text-center px-4 py-3.5">Status</th>
                            <th className="text-right px-6 py-3.5">Actions</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-black/[0.04]">
                          {productsPage?.products.map(p => (
                            <tr key={p.product_id} className="hover:bg-zinc-50/80 transition-colors">
                              <td className="px-6 py-3.5">
                                <div>
                                  <p className="font-semibold text-zinc-900 truncate max-w-[220px]">{p.name}</p>
                                  <p className="text-xs text-zinc-500 truncate max-w-[220px] mt-0.5">{p.description}</p>
                                </div>
                              </td>
                              <td className="px-4 py-3.5">
                                <Badge variant="neutral" size="sm">{p.category || 'General'}</Badge>
                              </td>

                              {/* Inline price edit */}
                              <td className="px-4 py-3.5 text-right">
                                {editing?.product_id === p.product_id && editing.field === 'price_inr' ? (
                                  <div className="flex items-center justify-end gap-1">
                                    <input
                                      type="number"
                                      autoFocus
                                      value={editing.value as number}
                                      onChange={e => setEditing(ed => ed ? { ...ed, value: parseFloat(e.target.value) } : null)}
                                      className="w-24 text-right border border-zinc-400 rounded-lg px-2 py-1 text-xs font-semibold focus:outline-none focus:ring-1 focus:ring-black"
                                    />
                                    <button onClick={handleSaveEdit} className="p-1 hover:bg-black/5 rounded"><Save className="w-3.5 h-3.5 text-emerald-600" /></button>
                                    <button onClick={() => setEditing(null)} className="p-1 hover:bg-black/5 rounded"><X className="w-3.5 h-3.5 text-zinc-400" /></button>
                                  </div>
                                ) : (
                                  <button
                                    className="inline-flex items-center gap-1.5 font-semibold text-zinc-900 hover:text-black group ml-auto"
                                    onClick={() => setEditing({ product_id: p.product_id, field: 'price_inr', value: p.price_inr })}
                                    title="Click to edit price"
                                  >
                                    ₹{p.price_inr.toLocaleString('en-IN')}
                                    <Edit3 className="w-3 h-3 opacity-0 group-hover:opacity-60 transition-opacity" />
                                  </button>
                                )}
                              </td>

                              {/* Inline stock edit */}
                              <td className="px-4 py-3.5 text-right">
                                {editing?.product_id === p.product_id && editing.field === 'stock_count' ? (
                                  <div className="flex items-center justify-end gap-1">
                                    <input
                                      type="number"
                                      autoFocus
                                      min="0"
                                      value={editing.value as number}
                                      onChange={e => setEditing(ed => ed ? { ...ed, value: parseInt(e.target.value) } : null)}
                                      className="w-20 text-right border border-zinc-400 rounded-lg px-2 py-1 text-xs font-semibold focus:outline-none focus:ring-1 focus:ring-black"
                                    />
                                    <button onClick={handleSaveEdit} className="p-1 hover:bg-black/5 rounded"><Save className="w-3.5 h-3.5 text-emerald-600" /></button>
                                    <button onClick={() => setEditing(null)} className="p-1 hover:bg-black/5 rounded"><X className="w-3.5 h-3.5 text-zinc-400" /></button>
                                  </div>
                                ) : (
                                  <button
                                    className="inline-flex items-center gap-1.5 text-zinc-700 hover:text-black group ml-auto"
                                    onClick={() => setEditing({ product_id: p.product_id, field: 'stock_count', value: p.stock_count })}
                                    title="Click to edit stock"
                                  >
                                    <span className={p.stock_count === 0 ? 'text-red-500 font-semibold' : 'font-medium'}>
                                      {p.stock_count}
                                    </span>
                                    <Edit3 className="w-3 h-3 opacity-0 group-hover:opacity-60 transition-opacity" />
                                  </button>
                                )}
                              </td>

                              {/* Availability toggle */}
                              <td className="px-4 py-3.5 text-center">
                                <button
                                  onClick={() => handleToggleAvailability(p)}
                                  className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors ${p.availability ? 'bg-emerald-600' : 'bg-zinc-200'}`}
                                  title={p.availability ? 'Available for purchase' : 'Marked unavailable'}
                                >
                                  <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform shadow-sm ${p.availability ? 'translate-x-5' : 'translate-x-1'}`} />
                                </button>
                              </td>

                              <td className="px-6 py-3.5 text-right">
                                <button
                                  onClick={() => handleDelete(p.product_id)}
                                  className="text-zinc-300 hover:text-red-500 p-1 rounded-lg transition-colors"
                                  title="Delete product"
                                >
                                  <Trash2 className="w-4 h-4" />
                                </button>
                              </td>
                            </tr>
                          ))}
                          {productsPage?.products.length === 0 && (
                            <tr>
                              <td colSpan={6} className="px-6 py-10 text-center text-zinc-400 text-sm">
                                No products found in this merchant catalog.
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {/* Pagination */}
                  {totalPages > 1 && (
                    <div className="flex items-center justify-between px-6 py-3.5 border-t border-black/[0.06] bg-zinc-50/40 text-xs text-zinc-500">
                      <span>Page {currentPage} of {totalPages}</span>
                      <div className="flex items-center gap-1.5">
                        <button
                          disabled={currentPage === 1}
                          onClick={() => loadProducts(selectedMerchant.merchant_id, currentPage - 1)}
                          className="p-1.5 rounded-lg border border-black/10 bg-white hover:bg-zinc-50 disabled:opacity-40 transition-colors"
                        >
                          <ChevronLeft className="w-4 h-4" />
                        </button>
                        <button
                          disabled={currentPage === totalPages}
                          onClick={() => loadProducts(selectedMerchant.merchant_id, currentPage + 1)}
                          className="p-1.5 rounded-lg border border-black/10 bg-white hover:bg-zinc-50 disabled:opacity-40 transition-colors"
                        >
                          <ChevronRight className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  )}
                </GlassCard>
              )}

              {/* Tab 2: Guardrails & Boundaries */}
              {activeSection === 'guardrails' && (
                <div className="animate-fade-in">
                  <PermissionEditor
                    merchantId={selectedMerchant.merchant_id}
                    initialPermissions={selectedMerchant.agent_permissions}
                    onSaved={() => listMerchants().then(setMerchants)}
                  />
                </div>
              )}

              {/* Tab 3: Vector Embeddings & Dense Search */}
              {activeSection === 'vectors' && (
                <div className="space-y-4 animate-fade-in">
                  <GlassCard variant="default" padding="lg" className="space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600">
                          <Sparkles className="w-5 h-5" />
                        </div>
                        <div>
                          <h3 className="font-semibold text-sm text-zinc-900">Dense Vector Search Engine</h3>
                          <p className="text-xs text-zinc-500">Model: all-MiniLM-L6-v2 · 384-dimensional cosine index</p>
                        </div>
                      </div>
                      <Badge variant="indigo" size="sm">Dense Semantic Index</Badge>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2">
                      <div className="p-3 bg-zinc-50/70 border border-black/[0.04] rounded-xl">
                        <span className="text-[11px] text-zinc-400 uppercase tracking-wider block">Dimensions</span>
                        <strong className="text-sm font-semibold text-zinc-900">384-dim Floats</strong>
                      </div>
                      <div className="p-3 bg-zinc-50/70 border border-black/[0.04] rounded-xl">
                        <span className="text-[11px] text-zinc-400 uppercase tracking-wider block">Search Metric</span>
                        <strong className="text-sm font-semibold text-zinc-900">Cosine Similarity</strong>
                      </div>
                      <div className="p-3 bg-zinc-50/70 border border-black/[0.04] rounded-xl">
                        <span className="text-[11px] text-zinc-400 uppercase tracking-wider block">Indexed Vectors</span>
                        <strong className="text-sm font-semibold text-zinc-900">{status?.embedded_products ?? 0} items</strong>
                      </div>
                    </div>

                    {/* Interactive Semantic Search Test */}
                    <div className="pt-4 border-t border-black/[0.06] space-y-3">
                      <label className="block text-xs font-semibold text-zinc-700">
                        Test Real-time Semantic Retrieval
                      </label>
                      <form onSubmit={handleVectorSearch} className="flex gap-2">
                        <div className="relative flex-1">
                          <Search className="w-4 h-4 text-zinc-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                          <input
                            type="text"
                            placeholder="e.g. 'pure cotton red outfit under 800' or 'brass handcrafted home item'"
                            value={vectorSearchQuery}
                            onChange={e => setVectorSearchQuery(e.target.value)}
                            className="w-full bg-white border border-black/10 rounded-xl pl-10 pr-4 py-2.5 text-xs focus:outline-none focus:ring-2 focus:ring-black/10"
                          />
                        </div>
                        <button
                          type="submit"
                          disabled={vectorSearching}
                          className="bg-zinc-900 text-white rounded-xl px-5 py-2 text-xs font-semibold hover:bg-black disabled:opacity-50 transition-all shadow-sm shrink-0"
                        >
                          {vectorSearching ? 'Searching...' : 'Test Vector Query'}
                        </button>
                      </form>

                      {vectorSearchResults && (
                        <div className="mt-3 space-y-2">
                          <span className="text-[11px] font-semibold text-zinc-500">
                            Retrieval Results ({vectorSearchResults.length} matches):
                          </span>
                          <div className="divide-y divide-black/[0.04] border border-black/[0.06] rounded-xl overflow-hidden bg-white">
                            {vectorSearchResults.map((r: any, idx: number) => (
                              <div key={idx} className="p-3 flex items-center justify-between gap-3 text-xs hover:bg-zinc-50">
                                <div>
                                  <p className="font-semibold text-zinc-900">{r.name}</p>
                                  <p className="text-[11px] text-zinc-500 line-clamp-1">{r.description}</p>
                                </div>
                                <div className="text-right shrink-0">
                                  <span className="font-semibold text-zinc-900 block">₹{r.price_inr}</span>
                                  {r.similarity_score !== undefined && (
                                    <span className="text-[10px] text-indigo-600 font-mono">
                                      score: {(r.similarity_score * 100).toFixed(1)}%
                                    </span>
                                  )}
                                </div>
                              </div>
                            ))}
                            {vectorSearchResults.length === 0 && (
                              <div className="p-4 text-center text-xs text-zinc-400">
                                No semantic matches found for this query.
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  </GlassCard>
                </div>
              )}

              {/* Tab 4: Version History */}
              {activeSection === 'history' && (
                <div className="space-y-4 animate-fade-in">
                  <GlassCard variant="default" padding="lg" className="space-y-4">
                    <div className="flex items-center justify-between border-b border-black/[0.06] pb-3">
                      <div className="flex items-center gap-2">
                        <History className="w-4 h-4 text-zinc-700" />
                        <h3 className="font-semibold text-sm text-zinc-900">Catalog Version History & Snapshots</h3>
                      </div>
                      <Badge variant="neutral" size="sm">Immutable Snapshots</Badge>
                    </div>
                    {versions?.note && <p className="text-xs text-zinc-500">{versions.note}</p>}
                    <div className="space-y-2">
                      {versions?.versions?.map((v: any, i: number) => (
                        <div key={i} className="flex items-center justify-between bg-zinc-50/80 rounded-xl px-4 py-3 border border-black/[0.04]">
                          <div className="flex items-center gap-2.5">
                            <span className="font-mono text-xs font-semibold bg-zinc-200 text-zinc-800 px-2 py-0.5 rounded-lg">
                              {v.version}
                            </span>
                            <MerchantStatusBadge status={v.status} />
                          </div>
                          <div className="text-right">
                            <p className="text-xs font-medium text-zinc-700">{v.product_count} products registered</p>
                            <p className="text-[11px] text-zinc-400">{new Date(v.updated_at).toLocaleString()}</p>
                          </div>
                        </div>
                      ))}
                      {(!versions || !versions.versions || versions.versions.length === 0) && (
                        <div className="p-8 text-center text-zinc-400 text-xs">
                          No version snapshots recorded yet.
                        </div>
                      )}
                    </div>
                  </GlassCard>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Add product slide-over */}
      {showAddProduct && selectedMerchant && (
        <AddProductSlideOver
          merchantId={selectedMerchant.merchant_id}
          onClose={() => setShowAddProduct(false)}
          onAdded={() => loadProducts(selectedMerchant.merchant_id, 1)}
        />
      )}
    </div>
  )
}
