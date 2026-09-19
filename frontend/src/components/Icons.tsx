/** Inline SVG icons: no icon dependency, and they inherit `currentColor`. */

type Props = { className?: string }

const base = 'h-4 w-4'

export const PlayIcon = ({ className = base }: Props) => (
  <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M8 5.14v13.72a1 1 0 0 0 1.54.84l10.2-6.86a1 1 0 0 0 0-1.68L9.54 4.3A1 1 0 0 0 8 5.14Z" />
  </svg>
)

export const PauseIcon = ({ className = base }: Props) => (
  <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M7 4h3.5v16H7zM13.5 4H17v16h-3.5z" />
  </svg>
)

export const DownloadIcon = ({ className = base }: Props) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 3v12m0 0 4-4m-4 4-4-4M4 19h16" />
  </svg>
)

export const TrashIcon = ({ className = base }: Props) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M4 7h16M10 11v6m4-6v6M6 7l1 13h10l1-13M9 7V4h6v3" />
  </svg>
)

export const RetryIcon = ({ className = base }: Props) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M20 12a8 8 0 1 1-2.6-5.9M20 4v4h-4" />
  </svg>
)

export const StopIcon = ({ className = base }: Props) => (
  <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <rect x="6" y="6" width="12" height="12" rx="2" />
  </svg>
)

export const UploadIcon = ({ className = 'h-8 w-8' }: Props) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 16V4m0 0 4 4m-4-4L8 8M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
  </svg>
)

export const ChevronIcon = ({ className = base }: Props) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="m6 9 6 6 6-6" />
  </svg>
)

export const InfoIcon = ({ className = 'h-3.5 w-3.5' }: Props) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5M12 7.5v.5" />
  </svg>
)

export const WaveIcon = ({ className = 'h-5 w-5' }: Props) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
    <path d="M3 12h2m2-5v10m3-7v4m3-8v12m3-9v6m3-4v2m2 0h2" />
  </svg>
)
