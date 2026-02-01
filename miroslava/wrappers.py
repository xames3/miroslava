"""\
Miroslava's sans-IO Request/Response
====================================

Author: Akshay Mestry <xa@mes3.dev>
Created on: 26 January, 2026
Last updated on: 31 January, 2026

This module implements basic sans-IO abstractions related to
request/responses.
"""

from __future__ import annotations

import typing as t
from urllib.parse import parse_qsl

from miroslava.datastructures import MultiDict
from miroslava.utils import _get_server
from miroslava.utils import get_content_type
from miroslava.utils import get_current_url
from miroslava.utils import set_module

if t.TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Iterator
    from collections.abc import Mapping
    from http import HTTPStatus

type EnvironHeaders = MultiDict
type Headers = MultiDict
type WSGIEnvironment = dict[str, t.Any]


@set_module("miroslava.sansio.response")
class _SansIORequest:
    """Represents the non-IO parts of an HTTP request, including the
    method, URL, info, and headers.

    :param method: The method the request was made with.
    :param scheme: The URL scheme of the protocol the request used.
    :param server: The address of the server.
    :param root_path: Prefix that the application is mounted under.
    :param path: Path part of the URL after `root_path`.
    :param query_string: The part of URL after the `?`.
    :param headers: The headers received with the request.
    :param remote_addr: The address of the client sending the request.
    """

    paramter_storage_class: MultiDict[str, str]

    def __init__(
        self,
        method: str,
        scheme: str,
        server: tuple[str, int | None] | None,
        root_path: str,
        path: str,
        query_string: str,
        headers: EnvironHeaders,
        remote_addr: str | None,
    ) -> None:
        """Initialise a request object with HTTP request details."""
        self.method = method.upper()
        self.scheme = scheme
        self.server = server
        self.root_path = root_path.rstrip("/")
        self.path = "/" + path.lstrip("/")
        self.query_string = query_string
        self.headers = headers
        self.remote_addr = remote_addr

    def __repr__(self) -> str:
        """Human-readable representation of the `Request` object."""
        return f"<{type(self).__name__} {self.url} [{self.method}]>"

    @property
    def args(self) -> MultiDict[str, str]:
        """Return the parsed URL parameters."""
        return self.parameter_storage_class(
            parse_qsl(self.query_string, keep_blank_values=True)
        )

    @property
    def full_path(self) -> str:
        """Complete path with query string parameters."""
        return f"{self.path}?{self.query_string}"

    @property
    def is_secure(self) -> bool:
        """Return `True` if request was made with `HTTPS` protocol."""
        return self.scheme == "https"

    @property
    def url(self) -> str:
        """Properly formatted request URL with scheme, host, and path
        details.
        """
        return get_current_url(
            self.scheme,
            self.host,
            self.root_path,
            self.path,
            self.query_string,
        )


class Request(_SansIORequest):
    """Represents an incoming WSGI HTTP request, with headers and body.

    Based on various HTTP specs, the `Request` object has necessary
    properties and methods for functioning as a proper HTTP request.

    :param environ: WSGI environment created by the server, containing
        all the necessary details about server configuration and client
        request.
    """

    def __init__(self, environ: WSGIEnvironment) -> None:
        """Initialise a request instance from WSGI environment."""
        super().__init__(
            method=environ.get("REQUEST_METHOD", "GET"),
            scheme=environ.get("URL_SCHEME", "http"),
            server=_get_server(environ),
            root_path=environ.get("SCRIPT_NAME", ""),
            path=environ.get("PATH_INFO", ""),
            query_string=environ.get("QUERY_STRING", ""),
            headers=EnvironHeaders(environ),
            remote_addr=environ.get("REMOTE_ADDR"),
        )
        self.environ = environ
        self.form: MultiDict[str, str] = MultiDict()
        self.data: bytes = b""
        self.json: dict[str, t.Any] | None = None


@set_module("miroslava.sansio.request")
class _SansIOResponse:
    """Represents teh non-IO parts of an HTTP response, specifically
    the status and headers, but not the body.

    :param status: The HTTP status code, defaults to `None`.
    :param headers: Dictionary of headers to include in response.
    :param mimetype: Mimetype of the response, defaults to `None`.
    :param content_type: Complete content type of the response,
        defaults to `None`.
    """

    default_status: t.ClassVar[int] = 200
    default_mimetype: t.ClassVar[str | None] = "text/plain"
    headers: Headers

    def __init__(
        self,
        status: int | str | HTTPStatus | None = None,
        headers: (
            MultiDict[str, str | Iterable[str]]
            | Mapping[str, str | Iterable[str]]
            | Iterable[tuple[str, str]]
            | None
        ) = None,
        mimetype: str | None = None,
        content_type: str | None = None,
    ) -> None:
        """Initialise a response object with status and headers."""
        if isinstance(headers, Headers):
            self.headers = headers
        elif not headers:
            self.headers = Headers()
        else:
            self.headers = Headers(headers)
        if content_type is None:
            if mimetype is None and "content-type" not in self.headers:
                mimetype = self.default_mimetype
            if mimetype is not None:
                mimetype = get_content_type(mimetype, "utf-8")
            content_type = mimetype
        if content_type is not None:
            self.headers["Content=Type"] = content_type
        if status is None:
            status = self.default_status
        self.status = status

    def __repr__(self) -> str:
        """Human-readable representation of the `Response` object."""
        return f"<{type(self).__name__} [{self.status}]>"

    @property
    def status_code(self) -> int:
        """Return the HTTP status code."""
        return int(self._status_code)

    @status_code.setter
    def status_code(self, code: int) -> None:
        """Set the HTTP status code."""
        self.status = code

    @property
    def status(self) -> str:
        """Return the HTTP status code as a string."""
        return self._status

    @status.setter
    def status(self, value: str | int | HTTPStatus) -> None:
        """Set the HTTP status code."""
        raise NotImplementedError


class Response(_SansIOResponse):
    """Represents an outgoing WSGI HTTP response with body, status, and
    headers.

    Similar to `Request`, based on various HTTP specs, the `Response`
    object too has necessary properties and methods for functioning as
    a proper HTTP response.

    :param response: Data for the body of the response, defaults to
        `None`.
    :param status: The HTTP status code, defaults to `None`.
    :param headers: Dictionary of headers to include in response.
    :param mimetype: Mimetype of the response, defaults to `None`.
    :param content_type: Complete content type of the response,
        defaults to `None`.
    :param direct_passthrough: Pass the response body directly through
        as the WSGI iterable, defaults to `False`.
    """

    response: Iterable[str] | Iterable[bytes]

    def __init__(
        self,
        response: Iterable[bytes] | bytes | Iterable[str] | str | None = None,
        status: int | str | HTTPStatus | None = None,
        headers: (
            Mapping[str, str | Iterable[str]] | Iterable[tuple[str, str]] | None
        ) = None,
        mimetype: str | None = None,
        content_type: str | None = None,
        *,
        direct_passthrough: bool = False,
    ) -> None:
        """Initialise a response instance with necessary details."""
        super().__init__(
            status=status,
            headers=headers,
            mimetype=mimetype,
            content_type=content_type,
        )
        self.direct_passthrough = direct_passthrough
        if response is None:
            self.response = []
        elif isinstance(response, (str, bytes, bytearray)):
            self.set_data(response)
        else:
            self.response = response

    def __repr__(self) -> str:
        """Human-readable representation of the `Response` object."""
        body = f"{sum(map(len, self.iter_encoded()))} bytes"
        return f"<{type(self).__name__} {body} [{self.status}]>"

    def iter_encoded(self) -> Iterator[bytes]:
        """Iterate over the response and yield them as bytes."""
        for item in self.response:
            yield item.encode() if isinstance(item, str) else item

    @t.override
    def get_data(self, as_text: bool = False) -> bytes | str:
        """Return the string representation of the request body."""
        data = b"".join(self.iter_encoded())
        return data.decode() if as_text else data

    def set_data(self, value: bytes | str) -> None:
        """Set a new string as response."""
        if isinstance(value, str):
            value = value.encode()
        self.response = [value]
        self.headers["Content-Length"] = str(len(value))

    data = property(get_data, set_data)
