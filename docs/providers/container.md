# Container Provider

The Container Provider is a special provider that you should not initialize
It is automatically registered with each container, so you can resolve the container itself directly:

```python
from modern_di import Container, providers

container = Container()

# Resolve the container itself
the_container = container.resolve(Container)
the_same_container = container.resolve_provider(providers.container_provider)
```

It's synthetic example just to show that it works. More useful example is to inject `Container` to another object:

```python
from modern_di import Container, Group, providers

def some_creator(di_container: Container) -> str:
    # do sth with container
    return "string"

class Dependencies(Group):
    some_factory = providers.Factory(creator=some_creator)

    # explicit container injection
    another_factory = providers.Factory(creator=some_creator, kwargs={"di_container": providers.container_provider})

```
