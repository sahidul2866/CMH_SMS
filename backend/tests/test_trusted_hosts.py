import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient

from app.trusted_hosts import NetworkTrustedHostMiddleware


async def hello(request):
    return PlainTextResponse('ok')


async def socket(websocket):
    await websocket.accept()
    await websocket.send_text('ok')
    await websocket.close()


def application():
    return NetworkTrustedHostMiddleware(
        Starlette(routes=[Route('/', hello), WebSocketRoute('/ws', socket)]),
        allowed_hosts=['localhost', '127.0.0.1', '192.168.0.103', '10.0.0.0/8'],
    )


@pytest.mark.parametrize('host', ['localhost', '127.0.0.1:8100', '192.168.0.103', '10.0.0.1:8100', '10.255.255.254'])
def test_allowed_hosts(host):
    assert TestClient(application()).get('/', headers={'host': host}).status_code == 200


@pytest.mark.parametrize('host', ['11.0.0.1', '192.168.0.104', '10.example.com', '10.0.0.1.evil.example', '10.999.0.1'])
def test_other_hosts_are_rejected(host):
    assert TestClient(application()).get('/', headers={'host': host}).status_code == 400


def test_lan_websocket_allowed():
    with TestClient(application()).websocket_connect('/ws', headers={'host': '10.2.3.4:8100'}) as ws:
        assert ws.receive_text() == 'ok'
