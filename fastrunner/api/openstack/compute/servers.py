# Copyright 2010 OpenStack Foundation
# Copyright 2011 Piston Cloud Computing, Inc
# All Rights Reserved.
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

import base64
import re

from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging as messaging
from oslo_utils import strutils
from oslo_utils import timeutils
from oslo_utils import uuidutils
import six
import stevedore
import webob
from webob import exc
from sqlalchemy import *
import redis


from fastrunner.api.openstack import extensions
from fastrunner.api.openstack import wsgi
from fastrunner.api import validation
from fastrunner import exception
from fastrunner.i18n import _
from fastrunner.i18n import _LW
from fastrunner import utils

ALIAS = 'servers'

CONF = cfg.CONF
CONF.import_opt('extensions_blacklist', 'fastrunner.api.openstack',
                group='osapi_v21')
CONF.import_opt('extensions_whitelist', 'fastrunner.api.openstack',
                group='osapi_v21')

LOG = logging.getLogger(__name__)
authorize = extensions.os_compute_authorizer(ALIAS)


class ServersController(wsgi.Controller):
    """The Server API base controller class for the OpenStack API."""


    @staticmethod
    def _add_location(robj):
        # Just in case...
        if 'server' not in robj.obj:
            return robj

        link = [l for l in robj.obj['server']['links'] if l['rel'] == 'self']
        if link:
            robj['Location'] = utils.utf8(link[0]['href'])

        # Convenience return
        return robj

    def __init__(self, **kwargs):
        self.extension_info = kwargs.pop('extension_info')
        super(ServersController, self).__init__(**kwargs)

    @extensions.expected_errors((400, 403))
    def index(self, req):
        """Returns a list of server names and ids for a given user."""
        context = req.environ['fastrunner.context']
        authorize(context, action="index")

        LOG.info("TODO index")

    @extensions.expected_errors((400, 403))
    def detail(self, req):
	"""Returns a list of server details for a given user."""
        context = req.environ['fastrunner.context']
        authorize(context, action="detail")

        search_opts = {}
        search_opts.update(req.GET)

        all_tenants = self._is_all_tenants(search_opts)
        if all_tenants:
            authorize(context, action="detail:get_all_tenants")
            

        LOG.info("=========detail() started=======")

        project_id = req.environ['HTTP_X_PROJECT_ID']
        LOG.debug("type:%s" %(req.environ['HTTP_X_PROJECT_ID']))

        r_redis = redis.StrictRedis(host='localhost', port=6379, db=0)
        LOG.info("redis connected!")

        uuids = r_redis.smembers("projects:%s" %(project_id))
        LOG.info("redis test: %s" %(uuids))

        for uuid in uuids:
            instance = r_redis.hgetall("instances:%s" %(uuid))

        LOG.info("=========detail() end=======")
        return instance

    def _is_all_tenants(self, search_opts):
        """Checks to see if the all_tenants flag is in search_opts
    
        :param dict search_opts: The search options for a request
        :returns: boolean indicating if all_tenants are being requested or not
        """
        all_tenants = search_opts.get('all_tenants')
        if all_tenants:
            try:
                all_tenants = strutils.bool_from_string(all_tenants, True)
            except ValueError as err:
                raise exception.InvalidInput(six.text_type(err))
        else:
            # The empty string is considered enabling all_tenants
            all_tenants = 'all_tenants' in search_opts
        return all_tenants


    @extensions.expected_errors(404)
    def show(self, req, id):
        """Returns server details by server id."""
        context = req.environ['fastrunner.context']
        authorize(context, action="show")
  
        LOG.info("TODO show")



def remove_invalid_options(context, search_options, allowed_search_options):
    """Remove search options that are not valid for non-admin API/context."""
    if context.is_admin:
        # Only remove parameters for sorting and pagination
        for key in ('sort_key', 'sort_dir', 'limit', 'marker'):
            search_options.pop(key, None)
        return
    # Otherwise, strip out all unknown options
    unknown_options = [opt for opt in search_options
                        if opt not in allowed_search_options]
    if unknown_options:
        LOG.debug("Removing options '%s' from query",
                  ", ".join(unknown_options))
        for opt in unknown_options:
            search_options.pop(opt, None)


class Servers(extensions.V21APIExtensionBase):
    """Servers."""

    name = "Servers"
    alias = ALIAS
    version = 1

    def get_resources(self):
        member_actions = {'action': 'POST'}
        collection_actions = {'detail': 'GET'}
        resources = [
            extensions.ResourceExtension(
                ALIAS,
                ServersController(extension_info=self.extension_info),
                member_name='server', collection_actions=collection_actions,
                member_actions=member_actions)]

        return resources

    def get_controller_extensions(self):
        return []
