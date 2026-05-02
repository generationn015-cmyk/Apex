'use client'

import { useEffect } from 'react'

// This page clears the site lock and redirects to home to set a new password.
// Security: still requires physical access to the URL — not linked anywhere.
export default function ResetPage() {
  useEffect(() => {
    localStorage.removeItem('wolf_site_hash')
    sessionStorage.removeItem('wolf_site_unlocked')
    window.location.replace('/')
  }, [])

  return (
    <div className="fixed inset-0 bg-[#06060e] flex items-center justify-center">
      <div className="text-amber-500 text-sm font-mono tracking-widest animate-pulse">
        RESETTING ACCESS CREDENTIALS...
      </div>
    </div>
  )
}
