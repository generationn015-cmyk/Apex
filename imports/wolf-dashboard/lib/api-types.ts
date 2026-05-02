// API Response types for OpenClaw agent integration

export interface ApiResponse<T = unknown> {
  success: boolean
  data?: T
  error?: string
  timestamp: string
}

export interface TradeUpdate {
  id: string
  symbol: string
  side: 'LONG' | 'SHORT'
  entryPrice: number
  exitPrice?: number
  quantity: number
  status: 'OPEN' | 'CLOSED' | 'PENDING'
  pnl?: number
  pnlPercent?: number
  entryTime: string
  exitTime?: string
  strategy?: string
  notes?: string
  marketEnd?: number   // ms timestamp of market expiry (0 = unknown)
  confidence?: number
}

export interface WolfStatusUpdate {
  status: 'hunting' | 'stalking' | 'resting' | 'learning' | 'error'
  message: string
  currentPosition?: {
    symbol: string
    side: 'LONG' | 'SHORT'
    unrealizedPnl: number
  }
  ddubSignal?: {
    value: number
    direction: 'BUY' | 'SELL' | 'HOLD'
    confidence: number
  }
}

export interface PerformanceUpdate {
  dailyPnl: number
  weeklyPnl: number
  monthlyPnl: number
  totalTrades: number
  winRate: number
  winStreak: number
  bestStreak: number
  totalProfit: number
  balance?: number        // Current account balance (paper or live)
  paperMode?: boolean     // True = paper trading, False = live
}

export interface MarketDataUpdate {
  symbol: string
  price: number
  change: number
  changePercent: number
}

export interface ActivityLogEntry {
  id: string
  type: 'TRADE' | 'ANALYSIS' | 'LEARNING' | 'ALERT' | 'SYSTEM'
  message: string
  timestamp: string
  priority: 'low' | 'medium' | 'high' | 'critical'
}

export interface DdubDataPoint {
  time: string
  value: number
  signal: 'BUY' | 'SELL' | 'HOLD'
  volume?: number
}

export interface PnlDataPoint {
  date: string
  pnl: number
  cumulative: number
  trades: number
}

export interface LearningUpdate {
  progress: number
  modulesCompleted: number
  totalModules: number
  currentModule: string
  accuracy: number
  lessonsLearned: string[]
}

// Webhook payload from OpenClaw
export interface OpenClawWebhook {
  event: 'trade_opened' | 'trade_closed' | 'status_change' | 'alert' | 'performance_update' | 'market_update' | 'ddub_signal' | 'learning_update'
  payload: TradeUpdate | WolfStatusUpdate | PerformanceUpdate | MarketDataUpdate | ActivityLogEntry | DdubDataPoint | LearningUpdate
  agentId: string
  timestamp: string
}
