"""\
Miroslava's Wrappers
====================

Author: Akshay Mestry <xa@mes3.dev>
Created on: 26 January, 2026
Last updated on: 03 February, 2026

This module provides the public ``Request`` and ``Response`` classes.

The ``Request`` class turns a WSGI environment mapping into a
friendlier object that exposes parsed query arguments, form data, and
JSON bodies.

The ``Response`` class holds outgoing HTTP payloads, status metadata,
and headers, keeping its interface close to Flask's base response type
so that view functions can return strings, bytes, iterables, or fully
constructed ``Response`` objects.
"""

from __future__ import annotations

import json
import typing as t
from http import HTTPStatus
from urllib.parse import parse_qsl

from miroslava.datastructures import Headers
from miroslava.datastructures import MultiDict
from miroslava.utils import _get_server
from miroslava.utils import get_content_type
from miroslava.utils import get_current_url

if t.TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Iterator
    from collections.abc import Mapping

type WSGIEnvironment = dict[str, t.Any]

HTTP_STATUS_CODES: dict[int, str] = {
    100: "Continue",
    101: "Switching Protocols",
    102: "Processing",
    103: "Early Hints",
    200: "OK",
    201: "Created",
    202: "Accepted",
    203: "Non Authoritative Information",
    204: "No Content",
    205: "Reset Content",
    206: "Partial Content",
    207: "Multi Status",
    208: "Already Reported",
    226: "IM Used",
    300: "Multiple Choices",
    301: "Moved Permanently",
    302: "Found",
    303: "See Other",
    304: "Not Modified",
    305: "Use Proxy",
    306: "Switch Proxy",
    307: "Temporary Redirect",
    308: "Permanent Redirect",
    400: "Bad Request",
    401: "Unauthorized",
    402: "Payment Required",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    406: "Not Acceptable",
    407: "Proxy Authentication Required",
    408: "Request Timeout",
    409: "Conflict",
    410: "Gone",
    411: "Length Required",
    412: "Precondition Failed",
    413: "Request Entity Too Large",
    414: "Request URI Too Long",
    415: "Unsupported Media Type",
    416: "Requested Range Not Satisfiable",
    417: "Expectation Failed",
    418: "I'm a teapot",
    421: "Misdirected Request",
    422: "Unprocessable Entity",
    423: "Locked",
    424: "Failed Dependency",
    425: "Too Early",
    426: "Upgrade Required",
    428: "Precondition Required",
    429: "Too Many Requests",
    431: "Request Header Fields Too Large",
    449: "Retry With",
    451: "Unavailable For Legal Reasons",
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
    505: "HTTP Version Not Supported",
    506: "Variant Also Negotiates",
    507: "Insufficient Storage",
    508: "Loop Detected",
    510: "Not Extended",
    511: "Network Authentication Failed",
}
EnvironHeaders = Headers


class Request:
    """Represents an incoming WSGI HTTP request.

    A ``Request`` instance stores the raw WSGI environment and exposes
    higher-level helpers for the HTTP method, path, query string, and
    body.

    Instances are created per request during dispatch and should be
    treated as read-only representations of the inbound message.

    :param environ: Mapping containing the CGI-style WSGI keys for
        the active request.
    """

    parameter_storage_class: type[MultiDict[str, str]] = MultiDict

    def __init__(self, environ: WSGIEnvironment) -> None:
        """Initialise a request object from the WSGI environment."""
        self.environ: WSGIEnvironment = environ
        self.method: str = environ.get("REQUEST_METHOD", "GET").upper()
        self.scheme: str = environ.get("wsgi.url_scheme", "http")
        self.server: tuple[str, int | None] | None = _get_server(environ)
        self.root_path: str = environ.get("SCRIPT_NAME", "")
        self.path: str = environ.get("PATH_INFO", "/")
        self.query_string: str = environ.get("QUERY_STRING", "")
        self.headers: EnvironHeaders = EnvironHeaders()
        for key, value in environ.items():
            if key.startswith("HTTP_"):
                header = key[5:].replace("_", "-").title()
                self.headers[header] = value
            elif key in ("CONTENT_LENGTH", "CONTENT_TYPE"):
                header = key.replace("_", "-").title()
                self.headers[header] = value
        self.remote_addr: str | None = environ.get("REMOTE_ADDR")
        self.data: bytes = environ.get("miroslava.request_body", b"")
        self._form: MultiDict[str, str] | None = None
        self._json: dict[str, t.Any] | None = None

    def __repr__(self) -> str:
        """Human-readable representation of the `Request` object."""
        return f"<{type(self).__name__} {self.url} [{self.method}]>"

    @property
    def args(self) -> MultiDict[str, str]:
        """Return parsed query parameters from the URL.

        The query string is decoded into a MultiDict so repeated keys
        remain accessible.
        """
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

    @property
    def form(self) -> MultiDict[str, str]:
        """Return parsed form data for URL-encoded bodies.

        When the ``Content-Type`` header indicates form submission, the
        cached body is decoded as UTF-8 and split into a ``MultiDict``.
        When the body is absent or parsing fails, an empty
        ``MultiDict`` is provided.

        .. note::

            Accessing this property does not mutate the request.
        """
        if self._form is None:
            if "application/x-www-form-urlencoded" in self.headers.get(
                "Content-Type", ""
            ):
                try:
                    self._form = self.parameter_storage_class(
                        parse_qsl(self.data.decode(), keep_blank_values=True)
                    )
                except Exception:
                    self._form = MultiDict()
            else:
                self._form = MultiDict()
        return self._form

    @property
    def json(self) -> dict[str, t.Any] | None:
        """Return parsed JSON content when the request body is JSON.

        The method checks the ``Content-Type`` header for an
        ``application/json`` marker before attempting to decode the
        cached body. On decoding errors the property yields ``None`` to
        mirror Flask's behaviour when silent parsing is desired.
        """
        if self._json is None and "application/json" in self.headers.get(
            "Content-Type", ""
        ):
            try:
                self._json = json.loads(self.data.decode())
            except Exception:
                self._json = None
        return self._json


class Response:
    """Represents an outgoing WSGI response.

    This class mirrors Flask's response object by capturing the status
    code, reason phrase, headers, and body. It accepts common return
    value shapes from view functions, including strings, bytes, and
    iterables of bytes. The stored data can be read back as bytes or
    decoded text, and the status line is normalised to include an
    integer code and phrase.

    :param response: Payload content as a string, bytes, iterable of
        bytes, or None for an empty body.
    :param status: HTTP status code or string; integers are matched
        to HTTPStatus for a reason phrase when possible.
    :param headers: Initial header mapping to apply to the response.
    :param mimetype: Convenience mimetype; resolved to a content
        type with charset for textual types.
    :param content_type: Explicit content type overriding mimetype.
    """

    default_status: t.ClassVar[int] = 200
    default_mimetype: t.ClassVar[str | None] = "text/html"
    headers: Headers
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
        direct_passthrough: bool = False,
    ) -> None:
        """Initialise the response object from flexible inputs."""
        self.headers: Headers = Headers(headers or {})
        if status is None:
            status = self.default_status
        self.status = status
        if content_type is None:
            if mimetype is None and "Content-Type" not in self.headers:
                mimetype = self.default_mimetype
            if mimetype is not None:
                mimetype = get_content_type(mimetype, "utf-8")
            content_type = mimetype
        if content_type:
            self.headers["Content-Type"] = content_type
        if response is None:
            self.response = [b""]
        elif isinstance(response, str):
            self.response = [response.encode()]
        elif isinstance(response, bytes):
            self.response = [response]
        else:
            self.response = [
                chunk if isinstance(chunk, bytes) else str(chunk).encode()
                for chunk in response
            ]
        self.direct_passthrough = direct_passthrough

    def __repr__(self) -> str:
        """Human-readable representation of the response object."""
        body = f"{sum(map(len, self.iter_encoded()))} bytes"
        return f"<{type(self).__name__} {body} [{self.status}]>"

    @property
    def status_code(self) -> int:
        """Return HTTP status code as a number."""
        return self._status_code

    @status_code.setter
    def status_code(self, code: int) -> None:
        """Set an HTTP status code."""
        self.status = code

    @property
    def status(self) -> str:
        """Return the concatenated status code and phrase."""
        return self._status

    @status.setter
    def status(self, value: str | int | HTTPStatus) -> None:
        """Set HTTP status."""
        self._status, self._status_code = self._clean_status(value)

    @staticmethod
    def _clean_status(value: int | str | HTTPStatus) -> tuple[str, int]:
        """Normalise status inputs to a numeric code and phrase."""
        if isinstance(value, HTTPStatus):
            return f"{value.value} {value.phrase}", value.value
        if isinstance(value, int):
            try:
                status = HTTPStatus(value)
            except ValueError:
                return str(value), value
            else:
                return f"{value} {status.phrase}", value
        if isinstance(value, str):
            parts = value.split(" ", 1)
            try:
                status_code = int(parts[0])
                phrase = parts[1] if len(parts) > 1 else ""
                if not phrase:
                    try:
                        phrase = HTTPStatus(status_code).phrase
                    except ValueError:
                        phrase = ""
                status = f"{status_code} {phrase}".strip()
            except ValueError as err:
                raise ValueError(
                    "Status must start with an integer code"
                ) from err
            else:
                return (
                    f"{status_code} {HTTP_STATUS_CODES[status_code].upper()}"
                ), status_code
        raise TypeError("Invalid status value type")

    def iter_encoded(self) -> Iterator[bytes]:
        """Iterate over the response and yield them as bytes."""
        for item in self.response:
            yield item if isinstance(item, bytes) else str(item).encode()

    def get_data(self, as_text: bool = False) -> str | bytes:
        """Return the stored payload as bytes or text.

        :param as_text: When ``True``, decode the body using the
            supplied charset.
        :return: Decoded payload based on passed argument.
        """
        data = b"".join(self.iter_encoded())
        return data.decode() if as_text else data

    def set_data(self, value: str | bytes) -> None:
        """Replace the payload data on the response."""
        if isinstance(value, str):
            self.response = [value.encode()]
        else:
            self.response = [value]
        self.headers["Content-Length"] = str(len(value))

    data = property(get_data, set_data)
