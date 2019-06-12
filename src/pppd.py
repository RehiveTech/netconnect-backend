import fcntl
import os
import signal
import re
import time
from datetime import datetime

from subprocess import Popen, PIPE, STDOUT

__version__ = '1.0.3'
LOGFILE = '/tmp/netconnect-pppd.log'

PPPD_RETURNCODES = {
    1: 'Fatal error occured',
    2: 'Error processing options',
    3: 'Not executed as root or setuid-root',
    4: 'No kernel support, PPP kernel driver not loaded',
    5: 'Received SIGINT, SIGTERM or SIGHUP',
    6: 'Modem could not be locked',
    7: 'Modem could not be opened',
    8: 'Connect script failed',
    9: 'pty argument command could not be run',
    10: 'PPP negotiation failed',
    11: 'Peer failed (or refused) to authenticate',
    12: 'The link was terminated because it was idle',
    13: 'The link was terminated because the connection time limit was reached',
    14: 'Callback negotiated',
    15: 'The link was terminated because the peer was not responding to echo requests',
    16: 'The link was terminated by the modem hanging up',
    17: 'PPP negotiation failed because serial loopback was detected',
    18: 'Init script failed',
    19: 'Failed to authenticate to the peer',
    100: 'Timeout',
}


class PPPConnectionError(Exception):
    def __init__(self, code, output=None):
        self.code = code
        self.message = PPPD_RETURNCODES.get(code, 'Undocumented error occured')
        self.output = output

        super(Exception, self).__init__(code, output)

    def __str__(self):
        return self.message


class PPPConnection:
    def __init__(self, *args, **kwargs):
        self.output = ''
        self._laddr = None
        self._raddr = None

        commands = []

        pppd_path = kwargs.pop('pppd_path', '/usr/sbin/pppd')
        if not os.path.isfile(pppd_path) or not os.access(pppd_path, os.X_OK):
            raise IOError('%s not found' % pppd_path)

        commands.append(pppd_path)

        for k, v in kwargs.items():
            commands.append(k)
            commands.append(v)
        commands.extend(args)
        commands.append('nodetach')
        commands.append('debug')

        # print(commands)

        self.proc = Popen(commands,
                          stdout=PIPE,
                          stderr=STDOUT,
                          universal_newlines=True,
                          preexec_fn=os.setsid)

        # set stdout to non-blocking
        fd = self.proc.stdout.fileno()
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        t0 = time.monotonic()
        while True:
            try:
                self.output += self.proc.stdout.read()
                # print(self.output)
            except IOError as e:
                if e.errno != 11:
                    self._write_log(self.output)
                    raise
                time.sleep(1)

            except TypeError:
                time.sleep(1)

            if 'ip-up finished' in self.output:
                self._write_log(self.output)
                return
            elif self.proc.poll():
                self._write_log(self.output)
                raise PPPConnectionError(self.proc.returncode, self.output)
            elif t0 + 30 < time.monotonic():
                self._write_log(self.output)
                self.kill_pppd()
                raise PPPConnectionError(100, self.output)
                #raise Exception('Timeout')

    def _write_log(self, content):
        """"Write content to log file.
        """
        try:
            f = open(LOGFILE, 'w')
            f.write(str(datetime.now()) + '\n')
            f.write(content)
            f.close()
        except Exception:
            pass

    @property
    def laddr(self):
        if not self._laddr:
            try:
                self.output += self.proc.stdout.read()
            except IOError as e:
                if e.errno != 11:
                    raise
            result = re.search(r'local  IP address ([\d\.]+)', self.output)
            if result:
                self._laddr = result.group(1)

        return self._laddr

    @property
    def raddr(self):
        if not self._raddr:
            try:
                self.output += self.proc.stdout.read()
            except IOError as e:
                if e.errno != 11:
                    raise
            result = re.search(r'remote IP address ([\d\.]+)', self.output)
            if result:
                self._raddr = result.group(1)

        return self._raddr

    def dns(self):
        return re.findall('DNS address (.*)\n', self.output)

    def connected(self):
        if self.proc.poll():
            try:
                self.output += self.proc.stdout.read()
            except IOError as e:
                if e.errno != 11:
                    raise
            if self.proc.returncode not in [0, 5]:
                raise PPPConnectionError(self.proc.returncode, self.output)
            return False
        elif 'ip-up finished' in self.output:
            return True

        return False

    def disconnect(self):
        try:
            if not self.connected():
                return
        except PPPConnectionError:
            return
        self.kill_pppd()

    def kill_pppd(self):
        # Send the signal to all the processes in group
        # Based on stackoverlfow:
        # https://stackoverflow.com/questions/4789837/how-to-terminate-a-python-subprocess-launched-with-shell-true/
        try:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGHUP)
            os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
        except Exception:
            pass
