import React from 'react'
import clsx from 'clsx'

export type BadgeVariant =
  | 'neutral'
  | 'success'
  | 'warning'
  | 'primary'
  | 'purple'
  | 'mcp'
  | 'emerald'
  | 'amber'
  | 'rose'
  | 'indigo'
  | 'outline'
  | 'default'

export interface BadgeProps {
  children: React.ReactNode
  variant?: BadgeVariant
  pulse?: boolean
  pulsing?: boolean
  rotate?: '-rotate-3' | 'rotate-3' | 'rotate-6' | '-rotate-6' | '-rotate-1' | 'rotate-1' | '-rotate-2' | 'rotate-2' | 'none' | string
  size?: 'sm' | 'md' | 'lg'
  className?: string
  icon?: React.ReactNode
}

export function Badge({
  children,
  variant = 'neutral',
  pulse = false,
  pulsing = false,
  rotate = 'none',
  size = 'md',
  className = '',
  icon,
}: BadgeProps) {
  const isPulsing = pulse || pulsing

  // Normalize variant aliases
  const v = (
    variant === 'emerald' ? 'success' :
    variant === 'amber' ? 'warning' :
    variant === 'rose' ? 'rose' :
    variant === 'indigo' ? 'mcp' :
    variant === 'default' ? 'neutral' :
    variant === 'outline' ? 'neutral' :
    variant
  )

  const variantStyles: Record<string, string> = {
    neutral: 'bg-neutral-100 text-neutral-800 border-neutral-200/80 dark:bg-neutral-800 dark:text-neutral-200 dark:border-neutral-700',
    success: 'bg-emerald-50 text-emerald-700 border-emerald-200/80 dark:bg-emerald-950/40 dark:text-emerald-400 dark:border-emerald-800',
    warning: 'bg-amber-50 text-amber-700 border-amber-200/80 dark:bg-amber-950/40 dark:text-amber-400 dark:border-amber-800',
    primary: 'bg-blue-50 text-blue-700 border-blue-200/80 dark:bg-blue-950/40 dark:text-blue-400 dark:border-blue-800',
    purple: 'bg-purple-50 text-purple-700 border-purple-200/80 dark:bg-purple-950/40 dark:text-purple-400 dark:border-purple-800',
    mcp: 'bg-gradient-to-r from-blue-50 to-indigo-50 text-indigo-900 border-indigo-200/90 shadow-sm shadow-indigo-100/50',
    rose: 'bg-rose-50 text-rose-700 border-rose-200/80 dark:bg-rose-950/40 dark:text-rose-400 dark:border-rose-800',
  }

  const dotColors: Record<string, string> = {
    neutral: 'bg-neutral-500',
    success: 'bg-emerald-500',
    warning: 'bg-amber-500',
    primary: 'bg-blue-500',
    purple: 'bg-purple-500',
    mcp: 'bg-indigo-600',
    rose: 'bg-rose-500',
  }

  const sizeStyles = {
    sm: 'text-[10px] px-2 py-0.5 tracking-wider font-semibold',
    md: 'text-xs px-2.5 py-1 tracking-normal font-medium',
    lg: 'text-sm px-3.5 py-1.5 font-medium',
  }

  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full border font-sans select-none transition-all duration-200',
        variantStyles[v] || variantStyles.neutral,
        sizeStyles[size],
        rotate !== 'none' && rotate,
        className
      )}
    >
      {isPulsing && (
        <span className="relative flex h-2 w-2">
          <span
            className={clsx(
              'animate-ping absolute inline-flex h-full w-full rounded-full opacity-75',
              dotColors[v] || 'bg-emerald-500'
            )}
          />
          <span
            className={clsx(
              'relative inline-flex rounded-full h-2 w-2',
              dotColors[v] || 'bg-emerald-500'
            )}
          />
        </span>
      )}
      {icon && <span className="shrink-0">{icon}</span>}
      <span>{children}</span>
    </span>
  )
}
