##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

import socket
import threading
import unittest

import psycopg

from pgadmin.utils.route import BaseTestGenerator
from pgadmin.utils.kubernetes import (
    KubernetesError,
    PortForwardTunnel,
    bind_address_for_host_mode,
    connect_host_for_host_mode,
    list_namespaces,
    resolve_reference,
    resolve_target_pod,
)

from .utils import (
    FIXTURES,
    SKIP_REASON,
    TEST_CONTEXT,
    kubernetes_fixture_available,
)

CONNECT_TIMEOUT = 15


def port_accepts(port, host='127.0.0.1'):
    if not port:
        return False
    probe = socket.socket()
    probe.settimeout(5)
    try:
        probe.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


class HostModeTest(BaseTestGenerator):
    """The host dropdown decides who can reach the forward."""

    def setUp(self):
        pass

    def runTest(self):
        # localhost keeps the listener private to this machine.
        self.assertEqual(bind_address_for_host_mode('localhost'), '127.0.0.1')
        self.assertEqual(connect_host_for_host_mode('localhost'), 'localhost')

        # The Docker host name has to be reachable from containers, which a
        # loopback-only listener would not be.
        self.assertEqual(
            bind_address_for_host_mode('host.docker.internal'), '0.0.0.0')
        self.assertEqual(
            connect_host_for_host_mode('host.docker.internal'),
            'host.docker.internal')

        # Anything unexpected falls back to the private option.
        self.assertEqual(bind_address_for_host_mode(None), '127.0.0.1')


@unittest.skipUnless(kubernetes_fixture_available(), SKIP_REASON)
class PortForwardTest(BaseTestGenerator):
    """The forward itself, against a real cluster."""

    def setUp(self):
        self.tunnels = []

    def tearDown(self):
        for tunnel in self.tunnels:
            tunnel.stop()

    def open_tunnel(self, fixture, host_mode='localhost'):
        tunnel = PortForwardTunnel(
            TEST_CONTEXT, fixture.namespace, fixture.kind, fixture.name,
            fixture.port, host_mode)
        self.tunnels.append(tunnel)
        tunnel.start()
        return tunnel

    def check_forwards_every_fixture(self):
        for fixture in FIXTURES:
            with self.subTest(fixture=fixture.label):
                tunnel = self.open_tunnel(fixture)

                self.assertTrue(tunnel.is_alive)
                # The port is whatever was free; it is never the one the
                # user picked and never shown to them.
                self.assertTrue(1024 <= tunnel.local_port <= 65535)
                self.assertNotEqual(tunnel.local_port, fixture.port)
                self.assertTrue(port_accepts(tunnel.local_port))

                with psycopg.connect(
                    host='127.0.0.1', port=tunnel.local_port,
                    user=fixture.expect_username,
                    password=fixture.expect_password,
                    dbname=fixture.expect_database,
                    connect_timeout=CONNECT_TIMEOUT,
                ) as conn:
                    row = conn.execute(
                        'SELECT current_database(), current_user').fetchone()

                self.assertEqual(row[0], fixture.expect_database)
                self.assertEqual(row[1], fixture.expect_username)

    def check_each_tunnel_gets_its_own_port(self):
        ports = set()
        for fixture in FIXTURES:
            ports.add(self.open_tunnel(fixture).local_port)
        self.assertEqual(len(ports), len(FIXTURES))

    def check_carries_concurrent_connections(self):
        """pgAdmin opens a connection per database and per query tool tab,
        so one forward has to carry many at once."""
        fixture = FIXTURES[0]
        tunnel = self.open_tunnel(fixture)

        results = []
        errors = []

        def query():
            try:
                with psycopg.connect(
                    host='127.0.0.1', port=tunnel.local_port,
                    user=fixture.expect_username,
                    password=fixture.expect_password,
                    dbname=fixture.expect_database,
                    connect_timeout=CONNECT_TIMEOUT,
                ) as conn:
                    results.append(conn.execute('SELECT 1').fetchone()[0])
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=query) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        self.assertEqual(errors, [])
        self.assertEqual(results, [1] * 5)

    def check_opens_forwards_concurrently(self):
        """Every forward owns its client, so opening several at once neither
        queues them behind each other nor corrupts a shared one."""
        opened = []
        errors = []

        def open_one(fixture):
            try:
                tunnel = PortForwardTunnel(
                    TEST_CONTEXT, fixture.namespace, fixture.kind,
                    fixture.name, fixture.port, 'localhost')
                self.tunnels.append(tunnel)
                tunnel.start()
                opened.append(tunnel)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=open_one, args=(f,))
                   for f in FIXTURES * 2]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=90)

        self.assertEqual(errors, [])
        self.assertEqual(len(opened), len(FIXTURES) * 2)

        # Every one of them is a working, independent listener.
        ports = {t.local_port for t in opened}
        self.assertEqual(len(ports), len(opened))
        for tunnel in opened:
            self.assertTrue(tunnel.is_alive)
            self.assertTrue(port_accepts(tunnel.local_port))

        # And discovery, which shares only the credentials, is unaffected.
        self.assertIn(FIXTURES[0].namespace, list_namespaces(TEST_CONTEXT))

    def check_discovery_still_works_while_forwarding(self):
        """Opening a forward must not disturb ordinary API calls.

        kubernetes.stream.portforward() rewires ApiClient.request while it
        runs, so a shared client would leave discovery talking websocket.
        """
        fixture = FIXTURES[0]
        self.open_tunnel(fixture)

        self.assertIn(fixture.namespace, list_namespaces(TEST_CONTEXT))
        self.assertEqual(
            resolve_reference(
                TEST_CONTEXT, fixture.namespace, fixture.username_ref),
            fixture.expect_username)

    def check_stop_closes_the_listener(self):
        fixture = FIXTURES[0]
        tunnel = self.open_tunnel(fixture)
        port = tunnel.local_port

        self.assertTrue(port_accepts(port))

        tunnel.stop()

        self.assertFalse(tunnel.is_alive)
        self.assertIsNone(tunnel.local_port)
        self.assertFalse(port_accepts(port))

        # Stopping twice is harmless.
        tunnel.stop()

    def check_restart_takes_a_new_port(self):
        fixture = FIXTURES[0]
        tunnel = self.open_tunnel(fixture)
        first = tunnel.local_port

        tunnel.stop()
        tunnel.start()

        self.assertTrue(tunnel.is_alive)
        self.assertNotEqual(tunnel.local_port, first)
        self.assertTrue(port_accepts(tunnel.local_port))

    def check_reports_a_bad_target_instead_of_hanging(self):
        fixture = FIXTURES[0]

        missing_pod = PortForwardTunnel(
            TEST_CONTEXT, fixture.namespace, 'pod', 'no-such-pod',
            fixture.port, 'localhost')
        self.assertRaises(KubernetesError, missing_pod.start)
        self.assertFalse(missing_pod.is_alive)

        missing_port = PortForwardTunnel(
            TEST_CONTEXT, fixture.namespace, 'service', fixture.name,
            65000, 'localhost')
        self.assertRaises(KubernetesError, missing_port.start)

        # A port nothing is listening on is caught while opening the
        # forward, not left for libpq to trip over.
        dead_port = PortForwardTunnel(
            TEST_CONTEXT, fixture.namespace, 'pod',
            self._pod_name(fixture), 5999, 'localhost')
        self.tunnels.append(dead_port)
        self.assertRaises(KubernetesError, dead_port.start)

    def _pod_name(self, fixture):
        pod_name, _ = resolve_target_pod(
            TEST_CONTEXT, fixture.namespace, fixture.kind, fixture.name,
            fixture.port)
        return pod_name

    def runTest(self):
        self.check_forwards_every_fixture()
        self.check_each_tunnel_gets_its_own_port()
        self.check_carries_concurrent_connections()
        self.check_opens_forwards_concurrently()
        self.check_discovery_still_works_while_forwarding()
        self.check_stop_closes_the_listener()
        self.check_restart_takes_a_new_port()
        self.check_reports_a_bad_target_instead_of_hanging()
