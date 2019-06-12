import json
import os
import logging
import time
import connexion
from multiprocessing import Process, Manager, Event
from flask_cors import CORS
from flask import request
from netconnect import main as netconnect_app  # noqa
from interface_netconnect import InterfaceNetconnect  # noqa

BIN_PATH = os.path.dirname(os.path.realpath(__file__))
ROOT_PATH = os.path.dirname(BIN_PATH)
CONFIG = '/etc/netconnect/config.json'
SWAGGER_SPECIFICATION = BIN_PATH + '/swagger.yaml'
LOG_LEVEL = logging.DEBUG
APIPORT = 8080

# default application configuration
defconfig = {
    'lte': {
        'apn': 'internet.t-mobile.cz',
        'number': '*99#',
        'user': None,
        'password': None,
    },
    'wifi': {
        'name': 'wlan0',
        'ssid': 'RT',
        'key': 'rtoff789',
        'ipv4': {
            'dhcp': True,
        },
    },
    'lan': {
        'name': 'eth0',
        'ipv4': {
            'dhcp': True,
            'ip': '10.10.10.10',
            'netmask': '255.255.255.0',
            'gw': '10.10.10.1',
            'dns': ['8.8.8.8', '8.8.4.4']
        },
    },
    'connection_type': 'lan',
    'ap_timeout': 60,
    'ap_key': None,
}

# wifi accesspoint configuration
wifi_ap = {
    'name': 'wlan0',
    'wifi_ap': {
        'ssid': 'aurora-netconnect',
        'channel': 6,
    },
    'ipv4': {
        'ip': '10.10.10.10',
        'netmask': '255.255.255.0',
    },
}


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
    logging.getLogger('connexion').setLevel(logging.WARNING)
    logging.getLogger('openapi_spec_validator').setLevel(logging.WARNING)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)


def get_netconnect_config(d_cfg):
    """Convert app configuration to netconnect configuration
    """
    nc_cfg = {}
    if d_cfg['connection_type'] == 'wifi':
        wcfg = d_cfg['wifi']
        cfg = {}
        cfg['wifi_client'] = {}

        cfg['name'] = 'wlan0'
        cfg['ipv4'] = wcfg['ipv4']
        cfg['wifi_client']['ssid'] = wcfg['ssid']
        cfg['wifi_client']['key'] = wcfg['key']

        nc_cfg['lte'] = None
        nc_cfg['wifi_client'] = cfg

    elif d_cfg['connection_type'] == 'lte':
        cfg = {}
        cfg['name'] = 'ppp'
        cfg['metric'] = 300
        cfg['lte'] = d_cfg['lte']
        nc_cfg['lte'] = cfg
        nc_cfg['wifi_client'] = None

    else:
        nc_cfg['wifi_client'] = None
        nc_cfg['lte'] = None

    nc_cfg['lan'] = {'ipv4': {}}
    nc_cfg['lan']['ipv4'] = d_cfg['lan']['ipv4']
    nc_cfg['lan']['name'] = d_cfg['lan']['name']

    return nc_cfg


# API #########################################################################
def refresh():
    store['counter'] = 60
    return {}


def get_config():
    return store['config']


def set_config(body):
    log = logging.getLogger(__name__)
    ncfg = body['config']
    log.info('Saving configuration: ' + json.dumps(ncfg, indent=4, sort_keys=True))
    cfg = store['config']

    if 'lte_apn' in ncfg: cfg['lte']['apn'] = ncfg['lte_apn']
    if 'lte_number' in ncfg: cfg['lte']['number'] = ncfg['lte_number']
    if 'wifi_ssid' in ncfg: cfg['wifi']['ssid'] = ncfg['wifi_ssid']
    if 'wifi_key' in ncfg: cfg['wifi']['key'] = ncfg['wifi_key']
    if 'wifi_ip' in ncfg: cfg['wifi']['ipv4']['ip'] = ncfg['wifi_ip']
    if 'wifi_netmask' in ncfg: cfg['wifi']['ipv4']['netmask'] = ncfg['wifi_netmask']
    if 'wifi_gw' in ncfg: cfg['wifi']['ipv4']['gw'] = ncfg['wifi_gw']
    if 'wifi_dns1' in ncfg: cfg['wifi']['ipv4']['dns'] = [ncfg['wifi_dns1'], ncfg['wifi_dns2']]
    if 'wifi_dhcp' in ncfg: cfg['wifi']['ipv4']['dhcp'] = ncfg['wifi_dhcp']
    if 'wifi_ip' in ncfg: cfg['wifi']['ipv4']['ip'] = ncfg['wifi_ip']
    if 'wifi_netmask' in ncfg: cfg['wifi']['ipv4']['netmask'] = ncfg['wifi_netmask']
    if 'wifi_gw' in ncfg: cfg['wifi']['ipv4']['gw'] = ncfg['wifi_gw']
    if 'wifi_dns1' in ncfg: cfg['wifi']['ipv4']['dns'] = [ncfg['wifi_dns1'], ncfg['wifi_dns2']]
    if 'lan_dhcp' in ncfg: cfg['lan']['ipv4']['dhcp'] = ncfg['lan_dhcp']
    if 'lan_ip' in ncfg: cfg['lan']['ipv4']['ip'] = ncfg['lan_ip']
    if 'lan_netmask' in ncfg: cfg['lan']['ipv4']['netmask'] = ncfg['lan_netmask']
    if 'lan_gw' in ncfg: cfg['lan']['ipv4']['gw'] = ncfg['lan_gw']
    if 'lan_dns1' in ncfg: cfg['lan']['ipv4']['dns'] = [ncfg['lan_dns1'], ncfg['lan_dns2']]
    if 'connection_type' in ncfg: cfg['connection_type'] = ncfg['connection_type']
    if 'ap_timeout' in ncfg: cfg['ap_timeout'] = int(ncfg['ap_timeout'])
    if 'ap_key' in ncfg: cfg['ap_key'] = ncfg['ap_key']

    try:
        with open(CONFIG, 'w') as f:
            f.write(json.dumps(cfg, indent=4, sort_keys=True))
        store['config'] = cfg
    except Exception as e:
        log.error('Cannot save configuration: ' + str(e))

    store['counter'] = 1  # apply changes
    return {}


def wifi_scan():
    return store['scan_result']


def status():
    log = logging.getLogger(__name__)
    i_n = InterfaceNetconnect()
    ret = {}
    try:
        ret['lan'] = i_n.connection_info('lan')
        ret['wifi_client'] = i_n.connection_info('wifi_client')
        ret['lte'] = i_n.connection_info('lte')
        ret['ncstatus'] = i_n.status()
        ret['counter'] = store['counter']
    except Exception as e:
        log.error('Cannot get status information: ' + str(e))
        return {}, 405

    return ret


# Webserver stuff
app = connexion.App(__name__, specification_dir='.', debug=False)
app.app.static_url_path = ''
CORS(app.app, resources={r"/*": {"origins": "*"}})
app.add_api(SWAGGER_SPECIFICATION)


@app.app.errorhandler(404)
def page_not_found(e):
    try:
        return app.app.send_static_file(request.path[1:])
    except Exception as e:
        return str(e), 404


@app.route('/')
def index():
    return app.app.send_static_file('index.html')


def webserver():
    app.run(host='0.0.0.0', port=APIPORT, threaded=True)


# MAIN ########################################################################
init_logger()
log = logging.getLogger(__name__)
Process(target=netconnect_app).start()

config = defconfig

try:
    with open(CONFIG, 'r') as f:
        config = json.loads(f.read())
except Exception as e:
    log.warning('Configuration file is not available yet')

log.info(json.dumps(config, indent=4, sort_keys=True))
store = Manager().dict()
store['config'] = config
store['counter'] = config['ap_timeout']

i_n = InterfaceNetconnect()
i_n.wait_for_ready()
ncfg = get_netconnect_config(config)
# scan for wifi network
i_n.connect({'wifi_client': {'name': 'wlan0', 'wifi_client': {'ssid': 'scan'}, 'ipv4': {'dhcp': True}},
             'wifi_ap': None})
time.sleep(1)
store['scan_result'] = i_n.wifi_scan()
# set wifi access point
ncfg = get_netconnect_config(config)
if config.get('ap_key', None) is not None:
    wifi_ap['wifi_ap']['key'] = config.get('ap_key', None)

ncfg['wifi_ap'] = wifi_ap
ncfg['wifi_client'] = None
i_n.connect(ncfg)
# start webserver
time.sleep(5)
Process(target=webserver).start()

while True:
    if store['counter'] > 1:
        store['counter'] -= 1

    elif store['counter'] == 1:
        # timeout is over or changes has been applied from UI
        # disable WiFi AP
        i_n.wait_for_ready()
        i_n.connect({'wifi_ap': None})
        ncfg = get_netconnect_config(store['config'])
        i_n.connect(ncfg)
        store['counter'] = 0

    time.sleep(1)
