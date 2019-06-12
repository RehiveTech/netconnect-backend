import os
import json
import logging
import psutil
import time
import shlex
import tools
from multiprocessing import Process, Manager, Lock
from connection import Connection
from pathlib import Path
from subprocess import Popen, DEVNULL
from pppd import PPPConnection
from at_modem import ATModem

# path to pppd binary
PPPD_PATH = '/usr/sbin/pppd'
# path to chat binary
CHAT_PATH = '/usr/sbin/chat'
# path to generated chatscript file
CHATSCRIPT_PATH = '/tmp/gsm-keeper.chat'
# modem definitions json file
MODEM_DEFS_PATH = os.path.dirname(os.path.realpath(__file__)) + '/modem_defs.json'
MODEM_DEFS = json.loads(Path(MODEM_DEFS_PATH).read_text().strip())
# How often to check if pppd daemon is running
PPPD_CHECK = 15
# connect timeout (seconds)
CONNECT_TIMEOUT = 30

# pppd params - serial port, number, user and password required as parameters
# https://wiki.archlinux.org/index.php/3G_and_GPRS_modems_with_pppd
PPPD_PARAMS = '%s 921600 lock passive defaultroute \
noipdefault usepeerdns hide-password replacedefaultroute nodetach \
lcp-echo-failure 0 lcp-echo-interval 0 connect "%s -v -t 20 -f %s"'

# chatscript file content
# AT+cpin?
CHATSCRIPT = """ABORT 'BUSY'
ABORT 'NO CARRIER'
ABORT 'VOICE'
ABORT 'NO DIALTONE'
ABORT 'NO DIAL TONE'
ABORT 'NO ANSWER'
ABORT 'DELAYED'
REPORT CONNECT
TIMEOUT 6
'' 'ATQ0'
'OK-AT-OK' 'ATZ'
TIMEOUT 3
'OK\d-AT-OK' 'ATI'
'OK' 'ATZ'
'OK' 'AT+CFUN=1'
'OK' 'ATQ0 V1 E1 S0=0 &C1 &D2 +FCLASS=0'
'OK-AT-OK' AT+CGDCONT=1,"IP","%s"
'OK' 'ATDT%s'
TIMEOUT 30
CONNECT ''
"""


class Lte(Connection):

    def __init__(self, ev_conn):
        """Overloaded method: constructor.
        """
        self._at_modem = ATModem()
        super().__init__(ev_conn)
        self._status['ifname'] = None

    def _loop(self, config, status):
        """Overloaded method: Main loop taking care of link connection.
        """
        log = logging.getLogger(__name__)
        self._status['status'] = 'NOT_CONNECTED'
        self._modem = None
        pppdconn = None
        error_status = None

        while True:
            if self._status['status'] != 'CONNECTED':

                self._status['ifname'] = None
                modem = None
                try:
                    modem = self._get_modem()
                except Exception:
                    pass

                if modem is not None and self._at_modem.registered(modem['port_control']) is True:

                    # create neccessary files and connect
                    lte_cfg = config['lte']
                    self._status['status'] = 'CONNECTING'

                    pppd_params = self._pppd_params(lte_cfg['apn'],
                                                    lte_cfg['number'],
                                                    lte_cfg['user'],
                                                    lte_cfg['password'])

                    pppd_params = shlex.split(pppd_params)

                    self._terminate_pppd()
                    time.sleep(1)
                    try:
                        pppdconn = PPPConnection(*pppd_params)
                    except Exception as e:
                        self._status['error'] = 'Cannot connect: ' + str(e)
                        if hasattr(e, 'output') and e.output is not None:
                            self._status['error'] += ' pppd output: ' + e.output[-500:]
                    else:
                        log.info('Link layer of LTE connected')
                        log.info('Network info: %s' % str(self._at_modem.network_info(modem['port_control'])))
                        log.info('Signal: %s' % str(self._at_modem.signal(modem['port_control'])))
                        self._status['status'] = 'CONNECTED'
                        self._status['error'] = None
                        self._ev_conn.set()  # update online status
                        self._status['ifname'] = 'ppp0'
                        self._status['dns'] = pppdconn.dns()

                else:
                    self._status['error'] = 'NO_DEVICE_DETECTED'

            if self._status['status'] == 'CONNECTED':
                try:
                    ret = pppdconn.connected()
                except Exception as e:
                    self._status['error'] = 'Connection interrupted: ' + str(e)
                    if hasattr(e, 'output') and e.output is not None:
                        self._status['error'] += ' pppd output: ' + e.output[-500:]
                    self._status['status'] = 'NOT_CONNECTED'
                else:
                    self._status['error'] = None
                    if ret is False:
                        self._status['error'] = 'Connection interrupted'
                        self._status['status'] = 'NOT_CONNECTED'

            if error_status != self._status['error']:
                if self._status['error'] is not None:
                    log.info('Error: %s' % (self._status['error']))
                    self._ev_conn.set()  # update online status
                error_status = self._status['error']
                if modem is not None:
                    log.info('Network info: %s' % str(self._at_modem.network_info(modem['port_control'])))
                    log.info('Signal: %s' % str(self._at_modem.signal(modem['port_control'])))

            time.sleep(10)

    def info(self):
        """Overloaded method: Get connection information.
        """
        ret = {'status': self._status['status']}

        try:
            modem = self._get_modem()
        except Exception:
            return ret

        if modem is None:
            return ret

        ret['modem_signal'] = self._at_modem.signal(modem['port_control'])
        ret['modem_info'] = self._at_modem.model(modem['port_control'])
        ret['operator_info'] = self._at_modem.operator(modem['port_control'])
        ret['network_info'] = self._at_modem.network_info(modem['port_control'])
        ret['address'] = tools.get_address('ppp0')
        ret['ifstate'] = tools.get_operstate('ppp0')
        ret['ifname'] = 'ppp0'
        return ret

    def _get_modem(self):
        """Determine right USB modem interface
        """
        for i in tools.netifaces():
            if i['ifname'] == 'ppp':
                break
        else:
            return None

        usbid = i['usbid']
        if usbid not in MODEM_DEFS:
            return None

        ports = i['ttys']
        modem = dict(MODEM_DEFS[usbid])
        if usbid == '12d1:1506' and len(ports) == 2:
            # special case E3372h with firmware 21.326.62.00.55 that have only two serial ports
            modem['control'] = 0
            modem['data'] = 1
        elif (len(ports) < modem['control'] + 1 or len(ports) < modem['data'] + 1):
            return None

        ret = {'usbid': usbid,
               'ports': ports,
               'model': modem['desc'],
               'port_control': '/dev/' + ports[modem['control']],
               'port_data': '/dev/' + ports[modem['data']]}

        return ret

    def _pppd_params(self, apn, number, user, password):
        """Return pppd command string.
        """
        try:
            modem = self._get_modem()
        except Exception:
            return None

        if modem is None:
            return None

        # get pppd command line parameters
        pppd_params = PPPD_PARAMS % (modem['port_data'], CHAT_PATH, CHATSCRIPT_PATH)
        if user is not None and user:
            pppd_params += ' user "%s"' % user
            if password is not None:
                pppd_params += ' password "%s"' % password
        else:
            pppd_params += ' noauth'

        # create chatscript file
        with open(CHATSCRIPT_PATH, 'w') as f:
            f.write(CHATSCRIPT % (apn, number))

        return pppd_params

    def _terminate_pppd(self):
        """Disconnect pppd session.
        """
        # terminate all the running pppd procesess
        for i in psutil.process_iter():
            try:
                if i.name().startswith('ppp'):
                    i.terminate()
            except Exception:
                pass

    def clean(self):
        self._terminate_pppd()
