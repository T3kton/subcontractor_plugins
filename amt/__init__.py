MODULE_NAME = 'amt'

from subcontractor_plugins.amt.lib import set_power, power_state

MODULE_FUNCTIONS = {
                     'set_power': set_power,
                     'power_state': power_state
                   }
