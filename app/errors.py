"""Exception -> JSON error mapping. The API never returns HTML errors under /api."""
from __future__ import annotations

import logging

from flask import Flask, jsonify, request
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException

from .contracts import NoRoute, PointOutsideArea
from .engine.service import UnknownScenario

log = logging.getLogger(__name__)


class InvalidJSON(Exception):
    pass


def _error(status: int, code: str, detail=None):
    body = {"error": code}
    if detail is not None:
        body["detail"] = detail
    return jsonify(body), status


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ValidationError)
    def _validation(e: ValidationError):
        return _error(400, "validation", e.errors(include_url=False, include_context=False))

    @app.errorhandler(InvalidJSON)
    def _invalid_json(e: InvalidJSON):
        return _error(400, "validation", str(e))

    @app.errorhandler(UnknownScenario)
    def _unknown_scenario(e: UnknownScenario):
        return _error(400, "validation", str(e))

    @app.errorhandler(PointOutsideArea)
    def _outside(e: PointOutsideArea):
        return _error(422, "point_outside_area", {"index": e.index, "message": str(e)})

    @app.errorhandler(NoRoute)
    def _no_route(e: NoRoute):
        return _error(404, "no_route", str(e))

    @app.errorhandler(HTTPException)
    def _http(e: HTTPException):
        if not request.path.startswith("/api"):
            return e
        return _error(e.code or 500, (e.name or "error").lower().replace(" ", "_"))

    @app.errorhandler(Exception)
    def _internal(e: Exception):
        log.exception("unhandled error on %s %s", request.method, request.path)
        return _error(500, "internal")
