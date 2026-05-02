"""Print Apex Alpaca paper status without placing orders."""
from __future__ import annotations

import sys
from pathlib import Path

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus

ROOT_PATH = Path(__file__).resolve().parents[1]
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

from scripts.alpaca_paper_runner import ROOT, load_env


def main() -> None:
    env = load_env()
    client = TradingClient(env["APCA_API_KEY_ID"], env["APCA_API_SECRET_KEY"], paper=True)
    account = client.get_account()
    positions = client.get_all_positions()
    orders = client.get_orders(GetOrdersRequest(status=QueryOrderStatus.ALL, limit=5))

    print("Apex Alpaca Paper Status")
    print(f"account_status: {account.status}")
    print(f"trading_blocked: {account.trading_blocked}")
    print(f"portfolio_value: {account.portfolio_value}")
    print(f"buying_power: {account.buying_power}")
    print(f"cash: {account.cash}")
    print("")
    print("Positions")
    if not positions:
        print("- none")
    for p in positions:
        print(
            f"- {p.symbol}: qty={p.qty} side={p.side} entry={p.avg_entry_price} "
            f"current={p.current_price} unrealized_pl={p.unrealized_pl}"
        )
    print("")
    print("Recent Orders")
    if not orders:
        print("- none")
    for o in orders:
        print(f"- {o.submitted_at} {o.symbol} {o.side} {o.type} qty={o.qty} status={o.status}")

    heartbeat = ROOT / "runtime" / "alpaca_paper_runner.heartbeat"
    print("")
    print("Runner")
    print(f"heartbeat: {_read_text(heartbeat)}")
    print(f"journal: {ROOT / 'data' / 'paper_journal.csv'}")
    print(f"log: {ROOT / 'logs' / 'alpaca_paper_runner.log'}")


def _read_text(path: Path) -> str:
    if not path.exists():
        return "missing"
    return path.read_text(encoding="utf-8").strip()


if __name__ == "__main__":
    main()
