"""Per-symbol routing: OANDA only for configured symbols WITH credentials;
GC/GLD always simulated; everything simulated when OANDA not configured."""
from __future__ import annotations

import importlib

import app.config as config_module
from app.market_data import routing


def _reload_with(monkeypatch, **env):
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    importlib.reload(config_module)
    importlib.reload(routing)
    return routing


def test_simulated_when_oanda_not_configured(monkeypatch):
    r = _reload_with(monkeypatch, OANDA_API_KEY="", OANDA_ACCOUNT_ID="")
    assert r.provider_name_for_symbol("XAU_USD") == "simulated"
    assert r.provider_name_for_symbol("GC") == "simulated"
    assert r.provider_name_for_symbol("GLD") == "simulated"


def test_oanda_for_xau_only_when_configured(monkeypatch):
    r = _reload_with(monkeypatch, OANDA_API_KEY="key", OANDA_ACCOUNT_ID="acct",
                     OANDA_DATA_SYMBOLS="XAU_USD")
    assert r.provider_name_for_symbol("XAU_USD") == "oanda"
    # GC and GLD stay simulated — run alongside.
    assert r.provider_name_for_symbol("GC") == "simulated"
    assert r.provider_name_for_symbol("GLD") == "simulated"


def test_split_symbols_groups_by_provider(monkeypatch):
    r = _reload_with(monkeypatch, OANDA_API_KEY="key", OANDA_ACCOUNT_ID="acct",
                     OANDA_DATA_SYMBOLS="XAU_USD")
    groups = r.split_symbols(["XAU_USD", "GC", "GLD"])
    assert groups["oanda"] == ["XAU_USD"]
    assert sorted(groups["simulated"]) == ["GC", "GLD"]


def test_select_provider_returns_right_type(monkeypatch):
    r = _reload_with(monkeypatch, OANDA_API_KEY="key", OANDA_ACCOUNT_ID="acct",
                     OANDA_DATA_SYMBOLS="XAU_USD")
    from app.market_data.oanda import OandaMarketDataProvider
    from app.market_data.provider import SimulatedProvider
    assert isinstance(r.select_provider("XAU_USD"), OandaMarketDataProvider)
    assert isinstance(r.select_provider("GC"), SimulatedProvider)


def teardown_module(_):
    # Restore pristine config/routing for any later tests in the session.
    importlib.reload(config_module)
    importlib.reload(routing)
