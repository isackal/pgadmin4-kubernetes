/////////////////////////////////////////////////////////////
//
// pgAdmin 4 - PostgreSQL Tools
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import gettext from 'sources/gettext';
import _ from 'lodash';
import BaseUISchema from 'sources/SchemaView/base_schema.ui';
import pgAdmin from 'sources/pgadmin';
import {default as supportedServers} from 'pgadmin.server.supported_servers';
import current_user from 'pgadmin.user_management.current_user';
import { isEmptyString } from 'sources/validators';
import VariableSchema from './variable.ui';
import { getRandomColor } from '../../../../../static/js/utils';
import {
  getCachedKubernetesResourcePorts,
  getKubernetesContexts,
  getKubernetesNamespaces,
  getKubernetesResourcePorts,
  getKubernetesResources,
  getKubernetesSources,
} from './kubernetes_options';

const KUBERNETES_GROUP = gettext('Kubernetes');

/* Both values name the very same local listener.  They differ in who can
 * reach it: localhost keeps the forward private to this machine, while the
 * Docker host name is reachable from containers on it. */
const HOST_MODE_LOCALHOST = 'localhost';
const HOST_MODE_DOCKER = 'host.docker.internal';

const HOST_MODE_OPTIONS = [
  {label: HOST_MODE_LOCALHOST, value: HOST_MODE_LOCALHOST},
  {label: HOST_MODE_DOCKER, value: HOST_MODE_DOCKER},
];

const RESOURCE_KIND_OPTIONS = [
  {label: gettext('Service'), value: 'service'},
  {label: gettext('Pod'), value: 'pod'},
];

/* The four dropdowns narrow each other, so any change upstream invalidates
 * everything below it. */
const KUBERNETES_DOWNSTREAM_OF = {
  k8s_context: [
    'k8s_namespace', 'k8s_resource_name', 'k8s_username_ref',
    'k8s_password_ref', 'k8s_database_ref',
  ],
  k8s_namespace: [
    'k8s_resource_name', 'k8s_username_ref', 'k8s_password_ref',
    'k8s_database_ref',
  ],
  k8s_resource_kind: ['k8s_resource_name'],
};

function clearFields(names) {
  return names.reduce((cleared, name) => {
    cleared[name] = null;
    return cleared;
  }, {});
}

class TagsSchema extends BaseUISchema {
  get idAttribute() { return 'old_text'; }

  get baseFields() {
    return [
      {
        id: 'text', label: gettext('Text'), cell: 'text', group: null,
        mode: ['create', 'edit'], noEmpty: true, controlProps: {
          maxLength: 30,
        },
        disabled : this.top.isShared(this.top.origData),
      },
      {
        id: 'color', label: gettext('Color'), cell: 'color', group: null,
        mode: ['create', 'edit'], controlProps: {
          input: true,
        },
        disabled : this.top.isShared(this.top.origData),
      },
    ];
  }

  getNewData(data) {
    return {
      ...data,
      color: getRandomColor(),
    };
  }
}

export function getConnectionParameters() {
  let conParams = [{
    'value': 'hostaddr', 'label': gettext('Host address'), 'vartype': 'string'
  }, {
    'value': 'passfile', 'label': gettext('Password file'), 'vartype': 'file'
  }, {
    'value': 'channel_binding', 'label': gettext('Channel binding'), 'vartype': 'enum',
    'enumvals': ['prefer', 'require', 'disable'],
    'min_server_version': '13'
  }, {
    'value': 'connect_timeout', 'label': gettext('Connection timeout (seconds)'), 'vartype': 'integer'
  }, {
    'value': 'client_encoding', 'label': gettext('Client encoding'), 'vartype': 'string'
  },  {
    'value': 'options', 'label': gettext('Options'), 'vartype': 'string'
  }, {
    'value': 'application_name', 'label': gettext('Application name'), 'vartype': 'string'
  }, {
    'value': 'fallback_application_name', 'label': gettext('Fallback application name'), 'vartype': 'string'
  }, {
    'value': 'keepalives', 'label': gettext('Keepalives'), 'vartype': 'integer'
  }, {
    'value': 'keepalives_idle', 'label': gettext('Keepalives idle (seconds)'), 'vartype': 'integer'
  }, {
    'value': 'keepalives_interval', 'label': gettext('Keepalives interval (seconds)'), 'vartype': 'integer'
  }, {
    'value': 'keepalives_count', 'label': gettext('Keepalives count'), 'vartype': 'integer'
  }, {
    'value': 'tcp_user_timeout', 'label': gettext('TCP user timeout (milliseconds)'), 'vartype': 'integer',
    'min_server_version': '12'
  },  {
    'value': 'tty', 'label': gettext('TTY'), 'vartype': 'string',
    'max_server_version': '13'
  }, {
    'value': 'replication', 'label': gettext('Replication'), 'vartype': 'enum',
    'enumvals': ['on', 'off', 'database'],
    'min_server_version': '11'
  }, {
    'value': 'gssencmode', 'label': gettext('GSS encmode'), 'vartype': 'enum',
    'enumvals': ['prefer', 'require', 'disable'],
    'min_server_version': '12'
  }, {
    'value': 'sslmode', 'label': gettext('SSL mode'), 'vartype': 'enum',
    'enumvals': ['allow', 'prefer', 'require', 'disable', 'verify-ca', 'verify-full']
  }, {
    'value': 'sslcompression', 'label': gettext('SSL compression?'), 'vartype': 'bool',
  }, {
    'value': 'sslcert', 'label': gettext('Client certificate'), 'vartype': 'file'
  }, {
    'value': 'sslkey', 'label': gettext('Client certificate key'), 'vartype': 'file'
  }, {
    'value': 'sslpassword', 'label': gettext('SSL password'), 'vartype': 'password',
    'min_server_version': '13'
  }, {
    'value': 'sslrootcert', 'label': gettext('Root certificate'), 'vartype': 'file'
  }, {
    'value': 'sslcrl', 'label': gettext('Certificate revocation list'), 'vartype': 'file',
  }, {
    'value': 'sslcrldir', 'label': gettext('Certificate revocation list directory'), 'vartype': 'file',
    'min_server_version': '14'
  }, {
    'value': 'sslsni', 'label': gettext('Server name indication'), 'vartype': 'bool',
    'min_server_version': '14'
  }, {
    'value': 'requirepeer', 'label': gettext('Require peer'), 'vartype': 'string',
  }, {
    'value': 'ssl_min_protocol_version', 'label': gettext('SSL min protocol version'),
    'vartype': 'enum', 'min_server_version': '13',
    'enumvals': ['TLSv1', 'TLSv1.1', 'TLSv1.2', 'TLSv1.3']
  }, {
    'value': 'ssl_max_protocol_version', 'label': gettext('SSL max protocol version'),
    'vartype': 'enum', 'min_server_version': '13',
    'enumvals': ['TLSv1', 'TLSv1.1', 'TLSv1.2', 'TLSv1.3']
  }, {
    'value': 'krbsrvname', 'label': gettext('Kerberos service name'), 'vartype': 'string',
  }, {
    'value': 'gsslib', 'label': gettext('GSS library'), 'vartype': 'string',
  }, {
    'value': 'target_session_attrs', 'label': gettext('Target session attribute'),
    'vartype': 'enum',
    'enumvals': ['any', 'read-write', 'read-only', 'primary', 'standby', 'prefer-standby']
  }, {
    'value': 'load_balance_hosts', 'label': gettext('Load balance hosts'),
    'vartype': 'enum', 'min_server_version': '16',
    'enumvals': ['disable', 'random']
  }, {
    'value': 'gssdelegation', 'label': gettext('GSS delegation?'), 'vartype': 'bool',
    'min_server_version': '16'
  }, {
    'value': 'require_auth', 'label': gettext('Require authentication'), 'vartype': 'string',
    'min_server_version': '16'
  }, {
    'value': 'sslnegotiation', 'label': gettext('SSL negotiation'),
    'vartype': 'enum', 'enumvals': ['postgres', 'direct'],
    'min_server_version': '17'
  }, {
    'value': 'sslkeylogfile', 'label': gettext('SSL Key Logfile'), 'vartype': 'file',
    'min_server_version': '18'
  }, {
    'value': 'min_protocol_version', 'label': gettext('Min protocol version'),
    'vartype': 'enum', 'min_server_version': '18',
    'enumvals': ['3.0', '3.2', 'latest']
  }, {
    'value': 'max_protocol_version', 'label': gettext('Max protocol version'),
    'vartype': 'enum', 'min_server_version': '18',
    'enumvals': ['3.0', '3.2', 'latest']
  }, {
    'value': 'oauth_issuer', 'label': gettext('OAuth issuer'), 'vartype': 'string',
    'min_server_version': '18'
  }, {
    'value': 'oauth_client_id', 'label': gettext('OAuth client id'), 'vartype': 'string',
    'min_server_version': '18'
  }, {
    'value': 'oauth_client_secret', 'label': gettext('OAuth client secret'), 'vartype': 'password',
    'min_server_version': '18'
  }, {
    'value': 'oauth_scope', 'label': gettext('OAuth scope'), 'vartype': 'string',
    'min_server_version': '18'
  }];

  conParams.sort(function (a, b) {
    return pgAdmin.natural_sort(a.value, b.value);
  });

  return conParams;
};

export default class ServerSchema extends BaseUISchema {
  constructor(serverGroupOptions=[], userId=0, initValues={}) {
    super({
      gid: undefined,
      id: undefined,
      name: '',
      bgcolor: '',
      fgcolor: '',
      host: '',
      port: 5432,
      db: 'postgres',
      username: current_user.name,
      role: null,
      connect_now: true,
      password: undefined,
      save_password: false,
      db_res: undefined,
      db_res_type: 'databases',
      passexec: undefined,
      passexec_expiration: undefined,
      service: undefined,
      shared_username: '',
      use_ssh_tunnel: false,
      tunnel_host: undefined,
      tunnel_port: 22,
      tunnel_username: undefined,
      tunnel_identity_file: undefined,
      tunnel_prompt_password: false,
      tunnel_password: undefined,
      tunnel_authentication: false,
      tunnel_keep_alive: 0,
      save_tunnel_password: false,
      connection_string: undefined,
      connection_params: [
        {'name': 'sslmode', 'value': 'prefer', 'keyword': 'sslmode'},
        {'name': 'connect_timeout', 'value': 10, 'keyword': 'connect_timeout'}],
      tags: [],
      kubernetes_conn: false,
      k8s_context: undefined,
      k8s_namespace: undefined,
      k8s_resource_kind: 'service',
      k8s_resource_name: undefined,
      k8s_username_ref: undefined,
      k8s_password_ref: undefined,
      k8s_database_ref: undefined,
      ...initValues,
    });

    this.serverGroupOptions = serverGroupOptions;
    this.paramSchema = new VariableSchema(getConnectionParameters(), null, null, ['name', 'keyword', 'value']);
    this.tagsSchema = new TagsSchema();
    this.userId = userId;
    _.bindAll(this, 'isShared', 'isKubernetes', 'isNotKubernetes',
      'kubernetesReadOnly');
  }

  initialise(state) {
    this.paramSchema.setAllReadOnly(this.isConnected(state));
  }

  isShared(state) {
    return !this.isNew(state) && this.userId != current_user.id && state.shared;
  }

  isConnected(state) {
    return Boolean(state.connected);
  }

  isConnectedOrShared(state) {
    return this.isConnected(state) || this.isShared(state);
  }

  isKubernetes(state) {
    return Boolean(state.kubernetes_conn);
  }

  isNotKubernetes(state) {
    return !this.isKubernetes(state);
  }

  /* The Kubernetes dropdowns only mean anything once the switch is on, and
   * the contract is pinned for as long as the server is connected. */
  kubernetesReadOnly(state) {
    return !this.isKubernetes(state) || this.isConnected(state);
  }

  /* Options for one of the cascading dropdowns, kept empty until every
   * level above it has been answered. */
  kubernetesOptions(state, fetch) {
    return () => this.isKubernetes(state) ? fetch() : Promise.resolve([]);
  }

  /* Username, password and database are all picked the same way: as a
   * <secret|configmap>/<name>/<key> reference from the chosen namespace. */
  kubernetesSourceField(state) {
    return {
      type: 'select',
      options: this.kubernetesOptions(state, () => getKubernetesSources(
        state.k8s_context, state.k8s_namespace
      )),
      optionsReloadBasis: [state.k8s_context, state.k8s_namespace].join('/'),
    };
  }

  get baseFields() {
    let obj = this;
    return [
      {
        id: 'id', label: gettext('ID'), type: 'int', group: null,
        mode: ['properties'],
      },{
        id: 'name', label: gettext('Name'), type: 'text', group: null,
        mode: ['properties', 'edit', 'create'], noEmpty: true,
        disabled: obj.isShared,
      },{
        id: 'gid', label: gettext('Server group'), type: 'select',
        options: obj.serverGroupOptions,
        mode: ['create', 'edit'],
        controlProps: { allowClear: false },
        disabled: obj.isShared,
      },
      {
        id: 'server_owner', label: gettext('Shared Server Owner'), type: 'text', mode: ['properties'],
        visible: function(state) {
          let serverOwner = obj.userId;
          return state.shared && serverOwner != current_user.id && pgAdmin.server_mode == 'True';
        },
      },
      {
        id: 'server_type', label: gettext('Server type'), type: 'select',
        mode: ['properties'], visible: obj.isConnected,
        options: supportedServers,
      }, {
        id: 'connected', label: gettext('Connected?'), type: 'switch',
        mode: ['properties'], group: gettext('Connection'),
      }, {
        id: 'version', label: gettext('Version'), type: 'text', group: null,
        mode: ['properties'], visible: obj.isConnected,
      },
      {
        id: 'bgcolor', label: gettext('Background'), type: 'color',
        group: null, mode: ['edit', 'create'],
        disabled: obj.isConnected, deps: ['fgcolor'], depChange: (state, source)=>{
          if(source[0] == 'fgcolor' && !state.bgcolor && state.fgcolor) {
            return {'bgcolor': '#ffffff'};
          }
        }
      },{
        id: 'fgcolor', label: gettext('Foreground'), type: 'color',
        group: null, mode: ['edit', 'create'], disabled: obj.isConnected,
      },
      {
        id: 'connect_now', label: gettext('Connect now?'), type: 'switch',
        group: null, mode: ['create'],
      },
      {
        id: 'shared', label: gettext('Shared?'), type: 'switch',
        mode: ['properties', 'create', 'edit'], deps: ['kubernetes_conn'],
        readonly: function(state){
          let serverOwner = obj.userId;
          return !obj.isNew(state) && serverOwner != current_user.id;
        }, visible: function(state){
          /* Sharing a Kubernetes connection would lend every other user the
           * cluster credentials it was registered with. */
          return current_user.is_admin && pgAdmin.server_mode == 'True'
            && !obj.isKubernetes(state);
        },
      },
      {
        id: 'shared_username', label: gettext('Shared Username'), type: 'text',
        controlProps: { maxLength: 64},
        mode: ['properties', 'create', 'edit'], deps: ['shared', 'username'],
        readonly: (s) => {
          return !(!this.origData.shared && s.shared);
        }, visible: ()=>{
          return current_user.is_admin && pgAdmin.server_mode == 'True';
        },
        depChange: (state, source, _topState, actionObj)=>{
          let ret = {};
          if(this.origData.shared) {
            return ret;
          }
          if(source == 'username' && actionObj.oldState.username == state.shared_username) {
            ret['shared_username'] = state.username;
          }
          if(source == 'shared') {
            if(state.shared) {
              ret['shared_username'] = state.username;
            } else {
              ret['shared_username'] = '';
            }
          }
          return ret;
        },
      },
      {
        id: 'comment', label: gettext('Comments'), type: 'multiline', group: null,
        mode: ['properties', 'edit', 'create'], disabled: obj.isShared,
      }, {
        id: 'connection_string', label: gettext('Connection String'), type: 'multiline',
        group: gettext('Connection'), mode: ['properties'], readonly: true,
      }, {
        id: 'host', label: gettext('Host name/address'), group: gettext('Connection'),
        mode: ['properties', 'edit', 'create'], disabled: obj.isShared,
        deps: ['kubernetes_conn'],
        /* A Kubernetes connection always reaches its port forward locally,
         * so the only choice is which local name to reach it by. */
        type: (state)=>{
          if(!obj.isKubernetes(state)) {
            return {type: 'text'};
          }
          return {
            type: 'select',
            options: HOST_MODE_OPTIONS,
            controlProps: {allowClear: false},
          };
        },
        helpMessage: gettext('Choose "%s" when something inside a Docker container has to reach the forwarded port; the listener is then bound on all interfaces rather than kept private to this machine.', HOST_MODE_DOCKER),
        helpMessageMode: ['edit', 'create'],
        depChange: (state)=>{
          if(obj.origData.host != state.host && !obj.isNew(state) && state.connected){
            obj.informText = gettext(
              'To apply changes to the connection configuration, please disconnect from the server and then reconnect.'
            );
          } else {
            obj.informText = undefined;
          }
        }
      },
      {
        id: 'port', label: gettext('Port'), group: gettext('Connection'),
        mode: ['properties', 'edit', 'create'], disabled: obj.isShared,
        deps: [
          'kubernetes_conn', 'k8s_context', 'k8s_namespace',
          'k8s_resource_kind', 'k8s_resource_name',
        ],
        /* In Kubernetes mode this is the port the service or pod exposes,
         * not the forwarded local port - that one is picked from whatever
         * is free and is never shown. */
        type: (state)=>{
          if(!obj.isKubernetes(state)) {
            return {type: 'int', min: 1, max: 65535};
          }
          return {
            type: 'select',
            options: obj.kubernetesOptions(state, ()=>getKubernetesResourcePorts(
              state.k8s_context, state.k8s_namespace,
              state.k8s_resource_kind, state.k8s_resource_name
            )),
            optionsReloadBasis: [
              state.k8s_context, state.k8s_namespace,
              state.k8s_resource_kind, state.k8s_resource_name,
            ].join('/'),
            controlProps: {allowClear: false},
          };
        },
        depChange: (state)=>{
          if(obj.origData.port != state.port && !obj.isNew(state) && state.connected){
            obj.informText = gettext(
              'To apply changes to the connection configuration, please disconnect from the server and then reconnect.'
            );
          } else {
            obj.informText = undefined;
          }
        }
      },{
        id: 'db', label: gettext('Maintenance database'), type: 'text', group: gettext('Connection'),
        mode: ['properties', 'edit', 'create'], deps: ['kubernetes_conn'],
        readonly: (state)=>obj.isConnectedOrShared(state) || obj.isKubernetes(state),
        /* A Kubernetes connection reads this from the cluster, so there is
         * nothing to show until the server has been registered. */
        visible: (state)=>!obj.isKubernetes(state) || !obj.isNew(state),
      },{
        id: 'username', label: gettext('Username'), type: 'text', group: gettext('Connection'),
        mode: ['properties', 'edit', 'create'], deps: ['kubernetes_conn'],
        readonly: (state)=>obj.isKubernetes(state),
        visible: (state)=>!obj.isKubernetes(state) || !obj.isNew(state),
        depChange: (state)=>{
          if(obj.origData.username != state.username && !obj.isNew(state) && state.connected){
            obj.informText = gettext(
              'To apply changes to the connection configuration, please disconnect from the server and then reconnect.'
            );
          } else {
            obj.informText = undefined;
          }
        }
      },{
        id: 'kerberos_conn', label: gettext('Kerberos authentication?'), type: 'switch',
        group: gettext('Connection'), disabled: obj.isShared,
        deps: ['kubernetes_conn'], visible: obj.isNotKubernetes,
      },{
        id: 'gss_authenticated', label: gettext('GSS authenticated?'), type: 'switch',
        group: gettext('Connection'), mode: ['properties'], visible: obj.isConnected,
      },{
        id: 'gss_encrypted', label: gettext('GSS encrypted?'), type: 'switch',
        group: gettext('Connection'), mode: ['properties'], visible: obj.isConnected,
      },{
        id: 'password', label: gettext('Password'), type: 'password',
        group: gettext('Connection'),
        mode: ['create', 'edit'],
        deps: ['kerberos_conn', 'save_password', 'kubernetes_conn'],
        controlProps: {
          maxLength: null,
          autoComplete: 'new-password'
        },
        readonly: function(state) {
          if (obj.isNew())
            return false;
          return state.connected || !state.save_password;
        },
        disabled: function(state) {return state.kerberos_conn;},
        /* Nothing to type or store: a Kubernetes connection reads its
         * password from the cluster every time it connects. */
        visible: obj.isNotKubernetes,
        helpMessage: gettext('In edit mode the password field is enabled only if Save Password is set to true.')
      },{
        id: 'save_password', label: gettext('Save password?'),
        type: 'switch', group: gettext('Connection'), mode: ['create', 'edit'],
        deps: ['kerberos_conn', 'kubernetes_conn'],
        readonly: function(state) {
          return state.connected;
        },
        disabled: function(state) {
          return !current_user.allow_save_password || state.kerberos_conn;
        },
        visible: obj.isNotKubernetes,
      },{
        id: 'role', label: gettext('Role'), type: 'text', group: gettext('Connection'),
        mode: ['properties', 'edit', 'create'], readonly: obj.isConnected,
      },{
        id: 'service', label: gettext('Service'), type: 'text',
        mode: ['properties', 'edit', 'create'], readonly: obj.isConnectedOrShared,
        group: gettext('Connection'), deps: ['kubernetes_conn'],
        /* A libpq service file would supply its own host and port, which is
         * exactly what the port forward is there to decide. */
        visible: obj.isNotKubernetes,
      },
      {
        id: 'kubernetes_conn', label: gettext('Connect through Kubernetes?'),
        type: 'switch', group: KUBERNETES_GROUP,
        mode: ['properties', 'edit', 'create'],
        readonly: obj.isConnected,
        disabled: function() {
          return !pgAdmin.Browser.utils.support_kubernetes;
        },
        helpMessage: gettext('pgAdmin forwards a free local port to the selected service or pod, and reads the username, password and database name from the selected Secret or Config Map keys each time it connects. The forward is opened on connect and closed again when the server is disconnected or removed.'),
        depChange: (state, source)=>{
          if(source[0] != 'kubernetes_conn') return;

          if(state.kubernetes_conn) {
            /* These all describe a different way of reaching the server and
             * cannot apply at the same time as a port forward. */
            return {
              host: HOST_MODE_LOCALHOST,
              use_ssh_tunnel: false,
              kerberos_conn: false,
              shared: false,
              service: null,
              password: null,
              save_password: false,
              k8s_resource_kind: state.k8s_resource_kind || 'service',
            };
          }

          return {
            host: '',
            ...clearFields([
              'k8s_context', 'k8s_namespace', 'k8s_resource_name',
              'k8s_username_ref', 'k8s_password_ref', 'k8s_database_ref',
            ]),
          };
        },
      },
      {
        id: 'k8s_context', label: gettext('Context'), group: KUBERNETES_GROUP,
        mode: ['properties', 'edit', 'create'], deps: ['kubernetes_conn'],
        readonly: obj.kubernetesReadOnly,
        type: (state)=>({
          type: 'select',
          options: obj.kubernetesOptions(state, getKubernetesContexts),
          optionsReloadBasis: String(obj.isKubernetes(state)),
        }),
        depChange: (state, source)=>{
          if(source[0] == 'k8s_context') {
            return clearFields(KUBERNETES_DOWNSTREAM_OF.k8s_context);
          }
        },
      },
      {
        id: 'k8s_namespace', label: gettext('Namespace'),
        group: KUBERNETES_GROUP, mode: ['properties', 'edit', 'create'],
        deps: ['kubernetes_conn', 'k8s_context'],
        readonly: obj.kubernetesReadOnly,
        type: (state)=>({
          type: 'select',
          options: obj.kubernetesOptions(
            state, ()=>getKubernetesNamespaces(state.k8s_context)),
          optionsReloadBasis: state.k8s_context,
        }),
        depChange: (state, source)=>{
          if(source[0] == 'k8s_namespace') {
            return clearFields(KUBERNETES_DOWNSTREAM_OF.k8s_namespace);
          }
        },
      },
      {
        id: 'k8s_resource_kind', label: gettext('Resource type'),
        type: 'toggle', group: KUBERNETES_GROUP,
        mode: ['properties', 'edit', 'create'],
        options: RESOURCE_KIND_OPTIONS,
        deps: ['kubernetes_conn'],
        readonly: obj.kubernetesReadOnly,
        depChange: (state, source)=>{
          if(source[0] == 'k8s_resource_kind') {
            return clearFields(KUBERNETES_DOWNSTREAM_OF.k8s_resource_kind);
          }
        },
      },
      {
        id: 'k8s_resource_name', label: gettext('Service or pod'),
        group: KUBERNETES_GROUP, mode: ['properties', 'edit', 'create'],
        deps: [
          'kubernetes_conn', 'k8s_context', 'k8s_namespace',
          'k8s_resource_kind',
        ],
        readonly: obj.kubernetesReadOnly,
        type: (state)=>({
          type: 'select',
          options: obj.kubernetesOptions(state, ()=>getKubernetesResources(
            state.k8s_context, state.k8s_namespace, state.k8s_resource_kind
          )),
          optionsReloadBasis: [
            state.k8s_context, state.k8s_namespace, state.k8s_resource_kind,
          ].join('/'),
        }),
        depChange: (state, source)=>{
          if(source[0] != 'k8s_resource_name') return;

          /* Most workloads expose exactly one port; pick it so the common
           * case needs no extra decision.  The list was already fetched to
           * populate this dropdown, so this costs no round trip. */
          const ports = getCachedKubernetesResourcePorts(
            state.k8s_context, state.k8s_namespace,
            state.k8s_resource_kind, state.k8s_resource_name
          );
          return {port: ports.length ? ports[0].value : null};
        },
      },
      {
        id: 'k8s_username_ref', label: gettext('Username from'),
        group: KUBERNETES_GROUP, mode: ['properties', 'edit', 'create'],
        deps: ['kubernetes_conn', 'k8s_context', 'k8s_namespace'],
        readonly: obj.kubernetesReadOnly,
        type: (state)=>obj.kubernetesSourceField(state),
        helpMessage: gettext('The Secret or Config Map key holding the user name to connect as.'),
      },
      {
        id: 'k8s_password_ref', label: gettext('Password from'),
        group: KUBERNETES_GROUP, mode: ['properties', 'edit', 'create'],
        deps: ['kubernetes_conn', 'k8s_context', 'k8s_namespace'],
        readonly: obj.kubernetesReadOnly,
        type: (state)=>obj.kubernetesSourceField(state),
        helpMessage: gettext('The Secret or Config Map key holding the password. Leave empty if the server does not need one.'),
      },
      {
        id: 'k8s_database_ref', label: gettext('Database from'),
        group: KUBERNETES_GROUP, mode: ['properties', 'edit', 'create'],
        deps: ['kubernetes_conn', 'k8s_context', 'k8s_namespace'],
        readonly: obj.kubernetesReadOnly,
        type: (state)=>obj.kubernetesSourceField(state),
        helpMessage: gettext('The Secret or Config Map key holding the maintenance database name.'),
      },
      {
        id: 'connection_params', label: gettext('Connection Parameters'),
        type: 'collection', group: gettext('Parameters'),
        schema: this.paramSchema, mode: ['edit', 'create'], uniqueCol: ['name'],
        canAdd: (state)=> !obj.isConnected(state), canEdit: false,
        canDelete: (state)=> !obj.isConnected(state),
      }, {
        id: 'use_ssh_tunnel', label: gettext('Use SSH tunneling'), type: 'switch',
        mode: ['properties', 'edit', 'create'], group: gettext('SSH Tunnel'),
        deps: ['kubernetes_conn'],
        disabled: function(state) {
          /* A Kubernetes connection already tunnels through the API
           * server, so an SSH tunnel has nothing left to reach. */
          return !pgAdmin.Browser.utils.support_ssh_tunnel
            || obj.isKubernetes(state);
        },
        readonly: obj.isConnected,
      },{
        id: 'tunnel_host', label: gettext('Tunnel host'), type: 'text', group: gettext('SSH Tunnel'),
        mode: ['properties', 'edit', 'create'], deps: ['use_ssh_tunnel'],
        disabled: function(state) {
          return !state.use_ssh_tunnel;
        },
        readonly: obj.isConnected,
      },{
        id: 'tunnel_port', label: gettext('Tunnel port'), type: 'int', group: gettext('SSH Tunnel'),
        mode: ['properties', 'edit', 'create'], deps: ['use_ssh_tunnel'], max: 65535,
        disabled: function(state) {
          return !state.use_ssh_tunnel;
        },
        readonly: obj.isConnected,
      },{
        id: 'tunnel_username', label: gettext('Username'), type: 'text', group: gettext('SSH Tunnel'),
        mode: ['properties', 'edit', 'create'], deps: ['use_ssh_tunnel'],
        disabled: function(state) {
          return !state.use_ssh_tunnel;
        },
        readonly: obj.isConnected,
      },{
        id: 'tunnel_authentication', label: gettext('Authentication'), type: 'toggle',
        mode: ['properties', 'edit', 'create'], group: gettext('SSH Tunnel'),
        options: [
          {'label': gettext('Password'), value: false},
          {'label': gettext('Identity file'), value: true},
        ],
        disabled: function(state) {
          return !state.use_ssh_tunnel;
        },
        readonly: obj.isConnected,
      },
      {
        id: 'tunnel_identity_file', label: gettext('Identity file'), type: 'file',
        group: gettext('SSH Tunnel'), mode: ['properties', 'edit', 'create'],
        controlProps: {
          dialogType: 'select_file', supportedTypes: ['*'],
        },
        deps: ['tunnel_authentication', 'use_ssh_tunnel'],
        depChange: (state)=>{
          if (!state.tunnel_authentication && state.tunnel_identity_file) {
            return {tunnel_identity_file: null};
          }
        },
        disabled: function(state) {
          return !state.tunnel_authentication || !state.use_ssh_tunnel;
        },
      },
      {
        id: 'tunnel_password', label: gettext('Password'), type: 'password',
        group: gettext('SSH Tunnel'), mode: ['create'],
        deps: ['use_ssh_tunnel'],
        disabled: function(state) {
          return !state.use_ssh_tunnel;
        },
        controlProps: {
          maxLength: null
        },
        readonly: obj.isConnected,
      },
      {
        id: 'tunnel_prompt_password',
        label: gettext('Prompt for identity file password?'),
        type: 'switch', group: gettext('SSH Tunnel'), mode: ['properties', 'edit', 'create'],
        deps: ['tunnel_authentication', 'use_ssh_tunnel'],
        depChange: (state)=>{
          if (!state.tunnel_authentication) {
            return {tunnel_prompt_password: false};
          }
        },
        disabled: function(state) {
          return !state.tunnel_authentication || !state.use_ssh_tunnel;
        },
        helpMessage: gettext('Enable to be prompted for the identity file\'s passphrase at connection time, if the file is passphrase-protected. This setting applies only to identity-file authentication. When using password authentication for the SSH tunnel, leave the SSH password field empty to be prompted on connection.')
      },
      {
        id: 'save_tunnel_password', label: gettext('Save password?'),
        type: 'switch', group: gettext('SSH Tunnel'), mode: ['create'],
        deps: ['connect_now', 'use_ssh_tunnel'],
        visible: function(state) {
          return state.connect_now && obj.isNew(state);
        },
        disabled: function(state) {
          return (!current_user.allow_save_tunnel_password || !state.use_ssh_tunnel);
        },
      },
      {
        id: 'tunnel_keep_alive', label: gettext('Keep alive (seconds)'),
        type: 'int', group: gettext('SSH Tunnel'), min: 0,
        mode: ['properties', 'edit', 'create'], deps: ['use_ssh_tunnel'],
        disabled: function(state) {
          return !state.use_ssh_tunnel;
        },
        readonly: obj.isConnected,
      },
      {
        id: 'db_res_type', label: gettext('DB restriction type'), type: 'toggle',
        mode: ['properties', 'edit', 'create'], group: gettext('Advanced'),
        options: [
          {'label': gettext('Databases'), value: 'databases'},
          {'label': gettext('SQL'), value: 'sql'},
        ],
        readonly: obj.isConnectedOrShared,
        depChange: ()=>{
          return {
            db_res: null,
          };
        }
      },
      {
        id: 'db_res', label: gettext('DB restriction'), group: gettext('Advanced'),
        mode: ['properties', 'edit', 'create'], readonly: obj.isConnectedOrShared,
        deps: ['db_res_type'],
        type: (state) => {
          if (state.db_res_type == 'databases') {
            return {
              type: 'select',
              options: [],
              controlProps: {
                multiple: true,
                allowClear: false,
                creatable: true,
                noDropdown: true,
                placeholder: 'Specify the databases to be restrict...'
              }
            };
          } else {
            return {
              type: 'sql',
            };
          }
        },
      },
      {
        id: 'passexec_cmd', label: gettext('Password exec command'), type: 'text',
        group: gettext('Advanced'), controlProps: {maxLength: null},
        mode: ['properties', 'edit', 'create'], deps: ['kubernetes_conn'],
        disabled: pgAdmin.server_mode == 'True' && pgAdmin.enable_server_passexec_cmd == 'False',
        /* The cluster is already the source of the password. */
        visible: obj.isNotKubernetes,
        helpMessage: gettext('The server hostname, port, and username can be passed as variables by using the placeholders %HOSTNAME%, %PORT%, and %USERNAME%, which will be replaced with the corresponding server connection information.')
      },
      {
        id: 'passexec_expiration', label: gettext('Password exec expiration (seconds)'), type: 'int',
        group: gettext('Advanced'),
        mode: ['properties', 'edit', 'create'], deps: ['kubernetes_conn'],
        disabled: function(state) {
          return isEmptyString(state.passexec_cmd);
        },
        visible: obj.isNotKubernetes,
      },
      {
        id: 'prepare_threshold', label: gettext('Prepare threshold'), type: 'int',
        group: gettext('Advanced'), disabled: obj.isShared,
        mode: ['properties', 'edit', 'create'],
        helpMessageMode: ['edit', 'create'],
        helpMessage: gettext('If it is set to 0, every query is prepared the first time it is executed. If it is set to blank, prepared statements are disabled on the connection.')
      },
      {
        id: 'post_connection_sql', label: gettext('Post Connection SQL'),
        group: gettext('Post Connection SQL'),
        mode: ['properties', 'edit', 'create'],
        type: 'sql', isFullTab: true,
        readonly: obj.isConnected,
        helpMessage: gettext('Any query specified in the control below will be executed with autocommit mode enabled for each connection to any database on this server.'),
      },
      {
        id: 'tags', label: gettext('Tags'),
        type: 'collection', group: gettext('Tags'), disabled: obj.isShared,
        schema: this.tagsSchema, mode: ['edit', 'create'], uniqueCol: ['text'],
        canAdd: true, canEdit: false, canDelete: true, maxCount: pgAdmin.Browser.utils.max_server_tags_allowed,
      },
    ];
  }

  /* A Kubernetes connection is described entirely by its contract, so none
   * of the host/username/password checks below apply to it. */
  validateKubernetes(state, setError) {
    _.each(['host', 'db', 'username', 'port', 'service', 'tunnel_host',
      'tunnel_port', 'tunnel_username', 'tunnel_identity_file',
      'tunnel_keep_alive'], (item) => {
      setError(item, null);
    });

    const required = [
      ['k8s_context', gettext('Kubernetes context must be selected.')],
      ['k8s_namespace', gettext('Namespace must be selected.')],
      ['k8s_resource_name', gettext('A service or pod must be selected.')],
      ['port', gettext('The port to forward must be selected.')],
      ['k8s_username_ref', gettext('A username source must be selected.')],
      ['k8s_database_ref', gettext('A database source must be selected.')],
    ];

    for(const [field, message] of required) {
      if(isEmptyString(state[field])) {
        setError(field, message);
        return true;
      }
      setError(field, null);
    }

    setError('k8s_password_ref', null);
    return false;
  }

  validate(state, setError) {
    let errmsg = null;

    if(isEmptyString(state.gid)) {
      errmsg = gettext('Server group must be specified.');
      setError('gid', errmsg);
      return true;
    } else {
      setError('gid', null);
    }

    if (this.isKubernetes(state)) {
      return this.validateKubernetes(state, setError);
    }

    _.each(['k8s_context', 'k8s_namespace', 'k8s_resource_name',
      'k8s_username_ref', 'k8s_database_ref'], (item) => {
      setError(item, null);
    });

    /* Moved off the `db` field's noEmpty so a Kubernetes connection, whose
     * database name is only known once the cluster has been read, can leave
     * it blank at registration time. */
    if(isEmptyString(state.db)) {
      setError('db', gettext('Maintenance database must be specified.'));
      return true;
    } else {
      setError('db', null);
    }

    if (isEmptyString(state.service)) {
      errmsg = gettext('Either Host name or Service must be specified.');
      if(isEmptyString(state.host)) {
        setError('host', errmsg);
        return true;
      } else {
        setError('host', null);
      }

      /* Hostname, IP address validate */
      if (state.host) {
        // Check for leading and trailing spaces.
        if (/(^\s)|(\s$)/.test(state.host)){
          errmsg = gettext('Host name must be valid hostname or IPv4 or IPv6 address.');
          setError('host', errmsg);
          return true;
        } else {
          setError('host', null);
        }
      }

      if(isEmptyString(state.username)) {
        errmsg = gettext('Username must be specified.');
        setError('username', errmsg);
        return true;
      } else {
        setError('username', null);
      }

      if(isEmptyString(state.port)) {
        errmsg = gettext('Port must be specified.');
        setError('port', errmsg);
        return true;
      } else {
        setError('port', null);
      }
    } else {
      _.each(['host', 'db', 'username', 'port'], (item) => {
        setError(item, null);
      });
    }

    if (state.use_ssh_tunnel) {
      if(isEmptyString(state.tunnel_host)) {
        errmsg = gettext('SSH Tunnel host must be specified.');
        setError('tunnel_host', errmsg);
        return true;
      } else {
        setError('tunnel_host', null);
      }

      if(isEmptyString(state.tunnel_port)) {
        errmsg = gettext('SSH Tunnel port must be specified.');
        setError('tunnel_port', errmsg);
        return true;
      } else {
        setError('tunnel_port', null);
      }

      if(isEmptyString(state.tunnel_username)) {
        errmsg = gettext('SSH Tunnel username must be specified.');
        setError('tunnel_username', errmsg);
        return true;
      } else {
        setError('tunnel_username', null);
      }

      if (state.tunnel_authentication) {
        if(isEmptyString(state.tunnel_identity_file)) {
          errmsg = gettext('SSH Tunnel identity file must be specified.');
          setError('tunnel_identity_file', errmsg);
          return true;
        } else {
          setError('tunnel_identity_file', null);
        }
      }

      if(isEmptyString(state.tunnel_keep_alive)) {
        errmsg = gettext('Keep alive must be specified. Specify 0 for no keep alive.');
        setError('tunnel_keep_alive', errmsg);
        return true;
      } else {
        setError('tunnel_keep_alive', null);
      }
    }
    return false;
  }
}
