##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""
Kubernetes support for server connections.

A Kubernetes server connection does not store a host, port or credentials.
Instead it stores a *contract*: which context, namespace and workload to
reach, and which Secret/ConfigMap keys hold the username, password and
database name.  Everything else is resolved when the server is connected:

* a port forward is opened on an ephemeral local port (see ``portforward``),
* the credential references are read straight from the cluster
  (see ``client.resolve_reference``).

The port forward lives exactly as long as the connection does; releasing the
server manager tears it down.
"""

from .client import (
    KUBERNETES_AVAILABLE,
    KubernetesError,
    HOST_MODES,
    HOST_MODE_LOCALHOST,
    HOST_MODE_DOCKER,
    RESOURCE_KIND_SERVICE,
    RESOURCE_KIND_POD,
    RESOURCE_KINDS,
    bind_address_for_host_mode,
    connect_host_for_host_mode,
    format_reference,
    is_kubernetes_supported,
    list_contexts,
    list_data_sources,
    list_namespaces,
    list_resources,
    parse_reference,
    resolve_reference,
    resolve_target_pod,
)
from .portforward import PortForwardTunnel

__all__ = [
    'KUBERNETES_AVAILABLE',
    'KubernetesError',
    'HOST_MODES',
    'HOST_MODE_LOCALHOST',
    'HOST_MODE_DOCKER',
    'RESOURCE_KIND_SERVICE',
    'RESOURCE_KIND_POD',
    'RESOURCE_KINDS',
    'PortForwardTunnel',
    'bind_address_for_host_mode',
    'connect_host_for_host_mode',
    'format_reference',
    'is_kubernetes_supported',
    'list_contexts',
    'list_data_sources',
    'list_namespaces',
    'list_resources',
    'parse_reference',
    'resolve_reference',
    'resolve_target_pod',
]
