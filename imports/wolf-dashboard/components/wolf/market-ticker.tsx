'use client'

import { useEffect, useState } from 'react'
import { TrendingUp, TrendingDown, RefreshCw, ArrowUpRight, ArrowDownRight } from 'lucide-react'
import type { MarketData, Trade } from '@/lib/wolf-types'

interface MarketTickerProps {
  data: MarketData[]
  trades?: Trade[]
}

interface LivePrice {
  symbol: string
  price: number
  change: number
  changePercent: number
  high: number
  low: number
  volume: number
}

// Wolf's active Polymarket prediction markets (matches VPS trades)
const WOLF_MARKETS = [
  { symbol: 'BTC >$100K', question: 'Will BTC exceed $100K before June?', side: 'YES', entry: 0.063, strategy: 'value_bet' },
  { symbol: 'Rihanna Album', question: 'New Rihanna Album before GTA VI?', side: 'NO', entry: 0.405, strategy: 'value_bet' },
  { symbol: 'Italy FIFA', question: 'Will Italy qualify for FIFA 2026?', side: 'NO', entry: 0.225, strategy: 'value_bet' },
  { symbol: 'Sweden FIFA', question: 'Will Sweden qualify for FIFA 2026?', side: 'NO', entry: 0.375, strategy: 'value_bet' },
  { symbol: 'Weinstein', question: 'Will Harvey Weinstein be sentenced?', side: 'YES', entry: 0.218, strategy: 'copy_trading' },
  { symbol: 'Fed Cut May', question: 'Will Fed cut rates in May 2026?', side: 'YES', entry: 0.38, strategy: 'copy_trading' },
]

export function MarketTicker({ data, trades = [] }: MarketTickerProps) {
  const [livePrices, setLivePrices] = useState<LivePrice[]>([])
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date())
  const [loading, setLoading] = useState(true)

  // Fetch real BTC/ETH from CoinGecko
  useEffect(() => {
    const fetchPrices = async () => {
      try {
        const res = await fetch(
          'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true&include_high_24h=true&include_low_24h=true',
          { cache: 'no-store' }
        )
        if (!res.ok) throw new Error('fetch failed')
        const json = await res.json()
        const btc = json.bitcoin
        const eth = json.ethereum

        const prices: LivePrice[] = [
          {
            symbol: 'BTC',
            price: btc?.usd ?? 0,
            change: (btc?.usd ?? 0) * (btc?.usd_24h_change ?? 0) / 100,
            changePercent: btc?.usd_24h_change ?? 0,
            volume: btc?.usd_24h_vol ?? 0,
            high: btc?.usd_24h_high ?? 0,
            low: btc?.usd_24h_low ?? 0,
          },
          {
            symbol: 'ETH',
            price: eth?.usd ?? 0,
            change: (eth?.usd ?? 0) * (eth?.usd_24h_change ?? 0) / 100,
            changePercent: eth?.usd_24h_change ?? 0,
            volume: eth?.usd_24h_vol ?? 0,
            high: eth?.usd_24h_high ?? 0,
            low: eth?.usd_24h_low ?? 0,
          },
        ]

        // Add any other live prices pushed by Wolf
        const wolfPrices = data.filter(d => !['BTC', 'ETH', 'POLY'].includes(d.symbol) && d.price > 0)
        wolfPrices.forEach(wp => {
          if (!prices.find(p => p.symbol === wp.symbol)) {
            prices.push({ symbol: wp.symbol, price: wp.price, change: wp.change, changePercent: wp.changePercent, volume: wp.volume ?? 0, high: wp.high ?? 0, low: wp.low ?? 0 })
          }
        })

        setLivePrices(prices)
        setLastUpdate(new Date())
        setLoading(false)
      } catch {
        // Fallback to whatever Wolf pushed (excluding POLY)
        const filtered = data.filter(d => d.symbol !== 'POLY' && d.price > 0)
        setLivePrices(filtered.map(d => ({ symbol: d.symbol, price: d.price, change: d.change, changePercent: d.changePercent, volume: d.volume ?? 0, high: d.high ?? 0, low: d.low ?? 0 })))
        setLoading(false)
      }
    }

    fetchPrices()
    const interval = setInterval(fetchPrices, 30000) // every 30s
    return () => clearInterval(interval)
  }, [data])

  // Get active trades from API or use WOLF_MARKETS as fallback
  const activeMarkets = trades.filter(t => t.status === 'OPEN').length > 0
    ? trades.filter(t => t.status === 'OPEN').slice(0, 6).map(t => ({
        symbol: t.symbol.length > 18 ? t.symbol.slice(0, 16) + '…' : t.symbol,
        question: t.symbol,
        side: t.type === 'LONG' ? 'YES' : 'NO',
        entry: t.entry,
        strategy: t.strategy,
      }))
    : WOLF_MARKETS

  const formatPrice = (p: number) => {
    if (p >= 10000) return p.toLocaleString('en-US', { maximumFractionDigits: 0 })
    if (p >= 1000) return p.toLocaleString('en-US', { maximumFractionDigits: 0 })
    if (p >= 1) return p.toFixed(2)
    return p.toFixed(3)
  }

  const formatVol = (v: number) => {
    if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`
    if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`
    if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`
    return null
  }

  const stratColor: Record<string, string> = {
    'value_bet': 'text-amber-400',
    'copy_trading': 'text-blue-400',
    'market_making': 'text-purple-400',
    'latency_arb': 'text-emerald-400',
  }

  return (
    <div className="space-y-3">
      {/* ── Crypto price strip ─────────────────────────────────────── */}
      <div className="flex items-center gap-3 overflow-x-auto pb-1 scrollbar-hide">
        {loading && (
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <RefreshCw className="h-3 w-3 animate-spin" />
            Fetching live prices...
          </div>
        )}
        {livePrices.map(lp => (
          <div
            key={lp.symbol}
            className="shrink-0 flex items-center gap-3 rounded-2xl bg-[#161624] border border-white/5 px-4 py-2.5 min-w-[180px]"
          >
            <div className="h-8 w-8 rounded-full bg-amber-500/10 flex items-center justify-center shrink-0">
              <span className="text-xs font-black text-amber-400">{lp.symbol[0]}</span>
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-black text-white">{lp.symbol}</span>
                <span className={`text-[10px] font-bold ${lp.changePercent >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {lp.changePercent >= 0 ? '▲' : '▼'}{Math.abs(lp.changePercent).toFixed(2)}%
                </span>
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-base font-black text-white font-mono">${formatPrice(lp.price)}</span>
              </div>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-[9px] text-zinc-600">H: ${formatPrice(lp.high)}</span>
                <span className="text-[9px] text-zinc-600">L: ${formatPrice(lp.low)}</span>
                {formatVol(lp.volume) && <span className="text-[9px] text-amber-500/60">{formatVol(lp.volume)}</span>}
              </div>
            </div>
            <div>
              {lp.changePercent >= 0
                ? <TrendingUp className="h-4 w-4 text-emerald-500" />
                : <TrendingDown className="h-4 w-4 text-red-500" />
              }
            </div>
          </div>
        ))}

        {/* Live indicator */}
        <div className="shrink-0 flex items-center gap-1.5 text-[10px] text-zinc-600 pl-2">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
          LIVE · {lastUpdate.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
        </div>
      </div>

      {/* ── Wolf's active prediction markets ───────────────────────── */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <span className="text-[10px] font-black text-zinc-500 uppercase tracking-widest">Wolf's Active Markets</span>
          <span className="h-1 w-1 rounded-full bg-amber-500 animate-pulse" />
          <span className="text-[10px] text-amber-500/70 font-bold">{activeMarkets.length} positions</span>
        </div>
        <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
          {activeMarkets.map((m, i) => (
            <div
              key={i}
              className="shrink-0 rounded-2xl bg-[#161624] border border-white/5 p-3 min-w-[200px] max-w-[220px]"
            >
              <div className="flex items-center gap-2 mb-2">
                <div className={`shrink-0 h-5 w-5 rounded-full flex items-center justify-center ${m.side === 'YES' ? 'bg-emerald-500/15' : 'bg-red-500/15'}`}>
                  {m.side === 'YES'
                    ? <ArrowUpRight className="h-3 w-3 text-emerald-400" />
                    : <ArrowDownRight className="h-3 w-3 text-red-400" />
                  }
                </div>
                <span className={`text-[10px] font-black ${m.side === 'YES' ? 'text-emerald-400' : 'text-red-400'}`}>{m.side}</span>
                <span className={`ml-auto text-[9px] font-bold ${stratColor[m.strategy] ?? 'text-zinc-500'}`}>
                  {m.strategy.replace('_', ' ')}
                </span>
              </div>
              <p className="text-[11px] font-bold text-white leading-tight line-clamp-2">{m.question}</p>
              <p className="text-[10px] text-zinc-500 mt-1.5 font-mono">@ ${m.entry.toFixed(3)}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
