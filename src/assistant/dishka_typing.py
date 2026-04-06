from collections.abc import Callable
from typing import Any, Protocol, cast, overload

from dishka import (
    BaseScope,
)
from dishka import (
    provide as _provide,  # pyright: ignore[reportUnknownVariableType]
)
from dishka.dependency_source import CompositeDependencySource
from dishka.entities.marker import BaseMarker
from dishka.provider.make_factory import ProvideSource


class _Provide(Protocol):
    @overload
    def __call__(
        self,
        *,
        scope: BaseScope | None = None,
        provides: Any = None,  # noqa: ANN401
        cache: bool = True,
        recursive: bool = False,
        override: bool = False,
        when: BaseMarker | None = None,
    ) -> Callable[[Callable[..., Any]], CompositeDependencySource]: ...

    @overload
    def __call__(
        self,
        source: ProvideSource | None,  # pyright: ignore[reportUnknownParameterType]
        *,
        scope: BaseScope | None = None,
        provides: Any = None,  # noqa: ANN401
        cache: bool = True,
        recursive: bool = False,
        override: bool = False,
        when: BaseMarker | None = None,
    ) -> CompositeDependencySource: ...

    def __call__(  # noqa: PLR0913
        self,
        source: ProvideSource | None = None,  # pyright: ignore[reportUnknownParameterType]
        *,
        scope: BaseScope | None = None,
        provides: Any = None,
        cache: bool = True,
        recursive: bool = False,
        override: bool = False,
        when: BaseMarker | None = None,
    ) -> (
        CompositeDependencySource
        | Callable[
            [Callable[..., Any]],
            CompositeDependencySource,
        ]
    ): ...


provide = cast("_Provide", _provide)
