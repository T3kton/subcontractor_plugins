MODULE_NAME = 'ipmi'

from subcontractor_plugins.ipmi.lib import link_test, set_power, power_state

MODULE_FUNCTIONS = {
                     'link_test': link_test,
                     'set_power': set_power,
                     'power_state': power_state
                   }
