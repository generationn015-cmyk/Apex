import { NextRequest, NextResponse } from 'next/server'

/**
 * POST /api/wolf/go-live
 * Sends a command to the Wolf VPS to flip WOLF_PAPER_MODE=false and restart.
 * Requires WOLF_API_KEY + WOLF_VPS_URL env vars.
 */
export async function POST(request: NextRequest) {
  const apiKey = request.headers.get('x-wolf-api-key') ||
    request.headers.get('authorization')?.replace('Bearer ', '')
  const expectedKey = process.env.WOLF_API_KEY
  if (expectedKey && apiKey !== expectedKey) {
    return NextResponse.json({ success: false, error: 'Unauthorized' }, { status: 401 })
  }

  const vpsUrl = process.env.WOLF_VPS_URL
  if (!vpsUrl) {
    // VPS URL not configured — return instruction for manual activation
    return NextResponse.json({
      success: false,
      error: 'WOLF_VPS_URL not configured',
      manual: 'Set WOLF_PAPER_MODE=false in wolf/.env on the VPS and run: bash watchdog.sh',
    }, { status: 503 })
  }

  try {
    const res = await fetch(`${vpsUrl}/control/go-live`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-wolf-api-key': process.env.WOLF_API_KEY ?? '',
      },
      body: JSON.stringify({ action: 'go-live', timestamp: new Date().toISOString() }),
      signal: AbortSignal.timeout(10000),
    })
    const data = await res.json().catch(() => ({}))
    return NextResponse.json({ success: res.ok, data, timestamp: new Date().toISOString() })
  } catch (e) {
    return NextResponse.json({
      success: false,
      error: 'Could not reach Wolf VPS',
      manual: 'Set WOLF_PAPER_MODE=false in wolf/.env on the VPS and run: bash watchdog.sh',
    }, { status: 503 })
  }
}
