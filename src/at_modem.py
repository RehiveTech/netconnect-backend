import re
from multiprocessing import Lock
import serial


class ATModem(object):
    """Parse AT command response

    CMS and CME error codes for GSM. CME and CMS errors needs to be enabled
    firts by AT+CMEE=2.
    - http://www.smssolutions.net/tutorials/gsm/gsmerrorcodes/

    """
    _at_response_line = ''  # at response line
    _at_response = None  # parsed response

    _final_responses = ['OK',
                        'ERROR',
                        'NO CARRIER',
                        '+CME ERROR:',
                        '+CMS ERROR:']

    def __init__(self):
        self._serial_lock = Lock()

    def reset(self):
        self._at_response_line = ''
        self._at_response = None

    def feed(self, char):
        """Feed the parser char by char.
        """
        self._at_response_line += char

        # parse and check for complete response
        matches = re.findall('(?=\\r\\n(.+?)\\r\\n)', self._at_response_line)

        if matches:
            for j in self._final_responses:
                # there is CME or CMS error message
                if j[-1] == ':' and matches[-1].startswith(j):
                    self._at_response = matches
                    break
                if matches[-1] == j:
                    self._at_response = matches
                    break

    def response(self):
        """Return complete response or None
        """
        return self._at_response

    def send(self, dev, atcmd, expect_ok=True):
        """Send AT command.

        :returns: None in case of error
        """
        if dev is None:
            return None

        ret = None
        atcmd = atcmd + '\r'
        self.reset()

        self._serial_lock.acquire()
        try:
            ser = serial.Serial(dev, baudrate=115200, timeout=0.5, dsrdtr=True, rtscts=True, write_timeout=1)
            ser.write(atcmd.encode())
            for i in range(100):  # maximum chars to be read
                self.feed(ser.read(1).decode())
                ret = self.response()
                if ret is not None:
                    break

        except Exception:
            pass
        self._serial_lock.release()

        if not ret:
            return None

        if expect_ok is True and ret[-1] != 'OK':
            return None

        return ret

    def signal(self, dev=None):
        """
        Signal strength levels
        ======================
        Marginal - Levels of -95dBm or lower. At these sort of levels, it is very
        likely that you may suffer low throughput and disconnects due to cell l
        oading/breathing even with an outdoor antenna.

        OK - Levels of -85dBm to -95dBm. Probably worth considering an outdoor gain
        type antenna. Could suffer poor throughput and disconnects due to cell
        loading/breathing.

        Good - Levels between -75dBm and -85dBm - normally no problem holding a
        connection with this sort of level (even with cell breathing) without the use
        of an external antenna.

        Excellent - levels above -75dBm. Should not be affected by cell
        breathing/loading and should not require an external antenna.
        """
        res = self.send(dev, 'AT+CSQ')
        if res is None:
            return None
        res = re.match('\+CSQ: (?P<rssi>[0-9]{1,3}),(?P<ber>[0-9]{1,3})',
                       res[0])
        if res is None or res.group('rssi') is None or res.group('ber') is None:
            return None

        ret = {'rssi': None, 'ber': None, 'level': None}
        if res.group('rssi') is not None:
            rssi = int(res.group('rssi'))
            ret['rssi'] = -(113 - (rssi * 2))
            if rssi < 2 or rssi > 30:
                ret['rssi'] = -113
            # level on scale 0 - 3
            if ret['rssi'] <= -95:
                ret['level'] = (0, 3)
            elif ret['rssi'] <= -85:
                ret['level'] = (1, 3)
            elif ret['rssi'] <= -75:
                ret['level'] = (2, 3)
            else:
                ret['level'] = (3, 3)

        if res.group('ber') is None:
            return None

        ret['ber'] = res.group('ber')
        return ret

    def registered(self, dev=None):
        res = self.send(dev, 'AT+CREG?')
        if res is None:
            return None

        ret = False

        res = re.match('\+CREG: (?P<n>[0-9]),(?P<stat>[0-9]).*', res[0])
        if res is None:
            return None

        if res.group('stat') is not None:
            if res.group('stat') == '5' or res.group('stat') == '1':
                ret = True

        return ret

    def network_info(self, dev=None):
        res = self.send(dev, 'AT+CREG?')
        if res is None:
            return None

        ret = {}
        ret['registered'] = False

        res = re.match('\+CREG: (?P<n>[0-9]),(?P<stat>[0-9]).*', res[0])
        if res.group('stat') is not None:
            if res.group('stat') == '5' or res.group('stat') == '1':
                ret['registered'] = True

        ret['sim_ready'] = True
        if ret['registered'] is False:
            res = self.send(dev, 'AT+CPIN?', expect_ok=False)
            if res is not None:
                res = re.match('\+CPIN: READY.*', res[0])
                if not res:
                    ret['sim_ready'] = False
            else:
                ret['sim_ready'] = False

        return ret

    def model(self, dev=None):
        res = self.send(dev, 'AT+CGMI')
        if res is None:
            return None
        ret = {}
        ret['vendor'] = res[0].title()

        res = self.send(dev, 'AT+CGMM')
        if res is None:
            return None
        ret['product'] = res[0]
        ret['rev'] = ''

        try:
            res = self.send(dev, 'ATI')
            if res is not None:
                res = re.findall('^Revision: (?P<rev>.*)$', res[2], re.M)
                ret['rev'] = res[0]
        except Exception:
            pass

        return ret

    def operator(self, dev=None):
        res = self.send(dev, 'AT+COPS=3,0')
        if res is None:
            return None

        res = self.send(dev, 'AT+COPS?')
        if res is None:
            return None

        res = re.match('\+COPS:.*?,.*?,"(?P<operator>(.*))"', res[0])
        if res is None or res.group('operator') is None:
            return None

        return {'operator': res.group('operator')}

    def ndis_connect(self, apn='internet', dev=None):
        res = self.send(dev, 'AT^NDISDUP=1,1,"%s"\r\n' % apn)

    def ndis_disconnect(self, dev=None):
        res = self.send(dev, 'AT^NDISDUP=1,0')

    def ndis_connected(self, dev=None):
        res = self.send(dev, 'AT^NDISSTATQRY?', expect_ok=False)  # returns '^NDISSTATQRY: 0,,,"IPV4"'
        # AT^NDISSTATQRY?
        # 0 Disconnected
        # 1 Connected
        # 2 In connection (reported only when the device is automatically
        return res[0][14] == '1' or res[0][14] == '2'
