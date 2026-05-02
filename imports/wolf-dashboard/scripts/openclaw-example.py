"""
OpenClaw Agent Integration Script for Wolf Mission Control Dashboard

This script provides example functions to push updates from your OpenClaw agent
to the Wolf Mission Control dashboard. Run this on your Hostinger VPS alongside
your trading bot.

Usage:
    1. Set the WOLF_DASHBOARD_URL and WOLF_API_KEY environment variables
    2. Import the WolfDashboard class in your OpenClaw agent
    3. Call the appropriate methods when events occur

Example:
    from openclaw_example import WolfDashboard
    
    dashboard = WolfDashboard()
    dashboard.send_trade_opened("TRADE-001", "ES", "LONG", 5280.50, 2)
"""

import os
import requests
import json
from datetime import datetime
from typing import Optional, Literal

# Configuration
WOLF_DASHBOARD_URL = os.getenv("WOLF_DASHBOARD_URL", "http://localhost:3000")
WOLF_API_KEY = os.getenv("WOLF_API_KEY", "")


class WolfDashboard:
    def __init__(self, base_url: str = WOLF_DASHBOARD_URL, api_key: str = WOLF_API_KEY):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.headers = {
            "Content-Type": "application/json",
            "x-wolf-api-key": self.api_key
        }
    
    def _post(self, endpoint: str, payload: dict) -> dict:
        """Send POST request to dashboard API"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.post(url, json=payload, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"[Wolf Dashboard] Error sending to {endpoint}: {e}")
            return {"success": False, "error": str(e)}

    def _webhook(self, event: str, payload: dict) -> dict:
        """Send webhook event to dashboard"""
        webhook_payload = {
            "event": event,
            "payload": payload,
            "agentId": "openclaw-vps",
            "timestamp": datetime.now().isoformat()
        }
        return self._post("/api/wolf/webhook", webhook_payload)

    # ============ Trade Events ============
    
    def send_trade_opened(
        self,
        trade_id: str,
        symbol: str,
        side: Literal["LONG", "SHORT"],
        entry_price: float,
        quantity: int,
        strategy: str = "D-Dub Signal"
    ) -> dict:
        """Notify dashboard that a new trade was opened"""
        payload = {
            "id": trade_id,
            "symbol": symbol,
            "side": side,
            "entryPrice": entry_price,
            "quantity": quantity,
            "status": "OPEN",
            "entryTime": datetime.now().isoformat(),
            "strategy": strategy
        }
        return self._webhook("trade_opened", payload)

    def send_trade_closed(
        self,
        trade_id: str,
        symbol: str,
        side: Literal["LONG", "SHORT"],
        entry_price: float,
        exit_price: float,
        quantity: int,
        pnl: float,
        pnl_percent: float,
        entry_time: str,
        strategy: str = "D-Dub Signal"
    ) -> dict:
        """Notify dashboard that a trade was closed"""
        payload = {
            "id": trade_id,
            "symbol": symbol,
            "side": side,
            "entryPrice": entry_price,
            "exitPrice": exit_price,
            "quantity": quantity,
            "status": "CLOSED",
            "pnl": pnl,
            "pnlPercent": pnl_percent,
            "entryTime": entry_time,
            "exitTime": datetime.now().isoformat(),
            "strategy": strategy
        }
        return self._webhook("trade_closed", payload)

    # ============ Status Events ============

    def update_status(
        self,
        status: Literal["hunting", "stalking", "resting", "learning", "error"],
        message: str,
        current_position: Optional[dict] = None,
        ddub_signal: Optional[dict] = None
    ) -> dict:
        """Update Wolf's current status"""
        payload = {
            "status": status,
            "message": message,
            "currentPosition": current_position,
            "ddubSignal": ddub_signal
        }
        return self._webhook("status_change", payload)

    # ============ Performance Events ============

    def update_performance(
        self,
        daily_pnl: float,
        weekly_pnl: float,
        monthly_pnl: float,
        total_trades: int,
        win_rate: float,
        win_streak: int,
        best_streak: int,
        total_profit: float
    ) -> dict:
        """Update performance metrics"""
        payload = {
            "dailyPnl": daily_pnl,
            "weeklyPnl": weekly_pnl,
            "monthlyPnl": monthly_pnl,
            "totalTrades": total_trades,
            "winRate": win_rate,
            "winStreak": win_streak,
            "bestStreak": best_streak,
            "totalProfit": total_profit
        }
        return self._webhook("performance_update", payload)

    # ============ Market Data ============

    def update_market_data(
        self,
        symbol: str,
        price: float,
        change: float,
        change_percent: float
    ) -> dict:
        """Update market data for a symbol"""
        payload = {
            "symbol": symbol,
            "price": price,
            "change": change,
            "changePercent": change_percent
        }
        return self._webhook("market_update", payload)

    def update_market_batch(self, data: list[dict]) -> dict:
        """Update multiple symbols at once"""
        return self._post("/api/wolf/market", data)

    # ============ D-Dub Index ============

    def send_ddub_signal(
        self,
        value: float,
        signal: Literal["BUY", "SELL", "HOLD"],
        volume: Optional[float] = None
    ) -> dict:
        """Send D-Dub index data point"""
        payload = {
            "time": datetime.now().strftime("%H:%M"),
            "value": value,
            "signal": signal,
            "volume": volume
        }
        return self._webhook("ddub_signal", payload)

    # ============ Alerts ============

    def send_alert(
        self,
        message: str,
        priority: Literal["low", "medium", "high", "critical"] = "medium",
        alert_type: Literal["TRADE", "ANALYSIS", "LEARNING", "ALERT", "SYSTEM"] = "ALERT"
    ) -> dict:
        """Send alert/activity log entry"""
        payload = {
            "id": f"alert-{datetime.now().timestamp()}",
            "type": alert_type,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "priority": priority
        }
        return self._webhook("alert", payload)

    # ============ Learning Updates ============

    def update_learning(
        self,
        progress: float,
        modules_completed: int,
        total_modules: int,
        current_module: str,
        accuracy: float,
        lessons_learned: list[str]
    ) -> dict:
        """Update learning engine status"""
        payload = {
            "progress": progress,
            "modulesCompleted": modules_completed,
            "totalModules": total_modules,
            "currentModule": current_module,
            "accuracy": accuracy,
            "lessonsLearned": lessons_learned
        }
        return self._webhook("learning_update", payload)


# ============ Example Usage ============

if __name__ == "__main__":
    # Initialize dashboard connection
    dashboard = WolfDashboard(
        base_url="https://your-wolf-dashboard.vercel.app",  # Replace with your deployed URL
        api_key="your-secret-api-key"  # Set in Vercel environment variables
    )
    
    # Example: Wolf is now hunting
    dashboard.update_status(
        status="hunting",
        message="Scanning for D-Dub signals...",
        ddub_signal={"value": 62.5, "direction": "BUY", "confidence": 0.85}
    )
    
    # Example: Send D-Dub signal
    dashboard.send_ddub_signal(
        value=65.2,
        signal="BUY",
        volume=12500
    )
    
    # Example: Open a trade
    dashboard.send_trade_opened(
        trade_id="WOLF-001",
        symbol="ES",
        side="LONG",
        entry_price=5285.50,
        quantity=2,
        strategy="D-Dub Breakout"
    )
    
    # Example: Update market data
    dashboard.update_market_batch([
        {"symbol": "ES", "price": 5287.25, "change": 12.50, "changePercent": 0.24},
        {"symbol": "NQ", "price": 18542.00, "change": 85.00, "changePercent": 0.46},
        {"symbol": "SPY", "price": 528.32, "change": 2.15, "changePercent": 0.41},
        {"symbol": "QQQ", "price": 445.80, "change": 3.20, "changePercent": 0.72}
    ])
    
    # Example: Close the trade with profit
    dashboard.send_trade_closed(
        trade_id="WOLF-001",
        symbol="ES",
        side="LONG",
        entry_price=5285.50,
        exit_price=5292.25,
        quantity=2,
        pnl=337.50,  # (5292.25 - 5285.50) * 2 * 25 (ES multiplier)
        pnl_percent=0.13,
        entry_time="2024-01-15T09:35:00",
        strategy="D-Dub Breakout"
    )
    
    # Example: Update performance
    dashboard.update_performance(
        daily_pnl=1250.75,
        weekly_pnl=4532.50,
        monthly_pnl=12845.00,
        total_trades=47,
        win_rate=74.5,
        win_streak=8,
        best_streak=12,
        total_profit=15623.80
    )
    
    # Example: Send alert
    dashboard.send_alert(
        message="Win rate threshold achieved: 74.5%!",
        priority="high",
        alert_type="ALERT"
    )
    
    # Example: Update learning
    dashboard.update_learning(
        progress=78,
        modules_completed=4,
        total_modules=5,
        current_module="Advanced Pattern Recognition",
        accuracy=0.82,
        lessons_learned=[
            "Avoid trading first 15 minutes of market open",
            "D-Dub signals above 70 have 85% success rate",
            "Cut losses at 1.5x target for better risk/reward"
        ]
    )
    
    print("All example events sent successfully!")
