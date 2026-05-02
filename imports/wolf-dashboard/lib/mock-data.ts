import type { Trade, WolfStatus, ActivityLog, PnLDataPoint, DdubIndexData, MarketData } from './wolf-types'

// Generate realistic P&L data for the last 30 days
export function generatePnLData(): PnLDataPoint[] {
  const data: PnLDataPoint[] = []
  let cumulative = 0
  const today = new Date()
  
  for (let i = 29; i >= 0; i--) {
    const date = new Date(today)
    date.setDate(date.getDate() - i)
    const dailyPnl = (Math.random() - 0.35) * 500 // Slightly positive bias
    cumulative += dailyPnl
    data.push({
      date: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      pnl: Math.round(dailyPnl * 100) / 100,
      cumulative: Math.round(cumulative * 100) / 100,
      trades: Math.floor(Math.random() * 8) + 2
    })
  }
  return data
}

// Generate D-Dub Index data
export function generateDdubData(): DdubIndexData[] {
  const data: DdubIndexData[] = []
  const now = new Date()
  
  for (let i = 23; i >= 0; i--) {
    const timestamp = new Date(now)
    timestamp.setHours(timestamp.getHours() - i)
    const value = 45 + Math.random() * 30
    const signal: 'BUY' | 'SELL' | 'HOLD' = value > 65 ? 'BUY' : value < 45 ? 'SELL' : 'HOLD'
    data.push({
      timestamp: timestamp.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
      value: Math.round(value * 100) / 100,
      signal,
      strength: Math.round((Math.abs(value - 50) / 25) * 100)
    })
  }
  return data
}

// Mock trades — Polymarket prediction market style
export function generateTrades(): Trade[] {
  const markets = [
    { symbol: 'Will BTC exceed $100K before June?', strategy: 'value_bet',
    size: Math.round((Math.random() * 180 + 20) * 100) / 100 },
    { symbol: 'Will Harvey Weinstein sentence be extended?', strategy: 'value_bet',
    size: Math.round((Math.random() * 180 + 20) * 100) / 100 },
    { symbol: 'Will Italy qualify for 2026 FIFA World Cup?', strategy: 'value_bet',
    size: Math.round((Math.random() * 180 + 20) * 100) / 100 },
    { symbol: 'Will Sweden qualify for 2026 FIFA World Cup?', strategy: 'value_bet',
    size: Math.round((Math.random() * 180 + 20) * 100) / 100 },
    { symbol: 'New Rihanna album before GTA VI?', strategy: 'value_bet',
    size: Math.round((Math.random() * 180 + 20) * 100) / 100 },
    { symbol: 'Will Fed cut rates in May 2026?', strategy: 'copy_trading' },
    { symbol: 'Will Trump sign new crypto bill in Q2?', strategy: 'copy_trading' },
    { symbol: 'Will ETH flip BTC in market cap by 2027?', strategy: 'copy_trading' },
    { symbol: 'Will Elon Musk leave DOGE by April?', strategy: 'copy_trading' },
    { symbol: 'US recession declared before year end?', strategy: 'market_making' },
  ]
  const trades: Trade[] = []

  // Open positions — paper mode, all hunting
  markets.slice(0, 6).forEach((m, i) => {
    const side = i % 3 === 0 ? 'SHORT' : 'LONG'
    const entry = 0.06 + Math.random() * 0.55
    const timestamp = new Date()
    timestamp.setHours(timestamp.getHours() - Math.floor(Math.random() * 8 + 1))
    trades.push({
      id: `open-${i + 1}`,
      symbol: m.symbol,
      type: side,
      entry: Math.round(entry * 1000) / 1000,
      exit: null,
      pnl: 0,
      status: 'OPEN' as const,
      timestamp,
      confidence: Math.round((0.68 + Math.random() * 0.15) * 100),
      strategy: m.strategy,
    })
  })

  // Closed trades — mixed results
  const results = [
    { pnl: 175.40, won: true },
    { pnl: 92.15, won: true },
    { pnl: -48.30, won: false },
    { pnl: 210.00, won: true },
  ]
  markets.slice(6).forEach((m, i) => {
    const r = results[i] || { pnl: 50, won: true }
    const entry = 0.08 + Math.random() * 0.4
    const exit = r.won ? Math.min(0.99, entry + 0.2 + Math.random() * 0.3) : Math.max(0.01, entry - 0.1 - Math.random() * 0.2)
    const timestamp = new Date()
    timestamp.setHours(timestamp.getHours() - Math.floor(Math.random() * 24 + 8))
    trades.push({
      id: `closed-${i + 1}`,
      symbol: m.symbol,
      type: r.won ? 'LONG' : 'SHORT',
      entry: Math.round(entry * 1000) / 1000,
      exit: Math.round(exit * 1000) / 1000,
      pnl: r.pnl,
      status: 'CLOSED' as const,
      timestamp,
      confidence: Math.round((0.70 + Math.random() * 0.12) * 100),
      strategy: m.strategy,
    })
  })

  return trades.sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime())
}

// Wolf status
export function getWolfStatus(): WolfStatus {
  return {
    status: 'ACTIVE',
    winRate: 0,
    totalTrades: 0,
    dailyPnL: 0,
    weeklyPnL: 0,
    monthlyPnL: 0,
    learningProgress: 0,
    lastActivity: new Date(),
    openPositions: 16,
    riskLevel: 'MEDIUM'
  }
}

// Activity logs
export function generateActivityLogs(): ActivityLog[] {
  const logs: ActivityLog[] = [
    {
      id: '1',
      type: 'TRADE',
      message: 'Opened LONG position on ES at 5,245.50',
      timestamp: new Date(),
      priority: 'HIGH'
    },
    {
      id: '2',
      type: 'ANALYSIS',
      message: 'D-Dub Index crossed above 65 - Bullish signal detected',
      timestamp: new Date(Date.now() - 15 * 60000),
      priority: 'MEDIUM'
    },
    {
      id: '3',
      type: 'LEARNING',
      message: 'Self-correction applied: Tightened stop-loss parameters by 2.5%',
      timestamp: new Date(Date.now() - 32 * 60000),
      priority: 'MEDIUM'
    },
    {
      id: '4',
      type: 'TRADE',
      message: 'Closed SHORT position on NQ at 18,432.00 | P&L: +$187.50',
      timestamp: new Date(Date.now() - 45 * 60000),
      priority: 'HIGH'
    },
    {
      id: '5',
      type: 'ALERT',
      message: 'Win rate approaching 72% threshold (Current: 71.4%)',
      timestamp: new Date(Date.now() - 60 * 60000),
      priority: 'HIGH'
    },
    {
      id: '6',
      type: 'SYSTEM',
      message: 'Learning engine checkpoint saved - State persisted',
      timestamp: new Date(Date.now() - 90 * 60000),
      priority: 'LOW'
    },
    {
      id: '7',
      type: 'ANALYSIS',
      message: 'Market volatility increased - Adjusting position sizing',
      timestamp: new Date(Date.now() - 120 * 60000),
      priority: 'MEDIUM'
    },
    {
      id: '8',
      type: 'LEARNING',
      message: 'Pattern recognition model updated with 24 new samples',
      timestamp: new Date(Date.now() - 180 * 60000),
      priority: 'LOW'
    }
  ]
  return logs
}

// Market data
export function getMarketData(): MarketData[] {
  // These get replaced by live CoinGecko data in market-ticker.tsx
  return [
    { symbol: 'BTC', price: 0, change: 0, changePercent: 0, volume: 0, high: 0, low: 0 },
    { symbol: 'ETH', price: 0, change: 0, changePercent: 0, volume: 0, high: 0, low: 0 },
  ]
}
