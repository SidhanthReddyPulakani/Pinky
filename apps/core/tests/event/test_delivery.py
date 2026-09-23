from pinky_core.event.delivery import DeliveryTarget


def test_delivery_target_is_callable_type_alias() -> None:
    async def deliver(event) -> None:
        return None

    target: DeliveryTarget = deliver

    assert callable(target)