MODULE_NAME = 'ssh'

from subcontractor_plugins.ssh.lib import execute, file

MODULE_FUNCTIONS = {
                     'execute': execute,
                     'file': file
                   }
