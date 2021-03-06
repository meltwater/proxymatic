import logging
import json
import socket
import traceback
import urllib2
from urlparse import urlparse
from proxymatic.services import Server, Service
from proxymatic import util

class RegistratorEtcdDiscovery(object):
    def __init__(self, backend, url):
        self._backend = backend
        self._url = urlparse(url)
        self._healthy = False
        self.priority = 5

    def isHealthy(self):
        return self._healthy

    def start(self):
        def action():
            # Fetch all registered service instances
            geturl = 'http://%s/v2/keys%s?recursive=true' % (self._url.netloc, self._url.path)
            logging.debug("GET registrator services from %s", geturl)
            response = urllib2.urlopen(geturl)
            waitIndex = int(response.info().getheader('X-Etcd-Index')) + 1
            services = self._parse(response.read())
            self._backend.update(self, services)
            logging.info("Refreshed services from registrator store %s", self._url.geturl())

            # Signal that we're up and running
            self._healthy = True

            # Long poll for updates
            pollurl = 'http://%s/v2/keys%s?wait=true&recursive=true&waitIndex=%s' % (self._url.netloc, self._url.path, waitIndex)
            urllib2.urlopen(pollurl).read()

        # Run action() in thread with retry on error
        util.run(action, "etcd error from '" + self._url.geturl() + "': %s")

    def _parse(self, content):
        services = {}
        state = json.loads(content)

        for node in util.rget(state, 'node', 'nodes') or []:
            for backend in util.rget(node, 'nodes') or []:
                try:
                    parts = backend['key'].split(':')
                    port = int(parts[2])
                    protocol = parts[3] if len(parts) > 3 else 'tcp'
                    key = '%s/%s' % (port, protocol.lower())

                    # Resolve hostnames since HAproxy wants IP addresses
                    endpoint = backend['value'].split(':')
                    ipaddr = socket.gethostbyname(endpoint[0])
                    server = Server(ipaddr, endpoint[1], endpoint[0])

                    # Append backend to service
                    if key not in services:
                        name = node['key'].split('/')[-1]
                        services[key] = Service(name, 'registrator:%s' % self._url.geturl(), port, protocol)
                    services[key] = services[key].addServer(server)
                except Exception as e:
                    logging.warn("Failed to parse service %s backend %s/%s: %s", node['key'], backend['key'], backend['value'], str(e))
                    logging.debug(traceback.format_exc())

        return services
