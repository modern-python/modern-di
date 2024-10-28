import dataclasses
import datetime
import logging
import typing

from modern_di import BaseGraph, Scope, resolvers


logger = logging.getLogger(__name__)


def create_sync_resource() -> typing.Iterator[datetime.datetime]:
    logger.debug("Resource initiated")
    try:
        yield datetime.datetime.now(tz=datetime.timezone.utc)
    finally:
        logger.debug("Resource destructed")


async def create_async_resource() -> typing.AsyncIterator[datetime.datetime]:
    logger.debug("Async resource initiated")
    try:
        yield datetime.datetime.now(tz=datetime.timezone.utc)
    finally:
        logger.debug("Async resource destructed")


@dataclasses.dataclass(kw_only=True, slots=True)
class SimpleFactory:
    dep1: str
    dep2: int


@dataclasses.dataclass(kw_only=True, slots=True)
class DependentFactory:
    simple_factory: SimpleFactory
    sync_resource: datetime.datetime
    async_resource: datetime.datetime


@dataclasses.dataclass(kw_only=True, slots=True)
class SingletonFactory:
    dep1: bool


class DIGraph(BaseGraph):
    sync_resource_app = resolvers.Resource(Scope.APP, create_sync_resource)
    async_resource_app = resolvers.Resource(Scope.APP, create_async_resource)

    sync_resource_request = resolvers.Resource(Scope.REQUEST, create_sync_resource)
    async_resource_request = resolvers.Resource(Scope.REQUEST, create_async_resource)

    simple_factory = resolvers.Factory(Scope.REQUEST, SimpleFactory, dep1="text", dep2=123)
    dependent_factory = resolvers.Factory(
        Scope.REQUEST,
        DependentFactory,
        simple_factory=simple_factory.cast,
        sync_resource=sync_resource_app.cast,
        async_resource=async_resource_app.cast,
    )
    dependent_factory_on_request_resources = resolvers.Factory(
        Scope.REQUEST,
        DependentFactory,
        simple_factory=simple_factory.cast,
        sync_resource=sync_resource_request.cast,
        async_resource=async_resource_request.cast,
    )
    singleton = resolvers.Factory(Scope.APP, SingletonFactory, dep1=True)
