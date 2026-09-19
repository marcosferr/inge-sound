import clsx from 'clsx'
import { useMemo, useState } from 'react'

import type { Capabilities, ModelInfo, OptionSpec } from '../lib/types'
import { ChevronIcon } from './Icons'
import { OptionField } from './OptionField'

interface Props {
  capabilities: Capabilities
  values: Record<string, unknown>
  onChange: (values: Record<string, unknown>) => void
}

const SPEED_LABELS: Record<ModelInfo['speed'], string> = {
  fast: 'Rápido',
  medium: 'Medio',
  slow: 'Lento',
  very_slow: 'Muy lento',
}

const QUALITY_LABELS: Record<ModelInfo['quality'], string> = {
  good: 'Buena',
  better: 'Muy buena',
  best: 'Excelente',
}

export function OptionsPanel({ capabilities, values, onChange }: Props) {
  const [advanced, setAdvanced] = useState(false)

  const model = capabilities.models.find((item) => item.name === values.model)
  const set = (key: string, value: unknown) => onChange({ ...values, [key]: value })

  /** An option is shown only if its `depends_on` conditions currently hold. */
  const visible = useMemo(
    () =>
      capabilities.options.filter((option) => {
        if (option.supported === false) return false
        if (option.advanced && !advanced) return false
        if (!option.depends_on) return true
        return Object.entries(option.depends_on).every(([key, accepted]) =>
          accepted.includes(values[key] as never),
        )
      }),
    [capabilities.options, advanced, values],
  )

  const byGroup = useMemo(() => {
    const map = new Map<string, OptionSpec[]>()
    for (const option of visible) {
      map.set(option.group, [...(map.get(option.group) ?? []), option])
    }
    return map
  }, [visible])

  return (
    <div className="space-y-5">
      <div>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-200">Presets</h3>
          <button
            type="button"
            onClick={() => setAdvanced((current) => !current)}
            className="flex items-center gap-1 text-xs text-slate-400 transition hover:text-accent"
          >
            {advanced ? 'Ocultar avanzado' : 'Modo avanzado'}
            <ChevronIcon className={clsx('h-3.5 w-3.5 transition', advanced && 'rotate-180')} />
          </button>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {capabilities.presets.map((preset) => {
            const active = Object.entries(preset.options).every(
              ([key, value]) => values[key] === value,
            )
            return (
              <button
                key={preset.key}
                type="button"
                title={preset.description}
                onClick={() => onChange({ ...values, ...preset.options })}
                className={clsx(
                  'rounded-xl border px-3 py-2 text-left text-xs transition',
                  active
                    ? 'border-accent/60 bg-accent/10 text-accent'
                    : 'border-white/10 text-slate-300 hover:border-white/25 hover:text-white',
                )}
              >
                <span className="block font-semibold">{preset.label}</span>
                <span className="mt-0.5 block leading-snug text-slate-500">
                  {preset.description}
                </span>
                {preset.dropped && preset.dropped.length > 0 && (
                  <span className="mt-1 block leading-snug text-amber-500/80">
                    Sin {preset.dropped.join(', ').toLowerCase()} en esta versión de Demucs.
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      {model && (
        <div className="rounded-xl border border-white/5 bg-ink-800/50 p-3 text-xs">
          <p className="text-slate-300">{model.description}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="chip bg-accent/10 text-accent">
              Calidad {QUALITY_LABELS[model.quality]}
            </span>
            <span className="chip bg-white/5 text-slate-300">
              Velocidad {SPEED_LABELS[model.speed]}
            </span>
            {model.sub_models > 1 && (
              <span className="chip bg-amber-500/10 text-amber-300">
                {model.sub_models} redes en cascada
              </span>
            )}
            <span className="text-slate-500">Pistas: {model.stems.join(', ')}</span>
          </div>
        </div>
      )}

      {capabilities.option_groups.map((group) => {
        const options = byGroup.get(group.key)
        if (!options?.length) return null
        return (
          <section key={group.key} className="space-y-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              {group.label}
            </h4>
            <div className="grid gap-4 sm:grid-cols-2">
              {options.map((option) => (
                <OptionField
                  key={option.key}
                  option={option}
                  value={values[option.key]}
                  onChange={(value) => set(option.key, value)}
                  choices={narrowChoices(option, model, capabilities)}
                />
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}

/** Some choice lists only make sense against the selected model or host. */
function narrowChoices(
  option: OptionSpec,
  model: ModelInfo | undefined,
  capabilities: Capabilities,
): OptionSpec['choices'] | undefined {
  if (option.key === 'two_stems' && model) {
    return option.choices.filter((choice) => model.stems.includes(String(choice.value)))
  }
  if (option.key === 'device') {
    return option.choices.filter(
      (choice) => choice.value === 'auto' || capabilities.devices.includes(String(choice.value)),
    )
  }
  return undefined
}
