from app.core.route_inventory import find_stale_policies, find_unlisted_routes
from app.main import app


def test_no_unlisted_or_stale_routes():
    assert find_unlisted_routes(app) == []
    assert find_stale_policies(app) == []


def test_new_route_is_reported_as_unlisted():
    path = "/__inventory_probe__"

    async def probe():
        return {}

    app.add_api_route(path, probe, methods=["GET"])
    try:
        assert ("GET", path) in find_unlisted_routes(app)
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != path]
    assert find_unlisted_routes(app) == []
