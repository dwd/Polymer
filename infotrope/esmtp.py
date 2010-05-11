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
import infotrope.xtp
import infotrope.sasl
import StringIO
import infotrope.message
from infotrope.weak import weakref

suppress_extension = []

# ESMTP [RFC2821] class, designed for submission.

class auth(infotrope.xtp.command):
    def __init__( self, idc, server ):
        print 1
        self.cmd = None
        self.server = weakref.ref( server )
        self.sasl = server.sasl
        try:
            print 2
            self.mech = self.sasl.mechlist( server.get_capability('AUTH') )
            print 3, `self.mech`
            if self.mech is None:
                raise "No mech"
            sir = self.mech.process( None )
            print 4, `sir`
            if sir is None:
                cmd = 'AUTH %s' % self.mech.name()
            else:
                cmd = 'AUTH %s %s' % ( self.mech.name(), ''.join( sir.encode('base64').split('\n') ) )
            print 5
            infotrope.xtp.command.__init__( self, server.env, idc, cmd )
            print 6
            self.oncomplete( self.auth_complete )
        except infotrope.sasl.error, e:
            server.sasl_fail( e )
            raise
        print 7

    def auth_complete( self, me, r, e, t ):
        if (r&0xF00) == 0x200:
            if self.mech.okay():
                self.server().auth_complete( self.mech )
                self.sasl.success( self.mech )
                return
        self.sasl.failure( self.mech )
        self.server().issue_auth()

    def feed( self, resp, erc, txt ):
        try:
            if resp == 0x334:
                gunk = ''.join(txt).decode('base64')
                junk = self.mech.process( gunk )
                tmp = ''
                if junk is not None:
                    tmp = ''.join( junk.encode('base64').split('\n') )
                self.server().s.write(tmp)
                self.server().s.write('\r\n')
                self.server().flush()
        except infotrope.sasl.error, e:
            self.server().sasl_fail( e )

class data(infotrope.xtp.command):
    def __init__( self, server, payload ):
        infotrope.xtp.command.__init__( self, server.env, None, 'DATA' )
        self.server = weakref.ref( server )
        self.payload = payload

    def feed( self, resp, erc, txt ):
        f = StringIO.StringIO( self.payload )
        for l in f:
            l = l.rstrip('\r\n')
            if l and l[0]=='.':
                l = '.' + l
            self.server().log( "Data: " + `l` )
            self.server().s.write( l )
            self.server().s.write( '\r\n' )
        self.server().s.write( '.\r\n' )
        self.server().flush()

class connection(infotrope.xtp.connection):
    def __init__( self, uri, env ):
        if uri.port is not None:
            ports = uri.port
        elif uri.scheme in ['ssmtp','smtps']:
            ports = [465]
        else:
            ports = [587,25]
        self._operation = env.make_operation( str(uri), "Connecting", 5 )
        self._op_stage = 0
        infotrope.xtp.connection.__init__( self, uri, ports, env , using_alt_port=(uri.scheme=='ssmtp') )
        self._ehlo_complete = False
        self._compress_tried = False
        self._burl_ehlo = False
        self.caps = {}
        self._esmtp = True
        self._idle = False
        self._trans = []
        self._this_trans = None
        self._imap_friends = []
        self.do_connect()

    def add_transaction( self, what ):
        self._trans.append( what )
        if not self.ready:
            return
        if self._this_trans is None:
            self.trans_finished()

    def you_are_ready( self ):
        if self._operation:
            self._operation.stop()
            self._operation = None
        if self.ready:
            self.trans_finished()

    def trans_finished( self ):
        import sys
        self._this_trans = None
        if self._trans:
            self._this_trans = self._trans[0]
            self._trans = self._trans[1:]
            if self.have_capability('BURL') and not self._burl_ehlo:
                self.cmd_ehlo( self.post_burl_ehlo )
                self._operation = self.env.make_operation( str(self.uri), "Getting BURL Data" )
            else:
                self.send( 'RSET' )
                self._this_trans.start()

    def reset( self ):
        cmd = self.send('RSET')
        self.wait( cmd )
        
    def post_burl_ehlo( self, *args ):
        self.ehlo_complete( *args )
        self._burl_ehlo = True
        self._this_trans.start()
        if self._operation:
            self._operation.stop()
            self._operation = None
        
    def get_capability( self, what ):
        while not self._ehlo_complete:
            self.fetch()
        what = what.upper()
        if what in self.caps:
            return self.caps[what]
        return []

    def have_capability( self, what ):
        while not self._ehlo_complete:
            self.fetch()
        what = what.upper()
        return what in self.caps

    def cmd_ehlo( self, then ):
        c = 'HELO'
        if self._esmtp:
            c = 'EHLO'
        import socket
        t = self.send( '%s %s' % ( c, socket.gethostname() ), True )
        if then:
            t.oncomplete( then )
        self.flush()

    def cmd_mail( self, who ):
        t = self.send( 'MAIL FROM:<%s>' % who )
        self.flush()
        return self.wait( t )

    def cmd_rcpt( self, who ):
        t = self.send( 'RCPT TO:<%s>' % who )
        self.flush()
        return self.wait( t )
    
    def post_banner( self, txt ):
        self._esmtp = True
        self.cmd_ehlo( self.ehlo_complete )
        if self._operation:
            self._operation.update( "Getting capabilities", 1 )

    def ehlo_complete( self, cmd, resp, erc, txt ):
        if ( resp & 0xF00 ) != 0x200:
            self._esmtp = False
            self.cmd_ehlo( self.ehlo_complete )
            return
        self._ehlo_complete = True
        if (resp & 0xF00)==0x200:
            self.remote_hostname = txt[0].split(' ')[0]
            for l in txt[1:]:
                c = l.split(' ')
                capname = c[0].upper()
                if capname not in suppress_extension:
                    self.caps[capname] = [ x.upper() for x in c[1:] ]
        if not self.tls_active() and 'STARTTLS' in self.caps and infotrope.core.platform_tls():
            t = self.send( 'STARTTLS', True )
            t.oncomplete( self.stls_complete )
            self.flush()
            if self._operation:
                self._operation.update( "Activating TLS", 2 )
        elif not self.logged_in:
            self.issue_auth()

    def stls_complete( self, cmd, r, e, t ):
        print "\n<%X> <%s> <%s>\n" % (r,e,t)
        if ( r & 0xF00 ) == 0x200:
            self.s.starttls()
            self.caps = {}
            self.cmd_ehlo( self.ehlo_complete )
            if self._operation:
                self._operation.update( "Refreshing capabilities", 3 )
        else:
            self.issue_auth()

    def compress_complete( self, cmd, r, e, t ):
        self.log( "Got completed comression" )
        if ( r & 0xF00 ) == 0x200:
            import infotrope.rfc195x
            self.s.set_comp( infotrope.rfc195x.compress( 'deflate', 'smtp' ),
                             infotrope.rfc195x.decompress( 'deflate', 'smtp' ) )
        self.issue_auth()

    def have_capability( self, what ):
        return what in self.caps

    def cmd_data( self, mail=None, then=None ):
        cmd = data( self, mail )
        self.send( cmd )
        if then:
            cmd.oncomplete( then )
        self.flush()
        
    def login( self, user=None, password=None ):
        if user is None:
            user = self.uri.username
        if user == 'anonymous':
            return
        callback = infotrope.core.callback( self.env.callback, user, password )
        self.sasl = infotrope.sasl.sasl( self.uri, callback=callback, service='smtp', secquery=self.env.secquery, tls_active=self.tls_active )

    def issue_auth( self, *args ):
        self.log( "Issue auth" )
        if not self.s.compress_on() and not self._compress_tried:
            self.log( "Not compressing" )
            if self.have_capability('COMPRESS'):
                if 'DEFLATE' in self.get_capability('COMPRESS'):
                    self.log( "Send command" )
                    t = self.send( 'COMPRESS DEFLATE', True )
                    self._compress_tried = True
                    self.log( "Sent" )
                    t.oncomplete( self.compress_complete )
                    self.log( "Complete mark" )
                    self.flush()
                    self.log( "Flushed" )
                    return
        self.log("Considering auth")
        if not self.uri.username or self.uri.username=='anonymous':
            self.auth_complete(None)
            return
        try:
            self.log("Doing SASL auth")
            cmd = auth( None, self )
            self.log("SASL auth command ready")
        except:
            if self._operation:
                self._operation.stop()
            return
        self.log("Sending...")
        self.send( cmd, True )
        self.log("... Done")
        self.flush()
        if self._operation:
            self._operation.update( "Authenticating", 4 )

    def reference_url( self, url, data ):
        if self.s.compressing():
            self.send( 'RURL %s' % url )
            self.flush()
            self.s.preload_compressor( data )
            self.s.flush()
        
    def get_trprops( self ):
        import infotrope.message
        avail = ['7bit','quoted-printable','base64']
        schemes = []
        trusted = []
        if self.have_capability( '8BITMIME' ):
            avail.append( '8bit' )
        if self.have_capability( 'BINARYMIME' ):
            avail.append( 'binary' )
        if self.have_capability( 'BURL' ):
            import infotrope.url
            for x in self.caps['BURL']:
                if ':' not in x:
                    schemes.append( x.lower() )
                else:
                    u = infotrope.url.URL( x.lower() )
                    trusted.append( u )
                    schemes.append( u.scheme )
        trp = infotrope.message.TrProps( encodings=avail, schemes=schemes, trusted=trusted, maxline=998, chunked=self.have_capability( 'CHUNKING' ), uriratifier=self.uriratifier )
        self.log( `trp` )
        return trp

    def add_friend( self, uri ):
        self._imap_friends.append( uri.root_user().asString() )

    def uriratifier( self, uris ):
        import infotrope.url
        if not isinstance( uris, list ):
            uris = [uris]
        uris = [ infotrope.url.URL( u ) for u in uris ]
        uri = uris[0]
        if uri.scheme != 'imap':
            raise "Erk!"
        import infotrope.serverman
        sm = infotrope.serverman.get_serverman()
        srv = sm[uri]
        import time
        if uri.root_user().asString() in self._imap_friends:
            uris = srv.genurlauth( uris, expire=time.time()+600, role='submit', userid=self.uri.username )
        else:
            uris = srv.genurlauth( uris, expire=time.time()+600 )
        if uris:
            return uris[0]
        return None

    def transaction( self, fr, to, message, status=None ):
        t = transaction( fr, to, message, status, self )
        if not status:
            t.wait()

    def sendmail( self, fr, to, message ):
        import infotrope.message
        if not isinstance( message, infotrope.message.BasePart ):
            import infotrope.mime
            p = infotrope.mime.parser()
            self.transaction( fr, to, p.parse( str(message) ) )
        else:
            self.transaction( fr, to, message )
        return {}

class transaction:
    def __init__( self, fr, to, message, status, conn, reference=None ):
        self._from = fr
        self._fromcmd = None
        self._to = to
        self._tocmd = None
        self._message = message
        self._status = status
        self._esmtp = conn
        self._trlist = None
        self._operation = None
        self._complete = False
        self._sent_okay = False
        self._ref = reference
        self._error_text = None
        self._operation = self._esmtp.env.make_operation( "Sending Message", "Waiting for connection", 7 )
        self._esmtp.notify_ready( self._connection )

    def check_error( self, *args ):
        if self._error_text:
            return
        if args and (args[1]&0xF00)!=0x200:
            self._error_text = args[3]

    def wait( self ):
        self._esmtp.wait_ready()
        while not self._complete:
            self._esmtp.fetch()

    def _connection( self, c ):
        if self._operation:
            self._operation.update( "Queueing transaction", 1 )
        c.add_transaction( self )

    def start( self ):
        #print "\n\n\nSTART TRANSACTION\n\n\n"
        if self._operation:
            self._operation.update( "Formatting message", 2 )
        trprops = self._esmtp.get_trprops()
        self._message.send_trlist( trprops, self.trlist )

    def trlist( self, trlist ):
        if self._operation:
            self._operation.update( "MAIL FROM", 3 )
        import infotrope.message
        self._trlist = trlist
        self._trlist.reverse()
        eight = False
        binary = False
        for t,v in self._trlist:
            if t is infotrope.message.TrType.BINARY:
                binary = True
                break
            if t is infotrope.message.TrType.EIGHTBIT:
                eight = True
        if binary:
            cmd = self._esmtp.send( 'MAIL FROM:<%s> BODY=BINARYMIME' % self._from )
        elif eight:
            cmd = self._esmtp.send( 'MAIL FROM:<%s> BODY=8BITMIME' % self._from )
        else:
            cmd = self._esmtp.send( 'MAIL FROM:<%s>' % self._from )
        if self._esmtp.have_capability('PIPELINING'):
            cmd.oncomplete( self.check_error )
            while self._to:
                self.recip()
            self.data()
        else:
            cmd.oncomplete( self.recip )
            self._esmtp.flush()

    def recip( self, *args ):
        if args and (args[1]&0xF00)!=0x200:
            return self.complete( *args )
        if self._operation:
            self._operation.update( "RCPT TO", 4 )
        to = self._to.pop()
        cmd = self._esmtp.send( 'RCPT TO:<%s>' % to )
        if not self._esmtp.have_capability('PIPELINING'):
            if self._to:
                cmd.oncomplete( self.recip )
            else:
                cmd.oncomplete( self.data )
            self._esmtp.flush()
        else:
            cmd.oncomplete( self.check_error )

    def data( self, *args ):
        if args and (args[1]&0xF00)!=0x200:
            return self.complete( *args )
        if self._ref:
            self._esmtp.reference_url( self._ref[0], self._ref[1] )
        if self._operation:
            self._operation.update( "Sending data", 5 )
        if not ( self._esmtp.have_capability('CHUNKING') or self._esmtp.have_capability('BINARYMIME') ):
            self._esmtp.cmd_data( self._trlist[0][1], self.complete )
            if self._operation:
                self._operation.update( "Waiting for server", 6 )
        else:
            cmd = self._esmtp.send('BDAT 0')
            cmd.oncomplete(self.check_error)
            self.more_data()

    def more_data( self, *args ):
        trp = self._trlist.pop()
        last = ''
        if not self._trlist:
            last = ' LAST'
        if trp[0] is infotrope.message.TrType.URI:
            if False and last and self._esmtp.have_capability('CHUNKING'):
                cmd = self._esmtp.send( 'BURL ' + trp[1] )
                cmd.oncomplete( self.check_error )
                cmd = self._esmtp.send( 'BDAT 0 LAST' )
            else:
                cmd = self._esmtp.send( 'BURL ' + trp[1] + last )
        else:
            cmd = self._esmtp.send( 'BDAT %d' % len(trp[1]) + last + '\r\n' + trp[1], nocrlf=True )
        if not self._trlist:
            self._esmtp.flush()
            if self._operation:
                self._operation.update( "Waiting for server", 6 )
            cmd.oncomplete( self.complete )
        elif not self._esmtp.have_capability('PIPELINING'):
            cmd.oncomplete( self.more_data )
            self._esmtp.flush()
        else:
            cmd.oncomplete( self.check_error )
            self.more_data()

    def complete( self, cmd, resp, erc, text ):
        if self._operation:
            self._operation.stop()
            self._operation = None
        self._esmtp.trans_finished()
        self._complete = True
        if (resp&0xF00)!=0x200:
            self._sent_okay = False
            if self._status:
                self._status( False, self._error_text or text )
        else:
            self._sent_okay = True
            if self._status:
                self._status( True, self._error_text or text )

if __name__=='__main__':
    smtp = connection( 'gateway', 587 )
    smtp.cmd_auth( user='dwd', password='Thisisnotmyrealpassword' )
    smtp.sendmail( 'dave@cridland.net', ['dave.cridland@clues.ltd.uk','dwd@clues.ltd.uk'], 'From: Dave Cridland <dave@cridland.net>\r\nTo: Dave Cridland <dave.cridland@clues.ltd.uk>\r\nCc: Dave Cridland <dwd@clues.ltd.uk>\r\nSubject: This is a test\r\n\r\nThis is a very simple test of the ESMTP code.\r\n' )
    print `smtp.cmd_quit()`
    # Parse a few nasty cases:
    print "[%s] %X %s %s" % smtp.parse( '220\r\n' )
    print "[%s] %X %s %s" % smtp.parse( '220Some text\r\n' )
    print "[%s] %X %s %s" % smtp.parse( '220 1.47.23 This is not a legal extended response code.\r\n' )
    print "[%s] %X %s %s" % smtp.parse( '220 2.47.23 This is a legal extended response code.\r\n' )
