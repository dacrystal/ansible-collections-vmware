#
# Copyright: (c) 2018, Ansible Project
# Copyright: (c) 2018, Abhijeet Kasurde <akasurde@redhat.com>
#
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = r'''
    name: vmware_vm_inventory
    plugin_type: inventory
    short_description: VMware Guest inventory source
    version_added: "2.7"
    author:
      - Abhijeet Kasurde (@Akasurde)
    description:
        - Get virtual machines as inventory hosts from VMware environment.
        - Uses any file which ends with vmware.yml, vmware.yaml, vmware_vm_inventory.yml, or vmware_vm_inventory.yaml as a YAML configuration file.
    extends_documentation_fragment:
      - inventory_cache
      - constructed
    requirements:
      - "Python >= 2.7"
      - "PyVmomi"
      - "requests >= 2.3"
      - "vSphere Automation SDK - For tag feature"
      - "vCloud Suite SDK - For tag feature"
    options:
        hostname:
            description: Name of vCenter or ESXi server.
            required: True
            env:
              - name: VMWARE_HOST
              - name: VMWARE_SERVER
        username:
            description: Name of vSphere user.
            required: True
            env:
              - name: VMWARE_USER
              - name: VMWARE_USERNAME
        password:
            description: Password of vSphere user.
            required: True
            env:
              - name: VMWARE_PASSWORD
        port:
            description: Port number used to connect to vCenter or ESXi Server.
            default: 443
            env:
              - name: VMWARE_PORT
        validate_certs:
            description:
            - Allows connection when SSL certificates are not valid.
            - Set to C(false) when certificates are not trusted.
            default: True
            type: bool
            env:
              - name: VMWARE_VALIDATE_CERTS
        with_tags:
            description:
            - Include tags and associated virtual machines.
            - Requires 'vSphere Automation SDK' library to be installed on the given controller machine.
            - Please refer following URLs for installation steps
            - U(https://code.vmware.com/web/sdk/65/vsphere-automation-python)
            default: False
            type: bool
        properties:
            description:
            - Specify the list of VMware schema properties associated with the VM.
            - These properties will be populated in hostvars of the given VM.
            - Each value in the list can be a path to a specific property in VM object or a path to a collection of VM objects.
            - In addition to VM properties, the following are special values
            - Use 'customValue' to populate VM's custom attributes.
            - Use 'all' to populate all VM properties.
            type: list
            default: [ 'name', 'config.cpuHotAddEnabled', 'config.cpuHotRemoveEnabled',
                       'config.instanceUuid', 'config.hardware.numCPU', 'config.template',
                       'config.name', 'config.uuid' ,'guest.hostName', 'guest.ipAddress',
                       'guest.guestId', 'guest.guestState', 'runtime.maxMemoryUsage',
                       'customValue', 'summary.runtime.powerState', 'config.guestId'
                       ]
            version_added: "2.9"
        resources:
            description:
            - A list of resources to limit search scope.
            - Each resource item is represented by exactly one C('vim_type_snake_case):C(list of resource names) pair and optional nested I(resources)
            - Key name is based on snake case of a vim type name; e.g C(host_system) correspond to C(vim.HostSystem)
            - See  L(VIM Types,https://pubs.vmware.com/vi-sdk/visdk250/ReferenceGuide/index-mo_types.html)
            version_added: "2.10"
            required: False
            type: list
            default: []
        with_path:
            description:
            - Include virtual machines path.
            - Set this option to a string value to replace root name from I('Datacenters').
            default: False
            type: bool
            version_added: "2.10"
        hostnames:
            description:
                - A list of templates in order of precedence to compose inventory_hostname.
                - Ignores template if it resulted in an empty string or None value.
                - You can use property specified in I(properties) as variables in template.
            type: list
            default: ['config.name + "_" + config.uuid']
            version_added: "2.10"
        with_nested_properties:
            description:
                - This option transform flatten properties name to nested dictionary.
            type: bool
            default: False
            version_added: "2.10"
        with_sanitized_property_name:
            description:
                - This option allows property name sanitization to create safe property names for use in Ansible.
            type: bool
            default: False
            version_added: "2.10"
        property_name_format:
            description:
                - Transforms property name format.
            type: str
            choices: [ snake_case, camel_case, lower_case ]
            default: 'camel_case'
            version_added: "2.10"
        keyed_groups:
            description: Add hosts to group based on the values of a variable.
            type: list
            default: [
                {key: 'config.guestId', separator: ''},
                {key: 'summary.runtime.powerState', separator: ''},
            ]
            version_added: "2.10"
'''

EXAMPLES = r'''
# Sample configuration file for VMware Guest dynamic inventory
    plugin: community.vmware.vmware_vm_inventory
    strict: False
    hostname: 10.65.223.31
    username: administrator@vsphere.local
    password: Esxi@123$%
    validate_certs: False
    with_tags: True

# Gather minimum set of properties for VMware guest
    plugin: community.vmware.vmware_vm_inventory
    strict: False
    hostname: 10.65.223.31
    username: administrator@vsphere.local
    password: Esxi@123$%
    validate_certs: False
    with_tags: True
    properties:
    - 'name'
    - 'guest.ipAddress'

# Use Datacenter, Cluster and Folder value to list VMs
    plugin: community.vmware.vmware_vm_inventory
    strict: False
    hostname: 10.65.200.241
    username: administrator@vsphere.local
    password: Esxi@123$%
    validate_certs: False
    with_tags: True
    resources:
      - datacenter:
        - Asia-Datacenter1
        - Asia-Datacenter2
        resources:
        - compute_resource:
          - Asia-Cluster1
          resources:
          - host_system:
            - Asia-ESXI4
        - folder:
          - dev
          - prod
'''

import ssl
import atexit
from ansible.errors import AnsibleError, AnsibleParserError
from ansible.utils.display import Display
from ansible.module_utils._text import to_text, to_native
from ansible.module_utils.common.dict_transformations import camel_dict_to_snake_dict, dict_merge
from ansible.module_utils.common.dict_transformations import _snake_to_camel
from ansible.module_utils.six import text_type

display = Display()

try:
    # requests is required for exception handling of the ConnectionError
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from pyVim import connect
    from pyVmomi import vim, vmodl
    from pyVmomi.VmomiSupport import DataObject
    from pyVmomi import Iso8601
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False

try:
    from com.vmware.vapi.std_client import DynamicID
    from vmware.vapi.vsphere.client import create_vsphere_client
    HAS_VSPHERE = True
except ImportError:
    HAS_VSPHERE = False


from ansible.plugins.inventory import BaseInventoryPlugin, Constructable, Cacheable
from ansible.parsing.yaml.objects import AnsibleVaultEncryptedUnicode


class BaseVMwareInventory:
    def __init__(self, hostname, username, password, port, validate_certs, with_tags):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.port = port
        self.with_tags = with_tags
        self.validate_certs = validate_certs
        self.content = None
        self.rest_content = None

        self.check_requirements()

    def do_login(self):
        """
        Check requirements and do login
        """
        self.check_requirements()
        self.content = self._login()
        if self.with_tags:
            self.rest_content = self._login_vapi()

    def _login_vapi(self):
        """
        Login to vCenter API using REST call
        Returns: connection object

        """
        session = requests.Session()
        session.verify = self.validate_certs
        if not self.validate_certs:
            # Disable warning shown at stdout
            requests.packages.urllib3.disable_warnings()

        server = self.hostname
        if self.port:
            server += ":" + str(self.port)

        client = None
        try:
            client = create_vsphere_client(server=server,
                                           username=self.username,
                                           password=self.password,
                                           session=session)
        except Exception as e:  # pylint: disable=bare-except
            display.warning(to_native(e))

        if client is None:
            raise AnsibleError("Failed to login to %s using %s" % (server, self.username))
        return client

    def _login(self):
        """
        Login to vCenter or ESXi server
        Returns: connection object

        """
        if self.validate_certs and not hasattr(ssl, 'SSLContext'):
            raise AnsibleError('pyVim does not support changing verification mode with python < 2.7.9. Either update '
                               'python or set validate_certs to false in configuration YAML file.')

        ssl_context = None
        if not self.validate_certs and hasattr(ssl, 'SSLContext'):
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
            ssl_context.verify_mode = ssl.CERT_NONE

        service_instance = None
        try:
            service_instance = connect.SmartConnect(host=self.hostname, user=self.username,
                                                    pwd=self.password, sslContext=ssl_context,
                                                    port=self.port)
        except vim.fault.InvalidLogin as e:
            raise AnsibleParserError("Unable to log on to vCenter or ESXi API at %s:%s as %s: %s" % (self.hostname, self.port, self.username, e.msg))
        except vim.fault.NoPermission as e:
            raise AnsibleParserError("User %s does not have required permission"
                                     " to log on to vCenter or ESXi API at %s:%s : %s" % (self.username, self.hostname, self.port, e.msg))
        except (requests.ConnectionError, ssl.SSLError) as e:
            raise AnsibleParserError("Unable to connect to vCenter or ESXi API at %s on TCP/%s: %s" % (self.hostname, self.port, e))
        except vmodl.fault.InvalidRequest as e:
            # Request is malformed
            raise AnsibleParserError("Failed to get a response from server %s:%s as "
                                     "request is malformed: %s" % (self.hostname, self.port, e.msg))
        except Exception as e:
            raise AnsibleParserError("Unknown error while connecting to vCenter or ESXi API at %s:%s : %s" % (self.hostname, self.port, e))

        if service_instance is None:
            raise AnsibleParserError("Unknown error while connecting to vCenter or ESXi API at %s:%s" % (self.hostname, self.port))

        atexit.register(connect.Disconnect, service_instance)
        return service_instance.RetrieveContent()

    def check_requirements(self):
        """ Check all requirements for this inventory are satisified"""
        if not HAS_REQUESTS:
            raise AnsibleParserError('Please install "requests" Python module as this is required'
                                     ' for VMware Guest dynamic inventory plugin.')
        elif not HAS_PYVMOMI:
            raise AnsibleParserError('Please install "PyVmomi" Python module as this is required'
                                     ' for VMware Guest dynamic inventory plugin.')
        if HAS_REQUESTS:
            # Pyvmomi 5.5 and onwards requires requests 2.3
            # https://github.com/vmware/pyvmomi/blob/master/requirements.txt
            required_version = (2, 3)
            requests_version = requests.__version__.split(".")[:2]
            try:
                requests_major_minor = tuple(map(int, requests_version))
            except ValueError:
                raise AnsibleParserError("Failed to parse 'requests' library version.")

            if requests_major_minor < required_version:
                raise AnsibleParserError("'requests' library version should"
                                         " be >= %s, found: %s." % (".".join([str(w) for w in required_version]),
                                                                    requests.__version__))

        if not HAS_VSPHERE and self.with_tags:
            raise AnsibleError("Unable to find 'vSphere Automation SDK' Python library which is required."
                               " Please refer this URL for installation steps"
                               " - https://code.vmware.com/web/sdk/65/vsphere-automation-python")

        if not all([self.hostname, self.username, self.password]):
            raise AnsibleError("Missing one of the following : hostname, username, password. Please read "
                               "the documentation for more information.")

    def get_managed_objects_properties(self, vim_type, properties=None, resources=None, strict=False):
        """
        Look up a Managed Object Reference in vCenter / ESXi Environment
        :param vim_type: Type of vim object e.g, for datacenter - vim.Datacenter
        :param properties: List of properties related to vim object e.g. Name
        :return: local content object
        """
        TraversalSpec = vmodl.query.PropertyCollector.TraversalSpec
        FilterSpec = vmodl.query.PropertyCollector.FilterSpec
        ObjectSpec = vmodl.query.PropertyCollector.ObjectSpec
        PropertySpec = vmodl.query.PropertyCollector.PropertySpec

        resource_filters = resources or []
        type_to_name_map = {}

        def _handle_error(message):
            if strict:
                raise AnsibleError(message)
            else:
                display.warning(message)

        def get_contents(container, vim_types):
            return self.content.propertyCollector.RetrieveContents([
                FilterSpec(
                    objectSet=[
                        ObjectSpec(
                            obj=self.content.viewManager.CreateContainerView(
                                container, vim_types, True),
                            skip=False,
                            selectSet=[TraversalSpec(
                                type=vim.view.ContainerView, path='view', skip=False)]
                        )],
                    propSet=[PropertySpec(type=t, all=False, pathSet=['name']) for t in vim_types],
                )
            ])

        def filter_containers(containers, typ, filter_list):
            if len(filter_list) > 0:
                objs = []
                results = []
                found_filters = {}

                for container in containers:
                    results.extend(get_contents(container, [typ]))

                for res in results:
                    if res.propSet[0].val in filter_list:
                        objs.append(res.obj)
                        found_filters[res.propSet[0].val] = True

                for fil in filter_list:
                    if fil not in found_filters:
                        _handle_error("Unable to find %s %s" % (type_to_name_map[typ], fil))

                return objs
            return containers

        def build_containers(containers, vim_type, names, filters):
            filters = filters or []
            if vim_type:
                containers = filter_containers(containers, vim_type, names)

            new_containers = []
            for fil in filters:
                new_filters = None
                for k, v in fil.items():
                    if k == "resources":
                        new_filters = v
                    else:
                        vim_type = getattr(vim, _snake_to_camel(k, True))
                        names = v
                        type_to_name_map[vim_type] = k.replace("_", " ")

                new_containers.extend(build_containers(containers, vim_type, names, new_filters))

            if len(filters) > 0:
                return new_containers
            return containers

        containers = build_containers([self.content.rootFolder], None, None, resource_filters)
        if len(containers) == 0:
            return []

        objs_list = [ObjectSpec(
            obj=self.content.viewManager.CreateContainerView(r, [vim_type], True),
            selectSet=[TraversalSpec(path='view', skip=False, type=vim.view.ContainerView)]) for r in containers]

        is_all = False if properties else True

        # Create Property Spec
        property_spec = PropertySpec(
            type=vim_type,  # Type of object to retrieved
            all=is_all,
            pathSet=properties
        )

        # Create Filter Spec
        filter_spec = FilterSpec(
            objectSet=objs_list,
            propSet=[property_spec],
            reportMissingObjectsInResults=False
        )

        try:
            return self.content.propertyCollector.RetrieveContents([filter_spec])
        except vmodl.query.InvalidProperty as err:
            _handle_error("Invalid property name: %s" % err.name)
        except Exception as err:  # pylint: disable=broad-except
            _handle_error("Couldn't retrieve contents from host: %s" % to_native(err))
        return []

    @staticmethod
    def _get_object_prop(vm, attributes):
        """Safely get a property or return None"""
        result = vm
        for attribute in attributes:
            try:
                result = getattr(result, attribute)
            except (AttributeError, IndexError):
                return None
        return result


class InventoryModule(BaseInventoryPlugin, Constructable, Cacheable):

    NAME = 'community.vmware.vmware_vm_inventory'

    def verify_file(self, path):
        """
        Verify plugin configuration file and mark this plugin active
        Args:
            path: Path of configuration YAML file
        Returns: True if everything is correct, else False
        """
        valid = False
        if super(InventoryModule, self).verify_file(path):
            if path.endswith(('vmware.yaml', 'vmware.yml', 'vmware_vm_inventory.yaml', 'vmware_vm_inventory.yml')):
                valid = True

        return valid

    def parse(self, inventory, loader, path, cache=True):
        """
        Parses the inventory file
        """
        super(InventoryModule, self).parse(inventory, loader, path, cache=cache)

        cache_key = self.get_cache_key(path)

        config_data = self._read_config_data(path)

        # set _options from config data
        self._consume_options(config_data)

        username = self.get_option('username')
        password = self.get_option('password')

        if isinstance(username, AnsibleVaultEncryptedUnicode):
            username = username.data

        if isinstance(password, AnsibleVaultEncryptedUnicode):
            password = password.data

        self.pyv = BaseVMwareInventory(  # pylint: disable=attribute-defined-outside-init
            hostname=self.get_option('hostname'),
            username=username,
            password=password,
            port=self.get_option('port'),
            with_tags=self.get_option('with_tags'),
            validate_certs=self.get_option('validate_certs')
        )

        self.pyv.do_login()

        if cache:
            cache = self.get_option('cache')

        update_cache = False
        if cache:
            try:
                cacheable_results = self._cache[cache_key]
            except KeyError:
                update_cache = True

        if cache and not update_cache:
            self._populate_from_cache(cacheable_results)
        else:
            cacheable_results = self._populate_from_source()

        if update_cache or (not cache and self.get_option('cache')):
            self._cache[cache_key] = cacheable_results

    def _populate_from_cache(self, cache_data):
        """ Populate cache using source data """
        for host, host_properties in cache_data.items():
            self._populate_host_properties(host_properties, host)

    def _get_hostname(self, properties, hostnames):
        strict = self.get_option('strict')
        hostname = None

        for preference in hostnames:
            try:
                hostname = self._compose(preference, properties)
            except Exception as e:  # pylint: disable=broad-except
                if strict:
                    raise AnsibleError("Could not compose %s as hostnames %s" % (preference, to_native(e)))

            if hostname:
                return to_text(hostname)

    def _populate_from_source(self):
        """
        Populate inventory data from direct source

        """
        hostvars = {}
        vm_properties = self.get_option('properties')
        if not isinstance(vm_properties, list):
            vm_properties = [vm_properties]

        if len(vm_properties) == 0:
            vm_properties = ['name']

        if 'all' in vm_properties:
            query_props = None
            vm_properties.remove('all')
        else:
            query_props = [x for x in vm_properties if x != "customValue"]

        objects = self.pyv.get_managed_objects_properties(
            vim_type=vim.VirtualMachine,
            properties=query_props,
            resources=self.get_option('resources'),
            strict=self.get_option('strict')
        )

        tags_info = None
        if self.pyv.rest_content:
            tag_svc = self.pyv.rest_content.tagging.Tag
            tag_association = self.pyv.rest_content.tagging.TagAssociation
            tags_info = dict()
            tags = tag_svc.list()
            for tag in tags:
                tag_obj = tag_svc.get(tag)
                tags_info[tag_obj.id] = tag_obj.name

        with_path = self.get_option('with_path')
        hostnames = self.get_option('hostnames')

        for vm_obj in objects:
            if not vm_obj.obj.config:
                # Sometime orphaned VMs return no configurations
                continue

            properties = {}
            for vm_obj_property in vm_obj.propSet:
                properties[vm_obj_property.name] = vm_obj_property.val

            # Custom values
            if 'customValue' in vm_properties:
                field_mgr = self.pyv.content.customFieldsManager.field
                for cust_value in vm_obj.obj.customValue:
                    properties[[y.name for y in field_mgr if y.key == cust_value.key][0]] = cust_value.value

            # Tags
            if tags_info:
                # Add virtual machine to appropriate tag group
                vm_mo_id = vm_obj.obj._GetMoId()  # pylint: disable=protected-access
                vm_dynamic_id = DynamicID(type='VirtualMachine', id=vm_mo_id)
                attached_tags = [tags_info[tag_id] for tag_id in tag_association.list_attached_tags(vm_dynamic_id)]
                properties['tags'] = attached_tags

            # Build path
            if with_path:
                path = []
                parent = vm_obj.obj.parent
                while parent:
                    path.append(parent.name)
                    parent = parent.parent
                path.reverse()
                properties['path'] = "/".join(path)

            host_properties = to_nested_dict(properties)
            host = self._get_hostname(host_properties, hostnames)

            if host not in hostvars:
                hostvars[host] = host_properties
                self._populate_host_properties(host_properties, host)

        return hostvars

    def _populate_host_properties(self, host_properties, host):
        # Load VM properties in host_vars
        with_path = self.get_option('with_path')
        with_nested_properties = self.get_option('with_nested_properties')

        self.inventory.add_host(host)

        # Use constructed if applicable
        strict = self.get_option('strict')
        # Composed variables
        self._set_composite_vars(self.get_option('compose'), host_properties, host, strict=strict)
        # Complex groups based on jinja2 conditionals, hosts that meet the conditional are added to group
        self._add_host_to_composed_groups(self.get_option('groups'), host_properties, host, strict=strict)
        # Create groups based on variable values and add the corresponding hosts to it
        self._add_host_to_keyed_groups(self.get_option('keyed_groups'), host_properties, host, strict=strict)

        if with_path:
            parents = host_properties['path'].split('/')
            if parents:
                if isinstance(with_path, text_type):
                    parents = [with_path] + parents

                c_name = self._sanitize_group_name('/'.join(parents))
                c_group = self.inventory.add_group(c_name)
                self.inventory.add_host(host, c_group)
                parents.pop()

                while len(parents) > 0:
                    p_name = self._sanitize_group_name('/'.join(parents))
                    p_group = self.inventory.add_group(p_name)

                    self.inventory.add_child(p_group, c_group)
                    c_group = p_group
                    parents.pop()

        # property_name_format
        property_name_format = self.get_option('property_name_format')
        if property_name_format.lower() == 'snake_case':
            host_properties = camel_dict_to_snake_dict(host_properties)
        elif property_name_format.lower() == 'lower_case':
            host_properties = rename_dict_key(host_properties, str.lower)

        # with_nested_properties
        host_properties = host_properties if with_nested_properties else to_flatten_dict(host_properties)

        # with_sanitized_property_name
        can_sanitize = self.get_option('with_sanitized_property_name')
        for k, v in host_properties.items():
            k = self._sanitize_group_name(k) if can_sanitize else k
            self.inventory.set_variable(host, k, v)


def parse_vim_property(vim_prop):
    prop_type = type(vim_prop).__name__
    if prop_type.startswith("vim") or prop_type.startswith("vmodl"):
        if isinstance(vim_prop, DataObject):
            r = {}
            for prop in vim_prop._GetPropertyList():  # pylint: disable=protected-access
                if prop.name not in ['dynamicProperty', 'dynamicType', 'managedObjectType']:
                    sub_prop = getattr(vim_prop, prop.name)
                    r[prop.name] = parse_vim_property(sub_prop)
            return r

        elif isinstance(vim_prop, list):
            r = []
            for prop in vim_prop:
                r.append(parse_vim_property(prop))
            return r
        return vim_prop.__str__()

    elif prop_type == "datetime":
        return Iso8601.ISO8601Format(vim_prop)

    elif prop_type == "long":
        return int(vim_prop)
    elif prop_type == "long[]":
        return [int(x) for x in vim_prop]

    elif isinstance(vim_prop, list):
        return [parse_vim_property(x) for x in vim_prop]

    elif prop_type in ['bool', 'int', 'NoneType']:
        return vim_prop

    return to_text(vim_prop)


def to_nested_dict(vm_properties):
    host_properties = {}

    for vm_prop_name, vm_prop_val in vm_properties.items():
        prop_parents = reversed(vm_prop_name.split("."))
        prop_dict = parse_vim_property(vm_prop_val)

        for k in prop_parents:
            prop_dict = {k: prop_dict}
        host_properties = dict_merge(host_properties, prop_dict)

    return host_properties


def to_flatten_dict(d, parent_key='', sep='.'):
    items = []
    for k, v in d.items():
        new_key = parent_key + sep + k if parent_key else k
        if v and isinstance(v, dict):
            items.extend(to_flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def rename_dict_key(item, rename_func):
    if isinstance(item, dict):
        new_dict = {}
        for k, v in item.items():
            new_dict[rename_func(k)] = rename_dict_key(v, rename_func)
        return new_dict
    elif isinstance(item, list):
        new_list = []
        for k in item:
            new_list.append(rename_dict_key(k, rename_func))
    else:
        return item
