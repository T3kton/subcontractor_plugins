MODULE_NAME = 'virtualbox'

from subcontractor_plugins.virtualbox.lib import create, create_rollback, destroy, set_power, power_state, get_interface_map

MODULE_FUNCTIONS = {
                     'create': create,
                     'create_rollback': create_rollback,
                     'destroy': destroy,
                     'set_power': set_power,
                     'power_state': power_state,
                     'get_interface_map': get_interface_map
                   }
