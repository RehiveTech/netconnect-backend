import os
import glob
import http.client as httplib
import shlex
from fs import USB
from pathlib import Path
from subprocess import Popen, PIPE
from pyroute2 import IPRoute

from messenger import Messenger

FPING_PATH = '/usr/bin/fping'


def touples2dict(touples):
    """"Counvert list of touples to dict
    [('a': 1), ('b': 2)] => {'a': 1, 'b':2}
    """
    ret = {}
    for i in touples:
        ret[i[0]] = i[1]
    return ret


def get_default_route():
    """Get list of default routes
    """
    ret = {'ifname': None, 'ip': None}

    ipr = IPRoute()
    defroutes = ipr.get_default_routes()
    links = ipr.get_links()
    ipr.close()

    prio = None
    oif = None
    gw = None

    try:
        for i in defroutes:
            attrs = touples2dict(i['attrs'])
            if prio is None or prio > attrs.get('RTA_PRIORITY', 0):
                prio = attrs.get('RTA_PRIORITY', 0)
                oif = attrs['RTA_OIF']
                gw = attrs.get('RTA_GATEWAY', None)

        if oif is not None:
            for link in links:
                if link.get('index') == oif:
                    ret['ifname'] = link.get_attr('IFLA_IFNAME')
                    ret['ip'] = gw
                    break
    except Exception:
        pass
    return ret


def iface_down(ifname):
    """Flush all ip addresses belonging to the interface.
    """
    if ifname is None:
        return

    ipr = IPRoute()
    try:
        ipr.flush_addr(label=ifname)
        x = ipr.link_lookup(ifname=ifname)[0]
        ipr.link('set', index=x, state='down')
    except Exception:
        pass
    ipr.close()


def get_address(ifname):
    """Get first interface IP address with netmask in format
    '192.168.1.1/24'
    """
    if ifname == None:
        return

    ipr = IPRoute()
    try:
        for i in ipr.get_addr(label=ifname):
            if 'prefixlen' in i and 'attrs' in i:
                for ii in i['attrs']:
                    if ii[0] == 'IFA_LOCAL':
                        ipr.close()
                        return ii[1] + '/' + str(i['prefixlen'])
    except Exception as e:
        pass
    ipr.close()

def get_operstate(ifname):
    """Get operstate of the interface
    """
    if ifname == None:
        return

    ret = None
    ipr = IPRoute()
    try:
        ret = ipr.get_links(ifname=ifname)[0].get_attr('IFLA_OPERSTATE')
    except Exception as e:
        pass
    ipr.close()

    return ret

def systemd_restart(service):
    """Enable and start systemd service.
    """
    os.system('/bin/systemctl restart ' + service)


def remove_networkd_file(name, networkd_path='/run/systemd/network'):
    """Test whether networkd file exists and if so its removed.
    :returns: T/F depending if file was removed.
    """
    file = networkd_path + '/netconnect_' + name + '.network'
    try:
        os.remove(file)
    except Exception:
        return False
    return True


def write_if_changed(filepath, content):
    """If changed write content to the file.

    :returns: T/F depending if the file was changed.
    """
    if(os.path.isfile(filepath)):
        with (open(filepath, 'r')) as f:
            if f.read() == content:
                return False
    with open(filepath, 'w') as f:
        f.write(content)

    return True


def gen_systemd_networkd(name, ipv4_cfg, mac=None, networkd_path='/run/systemd/network',
                         dhcp_server=False, metric=128, ifname=None):
    """Generate systemd newtork file in /run/systemd/network.
    Created file is named automatically with 'neconnect-' and postfix '.network'.

    :param ipv4_cfg: Dict with ipv4 parameters.
    :param dhcp: If T start DHCP server.
    :param name: Configuration name.
    """
    os.makedirs(networkd_path, exist_ok=True)
    file = networkd_path + '/netconnect_' + name + '.network'

    content = ''
    content += '[Match]\n'
    if mac is not None:
        content += 'MACAddress=%s\n' % mac
    if ifname is not None:
        content += 'Name=%s\n' % ifname

    content += '[Network]\n'
    dhcp = ipv4_cfg.get('dhcp', False)
    if dhcp is True:
        content += 'DHCP=ipv4\n'
        content += '[DHCP]\n'
        content += 'RouteMetric=%s\n' % metric
    else:
        mask = ipv4_cfg.get('netmask', '255.255.255.0')
        content += 'Address=%s/%s\n' % (ipv4_cfg.get('ip', '169.254.255.254'), mask2cidr(mask))
        content += 'Metric=%s\n' % metric
        if 'gw' in ipv4_cfg:
            content += 'Gateway=%s\n' % (ipv4_cfg['gw'])
        if 'dns' in ipv4_cfg:
            for i in ipv4_cfg['dns']:
                content += 'DNS=%s\n' % (i)

    if dhcp_server is True:
        content += 'DHCPServer=yes\n'

    if(os.path.isfile(file)):
        with (open(file, 'r')) as f:
            if f.read() == content:
                return False

    with open(file, 'w') as f:
        f.write(content)

    return True


def mask2cidr(mask):
    """Get cidr number bits from netmask.
    """
    try:
        return sum([bin(int(x)).count("1") for x in mask.split(".")])
    except Exception:
        return 24


def cidr2netmask(cidr):
    cidr = int(cidr)
    mask = (0xffffffff >> (32 - cidr)) << (32 - cidr)
    return (str((0xff000000 & mask) >> 24) + '.' +
            str((0x00ff0000 & mask) >> 16) + '.' +
            str((0x0000ff00 & mask) >> 8) + '.' +
            str((0x000000ff & mask)))


def keys_in_dict(keys, d):
    """
    :returns: T/F depending if all the keys are in dict.
    """
    return set(keys) <= set(d)


def ping_test(host):
    """Find out ping availability status.
    """
    fping = FPING_PATH + ' ' + '-q -c 5 -p 10 -t 3000 ' + host
    fping = shlex.split(fping)

    pppd = Popen(fping, stderr=PIPE, stdout=PIPE)
    ret = pppd.communicate()

    # test for delimiter showing if there any packets passed
    if b',' in ret[1]:
        return True
    return False


def http_test(host):
    """Check http request
    """
    conn = httplib.HTTPSConnection(host, timeout=3)
    try:
        conn.request("HEAD", "/")
        conn.close()
    except Exception as e:
        conn.close()
        return False
    return True


def get_usb_devices(usb, devlist):
    """Recursively get network interfaces on USB bus. Result is stored in
    devlist.
    """
    for k, v in usb.items():
        for j in (getattr(v, 'interfaces', [])):

            usbid = getattr(v, 'idVendor') + ':' + getattr(v, 'idProduct')
            if os.path.isdir(j.fs_path + '/net'):
                rec = {'ifname': None, 'bus': 'usb', 'port': j.fs_name,
                       'usbid': usbid, 'iftype': 'wired'}

                for ifname in glob.glob(j.fs_path + '/net/*'):
                    rec['ifname'] = os.path.basename(ifname)

                sysnetdir = '/sys/class/net/' + rec['ifname']
                if os.path.isdir(sysnetdir + '/wireless'):
                    rec['iftype'] = 'wifi'

                if os.path.isfile(sysnetdir + '/address'):
                    rec['mac'] = Path(sysnetdir + '/address').read_text().strip()

                devlist.append(rec)

            elif j.tty is not None:
                # detect tty capable devices
                for i in devlist:
                    if 'ttys' not in i:
                        continue

                    if i['usbid'] == usbid:
                        i['ttys'].append(j.tty)
                        i['ttys'].sort()
                        break
                else:
                    rec = {'ifname': 'ppp', 'bus': 'usb', 'port': j.fs_name,
                           'usbid': usbid, 'iftype': 'gsm_modem', 'ttys': [j.tty]}
                    devlist.append(rec)

        get_usb_devices(v, devlist)


def get_netifaces():
    """Returns list of interfaces from /sys/class/net
    """
    ret = []
    for i in glob.glob('/sys/class/net/*'):
        rec = {'ifname': os.path.basename(i), 'iftype': 'wired'}
        if os.path.isfile(i + '/address'):
            rec['mac'] = Path(i + '/address').read_text().strip()
        if os.path.isdir(i + '/wireless'):
            rec['iftype'] = 'wifi'

        ret.append(rec)

    return ret


def netifaces():
    """Returns list of available interfaces.
    """
    usb = USB()
    devlist = []
    get_usb_devices(usb, devlist)

    # merge '/sys/class/net' interfaces into usb list of interfaces
    for dev in get_netifaces():
        for usb_dev in devlist:
            if dev['ifname'] == usb_dev['ifname']:
                break
        else:
            devlist.append(dev)

    return devlist


def get_iface(config):
    """Determine right USB modem interface
    """
    try:
        ifaces = netifaces()
    except Exception:
        return None

    if 'mac' in config:
        return config['mac']

    for i in ifaces:
        if 'mac' not in i or 'ifname' not in i:
            continue
        if 'name' in config and config['name'] == i['ifname']:
            return Messenger(mac=i['mac'], ifname=i['ifname'])
        elif 'usb_port' in config and 'bus' in i and config['usb_port'] == i['port']:
            return Messenger(mac=i['mac'], ifname=i['ifname'])
    return None


def write_resolvconf(filepath, nameservers):
    """Write down resolv.conf file
    """
    content = '# This file is managed by Netconnect. Do not edit.\n'
    for i in nameservers:
        content += 'nameserver %s\n' % (i)

    return write_if_changed(filepath, content)
