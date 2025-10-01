"""Typer-based command layer for ZerodhaCLI."""

from __future__ import annotations

import asyncio
import atexit
from typing import List, Optional

import typer
from rich.console import Console

from ..core.config import AppConfig
from ..core.models import GTTLeg, GTTRequest, OrderRequest, OrderType, Product, Validity, Variety
from ..services.container import ServiceContainer

console = Console()
app = typer.Typer(help="Trade on Zerodha Kite with Insilico-style ergonomics.")
gtt_app = typer.Typer(help="Manage Zerodha GTT triggers.")


def _run(coro):
    return asyncio.run(coro)


def _mode_tag(dry_run: bool) -> str:
    return "[yellow]SIM[/yellow]" if dry_run else "[green]LIVE[/green]"


def _format_price(order: OrderRequest) -> str:
    if order.order_type == OrderType.MARKET:
        return "market"
    if order.price is None:
        return "--"
    return f"₹{order.price:.2f}"


def _render_order_result(services: ServiceContainer, order: OrderRequest, response, extra: Optional[str] = None) -> None:
    trigger_text = f" trigger=₹{order.trigger_price:.2f}" if order.trigger_price is not None else ""
    extra_text = f" {extra}" if extra else ""
    console.print(
        f"{_mode_tag(services.config.dry_run)} {order.transaction_type} {order.quantity} {order.tradingsymbol}"
        f" ({order.exchange}) {_format_price(order)}{trigger_text}{extra_text}"
        f" -> order_id={response.order_id} status={response.status}"
    )


def _render_simple_status(services: ServiceContainer, action: str, response) -> None:
    console.print(f"{_mode_tag(services.config.dry_run)} {action} -> order_id={response.order_id} status={response.status}")


def _register_cleanup(services: ServiceContainer) -> None:
    def _cleanup() -> None:
        try:
            asyncio.run(services.aclose())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(services.aclose())
            finally:
                loop.close()

    atexit.register(_cleanup)


@app.callback()
def main(
    ctx: typer.Context,
    dry_run: bool = typer.Option(True, "--dry-run/--live", help="Run orders in simulation mode (default) or hit the live Kite API."),
) -> None:
    """Initialise services and attach them to the CLI context."""

    config = AppConfig.load({"dry_run": dry_run})
    services = ServiceContainer.build(config)
    ctx.obj = {"services": services}
    _register_cleanup(services)
    _run(services.bootstrap())


@app.command()
def buy(
    ctx: typer.Context,
    symbol: str = typer.Argument(..., help="Trading symbol, e.g. NIFTY24JUNFUT"),
    quantity: int = typer.Argument(..., min=1),
    price: Optional[float] = typer.Option(None, help="Limit price; if omitted, market order is used."),
    exchange: str = typer.Option("NFO", help="Exchange segment."),
    product: Product = typer.Option(Product.MIS, case_sensitive=False),
    validity: Validity = typer.Option(Validity.DAY, case_sensitive=False),
    variety: Variety = typer.Option(Variety.REGULAR, case_sensitive=False),
) -> None:
    """Place a buy order."""

    services: ServiceContainer = ctx.obj["services"]
    order_type = OrderType.MARKET if price is None else OrderType.LIMIT
    order = OrderRequest(
        tradingsymbol=symbol,
        exchange=exchange,
        transaction_type="BUY",
        quantity=quantity,
        order_type=order_type,
        product=product,
        price=price,
        validity=validity,
        variety=variety,
        market_protection=services.config.market_protection,
        autoslice=services.config.autoslice,
    )
    response = _run(services.orders.place_order(order))
    _render_order_result(services, order, response)


@app.command()
def sell(
    ctx: typer.Context,
    symbol: str = typer.Argument(...),
    quantity: int = typer.Argument(..., min=1),
    price: Optional[float] = typer.Option(None),
    exchange: str = typer.Option("NFO"),
    product: Product = typer.Option(Product.MIS, case_sensitive=False),
    validity: Validity = typer.Option(Validity.DAY, case_sensitive=False),
    variety: Variety = typer.Option(Variety.REGULAR, case_sensitive=False),
) -> None:
    """Place a sell order."""

    services: ServiceContainer = ctx.obj["services"]
    order_type = OrderType.MARKET if price is None else OrderType.LIMIT
    order = OrderRequest(
        tradingsymbol=symbol,
        exchange=exchange,
        transaction_type="SELL",
        quantity=quantity,
        order_type=order_type,
        product=product,
        price=price,
        validity=validity,
        variety=variety,
        market_protection=services.config.market_protection,
        autoslice=services.config.autoslice,
    )
    response = _run(services.orders.place_order(order))
    _render_order_result(services, order, response)


@app.command()
def stop(
    ctx: typer.Context,
    symbol: str = typer.Argument(...),
    quantity: int = typer.Argument(..., min=1),
    trigger: float = typer.Option(..., help="Trigger price for the stop."),
    price: Optional[float] = typer.Option(None, help="Limit price for SL; omit for SL-M."),
    exchange: str = typer.Option("NFO"),
    product: Product = typer.Option(Product.MIS, case_sensitive=False),
    side: str = typer.Option("SELL", help="Side to place stop order (SELL/BUY)."),
) -> None:
    """Place a stop-loss order (SL or SL-M)."""

    services: ServiceContainer = ctx.obj["services"]
    order_type = OrderType.SL if price is not None else OrderType.SL_M
    order = OrderRequest(
        tradingsymbol=symbol,
        exchange=exchange,
        transaction_type=side.upper(),
        quantity=quantity,
        order_type=order_type,
        product=product,
        price=price,
        trigger_price=trigger,
    )
    response = _run(services.orders.place_order(order))
    _render_order_result(services, order, response, extra="[stop]")


@app.command()
def cancel(
    ctx: typer.Context,
    order_id: Optional[str] = typer.Option(None, "--id", help="Specific order id to cancel."),
    all: bool = typer.Option(False, help="Cancel all matching open orders."),
    side: Optional[str] = typer.Option(None, help="Filter open orders by BUY/SELL before cancellation."),
    count: Optional[int] = typer.Option(None, help="Cancel at most N orders after filtering."),
    latest: bool = typer.Option(False, help="Use most recent orders when selecting by count."),
) -> None:
    """Cancel one or more orders with Insilico-style scopes."""

    services: ServiceContainer = ctx.obj["services"]
    if order_id:
        responses = _run(services.orders.cancel_orders([order_id]))
        for resp in responses:
            _render_simple_status(services, "CANCEL", resp)
        return

    if latest and all:
        raise typer.BadParameter("--latest cannot be combined with --all; drop --latest or specify --count.")

    selection_count = None if all else (count or 1)
    matching = _run(services.orders.filter_orders(side=side, count=selection_count, latest=latest))
    if not matching:
        console.print("No matching open orders to cancel.")
        return
    responses = _run(services.orders.cancel_orders([order.order_id for order in matching]))
    for resp in responses:
        _render_simple_status(services, "CANCEL", resp)


@app.command()
def close(
    ctx: typer.Context,
    symbol: str = typer.Argument(..., help="Instrument to flatten, e.g. NFO:NIFTY24JUNFUT"),
    side: Optional[str] = typer.Option(None, help="Override exit side (BUY/SELL)."),
) -> None:
    """Close the provided position."""

    services: ServiceContainer = ctx.obj["services"]
    positions = _run(services.portfolio.index_by_symbol())
    if symbol not in positions:
        console.print(f"No open position for {symbol}")
        raise typer.Exit(code=1)
    preview_order = OrderRequest(
        tradingsymbol=positions[symbol].tradingsymbol,
        exchange=positions[symbol].exchange,
        transaction_type=side.upper() if side else ("BUY" if positions[symbol].quantity < 0 else "SELL"),
        quantity=abs(positions[symbol].quantity),
        order_type=OrderType.MARKET,
        product=positions[symbol].product,
        market_protection=services.config.market_protection,
        autoslice=services.config.autoslice,
    )
    response = _run(services.orders.close_position(positions[symbol], side=side))
    _render_order_result(services, preview_order, response, extra="[close]")


@app.command()
def scale(
    ctx: typer.Context,
    symbol: str = typer.Argument(...),
    count: int = typer.Option(3, min=1, help="Number of ladder orders."),
    start_price: float = typer.Option(..., help="Lower bound price."),
    end_price: float = typer.Option(..., help="Upper bound price."),
    side: str = typer.Option("BUY", help="Side to trade (BUY/SELL)."),
    quantity: int = typer.Option(..., min=1),
    exchange: str = typer.Option("NFO"),
    product: Product = typer.Option(Product.MIS, case_sensitive=False),
) -> None:
    """Ladder limit orders between two prices."""

    services: ServiceContainer = ctx.obj["services"]
    order = OrderRequest(
        tradingsymbol=symbol,
        exchange=exchange,
        transaction_type=side.upper(),
        quantity=quantity,
        order_type=OrderType.LIMIT,
        product=product,
        validity=Validity.DAY,
    )
    responses = _run(services.orders.scale_order(order, count, start_price, end_price))
    step = (end_price - start_price) / max(count - 1, 1)
    for idx, resp in enumerate(responses):
        ladder_price = round(start_price + step * idx, 2)
        child = OrderRequest(
            tradingsymbol=symbol,
            exchange=exchange,
            transaction_type=side.upper(),
            quantity=quantity,
            order_type=OrderType.LIMIT,
            product=product,
            price=ladder_price,
            validity=Validity.DAY,
        )
        _render_order_result(services, child, resp, extra=f"[scale {idx + 1}/{count}]")


@app.command()
def chase(
    ctx: typer.Context,
    symbol: str = typer.Argument(...),
    price: float = typer.Option(..., help="Starting limit price."),
    quantity: int = typer.Option(..., min=1),
    side: str = typer.Option("BUY", help="Side to trade (BUY/SELL)."),
    max_moves: int = typer.Option(20, help="Maximum number of price adjustments."),
    tick_size: float = typer.Option(0.05, help="Increment/decrement per chase step."),
    target_price: Optional[float] = typer.Option(None, help="Target price ceiling/floor."),
    exchange: str = typer.Option("NFO"),
    product: Product = typer.Option(Product.MIS, case_sensitive=False),
) -> None:
    """Chase a limit order towards a target price."""

    services: ServiceContainer = ctx.obj["services"]
    order = OrderRequest(
        tradingsymbol=symbol,
        exchange=exchange,
        transaction_type=side.upper(),
        quantity=quantity,
        order_type=OrderType.LIMIT,
        product=product,
        price=price,
    )
    response = _run(
        services.orders.chase_order(
            order,
            max_moves=max_moves,
            tick_size=tick_size,
            target_price=target_price,
        )
    )
    _render_order_result(services, order, response, extra=f"[chase max_moves={max_moves}]")


@app.command()
def swarm(
    ctx: typer.Context,
    symbol: str = typer.Argument(...),
    total_quantity: int = typer.Option(..., min=1, help="Total quantity to distribute across the swarm."),
    count: int = typer.Option(3, min=1, help="Number of child orders."),
    side: str = typer.Option("BUY", help="Side to trade (BUY/SELL)."),
    price: Optional[float] = typer.Option(None, help="Limit price for each child; omit for MARKET."),
    exchange: str = typer.Option("NFO"),
    product: Product = typer.Option(Product.MIS, case_sensitive=False),
) -> None:
    """Burst a swarm of child orders with even sizing."""

    services: ServiceContainer = ctx.obj["services"]
    base, remainder = divmod(total_quantity, count)
    if base == 0:
        raise typer.BadParameter("Increase quantity or reduce count to allocate at least 1 lot per order.")
    order_type = OrderType.MARKET if price is None else OrderType.LIMIT
    children: List[OrderRequest] = []
    for index in range(count):
        child_qty = base + (1 if index < remainder else 0)
        children.append(
            OrderRequest(
                tradingsymbol=symbol,
                exchange=exchange,
                transaction_type=side.upper(),
                quantity=child_qty,
                order_type=order_type,
                product=product,
                price=price,
            )
        )
    responses = _run(services.orders.swarm(children))
    for idx, resp in enumerate(responses):
        _render_order_result(services, children[idx], resp, extra=f"[swarm {idx + 1}/{count}]")


@app.command()
def config(ctx: typer.Context) -> None:
    """Show the active configuration for this session."""

    services: ServiceContainer = ctx.obj["services"]
    console.print(services.config)


@gtt_app.command("single")
def gtt_single(
    ctx: typer.Context,
    symbol: str = typer.Argument(...),
    exchange: str = typer.Option("NSE"),
    trigger: float = typer.Option(..., help="Trigger price for the alert."),
    limit_price: float = typer.Option(..., help="Limit price to place when triggered."),
    quantity: int = typer.Option(..., min=1),
    side: str = typer.Option("SELL", help="Side of the exit order."),
    last_price: Optional[float] = typer.Option(None, help="Reference last price for the trigger."),
) -> None:
    """Create a single-leg GTT."""

    services: ServiceContainer = ctx.obj["services"]
    if services.config.dry_run:
        console.print("[yellow]SIM[/yellow] GTT operations require --live mode; rerun with --live to hit Kite.")
        return
    payload = GTTRequest(
        tradingsymbol=symbol,
        exchange=exchange,
        trigger_values=[trigger],
        last_price=last_price,
        orders=[
            GTTLeg(
                price=limit_price,
                quantity=quantity,
                order_type=OrderType.LIMIT,
                transaction_type=side.upper(),
            )
        ],
    )
    response = _run(services.gtt.create_gtt(payload))
    console.print(response)


@gtt_app.command("oco")
def gtt_oco(
    ctx: typer.Context,
    symbol: str = typer.Argument(...),
    exchange: str = typer.Option("NSE"),
    trigger_up: float = typer.Option(..., help="Trigger that fires the profit-taking leg."),
    trigger_down: float = typer.Option(..., help="Trigger that fires the stop leg."),
    quantity: int = typer.Option(..., min=1),
    price_up: float = typer.Option(..., help="Limit price for the profit leg."),
    price_down: float = typer.Option(..., help="Limit price for the stop leg."),
    side: str = typer.Option("SELL", help="Direction of the exit legs."),
    last_price: Optional[float] = typer.Option(None),
) -> None:
    """Create a two-leg OCO GTT."""

    services: ServiceContainer = ctx.obj["services"]
    if services.config.dry_run:
        console.print("[yellow]SIM[/yellow] GTT operations require --live mode; rerun with --live to hit Kite.")
        return
    payload = GTTRequest(
        tradingsymbol=symbol,
        exchange=exchange,
        trigger_values=[trigger_up, trigger_down],
        last_price=last_price,
        orders=[
            GTTLeg(price=price_up, quantity=quantity, order_type=OrderType.LIMIT, transaction_type=side.upper()),
            GTTLeg(price=price_down, quantity=quantity, order_type=OrderType.LIMIT, transaction_type=side.upper()),
        ],
    )
    response = _run(services.gtt.create_gtt(payload))
    console.print(response)


@gtt_app.command("list")
def gtt_list(ctx: typer.Context) -> None:
    """List existing GTT triggers."""

    services: ServiceContainer = ctx.obj["services"]
    if services.config.dry_run:
        console.print("[yellow]SIM[/yellow] GTT operations require --live mode; rerun with --live to hit Kite.")
        return
    response = _run(services.gtt.list_gtts())
    console.print(response)


@gtt_app.command("delete")
def gtt_delete(ctx: typer.Context, trigger_id: int = typer.Argument(...)) -> None:
    """Delete a GTT trigger by id."""

    services: ServiceContainer = ctx.obj["services"]
    if services.config.dry_run:
        console.print("[yellow]SIM[/yellow] GTT operations require --live mode; rerun with --live to hit Kite.")
        return
    response = _run(services.gtt.delete_gtt(trigger_id))
    console.print(response)


app.add_typer(gtt_app, name="gtt")
