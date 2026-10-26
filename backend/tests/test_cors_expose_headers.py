"""Phase 7b S5: cross-origin downloads keep the server's file name (the frontend reads `Content-Disposition`)."""
from starlette.middleware.cors import CORSMiddleware


def test_main_app_exposes_content_disposition():
    from app.main import app

    cors = next(m for m in app.user_middleware if m.cls is CORSMiddleware)
    assert "Content-Disposition" in (cors.kwargs.get("expose_headers") or [])
