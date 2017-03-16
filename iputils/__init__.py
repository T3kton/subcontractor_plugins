MODULE_NAME = 'iputils'

from subcontractor_plugins.iputils.lib import ping, port_state

MODULE_FUNCTIONS = {
                     'ping': ping,
                     'port_state': port_state
                   }
