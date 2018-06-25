MODULE_NAME = 'docker'

from subcontractor_plugins.docker.lib import create, create_rollback, destroy, start_stop, state

MODULE_FUNCTIONS = {
                     'create': create,
                     'create_rollback': create_rollback,
                     'destroy': destroy,
                     'start_stop': start_stop,
                     'state': state
                    }
