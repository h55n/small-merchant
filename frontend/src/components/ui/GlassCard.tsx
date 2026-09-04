import React from 'react'
import clsx from 'clsx'

export interface GlassCardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode
  variant?: 'default' | 'subtle' | 'interactive' | 'accent' | 'dark' | 'elevated' | 'glow'
  padding?: 'none' | 'sm' | 'md' | 'lg' | 'xl'
  glow?: boolean
  glowColor?: 'indigo' | 'blue' | 'emerald' | 'amber' | 'rose' | string
  hoverEffect?: boolean
  interactive?: boolean
  className?: string
}

export function GlassCard({
  children,
  variant = 'default',
  padding = 'md',
  glow = false,
  glowColor,
  hoverEffect = false,
  interactive = false,
  className = '',
  ...props
}: GlassCardProps) {
  const isInteractive = interactive || hoverEffect || variant === 'interactive'

  const variantStyles = {
    default:
      'bg-white border-neutral-200/90 shadow-sm backdrop-blur-md',
    subtle:
      'bg-neutral-50/90 border-neutral-200/70 backdrop-blur-sm',
    interactive:
      'bg-white border-neutral-200/90 shadow-sm hover:shadow-md hover:-translate-y-0.5 hover:border-neutral-300 cursor-pointer backdrop-blur-md transition-all duration-300',
    accent:
      'bg-gradient-to-b from-blue-50/50 to-white/90 border-blue-100 shadow-sm backdrop-blur-md',
    elevated:
      'bg-white border-black/[0.08] shadow-lg backdrop-blur-md',
    glow:
      'bg-white/95 border-neutral-200/80 shadow-md ring-1 ring-emerald-500/20 backdrop-blur-md',
    dark:
      'bg-neutral-900 text-white border-neutral-800 shadow-xl backdrop-blur-xl',
  }

  const paddingStyles = {
    none: 'p-0',
    sm: 'p-3',
    md: 'p-5',
    lg: 'p-7',
    xl: 'p-9',
  }

  const glowStyles = glowColor ? {
    emerald: 'ring-1 ring-emerald-500/30 shadow-lg shadow-emerald-500/5',
    indigo: 'ring-1 ring-indigo-500/30 shadow-lg shadow-indigo-500/5',
    blue: 'ring-1 ring-blue-500/30 shadow-lg shadow-blue-500/5',
    amber: 'ring-1 ring-amber-500/30 shadow-lg shadow-amber-500/5',
    rose: 'ring-1 ring-rose-500/30 shadow-lg shadow-rose-500/5',
  }[glowColor] || 'ring-1 ring-blue-500/20 shadow-lg shadow-blue-500/5' : ''

  return (
    <div
      className={clsx(
        'relative rounded-2xl border transition-all duration-300',
        variantStyles[variant] || variantStyles.default,
        paddingStyles[padding],
        glow && 'ring-1 ring-blue-500/20 shadow-lg shadow-blue-500/5',
        glowStyles,
        isInteractive && 'hover:shadow-md hover:-translate-y-0.5 transition-all duration-200 cursor-pointer',
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
}
