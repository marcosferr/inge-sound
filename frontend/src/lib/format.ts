export function formatBytes(bytes: number): string {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / 1024 ** exponent
  return `${value.toFixed(value >= 10 || exponent === 0 ? 0 : 1)} ${units[exponent]}`
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '--:--'
  const total = Math.max(0, Math.round(seconds))
  const minutes = Math.floor(total / 60)
  const rest = total % 60
  return `${minutes}:${String(rest).padStart(2, '0')}`
}

export function formatEta(seconds: number | null): string {
  if (seconds == null || !Number.isFinite(seconds)) return ''
  if (seconds < 60) return `~${Math.round(seconds)} s`
  if (seconds < 3600) return `~${Math.round(seconds / 60)} min`
  return `~${(seconds / 3600).toFixed(1)} h`
}

export function formatRelativeTime(iso: string): string {
  const delta = (Date.now() - new Date(iso).getTime()) / 1000
  if (delta < 60) return 'hace instantes'
  if (delta < 3600) return `hace ${Math.floor(delta / 60)} min`
  if (delta < 86400) return `hace ${Math.floor(delta / 3600)} h`
  return new Date(iso).toLocaleDateString('es', { day: 'numeric', month: 'short' })
}

const STEM_LABELS: Record<string, string> = {
  vocals: 'Voces',
  drums: 'Batería',
  bass: 'Bajo',
  other: 'Otros',
  guitar: 'Guitarra',
  piano: 'Piano',
}

export function stemLabel(stem: string): string {
  if (stem.startsWith('no_')) {
    const base = STEM_LABELS[stem.slice(3)] ?? stem.slice(3)
    return `Sin ${base.toLowerCase()}`
  }
  return STEM_LABELS[stem] ?? stem
}

/** Per-stem accents, so the player reads as one system rather than a rainbow. */
const STEM_COLORS: Record<string, string> = {
  vocals: '#f472b6',
  drums: '#fbbf24',
  bass: '#60a5fa',
  other: '#a78bfa',
  guitar: '#34d399',
  piano: '#f87171',
}

export function stemColor(stem: string): string {
  const base = stem.startsWith('no_') ? stem.slice(3) : stem
  return STEM_COLORS[base] ?? '#94a3b8'
}
