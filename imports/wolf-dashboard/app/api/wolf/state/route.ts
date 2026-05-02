import { NextResponse } from 'next/server'
import { getFullState } from '@/lib/wolf-store'

export async function GET() {
  const state = await getFullState()
  return NextResponse.json({ success: true, data: state, timestamp: new Date().toISOString() })
}
