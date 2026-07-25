import base64
import json
import re

import pytest

from app.workers.register_handlers import mxluck


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+52 55 1234 5678", "5512345678"),
        ("5215512345678", "5512345678"),
        ("5512345678", "5512345678"),
    ],
)
def test_mx_local_number(raw, expected):
    assert mxluck._mx_local_number(raw) == expected


@pytest.mark.unit
def test_9amx_generated_identity_matches_frontend_rules():
    password = mxluck._gen_9amx_password()
    email = mxluck._gen_email()

    assert len(password) == 12
    assert re.search(r"[A-Z]", password)
    assert re.search(r"[a-z]", password)
    assert re.search(r"\d", password)
    assert re.fullmatch(r"mx[a-z0-9]{14}@gmail\.com", email)


@pytest.mark.unit
def test_parse_9amx_success_response():
    body = json.dumps({
        "status": 0,
        "user": {"userId": "abc123", "token": "session-token"},
    })

    assert mxluck._parse_register_response(200, body) == (True, 0)


@pytest.mark.unit
def test_parse_9amx_rejection_is_not_http_success():
    body = json.dumps({"status": 1004, "message": "Invalid image code"})

    assert mxluck._parse_register_response(200, body) == (False, 1004)


@pytest.mark.unit
@pytest.mark.parametrize(
    "body",
    [
        '{"success":true,"data":{"memberId":1}}',
        '{"code":0,"data":{"memberId":1}}',
        '{"code":200,"token":"abc"}',
    ],
)
def test_parse_legacy_success_response(body):
    ok, _status = mxluck._parse_register_response(200, body)
    assert ok is True


@pytest.mark.unit
def test_9amx_request_signature_matches_frontend_algorithm():
    values = {
        "sk-172bb21f1265ee3e219f6ad3400707a2": '"f75c4dd317a5bbf5abb484d6782094da"',
        "sk-c7998d8b485a9d8075971e7056de2f65": '"es"',
        "sk-04727cea908ef532ffca814a6835f9ae": '"MX"',
    }

    class Page:
        @staticmethod
        def evaluate(script, arg=None):
            if "localStorage" in script:
                return values.get(arg)
            if "getTimezoneOffset" in script:
                return -6
            if "navigator.userAgent" in script:
                return "test-agent"
            return None

    headers = mxluck._9amx_signed_headers(
        Page(), "/api/auth/register", now_ms=1784628546602
    )

    assert headers["ST"] == "1784628546602"
    assert headers["STT"] == "a54e4ff768ddb9db3e4b6c5c3ab06fb1"
    assert headers["x-path"] == "2LwFSah9XdoR3LlJ2ZzlGdyV"
    assert headers["BFID"] == "f75c4dd317a5bbf5abb484d6782094da"
    assert headers["COUNTRY"] == "MX"


@pytest.mark.unit
def test_9amx_api_registration_uses_same_origin_session(monkeypatch):
    class Page:
        url = "https://dx.9amx.com.mx/"
        posted = None

        @staticmethod
        def title():
            return "9AMX"

        def evaluate(self, script, arg=None):
            if "fetch(url" in script:
                assert arg.startswith("https://dx.9amx.com.mx/api/auth/image_code?t=")
                return {
                    "ok": True,
                    "status": 200,
                    "body": base64.b64encode(b"captcha-image").decode(),
                }
            if "fetch(arg.path" in script:
                assert arg["path"] == "/api/auth/register"
                self.posted = arg["payload"]
                return {
                    "status": 200,
                    "body": '{"status":0,"user":{"userId":"u1","token":"t1"}}',
                }
            if "localStorage" in script:
                return None
            if "getTimezoneOffset" in script:
                return -6
            if "navigator.userAgent" in script:
                return "test-agent"
            return None

    monkeypatch.setattr(
        "app.workers.geetest_solver.solve_image_captcha", lambda _image: "1234"
    )
    monkeypatch.setattr(
        "app.workers.geetest_solver.eval_captcha_answer", lambda answer: answer
    )

    page = Page()
    ok, credentials = mxluck._register_9amx_api(page, phone="+52 55 1234 5678")

    assert ok is True
    assert page.posted["phone"] == "5512345678"
    assert page.posted["countryId"] == "MX"
    assert page.posted["imageCode"] == "1234"
    assert "9AMX @ dx.9amx.com.mx" in credentials
