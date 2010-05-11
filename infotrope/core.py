#
# Copyright 2004 - 2006 Dave Cridland <dave@cridland.net>
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

import socket
import infotrope.socketry
import infotrope.sasl
import errno

def platform_tls():
    return infotrope.socketry.platform_tls()

class command:
    def __init__( self, env, tag ):
        self.notifier = None
        self.tag = tag
        self.env = env

    def __str__( self ):
        return str(self.tag)

    def __eq__( self, other ):
        if self is other:
            return True
        return str(self) == str(other)

    def __ne__( self, other ):
        return not self.__eq__( other )

    def oncomplete( self, n ):
        if self.notifier is not None:
            if not isinstance( self.notifier, list ):
                self.notifier = [self.notifier]
            self.notifier.append( n )
        else:
            self.notifier = [n]

    def notify_complete( self, *args ):
        if self.notifier is not None:
            if isinstance( self.notifier, list ):
                for n in self.notifier:
                    if self.env.defcall:
                        self.env.defer_call( n, self, *args )
                    else:
                        n( self, *args )
            else:
                if self.env.defcall:
                    self.env.defer_call( self.notifier, self, *args )
                else:
                    self.notifier( self, *args )
            self.notifier = None
    
class notify_all:
    def __init__( self, env, tags, notifier ):
        self.notifier = notifier
        self.tags = tags
        self.env = env
        for t in self.tags:
            t.oncomplete( self )
        if not self.tags:
            if self.env.defcall:
                self.env.defer_call( notifier, None, None, None )
            else:
                notifier( None, None, None )

    def __call__( self, cmd, *args ):
        self.tags = [ x for x in self.tags if x != cmd ]
        if not self.tags:
            if self.env.defcall:
                self.env.defer_call( self.notifier, cmd, *args )
            else:
                self.notifier( cmd, *args )

class callback:
    def __init__( self, c, user, password ):
        self.callback = c
        self.user = user
        self.password = password

    def __call__( self, m, v ):
        if 'username' in v:
            v['username'] = self.user
        if 'password' in v:
            v['password'] = self.password
        if None in v.values():
            self.callback( m, v )
        m.fulfill( v )


class exception:
    def __init__( self, *args ):
        self.msg = args[0]
        self.args = args
        
    def __str__( self ):
        return str(self.msg)

class connection:
    def __init__( self, uri, ports, environment, connect_async=False, using_alt_port=False ):
        self.s = None
        self.sasl = None
        self.env = environment
        self.hostname = uri.server
        self.port = ports or uri.port
        if self.port is None:
            raise exception( "No port was supplied" )
        self._proto_log = '>>> '
        self._log_pending = []
        self.uri = infotrope.url.URL( uri )
        self.logged_in = None
        self.logged_out = False
        self.using_alt_port = using_alt_port
        self.connect_async = connect_async
        self.ready = False
        self.inprog = {}
        self.fail_reason = None
        self.last_command = None
        self._wait_connected = False
        self.waiter = []

    def do_connect( self ):
        if self.hostname == '__DUMMY__':
            self.s = None
            self.connect_onfail( socket.error( errno.EPIPE, "Dummy server used" ) )
        else:
            self.s = infotrope.socketry.filething( self.hostname, self.port, banner=not self.using_alt_port, switch = self.using_alt_port )
            self.s.connect( not self.connect_async, onconnect=self.secret_sauce, onfail=self.connect_onfail )
    
    def tls_active( self ):
        if self.dead():
            return False
        return self.s.tls_cb_data()

    def secret_sauce( self ):
        self.env.status( "Connected to " + str(self.uri) )
        self.proto_log_commit( "<<< [Connected on %d]" % self.s.fileno() )
        self.read_banner()

    def wait_connected( self ):
        try:
            if self.hostname == '__DUMMY__':
                raise socket.error( errno.EPIPE, "Attempt to wait connected on dummy server" )
            self._wait_connected = True
            try:
                if self.s is not None:
                    self.s.wait_connected()
            except socket.error:
                self.s = None
                raise
        finally:
            self._wait_connected = False

    def read_banner( self ):
        pass

    def username( self ):
        return self.logged_in

    def connected( self ):
        if self.s is None:
            return False
        self.s.prod()
        return self.s.is_connected()

    def connect_onfail( self, how ):
        import infotrope.serverman
        sm = infotrope.serverman.try_serverman()
        if sm is not None:
            sm.fail( self )
        self.onfail( how.args[1] )
        
    def onfail( self, how ):
        how = self.fail_reason or how
        self.log( "Connect failed: %s" % how )
        self.env.status( str(self.uri) + ": Connection failed: %s" % how )

    def dead( self ):
        if self.s is None or self.s.dead():
            return True
        return False
    
    def notify_ready( self, who ):
        if self.ready:
            self.prod()
            if not self.dead():
                who(self)
        else:
            self.waiter.append( who )

    def full_restore_state( self ):
        pass

    def send_notify_ready( self ):
        if self.ready:
            self.env.status( "Authenticated to " + str(self.uri) )
        self.you_are_ready()
        waiters = self.waiter
        self.waiter = []
        for x in waiters:
            x( self )

    def sasl_fail( self, error ):
        self.send_notify_ready()
        self.onfail( error.txt )
        
    def you_are_ready( self ):
        pass

    def completion( self, idc, *args ):
        last = self.last_command
        if last == t:
            self.last_command = None
        if t in self.inprog:
            del self.inprog[t]
            cmd.complete( idc, *args )

    def proto_log( self, s ):
        self._proto_log += s

    def proto_log_crlf( self ):
        self.log_pending( self._proto_log )
        self._proto_log = '%d >> ' % ( self.s.fileno() )

    def proto_log_done( self ):
        self.log_pending( self._proto_log )
        self._proto_log = '%d>>> ' % ( self.s.fileno() )

    def log_pending(self, txt):
        self._log_pending.append(txt)

    def proto_log_commit( self, txt, t=None ):
        if self.env.protologging:
            import time
            self.env.proto_logger( self.uri, t or time.time(), txt )
        
    def log( self, txt, t=None ):
        if self.env.logging:
            import time
            self.env.logger( self.uri.asString(),`t or time.time()`,'::',txt )
        
    def username( self ):
        return self.logged_in

    def auth_complete( self, mech, ready=True ):
        self.s.set_mech(mech)
        if mech:
            self.logged_in = mech.getuser()
        else:
            self.logged_in = 'anonymous'
        if ready:
            self.now_ready()

    def now_ready(self, n=None):
        if n:
            self.logged_in = n
        self.uri.username = self.logged_in
        self.ready = True
        self.send_notify_ready()

    def wait_ready( self ):
        #print "WAIT READY"
        self.wait_connected()
        while not self.ready and not self.dead():
            self.fetch()
        
    def flush( self ):
        if not self.dead():
            import time
            t = time.time()
            for x in self._log_pending:
                self.proto_log_commit(x,t=t)
            self._log_pending = []
            return self.s.flush()
        return False
