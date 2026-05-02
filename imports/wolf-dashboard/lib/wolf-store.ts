// Wolf in-memory store — data is pushed by OpenClaw every 60s
// Vercel Edge Config/Blob not used — live pushes keep data fresh enough

import type {
  TradeUpdate,
  WolfStatusUpdate,
  PerformanceUpdate,
  MarketDataUpdate,
  ActivityLogEntry,
  DdubDataPoint,
  PnlDataPoint,
  LearningUpdate
} from './api-types'

interface GuardianState {
  scan_count: number
  healthy: boolean
  error_count: number
  errors: Array<{ name: string; severity: string; description: string; sample?: string }>
  last_scan_ts: number | null
}

interface WolfStore {
  trades: TradeUpdate[]
  status: WolfStatusUpdate
  performance: PerformanceUpdate
  marketData: MarketDataUpdate[]
  activityLogs: ActivityLogEntry[]
  ddubData: DdubDataPoint[]
  pnlData: PnlDataPoint[]
  learning: LearningUpdate
  guardian: GuardianState
  lastUpdated: string
}

const defaultStore: WolfStore = {
  trades: [],
  status: { status: 'hunting', message: 'Wolf is live — waiting for first push...' },
  performance: { dailyPnl: 0, weeklyPnl: 0, monthlyPnl: 0, totalTrades: 0, winRate: 0, winStreak: 0, bestStreak: 0, totalProfit: 0 },
  marketData: [
    { symbol: 'BTC', price: 0, change: 0, changePercent: 0 },
    { symbol: 'ETH', price: 0, change: 0, changePercent: 0 },
    { symbol: 'POLY', price: 0, change: 0, changePercent: 0 },
  ],
  activityLogs: [],
  ddubData: [],
  pnlData: [],
  learning: { progress: 0, modulesCompleted: 0, totalModules: 5, currentModule: 'Paper trading active', accuracy: 0, lessonsLearned: [] },
  guardian: { scan_count: 0, healthy: true, error_count: 0, errors: [], last_scan_ts: null },
  lastUpdated: new Date().toISOString()
}

declare global { var wolfStore: WolfStore | undefined }
export const store: WolfStore = global.wolfStore ?? { ...defaultStore }
if (process.env.NODE_ENV !== 'production') global.wolfStore = store

function touch() { store.lastUpdated = new Date().toISOString() }

export async function updateTrade(trade: TradeUpdate) {
  const i = store.trades.findIndex(t => t.id === trade.id)
  if (i >= 0) store.trades[i] = trade
  else store.trades.unshift(trade)
  if (store.trades.length > 100) store.trades = store.trades.slice(0, 100)
  store.activityLogs.unshift({
    id: `log-${Date.now()}`,
    type: 'TRADE',
    message: `${trade.side} ${trade.symbol} ${trade.status === 'CLOSED' ? 'closed' : 'opened'} @ $${trade.entryPrice}${trade.pnl != null ? ` | P&L: $${Number(trade.pnl).toFixed(2)}` : ''}`,
    timestamp: new Date().toISOString(),
    priority: trade.status === 'CLOSED' ? (trade.pnl && trade.pnl > 0 ? 'high' : 'medium') : 'medium'
  })
  if (store.activityLogs.length > 50) store.activityLogs = store.activityLogs.slice(0, 50)
  touch()
}

export async function updateStatus(status: WolfStatusUpdate) {
  store.status = status; touch()
}

export async function updatePerformance(performance: PerformanceUpdate) {
  store.performance = { ...store.performance, ...performance }; touch()
}

export async function updateMarketData(data: MarketDataUpdate) {
  const i = store.marketData.findIndex(m => m.symbol === data.symbol)
  if (i >= 0) store.marketData[i] = data
  else store.marketData.push(data)
  touch()
}

export async function addActivityLog(log: ActivityLogEntry) {
  store.activityLogs.unshift(log)
  if (store.activityLogs.length > 50) store.activityLogs = store.activityLogs.slice(0, 50)
  touch()
}

export async function addDdubDataPoint(point: DdubDataPoint) {
  store.ddubData.push(point)
  if (store.ddubData.length > 1440) store.ddubData = store.ddubData.slice(-1440)
  touch()
}

export async function addPnlDataPoint(point: PnlDataPoint) {
  const i = store.pnlData.findIndex(p => p.date === point.date)
  if (i >= 0) store.pnlData[i] = point
  else store.pnlData.push(point)
  if (store.pnlData.length > 30) store.pnlData = store.pnlData.slice(-30)
  touch()
}

export async function updateLearning(learning: LearningUpdate) {
  store.learning = learning; touch()
}

export async function updateGuardian(guardian: GuardianState) {
  store.guardian = guardian; touch()
}

export async function getFullState(): Promise<WolfStore & { isStale: boolean }> {
  // isStale = store is at default values (never received a push from Wolf since cold start)
  const isStale = store.performance.totalTrades === 0 && store.trades.length === 0 && store.pnlData.length === 0
  return { ...store, isStale }
}

export async function resetStore() {
  Object.assign(store, { ...defaultStore, lastUpdated: new Date().toISOString() })
}
