/////////////////////////////////////////////////////////////
//
// pgAdmin 4 - PostgreSQL Tools
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import pgAdmin from 'sources/pgadmin';
import ServerSchema from '../../../pgadmin/browser/server_groups/servers/static/js/server.ui';
import {genericBeforeEach, getCreateView, getEditView} from '../genericFunctions';

/* The dropdowns talk to a cluster; the schema behaviour under test does
 * not. kubernetes_options has its own spec covering the requests. */
jest.mock(
  '../../../pgadmin/browser/server_groups/servers/static/js/kubernetes_options',
  () => ({
    getKubernetesContexts: jest.fn(() => Promise.resolve([
      {label: 'kind-dbviewer', value: 'kind-dbviewer'},
    ])),
    getKubernetesNamespaces: jest.fn(() => Promise.resolve([
      {label: 'pg-standard', value: 'pg-standard'},
    ])),
    getKubernetesResources: jest.fn(() => Promise.resolve([
      {label: 'postgres', value: 'postgres'},
    ])),
    getKubernetesResourcePorts: jest.fn(() => Promise.resolve([
      {label: '5432', value: 5432},
    ])),
    getCachedKubernetesResourcePorts: jest.fn(() => [
      {label: '5433', value: 5433},
    ]),
    getKubernetesSources: jest.fn(() => Promise.resolve([
      {label: 'secret/pg-standard-credentials/username',
        value: 'secret/pg-standard-credentials/username'},
    ])),
  })
);

const KUBERNETES_STATE = {
  gid: 1,
  kubernetes_conn: true,
  host: 'localhost',
  port: 5432,
  k8s_context: 'kind-dbviewer',
  k8s_namespace: 'pg-standard',
  k8s_resource_kind: 'service',
  k8s_resource_name: 'postgres',
  k8s_username_ref: 'secret/pg-standard-credentials/username',
  k8s_password_ref: 'secret/pg-standard-credentials/password',
  k8s_database_ref: 'secret/pg-standard-credentials/database',
};

describe('ServerSchema Kubernetes', ()=>{
  const createSchemaObject = () => new ServerSchema([{
    label: 'Servers', value: 1,
  }], 0, {user_id: 'jest'});

  let schemaObj = createSchemaObject();

  beforeEach(()=>{
    genericBeforeEach();
    pgAdmin.Browser.utils.support_ssh_tunnel = true;
    pgAdmin.Browser.utils.support_kubernetes = true;
  });

  const fieldById = (id) => schemaObj.fields.find((f) => f.id == id);
  const evaluate = (prop, state) => {
    const field = fieldById(prop.id);
    const value = field[prop.name];
    return typeof value == 'function' ? value(state) : value;
  };

  it('renders the create view in Kubernetes mode', async ()=>{
    await getCreateView(createSchemaObject());
  });

  it('renders the edit view of a Kubernetes server', async ()=>{
    await getEditView(
      createSchemaObject(),
      () => Promise.resolve({...KUBERNETES_STATE, id: 1})
    );
  });

  it('defaults to a plain connection', ()=>{
    expect(schemaObj.defaults.kubernetes_conn).toBe(false);
    expect(schemaObj.defaults.k8s_resource_kind).toBe('service');
  });

  it('offers only local hosts, defaulting to localhost', ()=>{
    const hostType = evaluate({id: 'host', name: 'type'}, KUBERNETES_STATE);
    expect(hostType.type).toBe('select');
    expect(hostType.options).toEqual([
      {label: 'localhost', value: 'localhost'},
      {label: 'host.docker.internal', value: 'host.docker.internal'},
    ]);

    const applied = fieldById('kubernetes_conn').depChange(
      {kubernetes_conn: true}, ['kubernetes_conn']);
    expect(applied.host).toBe('localhost');
  });

  it('leaves the host a free text field for a plain connection', ()=>{
    const hostType = evaluate({id: 'host', name: 'type'},
      {kubernetes_conn: false});
    expect(hostType.type).toBe('text');
  });

  it('turns off the settings that cannot coexist with a forward', ()=>{
    const applied = fieldById('kubernetes_conn').depChange(
      {kubernetes_conn: true}, ['kubernetes_conn']);

    expect(applied.use_ssh_tunnel).toBe(false);
    expect(applied.kerberos_conn).toBe(false);
    expect(applied.shared).toBe(false);
    expect(applied.service).toBeNull();
    expect(applied.password).toBeNull();
    expect(applied.save_password).toBe(false);
  });

  it('clears the contract when Kubernetes is switched back off', ()=>{
    const applied = fieldById('kubernetes_conn').depChange(
      {kubernetes_conn: false}, ['kubernetes_conn']);

    expect(applied.k8s_context).toBeNull();
    expect(applied.k8s_namespace).toBeNull();
    expect(applied.k8s_resource_name).toBeNull();
    expect(applied.k8s_username_ref).toBeNull();
    expect(applied.k8s_password_ref).toBeNull();
    expect(applied.k8s_database_ref).toBeNull();
    expect(applied.host).toBe('');
  });

  it('invalidates every dropdown below the one that changed', ()=>{
    expect(fieldById('k8s_context').depChange(
      KUBERNETES_STATE, ['k8s_context'])).toEqual({
      k8s_namespace: null, k8s_resource_name: null,
      k8s_username_ref: null, k8s_password_ref: null, k8s_database_ref: null,
    });

    expect(fieldById('k8s_namespace').depChange(
      KUBERNETES_STATE, ['k8s_namespace'])).toEqual({
      k8s_resource_name: null, k8s_username_ref: null,
      k8s_password_ref: null, k8s_database_ref: null,
    });

    expect(fieldById('k8s_resource_kind').depChange(
      KUBERNETES_STATE, ['k8s_resource_kind'])).toEqual({
      k8s_resource_name: null,
    });
  });

  it('preselects the port of the chosen service or pod', ()=>{
    expect(fieldById('k8s_resource_name').depChange(
      KUBERNETES_STATE, ['k8s_resource_name'])).toEqual({port: 5433});
  });

  it('hides what the cluster supplies or what cannot apply', ()=>{
    for(const id of ['password', 'save_password', 'service', 'kerberos_conn',
      'passexec_cmd', 'passexec_expiration']) {
      expect(evaluate({id, name: 'visible'}, KUBERNETES_STATE)).toBe(false);
      expect(evaluate({id, name: 'visible'}, {kubernetes_conn: false}))
        .toBe(true);
    }
  });

  it('hides the resolved username and database only while registering', ()=>{
    for(const id of ['username', 'db']) {
      expect(evaluate({id, name: 'visible'}, KUBERNETES_STATE)).toBe(false);
      expect(evaluate({id, name: 'visible'}, {...KUBERNETES_STATE, id: 1}))
        .toBe(true);
      expect(evaluate({id, name: 'readonly'}, {...KUBERNETES_STATE, id: 1}))
        .toBe(true);
    }
  });

  it('will not let a Kubernetes connection be shared', ()=>{
    /* Sharing is only ever offered to an admin in server mode, so put both
     * in place before checking that Kubernetes still withholds it. */
    const current_user = require('pgadmin.user_management.current_user');
    const previousAdmin = current_user.is_admin;
    const previousMode = pgAdmin.server_mode;
    current_user.is_admin = true;
    pgAdmin.server_mode = 'True';

    try {
      expect(evaluate({id: 'shared', name: 'visible'},
        {kubernetes_conn: false})).toBe(true);
      expect(evaluate({id: 'shared', name: 'visible'}, KUBERNETES_STATE))
        .toBe(false);
    } finally {
      current_user.is_admin = previousAdmin;
      pgAdmin.server_mode = previousMode;
    }
  });

  it('disables SSH tunnelling, which has nothing left to reach', ()=>{
    expect(evaluate({id: 'use_ssh_tunnel', name: 'disabled'},
      KUBERNETES_STATE)).toBe(true);
    expect(evaluate({id: 'use_ssh_tunnel', name: 'disabled'},
      {kubernetes_conn: false})).toBe(false);
  });

  it('locks the contract while the server is connected', ()=>{
    for(const id of ['k8s_context', 'k8s_namespace', 'k8s_resource_kind',
      'k8s_resource_name', 'k8s_username_ref', 'k8s_password_ref',
      'k8s_database_ref']) {
      expect(evaluate({id, name: 'readonly'}, KUBERNETES_STATE)).toBe(false);
      expect(evaluate({id, name: 'readonly'},
        {...KUBERNETES_STATE, connected: true})).toBe(true);
      /* Meaningless until the switch is on. */
      expect(evaluate({id, name: 'readonly'}, {kubernetes_conn: false}))
        .toBe(true);
    }
  });

  it('validates the contract instead of the host and credentials', ()=>{
    let setError = jest.fn();

    const missing = [
      ['k8s_context', 'Kubernetes context must be selected.'],
      ['k8s_namespace', 'Namespace must be selected.'],
      ['k8s_resource_name', 'A service or pod must be selected.'],
      ['port', 'The port to forward must be selected.'],
      ['k8s_username_ref', 'A username source must be selected.'],
      ['k8s_database_ref', 'A database source must be selected.'],
    ];

    let state = {gid: 1, kubernetes_conn: true};
    for(const [field, message] of missing) {
      expect(schemaObj.validate(state, setError)).toBe(true);
      expect(setError).toHaveBeenCalledWith(field, message);
      state[field] = KUBERNETES_STATE[field];
    }

    /* A server with no password at all is a valid contract. */
    expect(schemaObj.validate(state, setError)).toBe(false);

    /* None of the plain-connection requirements should have fired. */
    expect(setError).toHaveBeenCalledWith('host', null);
    expect(setError).toHaveBeenCalledWith('username', null);
    expect(setError).toHaveBeenCalledWith('db', null);
    expect(setError).not.toHaveBeenCalledWith(
      'host', 'Either Host name or Service must be specified.');
  });
});
