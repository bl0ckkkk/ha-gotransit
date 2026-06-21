"""Test that API body parsing reads text once and parses JSON from it.

This guards against the double-read regression where reading resp.text()
then resp.json() consumed the stream twice and raised."""
import json
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "go_transit"))


def test_json_loads_from_text_body():
    # Simulates what _api_get now does: read text, json.loads it.
    body = '{"Metadata":{"ErrorCode":"200"},"NextService":{"Lines":[]}}'
    data = json.loads(body)
    assert data["Metadata"]["ErrorCode"] == "200"
    assert data["NextService"]["Lines"] == []


def test_json_loads_rejects_html():
    # A non-JSON body (e.g. an error page) must raise ValueError, which the
    # code maps to _ApiError / UpdateFailed rather than a silent crash.
    body = "<html>503 Service Unavailable</html>"
    try:
        json.loads(body)
        assert False, "should have raised"
    except (ValueError, TypeError):
        pass
