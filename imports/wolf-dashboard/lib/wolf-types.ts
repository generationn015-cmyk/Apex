export interface Trade {
  id: string
  symbol: string
  type: 'LONG' | 'SHORT'
  entry: number
  exit: number | null
  pnl: number
  unrealizedPnl?: number
  status: 'OPEN' | 'CLOSED' | 'PENDING'
  timestamp: Date
  confidence: number
  strategy: string
  size?: number  // USD position size (stake)
  marketEnd?: number  // ms timestamp of market expiry (0 = unknown)
}

export interface WolfStatus {
  status: 'ACTIVE' | 'IDLE' | 'LEARNING' | 'ERROR'
  winRate: number
  totalTrades: number
  dailyPnL: number
  weeklyPnL: number
  monthlyPnL: number
  learningProgress: number
  lastActivity: Date | null
  openPositions: number
  riskLevel: 'LOW' | 'MEDIUM' | 'HIGH'
  balance?: number
  paperMode?: boolean
}

export interface MarketData {
  symbol: string
  price: number
  change: number
  changePercent: number
  volume?: number
  high?: number
  low?: number
}

export interface ActivityLog {
  id: string
  type: 'TRADE' | 'ANALYSIS' | 'ALERT' | 'LEARNING' | 'SYSTEM'
  message: string
  timestamp: string | Date
  priority: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | 'low' | 'medium' | 'high' | 'critical'
}

export interface PnLDataPoint {
  date: string
  pnl: number
  cumulative: number
  trades: number
}

export interface DdubIndexData {
  timestamp: string
  value: number
  signal: 'BUY' | 'SELL' | 'HOLD'
  strength: number
}
