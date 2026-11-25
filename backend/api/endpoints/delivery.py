"""Mount the same delivery operations for three ownership scopes."""

from fastapi import APIRouter, Depends

from backend import delivery
from backend.api.dependencies import AppSettings, current_user
from backend.delivery import Subscription, Target, Verify

router = APIRouter()


def target_routes(prefix, scope, authenticated=False):
    staff_dependency = Depends(current_user) if authenticated else None

    def list_targets(settings: AppSettings, key='', user=staff_dependency):
        return delivery.list_targets(settings, scope, key, user)

    def register(settings: AppSettings, body: Target, key='', user=staff_dependency):
        return delivery.register(settings, scope, key, user, body)

    def verify(
        settings: AppSettings, channel: str, body: Verify, key='', user=staff_dependency
    ):
        return delivery.verify(settings, scope, key, user, channel, body)

    def disable(settings: AppSettings, channel: str, key='', user=staff_dependency):
        return delivery.disable(settings, scope, key, user, channel)

    def push(settings: AppSettings, body: Subscription, key='', user=staff_dependency):
        return delivery.push(settings, scope, key, user, body)

    router.add_api_route(prefix, list_targets, methods=['GET'])
    router.add_api_route(prefix, register, methods=['POST'])
    router.add_api_route(prefix + '/{channel}/verify', verify, methods=['POST'])
    router.add_api_route(prefix + '/{channel}/disable', disable, methods=['POST'])
    router.add_api_route(prefix + '/push', push, methods=['POST'])


target_routes('/delivery/targets', 'staff', authenticated=True)
target_routes('/patient/{key}/delivery', 'patient')
target_routes('/self-checkin/{key}/delivery', 'appointment')
