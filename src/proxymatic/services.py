import re
from copy import copy
from random import randint

class Server(object):
    def __init__(self, ip, port, hostname):
        self.ip = ip
        self.port = port
        self.hostname = hostname
        self.weight = 500
        self.maxconn = None

    def __cmp__(self, other):
        if not isinstance(other, Server):
            return -1
        return cmp((self.ip, self.port, self.weight, self.maxconn), (other.ip, other.port, other.weight, other.maxconn))

    def __hash__(self):
        return hash((self.ip, self.port, self.weight, self.maxconn))

    def __str__(self):
        extra = []
        if self.weight != 500:
            extra.append("weight=%d" % self.weight)
        if self.maxconn:
            extra.append("maxconn=%d" % self.maxconn)

        result = '%s:%s' % (self.ip, self.port)
        if extra:
            result += '(%s)' % ','.join(extra)
        return result

    def __repr__(self):
        return 'Server(%s, %s, %s, %s)' % (repr(self.ip), repr(self.port), repr(self.weight), repr(self.maxconn))

    def clone(self):
        return copy(self)

    def setWeight(self, weight):
        clone = self.clone()
        clone.weight = weight
        return clone

    def setMaxconn(self, maxconn):
        clone = self.clone()
        clone.maxconn = maxconn
        return clone

class Service(object):
    def __init__(self, name, source, port, protocol, application='binary', healthcheck=False, healthcheckurl='/', timeoutclient=None, timeoutserver=None):
        self.name = name
        self.source = source
        self.port = port
        self.protocol = protocol
        self.application = application
        self.healthcheck = healthcheck
        self.healthcheckurl = healthcheckurl
        self.timeoutclient = timeoutclient
        self.timeoutserver = timeoutserver
        self.servers = set()
        self.slots = []

        # Check if there's a port override
        match = re.search('.@(\d+)$', self.name)
        if match:
            self.name = self.name[0:-(len(match.group(1))+1)]
            self.port = int(match.group(1))

    def clone(self):
        clone = Service(self.name, self.source, self.port, self.protocol, self.application, self.healthcheck, self.healthcheckurl, self.timeoutclient,
                        self.timeoutserver)
        clone.servers = set(self.servers)
        clone.slots = list(self.slots)
        return clone

    def __str__(self):
        # Represent misc. service attributes as k=v pairs, but only if their value is not None
        service_attributes = ['timeoutclient', 'timeoutserver']
        service_options = ['%s=%s' % (attr, getattr(self, attr)) for attr in service_attributes if getattr(self, attr) is not None]

        # Only use healthcheckurl if healtcheck has a meaningful value
        if self.healthcheck:
            service_options.append('healtcheck=%s' % self.healthcheck)
            service_options.append('healthcheckurl=%s' % self.healthcheckurl)

        return '%s:%s/%s%s -> [%s]' % (
            self.name, self.port, self.application if self.application != 'binary' else self.protocol,
            '(%s)' % ','.join(service_options) if service_options else '',
            ', '.join([str(s) for s in sorted(self.servers)]))

    def __repr__(self):
        return 'Service(%s, %s, %s, %s, %s)' % (repr(self.name), repr(self.port), repr(self.protocol), repr(self.application), repr(sorted(self.servers)))

    def __cmp__(self, other):
        if not isinstance(other, Service):
            return -1
        return cmp((self.name, self.port, self.protocol, self.servers), (other.name, other.port, other.protocol, other.servers))

    def __hash__(self):
        return hash((self.name, self.port, self.protocol, self.servers))

    @property
    def portname(self):
        return re.sub('[^a-zA-Z0-9]', '_', str(self.port))

    @property
    def marathonpath(self):
        ret = ''
        for s in self.name.split('.'):
            if ret is not '':
                ret = s + '.' + ret
            else:
                ret = s
        return ret

    def update(self, other):
        """
        Returns an new updated Service object
        """
        clone = self.clone()
        clone.name = other.name
        clone.source = other.source
        clone.port = other.port
        clone.protocol = other.protocol
        clone.timeoutclient = other.timeoutclient
        clone.timeoutserver = other.timeoutserver

        for server in clone.servers - other.servers:
            clone._remove(server)

        for server in other.servers - clone.servers:
            clone._add(server)

        return clone

    def addServer(self, server):
        clone = self.clone()
        clone._add(server)
        return clone

    def setApplication(self, application):
        clone = self.clone()
        clone.application = application
        return clone

    def _add(self, server):
        self.servers.add(server)

        # Keep servers in the same index when they're added
        for i in range(len(self.slots)):
            if not self.slots[i]:
                self.slots[i] = server
                return

        # Not present in list, just insert randomly
        self.slots.insert(randint(0, len(self.slots)), server)

    def _remove(self, server):
        self.servers.remove(server)

        # Set the server slot to None
        for i in range(len(self.slots)):
            if self.slots[i] == server:
                del self.slots[i]
                return

        raise KeyError(str(server))
