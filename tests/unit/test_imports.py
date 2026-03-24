from fastapi import FastAPI


def test_create_app_returns_fastapi_app():
    from pulse.app.main import create_app

    app = create_app()

    assert isinstance(app, FastAPI)
