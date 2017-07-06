# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# Copyright 2012 Red Hat, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from oslo_cache import core as cache
from oslo_config import cfg
from oslo_db import options
from oslo_log import log
from oslo_middleware import cors


CONF = cfg.CONF


# NOTE(mikal): suds is used by the vmware driver, removing this will
# cause many extraneous log lines for their tempest runs. Refer to
# https://review.openstack.org/#/c/219225/ for details.
_DEFAULT_LOG_LEVELS = ['amqp=WARN', 'amqplib=WARN', 'boto=WARN',
                       'qpid=WARN', 'sqlalchemy=WARN', 'suds=INFO',
                       'oslo_messaging=INFO', 'iso8601=WARN',
                       'requests.packages.urllib3.connectionpool=WARN',
                       'urllib3.connectionpool=WARN', 'websocket=WARN',
                       'keystonemiddleware=WARN', 'routes.middleware=WARN',
                       'stevedore=WARN', 'glanceclient=WARN']

_DEFAULT_LOGGING_CONTEXT_FORMAT = ('%(asctime)s.%(msecs)03d %(process)d '
                                   '%(levelname)s %(name)s [%(request_id)s '
                                   '%(user_identity)s] %(instance)s'
                                   '%(message)s')


def parse_args(argv, default_config_files=None, configure_db=True,
               init_rpc=True):
    log.set_defaults(_DEFAULT_LOGGING_CONTEXT_FORMAT, _DEFAULT_LOG_LEVELS)
    log.register_options(CONF)
    cache.configure(CONF)
    set_middleware_defaults()

    CONF(argv[1:],
         project='fastrunner',
         default_config_files=default_config_files)



def set_middleware_defaults():
    """Update default configuration options for oslo.middleware."""
    # CORS Defaults
    # TODO(krotscheck): Update with https://review.openstack.org/#/c/285368/
    cfg.set_defaults(cors.CORS_OPTS,
                     allow_headers=['X-Auth-Token',
                                    'X-Openstack-Request-Id',
                                    'X-Identity-Status',
                                    'X-Roles',
                                    'X-Service-Catalog',
                                    'X-User-Id',
                                    'X-Tenant-Id'],
                     expose_headers=['X-Auth-Token',
                                     'X-Openstack-Request-Id',
                                     'X-Subject-Token',
                                     'X-Service-Token'],
                     allow_methods=['GET',
                                    'PUT',
                                    'POST',
                                    'DELETE',
                                    'PATCH']
                     )
