import os
import logging
import signal
import tools
import time
import ipaddress
import subprocess
from multiprocessing import Process, Manager, Event

from lan import LAN
from lte import Lte
from wifi_client import WifiClient
from wifi_ap import WifiAP
from interface_netconnect import InterfaceNetconnect
import dnslookup


CONFIG_NAME = 'netconnect.conf'
ROOT_PATH = os.path.dirname(os.path.realpath(__file__))
CONFIG_LOCATION = [ROOT_PATH, '/opt/etc/netconnect']
SYSTEMD_NETWORK_DIR = '/run/systemd/network'
DEF_TEST_HOST = 'www.google.com'
CHECK_ONLINE_PERIOD = 1800
NETWORKCTL = '/bin/networkctl'
RESOVLCONF = '/run/netconnect/resolv.conf'
FALLBACK_DNS = ['8.8.8.8', '8.8.4.4']


def init_logger():
    """Logger initialization
    """
    log_format = '%(levelname)s %(filename)s:%(funcName)s:%(lineno)d %(message)s'
    logger = logging.getLogger()
    logger.handlers.clear()
    handler = logging.StreamHandler()
    fmt = logging.Formatter(log_format)
    handler.setFormatter(fmt)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)


class ModInterface(InterfaceNetconnect):

    def __init__(self, nc):
        super(ModInterface, self).__init__()
        self.nc = nc

    def echo(self, param1, param2):
        """Echo function for testing purposes.
        """
        return [param1, param2]

    def status(self):
        return self.nc.status()

    def connect(self, config):
        """Config and start a connection
        """
        return self.nc.connect(config)

    def connection_info(self, conn):
        """Get information about connection.
        """
        return self.nc.connection_info(conn)

    def wifi_scan(self):
        """Scan wifi networks
        """
        return self.nc.wifi_scan()

    def interfaces(self):
        """Get list of network interfaces.
        """
        return tools.netifaces()

    def online_check(self):
        """Trigger online check process.
        """
        return self.nc.online_check()

    def config(self, config):
        """Trigger online check process.
        """
        return self.nc.config(config)


class Netconnect():

    def __init__(self):
        self._config = list()
        ev_conn = Event()  # link layer connected event

        self._lte = Lte(ev_conn)
        self._wifi_client = WifiClient(ev_conn)
        self._wifi_ap = WifiAP(ev_conn)
        self._lan = LAN(ev_conn)
        self._ev_conn = ev_conn

        mgr = Manager()
        self._ncstatus = mgr.dict()
        Process(target=self._loop, args=(ev_conn,)).start()

        self._ncstatus['online'] = False
        self._ncstatus['last_online_check'] = int(time.time())
        self._ncstatus['test_host'] = DEF_TEST_HOST
        self._ncstatus['dns'] = []

    def _loop(self, ev_conn):
        log = logging.getLogger(__name__)
        t0 = 0  # 0 means check online immediately

        while True:
            time.sleep(1)

            self._ncstatus['dns'] = self.set_nameservers()

            if tools.get_default_route()['ifname'] is None:
                # no default route we, cannot be online anyway
                self._ncstatus['online'] = False
                continue

            if ev_conn.wait(timeout=10):
                # link layer changed status event
                t0 = 0
            ev_conn.clear()

            # here we are connected on link layer with default gateway
            if t0 == 0:
                if self.test_online() is False:
                    self._ncstatus['online'] = False
                    # testing with shorter interval until we are online
                    t0 = 0
                else:
                    log.info('Online')
                    t0 = time.monotonic()
                    self._ncstatus['online'] = True

                self._ncstatus['last_online_check'] = int(time.time())

            elif t0 + CHECK_ONLINE_PERIOD < time.monotonic():
                if self.test_online() is False:
                    self._ncstatus['online'] = False
                    log.info('Offline')
                    t0 = 0
                else:
                    t0 = time.monotonic()
                    self._ncstatus['online'] = True

                self._ncstatus['last_online_check'] = int(time.time())

    def set_nameservers(self):
        """Set nameservers according to current default route. If not possible
        fallback dns are set. Returns list of nameservers belonging to default
        gateway or fallback.
        """
        log = logging.getLogger(__name__)

        gw = tools.get_default_route()
        if gw['ifname'] is None:
            # there is no default gw, set fallback DNS servers
            self.write_dns(RESOVLCONF, FALLBACK_DNS)
            return FALLBACK_DNS

        if gw['ifname'].startswith('ppp'):
            ret = self._lte.status()
            if 'dns' in ret:
                self.write_dns(RESOVLCONF, ret['dns'])
                return ret['dns']
            return FALLBACK_DNS

        try:
            ret = subprocess.run([NETWORKCTL, 'status', gw['ifname'], '--no-page'], stdout=subprocess.PIPE)
            ret = ret.stdout.decode().split()

        except Exception as e:
            # log.error('Cannot get nameservers: ' + str(e))
            self.write_dns(RESOVLCONF, FALLBACK_DNS)
            return FALLBACK_DNS

        dns_list = []
        try:
            i_dns = ret.index('DNS:') + 1
            for ip in ret[i_dns:]:

                try:
                    ipaddress.ip_address(ip)
                except Exception:
                    break
                dns_list.append(ip)
        except Exception as e:
            self.write_dns(RESOVLCONF, FALLBACK_DNS)
            return FALLBACK_DNS

        self.write_dns(RESOVLCONF, FALLBACK_DNS)
        return dns_list

    def write_dns(self, resolvconf, dns_list):
        log = logging.getLogger(__name__)
        try:
            if tools.write_resolvconf(resolvconf, dns_list) is True:
                log.info('New nameservers set in %s: %s' % (resolvconf, str(dns_list)))
        except Exception as e:
            log.error('Cannot set nameservers %s: %s' % (str(dns_list), str(e)))

    def online_check(self):
        self._ev_conn.set()

    def status(self):
        ret = {'lte': self._lte.status(),
               'wifi_client': self._wifi_client.status(),
               'wifi_ap': self._wifi_ap.status(),
               'lan': self._lan.status(),
               'ncstatus': dict(self._ncstatus),
               'gw': tools.get_default_route()}
        return ret

    def connection_info(self, conn):
        if conn == 'lte':
            return self._lte.info()
        if conn == 'wifi_client':
            return self._wifi_client.info()
        if conn == 'wifi_ap':
            return self._wifi_ap.info()
        if conn == 'lan':
            return self._lan.info()

    def connect(self, config):
        """Configure and start appropriate connection.
        Does nothing in case of same configuration given.
        """
        if 'lte' in config:
            self._lte.connect(config['lte'])
        if 'wifi_client' in config:
            self._wifi_client.connect(config['wifi_client'])
        if 'wifi_ap' in config:
            self._wifi_ap.connect(config['wifi_ap'])
        if 'lan' in config:
            self._lan.connect(config['lan'])

    def config(self, config):
        """Netconnect main configuration. Does nothing in case of same config.
        """
        self._ncstatus['test_host'] = config.get('test_host')

    def wifi_scan(self):
        """"Scan wifi networks.
        """
        return self._wifi_client.scan()

    def test_online(self):
        """"Test if we are online.
        """
        test_host = str(self._ncstatus['test_host'])
        for i in range(3):
            ip = dnslookup.dnslookup(test_host, i + 1)
            if ip is not None:
                break
        else:
            # cannot resolve IP
            return False

        for i in range(2):
            if tools.ping_test(test_host) or tools.http_test(test_host):
                return True

        return False


def main():
    """Main loop"""
    log = logging.getLogger(__name__)
    log.info('Starting netconnect[%d]' % (os.getpid()))

    os.makedirs(SYSTEMD_NETWORK_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(RESOVLCONF), exist_ok=True)
    pid = os.getpid()

    nc = Netconnect()
    m_i = ModInterface(nc)

    def sig_handler(signum, frame):
        if pid == os.getpid():
            log.info('Exiting main thread netconnect[%d]' % (os.getpid()))
        os._exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    m_i.loop()


if __name__ == "__main__":
    main()
