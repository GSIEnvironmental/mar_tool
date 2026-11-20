import flask
import matplotlib
import pytest

import mar_dss.app.utils.data_storage as data_storage

# Don't open plot windows during tests.
matplotlib.use("Agg")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(data_storage, "_sessions", {})
    monkeypatch.setattr(data_storage, "_data_storage", {})
    app = flask.Flask(__name__)
    data_storage.init_app(app)

    @app.get("/set/<value>")
    def set_value(value):
        data_storage.set_data("project_name", value)
        return "ok"

    @app.get("/get")
    def get_value():
        return data_storage.get_data("project_name") or ""

    return app.test_client
