##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Kubernetes server connections

Adds the connection contract for servers reached through a Kubernetes port
forward: which context, namespace and workload to forward to, and which
Secret or ConfigMap keys hold the username, password and database name.

The forwarded local port is deliberately not stored - it is allocated fresh
every time the server connects.  `host` holds the local host name the user
picked and `port` the port exposed by the service or pod.

Revision ID: kubernetes_server_conn
Revises: normalize_locked_text_default
Create Date: 2026-08-13

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'kubernetes_server_conn'
down_revision = 'normalize_locked_text_default'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    existing_cols = {c['name'] for c in inspector.get_columns('server')}

    new_columns = [
        ('kubernetes_conn',
         sa.Column('kubernetes_conn', sa.Integer(), nullable=False,
                   server_default='0')),
        ('k8s_context',
         sa.Column('k8s_context', sa.String(256), nullable=True)),
        ('k8s_namespace',
         sa.Column('k8s_namespace', sa.String(256), nullable=True)),
        ('k8s_resource_kind',
         sa.Column('k8s_resource_kind', sa.String(16), nullable=True)),
        ('k8s_resource_name',
         sa.Column('k8s_resource_name', sa.String(256), nullable=True)),
        ('k8s_username_ref',
         sa.Column('k8s_username_ref', sa.String(512), nullable=True)),
        ('k8s_password_ref',
         sa.Column('k8s_password_ref', sa.String(512), nullable=True)),
        ('k8s_database_ref',
         sa.Column('k8s_database_ref', sa.String(512), nullable=True)),
    ]

    cols_to_add = [col for name, col in new_columns
                   if name not in existing_cols]

    if cols_to_add:
        with op.batch_alter_table('server') as batch_op:
            for col in cols_to_add:
                batch_op.add_column(col)


def downgrade():
    # pgAdmin only upgrades, downgrade not implemented.
    pass
