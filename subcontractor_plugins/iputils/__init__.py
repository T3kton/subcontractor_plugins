MODULE_NAME = 'iputils'

from subcontractor_plugins.iputils.lib import ping, port_state, snmp_get, snmp_set

MODULE_FUNCTIONS = {
                     'ping': ping,
                     'port_state': port_state,
                     'snmp_get': snmp_get,
                     'snmp_set': snmp_set
                   }
