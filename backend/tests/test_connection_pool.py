"""A reused connection keeps transaction boundaries for subsequent callers."""

import asyncio

import pytest

from backend.core.config import Settings
from backend.database import connection, pooled_settings, read_snapshot
from backend.tests.test_auth import ORIGIN, test_url


def test_pool_resets_read_snapshot_and_rolls_back(test_url):
    async def exercise():
        settings = Settings(test_url, (ORIGIN,), db_pool_max_size=1)
        async with pooled_settings(settings) as pooled:
            with read_snapshot(pooled) as conn:
                pid = conn.info.backend_pid
                assert conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only'] == 'on'
                assert (conn.execute('SHOW transaction_isolation').fetchone()['transaction_isolation']
                        == 'repeatable read')

            with pytest.raises(RuntimeError), connection(pooled) as conn:
                assert conn.info.backend_pid == pid
                assert conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only'] == 'off'
                assert (conn.execute('SHOW transaction_isolation').fetchone()['transaction_isolation']
                        == 'read committed')
                conn.execute("INSERT INTO patients(external_id) VALUES('POOL-ROLLBACK')")
                raise RuntimeError('roll back test insert')

            with connection(pooled) as conn:
                assert conn.info.backend_pid == pid
                assert not conn.execute("SELECT 1 FROM patients WHERE external_id='POOL-ROLLBACK'").fetchone()
        assert pooled.connection_pool.closed

    asyncio.run(exercise())
