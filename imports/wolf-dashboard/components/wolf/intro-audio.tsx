'use client'

/**
 * Wolf Audio Engine — WoWS Edition
 * - Auto-starts on first user interaction anywhere on the page
 * - Plays Jordan Belfort / Wolf of Wall Street audio clips
 * - Falls back to Web Audio API synth if CDN fails
 * - soundEnabled state controlled from Config tab only (no UI here)
 * - Renders nothing — completely invisible in the DOM
 */

import { useEffect, useRef } from 'react'

// ── Shared AudioContext singleton ─────────────────────────────────────────
let ctx: AudioContext | null = null

function getCtx(): AudioContext | null {
  if (ctx && ctx.state !== 'closed') {
    if (ctx.state === 'suspended') ctx.resume()
    return ctx
  }
  try {
    const Ctor = window.AudioContext ??
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    ctx = new Ctor()
    return ctx
  } catch { return null }
}

// ── Play an audio file URL, fall back to synthFn on failure ──────────────
function playClip(url: string, synthFn: () => void, volume = 0.7) {
  const audio = new Audio()
  audio.volume = volume
  audio.crossOrigin = 'anonymous'
  audio.preload = 'auto'

  const timeout = setTimeout(() => {
    // Took too long — use synth fallback
    synthFn()
  }, 3000)

  audio.oncanplaythrough = () => {
    clearTimeout(timeout)
    audio.play().catch(() => synthFn())
  }

  audio.onerror = () => {
    clearTimeout(timeout)
    synthFn()
  }

  audio.src = url
}

// ── Synth fallbacks ───────────────────────────────────────────────────────
function tone(freq: number, type: OscillatorType, gain: number, start: number, dur: number, endFreq?: number) {
  const c = getCtx(); if (!c) return
  const t = c.currentTime + start
  const o = c.createOscillator()
  const g = c.createGain()
  o.connect(g); g.connect(c.destination)
  o.type = type
  o.frequency.setValueAtTime(freq, t)
  if (endFreq) o.frequency.exponentialRampToValueAtTime(endFreq, t + dur)
  g.gain.setValueAtTime(0, t)
  g.gain.linearRampToValueAtTime(gain, t + 0.02)
  g.gain.exponentialRampToValueAtTime(0.001, t + dur)
  o.start(t); o.stop(t + dur + 0.05)
}

function synthIntro() {
  getCtx()
  tone(55, 'sine', 0.5, 0, 0.6, 28)
  tone(200, 'sawtooth', 0.08, 0.3, 0.9, 600)
  tone(1100, 'sine', 0.15, 0.75, 0.6)
  tone(1320, 'sine', 0.10, 0.9, 0.5)
}

export function synthWin() {
  getCtx()
  ;[523, 659, 784, 1047].forEach((f, i) => tone(f, 'sine', 0.18, i * 0.12, 0.55))
}

export function synthLoss() {
  getCtx()
  tone(320, 'sawtooth', 0.12, 0, 0.6, 110)
  tone(180, 'sine', 0.08, 0.15, 0.5)
}

// ── WoWS clip URLs — multiple CDN sources per sound ──────────────────────
// myinstants.com is the most reliable free SFX host
const CLIPS = {
  // "I'm not leaving!" — intro sound
  intro: [
    'https://www.myinstants.com/media/sounds/im-not-leaving.mp3',
    'https://www.myinstants.com/media/sounds/wolf-of-wall-street-not-leaving.mp3',
  ],
  // "Sell me this pen" — win sound
  win: [
    'https://www.myinstants.com/media/sounds/sell-me-this-pen.mp3',
    'https://www.myinstants.com/media/sounds/sell-me-this-pen_1.mp3',
  ],
  // "I've been a poor man..." — loss sound
  loss: [
    'https://www.myinstants.com/media/sounds/wolf-of-wall-street-poor-rich.mp3',
  ],
}

function tryClip(urls: string[], synthFn: () => void, volume = 0.7) {
  // Try first URL, if fails try second, if fails use synth
  function attempt(idx: number) {
    if (idx >= urls.length) { synthFn(); return }
    const audio = new Audio()
    audio.volume = volume
    audio.crossOrigin = 'anonymous'
    let fired = false

    const timeout = setTimeout(() => {
      if (!fired) { fired = true; attempt(idx + 1) }
    }, 2500)

    audio.oncanplaythrough = () => {
      if (!fired) {
        fired = true
        clearTimeout(timeout)
        audio.play().catch(() => attempt(idx + 1))
      }
    }
    audio.onerror = () => {
      if (!fired) {
        fired = true
        clearTimeout(timeout)
        attempt(idx + 1)
      }
    }
    audio.src = urls[idx]
  }
  attempt(0)
}

// ── Component — invisible, lives in page root ─────────────────────────────
interface IntroAudioProps {
  soundEnabled: boolean
  lastTradeResult?: 'win' | 'loss' | null
}

export function IntroAudio({ soundEnabled, lastTradeResult }: IntroAudioProps) {
  const bootedRef = useRef(false)
  const prevResult = useRef<string | null>(null)

  // Auto-start on first user interaction anywhere on the page
  useEffect(() => {
    if (!soundEnabled) return

    const handler = () => {
      if (bootedRef.current) return
      bootedRef.current = true
      // Create AudioContext on this gesture (required by browser policy)
      getCtx()
      // Play WoWS intro clip
      tryClip(CLIPS.intro, synthIntro, 0.75)
      ;['click', 'keydown', 'touchstart', 'scroll'].forEach(ev =>
        document.removeEventListener(ev, handler)
      )
    }

    ;['click', 'keydown', 'touchstart', 'scroll'].forEach(ev =>
      document.addEventListener(ev, handler, { passive: true })
    )

    return () => {
      ;['click', 'keydown', 'touchstart', 'scroll'].forEach(ev =>
        document.removeEventListener(ev, handler)
      )
    }
  }, [soundEnabled])

  // If sound toggled ON after page load, fire intro immediately
  useEffect(() => {
    if (soundEnabled && !bootedRef.current) {
      bootedRef.current = true
      getCtx()
      tryClip(CLIPS.intro, synthIntro, 0.75)
    }
    if (!soundEnabled) {
      bootedRef.current = false // allow re-fire if re-enabled
    }
  }, [soundEnabled])

  // Win/loss reactive SFX
  useEffect(() => {
    if (!soundEnabled || !lastTradeResult) return
    if (lastTradeResult === prevResult.current) return
    prevResult.current = lastTradeResult
    if (lastTradeResult === 'win') tryClip(CLIPS.win, synthWin, 0.7)
    else tryClip(CLIPS.loss, synthLoss, 0.6)
  }, [lastTradeResult, soundEnabled])

  // Renders nothing — completely invisible
  return null
}
