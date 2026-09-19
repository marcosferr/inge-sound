import clsx from 'clsx'
import { useMemo } from 'react'

import { useMultitrackPlayer } from '../hooks/useMultitrackPlayer'
import { api } from '../lib/api'
import { formatBytes, formatDuration, stemColor, stemLabel } from '../lib/format'
import type { Job, StemFile } from '../lib/types'
import { DownloadIcon, PauseIcon, PlayIcon } from './Icons'

interface Props {
  job: Job
}

/** One synchronized mixer per source track. */
export function StemPlayer({ job }: Props) {
  const byTrack = useMemo(() => {
    const map = new Map<string, StemFile[]>()
    for (const stem of job.stems) {
      map.set(stem.track, [...(map.get(stem.track) ?? []), stem])
    }
    return [...map.entries()]
  }, [job.stems])

  return (
    <div className="space-y-4">
      {byTrack.map(([track, stems]) => (
        <TrackMixer key={track || job.id} job={job} track={track} stems={stems} />
      ))}
    </div>
  )
}

function TrackMixer({ job, track, stems }: { job: Job; track: string; stems: StemFile[] }) {
  const player = useMultitrackPlayer(job.id, stems)
  const anySolo = Object.values(player.states).some((state) => state.solo)

  return (
    <div className="rounded-xl border border-white/5 bg-ink-800/40 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={player.toggle}
            aria-label={player.playing ? 'Pausar' : 'Reproducir'}
            className="flex h-10 w-10 items-center justify-center rounded-full bg-accent text-ink-950 transition hover:bg-accent-soft"
          >
            {player.playing ? <PauseIcon className="h-4 w-4" /> : <PlayIcon className="h-4 w-4" />}
          </button>
          <div>
            <p className="text-sm font-medium text-slate-100">{track || 'Pistas separadas'}</p>
            <p className="font-mono text-xs text-slate-500">
              {formatDuration(player.currentTime)} / {formatDuration(player.duration)}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={player.resetMix} className="btn-ghost !px-3 !py-1.5 text-xs">
            Restablecer mezcla
          </button>
          <a href={api.zipUrl(job.id)} className="btn-primary !px-3 !py-1.5 text-xs" download>
            <DownloadIcon className="h-3.5 w-3.5" />
            ZIP
          </a>
        </div>
      </div>

      <input
        type="range"
        aria-label="Posición de reproducción"
        min={0}
        max={player.duration || 0}
        step={0.01}
        value={player.currentTime}
        onChange={(event) => player.seek(Number(event.target.value))}
        className="mb-4"
      />

      <ul className="space-y-2">
        {stems.map((stem) => {
          const state = player.states[stem.id]
          const dimmed = anySolo && !state?.solo
          return (
            <li
              key={stem.id}
              className={clsx(
                'grid grid-cols-[auto_1fr_auto] items-center gap-3 rounded-lg px-2 py-2 transition',
                dimmed ? 'opacity-40' : 'bg-white/[0.02]',
              )}
            >
              <div className="flex items-center gap-2">
                <span
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: stemColor(stem.stem) }}
                  aria-hidden="true"
                />
                <span className="w-24 truncate text-sm text-slate-200">
                  {stemLabel(stem.stem)}
                </span>
              </div>

              <input
                type="range"
                aria-label={`Volumen de ${stemLabel(stem.stem)}`}
                min={0}
                max={1.5}
                step={0.01}
                value={state?.volume ?? 1}
                onChange={(event) => player.setVolume(stem.id, Number(event.target.value))}
              />

              <div className="flex items-center gap-1.5">
                <MixButton
                  active={Boolean(state?.muted)}
                  onClick={() => player.toggleMute(stem.id)}
                  label="M"
                  title="Silenciar"
                  activeClass="bg-rose-500/20 text-rose-300"
                />
                <MixButton
                  active={Boolean(state?.solo)}
                  onClick={() => player.toggleSolo(stem.id)}
                  label="S"
                  title="Solo"
                  activeClass="bg-amber-500/20 text-amber-300"
                />
                <span className="hidden w-16 text-right font-mono text-[11px] text-slate-600 sm:block">
                  {formatBytes(stem.size_bytes)}
                </span>
                <a
                  href={api.stemDownloadUrl(job.id, stem)}
                  download
                  title={`Descargar ${stem.filename}`}
                  className="rounded-md p-1.5 text-slate-500 transition hover:bg-white/5 hover:text-accent"
                >
                  <DownloadIcon className="h-3.5 w-3.5" />
                </a>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function MixButton({
  active,
  onClick,
  label,
  title,
  activeClass,
}: {
  active: boolean
  onClick: () => void
  label: string
  title: string
  activeClass: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-pressed={active}
      className={clsx(
        'h-7 w-7 rounded-md text-xs font-bold transition',
        active ? activeClass : 'bg-white/5 text-slate-500 hover:text-slate-200',
      )}
    >
      {label}
    </button>
  )
}
