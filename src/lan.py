import time
import logging

import tools
from connection import Connection

# wpa states - DISCONNECTED, SCANNING, COMPLETED, 4WAY_HANDSHAKE, GROUP_HANDSHAKE

class LAN(Connection):

    def __init__(self, ev_conn):
        """Overloaded method: constructor.
        """
        super().__init__(ev_conn)
        self._status['ifname'] = None

    def _loop(self, config, status):
        """Overloaded method: Main loop taking care of link connection.
        """
        log = logging.getLogger(__name__)
        self._status['status'] = 'NOT_CONNECTED'
        operstate = None

        while True:
            iface = tools.get_iface(config)

            if iface is not None:
                try:
                    self._status['ifname'] = iface.ifname
                except Exception as e:
                    log.error('Error: ' + str(e))
                    time.sleep(1)
                    continue

                if tools.gen_systemd_networkd(self.__class__.__name__, config['ipv4'], mac=iface.mac,
                                              metric=1024):
                    self._status['status'] = 'CONNECTING'
                    tools.systemd_restart('systemd-networkd')
                    log.info('Created systemd-networkd configuration for %s (%s)' % (iface.ifname, iface.mac))

                if tools.get_operstate(self._status['ifname']) == 'UP':
                    self._status['status'] = 'CONNECTED'

            else:
                self._status['error'] = 'NO_DEVICE_DETECTED'
                self._status['ifname'] = None

                if tools.remove_networkd_file(self.__class__.__name__):
                    tools.systemd_restart('systemd-networkd')
                    log.info('Removed systemd-networkd configuration')
                    self._ev_conn.set()  # update online status

            ops = tools.get_operstate(self._status['ifname'])
            if ops == 'UP' and operstate != 'UP':
                log.info('Link UP')
                self._ev_conn.set()
            if ops != 'UP' and operstate == 'UP':
                log.info('Link DOWN')
                self._ev_conn.set()

            operstate = ops
            time.sleep(5)

    def info(self):
        """Overloaded method: Get connection information.
        """
        ret = {'status': self._status['status']}
        ret['address'] = tools.get_address(self._status['ifname'])
        ret['ifstate'] = tools.get_operstate(self._status['ifname'])
        ret['ifname'] = self._status['ifname']
        return ret

    def clean(self):
        if tools.remove_networkd_file(self.__class__.__name__):
            tools.systemd_restart('systemd-networkd')
        tools.iface_down(self._status['ifname'])
