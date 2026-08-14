##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""
Discovery helpers for Kubernetes server connections.

Everything the Kubernetes tab of the server dialog offers in a dropdown is
produced here, and so is the resolution of the stored references back into
real values at connection time.
"""

import base64
import threading

import config
from flask_babel import gettext

try:
    from kubernetes import client as k8s_client, config as k8s_config
    from kubernetes.client.rest import ApiException
    from kubernetes.config.config_exception import ConfigException

    KUBERNETES_AVAILABLE = True
except ImportError:
    KUBERNETES_AVAILABLE = False
    ApiException = Exception
    ConfigException = Exception

# The two ends of the port forward the user can pick between.  Both address
# the very same listener; they differ in who is able to reach it.
HOST_MODE_LOCALHOST = 'localhost'
HOST_MODE_DOCKER = 'host.docker.internal'

HOST_MODES = (HOST_MODE_LOCALHOST, HOST_MODE_DOCKER)

RESOURCE_KIND_SERVICE = 'service'
RESOURCE_KIND_POD = 'pod'

RESOURCE_KINDS = (RESOURCE_KIND_SERVICE, RESOURCE_KIND_POD)

SOURCE_KIND_SECRET = 'secret'
SOURCE_KIND_CONFIGMAP = 'configmap'

REFERENCE_SEPARATOR = '/'

# Secret types whose payload is a structured blob (certificates, docker
# credentials, tokens) rather than the free-form key/value pairs we can use
# for a username, password or database name.
STRUCTURED_SECRET_TYPES = frozenset((
    'kubernetes.io/tls',
    'kubernetes.io/dockercfg',
    'kubernetes.io/dockerconfigjson',
    'kubernetes.io/service-account-token',
    'kubernetes.io/ssh-auth',
    'bootstrap.kubernetes.io/token',
))

# A credential is a short single-line string.  Anything longer or containing
# control characters is a certificate, a script or a config file that was
# merely stored in the same place, so it never shows up in the dropdown.
MAX_REFERENCE_VALUE_LENGTH = 512

_client_lock = threading.Lock()
_configuration_cache = {}
_client_cache = {}


class KubernetesError(Exception):
    """Raised when the cluster cannot be reached or does not hold what the
    connection contract claims it holds."""


def is_kubernetes_supported():
    """Kubernetes connections need the client library, the feature switch,
    and - in server mode - a deployment that opted into sharing the
    pgAdmin process's cluster identity with every logged in user."""
    if not KUBERNETES_AVAILABLE:
        return False
    if not getattr(config, 'SUPPORT_KUBERNETES', True):
        return False
    if getattr(config, 'SERVER_MODE', False) and not getattr(
            config, 'ALLOW_KUBERNETES_IN_SERVER_MODE', False):
        return False
    return True


def _require_support():
    if not KUBERNETES_AVAILABLE:
        raise KubernetesError(gettext(
            'The kubernetes Python package is not installed, so Kubernetes '
            'connections are unavailable.'))
    if not getattr(config, 'SUPPORT_KUBERNETES', True):
        raise KubernetesError(gettext(
            'Kubernetes connections are disabled by the server '
            'configuration.'))
    if getattr(config, 'SERVER_MODE', False) and not getattr(
            config, 'ALLOW_KUBERNETES_IN_SERVER_MODE', False):
        raise KubernetesError(gettext(
            'Kubernetes connections are disabled in server mode because '
            'every user would share the same cluster credentials. Set '
            'ALLOW_KUBERNETES_IN_SERVER_MODE to enable them.'))


def _load_configuration(context=None):
    """Resolve a context's credentials, falling back to the in-cluster
    service account when pgAdmin itself runs inside Kubernetes."""
    configuration = k8s_client.Configuration()
    try:
        k8s_config.load_kube_config(
            context=context, client_configuration=configuration)
    except (ConfigException, FileNotFoundError):
        # No usable kubeconfig.  If we are running inside a pod the mounted
        # service account is the right credential to use, but only when the
        # caller did not ask for a specific context.
        if context:
            raise
        k8s_config.load_incluster_config(client_configuration=configuration)

    return configuration


def get_configuration(context=None):
    """The cached, authenticated Configuration for a context.

    This is the expensive half of building a client: it reads kubeconfig
    and, for a cluster behind an exec credential plugin, shells out to that
    plugin.  It is also the half that is safe to share - a Configuration is
    only ever read, and it refreshes its own token on expiry - so it is
    cached and every client is built over it.
    """
    _require_support()

    key = context or ''
    with _client_lock:
        configuration = _configuration_cache.get(key)
        if configuration is None:
            try:
                configuration = _load_configuration(context)
            except (ConfigException, FileNotFoundError) as e:
                raise KubernetesError(gettext(
                    'Could not load the Kubernetes configuration: {0}'
                ).format(str(e)))
            _configuration_cache[key] = configuration
        return configuration


def new_api_client(context=None):
    """A brand new ApiClient over the shared Configuration.

    Cheap, because the credentials behind it were resolved once already.
    Port forwarding needs one of these per forward; see
    portforward.open_port_forward for why.
    """
    return k8s_client.ApiClient(get_configuration(context))


def get_core_api(context=None):
    """Return a cached CoreV1Api for the ordinary read-only API calls.

    Sharing one client across discovery calls is what gives them a shared
    connection pool.  Port forwarding must not use it - see
    portforward.open_port_forward.
    """
    key = context or ''
    with _client_lock:
        api = _client_cache.get(key)
        if api is not None:
            return api

    api = k8s_client.CoreV1Api(new_api_client(context))
    with _client_lock:
        return _client_cache.setdefault(key, api)


def clear_client_cache():
    """Drop the cached credentials and clients so the next call re-reads
    kubeconfig."""
    with _client_lock:
        _configuration_cache.clear()
        _client_cache.clear()


def bind_address_for_host_mode(host_mode):
    """The address the port forward listener binds to.

    ``localhost`` keeps the forward private to this machine.  The Docker
    host mode has to bind every interface, otherwise a container talking to
    ``host.docker.internal`` cannot reach it.
    """
    return '0.0.0.0' if host_mode == HOST_MODE_DOCKER else '127.0.0.1'


def connect_host_for_host_mode(host_mode):
    """The host name libpq should connect to for the given mode."""
    return HOST_MODE_DOCKER if host_mode == HOST_MODE_DOCKER \
        else HOST_MODE_LOCALHOST


def _api_error(e, what):
    if isinstance(e, ApiException):
        detail = getattr(e, 'reason', None) or str(e)
        if e.status == 403:
            return KubernetesError(gettext(
                'Not authorised to list {0} in the cluster ({1}).'
            ).format(what, detail))
        if e.status == 404:
            return KubernetesError(gettext(
                'Could not find {0}.').format(what))
        return KubernetesError(gettext(
            'Kubernetes API error while reading {0}: {1}'
        ).format(what, detail))
    return KubernetesError(gettext(
        'Could not reach the Kubernetes cluster while reading {0}: {1}'
    ).format(what, str(e)))


def list_contexts():
    """All contexts in the user's kubeconfig, flagging the active one."""
    _require_support()

    try:
        contexts, active = k8s_config.list_kube_config_contexts()
    except (ConfigException, FileNotFoundError):
        # Running in-cluster: there is exactly one identity available and it
        # is not named by any kubeconfig.
        try:
            k8s_config.load_incluster_config(
                client_configuration=k8s_client.Configuration())
        except Exception:
            raise KubernetesError(gettext(
                'No Kubernetes configuration was found. Set up a kubeconfig '
                'file or run pgAdmin inside a cluster.'))
        return []

    active_name = (active or {}).get('name')
    return [{
        'name': ctx['name'],
        'cluster': ctx.get('context', {}).get('cluster'),
        'namespace': ctx.get('context', {}).get('namespace'),
        'is_current': ctx['name'] == active_name,
    } for ctx in (contexts or [])]


def list_namespaces(context=None):
    """Namespace names visible to the context's identity.

    Identities that may not list namespaces cluster-wide still deserve a
    usable dialog, so the context's own default namespace is offered as a
    fallback rather than failing outright.
    """
    api = get_core_api(context)
    try:
        return sorted(
            ns.metadata.name for ns in api.list_namespace().items
        )
    except Exception as e:
        if isinstance(e, ApiException) and e.status == 403:
            fallback = _context_namespace(context)
            if fallback:
                return [fallback]
        raise _api_error(e, gettext('namespaces'))


def _context_namespace(context):
    try:
        contexts, active = k8s_config.list_kube_config_contexts()
    except Exception:
        return None
    for ctx in contexts or []:
        if ctx['name'] == (context or (active or {}).get('name')):
            return ctx.get('context', {}).get('namespace')
    return None


def _service_ports(service):
    ports = []
    for port in service.spec.ports or []:
        if (port.protocol or 'TCP').upper() != 'TCP':
            continue
        ports.append({
            'port': port.port,
            'name': port.name,
            'target_port': port.target_port,
        })
    return ports


def _pod_ports(pod):
    ports = []
    for container in pod.spec.containers or []:
        for port in container.ports or []:
            if (port.protocol or 'TCP').upper() != 'TCP':
                continue
            ports.append({
                'port': port.container_port,
                'name': port.name,
                'target_port': port.container_port,
            })
    return ports


def _pod_is_ready(pod):
    if (pod.status.phase or '') != 'Running':
        return False
    for condition in pod.status.conditions or []:
        if condition.type == 'Ready':
            return condition.status == 'True'
    return False


def list_resources(context, namespace, kind):
    """Services or pods in a namespace, each with the TCP ports it exposes.

    A pod that declares no ports is still listed: ``kubectl port-forward``
    happily forwards to an undeclared port and so do we, the user just has
    to say which one.
    """
    if kind not in RESOURCE_KINDS:
        raise KubernetesError(gettext(
            'Unknown Kubernetes resource kind "{0}".').format(kind))

    api = get_core_api(context)

    try:
        if kind == RESOURCE_KIND_SERVICE:
            return [{
                'name': svc.metadata.name,
                'ports': _service_ports(svc),
                'ready': True,
            } for svc in api.list_namespaced_service(namespace).items]

        return [{
            'name': pod.metadata.name,
            'ports': _pod_ports(pod),
            'ready': _pod_is_ready(pod),
        } for pod in api.list_namespaced_pod(namespace).items]
    except Exception as e:
        raise _api_error(e, gettext('{0}s in namespace "{1}"').format(
            kind, namespace))


def _usable_value(raw):
    """Return the decoded value if it looks like a credential, else None."""
    if raw is None:
        return None
    if isinstance(raw, bytes):
        try:
            raw = raw.decode('utf-8')
        except UnicodeDecodeError:
            return None
    if not raw or len(raw) > MAX_REFERENCE_VALUE_LENGTH:
        return None
    # isprintable() rejects newlines, tabs and other control characters,
    # which is exactly what separates a password from a PEM block or a
    # seeded .sql file.
    if not raw.isprintable():
        return None
    return raw


def _secret_values(secret):
    """Decode a Secret's data, dropping anything that is not a credential."""
    if secret.type in STRUCTURED_SECRET_TYPES:
        return {}

    values = {}
    for key, encoded in (secret.data or {}).items():
        try:
            decoded = base64.b64decode(encoded)
        except Exception:
            continue
        value = _usable_value(decoded)
        if value is not None:
            values[key] = value
    return values


def _configmap_values(configmap):
    values = {}
    for key, raw in (configmap.data or {}).items():
        value = _usable_value(raw)
        if value is not None:
            values[key] = value
    return values


def list_data_sources(context, namespace):
    """Secrets and ConfigMaps that actually hold usable key/value pairs.

    Both kinds behave identically for our purposes, so they are returned in
    one list and the UI renders them as ``<kind>/<name>/<key>``.
    """
    api = get_core_api(context)

    sources = []

    try:
        secrets = api.list_namespaced_secret(namespace).items
    except Exception as e:
        raise _api_error(e, gettext(
            'secrets in namespace "{0}"').format(namespace))

    for secret in secrets:
        keys = sorted(_secret_values(secret))
        if keys:
            sources.append({
                'kind': SOURCE_KIND_SECRET,
                'name': secret.metadata.name,
                'keys': keys,
            })

    try:
        configmaps = api.list_namespaced_config_map(namespace).items
    except Exception as e:
        raise _api_error(e, gettext(
            'config maps in namespace "{0}"').format(namespace))

    for configmap in configmaps:
        keys = sorted(_configmap_values(configmap))
        if keys:
            sources.append({
                'kind': SOURCE_KIND_CONFIGMAP,
                'name': configmap.metadata.name,
                'keys': keys,
            })

    return sorted(sources, key=lambda s: (s['kind'], s['name']))


def format_reference(kind, name, key):
    """Build the ``<kind>/<name>/<key>`` string stored on the server."""
    return REFERENCE_SEPARATOR.join((kind, name, key))


def parse_reference(reference):
    """Split a stored reference back into (kind, name, key).

    Kubernetes forbids ``/`` in both object names and data keys, so a plain
    split is unambiguous.
    """
    if not reference:
        raise KubernetesError(gettext('No Kubernetes reference was given.'))

    parts = reference.split(REFERENCE_SEPARATOR)
    if len(parts) != 3 or not all(parts):
        raise KubernetesError(gettext(
            'Malformed Kubernetes reference "{0}". Expected '
            '<secret|configmap>/<name>/<key>.').format(reference))

    kind, name, key = parts
    if kind not in (SOURCE_KIND_SECRET, SOURCE_KIND_CONFIGMAP):
        raise KubernetesError(gettext(
            'Unknown Kubernetes reference kind "{0}".').format(kind))

    return kind, name, key


def resolve_reference(context, namespace, reference):
    """Read the value a reference points at, straight from the cluster."""
    kind, name, key = parse_reference(reference)
    api = get_core_api(context)

    try:
        if kind == SOURCE_KIND_SECRET:
            values = _secret_values(
                api.read_namespaced_secret(name, namespace))
        else:
            values = _configmap_values(
                api.read_namespaced_config_map(name, namespace))
    except Exception as e:
        raise _api_error(e, gettext('{0} "{1}" in namespace "{2}"').format(
            kind, name, namespace))

    if key not in values:
        raise KubernetesError(gettext(
            'The key "{0}" is no longer available in {1} "{2}".'
        ).format(key, kind, name))

    return values[key]


def _resolve_named_port(pod, port_name):
    for container in pod.spec.containers or []:
        for port in container.ports or []:
            if port.name == port_name:
                return port.container_port
    return None


def resolve_target_pod(context, namespace, kind, name, port):
    """Map the chosen workload onto a concrete (pod name, pod port).

    The Kubernetes API can only forward to a pod, so a Service has to be
    followed through its selector the same way kubectl does: pick a ready
    backing pod and translate the service port to its target port.
    """
    api = get_core_api(context)

    if kind == RESOURCE_KIND_POD:
        try:
            pod = api.read_namespaced_pod(name, namespace)
        except Exception as e:
            raise _api_error(e, gettext(
                'pod "{0}" in namespace "{1}"').format(name, namespace))
        if not _pod_is_ready(pod):
            raise KubernetesError(gettext(
                'Pod "{0}" is not ready, so it cannot be forwarded to.'
            ).format(name))
        return pod.metadata.name, int(port)

    try:
        service = api.read_namespaced_service(name, namespace)
    except Exception as e:
        raise _api_error(e, gettext(
            'service "{0}" in namespace "{1}"').format(name, namespace))

    selector = (service.spec.selector or {})
    if not selector:
        raise KubernetesError(gettext(
            'Service "{0}" has no selector, so pgAdmin cannot work out '
            'which pod to forward to. Select the pod directly instead.'
        ).format(name))

    service_port = None
    for candidate in service.spec.ports or []:
        if candidate.port == int(port):
            service_port = candidate
            break

    if service_port is None:
        raise KubernetesError(gettext(
            'Service "{0}" no longer exposes port {1}.').format(name, port))

    label_selector = ','.join(
        '{0}={1}'.format(k, v) for k, v in sorted(selector.items()))

    try:
        pods = api.list_namespaced_pod(
            namespace, label_selector=label_selector).items
    except Exception as e:
        raise _api_error(e, gettext(
            'pods backing service "{0}"').format(name))

    ready_pods = [pod for pod in pods if _pod_is_ready(pod)]
    if not ready_pods:
        raise KubernetesError(gettext(
            'No ready pod backs service "{0}" in namespace "{1}".'
        ).format(name, namespace))

    pod = ready_pods[0]

    target = service_port.target_port
    if target is None:
        target_port = service_port.port
    elif isinstance(target, int):
        target_port = target
    else:
        try:
            target_port = int(target)
        except (TypeError, ValueError):
            target_port = _resolve_named_port(pod, target)
            if target_port is None:
                raise KubernetesError(gettext(
                    'Service "{0}" targets the named port "{1}", which pod '
                    '"{2}" does not declare.'
                ).format(name, target, pod.metadata.name))

    return pod.metadata.name, int(target_port)
