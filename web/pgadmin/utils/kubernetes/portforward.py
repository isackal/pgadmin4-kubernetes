##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""
A pure-Python equivalent of ``kubectl port-forward``.

pgAdmin listens on an ephemeral local port and, for every client connection
it accepts, opens its own port-forward stream to the target pod through the
Kubernetes API server.  That is the same one-stream-per-connection model
kubectl uses, and it matters here because pgAdmin opens a separate libpq
connection per database, query tool tab and background task.

The listener stays up for as long as the server is connected in pgAdmin.
Releasing the server manager - by disconnecting, by deleting the server, or
by the session being garbage collected - stops it.
"""

import errno
import select
import socket
import threading

from flask_babel import gettext

from .client import (
    KUBERNETES_AVAILABLE,
    KubernetesError,
    bind_address_for_host_mode,
    new_api_client,
    resolve_target_pod,
)

if KUBERNETES_AVAILABLE:
    from kubernetes import client as k8s_client
    from kubernetes.stream import portforward

# Bytes moved per read.  Large enough that bulk result sets do not thrash
# the select loop, small enough to stay off the large-object heap.
BUFFER_SIZE = 65536

# How long to wait for the API server to complain that the target port is
# not actually listening.  Only paid once, when the tunnel is opened.
PROBE_TIMEOUT = 1.0


def open_port_forward(context, namespace, pod, port):
    """Open a single port-forward stream to a pod.

    Each forward gets an ApiClient of its own, the way each
    ``kubectl port-forward`` is its own process.  That is not tidiness: the
    library's portforward() swaps ApiClient.request out for a websocket
    transport, runs the API method, and puts the original back afterwards.
    Anything else sharing that client is liable to be sent down the
    websocket path and fail with "Missing required parameter `ports`", and
    two forwards racing each other can restore the patched method and leave
    the client rewired for good.

    Owning the client makes both impossible rather than merely guarded
    against, and lets concurrent connections open in parallel.  The client
    is cheap because the credentials behind it are resolved once and shared,
    and it is closed as soon as the handshake is done - the websocket that
    carries the connection does not belong to it.
    """
    api_client = new_api_client(context)
    try:
        return portforward(
            k8s_client.CoreV1Api(
                api_client).connect_get_namespaced_pod_portforward,
            pod,
            namespace,
            ports=str(port),
        )
    finally:
        try:
            api_client.close()
        except Exception:
            pass


class PortForwardTunnel:
    """A local TCP listener that forwards to a port on a Kubernetes pod."""

    def __init__(self, context, namespace, kind, name, port,
                 host_mode=None, logger=None):
        self.context = context
        self.namespace = namespace
        self.kind = kind
        self.name = name
        self.port = int(port)
        self.bind_host = bind_address_for_host_mode(host_mode)
        self.logger = logger

        # Filled in by start().
        self.pod_name = None
        self.pod_port = None
        self.local_port = None

        self._listener = None
        self._accept_thread = None
        self._connections = set()
        self._lock = threading.Lock()
        self._closing = False

    # -- lifecycle --------------------------------------------------------

    @property
    def is_alive(self):
        return bool(self._listener) and not self._closing and \
            bool(self._accept_thread) and self._accept_thread.is_alive()

    def start(self):
        """Resolve the target, verify it is reachable and open the listener.

        Raises KubernetesError with a message worth showing to the user if
        any of that fails.
        """
        if not KUBERNETES_AVAILABLE:
            raise KubernetesError(gettext(
                'The kubernetes Python package is not installed, so '
                'Kubernetes connections are unavailable.'))

        if self.is_alive:
            return self.local_port

        self.pod_name, self.pod_port = resolve_target_pod(
            self.context, self.namespace, self.kind, self.name, self.port)

        self._probe()

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            # Port 0 asks the OS for any free port; the user never sees or
            # picks it.
            listener.bind((self.bind_host, 0))
            listener.listen(16)
        except OSError as e:
            listener.close()
            raise KubernetesError(gettext(
                'Could not open a local port to forward {0}/{1} to: {2}'
            ).format(self.kind, self.name, str(e)))

        self.local_port = listener.getsockname()[1]
        self._listener = listener
        self._closing = False

        self._accept_thread = threading.Thread(
            target=self._accept_loop,
            name='pgadmin k8s port forward {0}:{1}'.format(
                self.pod_name, self.pod_port),
            daemon=True,
        )
        self._accept_thread.start()

        self._log('Forwarding {0}:{1} -> {2}/{3}:{4} in {5}'.format(
            self.bind_host, self.local_port, self.kind, self.name,
            self.port, self.namespace))

        return self.local_port

    def stop(self):
        """Close the listener and every stream running through it."""
        self._closing = True

        listener, self._listener = self._listener, None
        if listener is not None:
            try:
                listener.close()
            except OSError:
                pass

        with self._lock:
            connections = list(self._connections)
            self._connections.clear()

        for sock in connections:
            _close(sock)

        thread, self._accept_thread = self._accept_thread, None
        if thread is not None and thread.is_alive() and \
                thread is not threading.current_thread():
            thread.join(timeout=2)

        self.local_port = None

    # -- plumbing ---------------------------------------------------------

    def _log(self, message):
        if self.logger is not None:
            self.logger.info(message)

    def _open_stream(self):
        """Open one port-forward stream to the resolved pod."""
        return open_port_forward(
            self.context, self.namespace, self.pod_name, self.pod_port)

    def _probe(self):
        """Open a throwaway stream so failures surface at connect time.

        Without this, an unreachable port would only show up as libpq
        reporting that the server closed the connection unexpectedly, which
        tells the user nothing about what is actually wrong.
        """
        forward = None
        try:
            forward = self._open_stream()
        except Exception as e:
            raise KubernetesError(gettext(
                'Could not start a port forward to pod "{0}" in namespace '
                '"{1}": {2}'
            ).format(self.pod_name, self.namespace, str(e)))

        try:
            if not forward.connected:
                raise KubernetesError(gettext(
                    'The Kubernetes API server refused to forward to pod '
                    '"{0}".').format(self.pod_name))

            sock = forward.socket(self.pod_port)
            # If nothing is listening on the pod side, the API server closes
            # the data channel and writes to the error channel.  Silence
            # here means the port answered.
            readable, _, _ = select.select([sock], [], [], PROBE_TIMEOUT)
            if readable and sock.recv(BUFFER_SIZE) == b'':
                error = forward.error(self.pod_port)
                raise KubernetesError(gettext(
                    'Nothing is listening on port {0} of pod "{1}"{2}.'
                ).format(
                    self.pod_port, self.pod_name,
                    ': {0}'.format(error) if error else ''))
        finally:
            try:
                forward.close()
            except Exception:
                pass

    def _accept_loop(self):
        listener = self._listener
        while not self._closing and listener is not None:
            try:
                client, _ = listener.accept()
            except OSError as e:
                # stop() closed the listener out from under us.
                if self._closing or e.errno in (
                        errno.EBADF, errno.EINVAL, errno.ENOTSOCK):
                    break
                self._log('Port forward accept failed: {0}'.format(e))
                break

            if self._closing:
                _close(client)
                break

            threading.Thread(
                target=self._handle,
                args=(client,),
                name='pgadmin k8s port forward conn',
                daemon=True,
            ).start()

    def _handle(self, client):
        """Pump one accepted connection through its own forward stream."""
        forward = None
        remote = None
        try:
            forward = self._open_stream()
            remote = forward.socket(self.pod_port)
        except Exception as e:
            self._log('Could not forward a connection to pod "{0}": {1}'
                      .format(self.pod_name, e))
            _close(client)
            if forward is not None:
                try:
                    forward.close()
                except Exception:
                    pass
            return

        with self._lock:
            self._connections.add(client)

        try:
            self._pump(client, remote)
        finally:
            with self._lock:
                self._connections.discard(client)
            _close(client)
            _close(remote)
            try:
                forward.close()
            except Exception:
                pass

    def _pump(self, client, remote):
        peers = {client: remote, remote: client}
        while not self._closing:
            try:
                readable, _, errored = select.select(
                    [client, remote], [], [client, remote], 1)
            except (OSError, ValueError):
                break

            if errored:
                break

            for source in readable:
                try:
                    data = source.recv(BUFFER_SIZE)
                except OSError:
                    return
                if not data:
                    return
                try:
                    peers[source].sendall(data)
                except OSError:
                    return


def _close(sock):
    if sock is None:
        return
    try:
        sock.close()
    except Exception:
        pass
