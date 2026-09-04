import { Link, useLocation } from 'react-router-dom'
import { Zap, ShieldCheck, Activity } from 'lucide-react'
import clsx from 'clsx'

const links = [
  { to: '/merchant', label: 'Onboard Merchant' },
  { to: '/buyer', label: 'Buyer Agent' },
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/evaluate', label: 'Evaluation' },
  { to: '/audit', label: 'Audit Trail' },
]

export default function Nav() {
  const { pathname } = useLocation()

  return (
    <header className="sticky top-3 z-50 px-4 sm:px-6 w-full max-w-7xl mx-auto pointer-events-none">
      <div className="pointer-events-auto flex items-center justify-between rounded-2xl border border-neutral-200/80 dark:border-white/10 bg-white/85 dark:bg-neutral-900/85 px-4 py-2.5 shadow-sm backdrop-blur-xl transition-all duration-300">
        
        {/* Brand */}
        <Link to="/" className="flex items-center gap-2.5 group">
          <div className="size-8 rounded-xl bg-gradient-to-tr from-neutral-950 to-neutral-800 text-white flex items-center justify-center shadow-md shadow-neutral-900/10 group-hover:scale-105 transition-transform duration-200">
            <Zap className="size-4 text-amber-400 fill-amber-400" />
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-1.5">
              <span className="font-bold text-sm tracking-tight text-neutral-900 dark:text-white">
                Small Merchant
              </span>
              <span className="rounded-full bg-blue-50 dark:bg-blue-950/60 border border-blue-200/80 dark:border-blue-800 px-1.5 py-0.2 text-[9px] font-semibold text-blue-700 dark:text-blue-400 uppercase tracking-wide">
                Agentic
              </span>
            </div>
            <span className="text-[10px] text-neutral-400 font-mono -mt-0.5">
              Razorpay Buildathon 2026
            </span>
          </div>
        </Link>

        {/* Navigation Tabs */}
        <nav className="hidden md:flex items-center gap-1 rounded-2xl bg-neutral-100/90 dark:bg-neutral-800/90 p-1.5 border border-neutral-200/80 dark:border-neutral-700/80 shadow-inner">
          {links.map(l => {
            const isActive = pathname.startsWith(l.to)
            return (
              <Link
                key={l.to}
                to={l.to}
                className={clsx(
                  'relative flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs select-none transition-all duration-200',
                  isActive
                    ? 'bg-neutral-950 dark:bg-white text-white dark:text-neutral-950 font-bold shadow-md ring-2 ring-neutral-950/10 scale-[1.02]'
                    : 'text-neutral-600 dark:text-neutral-300 hover:text-neutral-950 dark:hover:text-white hover:bg-neutral-200/60 font-medium'
                )}
              >
                {isActive && (
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 dark:bg-emerald-600 animate-pulse shrink-0" />
                )}
                <span>{l.label}</span>
              </Link>
            )
          })}
        </nav>

        {/* Right Info: Live MCP Status & Track */}
        <div className="flex items-center gap-2.5">
          <Link
            to="/buyer"
            className="flex items-center gap-2 rounded-full border border-emerald-200/80 bg-emerald-50/70 dark:bg-emerald-950/40 dark:border-emerald-800/80 px-3 py-1 text-[11px] font-medium text-emerald-800 dark:text-emerald-300 hover:bg-emerald-100/70 transition-colors shadow-xs"
            title="Razorpay Remote MCP Server Connected"
          >
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
            </span>
            <span className="font-mono font-semibold">Remote MCP</span>
            <span className="hidden lg:inline text-emerald-600 dark:text-emerald-400 font-normal">
              · 42 Tools
            </span>
          </Link>

          <div className="hidden sm:flex items-center gap-1 text-[11px] text-neutral-400 font-mono pl-1 border-l border-neutral-200 dark:border-neutral-800">
            <ShieldCheck className="size-3.5 text-blue-500" />
            <span>Test Mode</span>
          </div>
        </div>

      </div>

      {/* Mobile nav drawer / links bar */}
      <div className="md:hidden mt-2 pointer-events-auto flex items-center justify-center gap-1 overflow-x-auto rounded-xl bg-white/90 border border-neutral-200/70 p-1 shadow-sm backdrop-blur-md">
        {links.map(l => (
          <Link
            key={l.to}
            to={l.to}
            className={clsx(
              'px-2.5 py-1 rounded-md text-[11px] font-medium whitespace-nowrap transition-colors',
              pathname.startsWith(l.to)
                ? 'bg-neutral-900 text-white font-semibold'
                : 'text-neutral-600 hover:text-neutral-900'
            )}
          >
            {l.label}
          </Link>
        ))}
      </div>
    </header>
  )
}
