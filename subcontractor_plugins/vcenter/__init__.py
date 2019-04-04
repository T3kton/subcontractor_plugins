MODULE_NAME = 'vcenter'

from subcontractor_plugins.vcenter.lib import host_list, create_datastore, datastore_list, network_list, create, create_rollback, destroy, get_interface_map, set_power, power_state, execute

MODULE_FUNCTIONS = {
                     'host_list': host_list,
                     'create_datastore': create_datastore,
                     'datastore_list': datastore_list,
                     'network_list': network_list,
                     'create': create,
                     'create_rollback': create_rollback,
                     'destroy': destroy,
                     'get_interface_map': get_interface_map,
                     'set_power': set_power,
                     'power_state': power_state,
                     'execute': execute
                   }
