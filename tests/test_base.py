import sys
import unittest

BUILD_PATH = './build/bin'
sys.path.insert(0, BUILD_PATH)

from interface_netconnect import InterfaceNetconnect  # noqa

ZMQ_IFACE = 'ipc:///tmp/netconnect-interface.pipe'


class Base(unittest.TestCase):
    """General tests
    """
    def test_echo(self):
        i_a = InterfaceNetconnect(ZMQ_IFACE)
        ret = i_a.echo('a', 'b')
        print(ret)

    def test_status(self):
        i_a = InterfaceNetconnect(ZMQ_IFACE)
        ret = i_a.status()
        print(ret)

    def test_interfaces(self):
        i_a = InterfaceNetconnect(ZMQ_IFACE)
        ret = i_a.interfaces()
        for i in ret:
            print(i)

    def test_online_check(self):
        i_a = InterfaceNetconnect(ZMQ_IFACE)
        i_a.online_check()

    def test_config(self):
        i_a = InterfaceNetconnect(ZMQ_IFACE)
        i_a.config({'test_host': 'www.seznam.cz'})


class LTE(unittest.TestCase):
    """LTE Tests.
    """
    def test_connect(self):
        i_a = InterfaceNetconnect(ZMQ_IFACE)
        i_a.connect({
            'lte': {
                'name': 'ppp',
                'metric': 300,
                'lte': {
                    'apn': 'internet.t-mobile.cz',
                    'number': '*99#',
                    'user': None,
                    'password': None,
                }
            }
        })

    def test_disconnect(self):
        i_a = InterfaceNetconnect(ZMQ_IFACE)
        i_a.connect({'lte': None})

    def test_info(self):
        i_a = InterfaceNetconnect(ZMQ_IFACE)
        print(i_a.connection_info('lte'))


class WifiClient(unittest.TestCase):
    """Wifi client Tests.
    """
    def test_connect(self):
        i_a = InterfaceNetconnect(ZMQ_IFACE)
        i_a.connect({
            'wifi_client': {
                'usb_port': '4-1:1.0',
                'wifi_client': {
                    'ssid': 'huawei-p10',
                    'key': 'hrnek123'
                },
                'ipv4': {
                    'dhcp': True
                },
                #'ipv4': {
                #    'ip': '10.10.10.10',
                #    'netmask': '255.255.255.0',
                #    'gw': '10.10.10.1',
                #    'dns': ['8.8.8.8', '8.8.4.4']
                #},
            }
        })

    def test_disconnect(self):
        i_a = InterfaceNetconnect(ZMQ_IFACE)
        i_a.connect({'wifi_client': None})

    def test_info(self):
        i_a = InterfaceNetconnect(ZMQ_IFACE)
        print(i_a.connection_info('wifi_client'))

    def test_scan(self):
        i_a = InterfaceNetconnect(ZMQ_IFACE)
        ret = i_a.wifi_scan()
        for i in ret:
            print(i)


class WifiAP(unittest.TestCase):
    """Wifi client Tests.
    """
    def test_connect(self):
        i_a = InterfaceNetconnect(ZMQ_IFACE)
        i_a.connect({
            'wifi_ap': {
                'name': 'wlan0',
                'wifi_ap': {
                    'ssid': 'TESTAP',
                    'channel': 6
                },
                'ipv4': {
                    'ip': '10.10.10.10',
                    'netmask': '255.255.255.0',
                },
            }
        })

    def test_disconnect(self):
        i_a = InterfaceNetconnect(ZMQ_IFACE)
        i_a.connect({'wifi_ap': None})

    def test_info(self):
        i_a = InterfaceNetconnect(ZMQ_IFACE)
        print(i_a.connection_info('wifi_ap'))


class LAN(unittest.TestCase):
    """LAN client Tests.
    """
    def test_connect(self):
        i_a = InterfaceNetconnect(ZMQ_IFACE)
        i_a.connect({
            'lan': {
                'name': 'eth0',
                'lan': {},
                'ipv4': {
                    'dhcp': True,
                },
                #'ipv4': {
                #    'ip': '192.168.1.200',
                #    'netmask': '255.255.255.0',
                #    'gw': '10.10.10.1',
                #    'dns': ['8.8.8.8', '8.8.4.4']
                #},
            }
        })

    def test_disconnect(self):
        i_a = InterfaceNetconnect(ZMQ_IFACE)
        i_a.connect({'lan': None})

    def test_info(self):
        i_a = InterfaceNetconnect(ZMQ_IFACE)
        print(i_a.connection_info('lan'))


if __name__ == '__main__':
    unittest.main()
