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
#        self.api = compute.API()


    @extensions.expected_errors((400, 403))
    def index(self, req):
        """Returns a list of server names and ids for a given user."""
        context = req.environ['fastrunner.context']
        authorize(context, action="index")
 #       try:
 #           servers = self._get_servers(req, is_detail=False)
 #       except exception.Invalid as err:
 #           raise exc.HTTPBadRequest(explanation=err.format_message())
 #       return servers


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

        context = req.environ['fastrunner.context']
       # remove_invalid_options(context, search_opts,
       #        self._get_server_search_options(req))

	search_opts.pop('status', None)
        if 'status' in req.GET.keys():
            statuses = req.GET.getall('status')

        if 'changes-since' in search_opts:
            try:
                parsed = timeutils.parse_isotime(search_opts['changes-since'])
            except ValueError:
                msg = _('Invalid changes-since value')
                raise exc.HTTPBadRequest(explanation=msg)
            search_opts['changes-since'] = parsed

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

       	#TODO 
	#all_tenants = common.is_all_tenants(search_opts)
        all_tenants = False

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

	#TODO
        #limit, marker = common.get_limit_and_marker(req)
        #sort_keys, sort_dirs = common.get_sort_params(req.params)


	engine = create_engine('mysql://nova:redhat@localhost:3306/nova', echo=False)
	metadata = MetaData(engine, reflect=True)
        conn = engine.connect()

        table = metadata.tables['instances']
	
	select_str = select([
	    table.c.hostname,
	    table.c.task_state,
	    table.c.uuid,
	    table.c.image_ref,
	    table.c.availability_zone,
	    table.c.host,
	    table.c.project_id,
	    table.c.user_id,
	    table.c.updated_at,
	    table.c.power_state,
	    table.c.vm_state]).where(
		table.c.project_id == "%s" %(context.project_id))
	#select_str = select([table])
	print select_str
        instances = conn.execute(select_str)
	
	filled_instances = []
	for instance in instances:
	    instance = {
		'name':instance['hostname'],
		'OS-EXT-STS:power_state':instance['power_state'],
		'OS-EXT-STS:task_state':instance['task_state'],
		'id':instance['uuid'],
		'OS-EXT-AZ:availability_zone':instance['availability_zone'],
		'OS-EXT-SRV-ATTR:host':instance['host'],
		'tenant_id':instance['project_id']}

	    filled_instances.append(instance)

	return {'servers':filled_instances}

	if is_detail:
 	    expected_attrs.append('services')
	    if api_version_request.is_supported(req, '2.26'):
	        expected_attrs.append('tags')

	    expected_attrs = ['flavor', 'info_cache', 'metadata'] + expected_attrs

	try:
            instance_list = self.get_all(elevated or context,
                    search_opts=search_opts, limit=limit, marker=marker,
                    want_objects=True, expected_attrs=expected_attrs,
                    sort_keys=sort_keys, sort_dirs=sort_dirs)
        except exception.MarkerNotFound:
            msg = _('marker [%s] not found') % marker
            raise exc.HTTPBadRequest(explanation=msg)
        except exception.FlavorNotFound:
            LOG.debug("Flavor '%s' could not be found ",
                      search_opts['flavor'])
            instance_list = []
	response = dict(instance_list)
	return response 


    def get_all(self, context, search_opts=None, limit=None, marker=None,
                want_objects=False, expected_attrs=None, sort_keys=None,
                sort_dirs=None):
        """Get all instances filtered by one of the given parameters.

        If there is no filter and the context is an admin, it will retrieve
        all instances in the system.

        Deleted instances will be returned by default, unless there is a
        search option that says otherwise.

        The results will be sorted based on the list of sort keys in the
        'sort_keys' parameter (first value is primary sort key, second value is
        secondary sort ket, etc.). For each sort key, the associated sort
        direction is based on the list of sort directions in the 'sort_dirs'
        parameter.
        """
        
	if search_opts is None:
            search_opts = {}

        LOG.debug("Searching by: %s", str(search_opts))

        # Fixups for the DB call
        filters = {}

        def _remap_flavor_filter(flavor_id):
            flavor = objects.Flavor.get_by_flavor_id(context, flavor_id)
            filters['instance_type_id'] = flavor.id

        def _remap_fixed_ip_filter(fixed_ip):
            # Turn fixed_ip into a regexp match. Since '.' matches
            # any character, we need to use regexp escaping for it.
            filters['ip'] = '^%s$' % fixed_ip.replace('.', '\\.')

        def _remap_metadata_filter(metadata):
            filters['metadata'] = jsonutils.loads(metadata)

        def _remap_system_metadata_filter(metadata):
            filters['system_metadata'] = jsonutils.loads(metadata)

        # search_option to filter_name mapping.
        filter_mapping = {
                'image': 'image_ref',
                'name': 'display_name',
                'tenant_id': 'project_id',
                'flavor': _remap_flavor_filter,
                'fixed_ip': _remap_fixed_ip_filter,
                'metadata': _remap_metadata_filter,
                'system_metadata': _remap_system_metadata_filter}

        # copy from search_opts, doing various remappings as necessary
        for opt, value in six.iteritems(search_opts):
            # Do remappings.
            # Values not in the filter_mapping table are copied as-is.
            # If remapping is None, option is not copied
            # If the remapping is a string, it is the filter_name to use
            try:
                remap_object = filter_mapping[opt]
            except KeyError:
                filters[opt] = value
            else:
                # Remaps are strings to translate to, or functions to call
                # to do the translating as defined by the table above.
                if isinstance(remap_object, six.string_types):
                    filters[remap_object] = value
                else:
                    try:
                        remap_object(value)

                    # We already know we can't match the filter, so
                    # return an empty list
                    except ValueError:
                        if want_objects:
                            return objects.InstanceList()
                        else:
                            return []

        # IP address filtering cannot be applied at the DB layer, remove any DB
        # limit so that it can be applied after the IP filter.
        filter_ip = 'ip6' in filters or 'ip' in filters
        orig_limit = limit
        if filter_ip and limit:
            LOG.debug('Removing limit for DB query due to IP filter')
            limit = None


	fields = ['metadata', 'system_metadata', 'info_cache', 'security_groups']

	if expected_attrs:
	    fields.extend(expected_attrs)

	expected_attrs = fields
	
	func = self._get_expected_columns_method(search_opts['level'])
	expected_columns = getattr(self, func)()
	
	db_inst_lsit = db.instance_get_all_by_filters_sort(context, ) 



        inst_models = self._get_instances_by_filters(context, filters,
                limit=limit, marker=marker, expected_attrs=expected_attrs,
                sort_keys=sort_keys, sort_dirs=sort_dirs)

        if filter_ip:
            inst_models = self._ip_filter(inst_models, filters, orig_limit)

        if want_objects:
            return inst_models

        # Convert the models to dictionaries
        instances = []
        for inst_model in inst_models:
            instances.append(obj_base.obj_to_primitive(inst_model))

        return instances



    def _get_server(self, context, req, instance_uuid, is_detail=False):
        """Utility function for looking up an instance by uuid.

        :param context: request context for auth
        :param req: HTTP request. The instance is cached in this request.
        :param instance_uuid: UUID of the server instance to get
        :param is_detail: True if you plan on showing the details of the
            instance in the response, False otherwise.
        """
        expected_attrs = ['flavor', 'pci_devices', 'numa_topology']
        if is_detail:
            expected_attrs = self._view_builder.get_show_expected_attrs(
                                                            expected_attrs)
        instance = common.get_instance(self.compute_api, context,
                                       instance_uuid,
                                       expected_attrs=expected_attrs)
        req.cache_db_instance(instance)
        return instance

    def _get_requested_networks(self, requested_networks):
        """Create a list of requested networks from the networks attribute."""
        networks = []
        network_uuids = []
        for network in requested_networks:
            request = objects.NetworkRequest()
            try:
                # fixed IP address is optional
                # if the fixed IP address is not provided then
                # it will use one of the available IP address from the network
                request.address = network.get('fixed_ip', None)
                request.port_id = network.get('port', None)

                if request.port_id:
                    request.network_id = None
                    if not utils.is_neutron():
                        # port parameter is only for neutron v2.0
                        msg = _("Unknown argument: port")
                        raise exc.HTTPBadRequest(explanation=msg)
                    if request.address is not None:
                        msg = _("Specified Fixed IP '%(addr)s' cannot be used "
                                "with port '%(port)s': port already has "
                                "a Fixed IP allocated.") % {
                                    "addr": request.address,
                                    "port": request.port_id}
                        raise exc.HTTPBadRequest(explanation=msg)
                else:
                    request.network_id = network['uuid']

                if (not request.port_id and
                        not uuidutils.is_uuid_like(request.network_id)):
                    br_uuid = request.network_id.split('-', 1)[-1]
                    if not uuidutils.is_uuid_like(br_uuid):
                        msg = _("Bad networks format: network uuid is "
                                "not in proper format "
                                "(%s)") % request.network_id
                        raise exc.HTTPBadRequest(explanation=msg)

                # duplicate networks are allowed only for neutron v2.0
                if (not utils.is_neutron() and request.network_id and
                        request.network_id in network_uuids):
                    expl = (_("Duplicate networks"
                              " (%s) are not allowed") %
                            request.network_id)
                    raise exc.HTTPBadRequest(explanation=expl)
                network_uuids.append(request.network_id)
                networks.append(request)
            except KeyError as key:
                expl = _('Bad network format: missing %s') % key
                raise exc.HTTPBadRequest(explanation=expl)
            except TypeError:
                expl = _('Bad networks format')
                raise exc.HTTPBadRequest(explanation=expl)

        return objects.NetworkRequestList(objects=networks)

    def _get_server_admin_password(self, server):
        """Determine the admin password for a server on creation."""
        try:
            password = server['adminPass']
        except KeyError:
            password = utils.generate_password()
        return password

    def _get_server_search_options(self, req):
        """Return server search options allowed by non-admin."""
        opt_list = ('reservation_id', 'name', 'status', 'image', 'flavor',
                    'ip', 'changes-since', 'all_tenants')
        if api_version_request.is_supported(req, min_version='2.5'):
            opt_list += ('ip6',)
        return opt_list

    def _get_instance(self, context, instance_uuid):
        try:
            attrs = ['system_metadata', 'metadata']
            return objects.Instance.get_by_uuid(context, instance_uuid,
                                                expected_attrs=attrs)
        except exception.InstanceNotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.format_message())





    # NOTE(vish): Without this regex, b64decode will happily
    #             ignore illegal bytes in the base64 encoded
    #             data.
    B64_REGEX = re.compile('^(?:[A-Za-z0-9+\/]{4})*'
                           '(?:[A-Za-z0-9+\/]{2}=='
                           '|[A-Za-z0-9+\/]{3}=)?$')

    def _decode_base64(self, data):
        data = re.sub(r'\s', '', data)
        if not self.B64_REGEX.match(data):
            return None
        try:
            return base64.b64decode(data)
        except TypeError:
            return None

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
