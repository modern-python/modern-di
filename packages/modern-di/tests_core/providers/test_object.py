from modern_di import Container, Group, providers


instance = ["some item"]


class MyGroup(Group):
    object_provider = providers.Object(obj=instance, bound_type=list[str])


def test_object_provider() -> None:
    app_container = Container(groups=[MyGroup])
    instance1 = app_container.resolve_provider(MyGroup.object_provider)
    instance2 = app_container.resolve(list[str])

    assert instance1 is instance2 is instance
