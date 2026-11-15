"""API reference: ``/openapi.json``, ``/docs`` (Swagger UI), ``/redoc``.

Public only when ``ALERTD_DOCS_ENABLED`` says so (auto: open on a dev/HTTP
deploy, closed on a prod/TLS one — audit S-12). When not public, any
authenticated caller still gets them: an admin-UI session (cookie, path
``/``) or an ``X-API-Key``. Anonymous requests get 401 on the JSON and a
redirect to the admin login for the HTML pages, so the API shape is never
served to someone who has not logged in.

The schema is annotated with ``x-required-scope`` per operation, derived
from the ``require_scope(...)`` / ``require_user_session`` dependencies, so
the reference shows which key scope each call needs.
"""
from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi import routing as fastapi_routing
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import _HEADER, Actor, get_current_actor, require_user_session
from ..db import get_session

OPENAPI_PATH = "/openapi.json"
SCOPE_EXTENSION = "x-required-scope"
_SCOPE_DEP_PREFIX = "require_scope_"


async def _optional_actor(
    request: Request,
    api_key: str | None = Depends(_HEADER),
    session: AsyncSession = Depends(get_session),
) -> Actor | None:
    """The authenticated actor, or None for an anonymous request."""
    try:
        return await get_current_actor(request, api_key, session)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            return None
        raise


async def _no_actor() -> None:
    """Public reference: no authentication, no database access."""
    return None


def _api_routes(routes: Sequence[Any]) -> Iterator[Any]:
    """Every API route as the OpenAPI generator sees it: effective path
    (router prefixes applied) and dependant (router dependencies included).

    FastAPI ≥0.16x keeps included routers lazy (``iter_route_contexts``);
    older versions flatten them into plain ``APIRoute`` objects."""
    iter_contexts = getattr(fastapi_routing, "iter_route_contexts", None)
    if iter_contexts is None:  # pragma: no cover — older FastAPI
        yield from (r for r in routes if isinstance(r, APIRoute))
        return
    for ctx in iter_contexts(routes):
        if isinstance(ctx.original_route, APIRoute):
            yield ctx


def _dependency_scopes(route: Any) -> list[str]:
    """Scopes demanded by a route's dependency tree (``session`` for
    endpoints that only accept a browser session)."""
    found: set[str] = set()
    stack = list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        name = getattr(dep.call, "__name__", "")
        if name.startswith(_SCOPE_DEP_PREFIX):
            found.add(name[len(_SCOPE_DEP_PREFIX):])
        elif dep.call is require_user_session:
            found.add("session")
        stack.extend(dep.dependencies)
    return sorted(found)


def annotate_scopes(schema: dict[str, Any], routes: Sequence[Any]) -> None:
    """Add ``x-required-scope`` to every operation whose scope is declared
    through a dependency (in place)."""
    paths = schema.get("paths", {})
    for route in _api_routes(routes):
        if not route.include_in_schema:
            continue
        scopes = _dependency_scopes(route)
        if not scopes:
            continue
        ops = paths.get(route.path_format, {})
        for method in route.methods or ():
            op = ops.get(method.lower())
            if op is not None:
                op[SCOPE_EXTENSION] = scopes[0] if len(scopes) == 1 else scopes


def install_api_reference(app: FastAPI, *, public: bool) -> None:
    """Annotate the schema and register the three reference routes."""
    base_openapi = app.openapi
    annotated: list[int] = []  # id() of the schema object already annotated

    def openapi() -> dict[str, Any]:
        # FastAPI caches the schema and rebuilds it when the routes change;
        # annotate each freshly built object exactly once.
        schema = base_openapi()
        if not annotated or annotated[0] != id(schema):
            annotate_scopes(schema, app.routes)
            annotated[:] = [id(schema)]
        return schema

    app.openapi = openapi  # type: ignore[method-assign]

    # Public: don't touch auth (or the DB) at all. Otherwise resolve the
    # caller and let anonymous requests through to a 401 / login redirect.
    actor_dep = _no_actor if public else _optional_actor

    def allowed(actor: Actor | None) -> bool:
        return public or actor is not None

    def login_redirect() -> Response:
        return RedirectResponse("/admin/", status_code=status.HTTP_303_SEE_OTHER)

    @app.get(OPENAPI_PATH, include_in_schema=False)
    async def openapi_json(actor: Actor | None = Depends(actor_dep)) -> Response:
        if not allowed(actor):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail="Log in (admin UI session) or send X-API-Key to read the API schema",
                headers={"WWW-Authenticate": "ApiKey"},
            )
        return JSONResponse(app.openapi())

    @app.get("/docs", include_in_schema=False)
    async def swagger_ui(actor: Actor | None = Depends(actor_dep)) -> Response:
        if not allowed(actor):
            return login_redirect()
        return get_swagger_ui_html(
            openapi_url=OPENAPI_PATH,
            title=f"{app.title} — API reference",
            swagger_ui_parameters={"showExtensions": True, "persistAuthorization": False},
        )

    @app.get("/redoc", include_in_schema=False)
    async def redoc(actor: Actor | None = Depends(actor_dep)) -> Response:
        if not allowed(actor):
            return login_redirect()
        return get_redoc_html(openapi_url=OPENAPI_PATH, title=f"{app.title} — API reference")
