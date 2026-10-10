# What dependency injection is

Dependency injection (DI) is a design pattern where a class takes the things it depends on as
arguments, and whoever constructs the class decides what those are.

## Building dependencies inside the class

```python
import dataclasses


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class AppConfig:
    smtp_host: str = "localhost"


class SmtpEmailSender:
    def __init__(self, config: AppConfig) -> None:
        self.host = config.smtp_host

    def send_email(self, to: str, body: str) -> None:
        print(f"sending to {to} via {self.host}: {body}")


class Registration:
    def __init__(self) -> None:
        self.email_sender = SmtpEmailSender(AppConfig())

    def register_user(self, address: str) -> None:
        self.email_sender.send_email(address, "Welcome!")
```

The constructor takes no arguments, so nothing outside the class can change what it sends mail with.
A test of `register_user` reaches the real sender, and a caller reading the signature gets no hint
that mail is involved.

## Taking them as arguments

```python
import typing


class EmailSender(typing.Protocol):
    def send_email(self, to: str, body: str) -> None: ...


class Registration:
    def __init__(self, email_sender: EmailSender) -> None:
        self.email_sender = email_sender

    def register_user(self, address: str) -> None:
        self.email_sender.send_email(address, "Welcome!")
```

`Registration` names an abstraction now, and the caller supplies the implementation. A test supplies
a double:

```python
from unittest.mock import Mock


def test_registration() -> None:
    email_sender = Mock(spec=EmailSender)
    registration = Registration(email_sender=email_sender)

    registration.register_user("test@example.com")

    email_sender.send_email.assert_called_once_with("test@example.com", "Welcome!")
```

The same holds for any abstraction. A class written against a cache interface keeps working unchanged
when you swap `RedisCache` for `DictCache` in development, or `MockCache` in tests.

## Wiring by hand

Every object now has to be constructed somewhere, in an order that satisfies its arguments:

```python
config = AppConfig()
email_sender = SmtpEmailSender(config)
registration = Registration(email_sender)
```

This grows unwieldy as the application does: nothing manages how long each object lives, and
construction logic ends up wherever a dependency is needed. A container takes the construction
over. `modern-di` reads the type annotations of your classes and builds the same graph from a list
of providers:

```python
from modern_di import Container, Group, Scope, providers


class Dependencies(Group):
    config = providers.Factory(AppConfig, scope=Scope.APP, cache=True)
    email_sender = providers.Factory(SmtpEmailSender, bound_type=EmailSender, scope=Scope.APP, cache=True)
    registration = providers.Factory(Registration)


container = Container(groups=[Dependencies])
container.validate()
container.resolve(Registration).register_user("user@example.com")
```

`bound_type=EmailSender` tells the container which provider satisfies an `EmailSender` argument.
In tests, an override swaps one provider for the whole application; see
[Testing with overrides](../recipes/testing-overrides.md). The
[Quickstart](../index.md#2-resolve-a-dependency) walks through the syntax step by step.

## Scope and caching

One graph usually holds objects that need to live for different spans: one instance per process, one
per request, or a fresh one on every call. `modern-di` expresses this with
[scopes](../providers/scopes.md). A provider's scope decides how long its instances live, and
`cache=True` decides whether an instance is shared or rebuilt on each resolve. In the example above,
the config and the email sender are APP-scoped and cached, so the application shares one of each,
while `Registration` is built again on every resolve. See
[Cached factories](../providers/factories.md#cached-factories).

An object that holds a resource, such as an SMTP connection, also has to be closed when its scope
ends. A cached factory takes a finalizer for that; see [Lifecycle](../providers/lifecycle.md).

## See also

- [modern-di vs other libraries](comparison.md), including when a container pays off.
- [Quickstart](../index.md): modern-di's own syntax, end to end.
- [Design decisions](design-decisions.md): the reasoning behind the API's choices.
