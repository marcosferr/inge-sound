import clsx from 'clsx'

import type { OptionSpec } from '../lib/types'
import { InfoIcon } from './Icons'

interface Props {
  option: OptionSpec
  value: unknown
  onChange: (value: unknown) => void
  /** Choices to render, already narrowed by the parent (e.g. per model). */
  choices?: OptionSpec['choices']
}

/**
 * Renders one Demucs flag from its backend description.
 *
 * Every widget is driven by `option.type`, so a new flag in the catalog shows
 * up here without any frontend change.
 */
export function OptionField({ option, value, onChange, choices }: Props) {
  const available = (choices ?? option.choices).filter(
    (choice) => (choice as { supported?: boolean }).supported !== false,
  )

  return (
    <label className="block">
      <span className="field-label">
        <span className="flex items-center gap-1.5">
          {option.label}
          <span className="group relative inline-flex">
            <InfoIcon className="h-3.5 w-3.5 text-slate-600 transition group-hover:text-accent" />
            <span
              role="tooltip"
              className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 w-64 -translate-x-1/2
                         rounded-lg border border-white/10 bg-ink-800 p-2.5 text-[11px] font-normal
                         normal-case leading-relaxed tracking-normal text-slate-300 opacity-0 shadow-xl
                         transition group-hover:opacity-100"
            >
              {option.help}
              <code className="mt-1 block font-mono text-[10px] text-accent">{option.flag}</code>
            </span>
          </span>
        </span>
        {(option.type === 'int' || option.type === 'float') && (
          <span className="font-mono text-[11px] normal-case text-accent">
            {formatNumber(value, option)}
          </span>
        )}
      </span>

      {option.type === 'enum' && (
        <select
          className="input"
          value={value == null ? '' : String(value)}
          onChange={(event) => onChange(event.target.value === '' ? null : event.target.value)}
        >
          {option.default === null && <option value="">— sin usar —</option>}
          {available.map((choice) => (
            <option key={String(choice.value)} value={String(choice.value)}>
              {choice.label}
            </option>
          ))}
        </select>
      )}

      {(option.type === 'int' || option.type === 'float') && (
        <input
          type="range"
          min={option.minimum ?? 0}
          max={option.maximum ?? 10}
          step={option.step ?? (option.type === 'int' ? 1 : 0.05)}
          value={Number(value ?? option.minimum ?? 0)}
          onChange={(event) => onChange(Number(event.target.value))}
        />
      )}

      {option.type === 'bool' && (
        <button
          type="button"
          role="switch"
          aria-checked={Boolean(value)}
          onClick={() => onChange(!value)}
          className={clsx(
            'relative h-6 w-11 rounded-full transition',
            value ? 'bg-accent' : 'bg-ink-600',
          )}
        >
          <span
            className={clsx(
              'absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all',
              value ? 'left-[22px]' : 'left-0.5',
            )}
          />
        </button>
      )}

      {option.type === 'string' && (
        <input
          type="text"
          className="input font-mono text-xs"
          value={value == null ? '' : String(value)}
          placeholder={option.default ? String(option.default) : 'opcional'}
          onChange={(event) => onChange(event.target.value === '' ? null : event.target.value)}
        />
      )}
    </label>
  )
}

function formatNumber(value: unknown, option: OptionSpec): string {
  if (value == null) return 'auto'
  const numeric = Number(value)
  return option.type === 'float' ? numeric.toFixed(2) : String(numeric)
}
