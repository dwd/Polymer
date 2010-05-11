#
# Copyright 2004,2005 Dave Cridland <dave@cridland.net>
#
# This file forms part of the Infotrope Python Library.
#
# The Infotrope Python Library is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# The Infotrope Python Library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with the Infotrope Python Library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
#!/usr/bin/env python

import socket
import select
import errno
import time
import threading
try:
    from dns.resolver import query as dns_query
except:
    dns_query = None

import sys

_delay = None
def set_delay( d ):
    global _delay
    d = int(d)
    if d < 0:
        raise "Cannot have negative delay."
    _delay = d/1000.0

_bandwidth = None
def set_bandwidth( b ):
    global _bandwidth
    _bandwidth = None
    if b[-1] in 'kM':
        _bandwidth = float(b[0:-1])
        if b[-1] == 'k':
            _bandwidth *= 1000
        elif b[-1] == 'M':
            _bandwidth *= 1000000
    else:
        _bandwidth = float(b)
    _bandwidth = _bandwidth/8.0

_platform_tls = True
_pyopenssl = False
_tls_stats = False

if 'sslerror' not in dir(socket):
    class foo:
        pass
    socket.sslerror = foo
    _platform_tls = False

if _platform_tls:
    import sys
    if sys.version_info[0]==2:
        if sys.version_info[1]>=4:
            if sys.version_info[2]>=1:
                _platform_tls = True
            else:
                _platform_tls = False
        else:
            _platform_tls = False
    else:
        _platform_tls = False

try:
    import OpenSSL.SSL
    _pyopenssl = True
    if 'get_cipher_name' in dir(OpenSSL.SSL.Connection):
        _tls_stats = True
except:
    class foo:
        pass
    OpenSSL = foo()
    OpenSSL.SSL = foo()
    OpenSSL.SSL.WantReadError = foo
    OpenSSL.SSL.WantWriteError = foo
    OpenSSL.SSL.ZeroReturnError = foo
    OpenSSL.SSL.SysCallError = foo
    OpenSSL.SSL.Error = foo

def platform_tls():
    try:
        return _platform_tls or _pyopenssl
    except:
        pass
    return False

def adderrno( arr, *errnames ):
    for errname in errnames:
        if errname in dir(errno):
            arr.append( getattr( errno, errname ) )

droperrors = [ 10054 ]
adderrno( droperrors, 'EPIPE', 'ECONNRESET', 'ENETRESET', 'ESHUTDOWN' )
blockerrors = [ 10035 ]
adderrno( blockerrors, 'EAGAIN', 'EWOULDBLOCK', 'EINPROGRESS' )

class RLockWrapped:
    def __init__( self ):
        self.real = threading.RLock()

    def acquire( self ):
        try:
            self.real.acquire()
        except:
            pass

    def release( self ):
        try:
            self.real.release()
        except:
            pass

lock_type = RLockWrapped
loop_time = 0.5

class socket_thread(threading.Thread):
    def __init__( self ):
        self._lock = lock_type()
        self._socks = []
        self.loops = 0
        self.notifies = 0
        self._shutdown = False
        threading.Thread.__init__( self, name='Socket Thread' )
        self.setDaemon( True )

    def shutdown( self ):
        self._lock.acquire()
        self._shutdown = True
        self._lock.release()

    def addsock( self, newsock ):
        self._lock.acquire()
        self._socks.append( newsock )
        if not self.isAlive():
            self.start()
        self._lock.release()

    def run( self ):
        try:
            self._lock.acquire()
            while not self._shutdown:
                i = []
                o = []
                for s in self._socks:
                    if s.need_connect():
                        s.connect_start()
                    if s.dead():
                        self._socks.remove( s )
                        #print " --> Dead",`s`
                        continue
                    #print `s`," --> Check Status"
                    s.check_status()
                    #print `s`," --> DONE"
                    if s.need_switch():
                        s.starttls_real()
                    if s.dead():
                        self._socks.remove( s )
                        #print " --> Dead 2",`s`
                        continue
                    if s.need_close():
                        self._socks.remove( s )
                        #print " --> Formal close",`s`
                        s.close_real()
                        continue
                    if s.wantread():
                        i.append( s )
                    if s.wantwrite():
                        o.append( s )
                    if s.dead():
                        #print " --> Dead 3",`s`
                        self._socks.remove( s )
                        continue
                self._lock.release()
                if len(self._socks)==0:
                    #print " --> Thread death"
                    return
                try:
                    #print "==>",`i`,`o`
                    #t1 = time.time()
                    if sys.platform == 'symbian_s60':
                        save_o = o
                        o = []
                        save_i = i
                        i = [x.fileno() for x in i]
                    (igot,ogot,egot) = select.select( i, o, [], loop_time )
                    self.loops += 1
                    if sys.platform == 'symbian_s60':
                        ogot = save_o
                        if len(igot):
                            igot = [ x for x in save_i if x.fileno() in igot ]
                    #t2 = time.time()
                    #if ( t2 - t1 ) > 0.1:
                    #    print "<==",`igot`,`ogot`,`egot`,`t2 - t1`
                    self._lock.acquire()
                    try:
                        if len(igot):
                            for s in igot:
                                s.readavail()
                            if _onread is not None:
                                #print >>sys.stderr, "PRE-ONREAD"
                                self.notifies += 1
                                _onread()
                                #print >>sys.stderr, "POST-ONREAD"
                        if ogot:
                            for s in ogot:
                                s.writeavail( True )
                            if _onwrite is not None:
                                _onwrite()
                        for s in self._socks:
                            s.check_status()
                    except:
                        #print "THREAD EXC: 2"
                        self._lock.release()
                        raise
                except:
                    #print "THREAD EXC: 1"
                    self._lock.acquire()
            for s in self._socks:
                s.close_real()
            self._lock.release()
        except:
            #print "THREAD EXCEPTION"
            pass
        #print "THREAD EXIT"

_socket_thread = None


_onread = None
_onwrite = None

def set_notify( onread, onwrite ):
    global _onread,_onwrite
    _onread = onread
    _onwrite = onwrite

def addsock( sock ):
    global _socket_thread
    if _socket_thread is not None:
        if not _socket_thread.isAlive():
            _socket_thread.join()
            _socket_thread = None
    if _socket_thread is None:
        _socket_thread = socket_thread()
    _socket_thread.addsock( sock )

def check():
    global _socket_thread
    if _socket_thread is None:
        return "No thread"
    if _socket_thread.isAlive():
        return "Alive with %d sockets, %d loops, %d notifies" % ( len(_socket_thread._socks), _socket_thread.loops, _socket_thread.notifies )
    return "Thread dead"
    

# Configurables.
isolate_sockets = False
await_read = None
await_write = None
use_thread = True

def shutdown():
    global use_thread
    if use_thread:
        global _socket_thread
        if _socket_thread is not None:
            if _socket_thread.isAlive():
                _socket_thread.shutdown()
                _socket_thread.join()
                _socket_thread = None

class cond_wrapper:
    def __init__( self ):
        if use_thread:
            self._signal = threading.Condition()

    def acquire( self ):
        try:
            self._signal.acquire()
        except:
            pass
    def release( self ):
        try:
            self._signal.release()
        except:
            pass
    def notify( self ):
        try:
            self._signal.notify()
        except:
            pass
    def wait( self ):
        if not use_thread:
            print "***\n* *\n *  WAIT!\n* *\n***"
            raise "Argh! Wait while not using threads!"
        try:
            self._signal.wait()
        except:
            pass

_up_counter = 0
_pure_up_counter = 0
def up_counter( txt=True ):
    q = _up_counter
    if not txt:
        return q
    c = ''
    if q > 512:
        c = 'k'
        q /= 1024.0
        if q > 512:
            c = 'M'
            q /= 1024.0
    return (q,c)
def up_ratio():
    if _pure_up_counter:
        return _up_counter * 100.0 / _pure_up_counter
    return 100

_down_counter = 0
_pure_down_counter = 0
def down_counter( txt=True ):
    q = _down_counter
    if not txt:
        return q
    c = ''
    if q > 512:
        c = 'k'
        q /= 1024.0
        if q > 512:
            c = 'M'
            q /= 1024.0
    return (q,c)
def down_ratio():
    if _pure_down_counter:
        return _down_counter * 100.0 / _pure_down_counter
    return 100

def tls_stats():
    return _tls_stats

condition_type = cond_wrapper
class filething:
    def __init__( self, host=None, port=None, banner=True, switch=False ):
        self._host = host
        if port is None:
            port = []
        if not isinstance(port,list):
            port = [port]
        self._port = port[:]
        #self._port.reverse()
        self._onconnect = None
        self._onfail = None
        #self._banner = banner # Not needed anymore.
        self._connected = False
        self._need_connect = False
        self._need_close = False
        self._need_switch = switch
        self._connecting = None
        self._ibuf = ''
        self._ibbuf = []
        self._last_recv = None
        self._bandwidth = None
        self._bandwidth_data = []
        self._obuf = ''
        self._commit_buf = ''
        self._bcommit_buf = []
        self._sock = None
        self._sock_ssl = None
        self._compressor = None
        self._decompressor = None
        self._sasl_mech = None
        self._ssl_context = None
        self._digest = None
        self._signal = condition_type()
        self._fatal_error = None
        self._count_recv = 0
        self._count_send = 0
        self._autoflush = False
        self._encode_tls = False
        self._tls_obuf = ''
        self.connect( False )
        if use_thread:
            addsock( self )
            self._encode_lock = threading.RLock()
        else:
            self.connect_start()

    def set_mech(self, mech):
        self._sasl_mech = mech

    def _encode(self, s):
        if use_thread:
            self._encode_lock.acquire()
        try:
            if self._compressor:
                s = self._compressor.add(s)
            if self._sasl_mech and self._sasl_mech.encoding:
                s = self._sasl_mech.encode(s)
            if self._encode_tls and self._sock_ssl:
                self._tls_obuf += s
                s = ''
            return s
        finally:
            self._encode_lock.release()
    
    def _encode_flush(self):
        if use_thread:
            self._encode_lock.acquire()
        try:
            s = ''
            if self._compressor:
                s = self._compressor.flush()
            if self._sasl_mech and self._sasl_mech.encoding:
                s = self._sasl_mech.encode(s)
                s += self._sasl_mech.encode_flush()
            if self._encode_tls and self._sock_ssl:
                self._tls_obuf += s
                while self._tls_obuf:
                    #print >>sys.stderr, "Encode(%d): %d octets left in TLS buffer" % (self._sock.fileno(), len(self._tls_obuf))
                    try:
                        try:
                            n = self._sock_ssl.write(self._tls_obuf)
                            self._tls_obuf = self._tls_obuf[n:]
                            #print >>sys.stderr, "Encode(%d): %d octets left in TLS buffer" % (self._sock.fileno(), len(self._tls_obuf))
                        except OpenSSL.SSL.Error, e:
                            raise self.transform_exception( e, 'encode' )
                    except socket.error, e:
                        if e.args[0]!=errno.EAGAIN:
                            self._fatal_error = e
                            raise
                        break
                s = self._sock_foo.get_outdata()
            return s
        finally:
            self._encode_lock.release()

    def _decode(self, s):
        if use_thread:
            self._encode_lock.acquire()
        try:
            if self._encode_tls and self._sock_ssl:
                self._sock_foo.set_indata(s)
                s = ''
                try:
                    self._sock_foo.reading = True
                    try:
                        try:
                            while True:
                                s += self._sock_ssl.read(65536)
                        except OpenSSL.SSL.Error, e:
                            raise self.transform_exception( e, 'decode' )
                    except socket.error, e:
                        if e.args[0]!=errno.EAGAIN:
                            self._fatal_error = e
                            raise
                finally:
                    self._sock_foo.reading = False
            if self._sasl_mech and self._sasl_mech.encoding:
                s = self._sasl_mech.decode(s)
            if self._decompressor:
                s = self._decompressor.add(s)
            return s
        finally:
            self._encode_lock.release()

    def __repr__( self ):
        if self._sock:
            foo = self._sock.fileno()
        else:
            foo = None
        return '<filething ' + `foo` + '>'

    def tls_cb_data( self ):
        if self._sock_ssl is not None:
            try:
                cb = ''
                cb += self._sock_ssl.get_finished()
                return cb
            except:
                return True
        return None

    def compress_on(self):
        if self._compressor:
            return True
        if self._sock_ssl:
            try:
                return self._sock_ssl.get_comp_name() is not None
            except AttributeError:
                return False
        return False

    def autoflush( self, what ):
        self._signal.acquire()
        try:
            self._autoflush = what
        finally:
            self._signal.release()

    def bandwidth( self ):
        self._signal.acquire()
        try:
            return self._bandwidth
        finally:
            self._signal.release()

    def count_send( self ):
        self._signal.acquire()
        try:
            return self._count_send
        finally:
            self._signal.release()
        
    def count_recv( self ):
        self._signal.acquire()
        try:
            return self._count_recv
        finally:
            self._signal.release()
        
    def transform_exception( self, ex, how ):
        #print >>sys.stderr, "Transforming exception",`ex`,`ex.__class__`,"for",`how`
        if isinstance( ex, socket.sslerror ):
            if ex.args[0]==socket.SSL_ERROR_EOF:
                return socket.error( errno.EPIPE, ex.args[1] )
            if ex.args[0] in [socket.SSL_ERROR_WANT_READ,socket.SSL_ERROR_WANT_WRITE]:
                return socket.error( errno.EAGAIN, ex.args[1] )
            return socket.error( errno.EPIPE, `ex` )
        if isinstance( ex, socket.error ):
            if ex.args[0] in droperrors:
                return socket.error( errno.EPIPE, ex.args[1] )
            if ex.args[0] in blockerrors:
                return socket.error( errno.EAGAIN, ex.args[1] )
            return ex
        if isinstance( ex, OpenSSL.SSL.WantReadError ) or isinstance( ex, OpenSSL.SSL.WantWriteError ):
            return socket.error( errno.EAGAIN, `ex` )
        return socket.error( errno.EPIPE, `ex` )

    def dead( self ):
        return self._sock is None or ( not self._connecting and ( self._fatal_error is not None and self._fatal_error.args[0]==errno.EPIPE ) )

    def wantread( self ):
        return True

    def wantwrite( self ):
        self._signal.acquire()
        try:
            if not self._sock:
                return False
            if not self._connected:
                return True
            return len(self._commit_buf)!=0
        finally:
            self._signal.release()

    def handle_connect( self ):
        #print " }}} Handle Connect"
        e = self._sock.getsockopt( socket.SOL_SOCKET, socket.SO_ERROR )
        if e:
            import os
            self._sock.close()
            self._sock = None
            self._fatal_error = self.transform_exception( socket.error( e, os.strerror( e ) ), 'pending connect' )
            self.connect_start()
            raise socket.error( errno.EAGAIN, "Reconnecting" )
        self._connected = True
        if self._need_switch:
            self.starttls_real()
        if await_read:
            await_read( self )
        self._signal.notify()

    def check_status( self ):
        global _pure_down_counter
        global _down_counter
        self._signal.acquire()
        try:
            if not self._connected:
                #print "Check Status"
                if time.time() - self._connecting > 25.0:
                    #print "Connecting too long, try next address."
                    self._fatal_error = socket.error( errno.EPIPE, "Connection timeout" )
                    self._sock.close()
                    self._sock = None
                    self.connect_start()
            if _delay or _bandwidth:
                #print time.time(), `self._ibbuf`,`self._bcommit_buf`
                while self._ibbuf and self._ibbuf[0][0] <= time.time():
                    #print "BW in...",`self._decompressor`
                    tmp = self._decode(self._ibbuf[0][1])
                    #print "There"
                    _down_counter += len(self._ibbuf[0][1])
                    #print "Here"
                    _pure_down_counter += len(tmp)
                    self._ibuf += tmp
                    del self._ibbuf[0]
                    #print "Notify/onread"
                    self._signal.notify()
                    if _onread:
                        _onread()
                while self._bcommit_buf and self._bcommit_buf[0][0] <= time.time():
                    #print "BW out..."
                    self._commit_buf += self._bcommit_buf[0][1]
                    del self._bcommit_buf[0]
                    self._signal.notify()
                    if _onwrite:
                        _onwrite()
        finally:
            self._signal.release()

    def readavail( self ):
        self._signal.acquire()
        try:
            try:
                nbuf = ''
                if not self._connected:
                    #print "Not connected, readavail"
                    raise socket.error( errno.EAGAIN, "Not yet connected" )
                    #self.handle_connect()
                try:
                    while True:
                        if not self._encode_tls and self._sock_ssl is not None:
                            tmp = self._sock_ssl.read(16384)
                        else:
                            tmp = self._sock.recv(16384)
                        #print >>sys.stderr,"READ: socket %d, %d octets" % (self._sock.fileno(), len(tmp))
                        if tmp:
                            nbuf += tmp
                        else:
                            if sys.platform != 'symbian_s60' or not nbuf:
                                self._fatal_error = socket.error( errno.EPIPE, "Conection dropped" )
                                self.close()
                            break
                    #print >>sys.stderr,"Loop exit"
                finally:
                    self._count_recv += len(nbuf)
                    global _down_counter
                    global _pure_down_counter
                    now = time.time()
                    #print >>sys.stderr, "Read",`len(nbuf)`,"octets:",`nbuf`
                    if len(nbuf):
                        global _delay
                        global _bandwidth
                        if _delay or _bandwidth:
                            #print "Read to BW buf"
                            t0 = time.time()
                            if _delay:
                                t0 += _delay / 2.0 # Half RTT
                            #print "t0 [1]",`t0`
                            if len(self._ibbuf):
                                if t0 < self._ibbuf[-1][0]:
                                    t0 = self._ibbuf[-1][0]
                            #print "t0 [2]",`t0`
                            if _bandwidth:
                                t0 += len(nbuf) / _bandwidth # Bandwidth in bytes/sec
                            #print "t0 [3]",`t0`
                            self._ibbuf.append( (t0,nbuf) )
                            #print `self._ibbuf`
                        else:
                            _down_counter += len(nbuf)
                            #print >>sys.stderr, "Decoding NBUF"
                            tmp = self._decode( nbuf )
                            #print >>sys.stderr,"DECODE: socket %d, %d octets" % (self._sock.fileno(), len(tmp))
                            #print >>sys.stderr, "Decoded to",`tmp`
                            _pure_down_counter += len(tmp)
                            self._ibuf += tmp
                        #print >>sys.stderr,"ibuf changed:",`self._ibuf`
                        if self._last_recv is None:
                            self._last_recv = now
                        elif self._last_recv is not None:
                            use_this = False
                            if self._bandwidth is not None:
                                if (now - self._last_recv) > 0.1:
                                    if (len(nbuf)*8.0 / ( now - self._last_recv )) > ( self._bandwidth * 0.75 ):
                                        use_this = True
                            else:
                                use_this = True
                            if use_this:
                                self._bandwidth_data.append( (len(nbuf),now-self._last_recv) )
                                td,tt = 0.0,0.0
                                for d,t in self._bandwidth_data:
                                    td += d*8*d
                                    tt += t*d
                                b = td/tt
                                self._bandwidth = b
                            self._bandwidth_data = self._bandwidth_data[20:]
                            self._last_recv = now
                #print >>sys.stderr, "Here."
            except socket.error, e:
                e = self.transform_exception( e, 'read' )
                if e.args[0]!=errno.EAGAIN:
                    self._fatal_error = e
            except socket.sslerror, e:
                e = self.transform_exception( e, 'read' )
                if e.args[0]!=errno.EAGAIN:
                    self._fatal_error = e
            except OpenSSL.SSL.Error, e:
                e = self.transform_exception( e, 'read' )
                if e.args[0]!=errno.EAGAIN:
                    self._fatal_error = e
        finally:
            #print >>sys.stderr,"NOTIFY!"
            self._signal.notify()
            self._signal.release()

    def now_readable( self, *args ):
        self.readavail()
        return True

    def set_comp( self, comp, decomp ):
        self._signal.acquire()
        self._compressor = comp
        self._decompressor = decomp
        self._signal.release()

    def compressing( self ):
        self._signal.acquire()
        try:
            return self._compressor or self._decompressor
        finally:
            self._signal.release()

    def preload_compressor( self, data ):
        self._signal.acquire()
        try:
            self._obuf += self._compressor.preload( data )
        finally:
            self._signal.release()

    def readline( self, genexcept=False ):
        return self.readuntil( genexcept, charseq='\r\n' )
        
    def readuntil( self, genexcept=False, minlen=0, charseq=None ):
        self._signal.acquire()
        try:
            if not isolate_sockets and self._fatal_error is None:
                self.readavail()
            if not genexcept:
                while ( minlen and len(self._ibuf) < minlen ) or ( charseq and self._ibuf.find(charseq,minlen)==-1 ):
                    #print >>sys.stderr,"Waiting...",`self._ibuf`,len(self._ibuf),charseq,minlen
                    if self._fatal_error is not None:
                        break
                    if use_thread:
                        self._signal.wait()
                    else:
                        ig,og,eg = select.select([self.fileno()],[],[],None)
                        self.readavail()
            br = -1
            if len(self._ibuf) >= minlen:
                if charseq:
                    br = self._ibuf.find(charseq,minlen)
                    if br >= 0:
                        br += len(charseq)
                else:
                    br = minlen
            if br > 0:
                r = self._ibuf[:br]
                self._ibuf = self._ibuf[br:]
                #print >>sys.stderr, "Returning",`r`,"Keeping",`self._ibuf`,"minlen",minlen,"charseq",`charseq`
                return r
            if self._fatal_error is not None:
                raise self._fatal_error
            raise socket.error( errno.EAGAIN, "RL Blocked" )
        finally:
            self._signal.release()

    def read( self, l, genexcept=False ):
        return self.readuntil( genexcept, minlen=l )

    def write( self, s ):
        global _pure_up_counter
        if not s:
            return
        _pure_up_counter += len(s)
        #print >>sys.stderr, "Encoding %d octets" % (len(s))
        self._obuf += self._encode(s)
        #print >>sys.stderr, "Encoded to %d" % (len(self._obuf))
        if self._autoflush:
            self.flush()

    def flush( self ):
        #print >>sys.stderr, "Flushing (trying encode)"
        self._obuf += self._encode_flush()
        if not self._obuf:
            return False
        #print >>sys.stderr, "Flushing %d octets" % (len(self._obuf))
        self._signal.acquire()
        try:
            global _delay
            global _bandwidth
            if _delay or _bandwidth:
                t0 = time.time()
                if _delay:
                    t0 += _delay / 2.0
                if len(self._bcommit_buf):
                    if t0 < self._bcommit_buf[-1][0]:
                        t0 = self._bcommit_buf[-1][0]
                if _bandwidth:
                    t0 += len(self._obuf) / _bandwidth
                self._bcommit_buf.append( (t0,self._obuf) )
            else:
                self._commit_buf += self._obuf
                #print >>sys.stderr, "Committed %d octets" % (len(self._commit_buf))
            self._obuf = ''
            if not isolate_sockets:
                if self.writeavail() and await_write:
                    await_write( self._sock )
        finally:
            self._signal.release()
        return True

    def writeavail( self, select_hit=False ):
        self._signal.acquire()
        try:
            try:
                if not self._connected: # Connect succeeded
                    if not select_hit:
                        #print "not connected, not hit by select"
                        raise socket.error( errno.EAGAIN, "Not yet connected" )
                    self.handle_connect()
                while len(self._commit_buf):
                    if not self._encode_tls and self._sock_ssl is not None:
                        n = self._sock_ssl.write( self._commit_buf )
                    else:
                        n = self._sock.send( self._commit_buf )
                    if not n:
                        break
                    #print >>sys.stderr,"WRITE: socket %d, %d octets." % (self._sock.fileno(), n)
                    self._commit_buf = self._commit_buf[n:]
                    self._count_send += n
                    #print >>sys.stderr,"WRITE: socket %d, %d remaining." % (self._sock.fileno(), len(self._commit_buf))
                    global _up_counter
                    _up_counter += n
            except socket.error, e:
                e = self.transform_exception( e, 'write' )
                if e.args[0]!=errno.EAGAIN:
                    self._fatal_error = e
                    self._signal.notify()
            except socket.sslerror, e:
                e = self.transform_exception( e, 'write' )
                if e.args[0]!=errno.EAGAIN:
                    self._fatal_error = e
                    self._signal.notify()
            except OpenSSL.SSL.Error, e:
                e = self.transform_exception( e, 'write' )
                if e.args[0]!=errno.EAGAIN:
                    self._fatal_error = e
                    self._signal.notify()
        finally:
            self._signal.release()

    def now_writable( self, *args ):
        self.writeavail()
        return 0!=len(self._commit_buf)

    def connect( self, waiting=True, onconnect=None, retry=None, onfail=None ):
        self._signal.acquire()
        try:
            if onfail:
                self._onfail = onfail
            if self._fatal_error is not None:
                if self._onfail:
                    of = self._onfail
                    self._onfail = None
                    of( self._fatal_error )
                raise self._fatal_error
            if onconnect:
                self._onconnect = onconnect
            if self._connecting:
                if self._connected:
                    if self._onconnect:
                        oc = self._onconnect
                        self._onconnect = None
                        oc()
                    return True
                if waiting:
                    while not self._connected:
                        if self._connecting is None and self._fatal_error is not None:
                            if self._onfail:
                                of = self._onfail
                                self._onfail = None
                                of( self._fatal_error )
                            raise self._fatal_error
                        self._signal.wait()
                    return self.connect( True )
                return False
            self._need_connect = True
            self._connecting = time.time()
            self._addrinfo = []
            self._retry = retry or 1
            if waiting:
                return self.connect( True )
            return False
        finally:
            self._signal.release()

    def is_connected( self ):
        self._signal.acquire()
        try:
            return self._connected
        finally:
            self._signal.release()

    def tls_digest( self ):
        self._signal.acquire()
        try:
            return self._digest
        finally:
            self._signal.release()

    def wait_connected( self ):
        self.connect( True )

    def connect_start( self ):
        global dns_query
        self._signal.acquire()
        try:
            if self._host == '__DUMMY__':
                self._fatal_error = socket.error( errno.EPIPE, "I need to pretend to fail here" )
                return
            if self._sock is None:
                if not self._addrinfo:
                    #print "No addresses left to try"
                    self._retry -= 1
                    if self._retry < 0:
                        #print "Out of retries"
                        self._connecting = None
                        if not self._fatal_error:
                            self._fatal_error = socket.error( errno.EPIPE, "Unknown connection failure." )
                        self._signal.notify()
                        return
                    try:
                        for p in self._port:
                            if isinstance( p, int ):
                                self._addrinfo += socket.getaddrinfo( self._host, p, socket.AF_UNSPEC, socket.SOCK_STREAM )
                            elif dns_query is not None:
                                try:
                                    answers = dns_query( ('_%s._%s.' % p) + self._host, 'SRV' )
                                    for rdata in answers:
                                        self._addrinfo += socket.getaddrinfo( rdata.target, rdata.port, socket.AF_UNSPEC, socket.SOCK_STREAM )
                                except:
                                    pass
                    except socket.gaierror, e:
                        raise socket.error( errno.EPIPE, str(e) )
                    self._addrinfo.reverse()
                self._fatal_error = None
                af, st, pr, cname, sa = self._addrinfo.pop()
                try:
                    self._sock = socket.socket( af, st, pr )
                except socket.error, e:
                    self._fatal_error = self.transform_exception( e, 'socket create' )
                    if self._fatal_error.args[0] != errno.EAGAIN:
                        return self.connect_start()
                except:
                    return self.connect_start()
                if sys.platform != 'symbian_s60':
                    self._sock.setblocking( 0 )
                try:
                    #print "Connecting to",`sa`
                    self._connecting = time.time()
                    self._sock.connect( sa )
                except socket.error, e:
                    self._fatal_error = self.transform_exception( e, 'connect' )
                    if self._fatal_error.args[0] != errno.EAGAIN:
                        return self.connect_start()
                except:
                    return self.connect_start()
                if sys.platform == 'symbian_s60':
                    self._connected = True
                    self._signal.notify()
                    self._sock.setblocking( 0 )
                if await_write:
                    await_write( self )
                self._fatal_error = None
                self._need_connect = False
        finally:
            self._signal.release()

    def need_connect( self ):
        self._signal.acquire()
        try:
            return self._need_connect
        finally:
            self._signal.release()

    def starttls( self, with_message=None ):
        self._signal.acquire()
        try:
            self._need_switch = True
            if with_message:
                self.write( with_message )
            self._digest = None
            if use_thread:
                while self._sock_ssl is None:
                    self._signal.wait()
            else:
                self.starttls_real()
            return self._digest
        finally:
            self._signal.release()

    def need_switch( self ):
        self._signal.acquire()
        try:
            return self._need_switch and self._connected
        finally:
            self._signal.release()

    def set_tls_state( self ):
        #print >>sys.stderr, "TLS client mode setup"
        self._sock_ssl.set_connect_state()

    def starttls_real( self ):
        self._signal.acquire()
        try:
            try:
                self._need_switch = False
                self._sock.setblocking( 1 )
                self.writeavail()
                if _pyopenssl:
                    if self._ssl_context is None:
                        #print >>sys.stderr, "Creating TLS context."
                        self._ssl_context = OpenSSL.SSL.Context( OpenSSL.SSL.SSLv23_METHOD )
                        def info_callback(conn, where, ret):
                            print >>sys.stderr, "[info] %x = %d" % (where, ret),`conn.state_string()`
                        def verify(*args):
                            #print >>sys.stderr, "[verify]",`args`
                            return True
                        #self._ssl_context.set_cipher_list( 'ALL:RC4+RSA:+SSLv2:@STRENGTH' )
                        #print >>sys.stderr, "Here"
                        #self._ssl_context.set_info_callback( info_callback )
                        #print >>sys.stderr, "Here"
                        self._ssl_context.set_verify( OpenSSL.SSL.VERIFY_NONE, verify )
                        #print >>sys.stderr, "Here"
                        self._ssl_context.set_options( OpenSSL.SSL.OP_ALL|OpenSSL.SSL.OP_NO_SSLv2 )
                        #print >>sys.stderr, "Here"
                        #print >>sys.stderr, `self._ssl_context.get_cipher_list()`
                    class sock_foo:
                        def __init__(self, s):
                            self.s = s
                            self._inbuf = ''
                            self._outbuf = ''
                            self._dead = False
                            self.reading = False
                            
                        def read(self, l):
                            #print >>sys.stderr, "TLS(%d) wants %d octets from %d" % ( self.fileno(), l, len(self._inbuf))
                            t = self._inbuf[:l]
                            self._inbuf = self._inbuf[l:]
                            if not t:
                                if self._outbuf:
                                    #print >>sys.stderr, "Pending outbound, try flushing."
                                    self.s.flush()
                                    #print >>sys.stderr, "Done"
                                #print >>sys.stderr, "Raising error."
                                raise socket.error(errno.EAGAIN, "Foo")
                            return t
                        
                        def write(self, buf):
                            #print >>sys.stderr, "TLS(%d) writing %d octets" % ( self.fileno(), len(buf) )
                            self._outbuf += buf
                            if self.reading:
                                #print >>sys.stderr, "TLS read caused write, flushing"
                                self.s.flush()
                            return len(buf)
                        
                        def fileno(self):
                            return self.s._sock.fileno()

                        def setblocking(self, x):
                            return self.s._sock.setblocking(x)

                        def set_indata(self, s):
                            self._inbuf += s
                            
                        def get_outdata(self):
                            t = self._outbuf
                            self._outbuf = ''
                            return t
                        
                        
                    s = sock_foo(self)
                    self._sock_foo = s
                    self._sock_ssl = OpenSSL.SSL.Connection( self._ssl_context, s )
                    global _tls_stats
                    try:
                        self._sock_ssl.get_cipher_name()
                        _tls_stats = True
                    except AttributeError:
                        _tls_stats = False
                    except:
                        _tls_stats = True
                    #print >>sys.stderr, "Ciphers:",`self._sock_ssl.get_cipher_list()`
                    #print >>sys.stderr, "[1] %d now in state:" % self.fileno(), `self._sock_ssl.state_string()`
                    self.set_tls_state()
                    #print >>sys.stderr, "[2] %d now in state:" % self.fileno(), `self._sock_ssl.state_string()`
                    if _tls_stats == True:
                        self._encode_tls = True
                        self._sock.setblocking(0)
                        try:
                            self._sock_ssl.do_handshake()
                        except:
                            pass
                    else:
                        self._sock_ssl.do_handshake()
                    #print >>sys.stderr, "[3] %d now in state:" % self.fileno(), `self._sock_ssl.state_string()`
                    try:
                        if self._sock_ssl.get_peer_certificate() is not None:
                            self._digest = self._sock_ssl.get_peer_certificate().digest('SHA1')
                    except:
                        pass
                    #print >>sys.stderr, "[3] %d now in state:" % self.fileno(), `self._sock_ssl.state_string()`
                else:
                    self._sock_ssl = socket.ssl( self._sock )
            except socket.error,e:
                self._fatal_error = self.transform_exception( e, 'starttls' )
            except OpenSSL.SSL.Error, e:
                self._fatal_error = self.transform_exception( e, 'starttls' )
            except:
                self._fatal_error = self.transform_exception( 'TLS negotiation failed', 'starttls' )
            self._signal.notify()
            self.setblocking( 0 )
        finally:
            self._signal.release()
        
    def setblocking( self, q ):
        if _pyopenssl and self._sock_ssl and not self._encode_tls:
            self._sock_ssl.setblocking( q )
        else:
            self._sock.setblocking( q )

    def fileno( self ):
        try:
            return self._sock.fileno()
        except:
            return self._sock

    def close( self ):
        self._signal.acquire()
        try:
            self._need_close = True
            self._need_connect = False
            if not use_thread:
                self.close_real()
        finally:
            self._signal.release()

    def need_close( self ):
        self._signal.acquire()
        try:
            return self._need_close
        finally:
            self._signal.release()

    def close_real( self ):
        self._signal.acquire()
        try:
            self._sock.close()
            self._sock = None
            self._compressor = None
            self._decompressor = None
            self._sock_ssl = None
        finally:
            self._signal.release()

    def prod_checker( self ):
        self._signal.acquire()
        try:
            if self._connected:
                if self._fatal_error is not None:
                    raise self._fatal_error
                if self._onconnect:
                    oc = self._onconnect
                    self._onconnect = None
                    oc()
                    return True
                return self._ibuf!=''
            else:
                return self.connect(False)
        finally:
            self._signal.release()

    def prod( self ):
        t = self.prod_checker()
        #print "  [%s Returning" % `self.fileno()`,`t`,"]"
        return t

    def signal( self ):
        return self._signal

    def set_socket( self, what, connected ):
        self._sock = what
        self._connected = connected
        self.setblocking( 0 )

    def getpeer( self ):
        peer = self._sock.getpeername()
        return (socket.getnameinfo(peer,0)[0],socket.getnameinfo(peer,socket.NI_NUMERICHOST)[0])

class server_connection( filething ):
    def __init__( self, fd, certfile=None, privkey=None, switch=False ):
        filething.__init__( self )
        self.set_socket( socket.fromfd( 0, socket.AF_INET, socket.SOCK_STREAM ), True )
        self._tls_ready = False
        self._certfile = certfile
        self._privkey = privkey
        if switch and self.setup_tls():
            self.starttls()

    def set_tls_state( self ):
        #print >>sys.stderr, "Set accept state"
        self._sock_ssl.set_accept_state()

    def tls_init( self ):
        self.signal().acquire()
        try:
            if self._tls_ready:
                return True
            try:
                self._ssl_context = OpenSSL.SSL.Context( OpenSSL.SSL.SSLv23_METHOD )
                self._ssl_context.use_certificate_file( self._certfile )
                self._ssl_context.use_privatekey_file( self._privkey )
                self._tls_ready = True
                return True
            except:
                return False
        finally:
            self.signal().release()
        
