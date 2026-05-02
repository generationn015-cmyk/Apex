import { NextRequest, NextResponse } from 'next/server'
import { getFullState, updatePerformance, addPnlDataPoint } from '@/lib/wolf-store'

export async function GET() {
  const s = await getFullState()
  return NextResponse.json({ success: true, data: { performance: s.performance, pnlHistory: s.pnlData }, timestamp: new Date().toISOString() })
}

export async function POST(request: NextRequest) {
  const apiKey = request.headers.get('x-wolf-api-key') || request.headers.get('authorization')?.replace('Bearer ', '')
  const expectedKey = process.env.WOLF_API_KEY
  if (expectedKey && apiKey !== expectedKey) return NextResponse.json({ success: false, error: 'Unauthorized' }, { status: 401 })
  try {
    const body = await request.json()
    await updatePerformance(body)
    // Also record daily P&L data point
    if (body.dailyPnl !== undefined) {
      await addPnlDataPoint({ date: new Date().toISOString().split('T')[0], pnl: body.dailyPnl, cumulative: body.totalProfit || 0, trades: body.totalTrades || 0 })
    }
    return NextResponse.json({ success: true, data: body, timestamp: new Date().toISOString() })
  } catch {
    return NextResponse.json({ success: false, error: 'Invalid request body' }, { status: 400 })
  }
}
