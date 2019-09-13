MODULE_NAME = 'ipmi'

from subcontractor_plugins.ipmi.lib import set_power, power_state

MODULE_FUNCTIONS = {
                     'set_power': set_power,
                     'power_state': power_state
                   }
