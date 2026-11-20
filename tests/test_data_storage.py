import mar_dss.app.utils.data_storage as data_storage


def test_each_browser_gets_its_own_storage(client):
    alice, bob = client(), client()
    alice.get("/set/alpha")
    bob.get("/set/bravo")
    assert alice.get("/get").text == "alpha"
    assert bob.get("/get").text == "bravo"


def test_new_session_starts_from_startup_storage(client):
    data_storage.set_data("project_name", "default")  # outside a request
    browser = client()
    assert browser.get("/get").text == "default"
    browser.get("/set/changed")
    assert data_storage.get_data("project_name") == "default"


def test_session_count_is_capped(client, monkeypatch):
    monkeypatch.setattr(data_storage, "_MAX_SESSIONS", 3)
    browsers = [client() for _ in range(5)]
    for i, browser in enumerate(browsers):
        browser.get(f"/set/user{i}")
    assert len(data_storage._sessions) == 3
    # The two oldest sessions were dropped.
    assert browsers[-1].get("/get").text == "user4"
    assert browsers[0].get("/get").text == ""


def test_returning_browser_expires_after_inactivity(client, monkeypatch):
    now = 100
    monkeypatch.setattr(data_storage.time, "time", lambda: now)
    monkeypatch.setattr(data_storage, "_SESSION_TTL_SECONDS", 10)
    browser = client()

    browser.get("/set/alpha")
    now += 9
    assert browser.get("/get").text == "alpha"
    now += 9
    assert browser.get("/get").text == "alpha"
    now += 11
    assert browser.get("/get").text == ""
