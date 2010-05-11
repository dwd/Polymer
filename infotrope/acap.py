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

import infotrope.sasl
import infotrope.core
import infotrope.base
from infotrope.weak import weakref

#print "ACAP Module initializing."

cache_root = None

def set_cache_root( s ):
    global cache_root
    cache_root = s

def string( payload ):
    payload = str(payload)
    for x in ['\n','\r','\x00']:
        if payload.find(x)!=-1:
            return infotrope.base.literal( payload )
    lq = 2 + len(payload) + len([x for x in payload if x=='"'])
    ll = 3 + len(payload) + len(str(len(payload)))
    if lq > ll:
        return infotrope.base.literal( payload )
    return infotrope.base.string( payload )

class authenticate(infotrope.base.command):
    def __init__( self, server, use_plain=False ):
        self.server = weakref.ref(server)
        if not server.have_capability( 'SASL' ):
            raise infotrope.base.connection.exception( "ACAP server does not support SASL?" )
        self.sasl = server.sasl
        if use_plain:
            self.mech = self.sasl.mechlist( ['PLAIN'] )
        else:
            self.mech = self.sasl.mechlist( server.get_capability('SASL') )
        cmd = ['AUTHENTICATE', infotrope.base.string( self.mech.name() )]
        x = self.mech.process( None )
        if x is not None:
            cmd.append( string( x ) )
        infotrope.base.command.__init__( self, server.env, 'AUTH', cmd )
        self.feeding = True
        self.oncomplete( self.notify )
        self.resend = False

    def feed( self, s ):
        try:
            toks = self.server().generic_parse( s )
            gumph = self.mech.process(toks[0])
            self.server().write_cmd_chunk( self, string(gumph) )
            self.server().proto_log_done()
            self.server().s.write( '\r\n' )
            self.server().flush()
        except infotrope.sasl.error:
            self.server().s.write( '*\r\n' )
            self.server().proto_log('*')
            self.server().proto_log_done()
            self.server().flush()
            raise

    def notify( self, cmd, t, r, s ):
        self.notifier = None
        if r.upper()=='NO':
            if len(s)>1:
                if s[0][0].upper()=='TRANSITION-NEEDED':
                    self.sasl.transition_needed( self.mech )
                    if 'PLAIN' in self.server().get_capability('SASL'):
                        self.server().send( authenticate( self.server(), use_plain=True ) )
                        return
            self.server().env.alert( self.server().uri, s[-1] )
            self.sasl.failure( self.mech )
            self.server().send( authenticate( self.server() ) )
            return
        if r.upper()!='OK':
            raise s[-1]
        if len(s)>1:
            if s[0][0].upper()=='SASL':
                self.mech.process( s[0][1] )
        if self.mech.okay():
            self.server().auth_complete( self.mech )
            self.sasl.success( self.mech )
        else:
            raise "Mutual auth failed!"

class connection(infotrope.base.connection):
    "Encapsulates an ACAP connection, and dispatches contexts"
    
    def __init__( self, uri, env ):
        "Create an ACAP connection object."
        #print "__init__"
        if uri.port is None:
            uri.port=674
        self._capability = {}
        self._ctxt_dispatch = weakref.WeakValueDictionary()
        self.store_pending = []
        self._operation = env.make_operation( str(uri), "Connecting", 4 )
        infotrope.base.connection.__init__( self, uri, env, True )
        self.ns_lit = True
        self._cache_root = None
        if cache_root:
            import os.path
            uname = uri.username
            if uname is None:
                uname = 'anonymous'
            self._cache_root = os.path.join( cache_root, uname, uri.server, str(uri.port) )
        #print "Connected."

    def you_are_ready( self ):
        if self._operation:
            self._operation.stop()
            self._operation = None

    def cache_root( self ):
        return self._cache_root

    def read_banner( self ):
        t,r,s = self.fetch()
        if t!='*':
            raise "No idea what's going on here."
        if r.lower()!="acap":
            raise "Not an ACAP server."

    def post_tls( self, c, t, r, s ):
        if r.upper()=='OK':
            self.switch_tls()
            self.fetch()
        else:
            self.run_compress()

    def have_starttls( self ):
        return not self.tls_active() and self.have_capability( 'STARTTLS' )
        
    def starttls( self ):
        t,r,s = '*','NO','Not Supported'
        if not infotrope.core.platform_tls():
            return t,r,s
        #print "Trying RFC2595/3501 STARTTLS"
        if self.have_starttls():
            #print "Got capability, issuing command."
            t,r,s = self.send( 'STARTTLS' )
            if r is None:
                t,r,s = self.wait( t )
            if r.lower()=='ok':
                #print "Server happy, will switch."
                self.switch_tls()
                #print "Switched."
                self._capability = {}
                self.fetch()
        return t,r,s

    def local_logout( self ):
        self.log( "Local logout for ACAP" )
        self._capability = {}
        self.log( "Capability killed" )
        #self._ctxt_dispatch = weakref.WeakValueDictionary()
        self.log( "Context map killed" )
        
    def have_capability( self, what ):
        return what in self._capability

    def get_capability( self, what ):
        return self._capability[what]

    def _parse_init_acap( self, t, r, s ):
        "Parse the initial ACAP greeting, ensure it is valid."
        if t!='*':
            raise "No idea what's going on here."
        for tok in self.generic_parse( s ):
            if isinstance(tok,[].__class__):
                c = tok[0]
                l = tok[1:]
                self._capability[c]=l
            else:
                raise "Expected a list, but got a string."
        if infotrope.core.platform_tls() and self.have_starttls():
            if self._operation:
                self._operation.update( "Activating TLS", 1 )
            t2,r2,s2 = self.send( 'STARTTLS' )
            t2.notifier = self.post_tls
        else:
            self.run_compress()
        return t,r,s

    def run_compress( self ):
        if not self.s.compress_on() and self.have_capability( 'COMPRESS' ) and 'DEFLATE' in self.get_capability('COMPRESS'):
            try:
                import infotrope.rfc195x
                infotrope.rfc195x.init_zlib()
                if self._operation:
                    self._operation.update( "Compression", 2 )
                tx,rx,sx = self.send( 'COMPRESS', 'DEFLATE' )
                tx.oncomplete( self.post_compress )
                return
            except:
                pass
        self.run_authenticate()

    def post_compress( self, cmd, t, r, s ):
        if r.lower()=='ok':
            import infotrope.rfc195x
            comp = infotrope.rfc195x.compress('DEFLATE','acap')
            decomp = infotrope.rfc195x.decompress('DEFLATE','acap')
            self.s.set_comp( comp, decomp )
        self.run_authenticate()

    def run_authenticate( self ):
        if self._operation:
            self._operation.update( "Authenticating", 3 )
        self.send( authenticate( self ) )
    
    def login( self, user = None, password = None ):
        "Perform SASL based login sequence."
        if user is None:
            user = self.uri.username
        callback=infotrope.base.callback( self.env.callback, user, password )
        self.sasl = infotrope.sasl.sasl( self.uri, callback=callback, secquery=self.env.secquery, tls_active=self.tls_active )

    def _parse_entry( self, t, r, s ):
        "Generically parse an entry into tokens."
        return t,r,self.generic_parse(s)

    def _parse_addto( self, t, r, s ):
        "Parse and dispatch context ADDTO notification."
        tok = self.generic_parse(s)
        return self._ctxt_dispatch[tok[0]]._context_addto( t, r, tok )

    def _parse_change( self, t, r, s ):
        "Parse and dispatch context CHANGE notification."
        tok = self.generic_parse(s)
        return self._ctxt_dispatch[tok[0]]._context_change( t, r, tok )

    def _parse_removefrom( self, t, r, s ):
        "Parse and dispatch context REMOVEFROM notification."
        tok = self.generic_parse(s)
        return self._ctxt_dispatch[tok[0]]._context_removefrom( t, r, tok )

    def _parse_modtime( self, t, r, s ):
        "Parse and dispatch MODTIME."
        tok = self.generic_parse(s)
        if t=='*':
            return self._ctxt_dispatch[tok[0]]._handle_modtime( t, r, tok )
        return t,r,tok

    def _parse_ok( self, t, r, s ):
        return t,r,self.generic_parse(s)

    def _parse_no( self, t, r, s ):
        return t,r,self.generic_parse(s)

    def _parse_alert( self, t, r, s ):
        self.env.alert( self.uri, s )
        return t,r,s

    def register_context( self, ctxt, obj ):
        "Register a context name as being handled by an object."
        self._ctxt_dispatch[ctxt] = obj

    def store_flush( self, nowait=False ):
        if len( self.store_pending ):
            #print "Flushing pending stores."
            l = ['STORE']
            l += self.store_pending
            #print "Sending...",`l`
            t,r,s = self.send( tuple(l) )
            #print "...Done."
            self.store_pending = []
            if nowait:
                return
            if r is None:
                #print "Need to wait."
                t,r,s = self.wait(t)
            if r.lower()!='ok':
                raise s
        
    def store( self, path, attrs, async=False ):
        if 'entry' in attrs and len( attrs )==1 and attrs['entry'] is None:
            store_list = [infotrope.base.string(path), 'NOCREATE', infotrope.base.string('entry'), 'NIL']
        else:
            na = []
            for x in attrs:
                na.append( infotrope.base.string(x) )
                if attrs[x] is None:
                    na.append( 'NIL' )
                elif isinstance(attrs[x],list):
                    na.append( [infotrope.base.string("value"),[string(y) for y in attrs[x]]] )
                else:
                    na.append( string(attrs[x]) )
            store_list = [infotrope.base.string(path)] + na
        self.store_pending.append( store_list )
        if not async:
            self.store_flush()

class search:
    "Encapsulates an ACAP search, maintains the returned datastore, etc."
    def __init__( self, s=None, connection=None, base=None, enum=None, criteria=None, context=None, notify=None, ret=None, sort=None, notify_complete=None, depth=None, limit=None, chunked=False, index=None ):
        '''Create the search object. Uses:
        s = The search command, sans tag, in ACAP syntax. Sorry.
        connection = Connection to be used.
        context = The context name used, if any. This is optional.
        notify = An object instance used to notify that the context has changed.

        If there is a notify object given, but no context, (or a context which is not set
        to NOTIFY) then the notify object will still be called as search results come in.

        If there is a context but no notify, then no notifications will happen. But the
        results will still get updated.'''
        self._notify = None
        if notify is not None:
            self._notify = weakref.ref(notify)
        self._notify_complete = notify_complete
        self._written = False
        self._command_raw = s
        if isinstance(s,unicode):
            self._command_raw = s.encode('utf-8')
        self._command_parsed = None
        self._enumerate = enum
        self._base = base
        self._depth = depth
        self._criteria = criteria or 'ALL'
        self._sort = sort
        self._entries = {}
        self._connection = None
        self._ctxt = context
        self._complete = False
        self._state = None
        self._enum = index
        self._toomany = None
        self._retpart = ret
        self._state_payload = None
        self._enum_tag = None
        self._modtime = None
        if self._enumerate and self._sort is None:
            raise "Must sort with enumerate."
        self._limit = limit
        self._chunked = chunked
        if self._enum is None:
            if self._limit is None or self._limit!=0:
                self._enum = []
        if self._chunked and self._limit is None:
            self._limit = 25
        if connection is not None:
            self.set_connection( connection )

    def notify( self ):
        if self._notify is not None:
            return self._notify()
        return None
    def notify_complete( self ):
        if self._notify_complete is not None:
            return self._notify_complete
        return None

    def connection( self, conn=None ):
        if conn is not None:
            self.set_connection( conn )
        return self._connection

    def set_connection( self, conn ):
        if self._connection is not None:
            raise "Already have connection."
        self._connection = conn
        if self._retpart is None:
            #print "Parsing command locally.",`self._command_raw`
            s,i,tok = self._connection.nparser( self._command_raw, genex=False )
            #print " -->",`state`,`tok`,`remainder`
            self._command_parsed = tok
            ret = False
            self._retpart = []
            for foo in self._command_parsed:
                if isinstance(foo,str):
                    if foo.lower()=="return":
                        ret = True
                elif ret:
                    self._retpart = foo
                    break
        #print "Return part is",`self._retpart`
        self._return = []
        for ret in self._retpart:
            if isinstance(ret,list) or isinstance(ret,tuple):
                self._return = self._return[:-1]
                self._return.append( ret )
            else:
                if ret.find("*")!=-1:
                    self._return.append(ret)
                    self._return.append(["attribute","value"])
                else:
                    self._return.append(ret)
                    self._return.append(["value"])
        #print "Final return is",`self._return`
    
    def _check_written( self ):
        #print "Checking if I've been written."
        if not self._written:
            #print "Sending ACAP search."
            if self._command_raw is None:
                tmp = [ 'SEARCH' ]
                tmp.append( infotrope.base.string( self._base ) )
                if self._depth is not None:
                    tmp.append( 'DEPTH %d' % self._depth )
                if self._limit is not None:
                    tmp.append( 'LIMIT %d %d' % ( self._limit, self._limit ) )
                if self._ctxt is not None:
                    tmp.append( 'MAKECONTEXT' )
                    if self._enumerate:
                        tmp.append( 'ENUMERATE' )
                    tmp.append( 'NOTIFY' )
                    tmp.append( infotrope.base.string( self._ctxt ) )
                if self._sort is not None:
                    tmp.append( 'SORT' )
                    tmp.append( [ infotrope.base.string( x ) for x in self._sort ] )
                tmp.append( 'RETURN' )
                tmp.append( [ infotrope.base.string( x ) for x in self._retpart ] )
                tmp.append( self._criteria )
                self._command_raw = tuple(tmp)
            self._tag,r,s = self._connection.send( self._command_raw )
            self._connection.register( self._tag, self )
            if self._ctxt is not None:
                self._connection.register_context( self._ctxt, self )
            self._written = True

    def context( self ):
        return self._ctxt
    def sort( self ):
        return self._sort

    def send( self ):
        #print "Send requested."
        self._check_written()
    
    def _handle_entry( self, tag, resp, data ):
        '''This breaks apart a pre-parsed entry response, and stores the entry
        the semi-private _entries member, a dict associated by name, containing
        simple dicts representing the actual entry. This is, indeed, naff.'''
        entryname = data[0]
        payload = data[1:]
        try:
            self.add_entry( entryname, payload )
        except:
            print `self._return`
            print `payload`
            raise "All fucked up"
        if self._enum is not None:
            self._enum.append( entryname )
        if str(self._tag)==tag or str(self._enum_tag)==tag:
            if self.notify() is not None:
                self.notify().notify_addto( entryname, len(self._enum)-1 )
        return tag, resp, data

    def add_entry( self, entryname, payload, where=None ):
        retptr = 0
        cattr = {}
        entry = {}
        for thing in payload:
            #print "Considering ", `thing`
            if isinstance(thing,list):
                #print "A list. Hmmm."
                # Either it's a metadata collection, a value, or else it's a expansion collection.
                if self._return[retptr*2].find("*")==-1:
                    #print "Not expansion."
                    if len(self._return[retptr*2+1])==1:
                        # Value.
                        cattr[self._return[retptr*2+1][0]] = thing
                        entry[self._return[retptr*2]] = cattr
                        cattr = {}
                    else:
                        # Metadata collection
                        mptr = 0
                        for mdata in thing:
                            cattr[self._return[retptr*2+1][mptr]] = mdata
                            mptr = mptr+1
                        entry[self._return[retptr*2]]=cattr
                        cattr = {}
                else:
                    # Expansion collection.
                    for subthing in thing:
                        mptr = 0
                        for mdata in subthing:
                            cattr[self._return[retptr*2+1][mptr]] = mdata
                            mptr = mptr+1
                        entry[cattr["attribute"]] = cattr
                        cattr = {}
            else:
                #print "String value."
                cattr[self._return[retptr*2+1][0]] = thing
                entry[self._return[retptr*2]] = cattr
                cattr = {}
            retptr = retptr+1
        if where is None:
            self._entries[ entryname ] = entry
        else:
            where[ entryname ] = entry

    def _context_addto( self, tag, resp, data ):
        '''Handle an addto event.'''
        # * ADDTO "context" <entryname> x <entry-payload>
        if self._toomany is not None:
            self._toomany += 1
        self.add_entry( data[1], data[3:] )
        pos = int(data[2])-1
        if self._enum is not None:
            if int(data[2])==0:
                pos = len(self._enum)
                self._enum.append( data[1] )
            else:
                self._enum.insert( int(data[2])-1, data[1] )
        if self.notify() is not None:
            self.notify().notify_addto( data[1], pos )
        return tag, resp, data

    def _context_change( self, tag, resp, data ):
        '''Handles a change event.'''
        # * CHANGE "context" <entryname> x y <entry-payload>
        #print `data`
        if data[1] in self._entries:
            del self._entries[data[1]]
        self.add_entry(data[1],data[4:])
        opos = int(data[2])-1
        npos = int(data[3])-1
        if opos < 0:
            if self._enum is not None:
                opos = npos = self._enum.index( data[1] )
        if self._enum is not None and opos!=npos:
            self._enum.remove( data[1] )
            self._enum.insert( npos, data[1] )
        if self.notify() is not None:
            self.notify().notify_change( data[1], opos, npos )
        return tag, resp, data

    def _context_removefrom( self, tag, resp, data ):
        '''Handles a removefrom event.'''
        # * REMOVEFROM "context" <entryname> x
        if self._toomany is not None:
            self._toomany -= 1
        opos = int(data[2])-1
        if data[1] in self._entries:
            del self._entries[data[1]]
            if self._enum is not None:
                #if opos >= 0:
                #    del self._enum[opos]
                self._enum.remove( data[1] )
        if self.notify() is not None:
            self.notify().notify_removefrom( data[1], int(data[2])-1 )
        return tag, resp, data

    def get_entry( self, entry ):
        '''Returns a specific entry, or more accurately, the dict representing it.'''
        return self._entries[ entry ]

    def __getitem__( self, what ):
        ''' Returns an entry by index or name. '''
        if isinstance( what, int ):
            #print "Access to",`what`
            # If the search is not enumerated, then we'll advance through the list of values.
            if what >= len( self._enum ):
                #print "Too high."
                if self._toomany is not None:
                    #print "Have TOOMANY"
                    if what < self._toomany:
                        #print "Will expand."
                        self.expand( what )
            tmp = self._enum[what]
            return self._entries[tmp]
        else:
            return self._entries[what]

    def expand( self, what ):
        if self._enum_tag is not None:
            #print "Waiting..."
            self._connection.wait( self._enum_tag )
        cmd = ['SEARCH']
        cmd.append( infotrope.base.string( self._ctxt ) )
        cmd.append( 'SORT' )
        cmd.append( [ infotrope.base.string( x ) for x in self._sort ] )
        cmd.append( 'RETURN' )
        cmd.append( [ infotrope.base.string(x) for x in self._retpart ] )
        cmd.append( 'RANGE' )
        cmd.append( str(len(self._enum)+1) )
        what = ( what + 25 ) / 25 * 25
        cmd.append( str(what) )
        cmd.append( self._modtime )
        #print "Expanding with",`cmd`
        self._enum_tag,r,s = self._connection.send( tuple(cmd) )
        self._connection.register( self._enum_tag, self )
        self._connection.wait( self._enum_tag )
        self._enum_tag = None

    def set_index( self, what ):
        self._enum = what

    def __contains__( self, what ):
        if isinstance( what, int ):
            return what<len(self)
        else:
            return what in self._entries

    def __len__( self ):
        if self._toomany is not None:
            return int(self._toomany)
        return len(self._entries)

    def _handle_modtime( self, t, r, s ):
        if t=='*':
            self._modtime = s[1]
        elif self._modtime is None:
            self._modtime = s[0]
        return t,r,s

    def modtime( self ):
        return self._modtime

    def _handle_ok( self, t, r, s ):
        #print "Search complete with:",`s`
        if isinstance(s[0],list):
            if s[0][0].upper()=='TOOMANY':
                self._toomany = int(s[0][1])
        return self.handle_complete( t, r, s )

    def _handle_no( self, t, r, s ):
        #print "NO : ",`t`,`r`,`s`
        return self.handle_complete( t, r, s )

    def _handle_bad( self, t, r, s ):
        #print "BAD : ",`t`,`r`,`s`
        return self.handle_complete( t, r, s )

    def handle_complete( self, t,r,s ):
        self._completed = True
        self._state = r.lower()
        #print "Search ",`t`,", complete with ",`r`
        self._state_payload = s
        n = self.notify()
        if n is not None:
            n.notify_complete( self._state )
        n = self.notify_complete()
        if n is not None:
            n( self, self._state )
        self._notify_complete = None
        self._tag = None
        return t,r,s

    def complete( self ):
        return self._complete

    def state( self ):
        return self._state

    def state_payload( self ):
        return self._state_payload

    def wait( self ):
        '''Wait for this search to complete.'''
        self._check_written()
        if self._tag is not None:
            return self._connection.wait( self._tag )
        return '*',self._state,self._state_payload

    def entries( self ):
        return self._enum

    def updatecontext( self ):
        if self._ctxt is not None:
            if self._connection.connected():
                self._connection.send( 'UPDATECONTEXT', string(self._ctxt) )

    def freecontext(self, then):
        ''' Try to call this before you destroy the object. '''
        try:
            if self._written and self._state is not None and self._state.lower()=='ok':
                if self._ctxt is not None:
                    if self._connection.connected():
                        self._connection.register_context( self._ctxt, self ) # Too bizarre to even document.
                        t,r,s=self._connection.send( 'FREECONTEXT', string(self._ctxt) )
                        t.oncomplete(then)
        except AttributeError, e:
            print `e`,e
        except KeyError,e:
            print `e`,e
        except TypeError, e:
            print `e`,e
