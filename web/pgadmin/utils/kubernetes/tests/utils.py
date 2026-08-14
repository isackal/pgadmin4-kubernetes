##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""
Shared fixtures for the Kubernetes tests.

These tests talk to a real cluster, because the parts worth testing - the
port forward, the Service-to-pod resolution, the filtering of Secrets that
hold no usable key/value pairs - are exactly the parts a mock would have to
invent.  When no cluster with the expected fixtures is reachable the tests
skip rather than fail.

The fixtures are three PostgreSQL deployments that between them cover the
cases that behave differently:

* pg-standard  a Service whose port matches the container port, with
               conventionally named Secret keys, plus a second Secret that
               holds no credentials at all
* pg-bitnami   a Service on 5433 forwarding to container port 5432, with
               Secret keys named the way the Bitnami images expect
* pg-weird     a bare pod with no Service in front of it, and Secret keys
               that follow no convention

Point PGADMIN_KUBERNETES_TEST_CONTEXT at a different context to run them
against another cluster carrying the same fixtures.
"""

import os

from pgadmin.utils.kubernetes import KubernetesError, list_namespaces

TEST_CONTEXT = os.environ.get(
    'PGADMIN_KUBERNETES_TEST_CONTEXT', 'kind-dbviewer')


class Fixture:
    def __init__(self, label, namespace, kind, name, port, secret,
                 username_key, password_key, database_key,
                 expect_username, expect_password, expect_database):
        self.label = label
        self.namespace = namespace
        self.kind = kind
        self.name = name
        self.port = port
        self.secret = secret
        self.username_key = username_key
        self.password_key = password_key
        self.database_key = database_key
        self.expect_username = expect_username
        self.expect_password = expect_password
        self.expect_database = expect_database

    def reference(self, key):
        return 'secret/{0}/{1}'.format(self.secret, key)

    @property
    def username_ref(self):
        return self.reference(self.username_key)

    @property
    def password_ref(self):
        return self.reference(self.password_key)

    @property
    def database_ref(self):
        return self.reference(self.database_key)


FIXTURES = [
    Fixture('standard', 'pg-standard', 'service', 'postgres', 5432,
            'pg-standard-credentials',
            'username', 'password', 'database',
            'standard_user', 'standard-pw', 'standarddb'),
    # The service port and the container port differ here, so forwarding it
    # only works if the service port is translated to its target.
    Fixture('bitnami', 'pg-bitnami', 'service', 'postgres', 5433,
            'pg-bitnami-credentials',
            'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB',
            'bitnami_user', 'bitnami-pw', 'bitnamidb'),
    # No service at all, so this can only be reached by naming the pod.
    Fixture('weird', 'pg-weird', 'pod', 'postgres', 5432,
            'pg-weird-credentials',
            'principal', 'token', 'catalog',
            'weird_user', 'weird-pw', 'weirddb'),
]

FIXTURE_NAMESPACES = [f.namespace for f in FIXTURES]

_availability = None


def kubernetes_fixture_available():
    """True when the fixture cluster is reachable, cached per process."""
    global _availability

    if _availability is None:
        try:
            namespaces = list_namespaces(TEST_CONTEXT)
            _availability = all(
                ns in namespaces for ns in FIXTURE_NAMESPACES)
        except (KubernetesError, Exception):
            _availability = False

    return _availability


SKIP_REASON = (
    'No Kubernetes cluster with the pgAdmin test fixtures is reachable '
    'through context "{0}".'.format(TEST_CONTEXT)
)
