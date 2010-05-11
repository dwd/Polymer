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
import infotrope.base
import infotrope.url
import infotrope.sasl
import base64

favour_literals = False # Change to True to check literal handling.
send_empty_sasl_as_string = True # Changing to False sends NIL instead.

def string( payload ):
    for x in ['\n','\r','\x00']:
        if payload.find(x)!=-1:
            return infotrope.base.literal( payload )
    lq = 2 + len(payload) + len([x for x in payload if x=='"'])
    ll = 3 + len(payload) + len(str(len(payload)))
    if lq > ll or favour_literals:
        return infotrope.base.literal( payload )
    return infotrope.base.string( payload )

class authenticate(infotrope.base.command):
    def __init__( self, srv ):
        self.server = srv
        cmdline = ['AUTHENTICATE']
        self.mech = self.server.sasl.mechlist( [x.upper() for x in srv.capability['SASL']] )
        cmdline.append( string(self.mech.mechname) )
        csf = self.mech.process( None )
        if csf:
            cmdline.append( string(''.join( csf.encode( 'base64' ).split('\n') )) )
        infotrope.base.command.__init__( self, srv.env, 'AUTH', cmdline )
        self.use_tags = False
        self.feeding = True
        self.resend = False
        self.oncomplete( self.notify )

    def notify( self, cmd, t, r, s ):
        self.server.log( "Auth complete" )
        if len(s):
            s = s[0]
            if s[0].lower() == 'sasl':
                self.mech.process( self.xmit_decode(s[1]) )
        if r.upper()=='NO':
            self.server.sasl.failure( self.mech )
            self.server.send( authenticate( self.server ) )
            return
        elif r.upper()!='OK':
            raise s
        self.server.log( "Server says OK" )
        if self.mech.okay():
            self.server.log( "Mechanism says OK" )
            self.server.auth_complete( self.mech )
            self.server.sasl.success( self.mech )
            self.server.log( "Completed auth" )
        else:
            self.server.log( "Mechanism says bad" )

    def feed( self, s ):
        try:
            gunk = self.xmit_decode( s[0] )
            sendgunk = self.mech.process( gunk )
            self.server.write_cmd_chunk( '', string( self.xmit_encode( sendgunk ) ) )
            self.server.s.write( "\r\n" )
            self.server.proto_log_done()
            self.server.flush()
        except infotrope.sasl.error:
            self.server.proto_log("*");
            self.server.proto_log_done()
            self.server.s.write("*\r\n")
            self.server.flush()
            raise
    
    def xmit_encode( self, s ):
        if s is None:
            return ''
        return ''.join( s.encode( 'base64' ).split('\n') )

    def xmit_decode( self, s ):
        return s.decode( 'base64' )

class connection(infotrope.base.connection):
    def __init__( self, uri, env ):
        if uri.port is None:
            raise infotrope.base.connection.exception( "Managesieve service has no default port." )
        self.capability = {}
        self.state = 'nonauth'
        self._scripts = []
        self._active_script = None
        self._script_src = {}
        self._last_src = None
        self.tags_running = []
        infotrope.base.connection.__init__( self, uri, env, True )
        self.use_tags = False
        self.ns_lit = True
        self.sync_lit = False

    #def read_banner( self ):
    #    self.wait('')

    def you_are_ready( self ):
        if self.ready:
            self.state = 'auth'

    def send( self, *cmd, **kw ):
        self.wait_connected()
        t,r,s = infotrope.base.connection.send( self, *cmd, **kw )
        self.tags_running.insert( 0, t.tag )
        #self.last_command = t
        return t,r,s

    def _parse_init_ok( self, t, r, s ):
        self.send( authenticate( self ) )
        self.state = 'inauth'
        self.flush()
        
    def parse_first( self, ss ):
        t,r,s = '*','',self.generic_parse(ss)
        if s[0].upper() in ['OK','NO','BAD','BYE']:
            r = s[0].lower()
            s = s[1:]
            if r in ['ok','no','bad']:
                if self.tags_running:
                    t = self.tags_running.pop()
                    print "Using tag",`t`
                else:
                    self._parse_init_ok( t, r, s )
            if r in ['bad']:
                raise infotrope.base.connection.exception( s[0] )
        elif self.state == 'init':
            if len(s) > 1:
                self.capability[s[0].upper()] = s[1].split(' ')
            else:
                self.capability[s[0].upper()] = True
        elif self.state == 'inauth':
            t = '+'
        elif self.state=='listscripts':
            self._scripts.append( s[0] )
            if len(s)>1 and s[1].lower()=='active':
                self._active_script = s[0]
        elif self.state=='getscript':
            self._last_src = s[0]
        return t,r,s

    def login( self, user=None, password=None ):
        if user is not None:
            self.uri.username = user
        self.sasl = infotrope.sasl.sasl( self.uri, service='sieve', callback=infotrope.base.callback( self.env.callback, user, password ), secquery=self.env.secquery, tls_active=self.tls_active )
        
    def listscripts( self ):
        self.state = 'listscripts'
        tag,r,s = self.send( 'LISTSCRIPTS' )
        t,r,s = self.wait( tag )
        self.state = 'auth'
        if r != 'ok':
            raise infotrope.base.connection.exception( s )

    def scripts( self ):
        if self._active_script is None:
            self.listscripts()
        return self._scripts
    def active_script( self ):
        if self._active_script is None:
            self.listscripts()
        return self._active_script

    def getscript( self, which ):
        if which not in self._script_src:
            self.state = 'getscript'
            tag,r,s = self.send( 'GETSCRIPT', string( which ) )
            tag,r,s = self.wait(tag)
            self.state = 'auth'
            if r.lower()!='ok':
                raise s
            self._script_src[which] = self._last_src
        return self._script_src[which]

    def putscript( self, which, what ):
        self.state = 'putscript'
        tag,r,s = self.send( 'PUTSCRIPT', string( which ), infotrope.base.literal( what ) )
        tag,r,s = self.wait(tag)
        self.state = 'auth'
        if r != 'ok':
            raise infotrope.base.connection.exception( s )
        if which not in self._scripts:
            self._scripts.append( which )
        self._script_src[which] = what

    def setactive( self, which ):
        tag,r,s = self.send( 'SETACTIVE', string( which ) )
        tag,r,s = self.wait(tag)
        if r != 'ok':
            raise infotrope.base.connection.exception( s )
        self._active_script = which

def main( server, user ):
    def callback( m, v ):
        import getpass
        v['password'] = getpass.getpass( 'Password: ' )
    u = infotrope.url.URL( 'x-sieve://dwd;AUTH=*@217.155.137.59:2000/' )
    s = connection( u )
    s.login( callback=callback )
    scs = s.scripts()
    for sc in scs:
        print "Script",sc
        print s.getscript( sc )
