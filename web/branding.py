##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

##########################################################################
# Application branding
##########################################################################

# Name of the application to display in the UI
#
# pgAdminK is a fork of pgAdmin 4 that adds Kubernetes connections. It is
# deliberately branded as a separate application: an install must not be
# mistaken for upstream pgAdmin, and more importantly must not share state
# with one. See APP_SHORT_NAME and APP_PATH below.
APP_NAME = 'pgAdminK'
APP_ICON = 'pg-icon'

# To help define the configuration directory and data directory
#
# These MUST differ from upstream pgAdmin's 'pgadmin4' / 'pgadmin'. They pick
# the data directory (~/.pgadmink, /var/lib/pgadmink, %APPDATA%\pgAdminK) and
# the name of the SQLite configuration database inside it. Sharing those with
# an upstream install would mean sharing one pgadmin4.db between two apps with
# different schemas - this fork adds a migration upstream does not have, so it
# would be applied to their database as well.
APP_SHORT_NAME = 'pgadmink'
APP_PATH = 'pgadmink'
APP_WIN_PATH = "pgAdminK"

# Copyright string for display in the app
APP_COPYRIGHT = 'Based on pgAdmin 4, Copyright (C) 2013 - 2026, ' \
                'The pgAdmin Development Team'

# User ID (email address) to use for the default user in desktop mode.
# The default should be fine here, as it's not exposed in the app.
APP_DEFAULT_EMAIL = 'pgadmin4@pgadmin.org'
