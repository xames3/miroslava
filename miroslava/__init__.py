"""\
Miroslava
=========

Author: Akshay Mestry <xa@mes3.dev>
Created on: 26 January, 2026
Last updated on: 31 January, 2026

Miroslava is a lightweight, risky, and non-production ready WSGI web
application microframework designed to mimic Flask's API structures.
"""

from __future__ import annotations

from miroslava.app import Miroslava as Miroslava
from miroslava.globals import current_app as current_app
from miroslava.globals import g as g
from miroslava.globals import request as request
from miroslava.globals import session as session
from miroslava.utils import jsonify as jsonify
from miroslava.utils import render_template as render_template
from miroslava.wrappers import Request as Request
from miroslava.wrappers import Response as Response

version: str = "26.1.2026"
