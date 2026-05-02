import { NextRequest, NextResponse } from 'next/server'
import type { TradeUpdate } from '@/lib/api-types'
import { getFullState, updateTrade } from '@/lib/wolf-store'

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url)
  const status = searchParams.get('status')
  const limit = parseInt(searchParams.get('limit') || '50')
  const s = await getFullState()
  let trades = [...s.trades]
  if (status) trades = trades.filter(t => t.status === status.toUpperCase())
  trades = trades.slice(0, limit)
  return NextResponse.json({ success: true, data: { trades, total: s.trades.length, openPositions: s.trades.filter(t => t.status === 'OPEN').length }, timestamp: new Date().toISOString() })
}

export async function POST(request: NextRequest) {
  const apiKey = request.headers.get('x-wolf-api-key') || request.headers.get('authorization')?.replace('Bearer ', '')
  const expectedKey = process.env.WOLF_API_KEY
  if (expectedKey && apiKey !== expectedKey) return NextResponse.json({ success: false, error: 'Unauthorized' }, { status: 401 })
  try {
    const body = await request.json()
    // Normalize YES/NO → LONG/SHORT and open/won/lost → OPEN/CLOSED
    const trade: TradeUpdate = {
      ...body,
      side: body.side === 'YES' ? 'LONG' : body.side === 'NO' ? 'SHORT' : body.side,
      status: body.status === 'open' ? 'OPEN' : body.status === 'won' || body.status === 'lost' ? 'CLOSED' : (body.status || 'OPEN').toUpperCase(),
      entryTime: typeof body.entryTime === 'number' ? new Date(body.entryTime).toISOString() : body.entryTime || new Date().toISOString(),
      exitTime: body.exitTime && typeof body.exitTime === 'number' && body.exitTime > 0 ? new Date(body.exitTime).toISOString() : body.exitTime || undefined,
    }
    if (!trade.id || !trade.symbol || !trade.side) return NextResponse.json({ success: false, error: 'Missing required fields: id, symbol, side' }, { status: 400 })
    await updateTrade(trade)
    return NextResponse.json({ success: true, data: trade, timestamp: new Date().toISOString() })
  } catch (e) {
    return NextResponse.json({ success: false, error: 'Invalid request body' }, { status: 400 })
  }
}
