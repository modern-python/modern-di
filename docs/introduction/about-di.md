# What dependency injection is

Dependency injection (DI) is a design pattern where a class takes the things it depends on as
arguments, and whoever constructs the class decides what those are.

## Building dependencies inside the class

```python
class Registration:
    def __init__(self) -> None:
        self.email = SmtpEmailSender()

    def register_user(self, email: str) -> None:
        self.email.send_email(email, "Welcome!")
```

The constructor takes no arguments, so nothing outside the class can change what it sends mail with.
A test of `register_user` reaches the real sender, and a caller reading the signature gets no hint
that mail is involved.

## Taking them as arguments

```python
class Registration:
    def __init__(self, email: EmailSender) -> None:
        self.email = email

    def register_user(self, email: str) -> None:
        self.email.send_email(email, "Welcome!")
```

`Registration` names an abstraction now, and the caller supplies the implementation. A test supplies
a double:

```python
def test_registration() -> None:
    mock_email = Mock(spec=EmailSender)
    registration = Registration(email=mock_email)

    registration.register_user("test@example.com")

    mock_email.send_email.assert_called_once()
```

The same holds for any abstraction. A class written against a cache interface keeps working unchanged
when you swap `RedisCache` for `DictCache` in development, or `MockCache` in tests.

## Wiring by hand

Every object now has to be constructed somewhere, in an order that satisfies its arguments:

```python
config = AppConfig()
email = SmtpEmailSender(config)
registration = Registration(email)
```

This grows unwieldy as the application does: nothing manages how long each object lives, and
construction logic ends up wherever a dependency is needed. A Container takes the construction over.
`modern-di` reads your classes' type annotations and builds the graph for you, which the
[Quickstart](../index.md#2-first-success) walks through.

## Scope and caching

One graph usually holds objects that need to live for different spans: one instance per process, one
per request, or a fresh one on every call. `modern-di` expresses this with
[Scopes](../providers/scopes.md). A provider's Scope decides how long its instances live, and
`cache=True` decides whether an instance is shared or rebuilt on each resolve. See
[Cached factories](../providers/factories.md#cached-factories).

## See also

- [modern-di vs other libraries](comparison.md) — including whether you need a container at all.
- [Quickstart](../index.md) — modern-di's own syntax, end to end.
- [Design decisions](design-decisions.md) — the reasoning behind the API's choices.
