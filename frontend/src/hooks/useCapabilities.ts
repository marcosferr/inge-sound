import { useEffect, useState } from 'react'

import { api } from '../lib/api'
import type { Capabilities } from '../lib/types'

export function useCapabilities() {
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .capabilities()
      .then((data) => !cancelled && setCapabilities(data))
      .catch((err: Error) => !cancelled && setError(err.message))
    return () => {
      cancelled = true
    }
  }, [])

  return { capabilities, error, loading: !capabilities && !error }
}
