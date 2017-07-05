# Copyright 2013 IBM Corp.
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

import copy

from oslo_log import log as logging
import six
import webob.exc

from fastrunner.api.openstack import extensions
from fastrunner.api.openstack import wsgi
from fastrunner import exception
from fastrunner.i18n import _LE

ALIAS = 'extensions'
LOG = logging.getLogger(__name__)
authorize = extensions.os_compute_authorizer(ALIAS)

# NOTE(cyeoh): The following mappings are currently incomplete
# Having a v2.1 extension loaded can imply that several v2 extensions
# should also appear to be loaded (although they no longer do in v2.1)
v21_to_v2_extension_list_mapping = {
    'os-quota-sets': [{'name': 'UserQuotas', 'alias': 'os-user-quotas'},
                      {'name': 'ExtendedQuotas',
                       'alias': 'os-extended-quotas'}],
    'os-cells': [{'name': 'CellCapacities', 'alias': 'os-cell-capacities'}],
    'os-baremetal-nodes': [{'name': 'BareMetalExtStatus',
                            'alias': 'os-baremetal-ext-status'}],
    'os-block-device-mapping': [{'name': 'BlockDeviceMappingV2Boot',
                                 'alias': 'os-block-device-mapping-v2-boot'}],
    'os-cloudpipe': [{'name': 'CloudpipeUpdate',
                      'alias': 'os-cloudpipe-update'}],
    'servers': [{'name': 'Createserverext', 'alias': 'os-create-server-ext'},
                {'name': 'ExtendedIpsMac', 'alias': 'OS-EXT-IPS-MAC'},
                {'name': 'ExtendedIps', 'alias': 'OS-EXT-IPS'},
                {'name': 'ServerListMultiStatus',
                 'alias': 'os-server-list-multi-status'},
                {'name': 'ServerSortKeys', 'alias': 'os-server-sort-keys'},
                {'name': 'ServerStartStop', 'alias': 'os-server-start-stop'}],
    'flavors': [{'name': 'FlavorDisabled', 'alias': 'OS-FLV-DISABLED'},
                {'name': 'FlavorExtraData', 'alias': 'OS-FLV-EXT-DATA'},
                {'name': 'FlavorSwap', 'alias': 'os-flavor-swap'}],
    'os-services': [{'name': 'ExtendedServicesDelete',
                     'alias': 'os-extended-services-delete'},
                    {'name': 'ExtendedServices', 'alias':
                     'os-extended-services'}],
    'os-evacuate': [{'name': 'ExtendedEvacuateFindHost',
                     'alias': 'os-extended-evacuate-find-host'}],
    'os-floating-ips': [{'name': 'ExtendedFloatingIps',
                     'alias': 'os-extended-floating-ips'}],
    'os-hypervisors': [{'name': 'ExtendedHypervisors',
                     'alias': 'os-extended-hypervisors'},
                     {'name': 'HypervisorStatus',
                     'alias': 'os-hypervisor-status'}],
    'os-networks': [{'name': 'ExtendedNetworks',
                     'alias': 'os-extended-networks'}],
    'os-rescue': [{'name': 'ExtendedRescueWithImage',
                   'alias': 'os-extended-rescue-with-image'}],
    'os-extended-status': [{'name': 'ExtendedStatus',
                   'alias': 'OS-EXT-STS'}],
    'os-used-limits': [{'name': 'UsedLimitsForAdmin',
                        'alias': 'os-used-limits-for-admin'}],
    'os-volumes': [{'name': 'VolumeAttachmentUpdate',
                    'alias': 'os-volume-attachment-update'}],
    'os-server-groups': [{'name': 'ServerGroupQuotas',
                    'alias': 'os-server-group-quotas'}],
}

# v2.1 plugins which should never appear in the v2 extension list
# This should be the v2.1 alias, not the V2.0 alias
v2_extension_suppress_list = ['servers', 'images', 'versions', 'flavors',
                              'os-block-device-mapping-v1', 'os-consoles',
                              'extensions', 'image-metadata', 'ips', 'limits',
                              'server-metadata', 'server-migrations'
                            ]

# v2.1 plugins which should appear under a different name in v2
v21_to_v2_alias_mapping = {
    'image-size': 'OS-EXT-IMG-SIZE',
    'os-remote-consoles': 'os-consoles',
    'os-disk-config': 'OS-DCF',
    'os-extended-availability-zone': 'OS-EXT-AZ',
    'os-extended-server-attributes': 'OS-EXT-SRV-ATTR',
    'os-multinic': 'NMN',
    'os-scheduler-hints': 'OS-SCH-HNT',
    'os-server-usage': 'OS-SRV-USG',
    'os-instance-usage-audit-log': 'os-instance_usage_audit_log',
}

# V2.1 does not support XML but we need to keep an entry in the
# /extensions information returned to the user for backwards
# compatibility
FAKE_XML_URL = "http://docs.openstack.org/compute/ext/fake_xml"
FAKE_UPDATED_DATE = "2014-12-03T00:00:00Z"

class ExtensionInfo(extensions.V21APIExtensionBase):
    """Extension information."""

    name = "Extensions"
    alias = ALIAS
    version = 1

    def get_resources(self):
        resources = [
            extensions.ResourceExtension(
                ALIAS, ExtensionInfoController(self.extension_info),
                member_name='extension')]
        return resources

    def get_controller_extensions(self):
        return []


class LoadedExtensionInfo(object):
    """Keep track of all loaded API extensions."""

    def __init__(self):
        self.extensions = {}

    def register_extension(self, ext):
        if not self._check_extension(ext):
            return False

        alias = ext.alias

        if alias in self.extensions:
            raise exception.FastrunnerException("Found duplicate extension: %s"
                                          % alias)
        self.extensions[alias] = ext
        return True

    def _check_extension(self, extension):
        """Checks for required methods in extension objects."""
        try:
            extension.is_valid()
        except AttributeError:
            LOG.exception(_LE("Exception loading extension"))
            return False

        return True

    def get_extensions(self):
        return self.extensions
