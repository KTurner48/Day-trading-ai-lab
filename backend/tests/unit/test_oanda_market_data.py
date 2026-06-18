"""OANDA market-data adapter tests: PRICE/HEARTBEAT parsing, provider-timestamp
usage, and event-time aggregation. Pure (no network)."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.market_data.aggregator import BarAggregator, floor_to_bucket
from app.market_data.oanda import parse_oanda_time, parse_stream_message
from app.market_data.types import Tick


def test_parse_price_message_to_tick():
    line = (
        '{"type":"PRICE","instrument":"XAU_USD",'
        '"time":"2026-06-18T13:45:30.123456789Z",'
        '"bids":[{"price":"2351.20","liquidity":1000000}],'
        '"asks":[{"price":"2351.40","liquidity":1000000}]}'
    )
    tick = parse_stream_message(line)
    assert tick is not None
    assert tick.symbol == "XAU_USD"
    assert tick.source == "oanda"
    assert tick.bid == Decimal("2351.20")
    assert tick.ask == Decimal("2351.40")
    assert tick.mid == Decimal("2351.30")


def test_heartbeat_returns_none():
    line = '{"type":"HEARTBEAT","time":"2026-06-18T13:45:30.000000000Z"}'
    assert parse_stream_message(line) is None


def test_blank_and_malformed_lines_return_none():
    assert parse_stream_message("") is None
    assert parse_stream_message("   ") is None
    assert parse_stream_message("{not json") is None
    assert parse_stream_message('{"type":"PRICE"}') is None  # missing fields


def test_uses_provider_timestamp_not_arrival_time():
    line = (
        '{"type":"PRICE","instrument":"XAU_USD",'
        '"time":"2026-06-18T13:45:30.5Z",'
        '"bids":[{"price":"2351.20"}],"asks":[{"price":"2351.40"}]}'
    )
    tick = parse_stream_message(line)
    assert tick is not None
    # The tick carries the OANDA event time exactly, regardless of "now".
    assert tick.time == datetime(2026, 6, 18, 13, 45, 30, 500000, tzinfo=timezone.utc)


def test_parse_oanda_time_trims_nanoseconds():
    dt = parse_oanda_time("2026-06-18T13:45:30.123456789Z")
    assert dt == datetime(2026, 6, 18, 13, 45, 30, 123456, tzinfo=timezone.utc)


def test_floor_to_bucket_uses_event_time():
    ts = datetime(2026, 6, 18, 13, 47, 12, tzinfo=timezone.utc)
    assert floor_to_bucket(ts, 300) == datetime(2026, 6, 18, 13, 45, 0, tzinfo=timezone.utc)


def test_aggregator_buckets_by_event_time_not_arrival():
    agg = BarAggregator(timeframe_seconds=300)
    base = datetime(2026, 6, 18, 13, 45, 0, tzinfo=timezone.utc)

    def tick(sec, price):
        from datetime import timedelta
        return Tick(symbol="XAU_USD", time=base + timedelta(seconds=sec),
                    bid=Decimal(str(price)) - Decimal("0.1"),
                    ask=Decimal(str(price)) + Decimal("0.1"), source="oanda")

    # Three ticks in the first bucket, then one in the next closes the first bar.
    assert agg.add(tick(10, 2350)) is None
    assert agg.add(tick(120, 2360)) is None
    assert agg.add(tick(200, 2345)) is None
    bar = agg.add(tick(305, 2355))  # crosses into next 5-min bucket
    assert bar is not None
    assert bar.time == base
    assert bar.open == Decimal("2350")
    assert bar.high == Decimal("2360")
    assert bar.low == Decimal("2345")
    assert bar.close == Decimal("2345")
    assert bar.volume == 3
