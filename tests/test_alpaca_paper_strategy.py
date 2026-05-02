import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.alpaca_paper_runner import Decision, RunnerResult, append_journal, decide_signal, evaluate_risk
from scripts.apex_alerts import build_notifications, evaluate_alerts
from scripts.backtest_top_signals import passes_multi_year_gate
from scripts.backtest_spy_strategy import run_backtest
from scripts.backtest_binance_strategy import bars_from_binance_rows
from scripts.download_binance_klines import binance_monthly_kline_url
from scripts.run_equity_backtest_report import passes_gate


class AlpacaPaperStrategyTests(unittest.TestCase):
    def test_holds_existing_position_when_trend_is_up(self):
        bars = [
            {"close": 100 + i * 0.5}
            for i in range(60)
        ]

        decision = decide_signal(bars, has_position=True, entry_price=110)

        self.assertEqual(decision.action, "hold")

    def test_exits_existing_position_when_stop_is_hit(self):
        bars = [{"close": 100.0} for _ in range(59)] + [{"close": 97.0}]

        decision = decide_signal(bars, has_position=True, entry_price=100.0)

        self.assertEqual(decision.action, "sell")
        self.assertIn("stop", decision.reason)

    def test_uses_latest_price_for_stop_when_provided(self):
        bars = [{"close": 100.0} for _ in range(59)] + [{"close": 97.0}]

        decision = decide_signal(bars, has_position=True, entry_price=100.0, latest_price=101.0)

        self.assertEqual(decision.action, "hold")

    def test_buys_only_without_position_in_uptrend(self):
        bars = [
            {"close": 100 + i * 0.5}
            for i in range(60)
        ]

        decision = decide_signal(bars, has_position=False, entry_price=0)

        self.assertEqual(decision.action, "buy")

    def test_stays_flat_without_position_in_downtrend(self):
        bars = [
            {"close": 130 - i * 0.5}
            for i in range(60)
        ]

        decision = decide_signal(bars, has_position=False, entry_price=0)

        self.assertEqual(decision.action, "hold")

    def test_journal_writes_header_and_row(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.csv"

            append_journal(
                path=path,
                symbol="SPY",
                action="hold",
                reason="position_protected",
                market_open=False,
                equity=100_000.0,
                buying_power=190_000.0,
                position_qty=13.0,
                latest_price=720.65,
                dry_run=False,
            )

            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertIn("timestamp,symbol,action", lines[0])
            self.assertIn("SPY,hold,position_protected", lines[1])

    def test_runner_result_flags_dry_run_without_trade_logic_change(self):
        result = RunnerResult(
            symbol="SPY",
            decision=Decision("hold", "position_protected"),
            market_open=False,
            equity=100_000.0,
            buying_power=190_000.0,
            position_qty=13.0,
            latest_price=720.65,
            dry_run=True,
        )

        self.assertEqual(result.alerts, ["dry-run"])

    def test_alerts_flag_missing_heartbeat(self):
        self.assertEqual(evaluate_alerts({}), ["equity-unavailable", "missing-heartbeat"])

    def test_alerts_include_risk_flags(self):
        alerts = evaluate_alerts({"timestamp": "2026-01-01T00:00:00+00:00", "equity": 100, "risk": {"flags": ["daily-loss-over-300"]}}, max_age_seconds=999999999)

        self.assertIn("daily-loss-over-300", alerts)

    def test_notifications_include_actionable_signal(self):
        notifications = build_notifications(
            [],
            {
                "symbol": "SPY",
                "signals": {
                    "top": [
                        {"symbol": "NVDA", "actionable": True, "decision": "buy", "reason": "uptrend", "score": 100}
                    ]
                },
            },
        )

        self.assertEqual(notifications[0]["title"], "actionable-paper-signal")

    def test_risk_blocks_new_buy_without_forcing_exit(self):
        flags = evaluate_risk(
            equity=100_000,
            buying_power=50_000,
            market_value=11_500,
            day_pl=0,
            unrealized_pl=0,
            pending_buy_notional=5_000,
        )

        self.assertEqual(flags, ["new-buy-exposure-over-12pct"])

    def test_backtest_returns_basic_metrics(self):
        bars = []
        price = 100.0
        for i in range(90):
            price += 0.4 if i < 70 else -0.2
            bars.append({"timestamp": f"2026-01-{(i % 28) + 1:02d}", "close": price})

        metrics = run_backtest(bars, initial_cash=10_000.0, max_notional=1_000.0)

        self.assertIn("final_equity", metrics)
        self.assertIn("total_return_pct", metrics)
        self.assertIn("trades", metrics)

    def test_binance_monthly_kline_url_uses_official_vision_path(self):
        url = binance_monthly_kline_url("BTCUSDT", "1h", "2024-01", market="spot")

        self.assertEqual(
            url,
            "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2024-01.zip",
        )

    def test_binance_rows_convert_to_bars(self):
        rows = [
            {
                "open_time": "1704067200000",
                "open": "42000.0",
                "high": "42100.0",
                "low": "41900.0",
                "close": "42050.0",
                "volume": "12.5",
            }
        ]

        bars = bars_from_binance_rows(rows)

        self.assertEqual(bars[0]["close"], 42050.0)
        self.assertEqual(bars[0]["volume"], 12.5)

    def test_strategy_gate_requires_profit_factor_and_drawdown(self):
        good = {
            "profit_factor": 2.1,
            "max_drawdown_pct": 9.0,
            "closed_trades": 4,
            "total_return_pct": 12.0,
        }
        bad = {
            "profit_factor": 0.8,
            "max_drawdown_pct": 4.0,
            "closed_trades": 4,
            "total_return_pct": 12.0,
        }

        self.assertTrue(passes_gate(good))
        self.assertFalse(passes_gate(bad))

    def test_top_signal_gate_requires_full_5y_and_3y(self):
        good = {
            "profit_factor": 2.1,
            "max_drawdown_pct": 9.0,
            "closed_trades": 4,
            "total_return_pct": 12.0,
        }
        bad = {
            "profit_factor": 0.8,
            "max_drawdown_pct": 4.0,
            "closed_trades": 4,
            "total_return_pct": 12.0,
        }

        self.assertTrue(passes_multi_year_gate({"full": good, "recent_5y": good, "recent_3y": good}))
        self.assertFalse(passes_multi_year_gate({"full": good, "recent_5y": bad, "recent_3y": good}))


if __name__ == "__main__":
    unittest.main()
