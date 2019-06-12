import time
import logging
import psutil
import shlex
from subprocess import Popen, run, DEVNULL, PIPE
from multiprocessing import Lock

import tools
from connection import Connection

# wpa states - DISCONNECTED, SCANNING, COMPLETED, 4WAY_HANDSHAKE, GROUP_HANDSHAKE, ASSOCIATING

WPACLI = '/sbin/wpa_cli'
WPASUPPLICANT_CONF = '/tmp/netconnect_wpa_supplicant.conf'
WPASUPPLICANT_CTRL = '/tmp/netconnect_wpa_supplicant.ctrl'
WPASUPPLICANT_CMD = '/sbin/wpa_supplicant -Dwext -i %s -c %s'
WPASUPPLICANT_CONF_CONTENT = """
# WPA/WPA2
network={
    ssid="%s"
    key_mgmt=WPA-PSK
    psk="%s"
}
# WEP
network={
    ssid="%s"
    key_mgmt=NONE
    wep_key0="%s"
    wep_tx_keyidx=0
}
#OPEN
network={
    ssid="%s"
    key_mgmt=NONE
}
ctrl_interface=%s
"""


class WifiClient(Connection):

    def __init__(self, ev_conn):
        """Overloaded method: constructor.
        """
        self._wpacli_lock = Lock()
        super().__init__(ev_conn)
        self._status['ifname'] = None

    def _loop(self, config, status):
        """Overloaded method: Main loop taking care of link connection.
        """
        log = logging.getLogger(__name__)
        self._status['status'] = 'NOT_CONNECTED'
        proc = None
        link_status = {}
        error_status = None

        while True:
            iface = tools.get_iface(config)

            if iface is not None:
                self._status['ifname'] = iface.ifname

                if tools.gen_systemd_networkd(self.__class__.__name__, config['ipv4'], mac=iface.mac,
                                              metric=512):
                    self._status['status'] = 'CONNECTING'
                    tools.systemd_restart('systemd-networkd')
                    log.info('Created systemd-networkd configuration for %s (%s)' % (iface.ifname, iface.mac))

                if self._wpasupplicant_conf(config['wifi_client']):
                    self._status['status'] = 'CONNECTING'
                    log.info('Created wpa_supplicant configuration: %s' % (WPASUPPLICANT_CONF))

                # wpasupplicant up
                if proc is None:
                    self._status['status'] = 'CONNECTING'
                    log.info("Starting wpa_supplicant")
                    self._terminate_wpasupplicant()
                    wpasupplicant_cmd = WPASUPPLICANT_CMD % (iface.ifname, WPASUPPLICANT_CONF)
                    proc = Popen(shlex.split(wpasupplicant_cmd), stdin=DEVNULL, stderr=DEVNULL, stdout=DEVNULL)

                status = self._wifi_status()
                if status is not None and status['status'] == 'COMPLETED':
                    self._status['status'] = 'CONNECTED'

                self._status['error'] = None

            else:
                self._status['error'] = 'NO_DEVICE_DETECTED'
                self._status['ifname'] = None

                if tools.remove_networkd_file(self.__class__.__name__):
                    tools.systemd_restart('systemd-networkd')
                    log.info('Removed systemd-networkd configuration')
                    self._ev_conn.set()

                if proc is not None:
                    log.info('Terminating wpasupplicant process')
                    proc.terminate()
                    proc.wait()
                    proc = None

            if proc is not None and proc.poll() is not None:
                # wpasupplicant interrupted
                self._status['status'] = 'NOT_CONNECTED'
                proc = None

            # log important status changes
            ret = self._wifi_status()
            if ret is not None and link_status != ret:

                if ret['status'] != link_status.get('status', None):
                    log.info('Status: %s <%s> (%s dbm)' % (ret['status'], ret['ssid'], ret['rssi']))

                # update online status when status change from/to COMPLETED - wifi is connected to AP
                if ret['status'] == 'COMPLETED' and link_status.get('status', None) != 'COMPLETED':
                    self._ev_conn.set()
                if ret['status'] != 'COMPLETED' and link_status.get('status', None) == 'COMPLETED':
                    self._ev_conn.set()

                link_status = ret

            if error_status != self._status['error']:
                if self._status['error'] is not None:
                    log.info('Error: %s' % (self._status['error']))
                error_status = self._status['error']

            time.sleep(5)

    def _wpacli(self, command):
        """Wpa cli command. Returns stdout string or None in case of error.
        """
        with self._wpacli_lock:
            try:
                ret = run([WPACLI, '-p', WPASUPPLICANT_CTRL, '-i', self._status['ifname'], command],
                          timeout=1, stdout=PIPE, stderr=DEVNULL)
                if ret.returncode != 0:
                    return None
                return ret.stdout.decode()
            except Exception as e:
                print(e)
                pass

    def _wifi_status(self):
        result = {'status': 'DISCONNECTED', 'ssid': '', 'rssi': -99}
        ret = self._wpacli('status')
        if ret is None:
            return None
        for i in ret.split('\n'):
            if i.startswith('wpa_state') and '=' in i:
                result['status'] = i.split('=')[1].strip()
            if i.startswith('ssid') and '=' in i:
                result['ssid'] = i.split('=')[1].strip()

        ret = self._wpacli('signal_poll')
        for i in ret.split('\n'):
            if i.startswith('RSSI') and '=' in i:
                rssi = int(i.split('=')[1])
                result['rssi'] = rssi
                break

        return result

    def scan(self):
        try:
            ret = self._scan()
        except Exception:
            return []
        return ret

    def _scan(self):
        ret = self._wpacli('scan')
        if ret is None:
            return None
        time.sleep(3)
        ret = self._wpacli('scan_result')
        if ret is None:
            return []

        result = []
        for i in ret.split('\n'):
            if i.startswith('bssid') or i.strip() == '':
                continue
            row = i.split()
            if len(row) < 4:
                continue
            rec = {}
            if len(row) < 5:
                rec['ssid'] = ''
            else:
                rec['ssid'] = ' '.join(row[4:])
            rec['channel'] = row[1]
            rec['enc'] = True
            if row[3] == '[ESS]':
                rec['enc'] = False
            rec['signal'] = (int(int(row[2]) / 2)) - 100
            result.append(rec)

        return result

    def _wpasupplicant_conf(self, wifi_cfg):
        """Generates wpa supplicant configuration file.

        :returns: T/F depending if configuration changed.
        """
        ssid = wifi_cfg.get('ssid', 'UNKNOWN')
        wep = wifi_cfg.get('key', 'UNKNOWN')
        wpa = wifi_cfg.get('key', 'UNKNOWN')
        if len(wpa) < 8:
            wpa = 'dummy123'  # dummy password if incorrect length

        content = WPASUPPLICANT_CONF_CONTENT % (ssid, wpa, ssid, wep, ssid, WPASUPPLICANT_CTRL)
        return tools.write_if_changed(WPASUPPLICANT_CONF, content)

    def _terminate_wpasupplicant(self):
        """Disconnect pppd session.
        """
        # terminate all the running pppd procesess
        for i in psutil.process_iter():
            try:
                if i.name().startswith('wpa_supplicant'):
                    i.terminate()
                    psutil.wait_procs([i], timeout=4)
            except Exception:
                pass

    def info(self):
        """Overloaded method: Get connection information.
        """

        ret = {'status': self._status['status']}
        ret['wireless_status'] = self._wifi_status()
        ret['address'] = tools.get_address(self._status['ifname'])
        ret['ifstate'] = tools.get_operstate(self._status['ifname'])
        ret['ifname'] = self._status['ifname']
        return ret

    def clean(self):
        if tools.remove_networkd_file(self.__class__.__name__):
            tools.systemd_restart('systemd-networkd')
        self._terminate_wpasupplicant()
        tools.iface_down(self._status['ifname'])

        if self._wpacli_lock.acquire(block=False):
            self._wpacli_lock.release()
