"""\
Miroslava's Werkzeug-style Datastructures
=========================================

Author: Akshay Mestry <xa@mes3.dev>
Created on: 26 January, 2026
Last updated on: 28 January, 2026

This module implements custom data structures used by Miroslava to
handle HTTP data. These class mimic the behaviour of Werkzeug's
internal datastructures, specifically designed to handle multiple
values for the same key (`MultiDict`).

The `MultiDict` is the primary datastructure here. While working with
HTTP standard, it's perfectly valid to submit multiple values for the
same key (e.g., `?tag=python&tag=miroslava`). Standard Python
dictionaries can't represent this structure.
"""

from __future__ import annotations

import typing as t
from collections.abc import Iterable
from collections.abc import Iterator
from collections.abc import Mapping

T = t.TypeVar("T")
K = t.TypeVar("K")
V = t.TypeVar("V")


class MultiDict(dict[K, V]):
    """Type of dictionary which can represent multiple values.

    A `MultiDict` is a subclass of standard Python dictionary
    customised to deal with multiple values for the same key which is
    for example common when dealing with parsing of form data in the
    HTTP requests.
    """

    def __init__(
        self,
        mapping: (
            MultiDict[K, V]
            | Mapping[K, V | list[V] | tuple[V, ...] | set[V]]
            | Iterable[tuple[K, V]]
            | None
        ) = None,
    ) -> None:
        """Initialise a `MultiDict` object with optional mapping."""
        if mapping is None:
            super().__init__()
        elif isinstance(mapping, Mapping):
            for key, value in mapping.items():
                self[key] = [value] if not isinstance(value, list) else value
        else:
            for key, value in mapping:
                self.add(key, value)

    def __getitem__(self, key: K) -> V | None:
        """Return the first value for this key."""
        if key in self:
            value = super().__getitem__(key)
            return value[0] if value else None
        raise KeyError(key)

    def __setitem__(self, key: K, value: V) -> None:
        """Set the value for the key; override if existing."""
        super().__setitem__(
            key, [value] if not isinstance(value, list) else value
        )

    def __iter__(self) -> Iterator[K]:
        """Satisfying `mypy`."""
        return super().__iter__()

    def add(self, key: K, value: V) -> None:
        """Add a new value for the key."""
        if key in self:
            super().__getitem__(key).append(value)
        else:
            self[key] = [value]

    @t.overload
    def getlist(self, key: K) -> list[V]: ...
    @t.overload
    def getlist(self, key: K, type: t.Callable[[V], T]) -> list[T]: ...

    def getlist(
        self,
        key: K,
        type: t.Callable[[V], T] | None = None,  # noqa: A002
    ) -> list[V] | list[T]:
        """Return the list of items for the requested key.

        If `type` is provided and is a callable, it should then convert
        the value, return it or raise an exception if that's not
        possible.

        :param key: Key to lookup.
        :param type: Callable to convert each value.
        :return: A list of all the values for the key.
        """
        try:
            values = self[key]
        except KeyError:
            return []
        if type is None:
            return list(values)
        result: list[T] = []
        for value in values:
            try:
                result.append(type(value))
            except (ValueError, TypeError):
                pass
        return result
