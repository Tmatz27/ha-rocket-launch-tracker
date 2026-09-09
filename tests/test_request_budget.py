"""Offline tests: fake clock/HTTP and minimal HA coordinator scaffolding."""
import asyncio
from datetime import datetime, timedelta, timezone
import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / 'custom_components/rocket_launch_tracker'
PKG = 'rocket_budget_test'
pkg = types.ModuleType(PKG)
pkg.__path__ = [str(ROOT)]
sys.modules[PKG] = pkg
budget = importlib.import_module(PKG + '.request_budget')
api = importlib.import_module(PKG + '.api')


class Clock:
    value = 0
    def __call__(self):
        return self.value


class Response:
    def __init__(self, status=200, headers=None, payload=None):
        self.status, self.headers = status, headers or {}
        self.payload = payload or {'results': []}
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass
    async def json(self):
        return self.payload
    async def text(self):
        return 'test error'


class Session:
    def __init__(self, response=None):
        self.response = response or Response()
        self.calls = []
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class BudgetTests(unittest.TestCase):
    def test_rolling_hour_boundary(self):
        clock = Clock(); b = budget.RequestBudget(clock=clock)
        for _ in range(15): b.reserve()
        clock.value = 3599.5
        with self.assertRaises(budget.BudgetDeferred) as ctx: b.reserve()
        self.assertEqual(ctx.exception.retry_after, 1)
        clock.value = 3600; b.reserve()
        self.assertEqual(len(b.requests), 1)

    def test_hour_is_rolling_not_clock_hour(self):
        clock = Clock(); b = budget.RequestBudget(clock=clock)
        for minute in range(15):
            clock.value = minute * 60; b.reserve()
        clock.value = 3600; b.reserve()
        with self.assertRaises(budget.BudgetDeferred): b.reserve()
        clock.value = 3660; b.reserve()

    def test_entry_reloads_and_matching_keys_share_budget(self):
        data = {}
        self.assertIs(budget.shared_budget(data), budget.shared_budget(data))
        self.assertIs(budget.shared_budget(data, 'test-key'), budget.shared_budget(data, 'test-key'))
        self.assertIsNot(budget.shared_budget(data), budget.shared_budget(data, 'test-key'))
        self.assertNotIn('test-key', repr(data))

    def test_cooldown_cannot_be_shortened(self):
        clock = Clock(); b = budget.RequestBudget(clock=clock)
        b.defer(7200); clock.value = 30; b.defer(3600)
        with self.assertRaises(budget.BudgetDeferred) as ctx: b.reserve()
        self.assertEqual(ctx.exception.retry_after, 7170)
        clock.value = 7200; b.reserve()

    def test_backoff_never_shrinks_long_intervals(self):
        self.assertEqual(budget.backoff_seconds(1800, 300), 3600)
        self.assertEqual(budget.backoff_seconds(7200, 7200), 14400)
        self.assertEqual(budget.backoff_seconds(1800, 20000), 20000)
        self.assertEqual(budget.backoff_seconds(1800, 300, 90000), 90000)

    def test_retry_after_formats(self):
        now = datetime(2026, 9, 7, tzinfo=timezone.utc)
        self.assertEqual(budget.retry_after_seconds('7200'), 7200)
        self.assertEqual(budget.retry_after_seconds('Mon, 07 Sep 2026 02:00:00 GMT', now=now), 7200)
        for value in (None, '', 'nonsense', '-1', 'nan', 'inf'):
            self.assertEqual(budget.retry_after_seconds(value), 0)


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_sites_share_last_slot(self):
        clock = Clock(); b = budget.RequestBudget(clock=clock); session = Session()
        clients = [api.LaunchLibraryClient(session, budget=b) for _ in range(20)]
        results = await asyncio.gather(*(c.async_get_upcoming([i], 5) for i,c in enumerate(clients)), return_exceptions=True)
        self.assertEqual(len(session.calls), 15)
        self.assertEqual(sum(isinstance(r, budget.BudgetDeferred) for r in results), 5)
        self.assertEqual(session.calls[0][1]['params']['location__ids'], '0')

    async def test_setup_lookup_and_poll_share_budget(self):
        b = budget.RequestBudget(limit=2); session = Session()
        setup = api.LaunchLibraryClient(session, budget=b)
        poll = api.LaunchLibraryClient(session, budget=b)
        await setup.async_search_locations('Vandenberg')
        await setup.async_get_upcoming([11], 1)
        with self.assertRaises(budget.BudgetDeferred): await poll.async_get_upcoming([11], 5)
        self.assertEqual(len(session.calls), 2)

    async def test_429_blocks_other_clients_and_honors_retry_after(self):
        clock = Clock(); b = budget.RequestBudget(clock=clock)
        session = Session(Response(429, {'Retry-After': '7200'}))
        client = api.LaunchLibraryClient(session, budget=b)
        with self.assertRaises(api.LaunchLibraryRateLimited): await client.async_get_upcoming(None, 5)
        other = Session()
        with self.assertRaises(budget.BudgetDeferred):
            await api.LaunchLibraryClient(other, budget=b).async_get_upcoming(None, 5)
        self.assertEqual(other.calls, [])
        clock.value = 7200
        await api.LaunchLibraryClient(other, budget=b).async_get_upcoming(None, 5)

    async def test_failed_network_attempt_still_consumes_slot(self):
        b = budget.RequestBudget(limit=1); session = Session(Response(500))
        client = api.LaunchLibraryClient(session, budget=b)
        with self.assertRaises(api.LaunchLibraryError): await client.async_get_upcoming(None, 5)
        with self.assertRaises(budget.BudgetDeferred): await client.async_get_upcoming(None, 5)
        self.assertEqual(len(session.calls), 1)


def load_coordinator():
    class Base:
        def __class_getitem__(cls, item): return cls
        def __init__(self, hass, logger, name, update_interval):
            self.update_interval = update_interval
            self.data = None
            self.last_update_success = True
    class UpdateFailed(Exception): pass
    modules = {name: types.ModuleType(name) for name in (
        'homeassistant', 'homeassistant.core', 'homeassistant.helpers',
        'homeassistant.helpers.aiohttp_client', 'homeassistant.helpers.update_coordinator',
        'homeassistant.util', 'homeassistant.util.dt')}
    modules['homeassistant.core'].HomeAssistant = object
    modules['homeassistant.helpers.aiohttp_client'].async_get_clientsession = lambda hass: hass.session
    modules['homeassistant.helpers.update_coordinator'].DataUpdateCoordinator = Base
    modules['homeassistant.helpers.update_coordinator'].UpdateFailed = UpdateFailed
    modules['homeassistant.util.dt'].utcnow = lambda: datetime.now(timezone.utc)
    with patch.dict(sys.modules, modules):
        return importlib.import_module(PKG + '.coordinator'), UpdateFailed


coordinator, UpdateFailed = load_coordinator()


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    def make(self, hass, far=30):
        return coordinator.RocketLaunchCoordinator(hass, site_filter='Vandenberg', location_ids=[11],
            api_key=None, upcoming_count=5, near_window_hours=48, near_interval_minutes=3,
            far_interval_minutes=far)

    async def test_runtime_clamps_old_settings_and_shares_entries(self):
        hass = types.SimpleNamespace(data={}, session=Session())
        a, b = self.make(hass), self.make(hass)
        self.assertEqual(a._near_interval, timedelta(minutes=5))
        self.assertIs(a._client.budget, b._client.budget)
        await a._async_update_data()
        self.assertEqual(len(b._client.budget.requests), 1)

    async def test_scheduled_deferral_preserves_only_valid_cached_data(self):
        hass = types.SimpleNamespace(data={}, session=Session()); c = self.make(hass)
        c.data = [{'id':'known'}]; c._client.budget.defer(3600)
        self.assertIs(await c._async_update_data(), c.data)
        self.assertEqual(hass.session.calls, [])
        c.last_update_success = False
        with self.assertRaises(UpdateFailed): await c._async_update_data()
        c.last_update_success = True; c.data = None
        with self.assertRaises(UpdateFailed): await c._async_update_data()

    async def test_long_far_interval_429_and_manual_refresh_respect_cooldown(self):
        hass = types.SimpleNamespace(data={}, session=Session(Response(429)))
        c = self.make(hass, far=120)
        with self.assertRaises(UpdateFailed): await c._async_update_data()
        self.assertEqual(c.update_interval, timedelta(hours=4))
        with self.assertRaises(UpdateFailed): await c._async_update_data()
        self.assertEqual(len(hass.session.calls), 1)
        self.assertGreaterEqual(c.update_interval, timedelta(hours=4))


if __name__ == '__main__':
    unittest.main()
