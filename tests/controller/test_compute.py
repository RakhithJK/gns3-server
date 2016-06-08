#!/usr/bin/env python
#
# Copyright (C) 2016 GNS3 Technologies Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import pytest
import json
import aiohttp
import asyncio
from unittest.mock import patch, MagicMock

from gns3server.controller.project import Project
from gns3server.controller.compute import Compute, ComputeError, ComputeConflict
from gns3server.version import __version__
from tests.utils import asyncio_patch, AsyncioMagicMock


@pytest.fixture
def compute(controller):
    compute = Compute("my_compute_id", protocol="https", host="example.com", port=84, controller=controller)
    compute._connected = True
    return compute


def test_init(compute):
    assert compute.id == "my_compute_id"


def test_name():
    c = Compute("my_compute_id", protocol="https", host="example.com", port=84, controller=MagicMock(), name=None)
    assert c.name == "https://example.com:84"
    with patch("gns3server.config.Config.get_section_config", return_value={"local": True}):
        c = Compute("local", protocol="https", host="example.com", port=84, controller=MagicMock(), name=None)
        assert c.name == "Local"
    c = Compute("world", protocol="https", host="example.com", port=84, controller=MagicMock(), name="hello")
    assert c.name == "hello"
    c = Compute("world", protocol="https", host="example.com", port=84, controller=MagicMock(), user="azertyuiopqsdfghjklkm")
    assert c.name == "https://azertyuiopq...@example.com:84"


def test_compute_local(compute):
    """
    If the compute is local but the compute id is local
    it's a configuration issue
    """

    with patch("gns3server.config.Config.get_section_config", return_value={"local": False}):
        with pytest.raises(ComputeError):
            s = Compute("local", controller=MagicMock())

    with patch("gns3server.config.Config.get_section_config", return_value={"local": True}):
        s = Compute("test", controller=MagicMock())


def test_compute_httpQuery(compute, async_run):
    response = MagicMock()
    with asyncio_patch("aiohttp.ClientSession.request", return_value=response) as mock:
        response.status = 200

        async_run(compute.post("/projects", {"a": "b"}))
        mock.assert_called_with("POST", "https://example.com:84/v2/compute/projects", data='{"a": "b"}', headers={'content-type': 'application/json'}, auth=None, chunked=False)
        assert compute._auth is None


def test_compute_httpQueryAuth(compute, async_run):
    response = MagicMock()
    with asyncio_patch("aiohttp.ClientSession.request", return_value=response) as mock:
        response.status = 200

        compute.user = "root"
        compute.password = "toor"
        async_run(compute.post("/projects", {"a": "b"}))
        mock.assert_called_with("POST", "https://example.com:84/v2/compute/projects", data='{"a": "b"}', headers={'content-type': 'application/json'}, auth=compute._auth, chunked=False)
        assert compute._auth.login == "root"
        assert compute._auth.password == "toor"


def test_compute_httpQueryNotConnected(compute, controller, async_run):
    controller._notification = MagicMock()
    compute._connected = False
    response = AsyncioMagicMock()
    response.read = AsyncioMagicMock(return_value=json.dumps({"version": __version__}).encode())
    response.status = 200
    with asyncio_patch("aiohttp.ClientSession.request", return_value=response) as mock:
        async_run(compute.post("/projects", {"a": "b"}))
        mock.assert_any_call("GET", "https://example.com:84/v2/compute/version", headers={'content-type': 'application/json'}, data=None, auth=None, chunked=False)
        mock.assert_any_call("POST", "https://example.com:84/v2/compute/projects", data='{"a": "b"}', headers={'content-type': 'application/json'}, auth=None, chunked=False)
    assert compute._connected
    assert compute.version == __version__
    controller.notification.emit.assert_called_with("compute.updated", compute.__json__())


def test_compute_httpQueryNotConnectedInvalidVersion(compute, async_run):
    compute._connected = False
    response = AsyncioMagicMock()
    response.read = AsyncioMagicMock(return_value=json.dumps({"version": "1.42.4"}).encode())
    response.status = 200
    with asyncio_patch("aiohttp.ClientSession.request", return_value=response) as mock:
        with pytest.raises(aiohttp.web.HTTPConflict):
            async_run(compute.post("/projects", {"a": "b"}))
        mock.assert_any_call("GET", "https://example.com:84/v2/compute/version", headers={'content-type': 'application/json'}, data=None, auth=None, chunked=False)


def test_compute_httpQueryNotConnectedNonGNS3Server(compute, async_run):
    compute._connected = False
    response = AsyncioMagicMock()
    response.read = AsyncioMagicMock(return_value=b'Blocked by super antivirus')
    response.status = 200
    with asyncio_patch("aiohttp.ClientSession.request", return_value=response) as mock:
        with pytest.raises(aiohttp.web.HTTPConflict):
            async_run(compute.post("/projects", {"a": "b"}))
        mock.assert_any_call("GET", "https://example.com:84/v2/compute/version", headers={'content-type': 'application/json'}, data=None, auth=None, chunked=False)


def test_compute_httpQueryNotConnectedNonGNS3Server2(compute, async_run):
    compute._connected = False
    response = AsyncioMagicMock()
    response.read = AsyncioMagicMock(return_value=b'{}')
    response.status = 200
    with asyncio_patch("aiohttp.ClientSession.request", return_value=response) as mock:
        with pytest.raises(aiohttp.web.HTTPConflict):
            async_run(compute.post("/projects", {"a": "b"}))
        mock.assert_any_call("GET", "https://example.com:84/v2/compute/version", headers={'content-type': 'application/json'}, data=None, auth=None, chunked=False)


def test_compute_httpQueryError(compute, async_run):
    response = MagicMock()
    with asyncio_patch("aiohttp.ClientSession.request", return_value=response) as mock:
        response.status = 404

        with pytest.raises(aiohttp.web.HTTPNotFound):
            async_run(compute.post("/projects", {"a": "b"}))


def test_compute_httpQueryConflictError(compute, async_run):
    response = MagicMock()
    with asyncio_patch("aiohttp.ClientSession.request", return_value=response) as mock:
        response.status = 409
        response.read = AsyncioMagicMock(return_value=b'{"message": "Test"}')

        with pytest.raises(ComputeConflict):
            async_run(compute.post("/projects", {"a": "b"}))


def test_compute_httpQuery_project(compute, async_run):
    response = MagicMock()
    with asyncio_patch("aiohttp.ClientSession.request", return_value=response) as mock:
        response.status = 200

        project = Project()
        async_run(compute.post("/projects", project))
        mock.assert_called_with("POST", "https://example.com:84/v2/compute/projects", data=json.dumps(project.__json__()), headers={'content-type': 'application/json'}, auth=None, chunked=False)


def test_connectNotification(compute, async_run):
    ws_mock = AsyncioMagicMock()

    call = 0

    @asyncio.coroutine
    def receive():
        nonlocal call
        call += 1
        if call == 1:
            response = MagicMock()
            response.data = '{"action": "test", "event": {"a": 1}}'
            response.tp = aiohttp.MsgType.text
            return response
        else:
            response = MagicMock()
            response.tp = aiohttp.MsgType.closed
            return response

    compute._controller._notification = MagicMock()
    compute._session = AsyncioMagicMock(return_value=ws_mock)
    compute._session.ws_connect = AsyncioMagicMock(return_value=ws_mock)
    ws_mock.receive = receive
    async_run(compute._connect_notification())

    compute._controller.notification.dispatch.assert_called_with('test', {'a': 1}, compute_id=compute.id)
    assert compute._connected is False


def test_json(compute):
    compute.user = "test"
    assert compute.__json__() == {
        "compute_id": "my_compute_id",
        "name": compute.name,
        "protocol": "https",
        "host": "example.com",
        "port": 84,
        "user": "test",
        "connected": True
    }


def test_streamFile(project, async_run, compute):
    response = MagicMock()
    response.status = 200
    with asyncio_patch("aiohttp.ClientSession.request", return_value=response) as mock:
        async_run(compute.steam_file(project, "test/titi"))
    mock.assert_called_with("GET", "https://example.com:84/v2/compute/projects/{}/stream/test/titi".format(project.id), auth=None)


def test_close(compute, async_run):
    assert compute.connected is True
    async_run(compute.close())
    assert compute.connected is False


def test_update(compute, controller, async_run):
    compute._controller._notification = MagicMock()
    compute.name = "Test"
    compute.host = "example.org"
    compute._connected = True
    async_run(compute.update(name="Test 2"))
    assert compute.name == "Test 2"
    assert compute.host == "example.org"
    controller.notification.emit.assert_called_with("compute.updated", compute.__json__())
    assert compute.connected is False


def test_forward_get(compute, async_run):
    response = MagicMock()
    response.status = 200
    with asyncio_patch("aiohttp.ClientSession.request", return_value=response) as mock:
        async_run(compute.forward("GET", "qemu", "images"))
        mock.assert_called_with("GET", "https://example.com:84/v2/compute/qemu/images", auth=None, data=None, headers={'content-type': 'application/json'}, chunked=False)


def test_forward_post(compute, async_run):
    response = MagicMock()
    response.status = 200
    with asyncio_patch("aiohttp.ClientSession.request", return_value=response) as mock:
        async_run(compute.forward("POST", "qemu", "img", data={"id": 42}))
        mock.assert_called_with("POST", "https://example.com:84/v2/compute/qemu/img", auth=None, data='{"id": 42}', headers={'content-type': 'application/json'}, chunked=False)


def test_images(compute, async_run, images_dir):
    """
    Will return image on compute and on controller
    """
    response = MagicMock()
    response.status = 200
    response.read = AsyncioMagicMock(return_value=json.dumps([{"filename": "linux.qcow2", "path": "linux.qcow2"}]).encode())
    open(os.path.join(images_dir, "asa.qcow2"), "w+").close()
    with asyncio_patch("aiohttp.ClientSession.request", return_value=response) as mock:
        images = async_run(compute.images("qemu"))
        mock.assert_called_with("GET", "https://example.com:84/v2/compute/qemu/images", auth=None, data=None, headers={'content-type': 'application/json'}, chunked=False)

    assert images == [{"filename": "linux.qcow2", "path": "linux.qcow2"}, {"filename": "asa.qcow2", "path": "asa.qcow2"}]
