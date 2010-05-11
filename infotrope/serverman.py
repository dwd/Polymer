#
# Copyright 2004-2007 Dave Cridland <dave@cridland.net>
# Copyright 2007 Thomas Viehmann <tv@beamnet.de>
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
from infotrope.weak import weakref

_theserverman = None

def serverman( env=None, trace=None, debug=None ):
    global _theserverman
    if _theserverman is not None:
        raise exception( "Already got a serverman." )
    if not env:
        import infotrope.environment
        env = infotrope.environment.cli_environment()
        if trace:
            env.protologging = trace
        if debug:
            env.logging = debug
    _theserverman = serverman_impl( env )
    return _theserverman

def get_serverman():
    global _theserverman
    if _theserverman is None:
        raise exception( "No serverman" )
    return _theserverman

def try_serverman():
    global _theserverman
    return _theserverman

def shutdown():
    global _theserverman
    if _theserverman is not None:
        _theserverman.shutdown()
    _theserverman = None

class serverman_impl:
    def __init__( self, env ):
        self._servers = weakref.WeakValueDictionary()
        self._servers_pending = {}
        self._waiters = {}
        self.__env = env
        self.cache_root = None
        self.socketry_boot = False

    def environment(self):
        return self.__env

    def log( self, *txt ):
        if self.__env.logging:
            self.__env.logger( *txt )

    def status( self, *x ):
        self.__env.status( *x )
        
    def __getitem__( self, what ):
        import infotrope.url
        u = infotrope.url.URL( what )
        s = self.get( u )
        self.log( "Waiting for connection to",`u` )
        #print "wait connected"
        s.wait_connected()
        #print "done"
        if s.dead():
            #self.log( "Connection is dead, retrying." )
            s.reconnect()
            #self.log( "Not dead, hopefully." )
        s.wait_ready()
        #self.log( "Got connection ready for",`u` )
        return s

    def __contains__( self, what ):
        import infotrope.url
        u = infotrope.url.URL( what ).root_user()
        if u.asString() in self._servers:
            return True
        return False

    def set_cache_root( self, what ):
        self.cache_root = what

    def get( self, what ):
        import infotrope.url
        u = infotrope.url.URL( what ).root_user()
        s = u.asString()
        if s in self._servers:
            srv = self._servers[ s ]
        elif s in self._servers_pending:
            srv = self._servers_pending[ s ]
        else:
            srv = self.new_server( u, s, infotrope.url.URL(what) )
        if srv.ready:
            srv.prod()
            if srv.dead():
                self.fail(srv)
                return self.get( u )
        return srv

    def fail( self, what ):
        #print "\nConnection failed:",`what`,"\n"
        ks1 = []
        for k,v in self._servers_pending.items():
            if v is what:
                ks1.append( k )
        for k in ks1:
            del self._servers_pending[k]
        ks = []
        for k,v in self._servers.items():
            if v is what:
                ks.append( k )
        for k in ks:
            del self._servers[k]
        ks += ks1
        for k in ks:
            self._waiters[k] = what.waiter

    def notify_ready( self, server ):
        if server.ready:
            self._servers[ server.uri.asString() ] = server
            if self.status:
                self.status( "Connected to " + server.uri.asString() )
        delete = []
        for x,v in self._servers_pending.items():
            if v is server:
                if v.ready:
                    self._servers[ x ] = v
                delete.append( x )
        for x in delete:
            del self._servers_pending[ x ]

    def register( self, what, server ):
        import infotrope.url
        u = infotrope.url.URL( what ).root_user()
        s = u.asString()
        if s in self._waiters:
            server.waiter = self._waiters[s]
        self._servers_pending[ s ] = server
        server.notify_ready( self.notify_ready )

    def prod( self ):
        for s in self._servers.values():
            s.prod()
        for s in self._servers_pending.values():
            s.prod()

    def check_readable( self ):
        import select
        qin = [ s.selectable() for s in self._servers.values() + self._servers_pending.values() if s is not None ]
        qout,x,y = select.select( qin, [], [], 0.0 )
        return 0!=len(qout)

    def new_server( self, u, s, orig_url ):
        srv = None
        store = True
        if not self.socketry_boot:
            self.status( "Booting socketry" )
            import infotrope.socketry
            if self.__env.sock_delay:
                infotrope.socketry.set_delay( self.__env.sock_delay )
            if self.__env.sock_bandwidth:
                infotrope.socketry.set_bandwidth( self.__env.sock_bandwidth )
            infotrope.socketry.set_notify( self.__env.sock_readable, self.__env.sock_writable )
            self.socketry_boot
        self.status( "Connecting to " + u.asString() )
        if u.scheme == 'acap':
            import infotrope.acap
            if self.cache_root:
                import os.path
                infotrope.acap.set_cache_root( os.path.join( self.cache_root, 'acap' ) )
            srv = infotrope.acap.connection( u, self.__env )
        elif u.scheme in ['imap','imaps']:
            import infotrope.imap
            if self.cache_root:
                import os.path
                infotrope.imap.set_cache_root( os.path.join( self.cache_root, 'imap' ) )
            srv = infotrope.imap.connection( u, self.__env )
        elif u.scheme in ['smtp','ssmtp','smtps']:
            import infotrope.esmtp
            srv = infotrope.esmtp.connection( u, self.__env )
        elif u.scheme == 'nntp':
            import infotrope.nntp
            srv = infotrope.nntp.connection( u, self.__env )
        elif u.scheme == 'x-sieve':
            import infotrope.managesieve
            srv = infotrope.managesieve.connection( u, self.__env )
        elif u.scheme == 'xmpp':
            import infotrope.xmpp
            srv = infotrope.xmpp.connection( orig_url, self.__env )
        if u.username is None:
            u.username='anonymous'
        if self.cache_root:
            import os.path
            import infotrope.sasl
            infotrope.sasl.set_stash_file( os.path.join( self.cache_root, 'stash' ) )
        srv.login( user=u.username )
        if store:
            self.register( s, srv )
            self.register( srv.uri, srv )
        if s in self._waiters:
            del self._waiters[s]
        if srv.uri in self._waiters:
            del self._waiters[srv.uri]
        return srv

    def shutdown( self ):
        self.log( " * SM: Kill waiters" )
        self._waiters = {}
        #print " * SM: Kill pending"
        self._servers_pending = {}
        self.log( " * SM: Logout servers" )
        for x,y in self._servers.items():
            self.log( " * SM: Logout:", `x` )
            y.logout(phase2=True)
            self.log( " * SM: Done" )
        for x,y in self._servers.items():
            self.log( " * SM: Logout phase 2:", `x` )
            y.logout_phase2()
            self.log( " * SM: Done" )
        self.log( " * SM: Kill servers" )
        self._servers = {}
        self.log( " * SM: Socketry kill" )
        import infotrope.socketry
        infotrope.socketry.shutdown()
        self.log( " * SM: Done" )
        self.__env = None
