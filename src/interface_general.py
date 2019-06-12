import zmq


class InterfaceGeneral():

    # Used class variables
    _child_class = None  # Link to child heritaging class
    _iface = None
    _zmq_context = None

    class InterfaceException(Exception):
        """Custom Interface expcetion for handlin interface errors.
        """
        pass

    def __init__(self, child_class, iface):
        """Parent class which every interface module is herritaging from.

        :param child_class: Link to the child class implementing custom
                            methods.
        :param iface: A name of the interface as defined for Zero MQ.
        """
        self._child_class = child_class
        self._iface = iface
        self._zmq_context = zmq.Context.instance()

    def loop(self):
        """Message receiving blocking function. Supposed to be used in the
        appropriate module only. Parses incoming messages and calls appropriate
        functions from the module.
        """
        rep_socket = self._zmq_context.socket(zmq.REP)
        rep_socket.bind(self._iface)

        while True:
            msg = rep_socket.recv_json()
            resp = {}
            resp['mod_name'] = self._MOD_NAME

            if getattr(self, msg['func']).__code__ == \
               getattr(self._child_class, msg['func']).__code__:
                # Called function has not been implemented
                # in the child class (probably in ModInterface).
                resp['status'] = 'error'
                resp['message'] = 'Function "%s" is not implemented.'\
                                  % msg['func']
            else:
                # print(msg)
                # call a function implemented in ModInterface class
                func = getattr(self, msg['func'])
                resp['message'] = func(*msg['params'])
                resp['status'] = 'success'

            rep_socket.send_json(resp)

    def _send_cmd(self, func, params, timeout=5000):
        """Connect to the socket and send a message specified by calling function
        and its parameters.

        :param func: Name of called fucntion.
        :param params: List of parameters for the given function.
        :param timeout: Timeout on send and receive in milliseconds
        :returns: JSON response with the result.
        """

        context = zmq.Context()
        req_socket = context.socket(zmq.REQ)

        # https://stackoverflow.com/questions/26915347/zeromq-reset-req-rep-socket-state
        # RCVTIMEO to prevent forever block
        req_socket.setsockopt(zmq.RCVTIMEO, timeout)
        # SNDTIMEO is needed since script may not up up yet
        req_socket.setsockopt(zmq.SNDTIMEO, timeout)
        req_socket.setsockopt(zmq.REQ_RELAXED, 1)
        req_socket.setsockopt(zmq.REQ_CORRELATE, 1)
        # do not queue any message (even try/except will not block)
        req_socket.setsockopt(zmq.LINGER, 0)

        req_socket.connect(self._iface)

        msg = {}
        msg['src_mid'] = self._MOD_NAME
        msg['func'] = func
        msg['params'] = params

        try:
            req_socket.send_json(msg)
            ret = req_socket.recv_json()
            req_socket.close()
        except zmq.error.Again:
            req_socket.close()
            raise
        except Exception:
            raise
        finally:
            context.destroy()

        if ret['status'] == 'error':
            raise self.InterfaceException(ret['mod_name'] + ' ' + ret['message'])

        context.destroy()
        return ret

    def destroy(self):
        self._zmq_context.destroy()
