"""\
Miroslava's Werkzeug-style Datastructures
=========================================

Author: Akshay Mestry <xa@mes3.dev>
Created on: 26 January, 2026
Last updated on: 01 February, 2026

This module provides lightweight stand-ins for Werkzeug's ``MultiDict``
and ``Headers`` classes. The ``MultiDict`` can hold multiple values for
the same key, which is essential when handling form submissions and
query strings.
"""

from __future__ import annotations

import typing as t
from collections.abc import Iterable
from collections.abc import Mapping

from miroslava.utils import set_module as m

K = t.TypeVar("K")
V = t.TypeVar("V")
T = t.TypeVar("T")


@m("miroslava.twerkzeug.datastructures.structures")
class MultiDict(dict[K, V]):
    """A dictionary variant that stores multiple values for each key.

    This datastructure is a good choice when dealing with parsing of
    form data in the HTTP requests.

    :param mapping: Initial value for the object.

    .. note::

        In this implementation, the values are stored in insertion
        order and accessed using the first item by default. All the
        common accessing methods return the earliest value unless a
        list is explicitly requested.
    """

    def __init__(
        self,
        mapping: (
            MultiDict[K, V]
            | Mapping[K, V | list[V] | tuple[V, ...]]
            | Iterable[tuple[K, V]]
            | None
        ) = None,
    ) -> None:
        """Initialise object with optional mapping data."""
        if mapping is None:
            super().__init__()
        elif isinstance(mapping, MultiDict):
            for key, value in mapping.items(multi=True):
                self.add(key, value)
        elif isinstance(mapping, Mapping):
            for key, value in mapping.items():
                self[key] = [value] if not isinstance(value, list) else value
        else:
            for key, value in mapping:
                self.add(key, value)

    def __getitem__(self, key: K) -> V:
        """Return the first value associated with the key.

        :param key: Lookup key.
        :raises KeyError: When the key does not exist.
        """
        if key in self:
            return super().__getitem__(key)[0]
        raise KeyError(key)

    def __setitem__(self, key: K, value: V) -> None:
        """Set or replace all values for the key with a single value."""
        super().__setitem__(
            key, [value] if not isinstance(value, list) else value
        )

    def add(self, key: K, value: V) -> None:
        """Append a new value for the key, preserving existing ones.

        :param key: Target key to append to.
        :param value: Value to append.
        """
        if key in self:
            super().__getitem__(key).append(value)
        else:
            self[key] = [value]

    @t.overload
    def getlist(self, key: K) -> list[V]: ...
    @t.overload
    def getlist(self, key: K, type_: t.Callable[[V], T]) -> list[T]: ...

    def getlist(
        self,
        key: K,
        type_: t.Callable[[V], T] | None = None,
    ) -> list[V] | list[T]:
        """Return all stored values for the key.

        :param key: Lookup key.
        :param type_: Optional converter applied element-wise, defaults
            to ``None``.
        """
        try:
            values = super().__getitem__(key)
        except KeyError:
            return []
        if type_ is None:
            return list(values)
        result: list[T] = []
        for value in values:
            try:
                result.append(type_(value))
            except (ValueError, TypeError):
                pass
        return result

    def items(self, multi: bool = False) -> t.Iterator[tuple[K, V]]:
        """Iterate over key-value pairs.

        :param multi: When ``True``, yield each stored value
            separately; otherwise yield only the first value per key,
            defaults to ``False``.
        """
        for key in super().__iter__():
            values = super().__getitem__(key)
            if multi:
                for value in values:
                    yield key, value
            else:
                yield key, values[0]


@m("miroslava.twerkzeug.datastructures.headers")
class Headers(MultiDict[str, str]):
    """HTTP header container that stores some header."""

    def __getitem__(self, key: str) -> str:
        """Return the first header value matching the name."""
        return super().__getitem__(key.lower())

    def __setitem__(self, key: str, value: str) -> None:
        """Store a header value under a case-insensitive name."""
        super().__setitem__(key.lower(), value)

    def __contains__(self, key: object) -> bool:
        """Return True when the header name exists, ignoring case."""
        if isinstance(key, str):
            return super().__contains__(key.lower())
        return False

    @t.overload
    def get(self, key: str) -> str | None: ...
    @t.overload
    def get(self, key: str, default: str) -> str: ...
    @t.overload
    def get(self, key: str, default: T) -> str | T: ...
    @t.overload
    def get(self, key: str, type_: t.Callable[[str], T]) -> T | None: ...
    @t.overload
    def get(self, key: str, default: T, type_: t.Callable[[str], T]) -> T: ...

    def get(
        self,
        key: K,
        default: str | T | None = None,
        type_: t.Callable[[str], T] | None = None,
    ) -> str | T | None:
        """Return the first header value matching name  or a default.

        :param key: Lookup key.
        :param default: Value returned when the key is missing,
            defaults to ``None``.
        :param type_: Optional converter applied to the fetched value,
            defaults to ``None``.
        """
        try:
            value = self[key]
            return type_(value) if type_ is not None else value
        except (KeyError, ValueError):
            return default

    @t.overload
    def getlist(self, key: str) -> list[str]: ...
    @t.overload
    def getlist(self, key: str, type_: t.Callable[[str], T]) -> list[T]: ...

    def getlist(
        self,
        key: str,
        type_: t.Callable[[str], T] | None = None,
    ) -> list[str] | list[T]:
        """Return all header values matching the name."""
        return super().getlist(key.lower(), type_)
