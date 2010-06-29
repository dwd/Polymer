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

import errno
import socket
import infotrope.url
import infotrope.socketry
import infotrope.core
from infotrope.weak import weakref
import time

_idle_time = 5.0

import sys
if sys.platform.find('symbian')==0:
    _idle_time = 10.0

class command(infotrope.core.command):
    def __init__( self, env, tag, cmd, use_tags=True, pre_state=None ):
        infotrope.core.command.__init__( self, env, tag )
        self.command = cmd
        self.response = None
        self.payload = None
        self.feeding = False
        self.resend = True
        self.sent_lit = False
        self.pending_literal = None
        self.time_sent = None
        self.counter_sent = None
        self.time_recv = None
        self.idle_command = False
        self.use_tags = use_tags
        if cmd is None:
            self.resend = False
        self.sent = False
        self.sent_complete = False
        self.pre_state = pre_state

    def reset(self):
        self.tokens = self.toks()
        self.sent = False
        self.sent_complete = False

    def toks(self,stok=None):
        space = False
        if stok is None:
            if self.use_tags:
                yield self.tag
                space = True
            ts = self.command
        else:
            ts = stok
        for tok in ts:
            if space:
                yield ' '
            space = True
            if isinstance(tok,list) or isinstance(tok,tuple):
                yield '('
                for x in self.toks(tok):
                    yield x
                yield ')'
            elif tok is None:
                yield 'NIL'
            else:
                yield tok
        
    def complete( self, t, r, s ):
        #import sys
        #sys.stderr.write( "Tag %s, command %s, complete with %s (%s)" % ( self.tag, self.command, r, s ) )
        if self.response is None:
            self.response = r
            self.payload = s
        else:
            raise "Erm... Command completed twice?"
        if self.time_recv is None:
            self.time_recv = time.time()
        self.notify_complete( t, r, s )

    def __repr__( self ):
        return "infotrope.base.command( %s, %s )" % ( `self.tag`, `self.command` )

    def feed( self, payload ):
        raise infotrope.base.connection.exception( "Command fed, but not hungry." )

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

class connection(infotrope.core.connection):
    class pipeline:
        def __init__( self, c ):
            self.c = c
        def __del__( self ):
            self.c.end_pipeline()
    
    class exception(infotrope.core.exception):
        def __init__( self, msg ):
            infotrope.core.exception.__init__( self, msg )

    class need_more:
        def __init__( self ):
            pass
    
    def __init__( self, uri, environment, connectasync=False, using_alt_port=False ):
        infotrope.core.connection.__init__( self, uri, None, environment, connectasync, using_alt_port )
        self._in_pipeline = False
        self._idle_time = _idle_time
        self._waiting = 0
        self._taghit = 0
        self.sync_lit = True
        self.ns_lit = False
        self.use_tags = True
        self.have_literal8 = False
        self.ns_lit8 = True
        self._resyncs = []
        self._auto_reconnect = False
        self.last_prod = time.time()
        self.last_send = time.time()
        self.tags = weakref.WeakValueDictionary()
        self.connectasync = connectasync
        self.reconnect_switch = False
        self.state = 'dead'
        self.queue = {}
        self.report_fail = True
        self._line_buffer = ''
        self._line_want = None # Line, +ve int means num octets, 0 means line.
        self._line_start = None
        self.bandwidth = None
        self._bandwidth_stats = []
        self.latency = 0
        self.set_state('init')
        self.__logout_command = None
        self.do_connect()

    def set_state(self, newstate, reason=None):
        if self.state == newstate:
            return
        self.state = newstate
        if self.state == 'dead':
            for tag,cmd in self.inprog.items():
                cmd.complete(tag, 'BAD', 'Server disconnected')
            self.inprog = {}
        self.log('State change to %s (%s)' % (newstate, reason or 'No reason'))
        self.send_next_command()
        
    def set_line_buffer( self, s ):
        self._line_buffer = s

    def append_line_buffer( self, s ):
        self._line_buffer += s

    def secret_sauce_ssl( self ):
        self.switch_tls()
        self.secret_sauce()
        
    def logged_in_as( self, who ):
        self.set_state('auth','Logged in as %s' % who)
        self.logged_in = who
        self.ready = True
        self.report_fail = not self._auto_reconnect
        self.send_notify_ready()

    def wait_ready( self ):
        self.wait_connected()
        while not self.ready and not self.dead():
            self.fetch()
        
    def set_idle_time( self, newidle ):
        if newidle < 1.0:
            newidle = 1.0
        self._idle_time = newidle

    def adjust_idle_time( self, sample ):
        self.set_idle_time( ( self._idle_time + sample ) / 2.0 )

    def secret_sauce( self ):
        self.env.status( "Connected to " + str(self.uri) )
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

    def you_are_ready( self ):
        self.full_reconnect_state()

    def start_pipeline( self ):
        self._in_pipeline = False
        return connection.pipeline( self )
    def end_pipeline( self ):
        self._in_pipeline = False
        self.flush()

    def read_banner(self):
        pass

    def have_starttls( self ):
        return False
    
    def switch_tls( self ):
        if self.tls_active():
            raise connection.exception( "Attempt to switch to TLS twice!" )
        self.s.starttls()

    def add_resync( self, callable ):
        self._resyncs = [ x for x in self._resyncs if x() is not None ] + [ weakref.ref(callable) ]

    def username( self ):
        return self.logged_in

    def login( self, username = None, password = None ):
        raise connection.exception("Protocol has no login defined.")

    def connected( self ):
        if self.s is None:
            return False
        self.s.prod()
        return self.s.is_connected()

    def fileno( self ):
        return self.s.fileno()

    def selectable( self ):
        return self.s.selectable()

    def register( self, tag, command ):
        if command is not None:
            self.tags[ str(tag) ] = command
        else:
            del self.tags[ str(tag) ]

    def nparser(self, s, i=0, l=None, depth=None, justone=False, emptyok=False,
                fetchparts=False, processor=None, prockey=None, genex=True):
        try:
            l = l or []
            depth = depth or 0
            while i < len(s):
                if s[i] == ' ':
                    i += 1
                    continue
                if s[i] == '(':
                    i += 1
                    state, i, sl = self.nparser( s, i, depth=depth+1, fetchparts=fetchparts )
                    l.append(sl)
                    if justone:
                        return None,i,l[0]
                    continue
                if s[i] == '"':
                    buf = ''
                    i += 1
                    while True:
                        bs = s.find('\\', i)
                        bq = s.index('"', i)
                        if bs != -1 and bs < bq:
                            buf += s[i:bs]
                            buf += s[bs+1]
                            i = bs + 2
                            continue
                        buf += s[i:bq]
                        i = bq + 2
                        break
                    i -= 1
                    l.append(buf)
                    if justone:
                        return None,i,l[0]
                    continue
                if s[i] == ')':
                    return True,i+1,l
                if s[i:i+2] == '\r\n':
                    if depth or ( justone and not emptyok ):
                        sys.exit()
                        raise ValueError, "Need more data"
                    self.set_line_buffer(s[i+2:])
                    self._line_want = None
                    return False,i+2,l
                if self.have_literal8 and s[i:i+2] == '~{':
                    crlf = s.index('}',i+2)
                    crlf += 1
                    if s[crlf:crlf+2] != '\r\n':
                        self._line_want = 0
                        raise ValueError, "CRLF not found"
                    ll = int(s[i+2:crlf-1])
                    tok = s[crlf+2:crlf+2+ll]
                    if processor:
                        processor( prockey, tok, ll )
                    if len(tok) != ll:
                        self._line_want = ll - len(tok)
                        raise ValueError, "More data needed"
                    l.append(tok)
                    i = crlf + 2 + ll
                    if justone:
                        return None,i,l[0]
                    continue
                if s[i] == '{':
                    crlf = s.index('}',i+1)
                    crlf += 1
                    if s[crlf:crlf+2] != '\r\n':
                        self._line_want = 0
                        raise ValueError, "CRLF not found"
                    ll = int(s[i+1:crlf-1])
                    tok = s[crlf+2:crlf+2+ll]
                    if processor:
                        processor( prockey, tok, ll )
                    if len(tok) != ll:
                        self._line_want = ll - len(tok)
                        raise ValueError, "More data needed"
                    l.append(tok)
                    i = crlf + 2 + ll
                    if justone:
                        return None,i,l[0]
                    continue
                self._line_want = 0
                bs = s.find(' ',i)
                bp = s.find(')',i)
                br = s.find('\r',i)
                if bs == -1 or (bp != -1 and bs > bp):
                    bs = bp
                if bs == -1 or (br != -1 and bs > br):
                    bs = br
                if bs == -1:
                    if genex:
                        raise ValueError, "More data needed for Atom"
                    else:
                        bs = len(s)
                if fetchparts:
                    if '[' in s[i:bs]:
                        if ']' not in s[i:bs]:
                            bs = s.index(']',i) + 1
                buf = s[i:bs]
                if buf.upper() == "NIL":
                    l.append(None)
                else:
                    l.append(buf)
                i = bs
                self._line_want = None
                if justone:
                    return None,i,l[0]
            if genex:
                raise ValueError, "More Data needed"
            return None,i,l
        except ValueError,e:
            #print "\nNeed more?",e,"\n"
            raise connection.need_more()

    
    def default_parse( self, tag, resp, ss ):
        import cStringIO
        saved = ss
        fs = cStringIO.StringIO( ss )
        more_lines = False
        while True:
            l = fs.readline()
            self.log( "Read: %s // %s" % (`l`,more_lines) )
            if more_lines and -1==l.find('\r\n'):
                self._line_want = 0
                raise connection.need_more()
            more_lines = False
            l = l.rstrip( '\r\n' )
            self.log( "Check: %s" % `l` )
            if l[-1:]=='}':
                sp = l.rfind( ' ' )
                br = l.rfind( '(' )
                sp = max( sp, br )
                lit = l[sp+1:-1]
                self.log( "Checklit: %s" % `l` )
                if lit[0] == '{':
                    lit = int(lit[1:])
                elif self.have_literal8 and lit[0:2]=='~{':
                    lit = int(lit[2:])
                if isinstance(lit,int):
                    splurge = fs.read( lit )
                    self.log( "Checklitlen: %d" % len(splurge) )
                    if len(splurge)!=lit: # EOF reached!
                        self.log( "Checklitlen: FAIL" )
                        self._line_wait = lit-len(splurge)
                        raise connection.need_more()
                    else:
                        self.log( "Checklitlen: PASS: More lines" )
                        more_lines = True
            if not more_lines:
                self.log( "Nomore." )
                break
        self._line_buffer = fs.read()
        return tag, resp, saved[:len(self._line_buffer)]

    def line_wants( self ):
        if self._line_buffer == '':
            self._line_want = 0
            return
        tmp = self._line_buffer
        try:
            self.default_parse( '', '', self._line_buffer )
            self.log( "Default parse completed." )
            self._line_want = None
        except connection.need_more:
            self.log( "Exception with %s" % `self._line_want` )
            pass
        self._line_buffer = tmp

    def trim_to_line( self, s ):
        if -1!=s.find('\r\n'):
            self._line_buffer = s[s.index('\r\n')+2:]
            s = s[:s.index('\r\n')]
        return s
    
    def parse_first( self, s ):
        state,i,tag = self.nparser(s, justone=True)
        if tag == '+':
            return tag, '', s[i:]
        state,i,resp = self.nparser(s, i, justone=True)
        self.log( "Tag is %s, resp is %s" % ( `tag`,`resp` ) )
        methcall = None
        if resp.isdigit():
            num = resp
            state,i,resp = self.nparser(s, i, justone=True)
            method = '_parse_num_' + self.state + '_' + resp.lower()
            s = s[i:].lstrip(' ')
            try:
                methcall = getattr(self,method)
            except AttributeError:
                pass
            if methcall is None:
                try:
                    method = '_parse_num_' + resp.lower()
                    methcall = getattr(self,method)
                except AttributeError:
                    pass
            if methcall is None:
                return self.default_parse(tag, resp, num + ' ' + s)
            else:
                return methcall(tag, resp, num, s)
        else:
            s = s[i:].lstrip(' ')
            method = '_parse_' + self.state + '_' + resp.lower()
            try:
                methcall = getattr(self,method)
            except AttributeError:
                pass
            if methcall is None:
                method = '_parse_' + resp.lower()
                try:
                    methcall = getattr(self,method)
                except AttributeError:
                    methcall = self.default_parse
            return methcall(tag, resp, s)
        
    def parse( self, str ):
        now = time.time()
        now_data = self.s.count_recv()
        t,r,s = self.parse_first( str )
        #print "Trying to handle: %s %s %s" % ( `t`, `r`, `s` )
        cmd = None
        if t in self.inprog:
            cmd = self.inprog[t]
        if t!='*' and r.upper() in ['OK', 'NO', 'BAD']:
            #print "Command termination?",`t`,`cmd`
            last = self.last_command
            if last == t:
                self.last_command = None
            if t in self.inprog:
                del self.inprog[t]
                if cmd.counter_sent is not None:
                    delta_data = now_data - cmd.counter_sent
                    delta_time = now - cmd.time_sent
                    if delta_data > 256 and delta_time > 0.001:
                        self._bandwidth_stats.append( (delta_data,delta_time) )
                        tD,tT = 0.0,0.0
                        for dD, dT in self._bandwidth_stats:
                            tD += dD * dD
                            tT += dT * dD
                        self.bandwidth = tD * 8.0 / tT
                        self._bandwidth_stats = self._bandwidth_stats[-20:]
                #print "Complete."
                cmd.complete( t, r, s )
                #print "Done."
            else:
                self.env.alert( self.uri, "Unknown command %s" % t )
            self.send_next_command()
        if t == '+':
            if self.last_command is not None:
                if self.last_command.feeding:
                    self.log('Last command is feeding')
                    self.last_command.feed( s )
                if not self.last_command.feeding: # Finished feeding.
                    self.log('Last command not feeding.')
                    if not self.last_command.sent_complete:
                        self.log("Completing send of last command")
                        self.send_real(self.last_command,{})
                    self.send_next_command()
            # After this, it's always safe to wipe the line buffer. ?
            self.set_line_buffer( '' )
        handler = self.tags.get(t, None)
        if handler is not None:
            #print "Have handler object", `self.tags[t]`
            #print "Looking for _handle_%s" % r.lower()
            handlecall = None
            try:
                handlecall = getattr(handler,'_handle_'+r.lower())
            except AttributeError:
                pass
            if handlecall is not None:
                tag,r,s = handlecall(cmd, r, s)
        if t == '*' and r.upper() == 'BYE':
            self.fail_reason = s
            for ptag,pcmd in self.inprog.items():
                if pcmd.command[0].lower() == 'LOGOUT':
                    self.fail_reason = None
            if self.fail_reason:
                self.env.alert(self.uri, "Server closed connection:\n%s" % self.fail_reason)
        return t,r,s

    def fetch( self, genexcept=False, auto_reconnect=True ):
        ''' Fetch a line, parse it, and return the result. '''
        #if not genexcept:
        #    print "\n\nSYNC FETCH!\n"
        foo = ''
        if self.s is None:
            self.set_state('dead', 'No socket 549')
            #self.s = None
            #self._logged_out = True
            if auto_reconnect:
                self.log( "Reconnecting due to fetch." )
                self.reconnect()
            elif genexcept:
                self.onfail( "Not connected during fetch" )
                raise socket.error( errno.EPIPE, "Not connected." )
            else:
                self.onfail( "Not connected during fetch" )
                return '*','BYE','Not connected.'
        fail = False
        try:
            #print "Buffer is",`self._line_buffer`
            if not self._line_buffer:
                self._line_want = 0
            #lw_orig = self._line_want
            #self.line_wants()
            #if lw_orig != self._line_want:
            #    print "Buffer:",`self._line_buffer`,"LW::",`lw_orig`,`self._line_want`
            #    sys.exit()
            #print "Buffer is",`self._line_buffer`,"=>",`self._line_want`
            if self._line_want is not None:
                foo = ''
                while self.s is not None and self.s.is_connected():
                    if self._line_want is None:
                        break
                    if self._line_want is 0:
                        self.log("Reading a line")
                        tmp = self.s.readline( genexcept=genexcept )
                        if '\r\n' != tmp[-2:]:
                            self.set_state('dead', 'No CRLF 581')
                            self.proto_log_commit("<<< [disconnected]")
                            raise socket.error( errno.EPIPE, "Disconnected during fetch." )
                        self._line_want = None
                        #print "Checking line termination:"
                        if tmp[-3:] == '}\r\n':
                            self.log( "} found" )
                            ob = tmp.rfind('{')
                            if ob != -1:
                                try:
                                    #print "Literal"
                                    self._line_want = int(tmp[ob+1:-3])
                                    #print "OK"
                                except:
                                    pass
                    else:
                        self.log( "Reading %d octets with genexcept=%s" % ( self._line_want, genexcept ) )
                        tmp = self.s.read( self._line_want, genexcept=genexcept )
                        self._line_want -= len(tmp)
                    #print "Add to foo"
                    foo += tmp
                    pfx = '<<<'
                    if self._line_buffer != '':
                        pfx = ' <<'
                    self._line_buffer += tmp
                    self.proto_log_commit( "%s%s %s" % ( self.s.fileno() or '', pfx, tmp ) )
                    self.last_prod = time.time()
                else:
                    raise socket.error( errno.EAGAIN, "Not yet connected." )
        except socket.error, e:
            self.log( "Exception during fetch: %s" % e )
            if e.args[0]!=errno.EAGAIN:
                self.log( "Exception during fetch: %s" % e )
            if e.args[0]!=errno.EPIPE:
                raise e
            else:
                fail = True
        #self.bandwidth = self.s.bandwidth()
        if fail:
            self.log( "Disconnected during fetch." )
            if not self.logged_out:
                if auto_reconnect:
                    self.log( "Reconnecting..." )
                    self.reconnect()
                    if genexcept:
                        raise socket.error( errno.EGAIN, "Reconnecting." )
                    else:
                        return '*','NO','Reconnecting'
                else:
                    self.log( "No auto-reconnect, shutting down." )
                    self.s = None
                    self.set_state('dead', '632')
                    self.reset_state()
                    self.ready = False
                    self.logged_out = True
                    if genexcept:
                        self.onfail( "Not connected during fetch" )
                        self.log( "Raising exception." )
                        raise socket.error( errno.EPIPE, "Remote host closed connection." )
                    else:
                        self.onfail( "Not connected during fetch" )
                        return '*','DEAD','Synthetic: Remote host closed connection.'
            else:
                self.log( "Already logged out." )
                if genexcept:
                    self.onfail( "Not connected during fetch" )
                    self.log( "Raising exception." )
                    raise socket.error( errno.EPIPE, "Already disconnected." )
                else:
                    self.onfail( "Not connected during fetch" )
                    return '*','DEAD','Already logged out, this is synthetic.'
        try:
            t,r,s = self.parse( self._line_buffer[:] )
            self.log("Parse complete")
            return t,r,s
        except connection.need_more:
            #print "\n\nRecurse Two\n"
            return self.fetch( genexcept, auto_reconnect )
        except:
            self._line_buffer = ''
            import sys
            print "EXCEPTION IN fetch:",sys.exc_info()[1],`sys.exc_type`
            raise

    def reset_state( self ):
        pass

    def restore_state( self ):
        pass

    def reconnect( self ):
        self.log( "Reconnect called" )
        if self.reconnect_switch and self.s is not None and not self.s.dead():
            self.log( "Not actually dead." )
            return
        self.ready = False
        self.log( "Resetting state" )
        self.reset_state()
        self.log( "State reset" )
        self.logged_out = False
        self.reconnect_switch = True
        self.do_connect()
        self.set_state('init','Reconnect 683')
        
    def full_restore_state( self ):
        self.log( "Full restore state" )
        if not self.reconnect_switch:
            self.log( "Abstaining state restoration" )
            return
        self.reconnect_switch = False
        if self.logged_in is not None:
            self.login( user=self.logged_in )
        self.log( "Copying untagged listeners" )
        #print "Restoring state"
        t = self.tags
        if '*' in self.tags:
            t['*'] = self.tags['*']
        self.tags = t
        self.log( "Restoring local state" )
        self.restore_state()
        self.log( "Clearing inprog" )
        #print "State restored."
        tmp = {}
        tmp.update( self.inprog )
        self.inprog = {}
        self.log( "Resending" )
        for t,c in tmp.items():
            if c is not None and c.resend:
                self.log( "Resending %s : %s" % (`t`,`c`) )
                c.reset()
                tn,r,s = self.send( c )
        self.log( "Client object resyncs" )
        for x in self._resyncs:
            y = x()
            if y is not None:
                y( self )
        self.log( "State restore complete" )
        #print "Done reconnect."

    def auto_reconnect( self, foo=True ):
        self._auto_reconnect = foo
        
    def prod( self ):
        '''Process one or more lines if and only if there are lines to process.'''
        try:
            if self._auto_reconnect:
                if self.s is None or self.s.dead():
                    self.set_state('dead', 'Prod 727')
                    #print "Socket dead, reconnect"
                    self.reconnect()
            if self.s is None:
                self.set_state('dead', 'Prod 731')
                #print "No socket"
                return False
            if self._waiting:
                #print "Waiting"
                return False
            fooness = False
            #print "Prod!",`self._auto_reconnect`,`self.s`
            while self.s is not None and self.s.prod():
                try:
                    #print " Prod is trying fetch on",`self.s.fileno()`
                    r = self.fetch( genexcept=True, auto_reconnect=self._auto_reconnect )
                    #print " Prod fetch suceeded with ",`r`
                    fooness = True
                except socket.error, e:
                    break
            if not fooness and self.s is not None and self.s.is_connected():
                if ( time.time() - self.last_send ) > self._idle_time:
                    self.idle_handler( True )
            return fooness
        except socket.error, e:
            #print "Exception:",`e`,e
            if e.args[0] == errno.EPIPE:
                self.s.close()
                self.s = None
                self.set_state('dead', 'Prod exception 756')
                if self._auto_reconnect:
                    self.reconnect()
                else:
                    self.onfail( e.args[1] )
    
    def wait( self, tag, noincr=False, noidle=False, reconnect=True, wait_plus=False ):
        save_auto_reconnect = self._auto_reconnect
        self._auto_reconnect = reconnect
        start_data = 0
        start_time = 0
        try:
            self._waiting += 1
            if self.s is None or not self.s.is_connected():
                self.set_state('dead', 'wait 770')
                self.log( "Need to reconnect for wait." )
                self.reconnect()
                self.wait_ready()
            if not isinstance(tag, list):
                tag = [tag]
            alltags = tag[:]
            tag = []
            for tt in alltags:
                if isinstance( tt, command ):
                    tag.append( tt )
                else:
                    try:
                        tag.append( self.inprog[tt] )
                    except KeyError:
                        c = command( self.env, tt, None )
                        tag.append( c )
                        self.inprog[ tt ] = c
            self.log("Waiting for %s" % `tag`)
            self.flush()
            lt,lr,ls = None,None,None
            while True:
                t,r,s = self.fetch()
                self.log(" [ During wait: %s %s %s ]" % ( `t`, `r`, `s` ))
                for tt in tag:
                    if tt.response is not None:
                        if tt.response.upper() in ['NO','BAD']:
                            #print " -- Wait interrupted by error."
                            return tt,tt.response,tt.payload
                        else:
                            lt,lr,ls = tt,tt.response,tt.payload
                        del tag[tag.index(tt)]
                if t == '+' and wait_plus:
                    self.log( " -- Wait interrupted, more data required.")
                    return t,r,s
                if len(tag) == 0:
                    #print " -- Wait completed, none remain."
                    return lt,lr,ls
                if r.lower()=='dead':
                    return t,r,s
        finally:
            self._waiting -= 1
            self._auto_reconnect = save_auto_reconnect
    
    def generic_parse( self, s ):
        "Generically parse any server response."
        state,i,rtok = self.nparser(s)
        return rtok

    def logout( self, phase2=False ):
        self.log( "Logout" )
        if not self.logged_out and self.s is not None and self.s.is_connected():
            self.log( "Sending logout" )
            t,r,s = self.send( 'LOGOUT' )
            self.__logout_command = t
            self.flush()
            self.logged_out = True
            if not phase2:
                self.logout_phase2()

    def logout_phase2(self):
        if self.__logout_command is not None:
            self.wait( self.__logout_command, reconnect=False )
            self.log( "Logout complete" )
            if self.s is not None:
                self.s.close()
                self.s = None
            self._connected = False
            self._auto_reconnect = False
            self.logged_in = None
            self.log( "Socket killed." )
            self.tags = {}
            self.log( "Local logout" )
            self.local_logout()
            self.log( "Done" )
            
    def local_logout( self ):
        pass

    def write_cmd_chunk( self, tag, what, space=False ):
        if space:
            self.s.write( ' ' )
            self.proto_log( ' ' )
        if what is None:
            self.s.write( "NIL" )
            self.proto_log( 'NIL' )
        elif isinstance( what, infotrope.base.literal ):
            if not tag or what is not tag.pending_literal:
                if tag:
                    tag.pending_literal = what
                use_nslit = True
                if len(what.payload)>1024:
                    if not tag.sent_lit:
                        use_nslit = False
                        tag.sent_lit = True
                if what.binary:
                    use_nslit = False
                else:
                    if not self.ns_lit:
                        use_nslit = False
                if not self.sync_lit:
                    use_nslit = True
                self.s.write( "%s\r\n" % what.token( use_nslit ) )
                self.proto_log( what.token( use_nslit ) )
                self.proto_log_crlf()
                if not use_nslit:
                    return True,None,None
            if tag:
                tag.pending_literal = None
            self.s.write( what.payload )
            self.proto_log( what.payload )
        else:
            self.s.write( str(what) )
            self.proto_log( str(what) )
        return None,None,None

    def idle_handler( self, enter ):
        pass

    def flush( self ):
        if self.s is None or self.s.dead():
            return
        if not infotrope.core.connection.flush(self):
            return False
        self.last_prod = time.time()
        self.last_send = time.time()
        for t in self.inprog.values():
            if t.time_sent is None:
                t.time_sent = self.last_prod
        return True

    def enqueue_command( self, cmd, queue ):
        self.queue.setdefault(queue,[]).append(cmd)
        self.send_next_command()

    def send_next_command(self):
        self.log("Sending next command.")
        if self.last_command:
            if self.last_command.feeding or self.last_command.pending_literal:
                self.log("Last command is feeding or has pending literal")
                return
        states = [self.state] + self.valid_states()
        self.log("Looking for command from states %s" % (`states`))
        for s in states:
            cqueue = self.queue.get(s,[])
            while cqueue:
                cmd = cqueue[0]
                cqueue = cqueue[1:]
                if cqueue:
                    self.queue[s] = cqueue
                else:
                    try:
                        del self.queue[s]
                    except KeyError:
                        pass
                self.send_real(cmd,{'pipeline':True})
                if self.last_command.feeding or self.last_command.pending_literal: # Blocking.
                    self.log("New command is feeding or has pending literal")
                    return
                cqueue = self.queue.get(s,[])
        if not self.commands_in_progress():
            self.log("No command in valid state to send - changing state.")
            for s in self.queue.keys():
                self.log("Considering state change to %s" % s)
                if self.change_state(s):
                    self.log("Initiated state change to %s" % s)
                    break
        self.flush()

    def commands_in_progress(self):
        return len([x for x in self.inprog.values() if x.response is None and not x.idle_command])

    def valid_states(self):
        return ['any']

    def change_state(self, newstate):
        raise "Don't know how to change to %s" % newstate
    
    def send( self, *cmd, **kw ):
        try:
            tag,cmd = self.tuples_to_commands(cmd)
            if 'state' in kw:
                #print "Queueing"
                self.enqueue_command(tag,kw['state'])
                return tag,None,None
            else:
                #print "Sending",`tag`
                t,r,s = self.send_real( tag, kw )
            return t,r,s
        except infotrope.base.connection.exception, e:
            if had_nslit8 is None:
                self.ns_lit8 = False
                return self.send_real( tag, kw )
            raise e

    def new_tag(self):
        self._taghit += 1
        tag = ''
        tag += chr(ord('A')+(self._taghit % 26))
        th = self._taghit / 26
        while th:
            tc = th % 36
            if tc >= 26:
                tag += chr(ord('0')+tc-26)
            else:
                tag += chr(ord('A')+tc)
            th /= 36
        return tag

    def tuples_to_commands( self, cmd ):
        while True:
            if isinstance(cmd, command):
                break
            if len( cmd )==1:
                if isinstance(cmd[0],tuple):
                    cmd = cmd[0]
                elif isinstance(cmd[0],list):
                    cmd = cmd[0]
                elif isinstance(cmd[0], command):
                    cmd = cmd[0]
                else:
                    break
            else:
                break
        if isinstance( cmd, command ):
            self.log( "Sending command %s, reusing tag %s" % ( `cmd.command`, `cmd.tag` ) )
            if cmd.tag is None:
                cmd.tag = self.new_tag()
            tag = cmd
            cmd = cmd.command
            tag.use_tags = self.use_tags
        else:
            tag = command( self.env, self.new_tag(), cmd, use_tags=self.use_tags )
        return tag, cmd
    
    def send_real( self, tag, kw ):
        pipeline = False
        if 'pipeline' in kw:
            pipeline = kw['pipeline']
        if not tag.idle_command:
            self.idle_handler(False)
        self.inprog[ tag.tag ] = tag
        if tag.sent == False:
            tag.reset()
        tag.sent = True # Started sending
        try:
            if tag.pending_literal: # Write out any pending literal.
                t,r,s = self.write_cmd_chunk( tag, tag.pending_literal )
            for x in tag.tokens: # Write out (the rest of) the command.
                t,r,s = self.write_cmd_chunk( tag, x )
                self.last_command = tag
                if t is True:
                    self.flush() # Waiting for continue, flush anyway.
                    return tag,None,None
                if t is not None:
                    tag.sent = True
                    return t,r,s
            self.write_cmd_chunk(tag,'\r\n')
            tag.sent_complete = True
            tag.counter_sent = self.s.count_recv()
            tag.time_sent = time.time()
            self.proto_log_done()
            if tag.pre_state:
                self.set_state(tag.pre_state, 'Prestate after %s' % tag.tag)
            if not self._in_pipeline and not pipeline:
                self.flush()
            return tag,None,None
        except socket.error, e:
            self.log( "Got socket.error during send: %s" % e )
            if e.args[0]==errno.EPIPE:
                self.set_state('dead', 'Exception while sending %s' % tag.tag)
                self.proto_log_commit("<<< [disconnect]")
                return self.send( cmd )
            raise e
        except:
            raise
    
class literal:
    def __init__( self, payload, binary=False ):
        self.payload = str(payload)
        self.binary = binary

    def token( self, nslit ):
        tok = ''
        if self.binary:
            tok = '~'
        tok += '{%d' % len(self.payload)
        if nslit:
            tok += '+'
        return tok + '}'

    def __repr__( self ):
        return 'infotrope.base.literal('+`self.payload`+')'

class string:
    def __init__( self, payload ):
        self.payload = str(payload)
        for x in ['\n','\r','\x00']:
            if self.payload.find(x)!=-1:
                raise connection.exception("Illegal string: " + `self.payload` )
        self.rep = '"' + self.payload.replace('\\','\\\\').replace('"','\\"') + '"'

    def __str__( self ):
        return self.rep

    def __repr__( self ):
        return 'infotrope.base.string('+`self.payload`+')'
