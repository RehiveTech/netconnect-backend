import socket
from multiprocessing.pool import Pool


def _resolve(host):
    try:
        ret = socket.gethostbyname(host)
    except Exception:
        return None
    return ret


def dnslookup(host, timeout=3):
    """DNS lookup with timeout.
    """
    res = None
    pool = Pool(processes=1)
    async_result = pool.apply_async(_resolve, (host, ))
    try:
        res = async_result.get(timeout=timeout)
    except Exception:
        pool.terminate()
    else:
        pool.close()
    pool.join()
    return res
