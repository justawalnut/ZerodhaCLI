"""Command dispatcher and interactive shell for ZerodhaCLI."""

from __future__ import annotations

import asyncio
import shlex
import sys
import atexit
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Sequence, Tuple

import httpx
from rich.console import Console

from ..core.config import AppConfig
from ..core.models import OrderRequest, OrderType, Position, Product, Validity, Variety
from ..services.container import ServiceContainer
from ..utils.integrity import IntegrityReport, perform_integrity_check

console = Console()

BANNER = ""

DEFAULT_EXCHANGE = "NSE"
PROMPT = "z> "


class CommandError(Exception):
    """Raised when command parsing or validation fails."""


_GLOBAL_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_GLOBAL_LOOP)


def _shutdown_loop() -> None:
    pending = [task for task in asyncio.all_tasks(_GLOBAL_LOOP) if not task.done()]
    for task in pending:
        task.cancel()
    if pending:
        _GLOBAL_LOOP.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    _GLOBAL_LOOP.close()


atexit.register(_shutdown_loop)


def _run(coro):
    return _GLOBAL_LOOP.run_until_complete(coro)


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _mode_tag(config: AppConfig) -> str:
    return "SIM" if config.dry_run else "LIVE"


def _format_price(order_type: OrderType, price: Optional[float]) -> str:
    if order_type == OrderType.MARKET or price is None:
        return "@market"
    return f"@₹{price:.2f}"


def _format_trigger(trigger: Optional[float]) -> str:
    if trigger is None:
        return ""
    return f" trigger=₹{trigger:.2f}"


def _format_money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}₹{abs(value):.2f}"


def _print_integrity_report(report: IntegrityReport, config: AppConfig) -> None:
    mode = _mode_tag(config)
    ts = _timestamp()
    status = "OK" if report.ok else "WARN"
    digest_text = report.digest or "<empty>"
    console.print(f"[{ts}] {mode} INTEGRITY {status} (config hash {digest_text})")
    for issue in report.issues:
        console.print(f"- {issue}")


@dataclass(slots=True)
class CliSession:
    """Context manager for wiring services and integrity checks."""

    services: ServiceContainer
    integrity: IntegrityReport

    @classmethod
    def create(cls, dry_run_override: Optional[bool]) -> "CliSession":
        overrides = {}
        if dry_run_override is not None:
            overrides["dry_run"] = dry_run_override
        config = AppConfig.load(overrides)
        services = ServiceContainer.build(config)
        report = perform_integrity_check(services.config)
        return cls(services=services, integrity=report)

    def __enter__(self) -> "CliSession":
        _print_integrity_report(self.integrity, self.services.config)
        try:
            _run(self.services.bootstrap())
        except Exception as exc:  # pragma: no cover - best-effort bootstrap
            console.print(
                f"[yellow]Warning[/yellow]: failed to bootstrap live services ({exc}). Proceeding without ticker."
            )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _run(self.services.aclose())


class CommandDispatcher:
    """Parse and execute trading commands."""

    def __init__(self, session: CliSession) -> None:
        self.session = session
        self.services = session.services
        try:
            self.default_product = Product(self.services.config.default_product)
        except ValueError:
            self.default_product = Product.MIS

    def execute(self, tokens: Sequence[str]) -> int:
        if not tokens:
            return 0
        if tokens[0].lower() == "z":
            tokens = tokens[1:]
            if not tokens:
                return 0
        command = tokens[0].lower()
        handler = getattr(self, f"do_{command}", None)
        if handler is None:
            raise CommandError(f"Unknown command: {command}")
        return handler(tokens[1:]) or 0

    def do_help(self, _: Sequence[str]) -> int:
        console.print(
            "Available commands: buy, sell, sl, close, cancel, scale, chase, orders, pos, history, help, quit"
        )
        console.print("Use --dry-run or --live when launching to toggle mode. Ctrl+D or 'quit' exits.")
        return 0

    def do_buy(self, args: Sequence[str]) -> int:
        symbol, qty, order_type, price = self._parse_basic_order_args(args, "buy")
        order = self._build_order(symbol, qty, "BUY", order_type, price)
        response = _run(self.services.orders.place_order(order))
        self._render_order(order, response)
        return 0

    def do_sell(self, args: Sequence[str]) -> int:
        symbol, qty, order_type, price = self._parse_basic_order_args(args, "sell")
        order = self._build_order(symbol, qty, "SELL", order_type, price)
        response = _run(self.services.orders.place_order(order))
        self._render_order(order, response)
        return 0

    def do_sl(self, args: Sequence[str]) -> int:
        if len(args) < 3:
            raise CommandError("Usage: sl SYMBOL QTY TRIGGER [PRICE]")
        symbol = args[0]
        quantity = self._parse_quantity(args[1])
        trigger = self._parse_float(args[2], "trigger")
        price = self._parse_optional_float(args[3]) if len(args) > 3 else None
        order_type = OrderType.SL if price is not None else OrderType.SL_M
        order = OrderRequest(
            tradingsymbol=symbol,
            exchange=DEFAULT_EXCHANGE,
            transaction_type="SELL",
            quantity=quantity,
            order_type=order_type,
            product=self.default_product,
            price=price,
            trigger_price=trigger,
            validity=Validity.DAY,
            variety=Variety.REGULAR,
        )
        response = _run(self.services.orders.place_order(order))
        self._render_order(order, response)
        return 0

    def do_close(self, args: Sequence[str]) -> int:
        if not args:
            raise CommandError("Usage: close SYMBOL")
        symbol = args[0]
        if self.services.config.dry_run:
            positions = self.services.orders.simulated_positions()
        else:
            positions = _run(self.services.portfolio.positions())
        match = self._select_position(positions, symbol)
        if match is None:
            raise CommandError(f"No open position for {symbol}")
        response = _run(self.services.orders.close_position(match))
        preview = OrderRequest(
            tradingsymbol=match.tradingsymbol,
            exchange=match.exchange,
            transaction_type="BUY" if match.quantity < 0 else "SELL",
            quantity=abs(match.quantity),
            order_type=OrderType.MARKET,
            product=match.product,
        )
        self._render_order(preview, response, extra="[close]")
        return 0

    def do_cancel(self, args: Sequence[str]) -> int:
        if not args:
            raise CommandError("Usage: cancel ORDERID | cancel all")
        open_orders = _run(self.services.orders.list_open_orders())
        if len(args) == 1 and args[0].lower() == "all":
            if not open_orders:
                console.print("No open orders to cancel.")
                return 0
            responses = _run(self.services.orders.cancel_orders(open_orders))
            self._render_cancelled(responses)
            return 0
        order_id = args[0]
        match = next((order for order in open_orders if order.order_id == order_id), None)
        variety = match.variety if match is not None else None
        responses = _run(self.services.orders.cancel_orders([(order_id, variety)]))
        self._render_cancelled(responses)
        return 0

    def do_scale(self, args: Sequence[str]) -> int:
        if len(args) != 5:
            raise CommandError("Usage: scale SYMBOL QTY START END COUNT")
        symbol = args[0]
        quantity = self._parse_quantity(args[1])
        start = self._parse_float(args[2], "start")
        end = self._parse_float(args[3], "end")
        count = self._parse_int(args[4], "count", minimum=1)
        template = OrderRequest(
            tradingsymbol=symbol,
            exchange=DEFAULT_EXCHANGE,
            transaction_type="BUY",
            quantity=quantity,
            order_type=OrderType.LIMIT,
            product=self.default_product,
            validity=Validity.DAY,
            autoslice=self.services.config.autoslice or None,
        )
        responses = _run(self.services.orders.scale_order(template, count, start, end))
        self._render_scale(template, responses, start, end, count)
        return 0

    def do_chase(self, args: Sequence[str]) -> int:
        if len(args) != 5:
            raise CommandError("Usage: chase SYMBOL QTY PRICE MAX_MOVES TICK")
        symbol = args[0]
        quantity = self._parse_quantity(args[1])
        price = self._parse_float(args[2], "price")
        max_moves = self._parse_int(args[3], "max_moves", minimum=1)
        tick = self._parse_float(args[4], "tick")
        order = OrderRequest(
            tradingsymbol=symbol,
            exchange=DEFAULT_EXCHANGE,
            transaction_type="BUY",
            quantity=quantity,
            order_type=OrderType.LIMIT,
            product=self.default_product,
            price=price,
            autoslice=self.services.config.autoslice or None,
        )
        response = _run(
            self.services.orders.chase_order(
                order,
                max_moves=max_moves,
                tick_size=tick,
            )
        )
        self._render_order(order, response, extra=f"[chase max_moves={max_moves} tick={tick}]")
        return 0

    def do_orders(self, _: Sequence[str]) -> int:
        open_orders = _run(self.services.orders.list_open_orders())
        ts = _timestamp()
        mode = _mode_tag(self.services.config)
        console.print(f"[{ts}] {mode} OPEN ORDERS ({len(open_orders)})")
        if not open_orders:
            console.print("None")
            return 0
        for order in open_orders:
            price = _format_price(OrderType.LIMIT if order.price else OrderType.MARKET, order.price)
            console.print(
                f"- {order.order_id}: {order.transaction_type} {order.quantity} {order.tradingsymbol} {price} status={order.status}"
            )
        return 0

    def do_pos(self, _: Sequence[str]) -> int:
        if self.services.config.dry_run:
            positions = self.services.orders.simulated_positions()
        else:
            positions = _run(self.services.portfolio.positions())
            positions = list(positions)
            try:
                _run(self.services.quotes.enrich_positions(positions, force=True))
            except httpx.HTTPError as exc:
                console.print(f"[yellow]Warning[/yellow]: quote lookup failed ({exc}).")
        positions = list(positions)
        ts = _timestamp()
        mode = _mode_tag(self.services.config)
        console.print(f"[{ts}] {mode} POSITIONS:")
        if not positions:
            console.print("None")
            return 0
        total_unrealized = 0.0
        total_day = 0.0
        for position in positions:
            mark = position.last_price if position.last_price is not None else position.average_price
            unrealized = (mark - position.average_price) * position.quantity
            total_unrealized += unrealized
            total_day += position.pnl
            direction = "+" if position.quantity >= 0 else ""
            mark_display = f"₹{mark:.2f}" if mark is not None else "--"
            console.print(
                f"- {position.exchange}:{position.tradingsymbol}: {direction}{position.quantity} @₹{position.average_price:.2f} "
                f"mark={mark_display} pnl={_format_money(unrealized)} day={_format_money(position.pnl)}"
            )
        console.print(f"Unrealized PnL: {_format_money(total_unrealized)}")
        console.print(f"Day PnL: {_format_money(total_day)}")
        return 0

    def do_history(self, args: Sequence[str]) -> int:
        limit = self._parse_int(args[0], "count", minimum=1) if args else 10
        records = _run(self.services.orders.recent_history(limit))
        ts = _timestamp()
        mode = _mode_tag(self.services.config)
        console.print(f"[{ts}] {mode} HISTORY (last {limit})")
        if not records:
            console.print("None")
            return 0
        for record in records:
            price = _format_price(record.request.order_type, record.request.price)
            stamp = record.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            console.print(
                f"- {stamp} {record.response.order_id} {record.request.transaction_type} {record.request.quantity} {record.request.tradingsymbol} {price} status={record.response.status}"
            )
        return 0

    def do_quit(self, _: Sequence[str]) -> int:
        raise SystemExit(0)

    # Parsing helpers -------------------------------------------------

    def _parse_basic_order_args(
        self, args: Sequence[str], action: str
    ) -> Tuple[str, int, OrderType, Optional[float]]:
        if len(args) < 2:
            raise CommandError(f"Usage: {action} SYMBOL QTY [@PRICE]")
        symbol = args[0]
        quantity = self._parse_quantity(args[1])
        price_token = args[2] if len(args) > 2 else None
        order_type, price = self._parse_price_token(price_token)
        return symbol, quantity, order_type, price

    def _parse_price_token(self, token: Optional[str]) -> Tuple[OrderType, Optional[float]]:
        if token is None:
            return OrderType.MARKET, None
        raw = token[1:] if token.startswith("@") else token
        lowered = raw.lower()
        if lowered in {"market", "mkt"}:
            return OrderType.MARKET, None
        try:
            value = float(raw)
        except ValueError as exc:
            raise CommandError("Invalid price token; expected @<number>") from exc
        return OrderType.LIMIT, value

    def _parse_quantity(self, token: str) -> int:
        return self._parse_int(token, "quantity", minimum=1)

    def _parse_int(self, token: str, label: str, *, minimum: int = 0) -> int:
        try:
            value = int(token)
        except ValueError as exc:
            raise CommandError(f"Invalid {label}; expected integer") from exc
        if value < minimum:
            raise CommandError(f"{label} must be >= {minimum}")
        return value

    def _parse_float(self, token: str, label: str) -> float:
        try:
            return float(token)
        except ValueError as exc:
            raise CommandError(f"Invalid {label}; expected number") from exc

    def _parse_optional_float(self, token: str) -> Optional[float]:
        if token.lower() in {"market", "mkt"}:
            return None
        return self._parse_float(token, "price")

    def _build_order(
        self,
        symbol: str,
        quantity: int,
        side: str,
        order_type: OrderType,
        price: Optional[float],
    ) -> OrderRequest:
        autoslice = self.services.config.autoslice if self.services.config.autoslice else None
        return OrderRequest(
            tradingsymbol=symbol,
            exchange=DEFAULT_EXCHANGE,
            transaction_type=side.upper(),
            quantity=quantity,
            order_type=order_type,
            product=self.default_product,
            price=price,
            validity=Validity.DAY,
            variety=Variety.REGULAR,
            market_protection=self.services.config.market_protection,
            autoslice=autoslice,
        )

    def _render_order(self, order: OrderRequest, response) -> None:
        ts = _timestamp()
        mode = _mode_tag(self.services.config)
        price = _format_price(order.order_type, order.price)
        trigger = _format_trigger(order.trigger_price)
        console.print(
            f"[{ts}] {mode} {order.transaction_type} {order.quantity} {order.tradingsymbol} {price}{trigger} -> order_id={response.order_id}"
        )
        console.print(f"status={response.status}")

    def _render_scale(
        self,
        template: OrderRequest,
        responses: Sequence,
        start: float,
        end: float,
        count: int,
    ) -> None:
        ts = _timestamp()
        mode = _mode_tag(self.services.config)
        order_ids = [resp.order_id for resp in responses]
        statuses = {resp.status for resp in responses}
        status_text = statuses.pop() if len(statuses) == 1 else str(list(statuses))
        console.print(
            f"[{ts}] {mode} SCALE {template.transaction_type} {template.quantity} {template.tradingsymbol} between {start}-{end} ({count} legs) -> order_ids={order_ids}"
        )
        console.print(f"status={status_text}")

    def _render_cancelled(self, responses) -> None:
        ts = _timestamp()
        mode = _mode_tag(self.services.config)
        order_ids = [resp.order_id for resp in responses]
        console.print(f"[{ts}] {mode} CANCEL -> order_ids={order_ids}")
        statuses = {resp.status for resp in responses}
        status_text = statuses.pop() if len(statuses) == 1 else str(list(statuses))
        console.print(f"status={status_text}")

    def _select_position(self, positions: Sequence[Position], token: str) -> Optional[Position]:
        token_upper = token.upper()
        if ":" in token_upper:
            for position in positions:
                if f"{position.exchange}:{position.tradingsymbol}".upper() == token_upper:
                    return position
        else:
            matches = [position for position in positions if position.tradingsymbol.upper() == token_upper]
            if len(matches) == 1:
                return matches[0]
        return None


def _extract_mode_override(argv: Sequence[str]) -> Tuple[Optional[bool], List[str]]:
    dry_run_override: Optional[bool] = None
    remaining: List[str] = []
    for arg in argv:
        if arg == "--dry-run":
            dry_run_override = True
            continue
        if arg == "--live":
            dry_run_override = False
            continue
        if arg in {"-h", "--help"}:
            return dry_run_override, ["help"]
        remaining.append(arg)
    return dry_run_override, remaining


def run_cli(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    dry_run_override, remaining = _extract_mode_override(argv)

    if not remaining:
        return run_repl(dry_run_override)

    with CliSession.create(dry_run_override) as session:
        dispatcher = CommandDispatcher(session)
        try:
            return dispatcher.execute(remaining)
        except CommandError as exc:
            console.print(f"Error: {exc}")
            return 1
        except httpx.HTTPStatusError as exc:
            console.print(f"HTTP error {exc.response.status_code}: {exc.response.text}")
            return 1
        except httpx.HTTPError as exc:
            console.print(f"HTTP error: {exc}")
            return 1


def run_repl(dry_run_override: Optional[bool] = None) -> int:
    with CliSession.create(dry_run_override) as session:
        dispatcher = CommandDispatcher(session)
        console.print(BANNER)
        console.print("Type 'help' for available commands, 'quit' to exit.")
        while True:
            try:
                raw = input(PROMPT)
            except EOFError:
                console.print("\nExited.")
                return 0
            except KeyboardInterrupt:
                console.print("\nInterrupted. Type 'quit' to exit.")
                continue
            command_line = raw.strip()
            if not command_line:
                continue
            try:
                tokens = shlex.split(command_line)
            except ValueError as exc:
                console.print(f"Parse error: {exc}")
                continue
            if not tokens:
                continue
            if tokens[0].lower() in {"quit", "exit"}:
                console.print("Bye.")
                return 0
            try:
                dispatcher.execute(tokens)
            except CommandError as exc:
                console.print(f"Error: {exc}")
            except SystemExit:
                console.print("Bye.")
                return 0
            except httpx.HTTPStatusError as exc:
                console.print(f"HTTP error {exc.response.status_code}: {exc.response.text}")
            except httpx.HTTPError as exc:
                console.print(f"HTTP error: {exc}")
    return 0


__all__ = ["run_cli", "run_repl"]
