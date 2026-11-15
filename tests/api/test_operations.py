"""Operational snapshots expose durable failures without credentials/capabilities."""
from datetime import timedelta

from sqlalchemy import select

from app.db import get_session_factory
from app.db.models import Channel, Delivery, DeliveryState
from app.utils.time import utc_now
from tests.core.test_telegram_actions import telegram_delivery as telegram_delivery


async def test_operations_require_read(db_client):
    response = await db_client.get('/v1/operations')
    assert response.status_code == 401


async def test_queue_overdue_excludes_future_retry_and_active_lease(db_client, admin_key, telegram_delivery):
    now = utc_now().replace(microsecond=0)
    async with get_session_factory()() as session:
        delivery = await session.get(Delivery, telegram_delivery['delivery'])
        delivery.next_attempt_at = now - timedelta(minutes=10)
        delivery.created_at = now - timedelta(hours=1)
        for index, (next_attempt, lease) in enumerate([
            (now - timedelta(minutes=10), now + timedelta(minutes=1)),
            (now + timedelta(minutes=10), None),
        ]):
            session.add(Delivery(notification_id=telegram_delivery['log'], channel=f'queued_{index}',
                                 state=DeliveryState.pending, attempts=0, next_attempt_at=next_attempt,
                                 lease_until=lease, idempotency_key=f'queued_{index}'))
        await session.commit()
    response = await db_client.get('/v1/operations', headers={'X-API-Key': admin_key})
    assert response.status_code == 200, response.text
    body = response.json()
    queue = next(q for q in body['queues'] if q['name'] == 'deliveries')
    assert queue['states']['pending'] == 3
    assert queue['overdue'] == 1
    assert queue['oldest_pending_seconds'] >= 3599
    assert queue['oldest_overdue_seconds'] >= 599
    assert 'test-bot-token' not in response.text
    assert 'callback_data' not in response.text


async def test_terminal_failures_are_linked_and_redacted(db_client, admin_key, telegram_delivery):
    async with get_session_factory()() as session:
        delivery = await session.get(Delivery, telegram_delivery['delivery'])
        delivery.state = DeliveryState.failed
        delivery.last_error = 'upstream https://api.telegram.org/botSHOULD_NOT_LEAK/sendMessage'
        delivery.next_attempt_at = None
        await session.commit()
    response = await db_client.get('/v1/operations', headers={'X-API-Key': admin_key})
    assert response.status_code == 200
    [failure] = response.json()['recent_failures']
    assert failure['notification_id'] == telegram_delivery['log']
    assert failure['channel'] == 'telegram_actions'
    assert failure['created_at'].endswith('Z')
    assert 'SHOULD_NOT_LEAK' not in response.text


async def test_operational_metrics_and_removed_channel_labels(db_client, telegram_delivery):
    response = await db_client.get('/v1/metrics')
    assert response.status_code == 200
    assert 'alertd_operations_collection_success 1.0' in response.text
    assert 'alertd_queue_rows{queue="deliveries",state="pending"} 1.0' in response.text
    assert 'alertd_telegram_receiver_connected{channel="telegram_actions"}' in response.text
    assert 'test-bot-token' not in response.text
    async with get_session_factory()() as session:
        channel = (await session.execute(select(Channel))).scalar_one()
        channel.enabled = False
        await session.commit()
    response = await db_client.get('/v1/metrics')
    assert 'alertd_telegram_receiver_connected{channel="telegram_actions"}' not in response.text
