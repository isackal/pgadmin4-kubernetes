/////////////////////////////////////////////////////////////
//
// pgAdmin 4 - PostgreSQL Tools
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import axios from 'axios';
import MockAdapter from 'axios-mock-adapter';

import {
  clearKubernetesOptionsCache,
  getCachedKubernetesResourcePorts,
  getKubernetesContexts,
  getKubernetesNamespaces,
  getKubernetesResourcePorts,
  getKubernetesResources,
  getKubernetesSources,
} from '../../../pgadmin/browser/server_groups/servers/static/js/kubernetes_options';

describe('kubernetes_options', ()=>{
  let networkMock;

  beforeEach(()=>{
    networkMock = new MockAdapter(axios);
    clearKubernetesOptionsCache();
  });

  afterEach(()=>{
    networkMock.restore();
  });

  it('marks the active context', async ()=>{
    networkMock.onGet('/browser/server/kubernetes_contexts').reply(200, [
      {name: 'kind-dbviewer', is_current: true},
      {name: 'staging', is_current: false},
    ]);

    expect(await getKubernetesContexts()).toEqual([
      {label: 'kind-dbviewer (current)', value: 'kind-dbviewer'},
      {label: 'staging', value: 'staging'},
    ]);
  });

  it('does not call out until the level above it is answered', async ()=>{
    expect(await getKubernetesNamespaces(undefined)).toEqual([]);
    expect(await getKubernetesResources('ctx', undefined, 'service'))
      .toEqual([]);
    expect(await getKubernetesSources('ctx', undefined)).toEqual([]);
    expect(networkMock.history.get).toHaveLength(0);
  });

  it('passes the selected context and namespace as query params', async ()=>{
    networkMock.onGet('/browser/server/kubernetes_namespaces')
      .reply(200, ['default', 'pg-standard']);

    expect(await getKubernetesNamespaces('kind-dbviewer')).toEqual([
      {label: 'default', value: 'default'},
      {label: 'pg-standard', value: 'pg-standard'},
    ]);
    expect(networkMock.history.get[0].params)
      .toEqual({context: 'kind-dbviewer'});
  });

  it('flags a resource that cannot be forwarded to', async ()=>{
    networkMock.onGet('/browser/server/kubernetes_resources').reply(200, [
      {name: 'postgres', ready: true, ports: [{port: 5432, name: null}]},
      {name: 'restarting', ready: false, ports: []},
    ]);

    expect(await getKubernetesResources('ctx', 'ns', 'pod')).toEqual([
      {label: 'postgres', value: 'postgres'},
      {label: 'restarting (not ready)', value: 'restarting'},
    ]);
  });

  it('lists the ports of the chosen resource only', async ()=>{
    networkMock.onGet('/browser/server/kubernetes_resources').reply(200, [
      {name: 'postgres', ready: true, ports: [
        {port: 5433, name: 'postgresql'},
        {port: 9187, name: null},
      ]},
      {name: 'other', ready: true, ports: [{port: 1234, name: null}]},
    ]);

    expect(await getKubernetesResourcePorts('ctx', 'ns', 'service', 'postgres'))
      .toEqual([
        {label: '5433 (postgresql)', value: 5433},
        {label: '9187', value: 9187},
      ]);
  });

  it('serves ports from cache so preselecting one costs no request',
    async ()=>{
      networkMock.onGet('/browser/server/kubernetes_resources').reply(200, [
        {name: 'postgres', ready: true, ports: [{port: 5432, name: null}]},
      ]);

      /* Nothing has been fetched yet, so there is nothing to preselect. */
      expect(
        getCachedKubernetesResourcePorts('ctx', 'ns', 'service', 'postgres')
      ).toEqual([]);

      await getKubernetesResources('ctx', 'ns', 'service');

      expect(
        getCachedKubernetesResourcePorts('ctx', 'ns', 'service', 'postgres')
      ).toEqual([{label: '5432', value: 5432}]);
      expect(networkMock.history.get).toHaveLength(1);
    });

  it('flattens secrets and config maps into one reference list', async ()=>{
    networkMock.onGet('/browser/server/kubernetes_sources').reply(200, [
      {kind: 'secret', name: 'pg-standard-credentials',
        keys: ['database', 'password', 'username']},
      {kind: 'configmap', name: 'pg-settings', keys: ['dbname']},
    ]);

    expect(await getKubernetesSources('ctx', 'pg-standard')).toEqual([
      {label: 'secret/pg-standard-credentials/database',
        value: 'secret/pg-standard-credentials/database'},
      {label: 'secret/pg-standard-credentials/password',
        value: 'secret/pg-standard-credentials/password'},
      {label: 'secret/pg-standard-credentials/username',
        value: 'secret/pg-standard-credentials/username'},
      {label: 'configmap/pg-settings/dbname',
        value: 'configmap/pg-settings/dbname'},
    ]);
  });

  it('surfaces the cluster error rather than an empty dropdown', async ()=>{
    networkMock.onGet('/browser/server/kubernetes_namespaces').reply(400, {
      errormsg: 'Not authorised to list namespaces in the cluster.',
    }, {'content-type': 'application/json'});

    await expect(getKubernetesNamespaces('ctx')).rejects.toThrow(
      'Not authorised to list namespaces in the cluster.');
  });
});
