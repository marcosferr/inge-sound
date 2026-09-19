import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { api } from '../lib/api'
import type { StemFile } from '../lib/types'

export interface TrackState {
  volume: number
  muted: boolean
  solo: boolean
  ready: boolean
}

/**
 * Plays every stem of a track as one synchronized mix.
 *
 * Each stem gets its own `<audio>` element routed through a Web Audio gain
 * node. Elements drift apart over time, so the first one acts as the clock and
 * the rest are nudged back whenever they slip past `DRIFT_TOLERANCE`.
 */
const DRIFT_TOLERANCE = 0.08

export function useMultitrackPlayer(jobId: string, stems: StemFile[]) {
  const elements = useRef(new Map<string, HTMLAudioElement>())
  const gains = useRef(new Map<string, GainNode>())
  const context = useRef<AudioContext | null>(null)
  const frame = useRef<number>(0)

  const [playing, setPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [states, setStates] = useState<Record<string, TrackState>>({})

  const stemIds = useMemo(() => stems.map((stem) => stem.id).join('|'), [stems])

  // Build the graph whenever the stem set changes.
  useEffect(() => {
    const audioContext = new AudioContext()
    context.current = audioContext
    const localElements = new Map<string, HTMLAudioElement>()
    const localGains = new Map<string, GainNode>()
    const initial: Record<string, TrackState> = {}

    stems.forEach((stem) => {
      const audio = new Audio(api.stemUrl(jobId, stem))
      audio.crossOrigin = 'anonymous'
      audio.preload = 'auto'
      const gain = audioContext.createGain()
      audioContext.createMediaElementSource(audio).connect(gain)
      gain.connect(audioContext.destination)

      audio.addEventListener('loadedmetadata', () => {
        setDuration((current) => Math.max(current, audio.duration || 0))
        setStates((current) => ({
          ...current,
          [stem.id]: { ...(current[stem.id] ?? defaultState()), ready: true },
        }))
      })
      audio.addEventListener('ended', () => setPlaying(false))

      localElements.set(stem.id, audio)
      localGains.set(stem.id, gain)
      initial[stem.id] = defaultState()
    })

    elements.current = localElements
    gains.current = localGains
    setStates(initial)
    setCurrentTime(0)
    setDuration(0)
    setPlaying(false)

    return () => {
      localElements.forEach((audio) => {
        audio.pause()
        audio.src = ''
      })
      void audioContext.close()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, stemIds])

  // Apply solo/mute/volume to the gain nodes.
  useEffect(() => {
    const anySolo = Object.values(states).some((state) => state.solo)
    gains.current.forEach((gain, id) => {
      const state = states[id]
      if (!state) return
      const audible = anySolo ? state.solo && !state.muted : !state.muted
      gain.gain.value = audible ? state.volume : 0
    })
  }, [states])

  // The master clock: follow the first element and correct drift on the rest.
  useEffect(() => {
    if (!playing) return
    const tick = () => {
      const [leader, ...followers] = [...elements.current.values()]
      if (leader) {
        setCurrentTime(leader.currentTime)
        followers.forEach((audio) => {
          if (Math.abs(audio.currentTime - leader.currentTime) > DRIFT_TOLERANCE) {
            audio.currentTime = leader.currentTime
          }
        })
      }
      frame.current = requestAnimationFrame(tick)
    }
    frame.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame.current)
  }, [playing])

  const play = useCallback(async () => {
    if (context.current?.state === 'suspended') await context.current.resume()
    const leader = [...elements.current.values()][0]
    const from = leader?.currentTime ?? 0
    elements.current.forEach((audio) => {
      audio.currentTime = from
    })
    await Promise.all([...elements.current.values()].map((audio) => audio.play()))
    setPlaying(true)
  }, [])

  const pause = useCallback(() => {
    elements.current.forEach((audio) => audio.pause())
    setPlaying(false)
  }, [])

  const toggle = useCallback(() => {
    if (playing) pause()
    else void play()
  }, [playing, pause, play])

  const seek = useCallback((seconds: number) => {
    elements.current.forEach((audio) => {
      audio.currentTime = seconds
    })
    setCurrentTime(seconds)
  }, [])

  const setVolume = useCallback((id: string, volume: number) => {
    setStates((current) => ({
      ...current,
      [id]: { ...(current[id] ?? defaultState()), volume },
    }))
  }, [])

  const toggleMute = useCallback((id: string) => {
    setStates((current) => ({
      ...current,
      [id]: { ...(current[id] ?? defaultState()), muted: !current[id]?.muted },
    }))
  }, [])

  const toggleSolo = useCallback((id: string) => {
    setStates((current) => ({
      ...current,
      [id]: { ...(current[id] ?? defaultState()), solo: !current[id]?.solo },
    }))
  }, [])

  const resetMix = useCallback(() => {
    setStates((current) =>
      Object.fromEntries(Object.keys(current).map((id) => [id, defaultState()])),
    )
  }, [])

  return {
    playing,
    currentTime,
    duration,
    states,
    play,
    pause,
    toggle,
    seek,
    setVolume,
    toggleMute,
    toggleSolo,
    resetMix,
  }
}

function defaultState(): TrackState {
  return { volume: 1, muted: false, solo: false, ready: false }
}
