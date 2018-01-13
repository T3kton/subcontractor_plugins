MODULE_NAME = 'vcenter'

from subcontractor_plugins.vcenter.lib import create, create_rollback, destroy, set_power, power_state

MODULE_FUNCTIONS = {
                     'create': create,
                     'create_rollback': create_rollback,
                     'destroy': destroy,
                     'set_power': set_power,
                     'power_state': power_state
                   }
