from interface_general import InterfaceGeneral

COMMAND_TIMEOUT = 5000


class InterfaceNetconnect(InterfaceGeneral):
    _MOD_NAME = 'netconnect-interface'

    def __init__(self, zmq_iface='ipc:///tmp/netconnect-interface.pipe'):
        super().__init__(InterfaceNetconnect, zmq_iface)

    def echo(self, param1, param2, timeout=COMMAND_TIMEOUT):
        ret = self._send_cmd('echo', [param1, param2], timeout=timeout)
        return ret['message']

    def wait_for_ready(self):
        while True:
            try:
                self.echo('a', 'b', timeout=200)
            except Exception:
                continue
            break

    def status(self):
        ret = self._send_cmd('status', [], timeout=COMMAND_TIMEOUT)
        return ret['message']

    def connect(self, config):
        ret = self._send_cmd('connect', [config], timeout=COMMAND_TIMEOUT)
        return ret['message']

    def connection_info(self, conn):
        ret = self._send_cmd('connection_info', [conn], timeout=COMMAND_TIMEOUT)
        return ret['message']

    def wifi_scan(self):
        ret = self._send_cmd('wifi_scan', [], timeout=COMMAND_TIMEOUT)
        return ret['message']

    def interfaces(self):
        ret = self._send_cmd('interfaces', [], timeout=COMMAND_TIMEOUT)
        return ret['message']

    def online_check(self):
        ret = self._send_cmd('online_check', [], timeout=COMMAND_TIMEOUT)
        return ret['message']

    def config(self, config):
        ret = self._send_cmd('config', [config], timeout=COMMAND_TIMEOUT)
        return ret['message']
