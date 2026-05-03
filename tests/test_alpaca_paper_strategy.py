import unittest
import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.alpaca_paper_runner import Decision, RunnerResult, append_journal, decide_signal, evaluate_risk
from scripts.apex_alerts import build_notifications, evaluate_alerts
from scripts.backtest_top_signals import passes_multi_year_gate
from scripts.backtest_spy_strategy import _dedupe_sorted_bars
from scripts.backtest_spy_strategy import run_backtest
from scripts.equity_universe import default_equity_symbols
from scripts.backtest_binance_strategy import bars_from_binance_rows
from scripts.backtest_binance_multi_year import latest_complete_month, month_range
from scripts.crypto_universe import default_crypto_symbols
from scripts.download_binance_klines import binance_monthly_kline_url
from scripts.run_equity_backtest_report import passes_gate
from scripts.walk_forward_backtest import passes_walk_forward, summarize_windows


ROOT = Path(__file__).resolve().parents[1]
RUNNER_HEARTBEAT_SPEC = importlib.util.spec_from_file_location(
    "runner_heartbeat_api",
    ROOT / "api" / "runner-heartbeat.py",
)
runner_heartbeat_api = importlib.util.module_from_spec(RUNNER_HEARTBEAT_SPEC)
RUNNER_HEARTBEAT_SPEC.loader.exec_module(runner_heartbeat_api)


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
        self.assertIn("sharpe", metrics)
        self.assertIn("sortino", metrics)
        self.assertIn("calmar", metrics)
        self.assertGreater(metrics["exposure_pct"], 0)

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

    def test_binance_multi_year_month_range_is_inclusive(self):
        self.assertEqual(month_range("2024-11", "2025-02"), ["2024-11", "2024-12", "2025-01", "2025-02"])

    def test_latest_complete_month_steps_back_from_current_month(self):
        self.assertEqual(latest_complete_month(datetime(2026, 5, 2, tzinfo=UTC)), "2026-04")

    def test_default_crypto_universe_contains_core_pairs(self):
        symbols = default_crypto_symbols()

        self.assertIn("BTCUSDT", symbols)
        self.assertIn("ETHUSDT", symbols)
        self.assertGreaterEqual(len(symbols), 5)

    def test_strategy_gate_requires_profit_factor_and_drawdown(self):
        good = {
            "profit_factor": 2.1,
            "max_drawdown_pct": 9.0,
            "closed_trades": 4,
            "total_return_pct": 12.0,
            "sharpe": 0.5,
            "calmar": 1.0,
        }
        bad = {
            "profit_factor": 0.8,
            "max_drawdown_pct": 4.0,
            "closed_trades": 4,
            "total_return_pct": 12.0,
            "sharpe": 0.5,
            "calmar": 1.0,
        }

        self.assertTrue(passes_gate(good))
        self.assertFalse(passes_gate(bad))

    def test_top_signal_gate_requires_full_5y_and_3y(self):
        good = {
            "profit_factor": 2.1,
            "max_drawdown_pct": 9.0,
            "closed_trades": 4,
            "total_return_pct": 12.0,
            "sharpe": 0.5,
            "calmar": 1.0,
        }
        bad = {
            "profit_factor": 0.8,
            "max_drawdown_pct": 4.0,
            "closed_trades": 4,
            "total_return_pct": 12.0,
            "sharpe": 0.5,
            "calmar": 1.0,
        }

        self.assertTrue(passes_multi_year_gate({"full": good, "recent_5y": good, "recent_3y": good}))
        self.assertFalse(passes_multi_year_gate({"full": good, "recent_5y": bad, "recent_3y": good}))

    def test_free_data_bars_are_deduped_and_sorted(self):
        bars = _dedupe_sorted_bars(
            [
                {"timestamp": "2026-01-02", "close": 102.0},
                {"timestamp": "2026-01-01", "close": 100.0},
                {"timestamp": "2026-01-02", "close": 103.0},
            ]
        )

        self.assertEqual([bar["timestamp"] for bar in bars], ["2026-01-01", "2026-01-02"])
        self.assertEqual(bars[-1]["close"], 103.0)

    def test_default_equity_universe_is_broader_than_initial_scan(self):
        symbols = default_equity_symbols()

        self.assertGreaterEqual(len(symbols), 50)
        self.assertIn("SPY", symbols)
        self.assertIn("NVDA", symbols)

    def test_runner_heartbeat_fallback_uses_alpaca_snapshot(self):
        calls = {
            "/v2/account": {"portfolio_value": "100000", "buying_power": "90000"},
            "/v2/positions": [
                {
                    "symbol": "SPY",
                    "qty": "13",
                    "current_price": "720.65",
                    "market_value": "9368.45",
                    "unrealized_pl": "113.24",
                }
            ],
            "/v2/clock": {"is_open": False},
        }
        original_get = runner_heartbeat_api._alpaca_get
        runner_heartbeat_api._alpaca_get = lambda path, params=None: calls[path]
        try:
            payload = runner_heartbeat_api._fallback_heartbeat()
        finally:
            runner_heartbeat_api._alpaca_get = original_get

        self.assertEqual(payload["status"], "alpaca-paper-fallback")
        self.assertEqual(payload["latest_decision"], "hold")
        self.assertEqual(payload["latest_reason"], "position_protected")
        self.assertEqual(payload["position_qty"], 13.0)
        self.assertFalse(payload["stale"])

    def test_walk_forward_summary_requires_consistent_windows(self):
        good_window = {
            "pass": True,
            "total_return_pct": 4.0,
            "max_drawdown_pct": 6.0,
            "sharpe": 0.6,
            "calmar": 0.7,
            "profit_factor": 2.0,
            "closed_trades": 4,
        }
        bad_window = {
            "pass": False,
            "total_return_pct": -1.0,
            "max_drawdown_pct": 5.0,
            "sharpe": -0.1,
            "calmar": -0.1,
            "profit_factor": 0.8,
            "closed_trades": 3,
        }

        summary = summarize_windows([good_window, good_window, bad_window])

        self.assertEqual(summary["window_count"], 3)
        self.assertGreaterEqual(summary["positive_rate_pct"], 60.0)
        self.assertTrue(passes_walk_forward(summary))


if __name__ == "__main__":
    unittest.main()
