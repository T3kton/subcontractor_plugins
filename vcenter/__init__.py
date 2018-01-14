MODULE_NAME = 'vcenter'

from subcontractor_plugins.vcenter.lib import host_list, datastore_list, create, create_rollback, destroy, get_interface_map, set_power, power_state

MODULE_FUNCTIONS = {
                     'host_list': host_list,
                     'datastore_list': datastore_list,
                     'create': create,
                     'create_rollback': create_rollback,
                     'destroy': destroy,
                     'get_interface_map': get_interface_map,
                     'set_power': set_power,
                     'power_state': power_state
                   }
