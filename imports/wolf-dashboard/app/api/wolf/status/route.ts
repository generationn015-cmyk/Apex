import { NextRequest, NextResponse } from 'next/server'
import { getFullState, updateStatus } from '@/lib/wolf-store'

export async function GET() {
  const s = await getFullState()
  return NextResponse.json({ success: true, data: s.status, timestamp: new Date().toISOString() })
}

export async function POST(request: NextRequest) {
  const apiKey = request.headers.get('x-wolf-api-key') || request.headers.get('authorization')?.replace('Bearer ', '')
  const expectedKey = process.env.WOLF_API_KEY
  if (expectedKey && apiKey !== expectedKey) return NextResponse.json({ success: false, error: 'Unauthorized' }, { status: 401 })
  try {
    const body = await request.json()
    // Normalize status string
    const statusMap: Record<string,string> = { online: 'hunting', offline: 'resting', error: 'error', learning: 'learning' }
    const normalized = { ...body, status: statusMap[body.status] || body.status || 'hunting' }
    await updateStatus(normalized)
    return NextResponse.json({ success: true, data: normalized, timestamp: new Date().toISOString() })
  } catch {
    return NextResponse.json({ success: false, error: 'Invalid request body' }, { status: 400 })
  }
}
