'use client'

import { useEffect } from 'react'

const CSS = `
@keyframes wolfTickerScroll {
  0%   { transform: translateX(0); }
  100% { transform: translateX(-50%); }
}
`

function injectCSS() {
  if (typeof document === 'undefined') return
  if (document.getElementById('wtb-css')) return
  const s = document.createElement('style')
  s.id = 'wtb-css'
  s.textContent = CSS
  document.head.appendChild(s)
}


// ── Ticker items ──────────────────────────────────────────────────────────
type TickerItem = { text: string; style: string }

const TICKER_ITEMS: TickerItem[] = [
  { text: "BUY OR FUCKING DIE",                                               style: 'text-amber-400 font-black' },
  { text: "THE HUNT NEVER STOPS",                                             style: 'text-white font-bold' },
  { text: "MONEY NEVER SLEEPS",                                               style: 'text-amber-300/80 font-medium italic' },
  { text: "STRATTON OAKMONT IS AMERICA",                                      style: 'text-amber-400 font-black' },
  { text: "SELL ME THIS PEN",                                                 style: 'text-amber-300/80 font-medium italic' },
  { text: "I'M NOT FUCKING LEAVING",                                          style: 'text-amber-400 font-black' },
  { text: "THERE'S NO NOBILITY IN POVERTY",                                  style: 'text-amber-300/80 font-medium italic' },
  { text: "ACT AS IF YOU'RE THE WOLF",                                       style: 'text-white font-bold' },
  { text: "16 OPEN POSITIONS · PAPER MODE ACTIVE",                           style: 'text-emerald-400 font-bold' },
  { text: "WIN RATE TARGET: 72%",                                             style: 'text-emerald-400 font-bold' },
  { text: "KILL SWITCH ARMED: -40%",                                          style: 'text-emerald-400 font-bold' },
  { text: "I'VE BEEN A POOR MAN AND I'VE BEEN A RICH MAN · I CHOOSE RICH",  style: 'text-amber-300/80 font-medium italic' },
  { text: "PREDATORY PATTERN RECOGNITION: ONLINE",                            style: 'text-emerald-400 font-bold' },
]

export function TickerBanner() {
  useEffect(() => { injectCSS() }, [])

  // Duplicate for seamless loop
  const items = [...TICKER_ITEMS, ...TICKER_ITEMS]

  return (
    <div className="relative overflow-hidden bg-black/60 border-b border-amber-500/20 h-7 flex items-center">
      {/* Left fade */}
      <div className="absolute left-0 top-0 bottom-0 w-12 bg-gradient-to-r from-black/80 to-transparent z-10 pointer-events-none" />
      {/* Right fade */}
      <div className="absolute right-0 top-0 bottom-0 w-12 bg-gradient-to-l from-black/80 to-transparent z-10 pointer-events-none" />

      {/* Scrolling track */}
      <div
        className="flex items-center whitespace-nowrap"
        style={{
          animation: 'wolfTickerScroll 70s linear infinite',
          willChange: 'transform',
        }}
      >
        {items.map((item, i) => (
          <span key={i} className="inline-flex items-center gap-3">
            <span className={`text-[11px] tracking-[0.15em] px-1 ${item.style}`}>
              {item.text}
            </span>
            <span className="text-amber-500/30 text-[10px] mx-1">◆</span>
          </span>
        ))}
      </div>
    </div>
  )
}
