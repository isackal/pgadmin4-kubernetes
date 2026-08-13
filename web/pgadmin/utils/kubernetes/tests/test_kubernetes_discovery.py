##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

import unittest

from pgadmin.utils.route import BaseTestGenerator
from pgadmin.utils.kubernetes import (
    KubernetesError,
    format_reference,
    list_contexts,
    list_data_sources,
    list_namespaces,
    list_resources,
    parse_reference,
    resolve_reference,
    resolve_target_pod,
)
from pgadmin.utils.kubernetes.client import _usable_value

from .utils import (
    FIXTURES,
    SKIP_REASON,
    TEST_CONTEXT,
    kubernetes_fixture_available,
)


class KubernetesReferenceTest(BaseTestGenerator):
    """References are parsed without touching a cluster."""

    def setUp(self):
        pass

    def runTest(self):
        self.assertEqual(
            format_reference('secret', 'creds', 'password'),
            'secret/creds/password')
        self.assertEqual(
            parse_reference('secret/creds/password'),
            ('secret', 'creds', 'password'))
        self.assertEqual(
            parse_reference('configmap/settings/db.name'),
            ('configmap', 'settings', 'db.name'))

        for bad in ('', None, 'secret/creds', 'secret//password',
                    'secret/creds/password/extra', 'unknown/creds/password'):
            with self.subTest(reference=bad):
                self.assertRaises(
                    KubernetesError, parse_reference, bad)


class KubernetesUsableValueTest(BaseTestGenerator):
    """Only short, single-line, printable values are offered as credentials.

    This is what keeps certificates, seeded .sql files and other blobs that
    merely share a namespace out of the dropdowns.
    """

    def setUp(self):
        pass

    def runTest(self):
        usable = ('postgres', 'p@ssw0rd!', 'db-1', 'a' * 512)
        for value in usable:
            with self.subTest(value=value[:20]):
                self.assertEqual(_usable_value(value), value)
                self.assertEqual(_usable_value(value.encode()), value)

        unusable = (
            None,
            '',
            'a' * 513,
            '-----BEGIN CERTIFICATE-----\nMIIDBTCC\n',
            'CREATE TABLE t (id int);\n',
            'tab\tseparated',
            'null\x00byte',
        )
        for value in unusable:
            with self.subTest(value=str(value)[:20]):
                self.assertIsNone(_usable_value(value))

        # Undecodable bytes are a binary blob, not a credential.
        self.assertIsNone(_usable_value(b'\xff\xfe\x00binary'))


@unittest.skipUnless(kubernetes_fixture_available(), SKIP_REASON)
class KubernetesDiscoveryTest(BaseTestGenerator):
    """Discovery against a real cluster."""

    def setUp(self):
        pass

    def runTest(self):
        self.check_contexts()
        self.check_namespaces()
        self.check_resources()
        self.check_data_sources()
        self.check_reference_resolution()
        self.check_target_resolution()

    def check_contexts(self):
        contexts = list_contexts()
        names = [ctx['name'] for ctx in contexts]
        self.assertIn(TEST_CONTEXT, names)
        # Exactly one context can be the active one.
        self.assertLessEqual(
            len([c for c in contexts if c['is_current']]), 1)

    def check_namespaces(self):
        namespaces = list_namespaces(TEST_CONTEXT)
        for fixture in FIXTURES:
            self.assertIn(fixture.namespace, namespaces)
        self.assertEqual(namespaces, sorted(namespaces))

    def check_resources(self):
        for fixture in FIXTURES:
            with self.subTest(fixture=fixture.label):
                resources = list_resources(
                    TEST_CONTEXT, fixture.namespace, fixture.kind)
                by_name = {r['name']: r for r in resources}
                self.assertIn(fixture.name, by_name)

                resource = by_name[fixture.name]
                self.assertTrue(resource['ready'])
                self.assertIn(
                    fixture.port, [p['port'] for p in resource['ports']])

        # A namespace with no service exposes none, which is exactly why
        # the pod has to be selectable directly.
        weird = next(f for f in FIXTURES if f.kind == 'pod')
        self.assertEqual(
            list_resources(TEST_CONTEXT, weird.namespace, 'service'), [])

        self.assertRaises(
            KubernetesError, list_resources,
            TEST_CONTEXT, FIXTURES[0].namespace, 'deployment')

    def check_data_sources(self):
        for fixture in FIXTURES:
            with self.subTest(fixture=fixture.label):
                sources = list_data_sources(TEST_CONTEXT, fixture.namespace)
                by_name = {s['name']: s for s in sources}

                self.assertIn(fixture.secret, by_name)
                self.assertEqual(by_name[fixture.secret]['kind'], 'secret')
                for key in (fixture.username_key, fixture.password_key,
                            fixture.database_key):
                    self.assertIn(key, by_name[fixture.secret]['keys'])

                # The service account CA bundle and the seeded schema are
                # both multi-line blobs, so neither is offered.
                self.assertNotIn('kube-root-ca.crt', by_name)
                self.assertNotIn('pg-seed', by_name)

                for source in sources:
                    self.assertTrue(source['keys'])

    def check_reference_resolution(self):
        for fixture in FIXTURES:
            with self.subTest(fixture=fixture.label):
                self.assertEqual(
                    resolve_reference(
                        TEST_CONTEXT, fixture.namespace, fixture.username_ref),
                    fixture.expect_username)
                self.assertEqual(
                    resolve_reference(
                        TEST_CONTEXT, fixture.namespace, fixture.password_ref),
                    fixture.expect_password)
                self.assertEqual(
                    resolve_reference(
                        TEST_CONTEXT, fixture.namespace, fixture.database_ref),
                    fixture.expect_database)

        fixture = FIXTURES[0]
        self.assertRaises(
            KubernetesError, resolve_reference, TEST_CONTEXT,
            fixture.namespace, fixture.reference('no-such-key'))
        self.assertRaises(
            KubernetesError, resolve_reference, TEST_CONTEXT,
            fixture.namespace, 'secret/no-such-secret/username')

    def check_target_resolution(self):
        for fixture in FIXTURES:
            with self.subTest(fixture=fixture.label):
                pod_name, pod_port = resolve_target_pod(
                    TEST_CONTEXT, fixture.namespace, fixture.kind,
                    fixture.name, fixture.port)

                self.assertTrue(pod_name)
                # Whatever the service exposes, forwarding always lands on
                # the port the container is actually listening on.
                self.assertEqual(pod_port, 5432)

                if fixture.kind == 'pod':
                    self.assertEqual(pod_name, fixture.name)
                else:
                    self.assertTrue(pod_name.startswith(fixture.name))

        service = next(f for f in FIXTURES if f.kind == 'service')
        self.assertRaises(
            KubernetesError, resolve_target_pod, TEST_CONTEXT,
            service.namespace, 'service', service.name, 65000)
        self.assertRaises(
            KubernetesError, resolve_target_pod, TEST_CONTEXT,
            service.namespace, 'pod', 'no-such-pod', 5432)
