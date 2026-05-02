'use client'

import { useState } from 'react'
import { ArrowUpRight, ArrowDownRight, TrendingUp, Target, Clock, DollarSign, Timer, AlertTriangle, Zap, Shield, X } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { WolfAnimation } from '@/components/wolf/wolf-animation'
import type { Trade } from '@/lib/wolf-types'

interface TradesTableProps {
  trades: Trade[]
  paperMode?: boolean
  onGoLive?: () => void
}

const MAX_HOLD_HOURS = 12

const getTradeMessage = (trade: Trade) => {
  if (trade.status !== 'CLOSED') return null
  if (trade.pnl >= 500) return '💰 Stratton approved'
  if (trade.pnl >= 100) return '📈 Wolf takes profit'
  if (trade.pnl >= 0)   return '🐺 Green'
  if (trade.pnl >= -100) return 'Minor scratch'
  return 'Part of the game'
}

const formatAge = (date: Date | string) => {
  const d = typeof date === 'string' ? new Date(date) : date
  if (isNaN(d.getTime())) return '—'
  const diff = Date.now() - d.getTime()
  const h = Math.floor(diff / 3600000)
  const m = Math.floor((diff % 3600000) / 60000)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

// Time until market expiry (marketEnd ms timestamp) — more useful than hold-time cap
const getExpiryRemaining = (marketEndMs: number) => {
  if (!marketEndMs || marketEndMs <= 0) return null
  const remaining = marketEndMs - Date.now()
  if (remaining <= 0) return { label: 'RESOLVED', urgency: 'critical' as const, pct: 100 }
  const days  = Math.floor(remaining / 86400000)
  const hours = Math.floor((remaining % 86400000) / 3600000)
  const mins  = Math.floor((remaining % 3600000) / 60000)
  // pct of a 14-day max window
  const pct = Math.min(100, Math.max(0, ((1 - remaining / (14 * 86400000)) * 100)))
  if (remaining < 3600000)   return { label: `${mins}m`, urgency: 'critical' as const, pct }
  if (remaining < 86400000)  return { label: `${hours}h ${mins}m`, urgency: 'warn' as const, pct }
  if (remaining < 3*86400000) return { label: `${days}d ${hours}h`, urgency: 'warn' as const, pct }
  return { label: `${days}d ${hours}h`, urgency: 'ok' as const, pct }
}

// Fallback: time remaining on 12h hold clock
const getHoldRemaining = (date: Date | string) => {
  const d = typeof date === 'string' ? new Date(date) : date
  if (isNaN(d.getTime())) return null
  const elapsedMs  = Date.now() - d.getTime()
  const maxMs      = MAX_HOLD_HOURS * 3600000
  const remainingMs = maxMs - elapsedMs
  const pct = Math.min(100, Math.max(0, (elapsedMs / maxMs) * 100))
  if (remainingMs <= 0) return { label: 'FORCE EXIT', urgency: 'critical' as const, pct: 100 }
  const rh = Math.floor(remainingMs / 3600000)
  const rm = Math.floor((remainingMs % 3600000) / 60000)
  if (remainingMs < 3600000)    return { label: `${rm}m`, urgency: 'critical' as const, pct }
  if (remainingMs < 3*3600000)  return { label: `${rh}h ${rm}m`, urgency: 'warn' as const, pct }
  return { label: `${rh}h ${rm}m`, urgency: 'ok' as const, pct }
}

const truncate = (s: string, n = 32) => s.length <= n ? s : s.slice(0, n - 1) + '…'

export function TradesTable({ trades, paperMode = true, onGoLive }: TradesTableProps) {
  const [showGoLiveModal, setShowGoLiveModal] = useState(false)

  const openTrades   = trades.filter(t => t.status === 'OPEN')
  const closedTrades = trades.filter(t => t.status === 'CLOSED')
  const totalPnL     = closedTrades.reduce((s, t) => s + (t.pnl || 0), 0)
  const wins         = closedTrades.filter(t => t.pnl >= 0).length
  const wr           = closedTrades.length > 0 ? Math.round(wins / closedTrades.length * 100) : null

  // Sort open trades: soonest market expiry first; unknown expiry goes to bottom of open group
  const sortedOpen = [...openTrades].sort((a, b) => {
    const aEnd = a.marketEnd ?? 0
    const bEnd = b.marketEnd ?? 0
    if (aEnd > 0 && bEnd > 0) return aEnd - bEnd          // both known: soonest first
    if (aEnd > 0) return -1                                 // a known, b unknown → a first
    if (bEnd > 0) return 1                                  // b known, a unknown → b first
    return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime() // both unknown: oldest first
  })

  // Closed: most recent first
  const sortedClosed = [...closedTrades].sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  )

  const allTrades = [...sortedOpen, ...sortedClosed]

  return (
    <Card className="rounded-2xl bg-[#161624] border border-white/5 h-full flex flex-col">
      <CardHeader className="pb-3 shrink-0">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <CardTitle className="text-base font-black flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-amber-500" />
            THE HUNT LOG
          </CardTitle>
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="outline" className="text-xs flex items-center gap-1 font-bold">
              <Target className="h-3 w-3 text-amber-400" />
              {openTrades.length} Active
            </Badge>
            {wr !== null && (
              <Badge className="text-xs bg-emerald-500/20 text-emerald-400 border-emerald-500/30 font-bold">
                WR {wr}%
              </Badge>
            )}
            {totalPnL !== 0 && (
              <Badge className={`text-xs font-bold ${totalPnL >= 0 ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' : 'bg-red-500/20 text-red-400 border-red-500/30'}`}>
                <DollarSign className="h-3 w-3 mr-0.5" />
                {totalPnL >= 0 ? '+' : ''}${totalPnL.toFixed(2)}
              </Badge>
            )}
            {paperMode ? (
              <button
                onClick={() => setShowGoLiveModal(true)}
                className="flex items-center gap-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 hover:bg-emerald-500/20 hover:border-emerald-500/60 active:scale-95 transition-all px-3 py-1.5 text-xs font-black text-emerald-400 tracking-wider"
              >
                <Zap className="h-3.5 w-3.5" />
                GO LIVE
              </button>
            ) : (
              <span className="flex items-center gap-1.5 rounded-lg bg-emerald-500/20 border border-emerald-500/50 px-3 py-1.5 text-xs font-black text-emerald-400 tracking-wider animate-pulse">
                <Zap className="h-3.5 w-3.5" />
                LIVE
              </span>
            )}
          </div>
        </div>
      </CardHeader>

      {/* Go Live modal */}
      {showGoLiveModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <div className="relative w-full max-w-md mx-4 rounded-2xl bg-[#0d0d1a] border border-emerald-500/30 shadow-2xl p-6">
            <button onClick={() => setShowGoLiveModal(false)} className="absolute top-4 right-4 text-zinc-600 hover:text-white transition-colors">
              <X className="h-5 w-5" />
            </button>
            <div className="flex justify-center mb-5">
              <div className="h-16 w-16 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center">
                <Zap className="h-8 w-8 text-emerald-400" />
              </div>
            </div>
            <h2 className="text-xl font-black text-white text-center mb-1">GO LIVE</h2>
            <p className="text-xs text-zinc-500 text-center mb-6">Switches Wolf to real trades with real money. No undo.</p>
            <div className="space-y-3 mb-6">
              <div className="flex items-start gap-3 rounded-xl bg-amber-500/5 border border-amber-500/20 p-3">
                <Shield className="h-4 w-4 text-amber-400 mt-0.5 shrink-0" />
                <div>
                  <p className="text-xs font-bold text-amber-400">Risk Acknowledgment</p>
                  <p className="text-[11px] text-zinc-500 mt-0.5">Kill switch armed at -40%. Ensure Polymarket wallet is funded.</p>
                </div>
              </div>
              <div className="flex items-start gap-3 rounded-xl bg-zinc-800/50 border border-white/5 p-3">
                <Zap className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <div>
                  <p className="text-xs font-bold text-white">What happens next</p>
                  <p className="text-[11px] text-zinc-500 mt-0.5">Wolf sets WOLF_PAPER_MODE=false and restarts. First live alert arrives on Telegram.</p>
                </div>
              </div>
            </div>
            <div className="flex gap-3">
              <button onClick={() => setShowGoLiveModal(false)} className="flex-1 rounded-xl bg-zinc-800 hover:bg-zinc-700 active:scale-95 transition-all py-3 text-sm font-bold text-zinc-400">
                Cancel
              </button>
              <button onClick={() => { setShowGoLiveModal(false); onGoLive?.() }} className="flex-1 rounded-xl bg-emerald-500 hover:bg-emerald-400 active:scale-95 transition-all py-3 text-sm font-black text-black tracking-wider">
                ACTIVATE
              </button>
            </div>
          </div>
        </div>
      )}

      <CardContent className="p-0 flex-1 min-h-0">
        {trades.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full py-16 gap-3">
            <WolfAnimation size={52} />
            <p className="text-sm font-bold text-muted-foreground">Wolf is scanning the markets…</p>
            <p className="text-xs text-muted-foreground italic">First positions loading</p>
          </div>
        ) : (
          <ScrollArea className="h-full max-h-[640px]">
            <Table>
              <TableHeader>
                <TableRow className="border-border hover:bg-transparent">
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold pl-4 min-w-[180px]">Market</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold">Side</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold">Entry</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold">Size</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold">Exit</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold text-right">P&L</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold">Conf</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold">Age</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold">Expires</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {allTrades.map((trade) => {
                  const isOpen    = trade.status === 'OPEN'
                  const isWin     = trade.status === 'CLOSED' && trade.pnl >= 0
                  const msg       = getTradeMessage(trade)
                  const confPct   = trade.confidence > 1 ? trade.confidence : Math.round(trade.confidence * 100)
                  const expiry    = isOpen ? getExpiryRemaining(trade.marketEnd ?? 0) : null
                  const holdLeft  = isOpen && !expiry ? getHoldRemaining(trade.timestamp) : null
                  const timeInfo  = expiry ?? holdLeft

                  return (
                    <TableRow
                      key={trade.id}
                      className={`border-border/50 transition-colors ${isOpen ? 'hover:bg-amber-500/[0.03]' : 'hover:bg-white/[0.015]'} ${isWin && trade.pnl >= 200 ? 'bg-emerald-500/[0.03]' : ''}`}
                    >
                      {/* Market */}
                      <TableCell className="pl-4 max-w-[180px]">
                        <div>
                          <span className="font-mono text-xs font-semibold text-white/90 block leading-snug">
                            {truncate(trade.symbol, 30)}
                          </span>
                          <div className="flex items-center gap-1 mt-0.5">
                            {isOpen
                              ? <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/25 text-[9px] font-bold px-1.5 py-0 h-4 animate-pulse">● OPEN</Badge>
                              : <Badge className="bg-zinc-700/60 text-zinc-400 border-zinc-600/30 text-[9px] px-1.5 py-0 h-4">{isWin ? '✓ WON' : '✗ LOST'}</Badge>
                            }
                            {trade.strategy && (
                              <span className="text-[9px] text-zinc-600 truncate max-w-[80px]">{trade.strategy.replace(/_/g,' ')}</span>
                            )}
                          </div>
                        </div>
                      </TableCell>

                      {/* Side */}
                      <TableCell>
                        {trade.type === 'LONG'
                          ? <span className="flex items-center gap-0.5 text-xs font-bold text-emerald-400"><ArrowUpRight className="h-3.5 w-3.5" />YES</span>
                          : <span className="flex items-center gap-0.5 text-xs font-bold text-red-400"><ArrowDownRight className="h-3.5 w-3.5" />NO</span>
                        }
                      </TableCell>

                      {/* Entry */}
                      <TableCell className="font-mono text-xs text-white/80">
                        ${trade.entry.toFixed(3)}
                      </TableCell>

                      {/* Size */}
                      <TableCell className="font-mono text-xs font-bold">
                        {trade.size != null && trade.size > 0
                          ? <span className="text-amber-400">${trade.size.toFixed(0)}</span>
                          : <span className="text-zinc-700">—</span>}
                      </TableCell>

                      {/* Exit */}
                      <TableCell className="font-mono text-xs">
                        {trade.exit
                          ? <span className={trade.exit >= trade.entry && trade.type === 'LONG' ? 'text-emerald-400 font-bold' : 'text-red-400 font-bold'}>${trade.exit.toFixed(3)}</span>
                          : <span className="text-zinc-600">—</span>}
                      </TableCell>

                      {/* P&L */}
                      <TableCell className="text-right">
                        {trade.status === 'CLOSED' ? (
                          <div>
                            <span className={`font-mono text-sm font-black ${trade.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                              {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}
                            </span>
                            {msg && <span className={`block text-[9px] italic ${isWin ? 'text-emerald-400/50' : 'text-red-400/50'}`}>{msg}</span>}
                          </div>
                        ) : trade.unrealizedPnl !== undefined ? (
                          <span className={`font-mono text-sm font-bold ${trade.unrealizedPnl >= 0 ? 'text-emerald-400/70' : 'text-red-400/70'}`}>
                            {trade.unrealizedPnl >= 0 ? '+' : ''}${trade.unrealizedPnl.toFixed(2)}
                          </span>
                        ) : (
                          <span className="text-zinc-600 text-xs">—</span>
                        )}
                      </TableCell>

                      {/* Confidence */}
                      <TableCell>
                        <div className="flex items-center gap-1.5">
                          <div className="h-1.5 w-9 overflow-hidden rounded-full bg-zinc-800">
                            <div
                              className={`h-full rounded-full ${confPct >= 80 ? 'bg-emerald-500' : confPct >= 70 ? 'bg-amber-500' : 'bg-orange-500'}`}
                              style={{ width: `${confPct}%` }}
                            />
                          </div>
                          <span className="text-[10px] text-zinc-500 font-mono">{confPct}%</span>
                        </div>
                      </TableCell>

                      {/* Age */}
                      <TableCell>
                        <div className="flex items-center gap-1 text-[10px] text-zinc-500">
                          <Clock className="h-3 w-3" />
                          {formatAge(trade.timestamp)}
                        </div>
                      </TableCell>

                      {/* Expiry */}
                      <TableCell>
                        {timeInfo ? (
                          <div className="min-w-[72px]">
                            <div className="flex items-center gap-1 mb-0.5">
                              {timeInfo.urgency === 'critical' && <AlertTriangle className="h-3 w-3 text-red-400 shrink-0" />}
                              {timeInfo.urgency === 'warn'     && <Timer className="h-3 w-3 text-amber-400 shrink-0" />}
                              <span className={`text-[10px] font-bold ${timeInfo.urgency === 'critical' ? 'text-red-400' : timeInfo.urgency === 'warn' ? 'text-amber-400' : 'text-zinc-400'}`}>
                                {timeInfo.label}
                              </span>
                            </div>
                            <div className="h-1 w-14 bg-zinc-800 rounded-full overflow-hidden">
                              <div
                                className={`h-full rounded-full transition-all ${timeInfo.urgency === 'critical' ? 'bg-red-500' : timeInfo.urgency === 'warn' ? 'bg-amber-500' : 'bg-zinc-500'}`}
                                style={{ width: `${timeInfo.pct}%` }}
                              />
                            </div>
                          </div>
                        ) : (
                          <span className="text-[10px] text-zinc-700">—</span>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  )
}
