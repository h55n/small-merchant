import { useState } from 'react'
import { Check, Copy } from 'lucide-react'
import clsx from 'clsx'

interface CodePillProps {
  code: string
  label?: string
  copyable?: boolean
  className?: string
}

export function CodePill({ code, label, className = '' }: CodePillProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div
      className={clsx(
        'group inline-flex items-center gap-2 rounded-full border border-neutral-200/80 bg-neutral-50/80 px-3 py-1 text-xs text-neutral-700 shadow-sm backdrop-blur-sm transition-all hover:border-neutral-300 hover:bg-white',
        className
      )}
    >
      {label && (
        <span className="font-semibold text-neutral-500 uppercase tracking-wider text-[10px]">
          {label}
        </span>
      )}
      <code className="font-mono text-inherit selection:bg-blue-100/30">{code}</code>
      <button
        type="button"
        onClick={handleCopy}
        className="inline-flex size-5 items-center justify-center rounded-full text-neutral-400 hover:text-neutral-900 transition-colors"
        title="Copy to clipboard"
        aria-label="Copy"
      >
        {copied ? (
          <Check className="size-3.5 text-emerald-600 animate-in zoom-in-50 duration-200" />
        ) : (
          <Copy className="size-3.5 opacity-60 group-hover:opacity-100 transition-opacity" />
        )}
      </button>
    </div>
  )
}
