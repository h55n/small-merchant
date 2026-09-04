import React from 'react'
import { motion } from 'framer-motion'
import clsx from 'clsx'

export interface TabItem {
  id: string
  label: string
  icon?: any
  badge?: string | number
}

export interface FluidTabsProps {
  tabs: TabItem[]
  activeId?: string
  activeTab?: string
  onChange: (id: string) => void
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

export function FluidTabs({
  tabs,
  activeId,
  activeTab,
  onChange,
  size = 'md',
  className = '',
}: FluidTabsProps) {
  const currentActive = activeId || activeTab || (tabs.length > 0 ? tabs[0].id : '')

  const sizeStyles = {
    sm: 'p-1 gap-1 text-xs',
    md: 'p-1.5 gap-1.5 text-sm',
    lg: 'p-2 gap-2 text-base',
  }

  const btnPadding = {
    sm: 'px-3 py-1',
    md: 'px-4 py-1.5',
    lg: 'px-5 py-2',
  }

  return (
    <div
      className={clsx(
        'inline-flex items-center rounded-2xl bg-neutral-100/90 dark:bg-neutral-900/90 border border-neutral-200/80 dark:border-neutral-800 shadow-inner backdrop-blur-md',
        sizeStyles[size],
        className
      )}
    >
      {tabs.map(tab => {
        const isActive = tab.id === currentActive

        const renderedIcon = React.isValidElement(tab.icon) ? (
          tab.icon
        ) : typeof tab.icon === 'function' || (typeof tab.icon === 'object' && tab.icon !== null) ? (
          <tab.icon className="w-4 h-4" />
        ) : null

        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onChange(tab.id)}
            className={clsx(
              'relative flex items-center gap-2 rounded-xl font-medium select-none transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500',
              btnPadding[size],
              isActive
                ? 'text-neutral-950 dark:text-white font-semibold'
                : 'text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200'
            )}
          >
            {isActive && (
              <motion.div
                layoutId="active-fluid-tab"
                transition={{ type: 'spring', stiffness: 450, damping: 35 }}
                className="absolute inset-0 rounded-xl bg-white dark:bg-neutral-800 shadow-sm border border-neutral-200/60 dark:border-neutral-700/60"
              />
            )}
            <span className="relative z-10 flex items-center gap-2">
              {renderedIcon && <span className="shrink-0">{renderedIcon}</span>}
              <span>{tab.label}</span>
              {tab.badge !== undefined && (
                <span
                  className={clsx(
                    'ml-0.5 rounded-full px-1.5 py-0.2 text-[10px] font-mono',
                    isActive
                      ? 'bg-neutral-100 text-neutral-800 dark:bg-neutral-700 dark:text-neutral-200'
                      : 'bg-neutral-200/70 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400'
                  )}
                >
                  {tab.badge}
                </span>
              )}
            </span>
          </button>
        )
      })}
    </div>
  )
}
