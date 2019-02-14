import os
import os.path
from setuptools import setup

__version__ = '0.9.2'

Description = """/
Network connection daemon that takes care of LTE, WiFi and LAN connections.
"""

def package_files(directory):
    paths = []
    for (path, directories, filenames) in os.walk(directory):
        for filename in filenames:
            paths.append(os.path.join('..', path, filename))
    return paths

extra_files = package_files('src/static')

# setup parameters
setup(name='NetConnect',
      version=__version__,
      description='Network connection daemon',
      long_description=Description,
      author='Pepa Hajek',
      packages=['src', 'misc'],
      author_email='hajek@rehivetech.com',
      entry_points={
          'console_scripts': ['netconnect = src.run:main']
      },
      install_requires=['pyzmq', 'pyserial', 'pyroute2', 'wheel', 'psutil', 'connexion', 'flask-cors', 'swagger_ui_bundle'],
      package_data={'': ['*.json', '*.yaml'] + extra_files}
)
