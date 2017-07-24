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
import json

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

from nova.api.openstack import common
#from fastrunner import extension
#from nova.api.openstack.compute.views import servers as views_servers

from fastrunner.api.openstack import extensions
from fastrunner.api.openstack import db
#from fastrunner import db
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

#CONF.import_opt('connection', 'fastrunner.api.openstack', group='database')


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
#        self.api = extension.API()


    @extensions.expected_errors((400, 403))
    def index(self, req):
        """Returns a list of server names and ids for a given user."""
        context = req.environ['fastrunner.context']
        authorize(context, action="index")
        try:
            servers = self._get_servers(req, is_detail=False)
        except exception.Invalid as err:
            raise exc.HTTPBadRequest(explanation=err.format_message())
        return servers


    @extensions.expected_errors((400, 403))
    def detail(self, req):
        """Returns a list of server details for a given user."""

        context = req.environ['fastrunner.context']
        authorize(context, action="detail")
        try:
            servers = self._get_servers(req, is_detail=True)
        except exception.Invalid as err:
            raise exc.HTTPBadRequest(explanation=err.format_message())
        return servers


    def _get_servers(self, req, is_detail):
        """Returns a list of servers, based on any search options specified."""
        
        search_opts = {}
        search_opts.update(req.GET)
        LOG.info("=====TODO: handling more search options =======")
        
        context = req.environ['fastrunner.context']

        # all_tenant to boolean
        all_tenants = common.is_all_tenants(search_opts)

        if all_tenants:
            if is_detail:
                authorize(context, action="detail:get_all_tenants")
            else:
                authorize(context, action="index:get_all_tenants")
        else:
            if context.project_id:
                search_opts['project_id'] = context.project_id
            else:
                search_opts['user_id'] = context.user_id

        # limit, marker = common.get_limit_and_marker(req)
        # sort_keys, sort_dirs = common.get_sort_params(req.params)

        if is_detail:
            try:
                servers = db.instance_get_all(context, search_opts)
            except:
                pass
                LOG.info("==========TODO: handing db.instance_get_all() exceptions=========")
        else:
            pass
            LOG.info("=======TODO: _get_servers() for index==========")
        
        return servers
    
   
      
        filled_instances = []
        for instance in instances:
            status = common.status_from_state(instance['vm_state'], instance['task_state'])
            #flavor = json.JSONDecoder().decode(instance['flavor'])['cur']['nova_object.data']
            #print flavor
            instance = {
                'status':status,
                'name':instance['hostname'],
                'id':instance['uuid'],
                'OS-EXT-STS:power_state':instance['power_state'],
                'OS-EXT-STS:task_state':instance['task_state'],
                'OS-EXT-AZ:availability_zone':instance['availability_zone'],
                'OS-EXT-SRV-ATTR:host':instance['host'],
                'OS-SRV-USG:created_at':instance['created_at'],
                'tenant_id':instance['project_id']}

            filled_instances.append(instance)

        return {'servers':filled_instances}


    def _get_servers_by_sqlalchemy_core(self, req, is_detail):
        """Returns a list of servers, based on any search options specified."""

        search_opts = {}
        search_opts.update(req.GET)
        context = req.environ['fastrunner.context']

        remove_invalid_options(context, search_opts, self._get_server_search_options(req))

        # Verify search by 'status' contains a valid status.
        # Convert it to filter by vm_state or task_state for compute_api.
        search_opts.pop('status', None)
        if 'status' in req.GET.keys():
            statuses = req.GET.getall('status')
            states = common.task_and_vm_state_from_status(statuses)
            vm_state, task_state = states
            if not vm_state and not task_state:
                return {'servers': []}
            search_opts['vm_state'] = vm_state
            # When we search by vm state, task state will return 'default'.
            # So we don't need task_state search_opt.
            if 'default' not in task_state:
                search_opts['task_state'] = task_state

        if 'changes-since' in search_opts:
            try:
                parsed = timeutils.parse_isotime(search_opts['changes-since'])
            except ValueError:
                msg = _('Invalid changes-since value')
                raise exc.HTTPBadRequest(explanation=msg)
            search_opts['changes-since'] = parsed

        # By default, compute's get_all() will return deleted instances.
        # If an admin hasn't specified a 'deleted' search option, we need
        # to filter out deleted instances by setting the filter ourselves.
        # ... Unless 'changes-since' is specified, because 'changes-since'
        # should return recently deleted instances according to the API spec.

        if 'deleted' not in search_opts:
            if 'changes-since' not in search_opts:
                # No 'changes-since', so we only want non-deleted servers
                search_opts['deleted'] = False
        else:
            # Convert deleted filter value to a valid boolean.
            # Return non-deleted servers if an invalid value
            # is passed with deleted filter.
            search_opts['deleted'] = strutils.bool_from_string(
                search_opts['deleted'], default=False)

        if search_opts.get("vm_state") == ['deleted']:
            if context.is_admin:
                search_opts['deleted'] = True
            else:
                msg = _("Only administrators may list deleted instances")
                raise exc.HTTPForbidden(explanation=msg)

        # If tenant_id is passed as a search parameter this should
        # imply that all_tenants is also enabled unless explicitly
        # disabled. Note that the tenant_id parameter is filtered out
        # by remove_invalid_options above unless the requestor is an
        # admin.

        # TODO(gmann): 'all_tenants' flag should not be required while
        # searching with 'tenant_id'. Ref bug# 1185290
        # +microversions to achieve above mentioned behavior by
        # uncommenting below code.

        # if 'tenant_id' in search_opts and 'all_tenants' not in search_opts:
            # We do not need to add the all_tenants flag if the tenant
            # id associated with the token is the tenant id
            # specified. This is done so a request that does not need
            # the all_tenants flag does not fail because of lack of
            # policy permission for compute:get_all_tenants when it
            # doesn't actually need it.
            # if context.project_id != search_opts.get('tenant_id'):
            #    search_opts['all_tenants'] = 1

        all_tenants = common.is_all_tenants(search_opts)
        # use the boolean from here on out so remove the entry from search_opts
        # if it's present
        search_opts.pop('all_tenants', None)

        elevated = None
        if all_tenants:
            if is_detail:
                authorize(context, action="detail:get_all_tenants")
            else:
                authorize(context, action="index:get_all_tenants")
            elevated = context.elevated()
        else:
            if context.project_id:
                search_opts['project_id'] = context.project_id
            else:
                search_opts['user_id'] = context.user_id

        limit, marker = common.get_limit_and_marker(req)
        sort_keys, sort_dirs = common.get_sort_params(req.params)

        expected_attrs = ['pci_devices']
        #if is_detail:
            # merge our expected attrs with what the view builder needs for
            # showing details
           # expected_attrs = self._view_builder.get_show_expected_attrs(
            #                                                    expected_attrs)
                
        connection = CONF.database.connection
        engine = create_engine(connection, echo=False)
        metadata = MetaData(engine, reflect=True)
        conn = engine.connect()

        instances_table = metadata.tables['instances']    
        instance_extra_table = metadata.tables['instance_extra']
       
        select_str = select([
            instances_table.c.hostname,
            instances_table.c.task_state,
            instances_table.c.uuid,
            instances_table.c.image_ref,
            instances_table.c.display_name,
            instance_extra_table.c.flavor,
            instances_table.c.availability_zone,
            instances_table.c.host,
            instances_table.c.project_id,
            instances_table.c.user_id,
            instances_table.c.created_at,
            instances_table.c.power_state,
            instances_table.c.vm_state]).select_from(
                instances_table.join(instance_extra_table,
                    instances_table.c.uuid==instance_extra_table.c.instance_uuid)).where(
                    instances_table.c.project_id == context.project_id)
        
        LOG.debug("%s" %(select_str))
        instances = conn.execute(select_str)
        f_instances =[]
        for instance in instances:
            f_instances.append(dict(instance))

        instances = f_instances

        #instances._context = context
       # instances.fill_faults()
        response = self._view_builder.detail(req, instances)
        return response

        filled_instances = []
        for instance in instances:
            status = common.status_from_state(instance['vm_state'], instance['task_state'])
            flavor = json.JSONDecoder().decode(instance['flavor'])['cur']['nova_object.data']
            print flavor
            instance = {
                'status':status,
                'name':instance['hostname'],
                'id':instance['uuid'],
                'OS-EXT-STS:power_state':instance['power_state'],
                'OS-EXT-STS:task_state':instance['task_state'],
                'OS-EXT-AZ:availability_zone':instance['availability_zone'],
                'flavor':{
                    'disk':flavor['ephemeral_gb'],
                    'vcpus':flavor['vcpus'],
                    'ram':flavor['memory_mb'],
                    'id':flavor['flavorid'],
                    'name':flavor['name']},
                'OS-EXT-SRV-ATTR:host':instance['host'],
                'OS-SRV-USG:created_at':instance['created_at'],
                'tenant_id':instance['project_id']}

            filled_instances.append(instance)

        return {'servers':filled_instances}


    @extensions.expected_errors(404)
    def show(self, req, id):
        """Returns server details by server id."""
        context = req.environ['nova.context']
        authorize(context, action="show")
        instance = self._get_server(context, req, id, is_detail=True)
        return self._view_builder.show(req, instance)
    # NOTE(gmann): Parameter 'req_body' is placed to handle scheduler_hint
    # extension for V2.1. No other extension supposed to use this as
    # it will be removed soon.


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


def _get_server_search_options(req):
    LOG.info("=========TODO=================")

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
