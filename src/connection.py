import logging
from multiprocessing import Process, Manager

# Allowed connection status:
# NOT_CONNECTED
# CONNECTING
# CONNECTED
# INACTIVE


class Connection(object):
    """docstring for Connection"""
    def __init__(self, ev_conn):
        self._p = None
        self._cfg = None
        self._ev_conn = ev_conn

        mgr = Manager()
        self._status = mgr.dict()
        self._status['status'] = 'INACTIVE'
        self._status['error'] = None
        self._status['config'] = None

    def _loop(self, config, status):
        """Main loop taking care of link connection.
        """
        raise NotImplementedError('Not implemented')

    def clean(self):
        """Action when disabling the connection
        """
        raise NotImplementedError('Not implemented')

    def reconnect(self):
        """Force reconnect.
        """
        log = logging.getLogger(__name__)

        if self._p is not None and self._p.is_alive():
            log.info('Terminating main loop of %s' % (self.__class__.__name__))
            self._p.terminate()
            self._p.join()
            self._ev_conn.set()  # update online status

        self._p = None
        self._status['status'] = 'INACTIVE'
        self._status['error'] = None
        self._status['config'] = self._cfg

        if self._cfg is not None:
            log.info('Set new configuration for %s: %s' % (self.__class__.__name__, str(self._cfg)))
            self._p = Process(target=self._loop, args=(self._cfg, self._status))
            self._p.start()
        else:
            log.info('Disconnecting %s' % (self.__class__.__name__))
            self.clean()

    def connect(self, config):
        """Set and apply configuration.
        """
        self._cfg = config
        self.reconnect()

    def status(self):
        """Get connection status.
        """
        return dict(self._status)

    def info(self):
        """Get connection information.
        """
        raise NotImplementedError('Not implemented')
