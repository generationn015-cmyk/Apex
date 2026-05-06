import unittest
import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.alpaca_paper_runner import (
    Decision,
    RunnerResult,
    append_journal,
    decide_signal,
    evaluate_risk,
    parse_symbols,
    pressure_rotation_symbol,
    replace_to_enter_exit_symbol,
    short_pressure_rotation_symbol,
)
from scripts.apex_alerts import build_notifications, evaluate_alerts
from scripts.backtest_top_signals import passes_multi_year_gate
from scripts.backtest_spy_strategy import _dedupe_sorted_bars
from scripts.backtest_spy_strategy import run_backtest
from scripts.equity_universe import default_equity_symbols
from scripts.backtest_binance_strategy import bars_from_binance_rows
from scripts.backtest_binance_multi_year import latest_complete_month, month_range
from scripts.crypto_universe import default_crypto_symbols
from scripts.download_binance_klines import binance_monthly_kline_url
from scripts.download_binance_klines import ensure_metadata
from scripts.generate_backtest_tearsheet import monthly_returns
from scripts.generate_backtest_tearsheet import write_index
from scripts.run_equity_backtest_report import passes_gate
from scripts.validate_cache_metadata import infer_binance_file, validate_file
from scripts.walk_forward_backtest import passes_walk_forward, summarize_windows


ROOT = Path(__file__).resolve().parents[1]
RUNNER_HEARTBEAT_SPEC = importlib.util.spec_from_file_location(
    "runner_heartbeat_api",
    ROOT / "api" / "runner-heartbeat.py",
)
runner_heartbeat_api = importlib.util.module_from_spec(RUNNER_HEARTBEAT_SPEC)
RUNNER_HEARTBEAT_SPEC.loader.exec_module(runner_heartbeat_api)


class FakePosition:
    def __init__(self, symbol, qty, unrealized_plpc):
        self.symbol = symbol
        self.qty = qty
        self.unrealized_plpc = unrealized_plpc
        self.unrealized_pl = 100.0
        self.avg_entry_price = 120.0
        self.current_price = 118.0
        self.market_value = abs(float(qty)) * self.current_price


class FakeReplacementTrading:
    def __init__(self):
        self.orders = []

    def get_account(self):
        return FakeAccount()

    def get_clock(self):
        clock = FakeClock()
        clock.is_open = True
        return clock

    def get_all_positions(self):
        return [
            FakePosition("VTI", 2, 0.004),
            FakePosition("XLK", 17, 0.014),
            FakePosition("QQQ", 4, 0.012),
        ]

    def submit_order(self, order_data):
        self.orders.append(order_data)
        return order_data


class FakeAccount:
    portfolio_value = 100_000.0
    buying_power = 150_000.0
    last_equity = 99_000.0


class FakeClock:
    is_open = False


class FakeTrading:
    def get_account(self):
        return FakeAccount()

    def get_clock(self):
        return FakeClock()

    def get_all_positions(self):
        return [FakePosition("MRK", -150, 0.01)]


class FakeData:
    pass


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

    def test_rotates_profitable_position_when_exposure_is_capped(self):
        bars = [{"close": 100 + i * 0.5} for i in range(60)]

        decision = decide_signal(
            bars,
            has_position=True,
            entry_price=100.0,
            latest_price=104.0,
            exposure_pct=0.82,
            unrealized_pl_pct=0.04,
        )

        self.assertEqual(decision.action, "sell")
        self.assertEqual(decision.reason, "rotation_take_profit")

    def test_rotates_lagging_position_when_exposure_is_capped(self):
        bars = [{"close": 100 + i * 0.2} for i in range(55)] + [{"close": 98.0} for _ in range(5)]

        decision = decide_signal(
            bars,
            has_position=True,
            entry_price=100.0,
            latest_price=99.0,
            exposure_pct=0.82,
            unrealized_pl_pct=-0.01,
        )

        self.assertEqual(decision.action, "sell")
        self.assertEqual(decision.reason, "rotation_laggard")

    def test_rotates_profitable_position_when_slot_pressure_is_high(self):
        bars = [{"close": 100 + i * 0.5} for i in range(60)]

        decision = decide_signal(
            bars,
            has_position=True,
            entry_price=100.0,
            latest_price=102.0,
            unrealized_pl_pct=0.02,
            slot_pressure=True,
        )

        self.assertEqual(decision.action, "sell")
        self.assertEqual(decision.reason, "slot_pressure_take_profit")

    def test_covers_profitable_short_when_short_sleeve_is_high(self):
        bars = [{"close": 130 - i * 0.5} for i in range(60)]

        decision = decide_signal(
            bars,
            has_position=False,
            entry_price=120.0,
            latest_price=118.0,
            unrealized_pl_pct=0.01,
            position_qty=-10,
            allow_short=True,
            short_pressure=True,
        )

        self.assertEqual(decision.action, "buy")
        self.assertEqual(decision.reason, "short_sleeve_take_profit")

    def test_pressure_rotation_targets_weakest_long_first(self):
        positions = {
            "SPY": FakePosition("SPY", 20, 0.03),
            "SMH": FakePosition("SMH", 5, -0.004),
            "AMZN": FakePosition("AMZN", 10, -0.001),
        }

        self.assertEqual(pressure_rotation_symbol(positions), "SMH")

    def test_short_pressure_rotation_targets_best_profitable_short(self):
        positions = {
            "COP": FakePosition("COP", -21, 0.009),
            "MRK": FakePosition("MRK", -22, 0.006),
            "XLV": FakePosition("XLV", -17, -0.004),
        }

        self.assertEqual(short_pressure_rotation_symbol(positions), "COP")

    def test_replace_to_enter_targets_weakest_allowed_long(self):
        positions = {
            "VTI": FakePosition("VTI", 2, 0.004),
            "XLK": FakePosition("XLK", 17, 0.011),
            "QQQ": FakePosition("QQQ", 4, 0.006),
        }

        self.assertEqual(replace_to_enter_exit_symbol(positions, exclude_symbol="SPY"), "VTI")

    def test_replace_to_enter_skips_strong_longs(self):
        positions = {
            "XLK": FakePosition("XLK", 17, 0.011),
            "QQQ": FakePosition("QQQ", 4, 0.012),
        }

        self.assertIsNone(replace_to_enter_exit_symbol(positions, exclude_symbol="SPY"))

    def test_max_position_buy_signal_swaps_weak_slot_into_target(self):
        import scripts.alpaca_paper_runner as runner

        original_fetch_bars = runner.fetch_bars
        original_load_historical = runner.load_historical_pass_symbols
        original_max_open_positions = runner.MAX_OPEN_POSITIONS
        try:
            runner.fetch_bars = lambda data, symbol, limit=100: [{"close": 100 + i * 0.5} for i in range(60)]
            runner.load_historical_pass_symbols = lambda: {"SPY"}
            runner.MAX_OPEN_POSITIONS = 3
            trading = FakeReplacementTrading()

            result = runner.run_once(
                "SPY",
                max_notional=3000.0,
                dry_run=False,
                trading=trading,
                data=FakeData(),
            )

            self.assertTrue(result.decision.reason.startswith("replace_to_enter:SPY_free:VTI"))
            self.assertEqual(len(trading.orders), 2)
            self.assertEqual(trading.orders[0].symbol, "VTI")
            self.assertEqual(trading.orders[1].symbol, "SPY")
        finally:
            runner.fetch_bars = original_fetch_bars
            runner.load_historical_pass_symbols = original_load_historical
            runner.MAX_OPEN_POSITIONS = original_max_open_positions

    def test_historical_gate_does_not_block_short_cover(self):
        import scripts.alpaca_paper_runner as runner

        original_fetch_bars = runner.fetch_bars
        original_load_historical = runner.load_historical_pass_symbols
        try:
            runner.fetch_bars = lambda data, symbol, limit=100: [{"close": 130 - i * 0.5} for i in range(60)]
            runner.load_historical_pass_symbols = lambda: {"SPY"}

            result = runner.run_once(
                "MRK",
                max_notional=3000.0,
                dry_run=True,
                trading=FakeTrading(),
                data=FakeData(),
            )

            self.assertEqual(result.decision.action, "buy")
            self.assertEqual(result.decision.reason, "short_sleeve_take_profit")
        finally:
            runner.fetch_bars = original_fetch_bars
            runner.load_historical_pass_symbols = original_load_historical

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

    def test_opens_short_when_enabled_in_downtrend(self):
        bars = [
            {"close": 130 - i * 0.5}
            for i in range(60)
        ]

        decision = decide_signal(bars, has_position=False, entry_price=0, allow_short=True)

        self.assertEqual(decision.action, "sell")
        self.assertEqual(decision.reason, "short_downtrend")

    def test_covers_short_when_trend_reverses(self):
        bars = [
            {"close": 100 + i * 0.5}
            for i in range(60)
        ]

        decision = decide_signal(
            bars,
            has_position=False,
            entry_price=100.0,
            latest_price=104.0,
            position_qty=-10,
            allow_short=True,
        )

        self.assertEqual(decision.action, "buy")
        self.assertEqual(decision.reason, "short_stop_2pct")

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
            market_value=44_000,
            day_pl=0,
            unrealized_pl=0,
            pending_buy_notional=2_000,
        )

        self.assertEqual(flags, ["projected-exposure-over-45%"])

    def test_risk_allows_measured_multi_symbol_scale(self):
        flags = evaluate_risk(
            equity=100_000,
            buying_power=50_000,
            market_value=10_000,
            day_pl=0,
            unrealized_pl=0,
            pending_buy_notional=5_000,
            open_position_count=1,
        )

        self.assertEqual(flags, [])

    def test_risk_blocks_oversized_short_sleeve(self):
        flags = evaluate_risk(
            equity=100_000,
            buying_power=50_000,
            market_value=80_000,
            day_pl=0,
            unrealized_pl=0,
            pending_short_notional=5_000,
            short_market_value=12_000,
        )

        self.assertIn("projected-short-exposure-over-12%", flags)

    def test_parse_symbols_dedupes_watchlist(self):
        self.assertEqual(parse_symbols("spy, NVDA,spy, qqq"), ["SPY", "NVDA", "QQQ"])

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

    def test_backtest_can_return_tearsheet_details(self):
        bars = [{"timestamp": f"2026-01-{i + 1:02d}", "close": 100.0 + i} for i in range(70)]

        metrics = run_backtest(bars, initial_cash=10_000.0, max_notional=1_000.0, include_details=True)

        self.assertIn("equity_curve", metrics)
        self.assertIn("trades_detail", metrics)
        self.assertEqual(len(metrics["equity_curve"]), len(bars))

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

    def test_binance_cache_metadata_sidecar_is_written(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "BTCUSDT-1h-2024-01.csv"
            path.write_text(
                "open_time,open,high,low,close,volume,close_time,quote_volume,trade_count,taker_buy_base,taker_buy_quote,ignore\n"
                "1704067200000,1,2,1,2,10,1704070799999,20,1,5,10,0\n",
                encoding="utf-8",
            )

            meta_path = ensure_metadata(path, "BTCUSDT", "1h", "2024-01", "spot", "https://example.test", "cache")

            self.assertTrue(meta_path.exists())
            self.assertIn('"row_count": 1', meta_path.read_text(encoding="utf-8"))

    def test_monthly_returns_summarize_tearsheet_curve(self):
        rows = monthly_returns(
            [
                {"timestamp": "2026-01-01", "equity": 100.0},
                {"timestamp": "2026-01-31", "equity": 110.0},
                {"timestamp": "2026-02-01", "equity": 110.0},
                {"timestamp": "2026-02-28", "equity": 99.0},
            ]
        )

        self.assertEqual(rows[0], {"month": "2026-01", "return_pct": 10.0})
        self.assertEqual(rows[1], {"month": "2026-02", "return_pct": -10.0})

    def test_tearsheet_index_is_written(self):
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            index_path = write_index(
                [
                    {
                        "symbol": "SPY",
                        "metrics": {
                            "profit_factor": 2.1,
                            "max_drawdown_pct": 9.0,
                            "closed_trades": 4,
                            "total_return_pct": 12.0,
                            "sharpe": 0.5,
                            "calmar": 1.0,
                        },
                    }
                ],
                output_dir,
            )

            self.assertTrue(index_path.exists())
            self.assertIn("spy-tearsheet.md", index_path.read_text(encoding="utf-8"))

    def test_cache_validator_flags_missing_metadata(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "BTCUSDT-1h-2024-01.csv"
            path.write_text(
                "open_time,open,high,low,close,volume,close_time,quote_volume,trade_count,taker_buy_base,taker_buy_quote,ignore\n"
                "1704067200000,1,2,1,2,10,1704070799999,20,1,5,10,0\n",
                encoding="utf-8",
            )

            row = validate_file(path)

            self.assertFalse(row["ok"])
            self.assertIn("missing-metadata", row["warnings"])

    def test_cache_validator_can_repair_missing_metadata(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "BTCUSDT-1h-2024-01.csv"
            path.write_text(
                "open_time,open,high,low,close,volume,close_time,quote_volume,trade_count,taker_buy_base,taker_buy_quote,ignore\n"
                "1704067200000,1,2,1,2,10,1704070799999,20,1,5,10,0\n",
                encoding="utf-8",
            )

            row = validate_file(path, repair=True)

            self.assertTrue(row["ok"])
            self.assertEqual(infer_binance_file(path)["symbol"], "BTCUSDT")

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
