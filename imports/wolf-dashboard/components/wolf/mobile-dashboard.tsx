'use client'

import React from 'react'
import { ArrowUpRight, ArrowDownRight, Activity, TrendingUp, Clock, ChevronRight, Zap, Target, DollarSign, Brain } from 'lucide-react'
import type { WolfStatus, Trade, ActivityLog, MarketData } from '@/lib/wolf-types'

interface MobileDashboardProps {
  wolfStatus: WolfStatus
  trades: Trade[]
  activityLogs: ActivityLog[]
  marketData: MarketData[]
  activeTab: string
  onTabChange: (tab: string) => void
}

// ─── Shared mobile card ───────────────────────────────────────────────────────
function MCard({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-2xl bg-[#161624] border border-white/5 p-4 ${className}`}>
      {children}
    </div>
  )
}

function MLabel({ children }: { children: React.ReactNode }) {
  return <p className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold mb-1">{children}</p>
}

// ─── Floor (Dashboard) tab ───────────────────────────────────────────────────
function MobileFloor({ wolfStatus, trades, activityLogs, marketData, onTabChange }: Omit<MobileDashboardProps, 'activeTab'>) {
  const openTrades = trades.filter(t => t.status === 'OPEN')
  const recentLogs = activityLogs.slice(0, 4)

  const formatCurrency = (v: number) => {
    const sign = v > 0 ? '+' : v < 0 ? '' : ''
    return `${sign}$${Math.abs(v).toFixed(2)}`
  }

  return (
    <div className="space-y-3">
      {/* Status hero */}
      <MCard className="bg-gradient-to-br from-amber-500/10 to-transparent border-amber-500/20">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className="relative">
              <span className="text-2xl">🐺</span>
              <span className="absolute -top-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-emerald-500 border-2 border-[#161624]" />
            </div>
            <div>
              <p className="text-sm font-black text-white tracking-wide">WOLF</p>
              <p className="text-[10px] text-amber-400 font-bold">HUNTING</p>
            </div>
          </div>
          <div className="text-right">
            <p className="text-xs text-zinc-500">Open Positions</p>
            <p className="text-2xl font-black text-white">{wolfStatus.openPositions}</p>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div className="rounded-xl bg-black/30 p-2.5 text-center">
            <MLabel>Daily</MLabel>
            <p className={`text-sm font-black ${wolfStatus.dailyPnL >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {formatCurrency(wolfStatus.dailyPnL)}
            </p>
          </div>
          <div className="rounded-xl bg-black/30 p-2.5 text-center">
            <MLabel>Win Rate</MLabel>
            <p className={`text-sm font-black ${wolfStatus.winRate >= 72 ? 'text-emerald-400' : wolfStatus.winRate === 0 ? 'text-zinc-500' : 'text-amber-400'}`}>
              {wolfStatus.winRate === 0 ? '—' : `${wolfStatus.winRate.toFixed(0)}%`}
            </p>
          </div>
          <div className="rounded-xl bg-black/30 p-2.5 text-center">
            <MLabel>Trades</MLabel>
            <p className="text-sm font-black text-white">{wolfStatus.totalTrades}</p>
          </div>
        </div>
      </MCard>

      {/* Live BTC/ETH strip */}
      {marketData.filter(m => m.price > 0).slice(0, 2).map(m => (
        <MCard key={m.symbol} className="py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="h-9 w-9 rounded-full bg-amber-500/10 flex items-center justify-center">
                <span className="text-sm font-black text-amber-400">{m.symbol[0]}</span>
              </div>
              <div>
                <p className="text-sm font-black text-white">{m.symbol}</p>
                <p className={`text-xs font-bold ${m.changePercent >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {m.changePercent >= 0 ? '▲' : '▼'} {Math.abs(m.changePercent).toFixed(2)}%
                </p>
              </div>
            </div>
            <p className="text-lg font-black text-white font-mono">
              ${m.price >= 1000 ? m.price.toLocaleString('en-US', { maximumFractionDigits: 0 }) : m.price.toFixed(2)}
            </p>
          </div>
        </MCard>
      ))}

      {/* Active positions preview */}
      {openTrades.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2 px-1">
            <p className="text-xs font-black text-white uppercase tracking-wider">Active Hunts</p>
            <span className="text-[10px] text-amber-400 font-bold">{openTrades.length} open</span>
          </div>
          <div className="space-y-2">
            {openTrades.slice(0, 3).map(trade => {
              const conf = trade.confidence > 1 ? trade.confidence : Math.round(trade.confidence * 100)
              return (
                <MCard key={trade.id} className="py-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <div className={`shrink-0 h-7 w-7 rounded-full flex items-center justify-center ${trade.type === 'LONG' ? 'bg-emerald-500/15' : 'bg-red-500/15'}`}>
                        {trade.type === 'LONG'
                          ? <ArrowUpRight className="h-3.5 w-3.5 text-emerald-400" />
                          : <ArrowDownRight className="h-3.5 w-3.5 text-red-400" />}
                      </div>
                      <div className="min-w-0">
                        <p className="text-xs font-bold text-white truncate">{trade.symbol.length > 28 ? trade.symbol.slice(0, 26) + '…' : trade.symbol}</p>
                        <p className="text-[10px] text-zinc-500">{trade.strategy} · {trade.type === 'LONG' ? 'YES' : 'NO'} @ ${trade.entry.toFixed(3)}</p>
                      </div>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className={`text-xs font-black ${conf >= 80 ? 'text-emerald-400' : 'text-amber-400'}`}>{conf}%</p>
                      <p className="text-[10px] text-zinc-600">conf</p>
                    </div>
                  </div>
                </MCard>
              )
            })}
            {openTrades.length > 3 && (
              <button
                onClick={() => onTabChange('trades')}
                className="w-full text-center text-xs text-amber-400/70 hover:text-amber-400 py-2 font-bold transition-colors active:scale-95"
              >
                +{openTrades.length - 3} more → tap to see all
              </button>
            )}
          </div>
        </div>
      )}

      {/* Activity feed preview */}
      {recentLogs.length > 0 && (
        <div>
          <p className="text-xs font-black text-white uppercase tracking-wider mb-2 px-1">Live Feed</p>
          <MCard className="py-2 divide-y divide-white/5">
            {recentLogs.map(log => (
              <div key={log.id} className="flex items-start gap-2 py-2">
                <div className={`mt-0.5 h-1.5 w-1.5 rounded-full shrink-0 ${
                  log.priority === 'CRITICAL' ? 'bg-red-500' :
                  log.priority === 'HIGH' ? 'bg-amber-500' :
                  'bg-zinc-600'
                }`} />
                <p className="text-xs text-zinc-400 leading-relaxed">{log.message}</p>
              </div>
            ))}
          </MCard>
        </div>
      )}
    </div>
  )
}

// ─── Hunts (Trades) tab ──────────────────────────────────────────────────────
function MobileHunts({ trades }: { trades: Trade[] }) {
  const open = trades.filter(t => t.status === 'OPEN')
  const closed = trades.filter(t => t.status === 'CLOSED')

  const formatAge = (d: Date | string) => {
    const date = typeof d === 'string' ? new Date(d) : d
    if (isNaN(date.getTime())) return '—'
    const diff = Date.now() - date.getTime()
    const h = Math.floor(diff / 3600000)
    const m = Math.floor((diff % 3600000) / 60000)
    return h > 0 ? `${h}h ${m}m` : `${m}m`
  }

  const TradeRow = ({ trade }: { trade: Trade }) => {
    const conf = trade.confidence > 1 ? trade.confidence : Math.round(trade.confidence * 100)
    const isOpen = trade.status === 'OPEN'
    return (
      <MCard className="py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
            <div className={`shrink-0 mt-0.5 h-8 w-8 rounded-xl flex items-center justify-center ${
              trade.type === 'LONG' ? 'bg-emerald-500/15' : 'bg-red-500/15'
            }`}>
              {trade.type === 'LONG'
                ? <ArrowUpRight className="h-4 w-4 text-emerald-400" />
                : <ArrowDownRight className="h-4 w-4 text-red-400" />}
            </div>
            <div className="min-w-0">
              <p className="text-xs font-bold text-white leading-snug line-clamp-2">{trade.symbol}</p>
              <div className="flex items-center gap-2 mt-1">
                <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-bold ${
                  isOpen ? 'bg-amber-500/20 text-amber-400' : 'bg-zinc-700 text-zinc-400'
                }`}>
                  {isOpen ? '🔴 Open' : 'Closed'}
                </span>
                <span className="text-[10px] text-zinc-600">{trade.strategy}</span>
              </div>
              <div className="flex items-center gap-3 mt-1.5">
                <span className="text-[10px] text-zinc-500">Entry <span className="text-white font-mono">${trade.entry.toFixed(3)}</span></span>
                {trade.exit && <span className="text-[10px] text-zinc-500">Exit <span className="text-white font-mono">${trade.exit.toFixed(3)}</span></span>}
              </div>
            </div>
          </div>
          <div className="shrink-0 text-right">
            {isOpen ? (
              <>
                <p className="text-xs font-black text-amber-400">{conf}%</p>
                <div className="flex items-center gap-1 mt-1 justify-end">
                  <Clock className="h-3 w-3 text-zinc-600" />
                  <span className="text-[10px] text-zinc-600">{formatAge(trade.timestamp)}</span>
                </div>
              </>
            ) : (
              <p className={`text-sm font-black ${trade.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}
              </p>
            )}
          </div>
        </div>
      </MCard>
    )
  }

  return (
    <div className="space-y-4">
      {open.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3 px-1">
            <Activity className="h-4 w-4 text-amber-400" />
            <p className="text-xs font-black text-white uppercase tracking-wider">Active Hunts</p>
            <span className="ml-auto text-[10px] bg-amber-500/20 text-amber-400 px-2 py-0.5 rounded-full font-bold">{open.length}</span>
          </div>
          <div className="space-y-2">{open.map(t => <TradeRow key={t.id} trade={t} />)}</div>
        </div>
      )}
      {closed.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3 px-1 mt-2">
            <TrendingUp className="h-4 w-4 text-zinc-500" />
            <p className="text-xs font-black text-zinc-500 uppercase tracking-wider">Closed</p>
            <span className="ml-auto text-[10px] bg-zinc-800 text-zinc-500 px-2 py-0.5 rounded-full font-bold">{closed.length}</span>
          </div>
          <div className="space-y-2">{closed.map(t => <TradeRow key={t.id} trade={t} />)}</div>
        </div>
      )}
      {trades.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <span className="text-5xl mb-4">🐺</span>
          <p className="text-sm font-bold text-zinc-400">Wolf is scanning the markets...</p>
          <p className="text-xs text-zinc-600 mt-1">First positions loading</p>
        </div>
      )}
    </div>
  )
}

// ─── Intel (Analytics) tab ───────────────────────────────────────────────────
function MobileIntel({ wolfStatus }: { wolfStatus: WolfStatus }) {
  const stats = [
    { label: 'Daily P&L', value: `${wolfStatus.dailyPnL >= 0 ? '+' : ''}$${Math.abs(wolfStatus.dailyPnL).toFixed(2)}`, color: wolfStatus.dailyPnL >= 0 ? 'text-emerald-400' : 'text-red-400', icon: DollarSign },
    { label: 'Weekly P&L', value: `${wolfStatus.weeklyPnL >= 0 ? '+' : ''}$${Math.abs(wolfStatus.weeklyPnL).toFixed(2)}`, color: wolfStatus.weeklyPnL >= 0 ? 'text-emerald-400' : 'text-red-400', icon: TrendingUp },
    { label: 'Win Rate', value: wolfStatus.winRate === 0 ? '—' : `${wolfStatus.winRate.toFixed(1)}%`, color: wolfStatus.winRate >= 72 ? 'text-emerald-400' : 'text-amber-400', icon: Target },
    { label: 'Total Trades', value: String(wolfStatus.totalTrades), color: 'text-white', icon: Activity },
    { label: 'Open Positions', value: String(wolfStatus.openPositions), color: 'text-amber-400', icon: Zap },
    { label: 'Learning', value: wolfStatus.learningProgress === 0 ? 'Pending' : `${wolfStatus.learningProgress}%`, color: 'text-blue-400', icon: Brain },
  ]

  return (
    <div className="space-y-3">
      <MCard className="bg-gradient-to-br from-amber-500/5 to-transparent border-amber-500/10">
        <MLabel>Win Rate Target</MLabel>
        <div className="flex items-center justify-between mb-2">
          <p className={`text-3xl font-black ${wolfStatus.winRate >= 72 ? 'text-emerald-400' : wolfStatus.winRate === 0 ? 'text-zinc-500' : 'text-amber-400'}`}>
            {wolfStatus.winRate === 0 ? '—' : `${wolfStatus.winRate.toFixed(1)}%`}
          </p>
          <p className="text-xs text-zinc-500">Target: 72%</p>
        </div>
        <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-700 ${wolfStatus.winRate >= 72 ? 'bg-emerald-500' : 'bg-amber-500'}`}
            style={{ width: `${Math.min(100, wolfStatus.winRate)}%` }}
          />
        </div>
        {wolfStatus.winRate >= 72 && (
          <p className="text-[10px] text-emerald-400 font-bold mt-2">🎯 Gate cleared — live mode eligible</p>
        )}
      </MCard>

      <div className="grid grid-cols-2 gap-3">
        {stats.map(s => {
          const Icon = s.icon
          return (
            <MCard key={s.label}>
              <div className="flex items-center gap-2 mb-2">
                <Icon className="h-3.5 w-3.5 text-zinc-600" />
                <MLabel>{s.label}</MLabel>
              </div>
              <p className={`text-xl font-black ${s.color}`}>{s.value}</p>
            </MCard>
          )
        })}
      </div>

      {/* Risk parameters */}
      <div>
        <p className="text-xs font-black text-white uppercase tracking-wider mb-2 px-1">Risk Desk</p>
        <div className="space-y-2">
          {[
            { label: 'Kill Switch', value: '-40%', sub: 'Max drawdown before halt', color: 'text-red-400' },
            { label: 'Position Cap', value: '$200', sub: 'Max per trade (paper)', color: 'text-amber-400' },
            { label: 'Force Exit', value: '12h', sub: 'Max hold time', color: 'text-blue-400' },
            { label: 'Min Confidence', value: '70%', sub: 'Entry gate threshold', color: 'text-purple-400' },
          ].map(r => (
            <MCard key={r.label} className="py-3">
              <div className="flex items-center justify-between">
                <div>
                  <MLabel>{r.label}</MLabel>
                  <p className="text-[10px] text-zinc-600">{r.sub}</p>
                </div>
                <p className={`text-xl font-black ${r.color}`}>{r.value}</p>
              </div>
            </MCard>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Ledger (History) tab ────────────────────────────────────────────────────
function MobileLedger({ trades, wolfStatus }: { trades: Trade[]; wolfStatus: WolfStatus }) {
  const closed = trades.filter(t => t.status === 'CLOSED')
  const wins = closed.filter(t => t.pnl >= 0)
  const losses = closed.filter(t => t.pnl < 0)
  const totalPnl = closed.reduce((s, t) => s + t.pnl, 0)

  return (
    <div className="space-y-3">
      {closed.length > 0 && (
        <MCard className="bg-gradient-to-br from-emerald-500/5 to-transparent">
          <div className="grid grid-cols-3 gap-3 text-center">
            <div>
              <MLabel>Closed</MLabel>
              <p className="text-xl font-black text-white">{closed.length}</p>
            </div>
            <div>
              <MLabel>Realized P&L</MLabel>
              <p className={`text-xl font-black ${totalPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}
              </p>
            </div>
            <div>
              <MLabel>W / L</MLabel>
              <p className="text-xl font-black text-white"><span className="text-emerald-400">{wins.length}</span> / <span className="text-red-400">{losses.length}</span></p>
            </div>
          </div>
        </MCard>
      )}

      {closed.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <span className="text-5xl mb-4">📖</span>
          <p className="text-sm font-bold text-zinc-400">No closed trades yet</p>
          <p className="text-xs text-zinc-600 mt-1">First resolution expected ~21:30 EDT</p>
        </div>
      ) : (
        <div className="space-y-2">
          {closed.map(trade => (
            <MCard key={trade.id} className="py-3">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-xs font-bold text-white truncate">{trade.symbol.length > 30 ? trade.symbol.slice(0, 28) + '…' : trade.symbol}</p>
                  <p className="text-[10px] text-zinc-500 mt-0.5">{trade.strategy} · {trade.type === 'LONG' ? 'YES' : 'NO'} · ${trade.entry.toFixed(3)} → ${trade.exit?.toFixed(3) ?? '—'}</p>
                </div>
                <p className={`shrink-0 text-sm font-black ${trade.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}
                </p>
              </div>
            </MCard>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Config tab ──────────────────────────────────────────────────────────────
function MobileConfig() {
  return (
    <div className="space-y-3">
      <MCard className="bg-gradient-to-br from-amber-500/10 to-transparent border-amber-500/20">
        <div className="flex items-center gap-3 mb-3">
          <span className="text-3xl">🐺</span>
          <div>
            <p className="text-sm font-black text-white">Wolf of All Streets</p>
            <p className="text-xs text-amber-400">v2.5 · Paper Mode</p>
          </div>
        </div>
        <p className="text-xs text-zinc-500 italic">&quot;The hunt never stops.&quot;</p>
      </MCard>

      {[
        { label: 'Live Mode', value: 'Disabled', sub: 'Paper trading active', color: 'text-zinc-400' },
        { label: 'Polymarket', value: 'Connected', sub: 'API authenticated', color: 'text-emerald-400' },
        { label: 'Binance US', value: 'REST ✅', sub: 'Price feed active', color: 'text-emerald-400' },
        { label: 'Kalshi', value: 'Pending', sub: 'Account required', color: 'text-zinc-500' },
        { label: 'Dashboard API', value: 'Live', sub: 'wolfofallstreets.xyz', color: 'text-emerald-400' },
        { label: 'Telegram Alerts', value: 'Active', sub: 'Entry + exit alerts', color: 'text-blue-400' },
      ].map(item => (
        <MCard key={item.label} className="py-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-bold text-white">{item.label}</p>
              <p className="text-[10px] text-zinc-600 mt-0.5">{item.sub}</p>
            </div>
            <p className={`text-xs font-black ${item.color}`}>{item.value}</p>
          </div>
        </MCard>
      ))}

      <MCard>
        <MLabel>API Endpoints</MLabel>
        <div className="space-y-1 mt-2">
          {['POST /api/wolf/status', 'POST /api/wolf/trades', 'POST /api/wolf/performance', 'GET /api/wolf/state'].map(e => (
            <p key={e} className="text-[10px] font-mono text-zinc-500">{e}</p>
          ))}
        </div>
      </MCard>
    </div>
  )
}

// ─── Mobile Guardian ─────────────────────────────────────────────────────────
function MobileGuardian() {
  const [data, setData] = React.useState<{scan_count:number,healthy:boolean,error_count:number,errors:Array<{name:string,severity:string,description:string}>,last_scan_age_s:number|null}|null>(null)
  const [loading, setLoading] = React.useState(true)

  React.useEffect(() => {
    fetch('/api/wolf/guardian')
      .then(r => r.json())
      .then(d => { setData(d.data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const ageLabel = (s: number | null) => {
    if (s === null) return 'never'
    if (s < 60) return `${s}s ago`
    if (s < 3600) return `${Math.round(s/60)}m ago`
    return `${Math.round(s/3600)}h ago`
  }

  return (
    <div className="space-y-3">
      <MCard className={`border ${!data ? 'border-zinc-700' : data.healthy && data.error_count === 0 ? 'border-emerald-500/30' : !data.healthy ? 'border-red-500/40' : 'border-amber-500/30'}`}>
        <div className="flex items-center gap-3">
          <span className="text-3xl">{loading ? '⏳' : !data ? '❓' : data.healthy && data.error_count === 0 ? '✅' : !data.healthy ? '🚨' : '⚠️'}</span>
          <div className="flex-1">
            <p className="text-sm font-black text-white">
              {loading ? 'Loading…' : !data ? 'No data' : data.healthy && data.error_count === 0 ? 'CLEAN — Wolf running healthy' : `${data.error_count} issue(s) detected`}
            </p>
            <p className="text-[10px] text-zinc-500 mt-0.5">
              {data ? `Scan #${data.scan_count} · ${ageLabel(data.last_scan_age_s)}` : 'Waiting for Guardian push…'}
            </p>
          </div>
        </div>
      </MCard>

      {data?.errors && data.errors.length > 0 && data.errors.map((e, i) => (
        <MCard key={i} className={`border-l-4 ${e.severity === 'CRITICAL' || e.severity === 'HIGH' ? 'border-l-red-500' : 'border-l-amber-500'}`}>
          <p className="text-xs font-bold text-red-400">[{e.severity}] {e.name}</p>
          <p className="text-[10px] text-zinc-500 mt-1">{e.description}</p>
        </MCard>
      ))}

      <MCard>
        <MLabel>Guardian Status</MLabel>
        <div className="space-y-1 mt-2 text-[10px] text-zinc-500">
          <p>Scans wolf.log every 5 minutes</p>
          <p>Checks DB integrity each scan</p>
          <p>Auto-fixes slug cache + DB retries</p>
          <p>Pushes results to this dashboard</p>
        </div>
      </MCard>
    </div>
  )
}

// ─── Root export ─────────────────────────────────────────────────────────────
export function MobileDashboard({ wolfStatus, trades, activityLogs, marketData, activeTab, onTabChange }: MobileDashboardProps) {
  const tabTitles: Record<string, { title: string; sub: string }> = {
    dashboard: { title: 'The Floor', sub: 'Mission Control' },
    trades:    { title: 'Hunt Log', sub: 'Active Positions' },
    analytics: { title: 'Intel', sub: 'Performance & Risk' },
    history:   { title: 'Ledger', sub: 'Closed Trades' },
    guardian:  { title: 'Guardian', sub: 'Error Monitor' },
    settings:  { title: 'Configure', sub: 'System Settings' },
  }
  const { title, sub } = tabTitles[activeTab] ?? { title: 'Wolf', sub: '' }

  return (
    <div className="flex flex-col min-h-full">
      {/* Page title */}
      <div className="px-4 pt-3 pb-2">
        <h1 className="text-lg font-black text-white tracking-tight">{title}</h1>
        <p className="text-[11px] text-zinc-600">{sub}</p>
      </div>

      {/* Content */}
      <div className="flex-1 px-4 pb-6">
        {activeTab === 'dashboard' && (
          <MobileFloor wolfStatus={wolfStatus} trades={trades} activityLogs={activityLogs} marketData={marketData} onTabChange={onTabChange} />
        )}
        {activeTab === 'trades' && <MobileHunts trades={trades} />}
        {activeTab === 'analytics' && <MobileIntel wolfStatus={wolfStatus} />}
        {activeTab === 'history' && <MobileLedger trades={trades} wolfStatus={wolfStatus} />}
        {activeTab === 'guardian' && <MobileGuardian />}
        {activeTab === 'settings' && <MobileConfig />}
      </div>
    </div>
  )
}
