import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ArrowRight, Zap, Store, Bot, BarChart3, ShieldCheck,
  CheckCircle2, Lock, Cpu, Sparkles,
  Terminal, Activity, ChevronDown, Upload,
  Globe, FileText, Database, Eye, MessageSquare, CreditCard,
  PlayCircle, BookOpen, TrendingUp, Code2, Layers, ArrowUpRight
} from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { GlassCard } from '../components/ui/GlassCard'
import { MetricCard } from '../components/ui/MetricCard'
import { CodePill } from '../components/ui/CodePill'
import { StatusIndicator } from '../components/ui/StatusIndicator'
import { getRazorpayMcpStatus, type RazorpayMcpStatus } from '../lib/api'

const statsData = [
  { title: 'Merchants On Razorpay', value: '500,000+', subtitle: 'Huge merchant base ready to unlock', change: 'India ecosystem', trend: 'neutral' as const, icon: Store },
  { title: 'Remote MCP Tools', value: '42 Active', subtitle: 'Hosted on mcp.razorpay.com/mcp', change: '100% Live', trend: 'up' as const, icon: Terminal },
  { title: 'Confirmation Gate', value: '100% Safe', subtitle: 'Zero unauthorized payments guaranteed', change: 'Deterministic', trend: 'up' as const, icon: ShieldCheck },
  { title: 'Discovery Latency', value: '< 1.2s', subtitle: 'Embedding-based hybrid product retrieval', change: 'SentenceTransformers', trend: 'up' as const, icon: Zap },
]

const howItWorksSteps = [
  { number: '01', icon: Store, title: 'Upload Merchant Catalog', desc: 'CSV, Google Sheets, manual form, or product URL. Automated normalization, validation, and embedding indexing in seconds.', tag: 'Self-Service', detail: 'Supports Indian price formats, stock counts, categories, and product descriptions.' },
  { number: '02', icon: Cpu, title: 'Vector Index & Remote MCP', desc: 'Products are exposed via natural-language semantic search and wired to 42 Razorpay Remote MCP payment and refund tools.', tag: 'Model-Agnostic', detail: 'Uses all-MiniLM-L6-v2 sentence transformers for fast offline embedding.' },
  { number: '03', icon: Bot, title: 'AI Buyer Agent Discovery', desc: 'Any autonomous buyer agent queries the catalog, selects matching products, and triggers the purchase workflow.', tag: 'Autonomous', detail: 'Multi-LLM cascade: Groq → NVIDIA NIM → Mistral → Template fallback.' },
  { number: '04', icon: ShieldCheck, title: 'Non-Bypassable Confirmation', desc: 'Deterministic safety rules force explicit human approval before any transaction. 2-attempt max retry limit enforced.', tag: 'Hard Invariant', detail: 'Physically impossible to skip — enforced in code, not in AI instructions.' },
]

const architecturePillars = [
  { title: 'Multi-LLM Resilience Cascade', desc: 'Primary Groq / OpenAI with automated zero-downtime failover to NVIDIA NIM and Mistral AI, backed by deterministic rule-based template.', icon: Cpu, color: 'indigo' as const },
  { title: 'Razorpay Remote MCP Integration', desc: 'Native client for mcp.razorpay.com/mcp running protocol 2024-11-05 with 42 tools for payment links, orders, invoices, and refunds.', icon: Terminal, color: 'blue' as const },
  { title: 'Deterministic Safety Gates', desc: 'Payment initiation is physically impossible without passing through the non-bypassable confirmation gate. No AI hallucinations can authorize spend.', icon: Lock, color: 'emerald' as const },
  { title: 'Immutable Session Audit Trail', desc: 'Every tool execution, token usage, latency milestone, and confidence score is chronologically recorded with complete transparency.', icon: Activity, color: 'amber' as const },
  { title: 'Semantic Vector Catalog Engine', desc: 'Local sentence-transformer embeddings enable fuzzy queries like "cheapest red kurta under Rs 800" to match accurately.', icon: Sparkles, color: 'indigo' as const },
  { title: '70-Scenario Evaluation Suite', desc: 'Rigorous batch evaluation across Happy Path, Ambiguous Intent, and Payment Failure categories with honest failure transparency.', icon: BarChart3, color: 'emerald' as const },
]

const guideSteps = [
  {
    role: 'merchant',
    icon: Store,
    label: 'I am a Merchant',
    color: 'bg-amber-50 text-amber-700 border-amber-200',
    steps: [
      { icon: Upload, text: 'Go to Merchant — fill in your business name and spending limit' },
      { icon: FileText, text: 'Upload your product catalog (CSV or paste a Google Sheets URL)' },
      { icon: Database, text: 'Wait ~3 seconds while we build your AI-searchable vector index' },
      { icon: Eye, text: 'Visit Dashboard to manage products, stock, and permissions' },
      { icon: Globe, text: 'Your store is now discoverable by any AI buyer agent!' },
    ],
  },
  {
    role: 'buyer',
    icon: Bot,
    label: 'I am an AI Buyer / Tester',
    color: 'bg-indigo-50 text-indigo-700 border-indigo-200',
    steps: [
      { icon: Store, text: 'Go to Buyer — select a merchant from the dropdown' },
      { icon: MessageSquare, text: 'Type your purchase intent (e.g. "I need a blue cotton kurta under Rs 1200")' },
      { icon: Sparkles, text: 'The AI agent searches the catalog and presents matching options' },
      { icon: ShieldCheck, text: 'Review the confirmation card — click Confirm or Cancel' },
      { icon: CreditCard, text: 'On confirmation, Razorpay payment link is created in test mode' },
    ],
  },
  {
    role: 'evaluator',
    icon: BarChart3,
    label: 'I want to Run Evaluations',
    color: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    steps: [
      { icon: PlayCircle, text: 'Go to Evaluate — select scenario group (All / Happy Path / Ambiguous / Failures)' },
      { icon: Activity, text: 'Click Run Evaluation — watch results stream in real time via SSE' },
      { icon: BarChart3, text: 'Review pass/fail rates for each of the 70 test scenarios' },
      { icon: BookOpen, text: 'Click Audit — drill into any session\'s step-by-step execution trace' },
      { icon: FileText, text: 'Export results JSON for external analysis or reporting' },
    ],
  },
]

const faqData = [
  { q: 'Does this process real payments?', a: 'No. The system runs exclusively in Razorpay Test Mode. All payment links created are test-mode links — no real money is transferred. Real transactions would require switching to live API keys.' },
  { q: 'What happens if the AI tries to skip the confirmation?', a: 'It is physically impossible. The confirmation gate is enforced in deterministic Python code — not in AI instructions. Even if an LLM produces a malformed tool call, the permission_enforcer.py blocks it before any payment API is touched.' },
  { q: 'What LLMs does the buyer agent use?', a: 'It uses a cascade: Groq (qwen3-32b, primary) → NVIDIA NIM (llama-3.2-11b) → Mistral AI (mistral-small-latest) → Anthropic Claude → OpenAI GPT-4o-mini → Google Gemini → Ollama → Template (always works with no keys).' },
  { q: 'Can I upload my own product catalog?', a: 'Yes. Go to the Merchant page and upload a CSV file (Name, Price, Description, Stock required columns), paste a public Google Sheets URL, or enter products manually one by one.' },
  { q: 'What is the Razorpay Remote MCP Server?', a: "It is Razorpay's hosted Model Context Protocol server at mcp.razorpay.com/mcp running protocol 2024-11-05. It exposes 42 tools (create_payment_link, create_order, refund_payment, etc.) accessible via JSON-RPC 2.0 with HTTP Basic Auth." },
  { q: 'How does the semantic search work?', a: 'Products are embedded offline using the all-MiniLM-L6-v2 sentence transformer model. At query time, the buyer natural language intent is embedded and compared via cosine similarity — no LLM is needed for search itself.' },
  { q: 'What if no AI API keys are configured?', a: 'The system falls back to a deterministic template-based buyer agent. All safety rules (confirmation gate, budget limits, retry caps) still enforce. The conversation will be less natural but fully functional.' },
  { q: 'How do I run the evaluation suite?', a: 'Open the Evaluate page in the UI and click Run Evaluation, or via CLI: cd backend && python -m src.evaluator --scenario all. Results are saved to backend/results/ as timestamped JSON files.' },
]

const useCaseCards = [
  { icon: TrendingUp, title: 'Artisan & Craft Stores', desc: 'Handmade jewelry, pottery, textiles — enable voice and text AI shopping for niche products with fuzzy search.' },
  { icon: Globe, title: 'Local Grocery & Food', desc: 'Organic produce, specialty foods — let AI meal-planning agents discover and purchase ingredients from your store automatically.' },
  { icon: Sparkles, title: 'D2C & Small Brands', desc: 'Fashion, accessories, home decor — become searchable by AI shopping assistants used by thousands of consumers.' },
]

function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border border-neutral-200 rounded-xl overflow-hidden" onClick={() => setOpen(!open)}>
      <button className="w-full text-left flex items-center justify-between px-5 py-4 text-sm font-medium text-neutral-800 hover:bg-neutral-50 transition-colors cursor-pointer">
        <span>{q}</span>
        <ChevronDown className={`w-4 h-4 text-neutral-500 shrink-0 ml-3 transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }}>
            <p className="px-5 pb-4 text-xs text-neutral-600 leading-relaxed border-t border-neutral-100 pt-3">{a}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default function Landing() {
  const nav = useNavigate()
  const [mcpStatus, setMcpStatus] = useState<RazorpayMcpStatus | null>(null)
  const [activeGuideRole, setActiveGuideRole] = useState<'merchant' | 'buyer' | 'evaluator'>('merchant')

  useEffect(() => {
    getRazorpayMcpStatus().then(st => setMcpStatus(st)).catch(() => {})
  }, [])

  const activeGuide = guideSteps.find(g => g.role === activeGuideRole)!

  return (
    <div className="min-h-screen bg-white font-sans selection:bg-neutral-900 selection:text-white">
      {/* Top Banner */}
      <div className="bg-neutral-950 text-neutral-300 text-center py-2 px-4 text-xs font-medium border-b border-neutral-800 flex items-center justify-center gap-3">
        <Badge variant="warning" size="sm" pulsing className="text-[11px] py-0.5">Razorpay Buildathon 2026</Badge>
        <span>Track 01: AI Growth &amp; Agentic Commerce</span>
        <span className="hidden sm:inline text-neutral-500">·</span>
        <button onClick={() => nav('/buyer')} className="hidden sm:inline text-white underline underline-offset-4 hover:text-neutral-200 transition-colors">Try Live Buyer Agent</button>
      </div>

      {/* Floating Header */}
      <header className="sticky top-3 z-50 max-w-6xl mx-auto px-4 sm:px-6">
        <div className="backdrop-blur-xl bg-white/85 border border-neutral-200/80 rounded-2xl shadow-sm px-5 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-neutral-950 rounded-xl flex items-center justify-center"><Zap className="w-4 h-4 text-amber-400 fill-amber-400" /></div>
            <div className="flex flex-col">
              <span className="font-semibold text-sm tracking-tight text-neutral-900">AI Readiness Agent</span>
              <span className="text-[10px] text-neutral-500 font-mono hidden sm:inline">Razorpay Test Mode</span>
            </div>
          </div>
          <nav className="hidden md:flex items-center gap-6 text-xs font-medium text-neutral-600">
            <a href="#guide" className="hover:text-neutral-900 transition-colors">User Guide</a>
            <a href="#how-it-works" className="hover:text-neutral-900 transition-colors">How it Works</a>
            <a href="#architecture" className="hover:text-neutral-900 transition-colors">Architecture</a>
            <a href="#faq" className="hover:text-neutral-900 transition-colors">FAQ</a>
          </nav>
          <div className="flex items-center gap-3">
            <StatusIndicator status={mcpStatus?.connected ? 'connected' : 'connecting'} label="Remote MCP" toolCount={mcpStatus?.tool_count || 42} className="hidden lg:flex" />
            <button onClick={() => nav('/merchant')} className="bg-neutral-900 hover:bg-neutral-800 text-white text-xs font-medium px-4 py-2 rounded-xl transition-all shadow-sm active:scale-95">Get Started</button>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative pt-20 pb-16 overflow-hidden">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[350px] bg-gradient-to-tr from-amber-200/40 via-blue-100/40 to-indigo-100/30 blur-3xl -z-10 pointer-events-none rounded-full" />
        <div className="max-w-5xl mx-auto px-6 text-center">
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="flex flex-wrap items-center justify-center gap-2 mb-6">
            <Badge variant="indigo" size="md" rotate="-rotate-1">Zero-Code Integration</Badge>
            <Badge variant="success" size="md" pulsing rotate="rotate-1">Razorpay Remote MCP (42 Tools)</Badge>
            <Badge variant="outline" size="md">100% Non-Bypassable Safety Gate</Badge>
          </motion.div>
          <motion.h1 initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.1 }} className="text-4xl sm:text-6xl md:text-7xl font-bold tracking-tight text-neutral-900 leading-[1.08] mb-6">
            Make any small merchant catalog <br className="hidden sm:inline" />
            <span className="bg-gradient-to-r from-neutral-950 via-neutral-700 to-neutral-500 bg-clip-text text-transparent">discoverable &amp; transactable by AI.</span>
          </motion.h1>
          <motion.p initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.2 }} className="text-base sm:text-xl text-neutral-600 max-w-2xl mx-auto leading-relaxed mb-10">
            Over 500,000 merchants accept payments on Razorpay, but practically none can be queried or bought from by autonomous AI buyer agents. We provide the instant, safe onboarding layer.
          </motion.p>
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.3 }} className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-14">
            <button onClick={() => nav('/merchant')} className="w-full sm:w-auto bg-neutral-950 hover:bg-neutral-800 text-white font-medium px-7 py-3.5 rounded-2xl flex items-center justify-center gap-2 shadow-lg transition-all active:scale-[0.98]">
              <Store className="w-4 h-4 text-neutral-300" /> Onboard Store in 2 Minutes <ArrowRight className="w-4 h-4 ml-1" />
            </button>
            <button onClick={() => nav('/buyer')} className="w-full sm:w-auto bg-white hover:bg-neutral-50 text-neutral-900 font-medium px-7 py-3.5 rounded-2xl border border-neutral-200 shadow-sm flex items-center justify-center gap-2 transition-all active:scale-[0.98]">
              <Bot className="w-4 h-4 text-neutral-600" /> Test as AI Buyer Agent
            </button>
          </motion.div>

          {/* Pipeline Graphic */}
          <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.4 }} className="max-w-4xl mx-auto">
            <GlassCard hoverEffect={false} className="p-6 text-left border-neutral-200/90 shadow-lg bg-neutral-900 text-white overflow-hidden">
              <div className="flex items-center justify-between pb-4 border-b border-neutral-800 mb-5">
                <div className="flex items-center gap-2">
                  <div className="flex gap-1.5"><div className="w-3 h-3 rounded-full bg-red-500/80" /><div className="w-3 h-3 rounded-full bg-amber-500/80" /><div className="w-3 h-3 rounded-full bg-emerald-500/80" /></div>
                  <span className="text-xs font-mono text-neutral-400 ml-2">pipeline_runtime_graph.json · Razorpay Remote MCP</span>
                </div>
                <Badge variant="success" size="sm" pulsing>End-to-End Loop Verified</Badge>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-5 gap-3 text-xs">
                <div className="bg-neutral-800/80 rounded-xl p-3.5 border border-neutral-700/60">
                  <span className="text-[10px] uppercase font-mono text-neutral-400">Step 1</span>
                  <h4 className="font-semibold text-white mt-1">Catalog Ingestion</h4>
                  <p className="text-neutral-400 text-[11px] mt-2">CSV / URL parsed, 30 products normalized</p>
                </div>
                <div className="bg-neutral-800/80 rounded-xl p-3.5 border border-neutral-700/60">
                  <span className="text-[10px] uppercase font-mono text-neutral-400">Step 2</span>
                  <h4 className="font-semibold text-white mt-1">Vector Search</h4>
                  <p className="text-neutral-400 text-[11px] mt-2">SentenceTransformers semantic embedding match</p>
                </div>
                <div className="bg-neutral-800/80 rounded-xl p-3.5 border border-neutral-700/60">
                  <span className="text-[10px] uppercase font-mono text-neutral-400">Step 3</span>
                  <h4 className="font-semibold text-white mt-1">Multi-LLM Tool Call</h4>
                  <p className="text-neutral-400 text-[11px] mt-2">Groq &rarr; NVIDIA NIM &rarr; Mistral cascade</p>
                </div>
                <div className="bg-amber-950/40 rounded-xl p-3.5 border border-amber-600/50">
                  <span className="text-[10px] uppercase font-mono text-amber-400">Step 4 (Safety)</span>
                  <h4 className="font-semibold text-amber-200 mt-1">Confirmation Gate</h4>
                  <p className="text-amber-300/80 text-[11px] mt-2">Mandatory human permission before payment</p>
                </div>
                <div className="bg-emerald-950/40 rounded-xl p-3.5 border border-emerald-600/50">
                  <span className="text-[10px] uppercase font-mono text-emerald-400">Step 5</span>
                  <h4 className="font-semibold text-emerald-200 mt-1">Razorpay MCP</h4>
                  <p className="text-emerald-300/80 text-[11px] mt-2">Payment link created &amp; test captured</p>
                </div>
              </div>
              <div className="mt-5 pt-4 border-t border-neutral-800 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs">
                <div className="font-mono text-neutral-200 flex items-center gap-2">
                  <Terminal className="w-4 h-4 text-emerald-400" />
                  <span className="font-semibold text-neutral-200">Connect any agent via MCP protocol:</span>
                </div>
                <CodePill code="curl -X POST http://127.0.0.1:8000/api/razorpay/mcp/tools" className="bg-neutral-950 text-emerald-400 border border-neutral-700 font-mono shadow-inner font-semibold" />
              </div>
            </GlassCard>
          </motion.div>
        </div>
      </section>

      {/* Metrics Row */}
      <section id="metrics" className="py-12 border-y border-neutral-200/80 bg-neutral-50/50">
        <div className="max-w-6xl mx-auto px-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            {statsData.map((stat, i) => (<MetricCard key={i} title={stat.title} value={stat.value} subtitle={stat.subtitle} change={stat.change} trend={stat.trend} icon={stat.icon} />))}
          </div>
        </div>
      </section>

      {/* What Is This */}
      <section id="about" className="py-24 max-w-6xl mx-auto px-6">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
          <div>
            <Badge variant="indigo" size="md" className="mb-4">What is this?</Badge>
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight text-neutral-900 mb-5">The missing AI commerce layer for small merchants.</h2>
            <p className="text-neutral-600 text-base leading-relaxed mb-5">
              Large platforms like Zomato, Swiggy, and BigBasket can be shopped by AI agents — they invested millions in custom integrations. The other 500,000 merchants on Razorpay have no equivalent capability.
            </p>
            <p className="text-neutral-600 text-base leading-relaxed mb-8">
              This project builds a <strong className="text-neutral-900">self-service onboarding layer</strong> that any small merchant can use to make their product catalog discoverable and transactable by autonomous AI buyer agents — in under 5 minutes, with zero engineering required.
            </p>
            <div className="flex flex-col sm:flex-row gap-3">
              <button onClick={() => nav('/merchant')} className="bg-neutral-950 text-white text-sm font-medium px-5 py-2.5 rounded-xl flex items-center gap-2 hover:bg-neutral-800 transition-all">
                <Store className="w-4 h-4" /> Onboard as Merchant
              </button>
              <button onClick={() => nav('/buyer')} className="border border-neutral-200 text-neutral-800 text-sm font-medium px-5 py-2.5 rounded-xl flex items-center gap-2 hover:bg-neutral-50 transition-all">
                <Bot className="w-4 h-4" /> Try AI Buyer
              </button>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-4">
            {useCaseCards.map((card, i) => (
              <GlassCard key={i} className="p-5 bg-white border border-neutral-200/90 shadow-sm">
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 bg-neutral-100 rounded-xl flex items-center justify-center shrink-0 border border-neutral-200/60">
                    <card.icon className="w-5 h-5 text-neutral-800" />
                  </div>
                  <div>
                    <h3 className="font-bold text-sm text-neutral-900 mb-1">{card.title}</h3>
                    <p className="text-xs text-neutral-600 font-normal leading-relaxed">{card.desc}</p>
                  </div>
                </div>
              </GlassCard>
            ))}
          </div>
        </div>
      </section>

      {/* User Guide */}
      <section id="guide" className="py-24 bg-neutral-50 border-y border-neutral-200/80">
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center max-w-2xl mx-auto mb-12">
            <Badge variant="amber" size="md" className="mb-3">Quick Start Guide</Badge>
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight text-neutral-900">How to use this platform</h2>
            <p className="text-neutral-600 mt-3 text-base">Follow the steps for your role — merchant, buyer agent tester, or evaluator.</p>
          </div>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mb-10">
            {guideSteps.map(guide => (
              <button key={guide.role} onClick={() => setActiveGuideRole(guide.role as 'merchant' | 'buyer' | 'evaluator')}
                className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold border transition-all ${activeGuideRole === guide.role ? 'bg-neutral-950 text-white border-neutral-950 shadow-md scale-[1.02]' : 'bg-white text-neutral-700 border-neutral-200 hover:border-neutral-300 hover:bg-neutral-50'}`}>
                <guide.icon className="w-4 h-4" />{guide.label}
              </button>
            ))}
          </div>
          <AnimatePresence mode="wait">
            <motion.div key={activeGuideRole} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.2 }} className="max-w-2xl mx-auto">
              <GlassCard className="p-8 bg-white border border-neutral-200 shadow-md">
                <div className="flex items-center gap-3 mb-6 pb-4 border-b border-neutral-200/70">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center border shadow-xs ${activeGuide.color}`}><activeGuide.icon className="w-5 h-5" /></div>
                  <h3 className="font-bold text-base text-neutral-900">{activeGuide.label}</h3>
                </div>
                <ol className="space-y-5">
                  {activeGuide.steps.map((step, i) => (
                    <li key={i} className="flex items-start gap-4">
                      <div className="w-7 h-7 rounded-full bg-neutral-900 text-white flex items-center justify-center text-xs font-bold shrink-0 mt-0.5 shadow-xs">{i + 1}</div>
                      <div className="flex items-start gap-3">
                        <step.icon className="w-4 h-4 text-neutral-600 mt-0.5 shrink-0" />
                        <p className="text-sm font-medium text-neutral-800 leading-relaxed">{step.text}</p>
                      </div>
                    </li>
                  ))}
                </ol>
                <div className="mt-8 pt-5 border-t border-neutral-200/70 flex justify-end">
                  <button onClick={() => nav(activeGuideRole === 'merchant' ? '/merchant' : activeGuideRole === 'buyer' ? '/buyer' : '/evaluate')}
                    className="bg-neutral-950 text-white text-xs font-semibold px-5 py-2.5 rounded-xl flex items-center gap-2 hover:bg-neutral-800 shadow-sm transition-all active:scale-95">
                    Start Now <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </GlassCard>
            </motion.div>
          </AnimatePresence>
        </div>
      </section>

      {/* How it Works */}
      <section id="how-it-works" className="py-24 max-w-6xl mx-auto px-6">
        <div className="text-center max-w-2xl mx-auto mb-16">
          <Badge variant="indigo" size="md" className="mb-3">Workflow Architecture</Badge>
          <h2 className="text-3xl sm:text-4xl font-bold tracking-tight text-neutral-900">From spreadsheet to AI-ready in 5 minutes.</h2>
          <p className="text-neutral-600 mt-3 text-base">No merchant code required. No complex backend deployment. Complete end-to-end flow verified on Razorpay test mode.</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {howItWorksSteps.map((step, i) => (
            <GlassCard key={i} className="p-6 flex flex-col justify-between bg-white border border-neutral-200 shadow-sm hover:shadow-md transition-shadow">
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="w-10 h-10 rounded-xl bg-neutral-950 text-white flex items-center justify-center font-bold text-sm shadow-xs">{step.number}</div>
                  <Badge variant="outline" size="sm" className="font-semibold">{step.tag}</Badge>
                </div>
                <h3 className="text-base font-bold text-neutral-900 mb-2">{step.title}</h3>
                <p className="text-xs text-neutral-700 leading-relaxed font-normal">{step.desc}</p>
                <p className="text-[11px] text-neutral-500 mt-3 italic font-medium">{step.detail}</p>
              </div>
              <div className="mt-6 pt-4 border-t border-neutral-100 flex items-center text-xs font-semibold text-neutral-800">
                <step.icon className="w-4 h-4 mr-2 text-emerald-600" /><span>Production Verified</span>
              </div>
            </GlassCard>
          ))}
        </div>
      </section>

      {/* Architecture */}
      <section id="architecture" className="py-24 bg-neutral-900 text-white">
        <div className="max-w-6xl mx-auto px-6">
          <div className="max-w-2xl mb-16">
            <Badge variant="warning" size="md" className="mb-3">Reliability First</Badge>
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight">Enterprise Resilience &amp; Full Observability</h2>
            <p className="text-neutral-400 mt-3 text-base">Every layer includes automated failover. The agent operates securely without any possibility of runaway spend.</p>
          </div>

          {/* System Architecture Diagram Showcase */}
          <div className="mb-14 rounded-2xl border border-neutral-700/80 bg-neutral-800/80 p-5 sm:p-7 shadow-2xl backdrop-blur-md">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5 pb-4 border-b border-neutral-700/60">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[11px] font-mono uppercase tracking-widest text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800/60">
                    System Architecture Diagram
                  </span>
                  <Badge variant="outline" size="sm" className="border-neutral-600 text-neutral-300">
                    Track 01 · Razorpay AI Buildathon 2026
                  </Badge>
                </div>
                <h3 className="text-lg font-bold text-white">Merchant Onboarding to Autonomous Checkout Architecture</h3>
              </div>
              <a
                href="/small-merchant-dia.png"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-neutral-300 hover:text-white bg-neutral-700/70 hover:bg-neutral-700 px-3.5 py-1.5 rounded-xl border border-neutral-600 transition-colors"
              >
                <span>Full Resolution</span>
                <ArrowUpRight className="w-3.5 h-3.5" />
              </a>
            </div>
            
            <div className="relative rounded-xl overflow-hidden bg-neutral-950/60 border border-neutral-700/50 group">
              <img
                src="/small-merchant-dia.png"
                alt="Small-Merchant AI Readiness Agent — System Diagram"
                className="w-full h-auto object-contain max-h-[640px] mx-auto transition-transform duration-300 group-hover:scale-[1.01]"
              />
            </div>
            <p className="text-xs text-neutral-400 mt-4 text-center">
              Comprehensive system map illustrating the deterministic normalizer pipeline, 384-dim semantic embeddings, Buyer Agent tool orchestrator, non-bypassable confirmation gate, and Razorpay test-mode execution.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-10">
            {architecturePillars.map((p, i) => (
              <div key={i} className="relative rounded-2xl border border-neutral-700/70 bg-neutral-800 p-6 flex flex-col justify-between transition-all duration-300 hover:-translate-y-0.5 hover:border-neutral-600">
                <div>
                  <div className="w-9 h-9 rounded-xl bg-neutral-700 flex items-center justify-center mb-4"><p.icon className="w-4 h-4 text-white" /></div>
                  <h3 className="text-base font-semibold text-white mb-2">{p.title}</h3>
                  <p className="text-xs text-neutral-400 leading-relaxed">{p.desc}</p>
                </div>
                <div className="mt-5 pt-3 border-t border-neutral-700/50 flex items-center text-[11px] font-mono text-neutral-400">
                  <CheckCircle2 className="w-3.5 h-3.5 mr-1.5 text-emerald-400" /><span>Tested &amp; Enforced</span>
                </div>
              </div>
            ))}
          </div>
          {/* LLM Cascade */}
          <div className="p-6 rounded-2xl border border-neutral-700/60 bg-neutral-800/40">
            <div className="flex items-center gap-2 mb-5">
              <Layers className="w-4 h-4 text-amber-400" />
              <span className="text-sm font-semibold text-white">Multi-LLM Cascade Order</span>
              <Badge variant="amber" size="sm" className="ml-2">Auto-Failover</Badge>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              {['1. Groq (primary)', '2. NVIDIA NIM', '3. Mistral AI', '4. Anthropic', '5. OpenAI', '6. Gemini', '7. Ollama', '8. Template'].map((provider, i, arr) => (
                <div key={provider} className="flex items-center gap-2">
                  <div className={`px-3 py-1.5 rounded-lg border font-mono text-[11px] ${i === 0 ? 'bg-emerald-950/50 border-emerald-600/50 text-emerald-300' : i === arr.length - 1 ? 'bg-neutral-700/50 border-neutral-600/50 text-neutral-400' : 'bg-neutral-800/50 border-neutral-700/50 text-neutral-400'}`}>{provider}</div>
                  {i < arr.length - 1 && <span className="text-neutral-600">&rarr;</span>}
                </div>
              ))}
            </div>
            <p className="text-[11px] text-neutral-500 mt-4">Primary: Groq qwen3-32b. Falls back automatically on 429 rate limits or timeouts. Template fallback requires zero network access.</p>
          </div>
        </div>
      </section>

      {/* Safety */}
      <section id="safety" className="py-24 max-w-6xl mx-auto px-6">
        <div className="text-center max-w-2xl mx-auto mb-16">
          <Badge variant="outline" size="md" className="mb-3">Safety Invariant Matrix</Badge>
          <h2 className="text-3xl sm:text-4xl font-bold tracking-tight text-neutral-900">Where AI is Used vs. Deterministically Restricted</h2>
          <p className="text-neutral-500 mt-3 text-base">We delegate fuzzy matching to AI, but lock down all financial transactions with deterministic code.</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-10">
          <GlassCard glowColor="indigo" className="p-7 bg-white border border-neutral-200/90 shadow-md">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center shadow-xs"><Sparkles className="w-4 h-4 text-indigo-600" /></div>
              <div><h3 className="font-bold text-base text-neutral-900">AI-Powered (Fuzzy &amp; Flexible)</h3><p className="text-xs text-neutral-600 font-medium">LLM reasoning with semantic vector matching</p></div>
            </div>
            <ul className="space-y-3.5 text-xs text-neutral-800 font-medium">
              <li className="flex items-start gap-2.5"><CheckCircle2 className="w-4 h-4 text-indigo-600 mt-0.5 shrink-0" /><span>Natural-language product discovery (e.g. cheapest red kurta under Rs 800)</span></li>
              <li className="flex items-start gap-2.5"><CheckCircle2 className="w-4 h-4 text-indigo-600 mt-0.5 shrink-0" /><span>Category inference from ambiguous user specifications</span></li>
              <li className="flex items-start gap-2.5"><CheckCircle2 className="w-4 h-4 text-indigo-600 mt-0.5 shrink-0" /><span>Ranking and presenting multiple options when intent is broad</span></li>
              <li className="flex items-start gap-2.5"><CheckCircle2 className="w-4 h-4 text-indigo-600 mt-0.5 shrink-0" /><span>Reasoning step explanations logged to audit trail</span></li>
            </ul>
          </GlassCard>
          <GlassCard glowColor="emerald" className="p-7 bg-white border border-neutral-200/90 shadow-md">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-9 h-9 rounded-xl bg-emerald-50 border border-emerald-100 flex items-center justify-center shadow-xs"><Lock className="w-4 h-4 text-emerald-600" /></div>
              <div><h3 className="font-bold text-base text-neutral-900">Deterministic (Zero AI Bypass)</h3><p className="text-xs text-neutral-600 font-medium">Hard-coded state machines and cryptographic checks</p></div>
            </div>
            <ul className="space-y-3.5 text-xs text-neutral-800 font-medium">
              <li className="flex items-start gap-2.5"><CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" /><span><strong className="text-neutral-950 font-bold">Confirmation Gate:</strong> Non-bypassable explicit user confirmation modal</span></li>
              <li className="flex items-start gap-2.5"><CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" /><span><strong className="text-neutral-950 font-bold">Budget Hard-Limit:</strong> Transactions exceeding budget are blocked in code</span></li>
              <li className="flex items-start gap-2.5"><CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" /><span><strong className="text-neutral-950 font-bold">Stopping Rule:</strong> Strictly capped at maximum 2 payment attempts</span></li>
              <li className="flex items-start gap-2.5"><CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" /><span><strong className="text-neutral-950 font-bold">Dual-Engine Razorpay:</strong> Seamless fallback between SDK &amp; Remote MCP</span></li>
            </ul>
          </GlassCard>
        </div>
        {/* Code Evidence */}
        <GlassCard className="p-6 bg-neutral-950 border-neutral-800">
          <div className="flex items-center gap-2 mb-4">
            <Code2 className="w-4 h-4 text-emerald-400" />
            <span className="text-sm font-semibold text-white">Safety Enforcement Code Evidence</span>
            <Badge variant="success" size="sm" className="ml-auto">permission_enforcer.py</Badge>
          </div>
          <pre className="text-[11px] font-mono text-neutral-400 overflow-x-auto leading-relaxed">{`# permission_enforcer.py — runs BEFORE any payment API call
def enforce_pre_payment(session, intent_amount):
    if not session.confirmation_gate_passed:
        raise PermissionError("CONFIRMATION_GATE_NOT_PASSED")   # Hard block
    if intent_amount > session.spending_limit:
        raise PermissionError("BUDGET_EXCEEDED")                 # Hard block
    if session.payment_attempts >= MAX_ATTEMPTS:
        raise PermissionError("MAX_ATTEMPTS_REACHED")            # Hard block`}</pre>
          <p className="text-[11px] text-neutral-500 mt-3">Source: backend/src/agent/permission_enforcer.py — enforced by Python, not by AI instructions.</p>
        </GlassCard>
      </section>

      {/* Eval CTA */}
      <section className="py-16 bg-neutral-950 text-white">
        <div className="max-w-5xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-8">
          <div>
            <Badge variant="warning" size="sm" className="mb-2">Automated Test Suite</Badge>
            <h2 className="text-2xl sm:text-3xl font-bold">Ready to inspect all 70 test scenarios?</h2>
            <p className="text-neutral-400 text-xs sm:text-sm mt-1 max-w-xl">Run real batch evaluations against live test scenarios with complete audit verification.</p>
            <div className="mt-4 grid grid-cols-3 gap-4 text-center max-w-xs">
              <div><div className="text-2xl font-bold text-emerald-400">30</div><div className="text-[11px] text-neutral-500">Happy Path</div></div>
              <div><div className="text-2xl font-bold text-amber-400">20</div><div className="text-[11px] text-neutral-500">Ambiguous</div></div>
              <div><div className="text-2xl font-bold text-rose-400">20</div><div className="text-[11px] text-neutral-500">Failures</div></div>
            </div>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <button onClick={() => nav('/evaluate')} className="bg-white hover:bg-neutral-100 text-neutral-950 font-medium text-xs px-6 py-3 rounded-xl transition-all shadow-sm flex items-center gap-2"><BarChart3 className="w-4 h-4" /> Open Eval Runner</button>
            <button onClick={() => nav('/audit')} className="border border-neutral-700 hover:border-neutral-500 text-white font-medium text-xs px-6 py-3 rounded-xl transition-all flex items-center gap-2"><Eye className="w-4 h-4" /> View Audit Trail</button>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="py-24 max-w-4xl mx-auto px-6">
        <div className="text-center mb-12">
          <Badge variant="outline" size="md" className="mb-3">FAQ</Badge>
          <h2 className="text-3xl sm:text-4xl font-bold tracking-tight text-neutral-900">Everything you need to know</h2>
          <p className="text-neutral-500 mt-3 text-base">Questions about safety, payments, LLMs, and how to run the system.</p>
        </div>
        <div className="space-y-3">{faqData.map((item, i) => <FaqItem key={i} q={item.q} a={item.a} />)}</div>
        <div className="mt-10 text-center">
          <p className="text-sm text-neutral-500">Still have questions? <button onClick={() => nav('/buyer')} className="text-neutral-900 font-medium underline underline-offset-4 hover:text-neutral-600">Try the live demo</button></p>
        </div>
      </section>

      {/* Tech Stack */}
      <section className="py-10 border-t border-neutral-200/80 bg-neutral-50/50">
        <div className="max-w-6xl mx-auto px-6">
          <p className="text-center text-xs text-neutral-400 font-medium uppercase tracking-widest mb-6">Technology Stack</p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            {['FastAPI', 'SQLAlchemy (async)', 'SentenceTransformers', 'Groq API', 'NVIDIA NIM', 'Mistral AI', 'Razorpay Remote MCP', 'React + TypeScript', 'Vite', 'SQLite / PostgreSQL', 'Redis', 'Docker Compose'].map(tech => (
              <span key={tech} className="px-3 py-1.5 bg-white border border-neutral-200 rounded-lg text-xs font-mono text-neutral-600 hover:border-neutral-300 transition-colors">{tech}</span>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-10 border-t border-neutral-200 text-xs text-neutral-500">
        <div className="max-w-6xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2 font-medium text-neutral-800">
            <div className="w-5 h-5 bg-neutral-950 rounded-md flex items-center justify-center"><Zap className="w-3 h-3 text-amber-400 fill-amber-400" /></div>
            AI Readiness Agent · Razorpay AI Buildathon 2026
          </div>
          <div className="flex items-center gap-4 text-[11px]">
            <span>Remote MCP: mcp.razorpay.com/mcp</span><span>·</span><span>Test Mode Only</span><span>·</span>
            <button onClick={() => nav('/audit')} className="hover:text-neutral-700 transition-colors">Audit Trail</button>
            <button onClick={() => nav('/evaluate')} className="hover:text-neutral-700 transition-colors">Evaluation</button>
          </div>
        </div>
      </footer>
    </div>
  )
}
