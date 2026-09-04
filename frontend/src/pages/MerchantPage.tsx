import { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import {
  Upload, Link2, PenLine, Globe, CheckCircle2, AlertTriangle,
  XCircle, ChevronDown, ChevronUp, Copy, ArrowRight, Plus, Trash2,
  Store, Sparkles, ShieldCheck, Layers
} from 'lucide-react'
import toast from 'react-hot-toast'
import clsx from 'clsx'
import {
  onboardCSV, onboardSheets, onboardManual, onboardURL, publishCatalog,
  type OnboardResponse, type AgentPermissions
} from '../lib/api'
import { FluidTabs } from '../components/ui/FluidTabs'
import { GlassCard } from '../components/ui/GlassCard'
import { Badge } from '../components/ui/Badge'
import { CodePill } from '../components/ui/CodePill'

type Tab = 'csv' | 'sheets' | 'manual' | 'url'

const DEFAULT_PERMISSIONS: AgentPermissions = {
  max_transaction_inr: 10000,
  requires_confirmation_above_inr: 0,
  auto_approve_below_inr: 0,
  excluded_product_ids: [],
}

const ONBOARD_TABS = [
  { id: 'csv', label: 'Upload CSV', icon: Upload },
  { id: 'sheets', label: 'Google Sheets', icon: Link2 },
  { id: 'manual', label: 'Manual Entry', icon: PenLine },
  { id: 'url', label: 'Product URL', icon: Globe },
]

export default function MerchantPage() {
  const [tab, setTab] = useState<Tab>('csv')
  const [merchantName, setMerchantName] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<OnboardResponse | null>(null)
  const [published, setPublished] = useState(false)
  const [permissions, setPermissions] = useState<AgentPermissions>(DEFAULT_PERMISSIONS)
  const [showPermissions, setShowPermissions] = useState(false)
  const [showAllProducts, setShowAllProducts] = useState(false)

  // CSV
  const [csvFile, setCsvFile] = useState<File | null>(null)
  // Sheets
  const [sheetsUrl, setSheetsUrl] = useState('')
  // URL
  const [productUrl, setProductUrl] = useState('')
  // Manual
  const [manualProducts, setManualProducts] = useState([
    { name: '', price: '', description: '', stock: '', category: '' }
  ])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: { 'text/csv': ['.csv'] },
    maxFiles: 1,
    onDrop: files => { if (files[0]) setCsvFile(files[0]) }
  })

  const handleSubmit = async () => {
    if (!merchantName.trim()) { toast.error('Enter a merchant name'); return }
    setLoading(true)
    setResult(null)
    setPublished(false)
    try {
      let res: OnboardResponse
      if (tab === 'csv') {
        if (!csvFile) { toast.error('Upload a CSV file'); return }
        res = await onboardCSV(merchantName, csvFile)
      } else if (tab === 'sheets') {
        if (!sheetsUrl) { toast.error('Enter a Google Sheets URL'); return }
        res = await onboardSheets(merchantName, sheetsUrl)
      } else if (tab === 'url') {
        if (!productUrl) { toast.error('Enter a product page URL'); return }
        res = await onboardURL(merchantName, productUrl)
      } else {
        const valid = manualProducts.filter(p => p.name && p.price)
        if (!valid.length) { toast.error('Add at least one product with name and price'); return }
        res = await onboardManual(merchantName, valid.map(p => ({
          name: p.name, price: parseFloat(p.price), description: p.description,
          stock: parseInt(p.stock) || 0, category: p.category || 'Other'
        })))
      }
      setResult(res)
      if (res.validation.errors.length > 0) toast.error(`${res.validation.errors.length} validation errors — fix before publishing`)
      else if (res.validation.warnings.length > 0) toast(`${res.validation.warnings.length} warnings — review before publishing`, { icon: '⚠️' })
      else toast.success('Products parsed successfully!')
    } catch (e: any) {
      toast.error(e.message || 'Failed to process products')
    } finally {
      setLoading(false)
    }
  }

  const handlePublish = async () => {
    if (!result) return
    setLoading(true)
    try {
      await publishCatalog(result.merchant_id, permissions)
      setPublished(true)
      toast.success('Catalog published! Your store is now AI-ready.')
    } catch (e: any) {
      toast.error(e.message || 'Publish failed')
    } finally {
      setLoading(false)
    }
  }

  const addProduct = () => setManualProducts(p => [...p, { name: '', price: '', description: '', stock: '', category: '' }])
  const removeProduct = (i: number) => setManualProducts(p => p.filter((_, idx) => idx !== i))
  const updateProduct = (i: number, field: string, val: string) =>
    setManualProducts(p => p.map((item, idx) => idx === i ? { ...item, [field]: val } : item))

  const displayProducts = showAllProducts ? result?.preview : result?.preview.slice(0, 5)

  return (
    <div className="max-w-3xl mx-auto py-4">
      {/* Hero Header */}
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-2">
          <Badge variant="indigo" size="sm">
            Self-Service Onboarding
          </Badge>
          <Badge variant="outline" size="sm">
            Track 01: Agentic Commerce
          </Badge>
        </div>
        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-neutral-900 dark:text-white mb-2">
          Make your store AI-ready.
        </h1>
        <p className="text-neutral-500 text-sm sm:text-base leading-relaxed">
          Publish your product catalog to a high-speed semantic API endpoint queryable by autonomous buyer agents on Razorpay test mode.
        </p>
      </div>

      {!published ? (
        <GlassCard className="p-6 sm:p-8 space-y-6">
          {/* Merchant name */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-neutral-700 dark:text-neutral-300 mb-2">
              Merchant / Store Name
            </label>
            <input
              value={merchantName}
              onChange={e => setMerchantName(e.target.value)}
              placeholder="e.g. Kiran Artisan Goods"
              className="w-full border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-neutral-900 transition-colors shadow-2xs"
            />
          </div>

          {/* Fluid Tabs */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-neutral-700 dark:text-neutral-300 mb-2">
              Catalog Source
            </label>
            <FluidTabs
              tabs={ONBOARD_TABS}
              activeTab={tab}
              onChange={id => setTab(id as Tab)}
            />
          </div>

          {/* Tab content */}
          {tab === 'csv' && (
            <div
              {...getRootProps()}
              className={clsx('border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors',
                isDragActive ? 'border-black bg-gray-50' : csvFile ? 'border-green-400 bg-green-50' : 'border-gray-200 hover:border-gray-400')}
            >
              <input {...getInputProps()} />
              <Upload className={clsx('w-8 h-8 mx-auto mb-3', csvFile ? 'text-green-600' : 'text-gray-400')} />
              {csvFile ? (
                <div><p className="font-medium text-green-700">{csvFile.name}</p><p className="text-sm text-gray-500 mt-1">{(csvFile.size / 1024).toFixed(1)} KB</p></div>
              ) : (
                <div><p className="font-medium">Drop your CSV or click to browse</p><p className="text-sm text-gray-500 mt-1">Columns: name, price, description, stock, category</p></div>
              )}
            </div>
          )}

          {tab === 'sheets' && (
            <div className="space-y-3">
              <input value={sheetsUrl} onChange={e => setSheetsUrl(e.target.value)}
                placeholder="https://docs.google.com/spreadsheets/d/..."
                className="w-full border border-gray-200 rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-black"
              />
              <p className="text-xs text-gray-500">Share the sheet as "Anyone with the link can view" for public access.</p>
            </div>
          )}

          {tab === 'url' && (
            <div className="space-y-3">
              <input value={productUrl} onChange={e => setProductUrl(e.target.value)}
                placeholder="https://yourstore.com/products"
                className="w-full border border-gray-200 rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-black"
              />
              <p className="text-xs text-gray-500">Best-effort scraper. Works on static HTML pages. SPAs may have limited extraction.</p>
            </div>
          )}

          {tab === 'manual' && (
            <div className="space-y-3">
              {manualProducts.map((p, i) => (
                <div key={i} className="border border-gray-200 rounded-xl p-4 relative">
                  <div className="grid grid-cols-2 gap-3 mb-3">
                    <input value={p.name} onChange={e => updateProduct(i, 'name', e.target.value)}
                      placeholder="Product name *" className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-black" />
                    <input value={p.price} onChange={e => updateProduct(i, 'price', e.target.value)}
                      placeholder="Price (₹) *" type="number" className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-black" />
                  </div>
                  <div className="grid grid-cols-3 gap-3">
                    <input value={p.description} onChange={e => updateProduct(i, 'description', e.target.value)}
                      placeholder="Description" className="col-span-2 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-black" />
                    <input value={p.stock} onChange={e => updateProduct(i, 'stock', e.target.value)}
                      placeholder="Stock" type="number" className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-black" />
                  </div>
                  {manualProducts.length > 1 && (
                    <button onClick={() => removeProduct(i)} className="absolute top-3 right-3 text-gray-400 hover:text-red-500 transition-colors">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
              ))}
              <button onClick={addProduct} className="flex items-center gap-2 text-sm font-medium text-gray-600 hover:text-black transition-colors">
                <Plus className="w-4 h-4" /> Add product
              </button>
            </div>
          )}

          <button onClick={handleSubmit} disabled={loading}
            className={clsx('mt-6 w-full bg-black text-white font-medium py-3 rounded-full flex items-center justify-center gap-2 transition-all',
              loading ? 'opacity-70 cursor-not-allowed' : 'hover:bg-gray-900')}
          >
            {loading ? <><Spinner /> Processing...</> : <><ArrowRight className="w-4 h-4" /> Parse Products</>}
          </button>

          {/* Results */}
          {result && (
            <div className="mt-8 animate-slide-up">
              {/* Validation summary */}
              <div className="border border-gray-200 rounded-xl p-5 mb-6">
                <h3 className="font-semibold mb-4">Validation Results</h3>
                <div className="flex gap-6 mb-4">
                  <Stat value={result.validation.valid} label="Ready" color="text-green-600" />
                  <Stat value={result.validation.invalid} label="Errors" color="text-red-500" />
                  <Stat value={result.validation.warnings.length} label="Warnings" color="text-amber-500" />
                </div>
                {result.validation.errors.map((e, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm text-red-600 py-2 border-t border-red-50">
                    <XCircle className="w-4 h-4 mt-0.5 shrink-0" />
                    <span>{e.message}</span>
                  </div>
                ))}
                {result.validation.warnings.map((w, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm text-amber-600 py-2 border-t border-amber-50">
                    <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                    <span>{w.message}</span>
                  </div>
                ))}
              </div>

              {/* Product preview */}
              {result.preview.length > 0 && (
                <div className="mb-6">
                  <h3 className="font-semibold mb-3">Product Preview</h3>
                  <div className="border border-gray-200 rounded-xl overflow-hidden">
                    <table className="w-full text-sm">
                      <thead><tr className="bg-gray-50 border-b border-gray-200">
                        <th className="text-left px-4 py-3 font-medium text-gray-600">Name</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-600">Price</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-600">Category</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-600">Stock</th>
                      </tr></thead>
                      <tbody>
                        {displayProducts?.map((p, i) => (
                          <tr key={i} className="border-b border-gray-100 last:border-0">
                            <td className="px-4 py-3 font-medium">{p.name}</td>
                            <td className="px-4 py-3 text-gray-700">₹{p.price_inr.toLocaleString()}</td>
                            <td className="px-4 py-3"><span className="bg-gray-100 text-gray-700 px-2 py-0.5 rounded-full text-xs">{p.category}</span></td>
                            <td className="px-4 py-3 text-gray-500">{p.stock_count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {result.preview.length > 5 && (
                      <button onClick={() => setShowAllProducts(s => !s)}
                        className="w-full py-3 text-sm text-gray-500 hover:text-black flex items-center justify-center gap-1 border-t border-gray-100">
                        {showAllProducts ? <><ChevronUp className="w-4 h-4" /> Show less</> : <><ChevronDown className="w-4 h-4" /> Show all {result.preview.length} products</>}
                      </button>
                    )}
                  </div>
                </div>
              )}

              {/* Agent permissions */}
              {result.can_publish && (
                <>
                  <div className="mb-6">
                    <button onClick={() => setShowPermissions(s => !s)}
                      className="flex items-center justify-between w-full border border-gray-200 rounded-xl px-5 py-4 hover:bg-gray-50 transition-colors">
                      <span className="font-medium">Agent Permissions</span>
                      {showPermissions ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </button>
                    {showPermissions && (
                      <div className="border border-gray-200 border-t-0 rounded-b-xl p-5 space-y-4">
                        <div>
                          <label className="block text-sm font-medium mb-1.5">Max transaction (₹)</label>
                          <input type="number" value={permissions.max_transaction_inr}
                            onChange={e => setPermissions(p => ({ ...p, max_transaction_inr: parseFloat(e.target.value) }))}
                            className="border border-gray-200 rounded-lg px-3 py-2 text-sm w-full focus:outline-none focus:border-black" />
                          <p className="text-xs text-gray-500 mt-1">AI agents cannot initiate payments above this amount.</p>
                        </div>
                        <div>
                          <label className="block text-sm font-medium mb-1.5">Require confirmation above (₹)</label>
                          <input type="number" value={permissions.requires_confirmation_above_inr}
                            onChange={e => setPermissions(p => ({ ...p, requires_confirmation_above_inr: parseFloat(e.target.value) }))}
                            className="border border-gray-200 rounded-lg px-3 py-2 text-sm w-full focus:outline-none focus:border-black" />
                          <p className="text-xs text-gray-500 mt-1">Confirmation is always required (cannot be disabled).</p>
                        </div>
                      </div>
                    )}
                  </div>

                  <button onClick={handlePublish} disabled={loading}
                    className={clsx('w-full bg-neutral-950 hover:bg-neutral-800 text-white font-medium py-3 rounded-xl flex items-center justify-center gap-2 shadow-sm transition-all',
                      loading ? 'opacity-70 cursor-not-allowed' : 'hover:scale-[1.01] active:scale-[0.99]')}
                  >
                    {loading ? <><Spinner /> Publishing...</> : '🚀 Publish Catalog to Live API'}
                  </button>
                </>
              )}
            </div>
          )}
        </GlassCard>
      ) : (
        /* Success state */
        <GlassCard glowColor="emerald" className="p-8 text-center animate-slide-up">
          <div className="w-14 h-14 bg-emerald-600 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-sm text-white">
            <CheckCircle2 className="w-7 h-7" />
          </div>
          <Badge variant="success" size="sm" className="mb-2">
            Catalog Published & Verified
          </Badge>
          <h2 className="text-2xl sm:text-3xl font-bold text-neutral-900 dark:text-white mb-2">
            Your store is now AI-ready.
          </h2>
          <p className="text-neutral-500 text-sm mb-6 max-w-md mx-auto">
            Autonomous AI buyer agents can now discover, browse semantic embeddings, and initiate test purchases from your catalog.
          </p>

          <div className="bg-neutral-50 dark:bg-neutral-900 border border-neutral-200/80 dark:border-neutral-800 rounded-xl p-4 mb-6 text-left max-w-lg mx-auto">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-neutral-500 mb-1.5">
              Live Catalog Discovery Endpoint
            </div>
            <div className="flex items-center justify-between gap-3">
              <CodePill code={`/catalog/${result?.merchant_id}`} className="bg-white dark:bg-neutral-800" />
              <button
                onClick={() => { navigator.clipboard.writeText(`/catalog/${result?.merchant_id}`); toast.success('Copied!') }}
                className="text-neutral-400 hover:text-neutral-900 dark:hover:text-white transition-colors"
                title="Copy endpoint"
              >
                <Copy className="w-4 h-4" />
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 mb-6 max-w-sm mx-auto text-left">
            <div className="p-3 bg-neutral-50 dark:bg-neutral-900 rounded-xl border border-neutral-200/60">
              <div className="text-xl font-bold text-neutral-900 dark:text-white">{result?.validation.valid || 0}</div>
              <div className="text-xs text-neutral-500">Products Indexed</div>
            </div>
            <div className="p-3 bg-neutral-50 dark:bg-neutral-900 rounded-xl border border-neutral-200/60">
              <div className="text-xl font-bold text-emerald-600">Active</div>
              <div className="text-xs text-neutral-500">MCP Discovery</div>
            </div>
          </div>

          <a
            href="/buyer"
            className="inline-flex items-center gap-2 bg-neutral-950 hover:bg-neutral-800 text-white font-medium text-xs sm:text-sm px-6 py-3 rounded-xl shadow-sm transition-all"
          >
            Test with Buyer Agent <ArrowRight className="w-4 h-4" />
          </a>
        </GlassCard>
      )}
    </div>
  )
}

function Stat({ value, label, color = 'text-black' }: { value: number | string; label: string; color?: string }) {
  return (
    <div>
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      <div className="text-xs text-gray-500 mt-0.5">{label}</div>
    </div>
  )
}

function Spinner() {
  return <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
}
