# NetConnect

LAN, LTE, WiFi connection manager suitable for embedded devices. Takes care of a configured connection and keeps it up to be persistent (reconnects are performed whenever a connection is lost).

The project is divided to two parts:

* Backend - this repository that contains backend source files.
* [Frontend](https://github.com/RehiveTech/netconnect-frontend) - javascript source repository.

## Dependencies

* `fping` (`/usr/bin/fping`) - ping test
* `pppd` (`/usr/sbin/pppd`) - LTE modem ppp connection
* `chat` (`/usr/sbin/chat`) - LTE modem chat script
* `wpa_supplicant` (`/sbin/wpa_supplicant`) - wifi client
* `wpa_cli` (`/sbin/wpa_cli`) - wpa supplicant command interface
* `hostapd` (`/usr/sbin/hostapd`) - sw access point

## Build

### Requirements

* Kernel modules `option`, `usb_wwan` (usually comprised in distribution kernels).
* `usb_modeswitch` - for switching a modem to correct a mode. Deb packages `usb-modeswitch`, `usb-modeswitch-data`
* `pppd` - connection dialing. Package `ppp`.
* `systemd` - only systemd based linux systems are supported.
* `python3` - the application is written in python3. Tested with `python 3.5` but higher version should also works.
* Python3 virtual environment to keep application in its own isolated environment. Package `python3-venv`.
* Python3 libraries for development purposes. Package `python3-dev`.
* Build tools for development purposes. Package `build-essentials`.

### Compilation for development purposes

```
make build-env  # prepare python virtual environment
make build-src  # install python sources
make build-run  # run application from local build directory
```

[Frontend](https://github.com/RehiveTech/netconnect-frontend) must compiled and placed in `build/static` directory.

## Debian package

* Version number can be changed in `setup.py` on the row `__version__ = '0.9.0'`.
* Library dependencies are defined on `install_requires` line.
* [Frontend](https://github.com/RehiveTech/netconnect-frontend) build must be placed in `src/static` directory.

To build the package simply run:

```
make deb-package
```

Deb package will be generated in the parent directory.

## /etc/resolv.conf

The application also takes care of DNS name resolution servers that keep updated according to the currently active connection. For this reason is needed to point out `/etc/resolv.conf` to `/var/run/netconnect/resolv.conf`.

```
rm /etc/resolv.conf
ln -s /var/run/netconnect/resolv.conf /etc/resolv.conf
```

This is done automatically in case of debian package installation (see `debian/netconnect.postinst`).

## Configuration

Is placed in `/etc/netconnect/config.json`. Usually there is no need to change it via command line.

```
{
    "connection_type": "lan",
    "test_host": "www.google.com",
    "lan": {
        "ipv4": {
            "dhcp": true,
            "dns": [
                "8.8.8.8",
                "8.8.4.4"
            ],
            "gw": "10.10.10.1",
            "ip": "10.10.10.10",
            "netmask": "255.255.255.0"
        },
        "name": "eth0"
    },
    "lte": {
        "apn": "internet",
        "number": "*99#",
        "password": null,
        "user": null
    },
    "wifi": {
        "ipv4": {
            "dhcp": true
        },
        "ssid": "RT"
        "key": "rtoff789",
        "name": "wlan0",
    }
}

```

## Testing

Build python environment based on `requirements.txt`
```
make build-env && make build-src
```
Run application (or use the one that is running as a daemon).
```
make build-run
```
Base unit tests are in `test/test_base.py` module. There are several test targets but basically, for each connection there are three options
* `test_connect` - connect a network with a given configration. Repeat call even with same configuration leads to network restart.
* `test disconnect` - disconnect the network and set down interface state.
* `test_info` - information about connection.

So if we want to test connect via wifi we have to run test as following or similarly for above targets. Test modules are named `LTE`, `WifiClient`, `WifiAP` and `LAN`. So these tests are specified for each particular connection.
```
make test TEST=WifiAP.test_connect
```

To test Wifi scanning. In case wifi is in INACTIVE state or iface is not up, function returns `None`.
```
make test TEST=WifiAP.test_scan
```

Get higher level online status. Returns status of all the modules, online state and last time of online check (unix timestamp).
```
make test TEST=Base.test_status
```

Set higher level condiguration
```
make test TEST=Base.test_config
```

Get list of interfaces
```
make test TEST=Base.test_interfaces
```

Trigger online check
```
make test TEST=Base.test_interfaces
```

To disable a module, config pro given connection must be `None`.
```
{
    lte: None
}
```

* Network device can be identified by
    * `name` (eg. eth0)
    * `usb_port` number (eg. 4-1:1.3)
    * `mac` (eg. 0255AABDFF55)
* Parameter `metric` determines communication priority in case multiple connection with given default gateway.
* IP configuration is specified by `ipv4` parameter.
    * For dhcp `{'dhcp': True}`
    * For static IP `{'ip': '192.168.1.111', 'netmask': '255.255.255.0', 'gw': '192.168.1.1', 'dns': ['8.8.8.8', '8.8.4.4']}`
