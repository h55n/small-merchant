import React from 'react'
import clsx from 'clsx'

export interface MetricCardProps {
  label?: string
  title?: string
  value: string | number
  sublabel?: string
  subtext?: string
  subtitle?: string
  change?: string
  target?: string
  ok?: boolean
  trend?: {
    value: string
    isPositive?: boolean
  } | string
  icon?: any
  chartType?: 'bar' | 'line' | 'avatars' | 'none'
  variant?: 'default' | 'emerald' | 'indigo' | 'amber' | 'rose'
  className?: string
}

export function MetricCard({
  label,
  title,
  value,
  sublabel,
  subtext,
  subtitle,
  change,
  target,
  ok,
  trend,
  icon: IconComponent,
  chartType = 'none',
  variant = 'default',
  className = '',
}: MetricCardProps) {
  const displayLabel = label || title || ''
  const displaySubtext = subtext || sublabel || subtitle || (change ? `${change}` : undefined) || (target ? `Target: ${target}` : undefined)

  // Normalize trend
  const trendObj = typeof trend === 'string'
    ? { value: trend, isPositive: trend !== 'down' }
    : trend

  // Render icon if it's a React element or a component
  const renderedIcon = React.isValidElement(IconComponent) ? (
    IconComponent
  ) : typeof IconComponent === 'function' || (typeof IconComponent === 'object' && IconComponent !== null) ? (
    <IconComponent className="w-5 h-5" />
  ) : null

  const variantStyles = {
    default: 'border-neutral-200/80 bg-white hover:border-neutral-300',
    emerald: 'border-emerald-200/80 bg-emerald-50/30 hover:border-emerald-300',
    indigo: 'border-indigo-200/80 bg-indigo-50/30 hover:border-indigo-300',
    amber: 'border-amber-200/80 bg-amber-50/30 hover:border-amber-300',
    rose: 'border-rose-200/80 bg-rose-50/30 hover:border-rose-300',
  }

  return (
    <article
      className={clsx(
        'group flex flex-col justify-between rounded-2xl border p-5 shadow-sm transition-all duration-300 hover:shadow-md backdrop-blur-sm',
        variantStyles[variant] || variantStyles.default,
        className
      )}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        {renderedIcon && (
          <span className="inline-flex size-10 items-center justify-center rounded-xl border border-black/[0.05] bg-black/[0.03] text-neutral-800 shadow-inner group-hover:scale-105 transition-transform duration-300">
            {renderedIcon}
          </span>
        )}
        {trendObj && (
          <span
            className={clsx(
              'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold',
              trendObj.isPositive !== false
                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200/60'
                : 'bg-rose-50 text-rose-700 border border-rose-200/60'
            )}
          >
            {trendObj.value}
          </span>
        )}
        {ok !== undefined && (
          <span
            className={clsx(
              'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold',
              ok
                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200/60'
                : 'bg-rose-50 text-rose-700 border border-rose-200/60'
            )}
          >
            {ok ? 'Passed' : 'Action Req'}
          </span>
        )}
      </div>

      {chartType === 'bar' && (
        <div className="flex h-10 items-end gap-1.5 py-1 mb-3 opacity-80 group-hover:opacity-100 transition-opacity">
          <span className="flex-1 rounded-sm h-4 bg-neutral-100 group-hover:bg-neutral-200 transition-colors" />
          <span className="flex-1 rounded-sm h-7 bg-neutral-100 group-hover:bg-neutral-200 transition-colors" />
          <span className="flex-1 rounded-sm h-5 bg-neutral-100 group-hover:bg-neutral-200 transition-colors" />
          <span className="flex-1 rounded-sm h-9 bg-neutral-100 group-hover:bg-neutral-200 transition-colors" />
          <span className="flex-1 rounded-sm h-8 bg-neutral-100 group-hover:bg-neutral-200 transition-colors" />
          <span className="flex-1 rounded-sm h-10 bg-neutral-200 group-hover:bg-neutral-300 transition-colors" />
          <span className="flex-1 rounded-sm h-10 bg-zinc-900 shadow-sm" />
        </div>
      )}

      <footer className="border-t border-black/[0.05] pt-3 mt-auto">
        <p className="font-sans text-2xl font-bold tracking-tight text-neutral-900 tabular-nums">
          {value}
        </p>
        <div className="mt-1 flex items-center justify-between text-xs text-neutral-500">
          <span className="font-medium">{displayLabel}</span>
          {displaySubtext && <span className="text-neutral-400 font-mono text-[11px]">{displaySubtext}</span>}
        </div>
      </footer>
    </article>
  )
}
