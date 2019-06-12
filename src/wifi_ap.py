import time
import shlex
import psutil
import logging
from subprocess import Popen, run, DEVNULL, PIPE

import tools
from connection import Connection

HOSTAPD_CONF = '/tmp/netconnect_hostapd.conf'
HOSTAPD_CMD = '/usr/sbin/hostapd %s'
HOSTAPD_CONF_CONTENT = """
interface=%s
ieee80211n=1
hw_mode=g
ssid=%s
channel=%s
"""

HOSTAPD_CONF_ENC_CONTENT = """
wpa=1
wpa_passphrase=%s
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP CCMP
"""


class WifiAP(Connection):

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
        proc = None

        while True:
            if self._status['status'] != 'CONNECTED':
                iface = tools.get_iface(config)

            if iface is not None:
                self._status['ifname'] = iface.ifname

                if tools.gen_systemd_networkd(self.__class__.__name__, config['ipv4'],
                                              mac=iface.mac, dhcp_server=True):
                    self._status['status'] = 'CONNECTING'
                    tools.systemd_restart('systemd-networkd')
                    log.info('Created systemd-networkd configuration for %s (%s)' % (iface.ifname, iface.mac))


                if self._hostapd_conf(iface.ifname, config['wifi_ap']):
                    self._status['status'] = 'CONNECTING'
                    log.info('Created hostapd configuration: %s' % (HOSTAPD_CONF))

                if proc is None:
                    self._status['status'] = 'CONNECTING'
                    self._terminate_hostapd()
                    hostapd_cmd = HOSTAPD_CMD % (HOSTAPD_CONF)
                    proc = Popen(shlex.split(hostapd_cmd), stdin=DEVNULL, stderr=DEVNULL, stdout=DEVNULL)

                time.sleep(1)
                if proc.poll() is None:
                    self._status['status'] = 'CONNECTED'

            else:
                self._status['error'] = 'NO_DEVICE_DETECTED'
                self._status['ifname'] = None

                if tools.remove_networkd_file(self.__class__.__name__):
                    tools.systemd_restart('systemd-networkd')
                    log.info('Removed systemd-networkd configuration')

                if proc is not None:
                    log.info('Terminating wpasupplicant process')
                    proc.terminate()
                    proc.wait()
                    proc = None

            if proc is not None and proc.poll() is not None:
                # wpasupplicant interrupted
                self._status['status'] = 'NOT_CONNECTED'
                proc = None

            time.sleep(5)

    def _terminate_hostapd(self):
        """Disconnect pppd session.
        """
        # terminate all the running pppd procesess
        for i in psutil.process_iter():
            try:
                if i.name().startswith('hostapd'):
                    i.terminate()
                    psutil.wait_procs([i], timeout=4)
            except Exception:
                pass

    def _hostapd_conf(self, ifname, wifiap_cfg):
        """Generates hostapd supplicant configuration file.

        :returns: T/F depending if configuration changed.
        """
        ssid = wifiap_cfg.get('ssid', 'NetconnectAP')
        channel = str(wifiap_cfg.get('channel', 5))
        content = HOSTAPD_CONF_CONTENT % (ifname, ssid, channel)

        if wifiap_cfg.get('key') is not None:
            content += HOSTAPD_CONF_ENC_CONTENT % wifiap_cfg.get('key')

        return tools.write_if_changed(HOSTAPD_CONF, content)

    def info(self):
        """Overloaded method: Get connection information.
        """
        ret = {'status': self._status['status']}
        #ret['wireless_status'] = self._wifi_status()
        ret['address'] = tools.get_address(self._status['ifname'])
        ret['ifstate'] = tools.get_operstate(self._status['ifname'])
        ret['ifname'] = self._status['ifname']
        return ret

    def clean(self):
        if tools.remove_networkd_file(self.__class__.__name__):
            tools.systemd_restart('systemd-networkd')
        self._terminate_hostapd()
        tools.iface_down(self._status['ifname'])
