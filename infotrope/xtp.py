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
import infotrope.core
import StringIO
import errno
import socket

"""*TP, including ESMTP and NNTP base class"""

class exception(infotrope.core.exception):
    def __init__( self, resp, erc, txt ):
        infotrope.core.exception.__init__( self, txt )
        self.resp = resp
        self.erc = erc
        self.txt = txt

    def __str__( self ):
        return "%X %s %s" % ( self.resp, '', ' | '.join( self.txt ) )

class command(infotrope.core.command):
    def __init__( self, env, idc, cmd ):
        infotrope.core.command.__init__( self, env, idc )
        self.cmd = cmd
        self.resp = None
        self.erc = None
        self.txt = None

    def feed( self, r, e, t ):
        raise "Error"

    def complete( self, r, e, t ):
        self.resp = r
        self.erc = e
        self.txt = t
        self.notify_complete( r, e, t )

class connection(infotrope.core.connection):
    def __init__( self, uri, ports, env , using_alt_port = False ):
        infotrope.core.connection.__init__( self, uri, ports, env, True, using_alt_port )
        self._pipeline_length = 0
        self.state = 'pre-banner'
        self._idle = False
        self._idc_counter = 0
        self._got_counter = 0
        self.current_more = True
        self.current_resp = None
        self.current_erc = None
        self.current_txt = []
        self.do_connect()

    def handle_banner( self, resp, erc, txt ):
        try:
            self.log( "Fetching banner." )
            if (resp & 0xF00)!=0x200:
                raise exception( resp, erc, txt )
            self.post_banner( txt )
        finally:
            self._idle = True

    def post_banner( self, txt ):
        pass
        
    def fetch( self, genexcept=False ):
        '''
        Pull one response from the server.
        Returns:
        Hex encoded response code.
        3-tuple of extended response code, if any.
        List of text lines returned.
        '''
        import socket
        try:
            self.s.flush()
            while self.current_more:
                s = self.s.readline( genexcept=genexcept )
                self.current_more,self.current_resp,erc,txt = self.parse( s )
                if self.current_erc is None:
                    if erc is not None:
                        self.current_erc = erc
                self.current_txt.append( txt )
            resp,erc,txt = self.current_resp, self.current_erc, self.current_txt
            self.current_more = True
            self.current_resp = None
            self.current_erc = None
            self.current_txt = []
            #print "%X %s %s" % ( resp,erc,txt )
            if ( resp & 0xF00 ) == 0x300:
                self.last_command.feed( resp, erc, txt )
            elif resp == 0x421:
                self.fail_reason = txt[0]
            else:
                if self._got_counter > 0:
                    if self.last_command == self._got_counter:
                        self.last_command = None
                    self.inprog[self._got_counter].complete( resp, erc, txt )
                    del self.inprog[self._got_counter]
                else:
                    self.handle_banner( resp, erc, txt )
                self._got_counter += 1
                self._pipeline_length -= 1
            return resp,erc,txt
        except socket.error,e:
            fail = None
            try:
                fail = e.args[1]
            except:
                pass
            if self.s is None or self.s.dead():
                import infotrope.serverman
                sm = infotrope.serverman.try_serverman()
                if sm is not None:
                    sm.fail( self )
                fail = self.fail_reason or fail or "Connection lost"
                self.env.status( str(self.uri) + ": " + ''.join( fail ) )
            raise

    def send( self, line, preready=False, nocrlf=False ):
        self.wait_connected()
        if not preready:
            self.wait_ready()
        self._idc_counter += 1
        cmd = line
        if isinstance( cmd, command ):
            cmd.tag = self._idc_counter
        else:
            cmd = command( self.env, self._idc_counter, line )
        self.last_command = cmd
        self.inprog[self._idc_counter] = self.last_command
        self.s.write( cmd.cmd )
        if not nocrlf:
            self.s.write( '\r\n' )
        self.proto_log_commit( "%d>> %s" % ( self._pipeline_length, cmd.cmd ) )
        #print ">>%s" % line
        self._pipeline_length += 1
        return self.last_command
    
    def parse( self, line ):
        '''
        Parse an ESMTP response.
        Return True if we need more, False otherwise.
        If True, rest of tuple means:
        1) Hex encoded response code.
        2) Hex encoded 3-tuple of extended response code, if any.
        3) Text, if any.
        If False, rest of tuple may or may not be set to None.
        '''
        crlf = line.find( '\r\n' )
        if crlf!=-1:
            line = line[0:crlf]
        #print "<<%s" % line
        self.proto_log_commit( "%d<< %s" % ( self._pipeline_length, line ) )
        resp_txt = line[0:3]
        if 3==len(line):
            txt = ''
            more = False
        else:
            more = line[3]=='-'
            if more or line[3]==' ':
                txt = line[4:]
            else:
                txt = line[3:]
        resp = 0
        for i in resp_txt:
            resp *= 16
            resp += int(i)
        c_resp = ''
        if len(txt)==0:
            c_resp = None
        else:
            for i in txt:
                if c_resp=='':
                    if i=='2' or i=='5' or i=='4':
                        c_resp += i
                    else:
                        c_resp = None
                        break
                elif len(c_resp)==1:
                    if i=='.':
                        c_resp += '.'
                    else:
                        c_resp = None
                        break
                else:
                    if i.isdigit() or i=='.':
                        c_resp += i
                    elif i==' ':
                        break
                    else:
                        c_resp = None
                        break
        if c_resp is not None:
            erc = [ int(i) for i in c_resp.split('.') ]
            if len(erc)==3 and erc[1]<1000 and erc[2]<1000:
                txt = txt[len(c_resp)+1:]
                c_resp = tuple(erc)
            else:
                c_resp = None
        return more,resp,c_resp,txt

    def prod( self ):
        try:
            if not self.s.prod():
                return
            while True:
                r,e,d = self.fetch( True )
                if (r&0x0FF) == 0x21:
                    raise socket.error( errno.EPIPE, ''.join( d ) )
        except socket.error,e:
            if e.args[0]==errno.EPIPE:
                self.fail_reason = self.fail_reason or e.args[1]
                self.s.close()
                self.s = None
        if self.s is None or self.s.dead():
            import infotrope.serverman
            sm = infotrope.serverman.try_serverman()
            if sm is not None:
                sm.fail( self )
            fail = self.fail_reason or "Connection lost"
            self.env.status( str(self.uri) + ": " + ''.join( fail ) )

    def logout( self, phase2=False ):
        if self.ready:
            self.__logout_command = self.send('QUIT')
            self.flush()
            if not phase2:
                self.logout_phase2()

    def logout_phase2(self):
        self.wait(self.__logout_command)

    def wait( self, t ):
        #print "WAITING FOR",`t`
        while t.resp is None:
            #print "Needs a wait"
            self.fetch()
            #print "Waited"
        return t.resp,t.erc,t.txt
        #print "WAIT COMPLETE"

    def cmd_quit( self ):
        try:
            t = self.send( 'QUIT' )
            self.wait( t )
        except:
            pass
        
