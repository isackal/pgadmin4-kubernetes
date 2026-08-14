##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""
Registering, connecting and removing a server that is reached through a
Kubernetes port forward, driven through the HTTP API the dialog uses.
"""

import json
import socket
import unittest

from pgadmin.utils.route import BaseTestGenerator
from pgadmin.utils.driver import get_driver
from config import PG_DEFAULT_DRIVER
from regression.python_test_utils import test_utils as utils

from pgadmin.utils.kubernetes.tests.utils import (
    FIXTURES,
    SKIP_REASON,
    TEST_CONTEXT,
    kubernetes_fixture_available,
)

SERVER_URL = '/browser/server/obj/'
CONNECT_URL = '/browser/server/connect/'
PROPERTIES_URL = '/browser/server/obj/'


def port_accepts(port):
    if not port:
        return False
    probe = socket.socket()
    probe.settimeout(5)
    try:
        probe.connect(('127.0.0.1', port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


@unittest.skipUnless(kubernetes_fixture_available(), SKIP_REASON)
class KubernetesDiscoveryApiTest(BaseTestGenerator):
    """The endpoints behind the cascading dropdowns."""

    def setUp(self):
        pass

    def runTest(self):
        fixture = FIXTURES[0]

        self.check_dialog_can_reach_the_endpoints()

        response = self.tester.get('/browser/server/kubernetes_contexts')
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            TEST_CONTEXT,
            [ctx['name'] for ctx in json.loads(response.data)])

        response = self.tester.get(
            '/browser/server/kubernetes_namespaces?context={0}'.format(
                TEST_CONTEXT))
        self.assertEqual(response.status_code, 200)
        self.assertIn(fixture.namespace, json.loads(response.data))

        response = self.tester.get(
            '/browser/server/kubernetes_resources?context={0}&namespace={1}'
            '&kind={2}'.format(
                TEST_CONTEXT, fixture.namespace, fixture.kind))
        self.assertEqual(response.status_code, 200)
        resources = {r['name']: r for r in json.loads(response.data)}
        self.assertIn(fixture.name, resources)
        self.assertIn(
            fixture.port, [p['port'] for p in resources[fixture.name]['ports']]
        )

        response = self.tester.get(
            '/browser/server/kubernetes_sources?context={0}&namespace={1}'
            .format(TEST_CONTEXT, fixture.namespace))
        self.assertEqual(response.status_code, 200)
        sources = {s['name']: s for s in json.loads(response.data)}
        self.assertIn(fixture.secret, sources)
        # Nothing without usable key/value pairs is offered.
        self.assertNotIn('kube-root-ca.crt', sources)
        self.assertNotIn('pg-seed', sources)

        # Incomplete requests are refused rather than guessed at.
        response = self.tester.get(
            '/browser/server/kubernetes_resources?context={0}&namespace={1}'
            .format(TEST_CONTEXT, fixture.namespace))
        self.assertEqual(response.status_code, 400)

        response = self.tester.get(
            '/browser/server/kubernetes_namespaces?context=no-such-context')
        self.assertEqual(response.status_code, 400)

    def check_dialog_can_reach_the_endpoints(self):
        """url_for() in the dialog only resolves endpoints the browser
        module publishes, so an unpublished one would leave every dropdown
        requesting `undefined`."""
        response = self.tester.get('/browser/js/endpoints.js')
        self.assertEqual(response.status_code, 200)

        published = response.data.decode()
        for name in ('contexts', 'namespaces', 'resources', 'sources'):
            self.assertIn('NODE-server.kubernetes_{0}'.format(name), published)

        # And the switch that decides whether the tab is usable at all.
        response = self.tester.get('/browser/js/utils.js')
        self.assertEqual(response.status_code, 200)
        self.assertIn('support_kubernetes', response.data.decode())


@unittest.skipUnless(kubernetes_fixture_available(), SKIP_REASON)
class KubernetesServerLifecycleTest(BaseTestGenerator):
    """Register, connect, disconnect and delete, checking that the port
    forward comes and goes with the connection."""

    def setUp(self):
        self.server_ids = []

    def tearDown(self):
        for server_id in self.server_ids:
            self.tester.delete('{0}{1}/{2}'.format(
                SERVER_URL, utils.SERVER_GROUP, server_id))

    def payload(self, fixture, **overrides):
        data = {
            'name': 'k8s-{0}'.format(fixture.label),
            'gid': utils.SERVER_GROUP,
            'kubernetes_conn': True,
            'host': 'localhost',
            'port': fixture.port,
            'k8s_context': TEST_CONTEXT,
            'k8s_namespace': fixture.namespace,
            'k8s_resource_kind': fixture.kind,
            'k8s_resource_name': fixture.name,
            'k8s_username_ref': fixture.username_ref,
            'k8s_password_ref': fixture.password_ref,
            'k8s_database_ref': fixture.database_ref,
            'connection_params': [],
            'connect_now': True,
        }
        data.update(overrides)
        return data

    def register(self, payload):
        return self.tester.post(
            '{0}{1}/'.format(SERVER_URL, utils.SERVER_GROUP),
            data=json.dumps(payload),
            content_type='html/json')

    def manager_for(self, server_id):
        driver = get_driver(PG_DEFAULT_DRIVER)
        for managers in driver.managers.values():
            if str(server_id) in managers:
                return managers[str(server_id)]
        return None

    def runTest(self):
        self.check_registers_and_connects()
        self.check_rejects_incomplete_contracts()
        self.check_forward_follows_the_connection()

    def check_registers_and_connects(self):
        for fixture in FIXTURES:
            with self.subTest(fixture=fixture.label):
                response = self.register(self.payload(fixture))
                self.assertEqual(response.status_code, 200)

                node = json.loads(response.data)['node']
                self.assertTrue(node['connected'])

                server_id = int(node['_id'])
                self.server_ids.append(server_id)

                response = self.tester.get('{0}{1}/{2}'.format(
                    PROPERTIES_URL, utils.SERVER_GROUP, server_id))
                properties = json.loads(response.data)

                # The username and database were read out of the cluster,
                # not typed by anyone.
                self.assertEqual(
                    properties['username'], fixture.expect_username)
                self.assertEqual(
                    properties['db'], fixture.expect_database)

                # The password never reaches the config database.
                self.assertFalse(properties['password'])
                self.assertFalse(properties['save_password'])

                # The contract round-trips for the dialog to reopen.
                self.assertTrue(properties['kubernetes_conn'])
                self.assertEqual(properties['k8s_context'], TEST_CONTEXT)
                self.assertEqual(
                    properties['k8s_namespace'], fixture.namespace)
                self.assertEqual(
                    properties['k8s_resource_kind'], fixture.kind)
                self.assertEqual(
                    properties['k8s_resource_name'], fixture.name)
                self.assertEqual(
                    properties['k8s_password_ref'], fixture.password_ref)

                # The forwarded local port is an implementation detail and
                # stays out of what the user is shown.
                manager = self.manager_for(server_id)
                self.assertIsNotNone(manager)
                self.assertNotIn(
                    'port={0}'.format(manager.local_bind_port),
                    properties['connection_string'])
                self.assertIn(
                    'port={0}'.format(fixture.port),
                    properties['connection_string'])

    def check_rejects_incomplete_contracts(self):
        fixture = FIXTURES[0]

        broken = [
            ({'k8s_namespace': None}, 'namespace'),
            ({'k8s_resource_name': None}, 'service or pod'),
            ({'k8s_username_ref': None}, 'username'),
            ({'k8s_database_ref': None}, 'database'),
            ({'host': 'example.com'}, 'host'),
            ({'k8s_resource_kind': 'deployment'}, 'resource type'),
            ({'k8s_username_ref': 'not-a-reference'}, 'malformed'),
            ({'shared': True}, 'shared'),
        ]

        for overrides, label in broken:
            with self.subTest(rejects=label):
                response = self.register(self.payload(fixture, **overrides))
                self.assertEqual(response.status_code, 400)
                self.assertFalse(json.loads(response.data)['success'])

        # A reference pointing at a key that is not there is caught before
        # anything is written.
        response = self.register(self.payload(
            fixture, k8s_password_ref=fixture.reference('no-such-key')))
        self.assertEqual(response.status_code, 400)

    def check_forward_follows_the_connection(self):
        fixture = FIXTURES[0]
        response = self.register(self.payload(
            fixture, name='k8s-lifecycle'))
        self.assertEqual(response.status_code, 200)

        server_id = int(json.loads(response.data)['node']['_id'])
        self.server_ids.append(server_id)

        manager = self.manager_for(server_id)
        first_port = manager.local_bind_port
        self.assertTrue(manager.kubernetes_tunnel_alive())
        self.assertTrue(port_accepts(first_port))

        # Disconnecting takes the forward with it.
        response = self.tester.delete('{0}{1}/{2}'.format(
            CONNECT_URL, utils.SERVER_GROUP, server_id))
        self.assertEqual(response.status_code, 200)

        self.assertFalse(manager.kubernetes_tunnel_alive())
        self.assertIsNone(manager.local_bind_port)
        self.assertFalse(port_accepts(first_port))

        # Reconnecting opens a fresh one, on a different free port. No
        # password is asked for along the way.
        response = self.tester.post(
            '{0}{1}/{2}'.format(CONNECT_URL, utils.SERVER_GROUP, server_id),
            data=json.dumps({}), content_type='html/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.data)['success'], 1)

        manager = self.manager_for(server_id)
        second_port = manager.local_bind_port
        self.assertTrue(manager.kubernetes_tunnel_alive())
        self.assertNotEqual(second_port, first_port)
        self.assertTrue(port_accepts(second_port))

        # Removing the server closes the forward as well.
        response = self.tester.delete('{0}{1}/{2}'.format(
            SERVER_URL, utils.SERVER_GROUP, server_id))
        self.assertEqual(response.status_code, 200)
        self.server_ids.remove(server_id)

        self.assertFalse(port_accepts(second_port))
