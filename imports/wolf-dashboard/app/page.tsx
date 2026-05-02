'use client'

import { useState, useEffect, useCallback } from 'react'
import useSWR from 'swr'
import { Header } from '@/components/wolf/header'
import { MobileNav } from '@/components/wolf/mobile-nav'
import { MobileDashboard } from '@/components/wolf/mobile-dashboard'
import { Sidebar } from '@/components/wolf/sidebar'
import { StatsCards } from '@/components/wolf/stats-cards'
import { PnLChart } from '@/components/wolf/pnl-chart'
import { DdubIndexChart } from '@/components/wolf/ddub-index-chart'
import { TradesTable } from '@/components/wolf/trades-table'
import { ActivityFeed } from '@/components/wolf/activity-feed'
import { MarketTicker } from '@/components/wolf/market-ticker'
import { BelfortSoundboard } from '@/components/wolf/belfort-soundboard'
import { SiteLock } from '@/components/wolf/site-lock'
import { LearningPanel } from '@/components/wolf/learning-panel'
import { EvolutionPanel } from '@/components/wolf/evolution-panel'
import { ConfigLock } from '@/components/wolf/config-lock'
import { Achievements } from '@/components/wolf/achievements'
import { StreakCounter } from '@/components/wolf/streak-counter'
import { BelfortQuotes } from '@/components/wolf/belfort-quotes'
import { TraderRank } from '@/components/wolf/trader-rank'
import { IntroAudio } from '@/components/wolf/intro-audio'
import { Confetti } from '@/components/wolf/confetti'
import { 
  generatePnLData, 
  generateDdubData, 
  generateTrades, 
  getWolfStatus, 
  generateActivityLogs,
  getMarketData 
} from '@/lib/mock-data'
import type { PnLDataPoint, DdubIndexData, Trade, WolfStatus, ActivityLog, MarketData } from '@/lib/wolf-types'

// API fetcher
const fetcher = (url: string) => fetch(url).then(res => res.json())

// ── Guardian Tab ─────────────────────────────────────────────────────────────
function GuardianTab() {
  const { data, mutate, isLoading } = useSWR('/api/wolf/guardian', fetcher, { refreshInterval: 30000 })
  const g = data?.data

  const sevColor: Record<string, string> = {
    CRITICAL: '#f87171', HIGH: '#f87171', MEDIUM: '#fbbf24', LOW: '#94a3b8'
  }

  const ageLabel = (s: number | null) => {
    if (s === null) return 'never'
    if (s < 60) return `${s}s ago`
    if (s < 3600) return `${Math.round(s / 60)}m ago`
    return `${Math.round(s / 3600)}h ago`
  }

  const stale = g?.stale === true

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-black text-foreground tracking-tight">🛡️ GUARDIAN — Error Monitor</h2>
        <p className="text-sm text-amber-400/80 italic">&quot;Scanning every 5 minutes. Every issue caught before it costs money.&quot;</p>
      </div>

      {/* Status card */}
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-4 mb-4">
          <span className="text-4xl">
            {isLoading ? '⏳' : stale ? '🔄' : !g ? '❓' : g.healthy && g.error_count === 0 ? '✅' : !g.healthy ? '🚨' : '⚠️'}
          </span>
          <div className="flex-1">
            <div className="text-lg font-black" style={{
              color: isLoading ? '#556070' : stale ? '#60a5fa' : !g ? '#556070' : g.healthy && g.error_count === 0 ? '#4ade80' : !g.healthy ? '#f87171' : '#fbbf24'
            }}>
              {isLoading ? 'Loading…' : stale ? 'Reconnecting to Wolf — next push in ~60s' : !g ? 'No data yet' : g.healthy && g.error_count === 0 ? 'CLEAN — No active issues' : !g.healthy ? `${g.error_count} CRITICAL/HIGH issue(s) detected` : `${g.error_count} warning(s) — no critical issues`}
            </div>
            <div className="text-xs text-zinc-500 mt-1">
              {stale ? 'Server restarted — Guardian state will reload on next Wolf push' : g ? `Scan #${g.scan_count} · last scan ${ageLabel(g.last_scan_age_s)} · auto-refresh every 30s` : 'Waiting for first Guardian push from VPS…'}
            </div>
          </div>
          <button
            onClick={() => mutate()}
            className="rounded-lg bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 px-4 py-2 text-xs text-blue-400 font-bold transition-colors"
          >
            ↻ Refresh
          </button>
        </div>

        {/* Issues list */}
        {g?.errors && g.errors.length > 0 ? (
          <div className="space-y-2 mt-4">
            {g.errors.map((e: any, i: number) => (
              <div key={i} className="rounded-lg bg-zinc-900 border-l-4 p-3" style={{ borderLeftColor: sevColor[e.severity] ?? '#556070' }}>
                <div className="text-sm font-bold" style={{ color: sevColor[e.severity] ?? '#556070' }}>
                  [{e.severity}] {e.name}
                </div>
                <div className="text-xs text-zinc-400 mt-1">{e.description}</div>
                {e.sample && <div className="text-xs text-zinc-600 font-mono mt-1 truncate">{e.sample}</div>}
              </div>
            ))}
          </div>
        ) : g && (
          <div className="text-sm text-emerald-600/70 mt-2">No active issues. Wolf is running clean.</div>
        )}
      </div>

      {/* Info card */}
      <div className="rounded-xl border border-border bg-card p-5 text-sm text-zinc-500 space-y-2">
        <div className="font-bold text-zinc-400">How Guardian works</div>
        <div>• Runs inside Wolf on the VPS — scans the live log every 5 minutes</div>
        <div>• Checks DB integrity: win rates, void trades, duplicate entries</div>
        <div>• Auto-fixes what it can (slug cache reload, DB retries)</div>
        <div>• Pushes status here via webhook every scan</div>
        <div>• Only alerts on issues <strong>from this boot forward</strong> — no false positives from old logs</div>
      </div>
    </div>
  )
}

export default function WolfMissionControl() {
  const [activeTab, setActiveTab] = useState('dashboard')
  const [isConnected, setIsConnected] = useState(true)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)
  const [soundEnabled, setSoundEnabled] = useState(() => {
    if (typeof window === 'undefined') return false
    return localStorage.getItem('wolf_sound_enabled') === 'true'
  })
  const [showConfetti, setShowConfetti] = useState(false)
  const [mounted, setMounted] = useState(false)
  const [useApiData, setUseApiData] = useState(true)
  
  // Gamification state
  const [winStreak, setWinStreak] = useState(0)
  const [bestStreak, setBestStreak] = useState(0)
  const [totalProfit, setTotalProfit] = useState(0)
  
  // Mock data state (fallback) - initialize empty to avoid hydration mismatch
  const [mockPnlData, setMockPnlData] = useState<PnLDataPoint[]>([])
  const [mockDdubData, setMockDdubData] = useState<DdubIndexData[]>([])
  const [mockTrades, setMockTrades] = useState<Trade[]>([])
  const [mockWolfStatus, setMockWolfStatus] = useState<WolfStatus>({
    status: 'ACTIVE',
    winRate: 0,
    totalTrades: 0,
    dailyPnL: 0,
    weeklyPnL: 0,
    monthlyPnL: 0,
    learningProgress: 0,
    lastActivity: null,
    openPositions: 0,
    riskLevel: 'MEDIUM',
    balance: 100,
    paperMode: true,
  })
  const [mockActivityLogs, setMockActivityLogs] = useState<ActivityLog[]>([])
  const [mockMarketData, setMockMarketData] = useState<MarketData[]>([])

  // SWR hooks for API data with auto-refresh
  const { data: apiState, mutate: refreshApiState } = useSWR(
    useApiData ? '/api/wolf/state' : null,
    fetcher,
    { refreshInterval: 15000 }
  )

  // Derived state from API or mock data
  const pnlData = useApiData && apiState?.data?.pnlData?.length > 0 
    ? apiState.data.pnlData.map((p: { date: string; pnl: number; cumulative: number; trades: number }) => ({
        date: p.date,
        pnl: p.pnl,
        cumulative: p.cumulative,
        trades: p.trades
      }))
    : (useApiData ? [] : mockPnlData)

  const ddubData = useApiData && apiState?.data?.ddubData?.length > 0
    ? apiState.data.ddubData.map((d: { time: string; value: number; signal: string }) => ({
        timestamp: d.time,
        value: d.value,
        signal: d.signal,
        strength: Math.round((Math.abs(d.value - 50) / 25) * 100)
      }))
    : (useApiData ? [] : mockDdubData)

  const trades: Trade[] = useApiData && apiState?.data?.trades?.length > 0
    ? apiState.data.trades.map((t: { id: string; symbol: string; side: string; entryPrice: number; exitPrice?: number; quantity: number; status: string; pnl?: number; pnlPercent?: number; entryTime: string | number; exitTime?: string | number; strategy?: string; confidence?: number; marketEnd?: number }) => ({
        id: t.id,
        symbol: t.symbol,
        // Normalize side: YES→LONG, NO→SHORT, LONG/SHORT pass through
        type: (t.side === 'YES' || t.side === 'LONG') ? 'LONG' as const : 'SHORT' as const,
        entry: t.entryPrice ?? 0,
        exit: t.exitPrice && t.exitPrice > 0 ? t.exitPrice : null,
        // Normalize status: open→OPEN, won/lost/closed→CLOSED
        status: (['OPEN','open'].includes(t.status) ? 'OPEN' : ['CLOSED','won','lost','closed'].includes(t.status) ? 'CLOSED' : 'PENDING') as 'OPEN' | 'CLOSED' | 'PENDING',
        pnl: t.pnl ?? 0,
        // Normalize timestamp: epoch ms number → Date, ISO string → Date
        timestamp: typeof t.entryTime === 'number' ? new Date(t.entryTime) : t.entryTime ? new Date(t.entryTime) : new Date(),
        confidence: t.confidence ?? 0.75,
        strategy: t.strategy ?? 'unknown',
        size: t.quantity ?? undefined,
        marketEnd: t.marketEnd ?? 0,
      }))
    : (useApiData ? [] : mockTrades)

  const wolfStatus: WolfStatus = useApiData && apiState?.data?.status
    ? {
        // Normalize Wolf status strings to WolfStatus enum
        status: (['hunting','online','active'].includes(apiState.data.status.status) ? 'ACTIVE'
                 : ['learning'].includes(apiState.data.status.status) ? 'LEARNING'
                 : ['error','crash'].includes(apiState.data.status.status) ? 'ERROR'
                 : 'IDLE') as 'ACTIVE' | 'IDLE' | 'LEARNING' | 'ERROR',
        winRate: apiState.data.performance?.winRate > 0 ? apiState.data.performance.winRate : (wolfStatus?.winRate ?? 0),
        totalTrades: apiState.data.performance?.totalTrades > 0 ? apiState.data.performance.totalTrades : (wolfStatus?.totalTrades ?? 0),
        dailyPnL: apiState.data.performance?.dailyPnl ?? 0,
        weeklyPnL: apiState.data.performance?.weeklyPnl ?? 0,
        monthlyPnL: apiState.data.performance?.monthlyPnl ?? 0,
        learningProgress: apiState.data.learning?.progress ?? 0,
        lastActivity: apiState.data.lastUpdated ? new Date(apiState.data.lastUpdated) : null,
        openPositions: (apiState.data.trades ?? []).filter((t: {status: string}) => t.status === 'OPEN' || t.status === 'open').length,
        riskLevel: 'MEDIUM' as const,
        balance: apiState.data.performance?.balance ?? undefined,
        paperMode: apiState.data.performance?.paperMode ?? true,
      }
    : mockWolfStatus

  const activityLogs: ActivityLog[] = useApiData && apiState?.data?.activityLogs?.length > 0
    ? apiState.data.activityLogs.map((l: { id: string; type: string; message: string; timestamp: string; priority: string }) => ({
        id: l.id,
        type: (l.type || 'SYSTEM').toUpperCase() as ActivityLog['type'],
        message: l.message,
        timestamp: l.timestamp,
        priority: (l.priority || 'medium').toUpperCase() as ActivityLog['priority'],
      }))
    : (useApiData ? [] : mockActivityLogs)

  const marketData: MarketData[] = useApiData && apiState?.data?.marketData?.length > 0
    ? apiState.data.marketData.map((m: { symbol: string; price: number; change: number; changePercent: number; volume?: number; high?: number; low?: number }) => ({
        symbol: m.symbol,
        price: m.price ?? 0,
        change: m.change ?? 0,
        changePercent: m.changePercent ?? 0,
        volume: m.volume ?? 0,
        high: m.high ?? m.price ?? 0,
        low: m.low ?? m.price ?? 0,
      }))
    : mockMarketData

  // Update gamification from API
  useEffect(() => {
    if (useApiData && apiState?.data?.performance) {
      const perf = apiState.data.performance
      // Only update if new value is non-zero to prevent cold-start store from zeroing display
      if (perf.winStreak > 0 || perf.bestStreak > 0) setWinStreak(perf.winStreak ?? winStreak)
      if (perf.bestStreak > 0) setBestStreak(perf.bestStreak ?? bestStreak)
      if ((perf.totalProfit ?? 0) !== 0) setTotalProfit(perf.totalProfit ?? totalProfit)
    }
  }, [apiState, useApiData, winStreak, bestStreak, totalProfit])

  // Track mounted state to avoid hydration mismatches
  useEffect(() => {
    setMounted(true)
    setLastRefresh(new Date())
  }, [])

  // Initialize mock data
  useEffect(() => {
    setMockPnlData(generatePnLData())
    setMockDdubData(generateDdubData())
    setMockTrades(generateTrades())
    setMockWolfStatus(getWolfStatus())
    setMockActivityLogs(generateActivityLogs())
    setMockMarketData(getMarketData())
  }, [])

  // Check API connection status
  useEffect(() => {
    if (useApiData) {
      setIsConnected(!!apiState?.success)
    }
  }, [apiState, useApiData])

  // Simulate live updates for mock data only
  useEffect(() => {
    if (useApiData) return // Skip mock updates when using API

    const interval = setInterval(() => {
      // Update market data with slight variations
      setMockMarketData(prev => prev.map(m => ({
        ...m,
        price: m.price + (Math.random() - 0.5) * 2,
        change: m.change + (Math.random() - 0.5) * 0.1,
        changePercent: m.changePercent + (Math.random() - 0.5) * 0.05,
      })))
      
      // Occasionally update D-Dub index
      if (Math.random() > 0.7) {
        setMockDdubData(prev => {
          const newData = [...prev.slice(1)]
          const lastValue = newData[newData.length - 1]?.value ?? 55
          const newValue = Math.max(35, Math.min(75, lastValue + (Math.random() - 0.5) * 5))
          const signal: 'BUY' | 'SELL' | 'HOLD' = newValue > 65 ? 'BUY' : newValue < 45 ? 'SELL' : 'HOLD'
          newData.push({
            timestamp: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
            value: Math.round(newValue * 100) / 100,
            signal,
            strength: Math.round((Math.abs(newValue - 50) / 25) * 100)
          })
          return newData
        })
      }

      // Simulate occasional wins (for demo purposes)
      if (Math.random() > 0.95) {
        setWinStreak(prev => {
          const newStreak = prev + 1
          if (newStreak > bestStreak) {
            setBestStreak(newStreak)
            setShowConfetti(true)
          }
          return newStreak
        })
        setTotalProfit(prev => prev + Math.random() * 500)
      }
    }, 3000)

    return () => clearInterval(interval)
  }, [bestStreak, useApiData])

  const handleRefresh = useCallback(() => {
    if (useApiData) {
      refreshApiState()
    } else {
      setMockPnlData(generatePnLData())
      setMockDdubData(generateDdubData())
      setMockTrades(generateTrades())
      setMockWolfStatus(getWolfStatus())
      setMockActivityLogs(generateActivityLogs())
      setMockMarketData(getMarketData())
    }
    setLastRefresh(new Date())
  }, [useApiData, refreshApiState])

  const handleToggleSound = useCallback(() => {
    setSoundEnabled(prev => {
      const next = !prev
      if (typeof window !== 'undefined') localStorage.setItem('wolf_sound_enabled', String(next))
      return next
    })
  }, [])

  const handleGoLive = useCallback(async () => {
    // POST to Wolf VPS webhook to flip PAPER_MODE=false and restart
    try {
      await fetch('/api/wolf/go-live', { method: 'POST' })
    } catch { /* best effort */ }
  }, [])

  // Trigger celebration for big wins
  const triggerCelebration = useCallback(() => {
    setShowConfetti(true)
  }, [])

  const toggleDataSource = useCallback(() => {
    setUseApiData(prev => !prev)
    setLastRefresh(new Date())
  }, [])

  return (
    <SiteLock>
    <div className="flex h-screen flex-col bg-background">
      {/* Confetti overlay */}
      <Confetti active={showConfetti} duration={4000} />
      
      {/* Header */}
      {/* Global audio engine — invisible, auto-starts on first interaction */}
      <IntroAudio soundEnabled={soundEnabled} />
      <Header 
        wolfStatus={wolfStatus} 
        onRefresh={handleRefresh} 
        isConnected={isConnected}
      />

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <Sidebar activeTab={activeTab} onTabChange={setActiveTab} />

        {/* Main Content */}
        <main className="flex-1 overflow-y-auto pb-20 lg:pb-6">
          {/* ── Mobile view (< lg) — clean native mobile layout ── */}
          <div className="lg:hidden">
            <MobileDashboard
              wolfStatus={wolfStatus}
              trades={trades}
              activityLogs={activityLogs}
              marketData={marketData}
              activeTab={activeTab}
              onTabChange={setActiveTab}
            />
          </div>

          {/* ── Desktop view (≥ lg) — full dashboard ── */}
          <div className="hidden lg:block p-6">
          {activeTab === 'dashboard' && (
            <div className="space-y-4 lg:space-y-6">
              {/* Top row: Market Ticker + Belfort Soundboard */}
              <div className="grid gap-4 lg:grid-cols-3">
                <div className="lg:col-span-2">
                  <MarketTicker data={marketData} trades={trades} />
                </div>
                <BelfortSoundboard />
              </div>

              {/* Motivational Quote */}
              <BelfortQuotes />

              {/* Stats Cards */}
              <StatsCards wolfStatus={wolfStatus} />

              {/* Gamification Row */}
              <div className="grid gap-6 lg:grid-cols-3">
                <StreakCounter 
                  currentStreak={winStreak} 
                  bestStreak={bestStreak}
                  lastTradeWin={true}
                />
                <div className="lg:col-span-2">
                  <Achievements 
                    winStreak={winStreak}
                    totalProfit={totalProfit}
                    winRate={wolfStatus.winRate}
                  />
                </div>
              </div>

              {/* Charts Row */}
              <div className="grid gap-6 lg:grid-cols-2">
                <PnLChart data={pnlData} />
                <DdubIndexChart data={ddubData} />
              </div>

              {/* Bottom Row — TradesTable takes full width, side panel stacked */}
              <div className="grid gap-6 xl:grid-cols-4">
                <div className="xl:col-span-3">
                  <TradesTable trades={trades} />
                </div>
                <div className="space-y-4">
                  <TraderRank 
                    totalProfit={totalProfit}
                    totalTrades={wolfStatus.totalTrades}
                    winRate={wolfStatus.winRate}
                  />
                  <ActivityFeed logs={activityLogs} />
                </div>
              </div>
            </div>
          )}

          {activeTab === 'trades' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-black text-foreground tracking-tight">🎯 HUNT LOG — Active Positions</h2>
                  <p className="text-sm text-amber-400/80 italic">&quot;The wolf doesn't chase. He waits, then strikes.&quot;</p>
                </div>
                <StreakCounter 
                  currentStreak={winStreak} 
                  bestStreak={bestStreak}
                  lastTradeWin={true}
                />
              </div>
              <TradesTable trades={trades} />
              {/* Session log shortcut */}
              <div className="rounded-2xl bg-[#161624] border border-white/5 p-4">
                <p className="text-xs font-black text-white uppercase tracking-wider mb-1">📋 Daily Session Log</p>
                <p className="text-xs text-zinc-500">View in Evolution tab → Session Log section</p>
              </div>
            </div>
          )}

          {activeTab === 'analytics' && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-black text-foreground tracking-tight">📊 INTEL — Market Performance</h2>
                <p className="text-sm text-amber-400/80 italic">&quot;Numbers don't lie. Stratton Oakmont approved.&quot;</p>
              </div>
              <div className="grid gap-6 lg:grid-cols-2">
                <PnLChart data={pnlData} />
                <DdubIndexChart data={ddubData} />
              </div>
              <div className="grid gap-6 lg:grid-cols-2">
                <TraderRank 
                  totalProfit={totalProfit}
                  totalTrades={wolfStatus.totalTrades}
                  winRate={wolfStatus.winRate}
                />
                <Achievements 
                  winStreak={winStreak}
                  totalProfit={totalProfit}
                  winRate={wolfStatus.winRate}
                />
              </div>
              <StatsCards wolfStatus={wolfStatus} />
            </div>
          )}

          {activeTab === 'learning' && (
            <div className="space-y-6">
              <EvolutionPanel
                progress={wolfStatus.learningProgress}
                activityLogs={activityLogs}
              />
            </div>
          )}

          {activeTab === 'history' && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-black text-foreground tracking-tight">📖 LEDGER — Closed Trades</h2>
                <p className="text-sm text-amber-400/80 italic">&quot;Every W and L is a lesson. Wolf journals everything.&quot;</p>
              </div>
              <div className="grid gap-6 lg:grid-cols-3">
                <div className="lg:col-span-2">
                  <TradesTable trades={trades.filter(t => t.status === 'CLOSED')} />
                </div>
                <TraderRank 
                  totalProfit={totalProfit}
                  totalTrades={wolfStatus.totalTrades}
                  winRate={wolfStatus.winRate}
                />
              </div>
            </div>
          )}

          {activeTab === 'risk' && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-black text-foreground tracking-tight">🛡️ RISK DESK — Kill Switch Active</h2>
                <p className="text-sm text-amber-400/80 italic">&quot;Discipline beats conviction every time. Kill switch: -40%.&quot;</p>
              </div>
              {/* Risk Parameters — real Wolf config values */}
              <div className="grid gap-4 lg:grid-cols-3">
                <div className="rounded-lg border border-border bg-card p-4">
                  <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold mb-3">Kill Switch</p>
                  <p className="text-2xl font-black text-red-400">-40%</p>
                  <p className="text-xs text-muted-foreground mt-1">Max drawdown before full stop</p>
                  <div className="mt-3 h-1.5 bg-secondary rounded-full overflow-hidden">
                    <div className="h-full bg-emerald-500 rounded-full" style={{width: `${Math.max(0, 100 + (wolfStatus.dailyPnL / 100))}%`}} />
                  </div>
                  <p className="text-[10px] text-emerald-400 mt-1">🟢 Armed — not triggered</p>
                </div>
                <div className="rounded-lg border border-border bg-card p-4">
                  <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold mb-3">Position Sizing</p>
                  <p className="text-2xl font-black text-amber-400">$200</p>
                  <p className="text-xs text-muted-foreground mt-1">Max per trade (paper mode)</p>
                  <p className="text-[10px] text-muted-foreground mt-3">Balance: ${wolfStatus.balance?.toLocaleString() ?? '100'}</p>
                  <p className="text-[10px] text-amber-400">2% per trade · 8% Kelly cap</p>
                </div>
                <div className="rounded-lg border border-border bg-card p-4">
                  <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold mb-3">Force Exit</p>
                  <p className="text-2xl font-black text-blue-400">12h</p>
                  <p className="text-xs text-muted-foreground mt-1">Max hold time per position</p>
                  <p className="text-[10px] text-muted-foreground mt-3">Open slots: {wolfStatus.openPositions}/24</p>
                  <p className="text-[10px] text-blue-400">Min confidence: 70%</p>
                </div>
              </div>
              <div className="grid gap-6 lg:grid-cols-2">
                <DdubIndexChart data={ddubData} />
                <ActivityFeed logs={activityLogs.filter((l: ActivityLog) => l.priority === 'HIGH' || l.priority === 'CRITICAL')} />
              </div>
              <StatsCards wolfStatus={wolfStatus} />
            </div>
          )}

          {activeTab === 'guardian' && (
            <GuardianTab />
          )}

          {activeTab === 'automation' && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-black text-foreground tracking-tight">⚡ AUTOPILOT — Strategy Engine</h2>
                <p className="text-sm text-amber-400/80 italic">&quot;Value Bet · Copy Trading · Market Making — all running.&quot;</p>
              </div>
              <div className="grid gap-6 lg:grid-cols-2">
                <LearningPanel progress={wolfStatus.learningProgress} />
                <ActivityFeed logs={activityLogs.filter(l => l.type === 'SYSTEM')} />
              </div>
            </div>
          )}

          {activeTab === 'settings' && (
            <ConfigLock soundEnabled={soundEnabled} onToggleSound={handleToggleSound}>
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-black text-foreground tracking-tight">⚙️ CONFIGURE — System Settings</h2>
                <p className="text-sm text-amber-400/80 italic">&quot;Set the rules. Wolf follows them precisely.&quot;</p>
              </div>
              
              {/* Data Source Toggle */}
              <div className="rounded-lg border border-border bg-card p-6">
                <h3 className="font-bold text-foreground mb-4">Data Source</h3>
                <div className="flex items-center gap-4">
                  <button
                    onClick={toggleDataSource}
                    className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                      !useApiData 
                        ? 'bg-amber-500 text-background' 
                        : 'bg-secondary text-muted-foreground hover:bg-secondary/80'
                    }`}
                  >
                    Demo Mode
                  </button>
                  <button
                    onClick={toggleDataSource}
                    className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                      useApiData 
                        ? 'bg-emerald-500 text-background' 
                        : 'bg-secondary text-muted-foreground hover:bg-secondary/80'
                    }`}
                  >
                    Live API
                  </button>
                  <span className="text-sm text-muted-foreground">
                    {useApiData 
                      ? 'Connected to OpenClaw agent via API' 
                      : 'Using simulated demo data'}
                  </span>
                </div>
                {useApiData && (
                  <div className="mt-4 rounded bg-secondary/50 p-3 text-xs font-mono text-muted-foreground">
                    <p>API Endpoint: <span className="text-emerald-500">/api/wolf/webhook</span></p>
                    <p>Status: <span className={isConnected ? 'text-emerald-500' : 'text-red-500'}>{isConnected ? 'Connected' : 'Disconnected'}</span></p>
                    <p>Last Update: {apiState?.data?.lastUpdated ?? 'Never'}</p>
                  </div>
                )}
              </div>

              {/* API Documentation */}
              <div className="rounded-lg border border-border bg-card p-6">
                <h3 className="font-bold text-foreground mb-4">OpenClaw API Integration</h3>
                <div className="space-y-3 text-sm">
                  <div className="rounded bg-secondary/50 p-3 font-mono">
                    <p className="text-amber-500 mb-2"># Main webhook endpoint (receives all updates)</p>
                    <p>POST /api/wolf/webhook</p>
                    <p className="text-muted-foreground mt-1">Header: x-wolf-api-key: YOUR_API_KEY</p>
                  </div>
                  <div className="rounded bg-secondary/50 p-3 font-mono">
                    <p className="text-amber-500 mb-2"># Individual endpoints</p>
                    <p>GET/POST /api/wolf/trades</p>
                    <p>GET/POST /api/wolf/status</p>
                    <p>GET/POST /api/wolf/performance</p>
                    <p>GET/POST /api/wolf/market</p>
                    <p>GET/POST /api/wolf/ddub</p>
                    <p>GET /api/wolf/state <span className="text-muted-foreground">(full dashboard state)</span></p>
                  </div>
                </div>
              </div>
              
              <div className="rounded-lg border border-amber-500/30 bg-gradient-to-r from-amber-500/5 to-transparent p-6">
                <div className="flex items-center gap-4">
                  <span className="text-4xl">&#x1F43A;</span>
                  <div>
                    <h3 className="font-bold text-foreground">Wolf of All Streets v1.0</h3>
                    <p className="text-sm text-muted-foreground">
                      Configure Wolf parameters, API connections, win rate thresholds (72%), 
                      risk limits, and notification preferences.
                    </p>
                  </div>
                </div>
                <div className="mt-4 flex gap-2">
                  <button 
                    onClick={triggerCelebration}
                    className="rounded-lg bg-amber-500/20 px-4 py-2 text-sm font-medium text-amber-500 transition-colors hover:bg-amber-500/30"
                  >
                    Test Celebration
                  </button>
                  <button className="rounded-lg bg-secondary px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary/80">
                    Export Data
                  </button>
                </div>
              </div>
              {/* Roadmap / Queued Expansions */}
              <div className="rounded-lg border border-border bg-card p-6">
                <h3 className="font-bold text-foreground mb-1">📍 Expansion Roadmap</h3>
                <p className="text-xs text-muted-foreground mb-4">Queued builds — unlocks after Polymarket live baseline is proven</p>
                <div className="space-y-3">
                  {/* Phase 1 — Current */}
                  <div className="flex items-start gap-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-3">
                    <span className="mt-0.5 h-2 w-2 rounded-full bg-emerald-500 animate-pulse shrink-0" />
                    <div>
                      <p className="text-sm font-bold text-emerald-400">Phase 1 — Polymarket Live <span className="ml-2 text-[10px] font-normal bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded-full">ACTIVE · April 1</span></p>
                      <p className="text-xs text-muted-foreground mt-0.5">8 strategies · $100 USDC · 72% WR gate · paper → live flip</p>
                    </div>
                  </div>
                  {/* Phase 2 — Hyperliquid */}
                  <div className="flex items-start gap-3 rounded-lg bg-secondary/50 border border-border p-3">
                    <span className="mt-0.5 h-2 w-2 rounded-full bg-zinc-500 shrink-0" />
                    <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-bold text-foreground">Phase 2 — Hyperliquid Perps <span className="ml-2 text-[10px] font-normal bg-zinc-700 text-zinc-400 px-2 py-0.5 rounded-full">QUEUED</span></p>
                        <span className="text-[10px] text-muted-foreground">~2 weeks post-live</span>
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">TA Signal + Latency Arb on BTC/ETH perps · 3x max leverage · isolated margin · separate risk engine</p>
                      <div className="mt-2 flex gap-2 flex-wrap">
                        <span className="text-[10px] bg-blue-500/10 text-blue-400 border border-blue-500/20 px-2 py-0.5 rounded-full">TA Signal</span>
                        <span className="text-[10px] bg-blue-500/10 text-blue-400 border border-blue-500/20 px-2 py-0.5 rounded-full">Latency Arb</span>
                        <span className="text-[10px] bg-zinc-700/50 text-zinc-400 px-2 py-0.5 rounded-full">Account: secured ✅</span>
                      </div>
                    </div>
                  </div>
                  {/* Phase 3 — placeholder */}
                  <div className="flex items-start gap-3 rounded-lg bg-secondary/30 border border-border/50 p-3 opacity-50">
                    <span className="mt-0.5 h-2 w-2 rounded-full bg-zinc-600 shrink-0" />
                    <div>
                      <p className="text-sm font-bold text-zinc-500">Phase 3 — Cross-Venue Arb <span className="ml-2 text-[10px] font-normal bg-zinc-800 text-zinc-600 px-2 py-0.5 rounded-full">FUTURE</span></p>
                      <p className="text-xs text-zinc-600 mt-0.5">Polymarket ↔ Hyperliquid unified position management · auto capital allocation</p>
                    </div>
                  </div>
                </div>
              </div>

              <Achievements 
                winStreak={winStreak}
                totalProfit={totalProfit}
                winRate={wolfStatus.winRate}
              />
            </div>
            </ConfigLock>
          )}

          {/* Footer with last refresh time */}
          <div className="mt-6 flex items-center justify-between border-t border-border pt-4">
            <span className="text-xs text-muted-foreground">
              Last updated: {mounted && lastRefresh ? lastRefresh.toLocaleTimeString() : '--:--:--'}
              {useApiData && <span className="ml-2 text-emerald-500">(Live)</span>}
            </span>
            <div className="flex items-center gap-4">
              <span className="text-xs text-amber-500/70">
                &quot;I&apos;m not f***ing leaving!&quot;
              </span>
              <span className="text-xs text-muted-foreground">
                Wolf of All Streets v1.0 | NYSE Live
              </span>
            </div>
          </div>
          </div>
          {/* end desktop */}
        </main>
      </div>
      {/* Mobile bottom nav — hidden on desktop */}
      <MobileNav activeTab={activeTab} onTabChange={setActiveTab} />
    </div>
  </SiteLock>
  )
}
