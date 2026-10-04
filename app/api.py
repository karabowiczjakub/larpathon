"""HTTP endpoints under /api. Thin: validate input, call Engine, return JSON."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from .engine import Engine
from .errors import InvalidJSON
from .schemas import ConditionsQuery, LayerQuery, RouteRequest

bp = Blueprint("api", __name__)


def _engine() -> Engine:
    return current_app.extensions["engine"]


def _json_body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise InvalidJSON("request body must be a JSON object")
    return data


@bp.post("/route")
def route():
    req = RouteRequest.model_validate(_json_body())
    return jsonify(_engine().route(req))


@bp.post("/route/tradeoff")
def route_tradeoff():
    req = RouteRequest.model_validate(_json_body())
    return jsonify(_engine().tradeoff(req))


@bp.get("/scenarios")
def scenarios():
    return jsonify(_engine().scenarios())


@bp.get("/conditions")
def conditions():
    q = ConditionsQuery.model_validate(request.args.to_dict())
    return jsonify(_engine().conditions(q.scenario, q.at))


@bp.get("/layers/shade")
def shade_layer():
    q = LayerQuery.model_validate(request.args.to_dict())
    return jsonify(_engine().shade_layer(q))


@bp.get("/health")
def health():
    return jsonify(_engine().health())
