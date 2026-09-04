import React from 'react'
import { Server, Sparkles } from 'lucide-react'
import clsx from 'clsx'

export interface StatusIndicatorProps {
  status?: 'connected' | 'connecting' | 'error' | 'idle' | 'online' | 'busy' | 'offline' | 'warning'
  label?: string
  sublabel?: string
  toolCount?: number
  pulse?: boolean
  onClick?: () => void
  icon?: React.ReactNode
  className?: string
}

export function StatusIndicator({
  status = 'connected',
  label,
  sublabel,
  toolCount,
  pulse = false,
  onClick,
  icon,
  className = '',
}: StatusIndicatorProps) {
  // Normalize status
  const normalizedStatus = (
    status === 'online' ? 'connected' :
    status === 'busy' ? 'connecting' :
    status === 'offline' ? 'idle' :
    status === 'warning' ? 'connecting' :
    status
  )

  const dotColors = {
    connected: 'bg-emerald-500',
    connecting: 'bg-amber-500',
    error: 'bg-rose-500',
    idle: 'bg-neutral-400',
  }

  const pingColors = {
    connected: 'bg-emerald-400',
    connecting: 'bg-amber-400',
    error: 'bg-rose-400',
    idle: 'bg-neutral-300',
  }

  const showPing = pulse || normalizedStatus === 'connected' || normalizedStatus === 'connecting'

  return (
    <div
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      className={clsx(
        'inline-flex items-center gap-2 rounded-full border border-neutral-200/90 bg-white/90 px-3 py-1 text-xs text-neutral-700 shadow-sm backdrop-blur-md transition-all duration-200',
        onClick && 'cursor-pointer hover:border-zinc-400 hover:bg-zinc-50 hover:shadow-md active:scale-98',
        className
      )}
    >
      <span className="relative flex h-2 w-2">
        {showPing && (
          <span
            className={clsx(
              'animate-ping absolute inline-flex h-full w-full rounded-full opacity-75',
              pingColors[normalizedStatus]
            )}
          />
        )}
        <span
          className={clsx(
            'relative inline-flex rounded-full h-2 w-2',
            dotColors[normalizedStatus]
          )}
        />
      </span>

      {icon || (label && <Server className="size-3 text-neutral-400" />)}

      {label && (
        <span className="font-semibold text-neutral-800 flex items-center gap-1.5">
          {label}
          {sublabel && (
            <span className="text-[11px] font-normal text-neutral-400 border-l border-neutral-200 pl-1.5">
              {sublabel}
            </span>
          )}
        </span>
      )}

      {toolCount !== undefined && (
        <span className="text-[11px] font-mono bg-zinc-100 text-zinc-600 px-1.5 py-0.2 rounded-full font-medium">
          {toolCount} tools
        </span>
      )}

      {onClick && (
        <Sparkles className="size-3 text-zinc-500 opacity-70 group-hover:opacity-100 transition-opacity" />
      )}
    </div>
  )
}
