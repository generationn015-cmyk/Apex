import { NextRequest, NextResponse } from 'next/server'
import { getFullState, addDdubDataPoint } from '@/lib/wolf-store'

export async function GET() {
  const s = await getFullState()
  return NextResponse.json({ success: true, data: { current: s.ddubData[s.ddubData.length - 1] || null, history: s.ddubData }, timestamp: new Date().toISOString() })
}

export async function POST(request: NextRequest) {
  const apiKey = request.headers.get('x-wolf-api-key') || request.headers.get('authorization')?.replace('Bearer ', '')
  const expectedKey = process.env.WOLF_API_KEY
  if (expectedKey && apiKey !== expectedKey) return NextResponse.json({ success: false, error: 'Unauthorized' }, { status: 401 })
  try {
    const body = await request.json()
    // Normalize signal: neutral→HOLD, bullish→BUY, bearish→SELL
    const sigMap: Record<string,string> = { neutral: 'HOLD', bullish: 'BUY', bearish: 'SELL', HOLD: 'HOLD', BUY: 'BUY', SELL: 'SELL' }
    const point = { ...body, signal: sigMap[body.signal] || 'HOLD', time: body.time || new Date().toISOString() }
    await addDdubDataPoint(point)
    return NextResponse.json({ success: true, data: point, timestamp: new Date().toISOString() })
  } catch {
    return NextResponse.json({ success: false, error: 'Invalid request body' }, { status: 400 })
  }
}
