'use client'

import { useState, useRef, useEffect } from 'react'
import { Play, Square, Volume2 } from 'lucide-react'

const CSS = `
@keyframes sbBar{0%,100%{transform:scaleY(0.25)}50%{transform:scaleY(1)}}
.sb-bar{display:inline-block;width:2px;background:currentColor;height:10px;border-radius:1px;margin:0 0.5px;transform-origin:bottom}
.sb-bar:nth-child(1){animation:sbBar 0.45s ease-in-out infinite}
.sb-bar:nth-child(2){animation:sbBar 0.45s ease-in-out infinite 0.15s}
.sb-bar:nth-child(3){animation:sbBar 0.45s ease-in-out infinite 0.3s}
`

let _ctx: AudioContext | null = null
function getCtx() {
  if (_ctx && _ctx.state !== 'closed') { if (_ctx.state === 'suspended') _ctx.resume(); return _ctx }
  try {
    const C = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    _ctx = new C(); return _ctx
  } catch { return null }
}
function tone(freq: number, type: OscillatorType, gain: number, start: number, dur: number, endFreq?: number) {
  const c = getCtx(); if (!c) return
  const t = c.currentTime + start, o = c.createOscillator(), g = c.createGain()
  o.connect(g); g.connect(c.destination); o.type = type
  o.frequency.setValueAtTime(freq, t)
  if (endFreq) o.frequency.exponentialRampToValueAtTime(endFreq, t + dur)
  g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(gain, t + 0.02); g.gain.exponentialRampToValueAtTime(0.001, t + dur)
  o.start(t); o.stop(t + dur + 0.05)
}

interface Sound { id: string; label: string; emoji: string; clip?: string; synth: () => void; synthDur: number; color: string }

const SOUNDS: Sound[] = [
  {
    id: 'not-leaving', label: "I'M NOT LEAVING", emoji: '🚫',
    clip: '/sounds/not-leaving.mp3',
    synth: () => { tone(55, 'sine', 0.4, 0, 0.6, 28); tone(200, 'sawtooth', 0.08, 0.4, 0.9, 600); tone(1100, 'sine', 0.12, 0.8, 0.6) },
    synthDur: 2000, color: 'amber',
  },
  {
    id: 'sell-pen', label: 'SELL ME THIS PEN', emoji: '🖊️',
    clip: '/sounds/pen.mp3',
    synth: () => { [523, 659, 784, 1047].forEach((f, i) => tone(f, 'sine', 0.18, i * 0.13, 0.6)) },
    synthDur: 1800, color: 'emerald',
  },
  {
    id: 'poverty', label: 'NO NOBILITY IN POVERTY', emoji: '👑',
    clip: '/sounds/poverty.mp3',
    synth: () => { tone(220, 'sine', 0.15, 0, 0.8); tone(330, 'sine', 0.1, 0.4, 0.6) },
    synthDur: 1500, color: 'yellow',
  },
  {
    id: 'show-goes-on', label: 'THE SHOW GOES ON', emoji: '🎭',
    clip: '/sounds/show-goes-on.mp3',
    synth: () => { [330, 440, 550, 660].forEach((f, i) => tone(f, 'triangle', 0.12, i * 0.15, 0.6)) },
    synthDur: 1800, color: 'purple',
  },
  {
    id: 'not-leaving2', label: 'SHOW GOES ON (ALT)', emoji: '🔁',
    clip: '/sounds/not-leaving.mp3',              // not-leaving.mp3 — 117KB (shorter cut) ✅
    synth: () => { tone(110, 'sawtooth', 0.12, 0, 0.4); tone(220, 'sawtooth', 0.08, 0.3, 0.6); tone(440, 'sine', 0.12, 0.6, 0.7) },
    synthDur: 1800, color: 'blue',
  },
  {
    id: 'choose-rich', label: 'I CHOOSE RICH', emoji: '💰',
    // No real clip — triumphant ascending synth
    synth: () => { tone(80, 'sine', 0.3, 0, 0.5, 40); [440, 554, 659, 880].forEach((f, i) => tone(f, 'sine', 0.14, 0.5 + i * 0.15, 0.55)) },
    synthDur: 2200, color: 'orange',
  },
  {
    id: 'stratton', label: 'STRATTON OAKMONT', emoji: '🇺🇸',
    // No real clip — patriotic trumpet fanfare synth
    synth: () => { [330, 440, 550, 440, 550, 660, 880].forEach((f, i) => tone(f, 'triangle', 0.14, i * 0.17, 0.22)) },
    synthDur: 1800, color: 'red',
  },
  {
    id: 'pick-up-phone', label: 'PICK UP THE PHONE', emoji: '📞',
    // No real clip — urgent dialing beep synth
    synth: () => {
      [0, 0.7, 1.4].forEach(s => { tone(480, 'sine', 0.15, s, 0.3); tone(620, 'sine', 0.12, s + 0.05, 0.25) })
      [2.0, 2.4].forEach(s => tone(880, 'sine', 0.2, s, 0.15))
    },
    synthDur: 2800, color: 'blue',
  },
]

const COLORS: Record<string, string> = {
  amber:   'border-amber-500/20 hover:border-amber-500/45 hover:bg-amber-500/8 text-amber-400',
  emerald: 'border-emerald-500/20 hover:border-emerald-500/45 hover:bg-emerald-500/8 text-emerald-400',
  yellow:  'border-yellow-500/20 hover:border-yellow-500/45 hover:bg-yellow-500/8 text-yellow-400',
  purple:  'border-purple-500/20 hover:border-purple-500/45 hover:bg-purple-500/8 text-purple-400',
  blue:    'border-blue-500/20 hover:border-blue-500/45 hover:bg-blue-500/8 text-blue-400',
  orange:  'border-orange-500/20 hover:border-orange-500/45 hover:bg-orange-500/8 text-orange-400',
  red:     'border-red-500/20 hover:border-red-500/45 hover:bg-red-500/8 text-red-400',
}

export function BelfortSoundboard() {
  const [playing, setPlaying] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  useEffect(() => {
    if (typeof document === 'undefined') return
    if (!document.getElementById('sb-css')) {
      const s = document.createElement('style'); s.id = 'sb-css'; s.textContent = CSS
      document.head.appendChild(s)
    }
  }, [])

  function stop() {
    if (audioRef.current) { audioRef.current.pause(); audioRef.current.currentTime = 0; audioRef.current = null }
    setPlaying(null)
  }

  function play(sound: Sound) {
    stop()
    getCtx() // unlock on user gesture

    if (sound.clip) {
      const audio = new Audio(sound.clip.startsWith('/') ? sound.clip : `/api/wolf/audio/${sound.clip}`)
      audio.volume = 0.9
      audioRef.current = audio

      let settled = false
      const timeout = setTimeout(() => {
        if (!settled) { settled = true; runSynth() }
      }, 4000)

      audio.oncanplaythrough = () => {
        if (settled) return
        settled = true; clearTimeout(timeout)
        audio.play().then(() => {
          setPlaying(sound.id)
          audio.onended = () => setPlaying(null)
        }).catch(() => runSynth())
      }
      audio.onerror = () => { if (!settled) { settled = true; clearTimeout(timeout); runSynth() } }
    } else {
      runSynth()
    }

    function runSynth() {
      sound.synth()
      setPlaying(sound.id)
      setTimeout(() => setPlaying(null), sound.synthDur)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Volume2 className="h-4 w-4 text-amber-500" />
        <span className="text-sm font-black text-white tracking-wider">BELFORT BOARD</span>
        <span className="text-[10px] text-zinc-600 italic ml-1">Wolf of Wall Street</span>
      </div>

      <div className="grid grid-cols-2 gap-1.5">
        {SOUNDS.map(sound => {
          const isPlaying = playing === sound.id
          const colors = COLORS[sound.color] ?? COLORS.amber
          return (
            <button
              key={sound.id}
              onClick={() => isPlaying ? stop() : play(sound)}
              className={`flex items-center gap-2 rounded-lg border bg-white/[0.02] px-2.5 py-2 text-left transition-all active:scale-95 ${colors}`}
            >
              <span className="text-sm shrink-0">{sound.emoji}</span>
              <span className="flex-1 text-[9px] font-black tracking-wider leading-tight truncate">{sound.label}</span>
              <span className="shrink-0 w-4 flex justify-center">
                {isPlaying
                  ? <span className="flex items-end"><span className="sb-bar" /><span className="sb-bar" /><span className="sb-bar" /></span>
                  : <Play className="h-2.5 w-2.5 opacity-25" />}
              </span>
            </button>
          )
        })}
      </div>

      <p className="text-[9px] text-zinc-800 text-center italic">Click to play · Click again to stop</p>
    </div>
  )
}
