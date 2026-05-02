'use client'

import { useEffect, useRef } from 'react'

/*
  Realistic wolf head — snarling, forward-facing.
  CSS animations injected once into document.head.
  No styled-jsx, no external files, no package deps.
*/

const CSS = `
@keyframes wfBlink{0%,90%,100%{transform:scaleY(1)}95%{transform:scaleY(0.1)}}
@keyframes wfGlow{0%,100%{opacity:.7;filter:drop-shadow(0 0 2px #f59e0b)}50%{opacity:1;filter:drop-shadow(0 0 6px #fbbf24)}}
@keyframes wfBreath{0%,100%{transform:translateY(0)}50%{transform:translateY(-1.5px)}}
@keyframes wfSnarl{0%,100%{transform:translateY(0)}40%,60%{transform:translateY(1px)}}
.wfa-head{animation:wfBreath 3.5s ease-in-out infinite;transform-origin:center center}
.wfa-eyes{animation:wfBlink 5s ease-in-out infinite}
.wfa-glow{animation:wfGlow 2s ease-in-out infinite}
.wfa-mouth{animation:wfSnarl 4s ease-in-out infinite;transform-origin:50px 68px}
`

function injectCSS() {
  if (typeof document === 'undefined') return
  if (document.getElementById('wfa-css')) return
  const s = document.createElement('style')
  s.id = 'wfa-css'
  s.textContent = CSS
  document.head.appendChild(s)
}

export function WolfAnimation({ size = 48, className = '' }: { size?: number; className?: string }) {
  useEffect(() => { injectCSS() }, [])

  return (
    <svg
      viewBox="0 0 100 100"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      style={{ width: size, height: size, display: 'block', overflow: 'visible' }}
    >
      {/* ── Ear shadows ── */}
      <path d="M24 42 L14 8 L36 28Z" fill="#0a0a18"/>
      <path d="M76 42 L86 8 L64 28Z" fill="#0a0a18"/>

      {/* ── Main head group — breathes ── */}
      <g className="wfa-head">

        {/* Outer head */}
        <path
          d="M22 55 C16 48 14 38 18 28 C22 18 32 12 50 10 C68 12 78 18 82 28 C86 38 84 48 78 55 C74 60 66 64 60 66 L50 70 L40 66 C34 64 26 60 22 55Z"
          fill="#111827" stroke="#1f2937" strokeWidth="1"
        />

        {/* Left ear */}
        <path d="M24 42 L14 8 L36 28Z" fill="#111827" stroke="#f59e0b" strokeWidth="1"/>
        <path d="M24 40 L17 12 L34 29Z" fill="#4c1d95" opacity="0.7"/>

        {/* Right ear */}
        <path d="M76 42 L86 8 L64 28Z" fill="#111827" stroke="#f59e0b" strokeWidth="1"/>
        <path d="M76 40 L83 12 L66 29Z" fill="#4c1d95" opacity="0.7"/>

        {/* Forehead fur texture */}
        <path d="M34 22 Q42 17 50 16 Q58 17 66 22" stroke="#1f2937" strokeWidth="1.5" fill="none" strokeLinecap="round"/>
        <path d="M38 18 Q50 13 62 18" stroke="#1f2937" strokeWidth="1" fill="none" strokeLinecap="round"/>

        {/* ── Brow ridge — angry V shape ── */}
        <path d="M26 38 Q34 32 42 37" stroke="#f59e0b" strokeWidth="2" strokeLinecap="round" fill="none"/>
        <path d="M74 38 Q66 32 58 37" stroke="#f59e0b" strokeWidth="2" strokeLinecap="round" fill="none"/>

        {/* ── Eyes — glowing amber ── */}
        <g className="wfa-eyes">
          {/* Left eye socket */}
          <ellipse cx="35" cy="44" rx="8" ry="6.5" fill="#0a0a18" stroke="#f59e0b" strokeWidth="0.8"/>
          {/* Left iris */}
          <ellipse cx="35" cy="44" rx="6" ry="5" fill="#92400e"/>
          {/* Left pupil */}
          <ellipse cx="35" cy="44" rx="2.8" ry="4" fill="#000"/>
          {/* Left glow */}
          <ellipse cx="35" cy="44" rx="6" ry="5" fill="#f59e0b" opacity="0.2" className="wfa-glow"/>
          {/* Left highlight */}
          <circle cx="36.5" cy="42" r="1.2" fill="white" opacity="0.9"/>
          <circle cx="33.5" cy="45.5" r="0.6" fill="white" opacity="0.5"/>

          {/* Right eye socket */}
          <ellipse cx="65" cy="44" rx="8" ry="6.5" fill="#0a0a18" stroke="#f59e0b" strokeWidth="0.8"/>
          {/* Right iris */}
          <ellipse cx="65" cy="44" rx="6" ry="5" fill="#92400e"/>
          {/* Right pupil */}
          <ellipse cx="65" cy="44" rx="2.8" ry="4" fill="#000"/>
          {/* Right glow */}
          <ellipse cx="65" cy="44" rx="6" ry="5" fill="#f59e0b" opacity="0.2" className="wfa-glow"/>
          {/* Right highlight */}
          <circle cx="66.5" cy="42" r="1.2" fill="white" opacity="0.9"/>
          <circle cx="63.5" cy="45.5" r="0.6" fill="white" opacity="0.5"/>
        </g>

        {/* ── Nose bridge ── */}
        <path d="M47 50 L50 54 L53 50" stroke="#374151" strokeWidth="1.2" fill="none" strokeLinecap="round"/>

        {/* ── Nose ── */}
        <path d="M42 55 Q50 52 58 55 Q56 60 50 61 Q44 60 42 55Z" fill="#0f0f1e" stroke="#374151" strokeWidth="0.8"/>
        <path d="M45 56.5 Q50 54.5 55 56.5" stroke="#1f2937" strokeWidth="0.8" fill="none"/>
        {/* Nostrils */}
        <ellipse cx="46" cy="57" rx="2" ry="1.2" fill="#000" opacity="0.7"/>
        <ellipse cx="54" cy="57" rx="2" ry="1.2" fill="#000" opacity="0.7"/>

        {/* ── Mouth / snarl ── */}
        <g className="wfa-mouth">
          {/* Upper lip pulled back */}
          <path d="M36 64 Q43 60 50 60 Q57 60 64 64" stroke="#4b5563" strokeWidth="1.2" fill="none" strokeLinecap="round"/>
          {/* Mouth open */}
          <path d="M38 66 Q44 63 50 63 Q56 63 62 66 Q60 74 50 76 Q40 74 38 66Z" fill="#0a0010"/>
          {/* Teeth — upper */}
          <rect x="42" y="63.5" width="3" height="5" rx="0.8" fill="white" opacity="0.95"/>
          <rect x="46.5" y="63" width="3" height="5.5" rx="0.8" fill="white" opacity="0.95"/>
          <rect x="51" y="63" width="3" height="5.5" rx="0.8" fill="white" opacity="0.95"/>
          <rect x="55.5" y="63.5" width="3" height="5" rx="0.8" fill="white" opacity="0.95"/>
          {/* Fangs */}
          <path d="M38.5 64 L36 70 L40 64" fill="white" opacity="0.9"/>
          <path d="M61.5 64 L64 70 L60 64" fill="white" opacity="0.9"/>
          {/* Teeth — lower (glimpse) */}
          <rect x="44" y="72" width="2.5" height="3.5" rx="0.6" fill="#e5e7eb" opacity="0.7"/>
          <rect x="48" y="72.5" width="2.5" height="3" rx="0.6" fill="#e5e7eb" opacity="0.7"/>
          <rect x="52" y="72.5" width="2.5" height="3" rx="0.6" fill="#e5e7eb" opacity="0.7"/>
          {/* Tongue */}
          <path d="M44 71 Q50 78 56 71" fill="#dc2626" opacity="0.85" stroke="#b91c1c" strokeWidth="0.5"/>
          {/* Saliva hint */}
          <path d="M50 73 L50 77" stroke="#dc2626" strokeWidth="0.8" opacity="0.5" strokeLinecap="round"/>
        </g>

        {/* Cheek fur lines */}
        <path d="M18 50 Q24 52 29 56" stroke="#1f2937" strokeWidth="1.3" fill="none" strokeLinecap="round"/>
        <path d="M16 57 Q22 58 27 62" stroke="#1f2937" strokeWidth="1" fill="none" strokeLinecap="round" opacity="0.7"/>
        <path d="M82 50 Q76 52 71 56" stroke="#1f2937" strokeWidth="1.3" fill="none" strokeLinecap="round"/>
        <path d="M84 57 Q78 58 73 62" stroke="#1f2937" strokeWidth="1" fill="none" strokeLinecap="round" opacity="0.7"/>

        {/* Outer amber ring */}
        <ellipse cx="50" cy="42" rx="36" ry="34" fill="none" stroke="#f59e0b" strokeWidth="0.6" opacity="0.2" className="wfa-glow"/>
      </g>
    </svg>
  )
}
