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

import infotrope.base
import infotrope.encoding
import infotrope.parser
import StringIO
import time
import infotrope.cache
import os
import os.path
from infotrope.weak import weakref

cache_root = None
#suppress_extension = ['NAMESPACE']
suppress_extension = []

extension_aliases = {
    'ESEARCH':('X-DRAFT-I01-ESEARCH','X-DRAFT-I02-ESEARCH'),
    'LIST-EXTENDED':('X-DRAFT-W13-LISTEXT',),
    'QRESYNC':('X-DRAFT-W05-QRESYNC',),
}

# All extensions that need enabling.
client_capabilities = (
    'CONDSTORE',
    'QRESYNC',
)
    

def set_cache_root( s ):
    global cache_root
    cache_root = s

readonly = False
def do_readonly( s=True ):
    global readonly
    readonly = s

def astring( s ):
    if len(s) == 0:
        return '""'
    quoted = ' \r\n"\\'
    if len([x for x in s if ord(x)>127]) > 0:
        return infotrope.base.literal(s)
    printable = True
    crlf = False
    for x in s:
        if not x.isalnum():
            printable = False
            if x == '\r' or x == '\n':
                crlf = True
    if printable:
        return s
    if crlf:
        return infotrope.base.literal( s )
    return infotrope.base.string( s )

class binarylit(infotrope.base.literal):
    def __init__( self, s ):
        infotrope.base.literal.__init__( self, s, True )

def bstring( s ):
    null = False
    for x in s:
        if ord(x)==0:
            return binarylit( s )
    return infotrope.base.literal( s )

class append_engine:
    def __init__(self, tag, msgs, mi, oncomplete):
        self.tag = tag
        self.msgs = msgs
        self.oncomplete = oncomplete
        self.mi = mi
        self.pending = {}
        self.complete = False
        self.okay = False

    def do_some_appends(self):
        if self.mi._sep is None: # Then we cannot construct URIs yet.
            self.mi.parent().do_list_async(then=self.do_some_appends)
            return
        command = ['APPEND', astring( self.mi.full_path )]
        trprops = self.mi.get_trprops()
        current = []
        while self.msgs:
            x = z = self.msgs.pop()
            flags = None
            internaldate = None
            if isinstance( x, unicode ):
                x = x.encode('us-ascii')
            if not isinstance( x, str ):
                flags = x.flags()
                internaldate = x.internaldate()
            if not self.mi.server().have_capability('CATENATE') and isinstance( z, infotrope.message.Message ):
                uris = [u for u in z.uri if u.scheme in ['imap','imaps'] and ( u.section == '' or u.section is None ) and self.mi.catenate_uri_ratifier( u ) is not None ] # Yay! Lists local message URIs.
                if uris:
                    done = False
                    for x in uris:
                        if self.mi.server().get_cwm() == x.mailbox:
                            self.mi.server().mailbox( x.mailbox ).copy( x.uid, self.mi.full_path )
                            done = True
                            break
                    if not done:
                        self.mi.server().mailbox( uris[0].mailbox ).copy( uris[0].uid, self.mi.full_path )
                        done = True
                    if done:
                        continue
            elif isinstance( z, infotrope.message.MessagePart ) and [self.mi.catenate_uri_ratifier( y ) for y in z.uri] and x.part.part_id=='': # Local message.
                x = z.msg # We understand these better.
            if isinstance( x, infotrope.imap.message ):
                turi = self.mi.catenate_uri_ratifier( x.uri() )
                if turi is not None:
                    if self.mi.server().have_capability( 'CATENATE' ) and len(msgs)>1 and self.mi.server().have_capability('MULTIAPPEND'):
                        trlist = [( infotrope.message.TrType.URI, self.mi.catenate_uri_ratifier( x.uri() ) )]
                    else:
                        srcm = x.mailbox()
                        srcm.copy( x, self.mi.full_path )
                        continue
                else:
                    if isinstance( z, infotrope.message.MessagePart ):
                        trlist = z.transmission_list( trprops )
                    else:
                        y = infotrope.message.MessageCopy( x )
                        trlist = y.transmission_list( trprops )
            elif isinstance( x, infotrope.message.BasePart ):
                trlist = x.transmission_list( trprops )
            elif isinstance( x, str ):
                if '\r\n' not in x:
                    x = x.replace('\n','\r\n')
                trlist = [( infotrope.message.TrType.TEXT, x )]
            current.append( z )
            if flags:
                flags = [x for x in flags if x.lower()!='\\recent']
            if flags:
                command.append( flags )
            if internaldate:
                command.append( astring(internaldate) )
            if len(trlist)>1:
                trl = []
                for tt,td in trlist:
                    if tt is infotrope.message.TrType.URI:
                        trl.append( 'URL' )
                        trl.append( astring(td) )
                    elif tt is infotrope.message.TrType.BINARY:
                        trl.append( 'TEXT' )
                        trl.append( binarylit( td ) )
                    else:
                        trl.append( 'TEXT' )
                        trl.append( infotrope.base.literal( td ) )
                command.append( 'CATENATE' )
                command.append( trl )
            elif trlist[0][0] is infotrope.message.TrType.URI:
                command += [ 'CATENATE', [ 'URL', trlist[0][1] ] ]
            elif trlist[0][0] is infotrope.message.TrType.BINARY:
                command.append( binarylit( trlist[0][1] ) )
            else:
                command.append( infotrope.base.literal( trlist[0][1] ) )
            if not self.mi.server().have_capability( 'MULTIAPPEND' ) and len(command)>2:
                self.send_command_append( current, command )
                command = ['APPEND',astring(self.mi.full_path)]
                current = []
        if len(command) > 2:
            self.send_command_append(current, command)
            current = []

    def send_command_append(self, current, command):
        t,r,s = self.mi.server().send(command, state='auth')
        self.pending[t.tag] = current
        t.oncomplete(self.append_complete)

    def append_complete(self,cmd,t,r,s):
        current = self.pending[t]
        del self.pending[t]
        #print "\n",`r`,`s`
        if r.lower()!='ok':
            if isinstance(s[0],list):
                if s[0][0].upper() == 'UNKNOWN-CTE':
                    self.msgs.append(current)
                    self.mi.binary_upload = False
                    self.do_some_appends()
                elif s[0][0].upper() == 'TRY-CREATE':
                    self.msgs.append(current)
                    self.mi.server().create(self.mi.full_path, oncomplete=self.do_some_appends)
                else:
                    #print "(Here)"
                    self.complete = True
                    self.okay = False
                    self.oncomplete(self, False, s)
            else:
                #print "(Here)"
                self.complete = True
                self.okay = False
                self.oncomplete(self, False, s)
            return
        if isinstance(s[0],list):
            if s[0][0].upper() == 'APPENDUID':
                uris = [ infotrope.url.URL( self.mi.uri().asString() + ';uidvalidity=' + s[0][1] + '/;uid=' + str(x) ) for x in self.mi.server().decompose_set( s[0][2] ) ]
                if len(uris) == len(current):
                    uris.reverse()
                    for x in current:
                        u = uris.pop()
                        if isinstance(x,infotrope.message.BasePart):
                            x.saved_as(u)
                else:
                    self.mi.server().alert('Length mismatch in APPENDUID')
        if self.msgs:
            self.do_some_appends()
        elif not self.pending:
            self.complete = True
            self.oncomplete(self, True, s)

class mbox_info:
    def __init__( self, server, display, full_path, flags=None, sep=None, ext=None, touch_time=None ):
        self._server = weakref.ref(server)
        self.parent_mi = None
        self.full_path = full_path
        self.displaypath = display
        self._flags = flags
        self._sep = sep
        self._have_children = None
        self._children = {}
        self._last_list = 0
        self._in_list = False
        self._myrights = None
        self._status_searches = {}
        self._status_results = {}
        self._status_callback = None
        self._extended = {}
        self.append_engines = {}
        self.binary_upload = True
        self.touch_time = touch_time
        if touch_time is None:
            self.touch_time = time.time()
        self._watchers = []
        self._after_list = []
        self._key = full_path
        if self._key is None:
            self._key = '%%'
        self._enable_cache = False
        ext = ext or []
        import string
        map( self._extended.setdefault, map( string.upper, [x[0] for x in ext] ), [x[1] for x in ext ] )
        self.update()

    def enable_cache(self):
        ''' Do this after first real LIST '''
        self._enable_cache = True
        
    def add_notify( self, obj ):
        self._watchers.append( weakref.ref( obj ) )
        for k,v in self._children.items():
            obj.mi_notify_add( k, v )

    def uri( self ):
        if self._sep is None:
            self.parent().do_list()
        if self._sep is None or self._sep != '/':
            return infotrope.url.URL( self.server().uri.asString() + self.full_path.decode('mod-utf-7').encode('urlencode') )
        else:
            return infotrope.url.URL( self.server().uri.asString() + '/'.join([x.decode('mod-utf-7').encode('urlencode') for x in self.full_path.split('/')]) )

    def get_trprops( self ):
        import infotrope.message
        avail = ['base64','7bit','quoted-printable','8bit']
        if self.server().have_capability( 'BINARY' ) and self.binary_upload:
            avail.append( 'binary' )
        if self.server().have_capability( 'CATENATE' ):
            return infotrope.message.TrProps( encodings=avail, maxline=998, schemes=[self.server().uri.scheme], trusted=[self.server().uri], uriratifier=self.catenate_uri_ratifier, chunked=True )
        return infotrope.message.TrProps( encodings=avail, maxline=998 )
    
    def postaddress( self ):
        if 'POSTADDRESS' in self._extended:
            return self._extended['POSTADDRESS']
        return None

    def catenate_uri_ratifier( self, uri ):
        if str(self.uri().root_user())!=str(uri.root_user().asString()):
            return None
        return uri.path
        cwm = self.server().get_cwm()
        if cwm is None:
            return uri.path
        if cwm == uri.mailbox:
            t = ';UID=%d' % uri.uid
            if uri.section and uri.type == 'SECTION':
                t += '/;SECTION=' + uri.section
            return t
        if '/' not in uri.path[1:]:
            return uri.path
        p = uri.path[1:].split('/')
        cp = self.server().mailbox(cwm).uri().path[1:].split('/')
        begin = []
        end = []
        p.reverse()
        cp.reverse()
        first = True
        while p and cp:
            pp, params = p.pop().split(';')
            pcp = cp.pop().split(';')[0]
            if pp != pcp:
                if first:
                    return uri.path
                begin.append('..')
                end.append(pp + ';' + params)
            first = False
        while cp:
            cp.pop()
            begin.append('..')
        while p:
            end.append(p.pop())
        return '/'.join(begin+end)
            

    def append(self, msgs, oncomplete=None):
        if not (isinstance(msgs,list) or isinstance(msgs,tuple)):
            msgs = [msgs]
        ae = append_engine(self.server().new_tag(), msgs, self, oncomplete=self.append_engine_complete)
        self.append_engines[ae.tag] = (ae,oncomplete)
        ae.do_some_appends()
        if oncomplete is None:
            while not ae.complete:
                self.server().fetch()
            return ae.okay
        return ae.tag

    def append_engine_complete(self, ae, success, txt):
        if self.append_engines[ae.tag][1]:
            #print "Calling with success =",`success`
            self.append_engines[ae.tag][1](ae.tag, success, txt)
        del self.append_engines[ae.tag]
        
    def server( self ):
        return self._server()

    def __repr__( self ):
        s = '<' + self.__class__.__name__ + ' for ' + `self.full_path` + ', AKA ' + `self.displaypath`  + '>'
        return s

    def open( self ):
        return self.server().mailbox( self.full_path )

    def create( self, owhat ):
        what = owhat.encode('modutf7')
        np = self.full_path + self._sep + what
        self.server().create( np, then=self.post_create )

    def post_create( self, cmd, t,r,s ):
        self._last_list = 0
        self.expand_children()
        if r.lower()!='ok':
            self.server().alert( s )

    def delete( self ):
        self.server().delete( self.full_path, then=self.post_delete )

    def post_delete( self, cmd, t, r, s ):
        self._last_list = 0
        self.parent()._last_list = 0
        self.expand_children()
        if r.lower()!='ok':
            self.server().alert( s )

    def update( self ):
        self._have_children = True
        if self._flags is not None:
            if self.server().have_capability( 'CHILDREN' ) or self.server().have_capability('LIST-EXTENDED') or self.server().have_capability('LISTEXT'):
                if '\\hasnochildren' in self._flags:
                    self._have_children = False
            if '\\noinferiors' in self._flags:
                self._have_children = False
            if '\\placeholder' in self._flags:
                self._have_children = True
            if '\\nonexistent' in self._flags and '\\noselect' not in self._flags:
                self._flags.append( '\\noselect' )
            if self._have_children and self.full_path and '$namespace' not in self._flags:
                for nsn,nss in self.server().namespace().items():
                    for ns in nss:
                        pfx = ns[0]
                        sep = ns[1]
                        if ( self.full_path + sep ) == pfx:
                            self._have_children = False # Covered by the prefix.
        if self._sep is not None:
            if self.displaypath is None:
                self.displaypath = self.server().displaypath( self.full_path, self._sep )[0]
        if self.displaypath is not None and len(self.displaypath)!=0:
            mi = self.server().mbox_info()
            dp = self.displaypath[:]
            dp.reverse()
            current = None
            while len(dp):
                current = dp.pop()
                if current in mi._children:
                    mi = mi._children[current]
                    if len(dp)==0:
                        if mi is self:
                            return
                        if mi.full_path == self.full_path:
                            if self._sep is not None and self._flags is not None:
                                mi.refresh( flags = self._flags, sep = self._sep )
                        return
                else:
                    break
            if len(dp)==0:
                mi.add_child( self )
                
    def set_sep(self, sep):
        self._sep = sep
        self.update()

    def refresh( self, flags=None, sep=None, ext=None ):
        self.touch_time = time.time()
        self._flags = flags
        self._sep = sep
        ext = ext or []
        import string
        map( self._extended.setdefault, map( string.upper, [x[0] for x in ext] ), [x[1] for x in ext ] )
        self.update()

    def status( self, what, how ):
        if not self.selectable():
            return
        if self.full_path == self.server().get_cwm():
            if self.server().have_capability( 'ESEARCH' ):
                if self._status_callback is not None:
                    return
                self._status_searches = {}
                self._status_results = {}
                self._status_callback = how
                for item in what:
                    if item == 'MESSAGES':
                        self._status_searches[item] = None
                        self._status_results[item] = len(self.open())
                    elif item in ('UNSEEN','RECENT','DELETED'):
                        t,r,s = self.server().send( ['SEARCH', 'RETURN', ['COUNT'], item ], pipeline=True, mbox=self.full_path )
                        self._status_searches[ item ] = t
                        self.server().register( t, self )
                self.check_status()
            return
        return self.server().status( self.full_path, what, how )

    def _handle_esearch( self, t, r, s ):
        for x,y in self._status_searches.items():
            if y is not None:
                if y==t:
                    self._status_results[x] = s['COUNT']
        self.check_status()
        return t,r,s

    def check_status( self ):
        if self._status_searches:
            if len( self._status_searches ) == len( self._status_results ):
                self._status_callback( self.full_path, self._status_results )
                self._status_searches = {}
                self._status_results = {}
                self._status_callback = None

    def selectable( self ):
        self.get_flags()
        return not ('\\noselect' in self._flags or '$namespace' in self._flags)

    def have_children( self ):
        if self._have_children is None:
            self.get_flags()
        return self._have_children

    def add_child( self, ch ):
        dp = ch.displaypath[-1:]
        if len(dp)==0:
            return
        new = True
        if dp[0] in self._children:
            new = False
        self.server().log("Already have " + dp[0] + "? " + `new`)
        self._children[dp[0]] = ch
        ch.parent_mi = weakref.ref( self )
        self._have_children = True
        if not self._in_list: # Otherwise save them all at the end.
            self.save_children()
        for x in self._watchers:
            y = x()
            if y is not None:
                if new:
                    y.mi_notify_add( dp[0], ch )
                else:
                    y.mi_notify_change( dp[0], ch )
    
    def children( self ):
        self.get_children()
        return self._children

    def get_flags( self ):
        if self._flags is None:
            self.parent().do_list()
        return self._flags

    def get_children( self ):
        if self.have_children() and not self._children:
            self.list()

    def list( self ):
        tt = time.time()
        if tt - self._last_list > 300:
            self.do_list()

    def expand_children( self ):
        self.parent().do_list_async( then=self.do_list_async )

    def do_list_async( self, *args, **kw ):
        if 'then' in kw:
            self._after_list.append( kw['then'] )
        if self._in_list:
            return self.post_list()
        self._in_list = True
        self.load_children()
        if ( time.time() - self._last_list ) < 300:
            return self.post_list()
        self._last_list = time.time()
        self.server().list( "", self.full_path + self._sep + '%', then=self.post_list )
        
    def post_list( self, *args ):
        self.post_list_deletes()
        self._in_list = False
        for x in self._after_list:
            x()
        self._after_list = []
        self.enable_cache()
        self.save_children()
        if True or args: # Somethign really happened.
            for x in self._watchers:
                y = x()
                if y is not None:
                    y.mi_notify_complete( *args )

    def post_list_deletes( self ):
        for k,v in self._children.items():
            if v.touch_time < self._last_list:
                del self._children[k]
                for x in self._watchers:
                    y = x()
                    if y is not None:
                        y.mi_notify_del( k )

    def save_children(self):
        if not self._enable_cache:
            return
        kids = [k.full_path for k in self._children.values() if k._flags is not None and '$namespace' not in k._flags]
        #print "Save the children!",`self._key`,`kids`
        self.server().mailbox_info_cache[self._key,'CHILDREN'] = kids
        self.server().mailbox_info_cache.sync()

    def load_children(self):
        kids = self.server().mailbox_info_cache.get((self._key,'CHILDREN'),[])
        for k in kids:
            self.server().mbox_info(k)
        
    def do_list( self ):
        if not self._in_list:
            self._in_list = True
            self.load_children()
            self._last_list = time.time()
            self.parent().list()
            self.server().list( "", self.full_path + self._sep + '%' )
            self.post_list_deletes()
            self.enable_cache()
            self.save_children()
            self._in_list = False

    def have_rights( self, rts ):
        self.get_rights()
        for x in rts:
            if x not in self._myrights:
                return False
        return True

    def get_rights( self ):
        self.get_flags()
        if self._myrights is None:
            self.server().log( "Finding mailbox rights." )
            use_acl = self.server().have_capability('ACL')
            if use_acl:
                self.server().log( "Have ACL (2086 or 2086upd) support" )
            if use_acl and self._flags is not None:
                if '$namespace' in self._flags or '\\noselect' in self._flags:
                    self.server().log( "Not selectable, won't use MYRIGHTS." )
                    use_acl = False
            if use_acl:
                self.server().log( "Using MYRIGHTS" )
                t,r,s = self.server().send( 'MYRIGHTS', astring(self.full_path), state='auth' )
                if r is None:
                    t,r,s = self.server().wait(t)
        if self._myrights is not None:
            return self._myrights
        self.server().log( "Using fallback rights" )
        self._myrights = 'lx'
        if '\\noinferiors' not in self._flags:
            self._myrights += 'k'
        if not ('\\noselect' in self._flags or '$namespace' in self._flags):
            self._myrights += 'rswtie'
        if self.full_path is None:
            self._myrights = 'l'
        return self._myrights

    def set_rights( self, rights ):
        self._myrights = rights

    def parent( self ):
        if self.parent_mi is not None:
            mmi = self.parent_mi()
            if mmi is not None:
                return mmi
        if self._sep is None:
            self.parent_mi = weakref.ref( self.server().mbox_info( '' ) )
        else:
            ppath = self._sep.join( self.full_path.split( self._sep )[:-1] )
            self.parent_mi = weakref.ref( self.server().mbox_info( ppath ) )
        return self.parent()

class mbox_info_tl( mbox_info ):
    def __init__( self, server, display=[], full_path=None, flags=None, touch_time=None ):
        mbox_info.__init__( self, server, display=display, full_path=full_path, flags=flags, sep='', touch_time=touch_time )
        self._have_children = True

    def get_flags( self ):
        if self._flags is None:
            self.server().log( "Performing LIST to get TL flags" )
            if self._key!='%%':
                self.do_list()
        if self._flags is None:
            self._flags = []
            if len(self.displaypath)==0 and self.server().have_capability('NAMESPACE'):
                self._flags.append('\\noinferiors')
            elif self.full_path is None:
                self._flags.append('\\noinferiors')
        self._flags.append('$namespace')
        return self._flags

    def expand_children( self ):
        if len(self._children)==0 and len(self.displaypath)==0:
            self.server().namespace( then=self.post_namespace )
        else:
            self.do_list_async()

    def post_list_deletes( self ):
        pass

    def post_namespace(self, *args, **kw):
        self._in_list = False
        self.do_list_async()
    
    def do_list_async( self, *args, **kw ):
        if 'then' in kw:
            self._after_list.append( kw['then'] )
        if self._in_list:
            self.post_list()
            return
        if ( time.time() - self._last_list ) < 300:
            self.post_list()
            return
        self._in_list = True
        self.load_children()
        self._last_list = time.time()        
        if self.server().have_capability('NAMESPACE') and len(self.displaypath)==0:
            self.server().log( "List INBOX async in list_async: " + `self` )
            self.server().list( '', 'INBOX', then=self.post_list )
        elif self.full_path is not None:
            self.server().log( "List full async in list_async: " + `self` )
            self.server().list( '', self.full_path + '%', then=self.post_list )

    def do_list( self ):
        self.server().log( "List called for TL? " + `self` )
        self._last_list = time.time()
        if not self._in_list:
            self._in_list = True
            if len(self._children)==0 and self._key=='%%':
                self.server().namespace()
            self.load_children()
            if self._key=='%%':
                if self.server().have_capability('NAMESPACE'):
                    self.server().list( '', 'INBOX' )
                    self._in_list = False
                    return
                elif self.full_path is not None:
                    self.server().list( '', self.full_path + '%' )
            elif self.full_path is not None:
                self.server().list( '', self.full_path + '%' )
            self._in_list = False
        else:
            while self._in_list:
                self.server().fetch()
        self.enable_cache()
        self.save_children()
        self.server().log( "Sync list done." )

    def add_namespace( self, displaypath, pfx=None ):
        self.server().log( "Adding namespace %s [%s] to %s" % ( `displaypath`, pfx, `self.displaypath` ) )
        if len(displaypath)-len(self.displaypath)==1:
            if displaypath[-1] not in self._children:
                self.server().log( "Adding to self." )
                ch = mbox_info_tl( self.server(), display=displaypath, full_path=pfx, flags=['$namespace'] )
                ch.parent_mi = weakref.ref( self )
            else:
                self.server().log( "Got it already." )
        else:
            if displaypath[0] not in self._children:
                self.server().log( "Adding parent namespace type." )
                self.add_namespace( [displaypath[0]] )
            self.server().log( "Adding child namespace" )
            self._children[displaypath[0]].add_namespace( displaypath, pfx )

class authenticate(infotrope.base.command):
    def __init__( self, server ):
        self.server = weakref.ref( server )
        cmd = None
        feedme = False
        self.sasl = server.sasl
        if server.have_capability( 'AUTH' ):
            server.log( "Checking authentication mechanisms" )
            self.mech = self.sasl.mechlist( server.get_capability('AUTH') )
            if self.mech is not None:
                cmd = ['AUTHENTICATE', self.mech.name()]
                if server.have_capability( 'SASL-IR' ):
                    x = self.mech.process( None )
                    self.server().log( "Sending IR: %s" % `x` )
                    if x is not None:
                        cmd.append( self.xmit_encode( x ) )
                feedme = True
        if cmd is None:
            server.log( "Trying to fallback to LOGIN" )
            if server.have_capability( 'LOGINDISABLED' ):
                raise infotrope.base.connection.exception( 'IMAP server offers no authentication methods we can use.' )
            self.mech = self.sasl.mechlist( None, force_plain=True )
            self.mech.process( None )
            cmd = ['LOGIN', self.mech.vals['username'], self.mech.vals['password']]
        infotrope.base.command.__init__( self, server.env, 'AUTH', cmd )
        server.reset_capability()
        self.oncomplete( self.notify )
        self.feeding = feedme
        self.resend = False

    def notify( self, cmd, t, r, s ):
        self.server().log( "Auth complete, checking status" )
        if r.upper()=='NO':
            self.sasl.failure( self.mech )
            self.server().restore_capability()
            self.server().send( authenticate( self.server() ) )
            return
        elif r.upper()!='OK':
            raise s
        self.server().log( "Server says OK" )
        if self.mech.okay():
            self.server().log( "Mechanism says OK" )
            self.server().auth_complete(self.mech)
            self.sasl.success( self.mech )
            self.server().log( "Complete and ready." )
        else:
            self.server().log( "Mechanism says bad. Hmmm." )

    def feed( self, s ):
        try:
            s = self.server().trim_to_line( s )
            gunk = self.xmit_decode( s )
            self.server().log( "Got SASL gunk: " + `gunk` )
            sendgunk = self.mech.process( gunk )
            self.server().log( "Sending SASL gunk: " + `sendgunk` )
            if sendgunk is None:
                self.feeding = False
            self.server().log( " >> %s" % ( self.xmit_encode( sendgunk ) ) )
            self.server().s.write( self.xmit_encode( sendgunk ) )
            self.server().s.write( "\r\n" )
            self.server().s.flush()
        except infotrope.sasl.error:
            self.server().s.write('*\r\n')
            self.server().s.flush()
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
            if uri.scheme == 'imap':
                uri.port = 143
            else:
                uri.port = 993
        if uri.scheme == 'imaps':
            if not infotrope.core.platform_tls():
                if uri.port == 993:
                    uri.scheme = 'imap'
                    uri.port = 143
                else:
                    raise infotrope.base.connection.exception( "No (reliable) SSL support, cannot connect." )
        self.seltime = None
        self.select_command = None
        self._enabled = False
        self._capability = {}
        self._old_capability = {}
        self._cwm = None
        self._cwm_mbx = None
        self._cwm_mbx_save = None
        self.mailbox_info = {}
        self.mailboxes = weakref.WeakValueDictionary()
        self.status_callback = {}
        #self.have_literal8 = True
        self.banner = None
        self._identity = None
        self._mbox_info = {}
        self._listext_works = True
        self.cache_root = None
        self._searches = []
        self._threads = []
        self._sorts = []
        self._namespace = None
        self._doing_lsub = False
        self.last_probe = None
        self.mailbox_info_cache = infotrope.cache.dummy_double()
        self.server_info_cache = infotrope.cache.dummy()
        global cache_root
        if cache_root is not None:
            u = uri.username
            if u is None:
                u = 'anonymous'
            self.cache_root = os.path.join( cache_root, u, uri.server, str(uri.port) )
            if not os.path.exists( os.path.join(self.cache_root, 'server') ):
                os.makedirs( os.path.join(self.cache_root, 'server') )
            self.mailbox_info_cache = infotrope.cache.open_double( os.path.join( self.cache_root, 'server', 'mboxinfo' ), str )
            self.server_info_cache = infotrope.cache.open( os.path.join( self.cache_root, 'server', 'serverinfo' ) )
        self.idling = False
        self._latency_data = []
        self._operation = env.make_operation( str(uri), "Connecting", 6 )
        infotrope.base.connection.__init__( self, uri, env, True, using_alt_port=(uri.scheme=='imaps') )

    def you_are_ready( self ):
        self.set_state('auth', 'YAR 829')
        self.full_restore_state()
        if self._operation:
            self._operation.stop()
            self._operation = None
        
    def alert( self, txt ):
        self.env.alert( self.uri, txt )

    def read_banner_old( self ):
        tag, resp, data = self.fetch()
        if tag == '*':
            if resp.upper() == 'OK':
                pass
            elif resp.upper() == 'BYE':
                if self.s is not None:
                    self.s.close()
                self.s = None
                self.set_state('dead', 'Banner read 847')
            else:
                if self.s is not None:
                    self.s.close()
                self.s = None
                self.set_state('dead', 'Banner read 852')
        else:
            if self.s is not None:
                self.s.close()
            self.s = None
            self.set_state('dead', 'Banner read 857')

    def valid_states(self):
        states = ['any']
        if self.state == 'mbox' and self._cwm:
            states.append('selected:%s' % self._cwm)
        if self.state == 'mbox' or self.state == 'select' or self.state == 'auth':
            states.append('auth')
        states.append('any')
        return states

    def change_state(self, newstate):
        if self.state == 'auth':
            if newstate.startswith('selected:'):
                newpath = newstate[len('selected:'):]
                mbx = self.mailbox(newpath,open=False)
                self.set_cwm(newpath, mbx, True)
                return True
        elif self.state == 'dead':
            self.idling = False
            self.set_state('init', 'Change State 876')
            self.do_connect()
            return True
        return False

    def send( self, *cmd, **kw ):
        tag,cmd = self.tuples_to_commands( cmd )
        if 'mbox' in kw:
            kw['state'] = 'selected:%s' % kw['mbox']
        tag,r,s = infotrope.base.connection.send( self, tag, **kw )
        if tag.command[0].upper() in ['SEARCH','UID SEARCH']:
            if not ( self.have_capability( 'ESEARCH' ) and tag.command[1].upper()=='RETURN' ):
                self._searches.insert( 0, tag.tag )
        elif tag.command[0].upper() in ['SORT','UID SORT']:
            self._sorts.insert( 0, t.tag )
        elif tag.command[0].upper() in ['THREAD','UID THREAD']:
            self._threads.insert( 0, tag.tag )
        return tag,r,s

    def __repr__( self ):
        return "<infotrope.imap.connection to %s:%s in state %s>" % ( self.hostname, self.port, self.state )
    
    def capability( self ):
        if not self._capability:
            self._capability = self.server_info_cache.get('CAPABILITY',{})
        if len(self._capability)==0:
            self.wait_ready()
        if not self._capability:
            tag,x1,x2 = self.send( "CAPABILITY", state='any' )
            t,r,data = self.wait( tag )
        return self._capability

    def urlfetch( self, us ):
        """
        Given an IMAP URL, provide the data.
        Given a list, provide a dictionary to the data.
        """
        urls = {}
        if not isinstance( us, list ) and not isinstance( us, tuple ):
            us = [us]
        for u in us:
            orig_u = u
            if isinstance( u, unicode ):
                u = u.encode('utf-8')
            if isinstance( u, str ):
                if not u.startswith( 'imap:' ):
                    if u[0] != '/':
                        raise "Not relative to base"
                    u = str(self.uri) + u[1:]
            urls[ str(infotrope.url.URL( u )) ] = orig_u
        if self.have_capability( 'URLAUTH' ):
            self._urlxlate = {}
            c = ['URLFETCH'] + urls.keys()
            t,r,s = self.send( c, state='auth' )
            if r is None:
                self.wait( t )
        else:
            self._urlxlate = {}
            for x in urls.keys():
                u = infotrope.url.URL( x )
                try:
                    mbx = self.mailbox( u.mailbox )
                    if u.uidvalidity and mbx.uidvalidity()!=u.uidvalidity:
                        self._urlxlate[ x ] = None
                        continue
                    msg = mbx[u.uid]
                    self._urlxlate[ x ] = msg.body_raw( u.section or '' )
                except:
                    self._urlxlate[ x ] = None
        res = {}
        for k,v in urls.items():
            if k in self._urlxlate:
                res[ v ] = self._urlxlate[ k ]
            else:
                res[ v ] = None
        self._urlxlate = {}
        if len(res)==1:
            return res.values()[0]
        return res

    def _parse_urlfetch( self, t, r, s ):
        s = self.generic_parse( s )
        self._urlxlate[ s[0] ] = s[1]
        return t,r,s

    def reset_capability( self ):
        self._old_capability = self._capability
        self._capability = {}

    def restore_capability(self):
        self._capability = self._old_capability

    def have_capability( self, what ):
        self.capability()
        #if what == 'CONDSTORE':
        #    print "\n\nCONDSTORE wanted, caps is",`self._capability`,"\n\n"
        if what in self._capability:
            return True
        if what in extension_aliases:
            for alias in extension_aliases[what]:
                if alias in self._capability:
                    return True
        return False

    def get_capability( self, what ):
        self.capability()
        if what in self._capability:
            return self._capability[what]
        return None

    def identity( self ):
        if self._identity is None:
            if self.have_capability( 'ID' ):
                t,r,x = self.send( 'ID ("vendor" "Dave Cridland" "name" "Infotrope Polymer" "version" "PRERELEASE")', state='any' )
                if r is None:
                    t,r,x = self.wait( t )
        return self._identity

    def have_starttls( self ):
        return self.have_capability( 'STARTTLS' )

    def starttls( self ):
        t,r,s = '*','NO','Not Supported'
        if not infotrope.core.platform_tls():
            return t,r,s
        if self.have_starttls():
            t,r,s = self.send( 'STARTTLS', state='preauth-cap' )
            if r is None:
                t,r,s = self.wait( t )
            if r.lower()=='ok':
                self.reset_capability()
                self.switch_tls()
                self.capability()
        return t,r,s

    def list( self, pfx, mbx, subscribed=False, then=None ):
        if isinstance(mbx,list) or isinstance(mbx,tuple):
            nmbx = [astring(x) for x in mbx]
        else:
            nmbx = [astring(mbx)]
        if self.have_capability('LIST-EXTENDED'):
            retopts = ['CHILDREN']
            if self.have_capability('POSTADDRESS'):
                retopts.append( 'POSTADDRESS' )
            selopts = ['REMOTE']
            if subscribed:
                selopts.append('SUBSCRIBED')
            else:
                retopts.append('SUBSCRIBED')
            if self.have_capability( 'ACL2' ):
                selopts.append('MYRIGHTS')
            smbx = nmbx
            if len(nmbx)==1:
                smbx = nmbx[0]
            t,r,s = self.send( 'LIST', selopts, astring( pfx ), smbx, 'RETURN', retopts, state='auth' )
            if r is None:
                if then is not None:
                    t.oncomplete( then )
                    return
                t,r,s = self.wait( t )
            return t,r,s
        if self.have_capability('LISTEXT'):
            if not subscribed or self.have_capability('LIST-SUBSCRIBED'):
                opts = ['REMOTE','CHILDREN']
                if subscribed:
                    opts.append('SUBSCRIBED')
                tags = []
                for x in nmbx:
                    t,r,s = self.send('LIST', opts, astring(pfx), x, state='auth')
                    if r is None:
                        tags.append(t)
                if len(tags)==1 and then is not None:
                    tags[0].oncomplete( then )
                    return
                t,r,s = self.wait(tags)
                return t,r,s
        try:
            tags = []
            for x in nmbx:
                t,r,s = None,None,None
                cmdbase = 'LIST'
                if subscribed:
                    cmdbase = 'LSUB'
                    self._doing_lsub = True
                else:
                    self._doing_lsub = False
                if self.have_capability('MAILBOX-REFERRALS'):
                    t,r,s = self.send('R' + cmdbase, astring(pfx), x, state='auth' )
                else:
                    t,r,s = self.send(cmdbase, astring(pfx), x, state='auth' )
                if r is None:
                    tags.append(t)
            if len(tags)==1 and not subscribed and then is not None:
                tags[0].oncomplete( then )
                return
            return self.wait( tags )
        finally:
            self._doing_lsub = False
        
    def guess_namespace( self, full_path ):
        best_ns = None
        best_ns_type = None
        best_ns_pfx_l = 0
        best_sep = None
        if full_path is not None and full_path.upper() == 'INBOX':
            return None,None,None
        ns = self.namespace()
        for nsn,nsp in ns.items():
            if nsp is None:
                continue
            for pfx,nsep in nsp:
                qpfx = pfx
                if qpfx[-1:] == nsep:
                    qpfx = pfx[:-1]
                if full_path[0:len(pfx)] == pfx or full_path==qpfx:
                    if best_ns_pfx_l <= len(pfx):
                        best_ns = pfx
                        best_ns_type = nsn
                        best_ns_pfx_l = len(pfx)
                        best_sep = nsep
        return best_ns_type,best_ns,best_sep
        
    def displaypath( self, full_path, sep=None ):
        ns = self.namespace()
        best_ns_type,best_ns,best_sep = self.guess_namespace( full_path )
        if best_sep is not None:
            sep = best_sep
        displaypath = []
        if full_path.upper() == 'INBOX':
            return [u'Inbox'],sep
        displaypath = []
        if full_path.upper().find( 'INBOX' + sep )==0:
            if best_ns == '':
                return [u'Inbox'] + [ x.decode('modutf7') for x in full_path[6:].split( sep ) ], sep
        if best_ns_type is not None:
            displaypath.append( best_ns_type )
            if len(ns[best_ns_type]) != 1:
                displaypath.append( best_ns.decode( 'modutf7' ) )
            full_path = full_path[len(best_ns):]
            if full_path == '':
                return displaypath,sep
        if sep is None:
            sep = self.mailbox_info_cache.get((full_path,'SEP'),None)
        if sep is None:
            self.list( '', full_path )
            if full_path not in self._mbox_info:
                return None,None
            return self._mbox_info[ full_path ].displaypath, self._mbox_info[full_path].sep
        displaypath += [ x.decode('modutf7') for x in full_path.split( sep ) ]
        return displaypath,sep
    
    def mbox_info( self, full_path = None ):
        if full_path is not None and full_path.upper()=='INBOX':
            full_path = 'INBOX'
        key = full_path
        if key is None:
            key = '%%'
        if key not in self._mbox_info:
            if full_path is None:
                self._mbox_info[key] = mbox_info_tl( self )
                return self._mbox_info[key]
            else:
                dp,sep = self.displaypath(full_path)
                flags = self.mailbox_info_cache.get((key,'FLAGS'),None)
                ext = self.mailbox_info_cache.get((key,'EXT'),None)
                if dp is not None:
                    if key not in self._mbox_info:
                        self._mbox_info[key] = mbox_info( self, dp, full_path, sep=sep, flags=flags, ext=ext, touch_time=0 )
                    return self._mbox_info[key]
                return None
        return self._mbox_info[key]
    
    def namespace( self, then=None ):
        if self._namespace is None:
            self._namespace = self.server_info_cache.get('NAMESPACE',None)
            if self._namespace is not None:
                self.process_namespaces()
                t,r,s = self.send('NAMESPACE', state='auth')
        if self._namespace is None:
            if self.have_capability( 'NAMESPACE' ):
                t,r,s = self.send( 'NAMESPACE', state='auth' )
                if r is None:
                    if then is not None:
                        t.oncomplete( then )
                        return {}
                    else:
                        t,r,s = self.wait(t)
                if r.lower()!='ok':
                    raise infotrope.base.connection.exception(s)
            else:
                if then is not None:
                    then()
                return {}
        if then is not None:
            then()
        return self._namespace

    def _parse_namespace( self, t, r, s ):
        tok = self.generic_parse( s )
        self._namespace = {}
        nsn = [u'Personal',u'Other Users',u'Shared']
        for x in range(3):
            if tok[x] is not None:
                self._namespace[ nsn[x] ] = tok[x]
        self.process_namespaces()
        self.server_info_cache['NAMESPACE'] = self._namespace
        self.server_info_cache.sync()
        return t,r,tok

    def process_namespaces(self):
        for nsn in [u'Personal',u'Other Users',u'Shared']:
            if nsn in self._namespace:
                if len(self._namespace[nsn])==1:
                    self.mbox_info().add_namespace( [nsn], self._namespace[nsn][0][0] )
                else:
                    for pfx,sep in self._namespace[nsn]:
                        self.mbox_info().add_namespace( [nsn,pfx.decode('modutf7')], pfx )

    def _parse_genurlauth( self, t, r, s ):
        tok = self.generic_parse( s )
        self._genurlauths = tok
        return t,r,tok

    def _parse_flags( self, t, r, s ):
        tok = self.generic_parse( s )
        tok = [ x.lower() for x in tok[0] ]
        return t,r,tok

    def _parse_myrights( self, t, r, s ):
        tok = self.generic_parse( s )
        mi = self.mbox_info( tok[0] )
        if not self.have_capability('RIGHTS'):
            if 'c' in tok[1]:
                tok[1] += 'k'
            if 'd' in tok[1]:
                tok[1] += 'et'
            tok[1] += 'x'
        tok[1] = ''.join([r for r in tok[1] if r not in 'cd'])
        mi.set_rights( tok[1] )
        return t,r,tok

    def login( self, user = None, password = None ):
        "Perform SASL based login sequence."
        import infotrope.base
        import infotrope.sasl
        if user is None:
            user = self.uri.username
        callback=infotrope.base.callback( self.env.callback, user, password )
        self.sasl = infotrope.sasl.sasl( self.uri, callback=callback, service='imap', secquery=self.env.secquery, tls_active=self.tls_active )
        
    def status( self, path, what, callback ):
        if not self.have_capability('IMAP4REV1'):
            return
        if path == self.get_cwm():
            return
        if what is None:
            what = ['MESSAGES','UNSEEN']
        t,r,s = self.send( 'STATUS', astring(path), what, pipeline=True, state='auth' )
        #self.s.write( st )
        self.status_callback[path] = callback
        
    def _parse_status( self, tag, resp, s ):
        toks = self.generic_parse( s )
        mbox = toks[0]
        if mbox in self.status_callback:
            info = toks[1]
            s = {}
            l = None
            for t in info:
                if l is None:
                    l = t.upper()
                else:
                    s[l]=t
                    l = None
            self.status_callback[mbox]( mbox, s )
        return tag,resp,toks
    
    def _parse_init_ok( self, tag, resp, s ):
        self.set_state('unauth', 'Parsed init OK')
        tag,resp,s = self._parse_ok( tag, resp, s )
        self.banner = s
        while not isinstance(self.banner,str):
            self.banner = self.banner[-1]
        if self._operation:
            self._operation.update( "Getting capabilities", 1 )
        if self._capability:
            self.post_capability()
        else:
            tx,rx,sx = self.send( 'CAPABILITY', state='any' )
            tx.oncomplete( self.post_capability )
        return tag,resp,s

    def post_capability( self, *stuff ):
        self.set_state('preauth', 'Parsed capability')
        if not self.tls_active() and infotrope.core.platform_tls() and self.have_starttls():
            if self._operation:
                self._operation.update( "Activating TLS", 2 )
            t,r,s = self.send('STARTTLS', state='preauth')
            t.oncomplete( self.post_tls )
        else:
            self.compression()

    def post_tls( self, cmd, t, r, s ):
        if r.upper()=='OK':
            self.reset_capability()
            self.switch_tls()
        if self._capability:
            self.compression()
        else:
            if self._operation:
                self._operation.update( "Refreshing capabilities", 3 )
            tx,rx,sx = self.send( 'CAPABILITY', state='any' )
            tx.oncomplete( self.compression )

    def compression( self, *args ):
        if not self.s.compress_on() and self.have_capability( 'COMPRESS' ) and 'DEFLATE' in self.get_capability('COMPRESS'):
            try:
                import infotrope.rfc195x
                infotrope.rfc195x.init_zlib()
                if self._operation:
                    self._operation.update( "Compression", 4 )
                tx,rx,sx = self.send( 'COMPRESS', 'DEFLATE', state='any' )
                tx.oncomplete( self.post_compress )
                return
            except:
                pass
        self.run_authenticate()

    def post_compress( self, cmd, t, r, s ):
        if r.lower()=='ok':
            import infotrope.rfc195x
            comp = infotrope.rfc195x.compress('DEFLATE','imap')
            decomp = infotrope.rfc195x.decompress('DEFLATE','imap')
            self.s.set_comp( comp, decomp )
        self.run_authenticate()

    def run_authenticate( self, *stuff ):
        if not self._enabled and self.have_capability('ENABLE'):
            cmd = ['ENABLE']
            caps = [x for x in client_capabilities if x not in suppress_extension] # Don't enable ones we're suppressing.
            cmd += caps
            for x in caps:
                if x in extension_aliases:
                    cmd += extension_aliases[x]
            self.send(cmd, state='preauth')
        if self._operation:
            self._operation.update( "Authenticating", 5 )
        self.send( authenticate( self ), state='preauth' )
        self.flush()

    def _parse_init_acap( self, tag, resp, s ):
        raise infotrope.base.connection.exception("This is an ACAP server.")

    def _parse_capability( self, tag, resp, s ):
        s = self.trim_to_line( s )
        for item in s.split(' '):
            if -1==item.find('='):
                self._capability[item.upper()] = []
            else:
                foo = []
                k = item[0:item.index('=')].upper()
                if k in self._capability:
                    foo = self._capability[k]
                foo.append( item[item.index('=')+1:] )
                self._capability[k] = foo
        for x in suppress_extension:
            if x.upper() in self._capability:
                self.log( "Supressing capability "+x.upper() )
                del self._capability[x.upper()]
        self.server_info_cache['CAPABILITY'] = self._capability
        self.server_info_cache.sync()
        if 'LITERAL+' in self._capability:
            self.ns_lit = True
        if 'BINARY' in self._capability:
            self.have_literal8 = True
        return tag, resp, s

    def _parse_id( self, tag, resp, data ):
        dx = self.generic_parse( data )
        tick = None
        data = {}
        if dx is not None:
            for t in dx[0]:
                if tick is None:
                    tick = t.lower()
                else:
                    data[tick] = t
                    tick = None
        self._identity = data
        return tag,resp,data

    def parse_oknobad( self, s ):
        s = self.trim_to_line( s )
        if s[0]=='[':
            if -1!=s.find( ']' ):
                cod = s[1:s.index(']')]
                state,i,tok = self.nparser( cod, genex=False )
                tok = [tok[0].upper()] +  tok[1:]
                s = [tok,s[s.index(']')+2:]]
                return [tok, s]
        return [s]

    def _parse_ok( self, tag, resp, s ):
        s = self.parse_oknobad( s )
        if isinstance(s[0],list):
            tok = s[0]
            if tok[0].upper() == 'CAPABILITY':
                self._capability = self._old_capability
                self._parse_capability( '*', 'CAPABILITY', ' '.join(tok[1:]) )
            elif tok[0].upper() == 'ALERT':
                self.alert( s[1] )
            elif tok[0].upper() == 'PERMANENTFLAGS':
                if self._cwm_mbx is not None:
                    mbx = self._cwm_mbx()
                    if mbx is not None:
                        mbx.set_permflags( tok[1] )
        return tag, resp, s

    def _parse_no( self, tag, resp, s ):
        s = self.parse_oknobad( s )
        if isinstance( s[0], list ):
            tok = s[0]
            if tok[0].upper() == 'ALERT':
                self.alert( s[1] )
        return tag, resp, s

    def _parse_bad( self, tag, resp, s ):
        s = self.parse_oknobad(s)
        cmd = None
        if tag in self.inprog:
            cmd = self.inprog[tag]
        self.alert( "Received BAD for tag %s: %s, command was %s" % ( tag, s, `cmd` ) )
        return tag, resp, s

    def _parse_num_exists( self, tag, resp, num, s ):
        s = self.trim_to_line( s )
        self.mailbox_info['EXISTS'] = num
        return tag, resp, int(num)
    
    def _parse_num_expunge( self, tag, resp, num, s ):
        s = self.trim_to_line( s )
        self.mailbox_info['EXISTS'] = str(int(self.mailbox_info['EXISTS'])-1)
        return tag, resp, int(num)

    def _parse_vanished( self, tag, resp, s ):
        s = self.generic_parse(s)
        uids = self.decompose_set(s[-1])
        if len(s) == 1:
            self.mailbox_info['EXISTS'] = str(int(self.mailbox_info['EXISTS'])-len(uids))
        return tag,resp,uids

    def _parse_num_recent( self, tag, resp, num, s ):
        if self._cwm_mbx is not None:
            mbx = self._cwm_mbx()
            if mbx is not None:
                mbx.recent( int(num) )
        return self._parse_num_select_recent( tag, resp, num, s )

    def _parse_num_select_recent( self, tag, resp, num, s ):
        s = self.trim_to_line( s )
        self.mailbox_info['RECENT'] = str(int(num))
        return tag,resp,num

    def _parse_select_ok( self, tag, resp, s ):
        t,r,s = self._parse_ok( tag, resp, s )
        if isinstance( s, list ):
            if len(s)>1:
                res = True
                if len(s[0])>1:
                    res = s[0][1]
                self.mailbox_info[s[0][0].upper()]=res
        return t, r, s

    def _parse_thread( self, tag, resp, s ):
        s = self.generic_parse( s )
        tag = self._threads.pop()
        return tag,resp,s
    
    def _parse_search( self, tag, resp, s ):
        s = self.trim_to_line( s )
        s = map(int,s.split())
        s.sort()
        tag = self._searches.pop()
        self.log( "Using tag %s" % tag )
        return tag,resp,s

    def decompose_set( self, set, star=None, nosort=False ):
        res = []
        if star is not None:
            set = set.replace('*',str(star))
        for r in [map(int,x.split(':')) for x in set.split(',')]:
            if len(r)==1:
                res.append( r[0] )
            else:
                res += range( r[0], r[1]+1 )
        if not nosort:
            res.sort()
        return res

    def _parse_esearch( self, tag, resp, s ):
        s = self.generic_parse( s )
        opt = {}
        optk = None
        for x in s[0]:
            if optk is None:
                optk = x.upper()
            else:
                opt[optk] = x
                optk = None
        s = s[1:]
        r = {'UID':False}
        if len(s) and s[0].upper()=='UID':
            r['UID'] = True
            s = s[1:]
        if not s:
            r['ALL'] = []
        for x in range(0,len(s),2):
            if s[x].upper() in ['COUNT','MIN','MAX']:
                r[s[x].upper()] = int(s[x+1])
            elif s[x].upper()=='ALL':
                r['ALL'] = self.decompose_set( s[x+1] )
            elif s[x].upper() in ['ADDTO','REMOVEFROM']:
                ch = r.get('CHANGE',[])
                for y in range(0,len(s[x+1]),2):
                    ch.append( (s[x].upper(),
                                int(s[x+1][y]),
                                self.decompose_set(s[x+1][y+1])
                                )
                               )
                r['CHANGE'] = ch
            elif s[x].upper() == 'PARTIAL':
                if s[x+1][1]:
                    r['PARTIAL'] = self.decompose_set(s[x+1][1])
                else:
                    r['PARTIAL'] = [] # No matches.
        tag = opt['TAG']
        self.log( "Using tag %s" % tag )
        return tag,resp,r

    def fetch_literal_processor( self, key, literal, size ):
        if self._cwm_mbx is not None:
            mbx = self._cwm_mbx()
            mbx.fetch_literal_processor( key, literal, size )
    
    def _parse_num_fetch( self, tag, resp, num, s ):
        msginfo = {"seqno":num}
        s = s.lstrip(' ')
        i = 0
        depth = 0
        if s[0] == '(':
            i = 1
            depth = 1
        while True:
            if s[i] == ')':
                i += 1
                depth = 0
            state,i,n = self.nparser(s, i, depth=depth, fetchparts=True, justone=True, emptyok=True )
            if not n:
                break
            key = n.upper()
            state,i,t = self.nparser(s, i, depth=depth, justone=True, processor=self.fetch_literal_processor, prockey=key)
            msginfo[key] = t
        if self._cwm_mbx is not None:
            mbx = self._cwm_mbx()
            mbx.rx_fetch( tag, resp, msginfo )
        elif self.select_command is not None:
            mbx = self.select_command.select_mbx
            mbx.rx_fetch( tag, resp, msginfo )
        else:
            self.log( "Got FETCH, but have no CWM." )
        return tag, resp, msginfo

    def _parse_list( self, tag, resp, ss ):
        tok = self.generic_parse( ss )
        if self._doing_lsub:
            tok[0] = None
        else:
            tok[0] = [ x.lower() for x in tok[0] ]
        if len(tok)<4:
            tok.append([]) # Spoof empty extended data items.
        self.mailbox_info_cache[tok[2], 'SEP'] = tok[1]
        self.mailbox_info_cache[tok[2], 'FLAGS'] = tok[0]
        self.mailbox_info_cache[tok[2], 'EXT'] = tok[3]
        if tok[2] not in self._mbox_info:
            dp,sep = self.displaypath( tok[2], tok[1] )
            self.log( "Creating new MI for %s" % `dp` )
            self._mbox_info[ tok[2] ] = mbox_info( self, display=dp, full_path=tok[2], flags=tok[0], sep=tok[1], ext=tok[3] )
        else:
            self.log( "Refreshing MI for %s" % `tok[2]` )
            self._mbox_info[ tok[2] ].refresh( tok[0], tok[1], tok[3] )
        return tag, resp, tok

    def get_cwm( self ):
        return self._cwm

    def reset_state( self ):
        if self._cwm_mbx is not None:
            mbx = self._cwm_mbx()
            if self.state != 'select':
                if mbx is not None:
                    mbx.sync()
                self._cwm_mbx_save = weakref.ref(mbx)
        self._state_save = self.state
        self.set_state('dead', 'Reset state')
        self._cwm = None
        self._cwm_mbx = None
        self.mailbox_info = {}
        self._capability = {}
        self._old_capability = {}
        self.idling = False

    def restore_state( self ):
        self.wait_ready()
        mbx = None
        if self._cwm_mbx_save is not None:
            mbx = self._cwm_mbx_save()
        if mbx is not None:
            if self._state_save != 'select':
                self._cwm_mbx = weakref.ref(mbx)
                mbx.uidvalidity()
        if self.state!=self._state_save:
            if self._state_save in ['select']:
                self.state = self._state_save

    def set_cwm( self, path, mbx, async=False ):
        if self._cwm==path:
            return False
        if self._cwm_mbx is not None:
            cmbox = self._cwm_mbx()
            if cmbox is mbx:
                return False
            if cmbox is not None:
                cmbox.sync()
        if self.select_command is not None:
            if self.select_command.select_mbx is mbx:
                return False
            elif not async:
                self.wait(self.select_command)
            else:
                class foo:
                    def __init__(self,s,*args,**kw):
                        self.s = s
                        self.args = args
                        self.kw = kw
                    def __call__(self,*a,**kw):
                        self.s(*self.args,**self.kw)
                f = foo(self.set_cwm,path,mbx,async=True)
                self.select_command.oncomplete(f)
                return True
        self.mailbox_info = {}
        old_path = self._cwm
        self._cwm = None
        self._cwm_mbx = None
        self.register( '*', mbx )
        before = time.time()
        if readonly:
            cmd = ['EXAMINE']
        else:
            cmd = ['SELECT']
        cmd.append(astring(path))
        using_qresync = False
        if self.have_capability('QRESYNC'):
            qresync_data = mbx.qresync_data()
            if qresync_data:
                cmd.append( ['QRESYNC', qresync_data] )
                using_qresync = True
        if not using_qresync and self.have_capability('CONDSTORE'):
            cmd.append( ['CONDSTORE'] )
        if not using_qresync:
            self.unselect(old_path, wait=False) ## Pipeline it.
        tag,x1,x2 = self.send( cmd, pipeline=True, state='auth' )
        tag.select_path = path
        tag.select_mbx = mbx
        tag.select_before = before
        tag.select_async = async
        tag.select_qresync = using_qresync
        tag.oncomplete(self.post_select)
        tag.pre_state = 'select'
        if tag.sent_complete:
            self.set_state('select', 'Sent Complete')
        self.select_command = tag
        if self.have_capability( 'ACL' ) and not self.have_capability('ACL2'):
            tag2,x1,x2 = self.send( 'MYRIGHTS', astring(path), state='auth' )
        self.flush()
        if not async:
            t,r,s = self.wait( tag, True )
        return True

    def post_select(self, tag, t,r,s):
        path = tag.select_path
        mbx = tag.select_mbx
        before = tag.select_before
        self.select_command = None
        if r.lower()=='ok':
            self.set_state('mbox', 'Select complete') #'selected:%s' % path
            self._cwm = path
            self._cwm_mbx = weakref.ref(mbx)
            after = time.time()
            seltime = after - before
            if self.seltime:
                seltime += self.seltime
                seltime /= 2.0
                self.seltime = seltime
                self.adjust_idle_time( self.seltime )
            else:
                self.seltime = seltime
            self.last_probe = None
            if tag.select_async:
                mbx.mailbox_reselected(tag)
        else:
            self.set_state('auth', 'SELECT failure')
            raise infotrope.base.connection.exception(s)
        
    def local_logout( self ):
        self._cwm = None
        self._cwm_mbx = None

    def unselect( self, path, wait=True ):
        try:
            if self._cwm is None:
                return
            if self._cwm!=path:
                return
            if self.s is None:
                return
            try:
                if self.have_capability('UNSELECT'):
                    t,r,s = self.send('UNSELECT', state='selected:%s' % path, discard=True)
                    class foo:
                        def __init__(self, svr):
                            self.__svr = svr
                        def __call__(self, *args):
                            self.__svr.set_state('auth', 'Unselect OK')
                    t.oncomplete(foo(self))
                    if not wait:
                        return
                    if r is None:
                        self.wait( t )
                    self.set_state('auth', 'UNSELECT completed')
                    self._cwm = None
                    return
                t,r,s = self.send( 'EXAMINE', astring('&#-&#/#'), state='selected:%s' % path, discard=True ) # Invalid modified UTF-7 on three counts.
                if not wait:
                    return
                if r is None:
                    self.wait(t)
                if r.lower() == 'no':
                    self._cwm = None
                self.set_state('auth', 'EXAMINE-UNSELECT OK')
                return
            except:
                pass
            self._cwm = None
        finally:
            if self._cwm is None:
                self._cwm_mbx = None

    def idle_prod( self ):
        if self.s is None or self.state=='dead':
            self.idling = False
            return
        if self.idling is True:
            self.idling = False
            if self.s is not None:
                self.s.write( 'DONE\r\n' )
                self.proto_log( 'DONE' )
                self.proto_log_done()
                self.log("(by IDLE prod)")
        elif self.idling is not False:
            self.idling.stop = True
            while self.idling:
                self.fetch()
        t,r,s = self.send( 'NOOP', state='any' )
        self.flush()
        
    def idle_handler( self, enter ):
        if enter and self.state not in ['auth','mbox']:
            return
        if self.idling and enter:
            if self._cwm_mbx is not None:
                mbx = self._cwm_mbx()
                if mbx is not None:
                    mbx.cleanup()
            if ( time.time() - self.last_send ) > ( 25 * 60 ):
                self.idle_prod()
                return
            return
        if not self.idling and not enter:
            return
        if enter == True:
            self.mailbox_info_cache.sync()
            self.server_info_cache.sync()
            if self._cwm_mbx is not None:
                mbx = self._cwm_mbx()
                if mbx is not None:
                    mbx.sync()
                    if mbx.notify():
                        self.log( "Pending notifies, won't change IDLE state." )
                        return
        if 'IDLE' not in self.capability():
            if enter and self.state == 'mbox' and ( time.time() - self.last_prod ) > ( 300 ):
                self.send( 'NOOP', state='any' )
                self.flush()
            return
        if enter == True:
            if self._cwm_mbx is not None:
                mbx = self._cwm_mbx()
                if mbx is not None:
                    mbx.sync()
                    if mbx.notify():
                        self.log( "Pending notifies, won't change IDLE state." )
                        return
            self.log( `[ x for x in self.inprog.values() if x.response is None]` )
            if len([ x for x in self.inprog.values() if x.response is None])>0:
                self.log( "Commands in progress still, won't change IDLE state." )
                self.flush()
                return
            self.log( "IDLE on" )
            class idle(infotrope.base.command):
                def __init__( self, env, server ):
                    infotrope.base.command.__init__( self, env, None, ('IDLE',) )
                    self.idle_command = True
                    self.resend = False
                    self.feeding = True
                    self.stop = False
                    self.server = weakref.ref(server)
                    self.oncomplete(self.check)

                def feed( self, payload ):
                    self.feeding = False
                    if self.stop:
                        if self.server().state != 'dead' and self.server().s is not None:
                            self.server().s.write('DONE\r\n')
                            self.server().proto_log('DONE')
                            self.server().proto_log_done()
                            self.server().log("(by IDLE)")
                        else:
                            self.server().set_state('dead', 'IDLE (cmd)')
                        self.server().idling = False
                    else:
                        self.server().idling = True
                    return

                def check(self, cmd, t,r,s):
                    if r.lower()!='ok':
                        self.server().idling = False
            self.idling,r,s = self.send( idle(self.env,self), state='auth' )
            self.idling.counter_sent = None
            self.flush()
            self.last_prod = time.time()
        else:
            self.log( "IDLE off" )
            if self.state =='dead' or self.s is None:
                self.set_state('dead', 'IDLE')
                self.idling = False
                return
            if self.idling is True:
                self.s.write( 'DONE\r\n' )
                self.proto_log( 'DONE' )
                self.proto_log_done()
                self.log("(by IDLE handler)")
                self.idling = False
            else:
                self.idling.stop = True
                while self.idling:
                    self.fetch()
    
    def genurlauth( self, uris, expire=None, role=None, userid=None ):
        if not isinstance( uris, list ):
            uris = [uris]
        if not self.have_capability( 'URLAUTH' ):
            return None
        self._genurlauths = []
        stuff = []
        for uri in uris:
            if not str(uri).startswith( str(self.uri) ):
                raise "Wrong server!"
            role = role or 'anonymous'
            if role in ['submit','user']:
                if userid is None:
                    if role == 'submit':
                        userid = uri.username
                    else:
                        raise "Needs userid"
                role = role + '+' + userid.encode('urlencode')
            uritxt = str(uri)
            if expire:
                uritxt += time.strftime( ";EXPIRE=%Y-%m-%dT%H:%M:%SZ", time.gmtime( expire ) )
            uritxt += ';URLAUTH=%s' % role
            stuff.append( uritxt )
            stuff.append( 'INTERNAL' )
        try:
            t,r,s = self.send( 'GENURLAUTH', *stuff )
            self.wait( t )
        except:
            self._genurlauths = []
        return self._genurlauths

    def mailbox( self, path, open=True ):
        import infotrope.base
        import infotrope.url
        if path in self.mailboxes:
            return self.mailboxes[path]
        try:
            mbx = mailbox2( self, path, self.mbox_info( path ) )
            if open:
                mbx.uidvalidity()
            self.mailboxes[path] = mbx
            return mbx
        except infotrope.base.connection.exception, ref:
            if len(ref.msg)==2:
                if len(ref.msg[0])==2:
                    if ref.msg[0][0].lower()=='referral':
                        import infotrope.serverman
                        uri = infotrope.url.URL( ref.msg[0][1] )
                        sman = infotrope.serverman.get_serverman()
                        conn = sman[uri]
                        mbx = conn.mailbox( uri.mailbox )
                        mbx.proxy_uri_stub = infotrope.url.URL( self.uri.asString() + path.decode('modutf7').encode('urlencode') ).asString()
                        return mbx
            raise

    def delete( self, path, then=None ):
        if path in self.mailboxes:
            del self.mailboxes[path]
        t,r,s = self.send( 'DELETE', astring( path ) )
        if r is None:
            if then:
                t.oncomplete(then)
                return
            else:
                t,r,s = self.wait( t )
        if r.lower()!='ok':
            raise infotrope.base.connection.exception( s )
        
    def create( self, path, then=None ):
        t,r,s = self.send( 'CREATE', astring( path ) )
        if then is None:
            if r is None:
                t,r,s = self.wait( t )
        if r is not None:
            if r.lower()!='ok':
                raise infotrope.base.connection.exception( s )
        elif then:
            t.oncomplete( then )

class message_part:
    def __init__( self, bs, part_id=None ):
        self.encoding = None
        self.params = {}
        self.children = []
        self.disposition = 'X-UNKNOWN'
        self.disposition_params = {}
        self.languages = []
        self.location = None
        self.id = None
        self.description = None
        if bs is not None:
            bs = bs[:]
        if part_id=='':
            self.type = 'MESSAGE'
            self.subtype = 'RFC822'
            self.part_id = ''
            self.children.append( message_part( bs, 'HEADER' ) )
            self.children.append( message_part( bs ) )
            self.children_disposition_probably('INLINE')
        elif part_id=='HEADER':
            self.type = 'MESSAGE'
            self.subtype = 'RFC822-HEADER'
            self.encoding = None
            self.params = {}
            self.part_id = 'HEADER'
            self.children = []
            self.disposition = 'INLINE'
            self.size = 0
        else:
            self.part_id = part_id
            self.children = []
            self.params = {}
            if self.part_id is None:
                self.part_id = 'TEXT'
                self.disposition = 'INLINE'
            if self.part_id=='1':
                self.disposition = 'INLINE'
            if self.part_id[-4:]=='TEXT':
                self.disposition = 'INLINE'
            bs.reverse()
            # Find the type.
            t = bs.pop()
            if isinstance( t, list ):
                self.type = 'MULTIPART'
                self.disposition = 'INLINE'
                self.add_child( t )
                n = None
                while bs:
                    n = bs.pop()
                    if not isinstance( n, list ):
                        break
                    self.add_child( n )
                self.subtype = n.upper()
                if bs:
                    n = bs.pop()
                    trip = True
                    save = None
                    for x in n:
                        if trip:
                            save = x
                            trip = False
                        else:
                            self.params[save] = x
                            trip = True
                if bs:
                    n = bs.pop()
                    if n is not None:
                        self.disposition = n[0].upper()
                        self.disposition_params = {}
                        if len(n)>1 and n[1] is not None:
                            trip = True
                            save = None
                            for x in n[1]:
                                if trip:
                                    save = x.upper()
                                    trip = False
                                else:
                                    self.disposition_params[save] = x
                                    trip = True
                if bs:
                    n = bs.pop()
                    if isinstance(n,list):
                        self.languages = n
                    else:
                        self.languages = [n]
                if bs:
                    n = bs.pop()
                    self.location = n
            else:
                if self.part_id[-4:] == 'TEXT':
                    self.part_id = self.part_id[:-4] + '1'
                self.type = t.upper()
                self.subtype = bs.pop().upper()
                self.params = {}
                n = bs.pop()
                if isinstance( n, list ):
                    l = None
                    for t in n:
                        if l is None:
                            l = t
                        else:
                            self.params[l] = t
                            l = None
                self.id = bs.pop()
                descr = bs.pop()
                if descr is not None:
                    self.description = infotrope.encoding.decode_header( descr )
                self.encoding = bs.pop().upper()
                self.size = bs.pop()
                if self.size is not None:
                    self.size = int(self.size)
                if self.type == 'MESSAGE' and self.subtype == 'RFC822':
                    hdr = message_part( None, 'HEADER' )
                    hdr.part_id = "%s.HEADER" % self.part_id
                    hdr.envelope = envelope( bs.pop() )
                    if self.description is None:
                        self.description = hdr.envelope.Subject
                    self.children.append( hdr )
                    self.add_child( bs.pop() )
                    self.lines = bs.pop()
                elif self.type == 'TEXT':
                    self.lines = bs.pop()
                    if self.subtype == 'PLAIN':
                        self.disposition = 'INLINE'
                # Extension fields:
                if bs:
                    self.md5 = bs.pop()
                if bs:
                    n = bs.pop()
                    if n is not None:
                        self.disposition = n[0].upper()
                        self.disposition_params = {}
                        if len(n)>1 and n[1] is not None:
                            trip = True
                            save = None
                            for x in n[1]:
                                if trip:
                                    save = x
                                    trip = False
                                else:
                                    self.disposition_params[save.upper()] = x
                                    trip = True
                if bs:
                    self.location = bs.pop()
        self.full_type = self.type + '/' + self.subtype

    def __repr__( self ):
        return '<%s id %s type %s/%s>' % ( self.__class__.__name__, self.part_id, self.type, self.subtype )

    def add_child( self, sbs ):
        snum = len(self.children)+1
        if self.part_id[-4:] == 'TEXT':
            npart_id = "%s%d" % ( self.part_id[0:-4], snum )
        elif self.type=='MESSAGE' and self.subtype=='RFC822':
            npart_id = "%s.TEXT" % self.part_id
        else:
            npart_id = "%s.%d" % ( self.part_id, snum )
        self.children.append( message_part( sbs, npart_id ) )

    def children_disposition_probably( self, what ):
        if self.disposition == 'X-UNKNOWN':
            self.disposition = what
        if self.type=='MULTIPART':
            if self.subtype=='ALTERNATIVE':
                for x in self.children:
                    x.children_disposition_probably(self.disposition)
            else:
                self.children[0].children_disposition_probably( self.disposition )
                for x in self.children[1:]:
                    x.children_disposition_probably( 'ATTACHMENT' )
        elif self.type=='MESSAGE':
            if self.subtype=='RFC822':
                for x in self.children:
                    x.children_disposition_probably('INLINE')
            else:
                for x in self.children:
                    x.children_disposition_probably('ATTACHMENT')

    def find_id( self, part_id ):
        if part_id == self.part_id:
            return self
        for x in self.children:
            r = x.find_id( part_id )
            if r is not None:
                return r
        return None

    def all_parts( self ):
        ids = [self]
        for x in self.children:
            ids += x.all_parts()
        return ids
    
    def find( self, type, subtypes ):
        if self.type==type:
            if self.subtype in subtypes:
                return self, subtypes[self.subtype]
            else:
                return self, 0
        elif self.type=='MULTIPART' or ( self.type=='MESSAGE' and self.subtype=='RFC822' ):
            if self.subtype=='ALTERNATIVE':
                # Pick best match.
                last_good = None
                last_pref = -1
                for child in self.children:
                    s,p = child.find( type, subtypes )
                    if p>last_pref:
                        last_good=s
                        last_pref=p
                return last_good,last_pref
            else:
                # Pick first good match.
                last_good = None
                last_pref = 0
                for child in self.children:
                    s,p = child.find( type, subtypes )
                    if p>0:
                        return s,p
                    else:
                        last_good = s
                        last_pref = p
                return last_good,last_pref
        else:
            return None,0

    def find_cid( self, cid ):
        if self.id == cid:
            return self
        for c in self.children:
            t = c.find_cid( cid )
            if t is not None:
                return t
        return None

    def filename( self ):
        sfn = None
        if 'NAME' in self.params:
            sfn = self.params['NAME']
        if 'FILENAME' in self.disposition_params:
            sfn = self.disposition_params['FILENAME']
        if sfn is None:
            return None
        if sfn.find('/')!=-1:
            sfn = sfn[sfn.find('/')+1:]
        if sfn.find('\\')!=-1:
            sfn = sfn[sfn.find('\\')+1:]
        return sfn
    

class message:
    reply_headers = 'BODY[HEADER.FIELDS (REFERENCES)]'
    ### reply_headers.__doc__ = 'A fetch part describing the headers useful when constructing a reply.'
    list_headers = 'BODY[HEADER.FIELDS (FOLLOWUP-TO LIST-ARCHIVE LIST-HELP LIST-ID LIST-POST LIST-SUBSCRIBE LIST-UNSUBSCRIBE NEWSGROUPS)]'
    capture_headers = 'BODY[HEADER.FIELDS (JABBER-ID)]'
    ### list_headers.__doc__ = 'A fetch part describing the headers relating to a mailing list message.'
    summary = ['FLAGS','BODYSTRUCTURE','ENVELOPE']
    ### summary.__doc__ = 'Fetch one, and fetch the lot.'
    
    def __init__( self, uid, mailbox ):
        self._uid = uid
        self._mailbox_ref = weakref.ref(mailbox)
        self._mailbox_path = mailbox.path()
        self._mailbox_server = mailbox.server()
        self._fetched = {}
        self._bodypart = None
        self._highest_modseq_flags = None
        self._lhn = None
        self.__uri = None
        self._watchers = {}
        self.need_notify = False

    def watch(self, obj, part):
        if self.have_cached(part):
            obj.message_watch_notify(self,part)
        else:
            self._watchers.get('BODY[%s]' % part.part_id,[part]).append(weakref.ref(obj))
            self._watchers.get('BINARY[%s]' % part.part_id,[part]).append(weakref.ref(obj))

    def server( self ):
        return self._mailbox_server

    def uid( self ):
        return self._uid

    def flag( self, f ):
        self.flag_change( '+FLAGS', f )
    def unflag( self, f ):
        self.flag_change( '-FLAGS', f )

    def flag_change( self, item, f ):
        if not (self.mailbox().condstore_enabled() and self.flags(True) is None):
            item += '.SILENT' # No point if CONDSTORE is on.
        if not isinstance( f, list ):
            f = [f]
        f = [ ff.lower() for ff in f ]
        self.mailbox().store( self, item, f )

    def set_annotation( self, annotation, val=None, shared=False ):
        value = 'value.priv'
        if shared:
            value = 'value.shared'
        self.mailbox().store( self, 'ANNOTATION\0%s\0%s' % ( annotation, value ), val )

    def feed( self, stuff ):
        for part,value in stuff.items():
            self._fetched[part]=value
            watchers = self._watchers.get(part,None)
            if watchers:
                part = watchers[0]
                for y in watchers[1:]:
                    x = y()
                    if x is not None:
                        x(self, part)
            if part == self.list_headers:
                if self._lhn is not None:
                    lhn = self._lhn
                    self._lhn = None
                    lhn( self )
            elif part == self.capture_headers:
                if self._chn is not None:
                    chn = self._chn
                    self._chn = None
                    chn( self )

    def fetch( self, what, extend=False, nofetch=False ):
        if isinstance(what,str):
            what = [what]
        #if 'FLAGS' not in what:
        #    what.append( 'FLAGS' )
        self.mailbox().fetch( self, what, extend, nofetch )
    
    def send_body( self, part, handon, decode=True, unpack=True ):
        if decode:
            if 'CHARSET' in part.params:
                try:
                    ''.decode( part.params['CHARSET'] )
                except LookupError:
                    self._mailbox_server.alert( 'Unknown charset %s.' % part.params['CHARSET'] )
                    return
        l = literal_processor( part, handon, decode, unpack )
        p = part.part_id
        p = p.strip( '0123456789.' )
        if unpack and len(p)==0 and self._mailbox_server.have_capability('BINARY') and part.encoding is not None and part.encoding not in ['7BIT','8BIT','BINARY']:
            what = 'BINARY[%s]' % ( part.part_id )
        else:
            what = 'BODY[%s]' % ( part.part_id )
        if what in self._fetched:
            l( what, self._fetched[what], len(self._fetched[what]) )
            #del self._fetched[what]
            return l
        self.mailbox().register_literal( what, l )
        self.mailbox().fetch( self, [what], False, False, False )
        self._mailbox_server.flush()
        return l # That's the letter, BTW... ;-)

    def get_reply_headers( self ):
        if self.reply_headers not in self._fetched:
            self.fetch( self.reply_headers )
        if 'reply_headers' not in self._fetched:
            self._fetched['reply_headers'] = infotrope.parser.rfc822( self._fetched[self.reply_headers] )
            del self._fetched[self.reply_headers]

    def reply_header( self, foo ):
        self.get_reply_headers()
        return self._fetched['reply_headers'][ foo ]

    def fetch_list_headers_and_notify( self, me ):
        if self.list_headers in self._fetched:
            me( self )
            return
        self._lhn = me
        self.mailbox().fetch( self, [self.list_headers], False, False, False )

    def fetch_capture_headers_and_notify( self, me ):
        if self.capture_headers in self._fetched:
            me( self )
            return
        self._chn = me
        self.mailbox().fetch( self, [self.capture_headers], False, False, False )

    def get_list_headers( self, nofetch=False ):
        if self.list_headers not in self._fetched:
            self.fetch( self.list_headers, nofetch=nofetch )
        if self.list_headers in self._fetched:
            if 'list_headers' not in self._fetched:
                self._fetched['list_headers'] = infotrope.parser.rfc822( self._fetched[self.list_headers] )
                del self._fetched[self.list_headers]

    def list_header( self, foo, nofetch=False ):
        self.get_list_headers( nofetch )
        if 'list_headers' in self._fetched:
            t = self._fetched['list_headers'][foo]
            if t is None:
                return None
            return infotrope.encoding.decode_header( self._fetched['list_headers'][ foo ] )
        return False

    def get_capture_headers( self, nofetch=False ):
        if self.capture_headers not in self._fetched:
            self.fetch( self.capture_headers, nofetch=nofetch )
        if self.capture_headers in self._fetched:
            if 'capture_headers' not in self._fetched:
                self._fetched['capture_headers'] = infotrope.parser.rfc822( self._fetched[self.capture_headers] )
                del self._fetched[self.capture_headers]

    def capture_header( self, foo, nofetch=False ):
        self.get_capture_headers( nofetch )
        if 'capture_headers' in self._fetched:
            t = self._fetched['capture_headers'][foo]
            if t is None:
                return None
            return infotrope.encoding.decode_header( self._fetched['capture_headers'][ foo ] )
        return False

    def flagged( self, flag ):
        return flag.lower() in self.flags()

    def flags( self, nofetch=False ):
        if 'FLAGS' not in self._fetched:
            if nofetch:
                self.need_notify = True
                return None
            if 'FLAGS' in self.summary:
                self.fetch( self.summary, True, nofetch )
            else:
                self.fetch( 'FLAGS', False, nofetch )
        elif not nofetch and self._highest_modseq_flags < self.mailbox().highest_modseq():
            self.fetch( 'FLAGS', True )
        if 'FLAGS' not in self._fetched:
            return None
        self._highest_modseq_flags = self.mailbox().highest_modseq()
        return self._fetched['FLAGS']

    def fetch_flags(self):
        'Should I fetch flags?'
        if 'FLAGS' not in self._fetched:
            return True
        if self._highest_modseq_flags >= self.mailbox().highest_modseq():
            return False
        if self._uid <= self.mailbox()._highwater_uid:
            if self._highest_modseq_flags < self.mailbox()._highwater_modseq:
                self._highest_modseq_flags = self.mailbox().highest_modseq()
                return False
        return True

    def annotation( self, annotation, shared=False, nullok=False ):
        value = 'value.priv'
        if shared:
            value = 'value.shared'
        key = 'ANNOTATION\0%s\0%s' % ( annotation, value )
        self.fetch( key, nofetch=nullok )
        if key in self._fetched:
            return self._fetched[key]
        
    def structure( self, nofetch=False ):
        if 'BODYSTRUCTURE' not in self._fetched:
            if nofetch:
                self.need_notify = True
            if 'BODYSTRUCTURE' in self.summary:
                self.fetch( self.summary, extend=True, nofetch=nofetch )
            else:
                self.fetch( 'BODYSTRUCTURE', extend=False, nofetch=nofetch )
        if 'BODYSTRUCTURE' in self._fetched:
            return self._fetched['BODYSTRUCTURE']

    def internaldate( self, nofetch=False ):
        if 'INTERNALDATE' not in self._fetched:
            if nofetch:
                self.need_notify = True
            if 'INTERNALDATE' in self.summary:
                self.fetch( self.summary, True, nofetch )
            else:
                self.fetch( 'INTERNALDATE', True, nofetch )
        if 'INTERNALDATE' in self._fetched:
            return self._fetched['INTERNALDATE']

    def parts( self ):
        if 'parts' not in self._fetched:
            tmp = [ x for x in self.structure() ]
            self._fetched['parts'] = message_part( tmp, '' )
        return self._fetched['parts']

    def envelope_raw( self, nofetch=False ):
        if 'ENVELOPE' not in self._fetched:
            if nofetch:
                self.need_notify = True
            if 'ENVELOPE' in self.summary:
                self.fetch( self.summary, True, nofetch )
            else:
                self.fetch( 'ENVELOPE', True, nofetch )
        if 'ENVELOPE' in self._fetched:
            e = self._fetched['ENVELOPE']
            return e

    def envelope( self, nofetch=False ):
        if 'envelope_parsed' not in self._fetched:
            tmp = self.envelope_raw( nofetch )
            if tmp is None:
                return
            self._fetched['envelope_parsed'] = envelope( tmp )
        return self._fetched['envelope_parsed']

    def get_from_name( self ):
        if self.envelope() is None:
            return
        if len(self.envelope().From):
            return self.envelope().From[0].hname
        return None

    def get_sent_date_real( self, env=None ):
        if env is None:
            env = self.envelope()
            if env is None:
                return
        try:
            datefield = env.Date
            if datefield is None:
                return None
            return time.localtime( infotrope.parser.parse_date( datefield ) )
        except:
            return None

    def get_sent_date( self ):
        if 'datesent' not in self._fetched:
            self._fetched['datesent'] = self.get_sent_date_real()
        return self._fetched['datesent']

    def body( self, part ):
        raw = self.body_decode( part )
        try:
            if 'CHARSET' in part.params:
                try:
                    out = raw.decode( part.params['CHARSET'].lower() )
                    return out
                except LookupError, e:
                    pass
                except UnicodeDecodeError, e:
                    pass
            # Try another one. Work through the common ones until we find a match.
            for ch in ['utf-8','us-ascii','iso-8859-15']:
                try:
                    out = raw.decode(ch)
                    return out
                except UnicodeDecodeError, e:
                    pass
            return raw.decode( 'us-ascii', errors='replace' )
        except AttributeError, e:
            pass
        return raw

    def body_decode( self, part ):
        p = part.part_id
        p = p.strip( '0123456789.' )
        ff = 'BINARY[%s]' % part.part_id
        if ff not in self._fetched:
            if len(p)==0 and self._mailbox_server.have_capability( 'BINARY' ) and part.encoding is not None and part.encoding not in ['7BIT','8BIT','BINARY'] and not self.mailbox().have_cached(self._uid, 'BODY[%s]' % part.part_id):
                self.fetch( ff )
            else:
                self._fetched[ff] = self.body_encoded( part )
        return self._fetched[ff]
    
    def body_encoded( self, part ):
        ff = "BODY[%s]" % part.part_id
        if ff not in self._fetched:
            self.fetch( ff )
        try:
            if part.encoding is None \
                   or part.encoding=='7BIT' \
                   or part.encoding=='BINARY' \
                   or part.encoding=='8BIT':
                return self._fetched[ff]
            elif part.encoding=='QUOTED-PRINTABLE':
                return self._fetched[ff].decode( 'quoted-printable' )
            elif part.encoding=='BASE64':
                return self._fetched[ff].decode( 'base64' )
            else:
                return self._fetched[ff]
        except AttributeError, e:
            pass
        return self._fetched[ff]

    def body_raw( self, part ):
        if isinstance( part, message_part ):
            part = part.part_id
        if part.lower().startswith( 'address ' ):
            s,i,toks = self._mailbox_server.nparser( part, genex=False )
            if len(toks)>2:
                toks = toks[:2] + [self._mailbox_server.decompose_set( toks[2] )]
            return str(self.address_part( *toks[1:] ))
        ff = "BODY[%s]" % part
        if ff not in self._fetched:
            self.fetch( ff )
        b = self._fetched[ff]
        del self._fetched[ff]
        return b

    def have_cached(self, part):
        if not self.mailbox().have_cached(self._uid, 'BINARY[%s]' % part.part_id):
            return self.mailbox().have_cached(self._uid, 'BODY[%s]' % part.part_id)
        return True

    def address_part( self, which, set=None ):
        if set is not None:
            set = [ x - 1 for x in set ]
        addresslist = envelope_addr( None )
        env = self.envelope()
        for x in which:
            if x.lower()=='all':
                addresslist += env.From
                addresslist += env.Sender
                addresslist += env.ReplyTo
                addresslist += env.To
                addresslist += env.CC
                addresslist += env.BCC
            elif x.lower()=='from':
                addresslist += env.From
            elif x.lower()=='sender':
                addresslist += env.Sender
            elif x.lower()=='replyto':
                addresslist += env.ReplyTo
            elif x.lower()=='to':
                addresslist += env.To
            elif x.lower()=='cc':
                addresslist += env.CC
            elif x.lower()=='bcc':
                addresslist += env.BCC
        if set is None:
            return addresslist
        addrs2 = envelope_addr( None )
        for x in set:
            if x >= len( addresslist ):
                continue
            addrs2.members.append( addresslist[x] )
        return addrs2

    def address_list( self, part ):
        s,i,toks = self._mailbox_server.nparser( part, genex=False )
        if len(toks)>2:
            toks = toks[:2] + [self._mailbox_server.decompose_set( toks[2] )]
        if toks[0].upper()!='ADDRESS':
            raise "Wrong part format"
        addresslist = self.address_part( *toks[1:] )
        return addresslist.list_addresses()

    def __getitem__( self, key ):
        return self._fetched[key]

    def mailbox( self ):
        m = self._mailbox_ref()
        if m is None:
            m = self._mailbox_server.mailbox( self._mailbox_path )
        return m

    def __repr__( self ):
        return "<infotrope.imap.message for %s>" % ( `self.mailbox().uri().asString() + '/;uid=%s'%self._uid` )

    def uri( self ):
        if self.__uri is None:
            self.__uri = infotrope.url.URL( self.mailbox().uri().asString() + ('/;uid=%s'%self._uid) )
        return self.__uri

class envelope_single:
    def __init__( self, toks ):
        self.name = toks[0]
        self.sourceRoute = toks[1]
        self.mailbox = toks[2]
        self.domain = toks[3]
        self.hname = self.name
        self.address = None
        if self.domain is not None:
            self.address = self.mailbox + '@' + self.domain
        if self.address is None:
            self.address = self.mailbox
        if self.address is None:
            self.address = 'Unknown'
        if self.hname is None:
            self.hname = self.address.decode( 'us-ascii' )
        else:
            self.hname = infotrope.encoding.decode_header( self.hname )

    def __contains__( self, s ):
        if str(s) in self.address:
            return True
        if s in self.hname:
            return True
        return False

    def __str__( self ):
        if self.name is None:
            return '<' + self.address + '>'
        else:
            return '"' + self.name + '" <' + self.address + '>'

    def list_addresses( self ):
        return [self.address]

class envelope_group(envelope_single):
    def __init__( self, toks ):
        envelope_single.__init__( self, toks )
        self.members = []
        self.hname = infotrope.encoding.decode_header( self.mailbox )

    def __contains__( self, s ):
        if s in self.hname:
            return True
        for m in self.members:
            if s in m:
                return True
        return False

    def __str__( self ):
        return self.hname + ': ' + ','.join( [str(x) for x in self.members] ) + ';'

    def list_addresses( self ):
        l = []
        for m in self.members:
            l += m.list_addresses()
        return l

class envelope_addr:
    def __init__( self, toks ):
        if toks is None:
            self.members = []
            return
        ret = []
        group = None
        for t in toks:
            a = envelope_single( t )
            if a.domain is None:
                if group is None:
                    group = envelope_group( t )
                    ret.append( group )
                else:
                    group = None
            else:
                if group is None:
                    ret.append( a )
                else:
                    group.members.append( a )
        self.members = ret

    def __contains__( self, s ):
        for m in self.members:
            if s in m:
                return True
        return False

    def __getitem__( self, s ):
        return self.members[s]

    def __len__( self ):
        return len(self.members)

    def __add__( self, other ):
        r = envelope_addr( None )
        r.members = self.members + other.members
        return r

    def __str__( self ):
        return ', '.join( [str(x) for x in self.members] )

    def list_addresses( self ):
        l = []
        for m in self.members:
            l += m.list_addresses()
        return l

class envelope:
    def __init__( self, toks ):
        self.Date = toks[0]
        self.SubjectRaw = toks[1]
        self.Subject = None
        self.From = envelope_addr( toks[2] )
        self.Sender = envelope_addr( toks[3] )
        self.ReplyTo = envelope_addr( toks[4] )
        self.To = envelope_addr( toks[5] )
        self.CC = envelope_addr( toks[6] )
        self.BCC = envelope_addr( toks[7] )
        self.InReplyTo = toks[8]
        self.MessageID = toks[9]
        if self.SubjectRaw is not None:
            self.Subject = infotrope.encoding.decode_header( self.SubjectRaw )

# Some configurables.
max_pull = 500
# max_pull - this needs dynamic adjustment for ESEARCH efficiency.
max_pull_resync = 50
# How many numbers should I stick all on one line? This amount seems to work, it's here to limit
# command length.
mutable_cache = ['FLAGS','ANNOTATION','MODSEQ']
never_cache = ['UID','seqno']

class seqno_cache_thing:
    seqno_lru_len = 15
    def __init__( self, real_one ):
        self._real = real_one
        self._cache = {}
        self._cache_lru = []

    def get_lru( self ):
        return self._cache_lru[:]

    def __getitem__( self, x ):
        t = self.get(x)
        if t is None:
            raise KeyError, x
        return t

    def get( self, x, default=None ):
        t = self._cache.get( x )
        if t is not None:
            if not t:
                self.__delitem__(x)
                return default
            try:
                self._cache_lru.remove(x)
            except ValueError:
                pass
            self._cache_lru.append(x)
            return t
        t = self._real.get(str(x))
        if t is None:
            return default
        if not t:
            self.__delitem__(x)
            return default
        self._cache[x] = t
        self._cache_lru.append( x )
        self.clean_lru()
        return t
    
    def clean_lru( self ):
        for p in self._cache_lru[:-self.seqno_lru_len]:
            try:
                del self._cache[p]
            except KeyError:
                pass
        self._cache_lru = self._cache_lru[-self.seqno_lru_len:]

    def writethrough( self ):
        for x,arr in self._cache.items():
            self._real[str(x)] = arr
        
    def sync( self ):
        self.writethrough()
        try:
            self._real.sync()
        except:
            pass

    def __setitem__( self, x, wha ):
        if 0 == len(wha):
            self.__delitem__( x )
            return
        import array
        wha = array.array('L',wha)
        if x in self._cache_lru:
            self._cache_lru.remove(x)
        self._cache_lru.append(x)
        self._cache[x] = wha
        self._real[str(x)] = wha
        self.clean_lru()

    def __len__( self ):
        return len(self._real)

    def __contains__( self, x ):
        return self.get(x) is not None
    
    def __delitem__( self, x ):
        if x in self._cache:
            del self._cache[x]
        if str(x) in self._real:
            del self._real[str(x)]
        if x in self._cache_lru:
            self._cache_lru.remove( x )
        
    def close( self ):
        self.sync()
        self._real.close()
        self._real = None

    def __del__( self ):
        if self._real is not None and not isinstance(self._real,dict):
            self.close()

class literal_processor:
    def __init__( self, part, handon, decode, unpack=True ):
        self.part = part
        self.handon = handon
        self.unpack = unpack
        self.decode = decode
    
    def __call__( self, what, tok, toklen ):
        d = tok
        if self.unpack and not what.startswith('BINARY'):
            enc = self.part.encoding
            if enc is not None:
                if enc == 'BASE64':
                    d = d.decode( 'base64' )
                elif enc == 'QUOTED-PRINTABLE':
                    d = d.decode( 'quopri' )
        if self.decode:
            cs = 'us-ascii'
            if 'CHARSET' in self.part.params:
                cs = self.part.params['CHARSET']
            if cs is not None:
                cs = cs.lower()
            d = d.decode( cs, 'ignore' )
        self.handon( d, len(tok), toklen )

class cache_wrapper:
    blocksize = 25
    summary_data = ['MODSEQ','FLAGS','BODYSTRUCTURE','ENVELOPE','LASTMODSEQ']
    def __init__(self, mbox, real):
        self._real = real
        self._mbox = mbox

    def __getitem__(self, k):
        uid,what = k
        block,key = self.transform(uid,what)
        data = self._real[(block,key)]
        actual = data[uid][what]
        if what == 'FLAGS':
            return self._mbox.flags_decode(actual)

    def transform(self,uid,what):
        block = long(uid / self.blocksize) * self.blocksize
        key = what
        if key in self.summary_data:
            key = 'SUMMARY'
        return block,key

    def get(self,k,default=None):
        uid,what = k
        block,key = self.transform(uid,what)
        data = self._real.get((block,key),None)
        if data is None:
            return default
        actual = data.get(uid,{}).get(what,None)
        if actual is None:
            return default
        if what=='FLAGS':
            return self._mbox.flags_decode(actual)
        return actual

    def __setitem__(self,k,value):
        uid,what = k
        block,key = self.transform(uid,what)
        data = self._real.get((block,key),{})
        if what=='FLAGS':
            value = self._mbox.flags_encode(value)
        data.setdefault(uid,{})[what] = value
        self._real[(block,key)] = data

    def items(self,uid=None):
        mk = None
        if uid is not None:
            mk = long(uid / self.blocksize) * self.blocksize
        for block,key,data in self._real.items(mk):
            for muid,value in data.items():
                if uid is not None and muid!=uid:
                    continue
                if key=='SUMMARY':
                    for kk in self.summary_data:
                        vv = value.get(kk,None)
                        if vv is not None:
                            if kk=='FLAGS':
                                yield muid,kk,self._mbox.flags_decode(vv)
                            else:
                                yield muid,kk,vv
                else:
                    yield muid,key,value[key]
        
    def __delitem__(self,k):
        uid,what = k
        block,key = self.transform(uid,what)
        data = self._real.get((block,key),{})
        uid_data = data.get(uid,{})
        del uid_data[what]
        if uid_data:
            data[uid] = uid_data
        else:
            del data[uid]
        if data:
            self._real[(block,key)] = data
        else:
            del self._real[(block,key)]

    def __contains__(self,k):
        return self.get(k,None) is not None

    def sync(self):
        self._real.sync()
    def close(self):
        self._real.close()

class mailbox2:
    def __init__( self, imap, path, mi ):
        self._imap = imap
        self._mi = mi
        self._path = path
        self._freeze = False
        self._pending = {}
        self._pending_codes = {}
        self._rights = None
        self._messages = weakref.WeakValueDictionary()#{}
        self._messages_cache = {}
        self._messages_lru = []
        self._uid_validity = None
        self._uid_next = None
        self._exists = None
        self._last_exists = None
        self._highest_modseq = None
        self._flags = None
        self._perm_flags = None
        self._witnessed_expunges = 0
        self._state = None
        self._notifies = []
        self._last_notify = time.time()
        self._mods = []
        self._waiting = 0
        self._lrq = 0
        self._priming = False
        self._resync = None
        self._last_prod = None
        self._condstore_real = None
        self._pretend_modseq = None
        self._last_modseq_key = 'LASTMODTIME'
        self._pull_multiplier = 2
        self._recent = 0
        self._seqno_search = []
        self.cachedir = None
        if self._imap.cache_root is not None:
            self.cachedir = os.path.join( self._imap.cache_root, 'pfx' + self._path )
            if not os.path.exists( self.cachedir ):
                os.makedirs( self.cachedir )
        self.cache = infotrope.cache.dummy_double()
        self.cache_real = {}
        self.cache_persist = False
        self.cache_start()
        self.seqno_cache = infotrope.cache.dummy()
        self.seqno_cache_real = {}
        self.seqno_cache_persist = False
        self.seqno_cache_start()
        self.detail_cache = infotrope.cache.dummy()
        self.detail_cache_persist = False
        self.detail_cache_start()
        self.detail_restore()
        self.mid_cache = infotrope.cache.dummy()
        self.mid_cache_persist = False
        self.mid_cache_start()
        self._prefetches = []
        self.proxy_uri_stub = None
        self._immediate_processors = weakref.WeakValueDictionary()
        self.__have_idle = self._imap.have_capability('IDLE')
        #self.uidvalidity()

    def register_literal( self, key, thing ):
        self._immediate_processors[key] = thing
    
    def fetch_literal_processor( self, key, token, token_length ):
        tmp = self._immediate_processors.get(key,None)
        if tmp is None:
            return
        if len(token) == token_length:
            del self._immediate_processors[key]
        tmp( key, token, token_length )
    
    def condstore_enabled( self ):
        if self._condstore_real is None:
            self.uidvalidity()
        return self._condstore_real

    def esearch_pull_calc( self, seqno, esearch ):
        ( s, d ) = self.esearch_pull_calc_real( seqno, esearch )
        d += s
        if s == 1:
            d -= 1
        if d > self._exists:
            d = '*'
        return s, str(d)
    
    def esearch_pull_calc_real( self, seqno, esearch ):
        if esearch and self._imap.have_capability('ESEARCH'):
            self._imap.log( "Using ESEARCH expansion for block %d" % seqno )
            u0 = 1
            un = None
            s0 = 1
            sn = None
            start = seqno
            for x in range( start-max_pull, -1, -max_pull ):
                if x in self.seqno_cache:
                    u0 = self.seqno_cache[x][-1] + 1
                    s0 = x + len( self.seqno_cache[x] )
                    break
            for x in range( start+max_pull, self._exists+1, max_pull ):
                if x in self.seqno_cache:
                    un = self.seqno_cache[x][0]
                    sn = x
                    break
            if un is None:
                sn = self._last_exists
                un = self._uid_next - 1
                s = ( self._exists / max_pull ) * max_pull
                for x in range( s, s0, -max_pull ):
                    if x in self.seqno_cache:
                        un = self.seqno_cache[x][0]
                        sn = x
                        break
            if un <= u0 or sn == s0:
                if seqno==0:
                    seqno = 1
                return seqno, 4*max_pull - 1
            cn = sn - s0
            rn = un - u0
            self._imap.log( "Adapting for range %d (%d) to %d (%d), across %d (%d)" % ( u0, s0, un, sn, rn, cn ) )
            holes = rn-cn
            if holes < 0:
                self._imap.log( "Holes is negative? UIDNEXT is buggy." )
                self._imap.alert( "Holes is negative? UIDNEXT is buggy." )
                import sys
                sys.exit()
                holes = 0
            max_num = 2*(holes+1)
            if max_num > cn:
                max_num = cn
            self._imap.log( "Max is %d, with range %d, count %d and holes %d." % ( max_num, rn, cn, holes ) )
            foo = ( rn * max_pull * 3 ) / max_num
            self._imap.log( "Foo is %s" % `foo` )
            to = ( int( foo ) / max_pull ) * max_pull - 1
            self._imap.log( "To is %s" % `to` )
            #if to >= ( max_pull * 15 ):
            #    to = max_pull * 15 - 1
            fr = ( s0 / max_pull ) * max_pull
            self._imap.log( "Initial start is %d" % fr )
            while fr + to < seqno:
                fr += max_pull
            self._imap.log( "Post coverage check, now %d" % fr )
            if fr==0:
                fr = 1
            return fr, to
        if seqno==0:
            seqno = 1
        return seqno, max_pull * 3 - 1

    def logical_start_position( self ):
        self.uidvalidity()
        return len(self) - self._recent

    def have_rights( self, what ):
        return self._mi.have_rights( what )

    def mbox_info( self ):
        return self._mi

    def register_notify( self, who ):
        self._notifies.append( weakref.ref( who ) )

    def delete_notify( self, who ):
        tmp = self._notifies
        self._notifies = []
        for x in tmp:
            xx = x()
            if xx is not None:
                if xx is not who:
                    self._notifies.append( x )
        
    def notify( self ):
        if self._waiting:
            return False
        if 0==len(self._mods):
            return False
        #tt = time.time()
        #if ( tt - self._last_notify ) < 2:
        #    return 0!=len(self._mods)
        #self._last_notify = tt
        yes = False
        omods = self._mods
        self._mods = []
        for x in self._notifies:
            xx = x()
            if xx is not None:
                yes = True
                xx.notify_change( self, omods )
        return yes

    def detail_save_real( self ):
        try:
            self.detail_cache['uid_validity'] = self._uid_validity
            self.detail_cache['uid_next'] = self._uid_next
            self.detail_cache['last_exists'] = self._last_exists
            self.detail_cache['exists'] = self._exists
            if self._condstore_real:
                self.detail_cache['highest_mod_seq'] = self._highest_modseq
                self.detail_cache['last_modseq_seen'] = self._last_modseq_seen
                self.detail_cache['highwater_uid'] = self._highwater_uid
                self.detail_cache['highwater_modseq'] = self._highwater_modseq
            else:
                self.detail_cache['highest_mod_seq'] = '0'
                self.detail_cache['last_modseq_seen'] = '0'
                self.detail_cache['highwater_uid'] = 0
                self.detail_cache['highwater_modseq'] = '0'
            self.detail_cache['witnessed_expunges'] = self._witnessed_expunges
            self.detail_cache['flags'] = self._flags
            self.detail_cache['permflags'] = self._perm_flags
        except:
            self.detail_cache_start( True )
            self.detail_save_real()
        self.seqno_cache.sync()
        self.cache.sync()
        self.mid_cache.sync()
        self.detail_cache.sync()

    def detail_save( self ):
        pass
        
    def detail_restore( self ):
        try:
            self._uid_validity = self.detail_cache['uid_validity']
            self._uid_next = self.detail_cache['uid_next']
            self._last_exists = self.detail_cache['last_exists']
            self._exists = self.detail_cache['exists']
            self._highest_modseq = self.detail_cache['highest_mod_seq']
            self._last_modseq_seen = self.detail_cache['last_modseq_seen']
            self._witnessed_expunges = self.detail_cache['witnessed_expunges']
            self._flags = self.detail_cache['flags']
            self._perm_flags = self.detail_cache['permflags']
            self._highwater_uid = self.detail_cache['highwater_uid']
            self._highwater_modseq = self.detail_cache['highwater_modseq']
        except:
            self.detail_cache_start( True )
            self._uid_validity = None
            self._uid_next = None
            self._last_exists = None
            self._exists = None
            self._highest_modseq = '0'
            self._last_modseq_seen = '0'
            self._highwater_uid = 0
            self._highwater_modseq = '0'
        
    def gen_cache_start( self, cache, persist, name, reset=False, double=False ):
        if cache is not None:
            try:
                if persist:
                    cache.close();
            except:
                pass
            try:
                cache = None
            except:
                pass
            if double:
                ncache = infotrope.cache.dummy_double()
            else:
                ncache = infotrope.cache.dummy()
            persist = False
        if self._imap.cache_root is not None:
            if reset:
                for x in os.listdir( self.cachedir ):
                    if x.find(name)==0:
                        os.remove( os.path.join( self.cachedir, x ) )
            try:
                if double:                    
                    ncache = infotrope.cache.open_double( os.path.join( self.cachedir, name ), int )
                else:
                    ncache = infotrope.cache.open( os.path.join( self.cachedir, name ) )
                persist = True
            except:
                if reset:
                    if double:
                        ncache = infotrope.cache.dummy_double()
                    else:
                        ncache = infotrope.cache.dummy()
                else:
                    self.gen_cache_start( ncache, persist, name, reset=True, double=double )
        return ( ncache, persist )

    def cache_start( self, reset=False ):
        ( self.cache_real, self.cache_persist ) = self.gen_cache_start( self.cache_real, self.cache_persist, 'cache', reset, double=True )
        self.cache = cache_wrapper(self, self.cache_real)
        
    def detail_cache_start( self, reset=False ):
        ( self.detail_cache, self.detail_cache_persist ) = self.gen_cache_start( self.detail_cache, self.detail_cache_persist, 'detail', reset )

    def seqno_cache_start( self, reset=False ):
        ( self.seqno_cache_real, self.seqno_cache_persist ) = self.gen_cache_start( self.seqno_cache_real, self.seqno_cache_persist, 'seqno', reset )
        self.seqno_cache = seqno_cache_thing( self.seqno_cache_real )

    def mid_cache_start( self, reset=False ):
        ( self.mid_cache, self.mid_cache_persist ) = self.gen_cache_start( self.mid_cache, self.mid_cache_persist, 'mid', reset )

    def server( self ):
        return self._imap
    def path( self ):
        return self._path

    def uri( self ):
        if self.proxy_uri_stub:
            return infotrope.url.URL( self.proxy_uri_stub + ';UIDVALIDITY=' + self._uid_validity )
        return infotrope.url.URL( str(self._imap.mbox_info(self._path).uri())+';UIDVALIDITY=' + self._uid_validity )

    def master_uri(self):
        return self.uri()
        
    def copy( self, msg, topath ):
        if isinstance(msg,message):
            uids = [int(msg.uid())]
        elif isinstance(msg,int):
            uids = [msg]
        elif isinstance(msg,list):
            uids = []
            for m in msg:
                if isinstance(m,message):
                    uids.append(int(m.uid()))
                elif isinstance(m,int):
                    uids.append(m)
                else:
                    uids.append(int(m))
        else:
            uids = [int(msg)]
        self.uidvalidity()
        t,r,s = self._imap.send( 'UID COPY', ','.join(self._make_msg_set(uids)), astring(topath), mbox=self.path() )
        if r is None:
            t,r,s = self._imap.wait( t )
        if r.lower()!='ok':
            raise infotrope.base.connection.exception(s)
        if isinstance( s[0], list ):
            if s[0][0].upper()=='COPYUID' and self._imap.have_capability('UIDPLUS'):
                dst_m = self._imap.mailbox( topath, open=False )
                if s[0][1]==dst_m._uid_validity:
                    dst_uids = self._imap.decompose_set(s[0][3],nosort=True)
                    if len(uids)!=len(dst_uids):
                        print "COPYUID Length Mismatch!"
                        return
                    uids = self._imap.decompose_set(s[0][2],nosort=True)
                    for i in range(len(uids)):
                        self.copy_cache( uids[i], dst_m, dst_uids[i] )

    def copy_cache(self, uid, dst_m, dst_uid):
        for u,k,v in self.cache.items(uid):
            if 'MODSEQ' in k:
                continue
            if k not in never_cache:
                dst_m.set_cache(dst_uid, k, v)
        dst_m.sync()

    def have_cached(self, uid, item):
        return (uid,item) in self.cache

    def copy_cache_old( self, uid, dst_m, dst_uid ):
        items = ['ENVELOPE','BODYSTRUCTURE','INTERNALDATE','RFC822.SIZE','RFC822', 'RFC822.HEADER', 'RFC822.TEXT', 'BODY' ]
        items += self[uid].parts().all_parts()
        for x in items:
            item = self.check_in_cache( uid, x )
            if item is not None:
                dst_m.set_cache( dst_uid, item, self.get_from_cache( uid, item ) )
        
    def seqno( self, seqno, testonly=False ):
        ''' Translate a sequence number for this mailbox into a UID. '''
        if self._imap.logged_out:
            return None
        self.uidvalidity()
        if seqno > self._exists:
            return None
        if seqno <= 0:
            return None
        start = ( seqno / max_pull ) * max_pull
        block = self.seqno_cache.get(start,[])
        if len(block)<=(seqno-start):
            if testonly:
                return None
            self.seqno_prime( seqno )
            block = self.seqno_cache.get(start,[])
        if len(block)<=(seqno-start):
            self._imap.log("Block at %d (length %d) too short to have seqno %d" % ( start, len(block), seqno ))
            return None
        return block[seqno-start]

    def check_seqno( self, seqno ):
        return self.seqno( seqno, testonly=True )

    def seqno_remove( self, seqno ):
        ''' Find and remove a specific seqno, rearranging seqno map to suit. '''
        # self.uidvalidity() Don't call this, we're definately selected.
        self._imap.log("Removing seqno %d" % (seqno))
        start = ( seqno / max_pull ) * max_pull
        block = self.seqno_cache.get(start)
        if block:
            if len(block) > (seqno - start):
                block = block[:]
                del block[seqno - start]
                self.seqno_cache[start] = block
                self._imap.log("Removed seqno")
        for chunk in range(start, self._exists+max_pull, max_pull):
            block = self.seqno_cache.get(chunk)
            if block:
                block = block[:]
                if chunk > start:
                    self._imap.log("Trim block %d" % (chunk))
                    block = block[1:]
                nextblock = self.seqno_cache.get(chunk+max_pull)
                if nextblock:
                    block.append(nextblock[0])
                    self._imap.log("Append from next for %d" % (chunk))
                self.seqno_cache[chunk] = block

    def seqno_add( self, seqno, uid ):
        self._imap.log("Adding seqno %d as %d" % (seqno, uid))
        start = ( seqno / max_pull ) * max_pull
        if start in self.seqno_cache:
            if len( self.seqno_cache[start] ) == ( seqno - start ):
                tmp = self.seqno_cache[start]
                tmp.append( uid )
                self.seqno_cache[start] = tmp
        elif start == seqno:
            self.seqno_cache[start] = [uid]
        elif seqno == 1:
            self.seqno_cache[0] = [0,uid]
    
    def seqno_prime( self, seqno, then=None ):
        self.uidvalidity()
        self.seqno_prime_real( seqno, then=then )

    def seqno_prime_real( self, seqno, new_exists=None, then=None ):
        try:
            self._imap.log("SEARCH for %s" % ( seqno ))
            search_override = new_exists
            self._seqno_search = [ x for x in self._seqno_search if x.response is None ]
            for x in self._seqno_search:
                if x.seqno_start <= seqno <= x.seqno_end:
                    self._imap.log( "SEARCH in progress for %d (%s)" % ( seqno, x ) )
                    if then is None:
                        self._imap.wait( x )
                    else:
                        x.oncomplete( then )
                    return
            use_esearch = False
            if new_exists is None:
                use_esearch = True
                search_override = self._exists
            start = ( seqno / max_pull ) * max_pull
            if start in self.seqno_cache:
                if len(self.seqno_cache[start])==max_pull:
                    return
                elif len(self.seqno_cache[start])+start-1==self._exists:
                    return
                else:
                    self._imap.log( "Fill search for %d, currently %d long." % ( start, len(self.seqno_cache[start]) ) )
                    s = start + len(self.seqno_cache[start])
                    c = ['UID SEARCH']
                    if self._imap.have_capability('ESEARCH'):
                        c += ['RETURN', ['ALL']]
                    end = max_pull - len(self.seqno_cache[start]) - 1 + s
                    if end >= self._exists:
                        end = '*'
                    c.append( '%d:%s' % ( s, end ) )
                    t,r,sq = self._imap.send( c, mbox=self.path() )
                    t.seqno_start = s
                    t.seqno_end = max_pull - len(self.seqno_cache[start]) - 1 + s
                    t.search_override = search_override
                    t.search_base = s
                    t.search_mode = 'seqno_prime'
                    self._seqno_search.append( t )
                    self._imap.register( t, self )
                    if then is not None:
                        if then:
                            t.oncomplete( then )
                    else:
                        self._imap.wait( t )
                    return
            else:
                c = ['UID SEARCH']
                if self._imap.have_capability('ESEARCH'):
                    c += ['RETURN', ['ALL']]
                ( a, b ) = self.esearch_pull_calc( start, use_esearch )
                c.append( '%d:%s' % ( a, b ) )
                t,r,s = self._imap.send( c, mbox=self.path() )
                t.seqno_start = a
                t.seqno_end = b
                t.search_base = a
                if t.search_base == 1:
                    t.search_base = 0
                t.search_mode = 'seqno_prime'
                t.search_override = search_override
                self._seqno_search.append( t )
                self._imap.register( t, self )
                if then is not None:
                    if then:
                        t.oncomplete( then )
                else:
                    self._imap.wait( t )
                return
        finally:
            pass

    def uidvalidity( self ):
        self.uidvalidity_real()
        if self._mods:
            self.notify()
        return self._uid_validity

    def highest_modseq( self ):
        self.uidvalidity_real()
        return self._highest_modseq

    def _handle_flags( self, r, t, s ):
        self._flags = s
        return r,t,s

    def flag_available( self, w, permonly=True ):
        self.uidvalidity()
        w = w.lower()
        if w in self._perm_flags:
            return True
        if self._create_flags:
            return True
        if not permonly:
            if w in self._flags:
                return True
        return False

    def permflags( self ):
        self.uidvalidity()
        return [x for x in self._perm_flags if x != '' ]

    def newflags( self ):
        return self._create_flags

    def set_permflags( self, pf ):
        self._create_flags = False
        stuff = [x.lower() for x in pf]
        if self._perm_flags is not None:
            for x in range(len(self._perm_flags)):
                if self._perm_flags[x] not in stuff:
                    self._perm_flags[x] = ''
        else:
            self._perm_flags = []
        for x in stuff:
            if x == '\\*':
                self._create_flags = True
                continue
            if x in self._perm_flags:
                continue
            self._perm_flags.append(x)

    def flag_encode( self, stuff ):
        try:
            i = self._perm_flags.index(stuff)
            return 1<<i
        except ValueError:
            if stuff[0]=='\\':
                return 0
            self._perm_flags.append(stuff)
            return self.flag_encode(stuff)

    def flags_encode( self, stuff ):
        f = 0
        for flag in stuff:
            f |= self.flag_encode(flag)
        return f

    def flags_decode( self, data ):
        flags = []
        for i in range(len(self._perm_flags)):
            if data&(1<<i):
                flags.append(self._perm_flags[i])
        return flags

    def recent( self, foo ):
        self._recent = int(foo)

    def sync( self, *args ):
        self._imap.log( "Sync mailbox." )
        self.detail_save_real()
    
    def uidvalidity_real( self ):
        async = True
        if self._perm_flags is None:
            async = False
        if not self._imap.set_cwm( self._path, self, async=async ):
            if self.__have_idle:
                return
            if self._last_prod is None or (time.time()-self._last_prod) > 60:
                self._last_prod = time.time()
                t,r,s = self._imap.send( 'NOOP', mbox=self.path() )
            return
        self._imap.log('Performing reselection, async is %s' % `async`)
        if async:
            return
        self.mailbox_reselected(None)

    def qresync_data(self):
        testing = False
        if not self._uid_validity or not self._highest_modseq or not self._exists:
            if not testing:
                return None
        self._last_modseq_key = 'LASTMODSEQ'
        self._condstore_real = True
        mhms = self._highest_modseq
        if self._last_modseq_seen != '0':
            mhms = self._last_modseq_seen
        high_block = int(self._exists / max_pull) * max_pull
        last_block = self.seqno_cache.get(high_block)
        max_uid = 0
        if last_block:
            max_uid = last_block[-1]
        else:
            if not testing:
                return None
        min_uid = 1
        block = self.seqno_cache.get(0)
        if block and len(block) > 1:
            min_uid = block[1]
        if min_uid == max_uid:
            uids = '%d' % min_uid
        else:
            uids = '%d:%d' % (min_uid, max_uid)
        basic_qresync = [self._uid_validity, mhms, uids]
        self._highwater_uid = max_uid
        known_seqs = []
        known_uids = []
        for x in range(high_block-max_pull,max(-max_pull,high_block - (max_pull*11)),-max_pull):
            block = self.seqno_cache.get(x)
            if not block:
                continue
            offset = 1
            if x:
                offset = 0
            else:
                x = 1
            known_seqs.append(str(x))
            known_uids.append(str(block[offset]))
        known_seqs.reverse()
        known_uids.reverse()
        if last_block:
            offset = 1
            if high_block:
                offset = 0
                known_uids += self._make_msg_set(last_block.tolist(), True)
            else:
                known_uids += self._make_msg_set(last_block.tolist()[1:], True)
            u0 = last_block[offset]
            u1 = last_block[-1]
            if u0 == u1:
                known_seqs.append('%d'%(high_block+offset))
            else:
                known_seqs.append('%d:%d' % (high_block+offset,high_block+len(last_block)-1))
        basic_qresync.append([','.join(known_seqs),','.join(known_uids)])
        #print "Would use",`basic_qresync`
        return basic_qresync
        
    def mailbox_reselected( self, tag ):
        really_changed = True
        tt = time.time()
        if really_changed:
            if 'RECENT' in self._imap.mailbox_info:
                self._recent = int(self._imap.mailbox_info['RECENT'])
            self._prefetches = []
            if 'PERMANENTFLAGS' in self._imap.mailbox_info:
                self.set_permflags( self._imap.mailbox_info['PERMANENTFLAGS'] )
            else:
                self._perm_flags = []
        uidnext = None
        if 'UIDNEXT' in self._imap.mailbox_info: # Annoyingly, some versions of MDaemon claim IMAP4rev1, but don't provide UIDNEXT.
            uidnext = int(self._imap.mailbox_info['UIDNEXT'])
        else:
            self._imap.log( "*** NO UIDNEXT *** ALGORITHM FAILURE IMMINENT ***" )
        exists = int(self._imap.mailbox_info['EXISTS'])
        oldexists = self._exists
        if 'UIDVALIDITY' not in self._imap.mailbox_info:
            self._imap.mailbox_info['UIDVALIDITY'] = None
            if really_changed:
                self._imap.log('Mailbox has no persistent UIDs')
                self._messages = weakref.WeakValueDictionary()#{}
                self._messages_cache = {}
                self._messages_lru = []
                self.detail_cache_start( True )
                self.cache_start( True )
                self.seqno_cache_start( True )
                self.mid_cache_start( True )
                really_changed = False
                self._uid_validity = self._imap.mailbox_info['UIDVALIDITY']
                if self._uid_validity is None:
                    self._uid_validity = -1
                self._uid_next = uidnext
                self._exists = exists
                self._last_exists = self._exists
                self.detail_save()
        if self._imap.mailbox_info['UIDVALIDITY']!=self._uid_validity or exists==0:
            self._imap.log('Mailbox UIDVALIDITY has changed')
            self._messages = weakref.WeakValueDictionary()#{}
            self._messages_cache = {}
            self._messages_lru = []
            self.detail_cache_start( True )
            self.cache_start( True )
            self.seqno_cache_start( True )
            self.mid_cache_start( True )
            self._last_prod = tt # No point prodding, this shouldn't happen unless we have really_changed, but you never know...
            really_changed = False # No point resyncing.
            self._uid_validity = self._imap.mailbox_info['UIDVALIDITY']
            if self._uid_validity is None:
                self._uid_validity = -1
            self._uid_next = uidnext
            self._exists = exists
            self._last_exists = self._exists
            self.detail_save()
            if exists!=0:
                self._mods.append(0)
        if tag and tag.select_qresync:
            self._last_modseq_seen = self._imap.mailbox_info['HIGHESTMODSEQ']
            self._highest_modseq = self._last_modseq_seen
            self._highwater_modseq = self._last_modseq_seen
        elif self._imap.have_capability('CONDSTORE') and 'HIGHESTMODSEQ' in self._imap.mailbox_info:
            self._imap.log('Checking HIGHESTMODSEQ')
            hms = long(self._imap.mailbox_info['HIGHESTMODSEQ'])
            mhms = long(self._highest_modseq)
            mlms = long(self._last_modseq_seen)
            self._condstore_real = True
            self._last_modseq_key = 'LASTMODSEQ'
            if hms > mlms: # Otherwise, conceptually, it's the same select.
                self._imap.log('New events')
                self._highest_modseq = self._imap.mailbox_info['HIGHESTMODSEQ']
                if oldexists and exists and mlms:
                    s = min(oldexists,exists)
                    bl = (s / max_pull) * max_pull
                    uid = None
                    while True:
                        block = self.seqno_cache.get(bl)
                        if block is not None:
                            uid = block[-1]
                            break
                        bl -= max_pull
                    self._highwater_uid = uid
                    self._highwater_modseq = self._highest_modseq
                    self._imap.log('Performing refresh')
                    self.fetch_submit_cmd( '1:%d' % uid, [], [('FLAGS','MODSEQ'),self._last_modseq_seen],highwater=True)
        elif really_changed:
            self._highest_modseq = '%020d' % long(tt*100)
            self._condstore_real = False
            self._last_modseq_key = 'LASTMODTIME'
        seqno_last = ( exists / max_pull ) * max_pull
        seqno_last_len = exists - seqno_last + 1
        if seqno_last in self.seqno_cache:
            if len(self.seqno_cache[seqno_last])>seqno_last_len:
                self._imap.log( "Truncating seqno cache." )
                self.seqno_cache[seqno_last] = self.seqno_cache[seqno_last][:seqno_last_len]
        for x in range(seqno_last+max_pull, (self._exists / max_pull + 1) * max_pull ):
            if x in self.seqno_cache:
                self._imap.log( "Erasing seqno cache entry %d" % x )
                del self.seqno_cache[x]
        self._uid_validity = self._imap.mailbox_info['UIDVALIDITY']
        if self._uid_validity is None:
            self._uid_validity = -1
        if not really_changed: # UID mappings must still be valid.
            if self._imap.have_capability('IDLE'):
                return
            if (tt-self._last_prod) > 60:
                self._last_prod = tt
                t,r,s = self._imap.send( 'NOOP', mbox=self.path() )
            return
        self._last_prod = tt # No point prodding for a bit.
        if really_changed:
            self._mods.append(0)
            self.resync( uidnext )
        self._uid_next = uidnext
        self._exists = exists
        self._last_exists = self._exists
        self._witnessed_expunges = 0
        self.detail_save()

    def _handle_vanished( self, t, r, uids ):
        for uid in uids:
            self.expunge_message(uid)
        self.detail_save()
        self.notify()
        return t,r,uids

    def _handle_expunge( self, t, r, n ):
        seq = n
        self._exists -= 1
        block = (seq*max_pull)/max_pull
        uid = None
        if block in self.seqno_cache:
            uid = self.seqno_cache[block][seq-block]
        self.expunge_message( uid, seq )
        self.detail_save()
        self.notify()
        return t,r,n

    def expunge_message(self, uid, seqno=None):
        self._mods.append(uid)
        if seqno is None:
            seqno = self.uid(uid, nocheck=True)
        if uid is not None:
            if uid in self._messages:
                del self._messages[uid]
            if uid in self._messages_lru:
                self._messages_lru.remove(uid)
            if uid in self._messages_cache:
                del self._messages_cache[uid]
        if seqno:
            self.seqno_remove(seqno)
        self._witnessed_expunges += 1
        self._exists -= 1

    def expunge( self, uids=None ):
        if uids is not None:
            if not self._imap.have_capability('UIDPLUS'):
                return
        self.uidvalidity()
        self.do_pending()
        self._imap.register( '*', self )
        try:
            self._waiting += 1
            if uids is not None:
                set = self._make_msg_set( uids )
                t,r,s = self._imap.send( 'UID EXPUNGE', ','.join(set), mbox=self.path() )
            else:
                t,r,s = self._imap.send( 'EXPUNGE', mbox=self.path() )
            if r is None:
                t,r,s = self._imap.wait( t )
            if r.lower()!='ok':
                raise infotrope.base.connection.exception( s )
        finally:
            self._waiting -= 1
            self.notify()
    
    def _handle_exists( self, t, r, n ):
        self._prime_cache = []
        self._prime_last_hunk = None
        self._prime_last_seqnos = []
        self._prime_uid_map_cache = {}
        if self._imap.state == 'select':
            return t,r,n
        self._exists = n
        self.detail_save()
        self._mods.append( 0 )
        self.notify()
        return t,r,n
    
    def resync( self, uidnext ):
        have_uidnext = False
        if uidnext is not None:
            have_uidnext = True
        exists = int(self._imap.mailbox_info['EXISTS'])
        if have_uidnext:
            if uidnext==self._uid_next and exists==self._exists:
                self._imap.log( "Resync: No change." )
                return
            else:
                if self._uid_next is None or self._last_exists is None:
                    self._imap.log( "Resync: New select." )
                    return
                if (self._uid_next-uidnext)==(self._last_exists-exists+self._witnessed_expunges):
                    self._imap.log( "Resync: Advance in sync." )
                    return
        self._uid_next = uidnext
        self._exists = exists
        self._prime_cache = []
        self._prime_last_hunk = None
        self._prime_last_seqnos = []
        self._prime_uid_map_cache = {}
        # Try looking at our last block.
        tgt_seq = min(self._exists,exists)
        last_block = ( tgt_seq / max_pull ) * max_pull
        for x in range( last_block+max_pull, (max(self._exists,exists)/max_pull)*max_pull, max_pull ):
            if x in self.seqno_cache:
                del self.seqno_cache[x]
        if last_block in self.seqno_cache:
            last_uid = self.seqno_cache[ last_block ][ 0 ]
            del self.seqno_cache[last_block]
            self.seqno_prime_real( tgt_seq, exists )
            new_uid = self.seqno_cache[ last_block ][ 0 ]
            if new_uid==last_uid:
                self._imap.log( "Resync: Last block has all changes." )
                return
        self.real_resync( uidnext, last_block )
            
    def real_resync( self, uidnext, last_block ):
        self._imap.log( "Resync: Second stage resync." )
        exists = int(self._imap.mailbox_info['EXISTS'])
        sr = []
        for x in range( last_block - max_pull, -1, -max_pull ):
            if x in self.seqno_cache:
                if x==0:
                    sr.append(1)
                else:
                    sr.append(x)
            if len(sr) > max_pull_resync:
                if self.resync_search( sr, last_block ):
                    sr = []
                    break
                else:
                    sr = []
        if len(sr)!=0:
            self.resync_search( sr, last_block )        

    def resync_search( self, sr, last_block ):
        self._resync = []
        t,r,s = self._imap.send( 'UID SEARCH', ','.join( [str(x) for x in sr] ), mbox=self.path() ) # No gain in ESEARCH.
        self._imap.register( t, self )
        t.search_mode = 'resync'
        self._imap.wait( t )
        tmp = t.resync_data
        tmp.sort() # Order not mentioned in 3501.
        tmp.reverse() # We need it in reverse order.
        for x in tmp:
            block = (sr[0]/max_pull) * max_pull
            which = 0
            if block==0:
                which = 1
            if self.seqno_cache[block][which] != x:
                del self.seqno_cache[block]
                del sr[0]
            else:
                self._imap.log( "Resync: Found matching block at %d" % sr[0] )
                del self.seqno_cache[block]
                del sr[0]
                return True
        self._imap.log( "Resync: Need further search." )
        return False

    def uid( self, u, closest=False, nocheck=False ):
        """
        Given a UID, find the corresponding sequence number.
        closest is a flag allowing a (GUI) client to find the closest existing message.
        removal says to find a seqno before the UID.
        """
        if not nocheck:
            self.uidvalidity()
        for chk in self.seqno_cache.get_lru():
            block = self.seqno_cache.get(chk)
            if block is None:
                continue
            try:
                #self._imap.log("Looking for %s in block %s len %d - %s" % (`u`,`chk`,len(block),`block`))
                return chk + block.index(u)
            except ValueError, e:
                if block[0] < u and block[-1] > u:
                    #self._imap.log("Check is %d, Block range %d to %d includes %s but missing." % (chk, block[0], block[-1], `u`))
                    #self._imap.log("Block is %s" % ( `block` ))
                    #self._imap.log("Exception is %s" % (str(e)))
                    if closest:
                        break
                    return None
        seqno0 = 1
        seqnon = self._exists
        self._imap.log("Searching for UID %s" % ( `u` ))
        while True:
            uid0 = self.seqno( seqno0 )
            if uid0 is None:
                self._imap.log("Seqno %d does not exist, aborting" % (seqno0))
                return None
            uidn = self.seqno( seqnon )
            self._imap.log("%s => %s, %s => %s" % (`seqno0`,`uid0`,`seqnon`,`uidn`))
            while uidn is None:
                uidn = self.seqno( self._exists )
                self._imap.log("Now got %s" % (`uidn`))
            if uid0 == u:
                return seqno0
            if uidn == u:
                return seqnon
            if uid0 == uidn:
                if closest:
                    return seqno0
                return None
            if u<uid0:
                if closest:
                    return seqno0
                return None
            if u>uidn:
                if closest:
                    return seqnon
                return None
            cseq = seqno0 + int( ( u - uid0 ) * ( 1.0 * ( seqnon - seqno0 ) ) / ( uidn - uid0 ) )
            cuid = self.seqno( cseq )
            if cuid==u:
                return cseq
            if cuid > u:
                seqnon = cseq - 1
            else:
                seqno0 = cseq + 1
    
    def get_message( self, uid ):
        try:
            m = self._messages[uid]
            self.update_cache_message( uid, m )
            return m
        except:
            pass
        self.uidvalidity()
        if self.uid( uid ) is None:
            raise infotrope.base.connection.exception("Message %d does not exist." % uid)
        return self.create_insert_message( uid )
    
    def update_cache_message( self, uid, msg ):
        if uid in self._messages_lru:
            self._messages_lru.remove( uid )
        self._messages_lru.append( uid )
        self._messages_cache[uid] = msg

    def cleanup( self ):
        if len(self._messages_lru) == 0:
            self._messages_cache = {}
            return
        minlength = 10
        if len(self._messages_cache) <= minlength:
            return
        excess = len(self._messages_cache) - minlength
        trim = 1 + excess / 4
        for x in self._messages_lru[:trim]:
            if x in self._messages_cache:
                del self._messages_cache[x]
        self._messages_lru = self._messages_lru[trim:]
        
    def create_insert_message( self, uid ):
        m = message( uid, self )
        self._messages[uid] = m
        self.update_cache_message( uid, m )
        return m

    def _handle_search( self, t, r, s ):
        import array
        if t.search_mode == 'seqno_prime':
            start = ( t.search_base / max_pull ) * max_pull
            if start == t.search_base:
                self._imap.log( "Incoming search is CREATE" )
                if start == 0:
                    s = array.array('L',[0] + s)
            else:
                self._imap.log( "Incoming search is FILL" )
                s = self.seqno_cache[start] + array.array('L',s)
            self._imap.log( "Length is now %d" % len(s) )
            for x in range(start,start+len(s),max_pull):
                self._imap.log( "Offset %d, putting %d UIDs" % ( x, len(s[x-start:x-start+max_pull]) ) )
                self.seqno_cache[x] = array.array('L',s[x-start:x-start+max_pull])
            #self.seqno_add( self._search_base + n, x )
            return t,r,s
        elif t.search_mode == 'resync':
            t.resync_data = s
        return t,r,s

    def _handle_esearch( self, t, r, s ):
        if 'ALL' in s:
            self._handle_search( t, r, s['ALL'] )
        return t,r,s

    def rx_fetch( self, t, r, s ):
        notify_this = False
        if 'UID' not in s:
            seq = int(s['seqno'])
            start = ( seq / max_pull ) * max_pull
            if start not in self.seqno_cache:
                return t,r,s
            if len(self.seqno_cache[start]) <= ( seq - start ):
                return t,r,s
            sqa = self.seqno_cache[start]
            uid = sqa[seq-start]
            s['UID'] = "%s" % uid
            notify_this = True
        else:
            uid = int(s['UID'])
        if 'FLAGS' in s:
            s['FLAGS'] = [x.lower() for x in s['FLAGS']]
            if 'MODSEQ' not in s:
                if not self._condstore_real:
                    pretend_modseq = self._pretend_modseq
                    if pretend_modseq is None:
                        pretend_modseq = long(time.time()*100)
                    s['MODSEQ'] = ['%020d' % pretend_modseq]
        if 'MODSEQ' in s:
            s['MODSEQ'] = s['MODSEQ'][0]
            s[self._last_modseq_key] = self._highest_modseq
            if long(self._last_modseq_seen) < long(s['MODSEQ']):
                self._last_modseq_seen = s['MODSEQ']
        try:
            msg = self._messages[uid]
        except:
            msg = self.create_insert_message( uid )
        if msg.need_notify:
            notify_this = True
            msg.need_notify = False
        ss = {}
        rw = 'BODY[HEADER.FIELDS ('
        for k,v in s.items():
            if k.find(rw)==0:
                fields = k[len(rw):-2]
                tok = [ x.upper() for x in fields.split(' ') ]
                tok.sort()
                k = rw + ' '.join( [ x.upper() for x in tok ] ) + ')]'
            ss[k] = v
        s = ss
        for x,y in s.items():
            if self.cachedir and x.startswith('BODY[') and x[5] in '1234567890T':
                # Text or section
                fname = '%d_body_' % (uid) + x[5:-1].replace('.','_')
                open(os.path.join(self.cachedir,fname),'wb').write(y)
            elif self.cachedir and x.startswith('BINARY[') and x[7] in '1234567890T':
                fname = '%d_binary_' % (uid) + x[7:-1].replace('.','_')
                open(os.path.join(self.cachedir,fname),'wb').write(y)
            elif x not in never_cache:
                k = (uid, x)
                try:
                    if x=='FLAGS':
                        y.sort()
                        oldf = self.cache.get(k,None)
                        if oldf is not None:
                            oldf.sort()
                            if oldf != y:
                                notify_this = True
                    elif x=='ANNOTATION':
                        y.reverse()
                        while len(y):
                            annotation = y.pop()
                            if len(y) and isinstance(y[-1],list):
                                annpayload = dict(y.pop())
                                annpayload['MODSEQ-FETCHED'] = s['MODSEQ']
                            else:
                                annpayload['MODSEQ-CHANGED'] = s['MODSEQ']
                            for annkey,anndata in anndata.items():
                                k = '%s::%s\0%s\0%s' % ( str(uid), 'ANNOTATION', annotation, annkey )
                                try:
                                    if k in self.cache:
                                        oldata = self.cache[k]
                                        if oldata != anndata:
                                            notify_this = True
                                except cPickle.UnpicklingError:
                                    del self.cache[k]
                                    notify_this = True
                                self.cache[k] = anndata
                        continue
                    self.cache[k] = y
                except:
                    import sys
                    print "Cache store failed: ", `sys.exc_info()`
                    print "Error was:",sys.exc_info()[1]
                    print "Tried writing",`k`
                    self.cache_start( True )
                    self.cache[k] = y
        msg.feed( s )
        if 'ENVELOPE' in s:
            try:
                self.mid_cache[ msg.envelope().MessageID ] = uid
            except:
                self.mid_cache_start( True )
                self.mid_cache[ msg.envelope().MessageID ] = uid
        if notify_this:
            self._mods.append( uid )
            self.notify()
        return t,r,s

    def check_in_cache( self, uid, what ):
        if isinstance( what, message_part ):
            return self.check_in_cache( uid, 'BODY[%s]' % what.part_id ) or self.check_in_cache( uid, 'BINARY[%s]' % what.part_id )
        try:
            if self.cachedir and what.startswith('BODY[') and what[5] in '123456789T]':
                try:
                    os.stat(os.path.join(self.cachedir,'%d_body_%s' % (uid,what[5:-1].replace('.','_'))))
                    return what
                except OSError:
                    return None
            elif self.cachedir and what.startswith('BINARY[') and what[5] in '123456789T]':
                try:
                    os.stat(os.path.join(self.cachedir,'%d_binary_%s' % (uid,what[5:-1].replace('.','_'))))
                    return what
                except OSError:
                    return None
            else:
                k = (uid, what)
                if k in self.cache:
                    return what
                return None
        except:
            print "CACHE ERROR?"
            raise
            #self.cache_start( True )
            return None

    def get_from_cache( self, uid, what ):
        try:
            if self.cachedir and what.startswith('BODY[') and what[5] in '123456789T]':
                try:
                    open(os.path.join(self.cachedir,'%d_body_%s' % (uid,what[5:-1].replace('.','_')))).read()
                except OSError:
                    return None
            elif self.cachedir and what.startswith('BINARY[') and what[5] in '123456789T]':
                try:
                    return open(os.path.join(self.cachedir,'%d_binary_%s' % (uid,what[5:-1].replace('.','_')))).read()
                except OSError:
                    return None
            else:
                k = (uid, what)
                return self.cache.get(k,None)
        except:
            print "CACHE ERROR?"
            raise
            self.cache_start( True )
            return None

    def set_cache( self, uid, what, data ):
        try:
            if self.cachedir and what.startswith('BODY[') and what[5] in '123456789T]':
                try:
                    open(os.path.join(self.cachedir,'%d_body_%s' % (uid,what[5:-1].replace('.','_')))).write(data)
                except OSError:
                    return None
            elif self.cachedir and what.startswith('BINARY[') and what[5] in '123456789T]':
                try:
                    return open(os.path.join(self.cachedir,'%d_binary_%s' % (uid,what[5:-1].replace('.','_')))).write(data)
                except OSError:
                    return None
            else:
                k = (uid, what)
                self.cache[k]=data
            #print "Set cache key",`k`,"to",`self.cache[k]`
        except:
            print "CACHE ERROR?"
            raise
            self.cache_start( True )

    def __len__(self):
        self.uidvalidity()
        while self._exists is None:
            self._imap.wait_ready()
            self._imap.fetch()
        return self._exists

    def index( self, uid ):
        u = self.uid( uid )
        if u is None:
            raise infotrope.base.connection.exception("Message %d not in mailbox." % uid)
        return u

    def __getitem__(self,key):
        key = int(key)
        return self.get_message( key )

    def fetch( self, msg, what, extend=False, nofetch=False, wait=True ):
        try:
            self._pretend_modseq = long(time.time()*100)
            sequence_start = int(msg._uid)
            sequence_end = sequence_start
            if extend:
                sequence_start -= sequence_start % 25
                sequence_end = sequence_start + 25
                if sequence_start == 0:
                    sequence_start = 1
                self.uid( sequence_start )
                self.uid( sequence_end )
            else:
                self.uid( sequence_start )
            stuff = self.real_fetch( sequence_start, sequence_end, what, nofetch )
            if stuff is not None and wait:
                self.fetch_wait( stuff[0], stuff[1] )
        finally:
            self._pretend_modseq = None

    def convert_sequence_then( self, action, seqs, *args ):
        class seqconverter:
            def __init__( self, mbx, seqs, action, args ):
                self.action = action
                self.args = args
                self.seqs = seqs
                self.uids = []
                self.mbx = mbx

            def step( self, *args  ):
                while len( self.seqs ):
                    s = self.seqs.pop()
                    if s > len(self.mbx):
                        continue
                    if s <= 0:
                        continue
                    start = ( s / max_pull ) * max_pull
                    if start not in self.mbx.seqno_cache:
                        self.seqs.append( s )
                        self.mbx.seqno_prime( s, then=self.step )
                        return
                    if len(self.mbx.seqno_cache[start]) <= (s-start):
                        self.seqs.append( s )
                        self.mbx.seqno_prime( s, then=self.step )
                        return
                    self.uids.append( self.mbx.seqno_cache[start][s-start] )
                self.action( self.uids, *self.args )
        s = seqconverter( self, seqs, action, args )
        s.step()

    def prefetch( self, uidrange, then=None ):
        #print "PREFETCH",`uidrange`
        tag = self.real_fetch( uidrange, None, message.summary )
        #print "FETCH DONE"
        ndone = False
        if tag and then:
            infotrope.core.notify_all( self.server().env, tag[0], then )
        #print "FLUSH"
        self._imap.flush()
        #print "FLUSH"
        if not tag and then:
            then( None, None, None )
        return tag

    def real_fetch( self, sequence_range, sequence_end, what, nofetch=False ):
        rwhat = {}
        mutables = []
        if sequence_end is not None:
            sequence_range = range(sequence_range,sequence_end+1)
        for uid in sequence_range:
            if self.uid( uid ) is not None or uid >= self._uid_next:
                autofeed = {}
                for x in what:
                    from_cache = False
                    condfetch = ''
                    k = (uid, x)
                    try:
                        data = self.cache.get( k )
                        self._imap.log("Cached: %s = %s" % (`k`,`data`))
                        if data is not None:
                            autofeed['UID'] = str(uid)
                            autofeed[x] = data
                            from_cache = True
                            if x=='FLAGS':
                                self._imap.log("Asked to fetch FLAGS. Have %s in cache." % (data))
                                from_cache = False
                                mseq = self.cache.get((uid, self._last_modseq_key),None)
                                self._imap.log("LASTMODSEQ is %s" % (`mseq`))
                                if mseq is not None:
                                    condfetch = long(mseq)
                                    mutables.append( uid )
                                    if condfetch >= long(self._highest_modseq):
                                        self._imap.log("We have newer")
                                        from_cache = True
                                    elif uid <= self._highwater_uid:
                                        self._imap.log("Below high water mark")
                                        if condfetch <= long(self._highwater_modseq):
                                            self.cache[(uid,self._last_modseq_key)] = self._highwater_modseq
                                        from_cache = True
                                elif uid <= self._highwater_uid:
                                    self._imap.log("No modseq, but below highwater")
                                    self.cache[(uid, self._last_modseq_key)] = self._highwater_modseq
                                    from_cache = True
                            elif x.startswith('ANNOTATION'):
                                from_cache = False
                                fk = x[0:x.rindex('\0')] + '\0' + 'MODSEQ-FETCH'
                                nk = x[0:x.rindex('\0')] + '\0' + 'MODSEQ-CHANGED'
                                if fk in self.cache:
                                    fm = long(self.cache[fk])
                                    if fm > long(self._highest_modseq):
                                        from_cache = True
                                        if nk in self.cache:
                                            nm = long(self.cache[fk])
                                            if fm > nm:
                                                from_cache = True
                                            else:
                                                condfetch = min( nm, long(self._highest_modseq) )
                                        else:
                                            condfetch = long(self._highest_modseq)
                        elif self.cachedir and x.startswith('BODY[') and x[5] in '1234567890T':
                            # Text or section
                            fname = '%d_body_' % (uid) + x[5:-1].replace('.','_')
                            try:
                                autofeed[x] = open(os.path.join(self.cachedir,fname),'rb').read()
                                autofeed['UID'] = str(uid)
                                from_cache = True
                            except:
                                pass
                        elif self.cachedir and x.startswith('BINARY[') and x[7] in '1234567890T':
                            # Text or section
                            fname = '%d_binary_' % (uid) + x[7:-1].replace('.','_')
                            try:
                                autofeed[x] = open(os.path.join(self.cachedir,fname),'rb').read()
                                autofeed['UID'] = str(uid)
                                from_cache = True
                            except:
                                pass

                    except:
                        import sys
                        t,v,tr = sys.exc_info()
                        print "Cache read failed: ", `t`, v
                        print "Tried reading",`k`
                        print "From:",`self.cache.__class__.__name__`,`dir(self.cache)`
                        raise v
                        self.cache_start( True )
                    if not from_cache:
                        if uid not in rwhat:
                            rwhat[uid] = {}
                        rwhat[ uid ][ ( x, condfetch ) ] = True
                    if len(autofeed):
                        try:
                            msg = self._messages[uid]
                        except:
                            msg = self.create_insert_message( uid )
                        for afkey in self._immediate_processors:
                            if afkey in autofeed:
                                aftok = autofeed[afkey]
                                self._immediate_processors[afkey]( afkey, aftok, len(aftok) )
                        msg.feed( autofeed )
                        if 'ENVELOPE' in autofeed:
                            try:
                                self.mid_cache[ msg.envelope().MessageID ] = uid
                            except:
                                self.mid_cache_start( True )
                                self.mid_cache[ msg.envelope().MessageID ] = uid
        if len(rwhat)==0:
            return
        if nofetch:
            return
        return self.fetch_send_cmd( rwhat, mutables )
        
    def fetch_send_cmd( self, rwhat, mutables ):
        self._imap.register( '*', self )
        tags = []
        fetching = {}
        for uid,rwhat2 in rwhat.items():
            fpts = []
            condfetch = ''
            for (x,cf) in rwhat2.keys():
                if cf is not None:
                    if condfetch!='':
                        if condfetch > cf:
                            condfetch = cf
                    else:
                        condfetch = cf
                if x.startswith( 'ANNOTATION' ):
                    ann = x.split('\0')
                    x = [ ann[0], ( ann[1], ann[2] ) ]
                    fpts += x
                else:
                    fpts.append( x )
            if not self._condstore_real:
                condfetch = ''
            if fpts is not None:
                fpts = tuple(fpts)
                ff = (fpts,condfetch)
                if ff not in fetching:
                    fetching[ff] = []
                fetching[ff].append(uid)
        for fpts,uids in fetching.items():
            seqs = self._make_msg_set( uids )
            if len(seqs)==0:
                continue
            tags.append( self.fetch_submit_cmd(','.join(seqs), mutables, fpts) )
        return tags,mutables

    def fetch_submit_cmd(self, set, mutables, fpts, highwater=False):
        tag1, x1, x2 = None, None, None
        if fpts[1]!='' and self._condstore_real:
            bits = fpts[0]
            if 'MODSEQ' not in fpts[0]:
                bits = list(fpts[0]) + ['MODSEQ']
            tag1,x1,x2 = self._imap.send( 'UID FETCH', set, bits, ['CHANGEDSINCE', fpts[1]], pipeline=True, mbox=self.path() )
        else:
            bits = fpts[0]
            if self._condstore_real and 'MODSEQ' not in bits and 'FLAGS' in bits:
                bits = list(bits) + ['MODSEQ']
            tag1,x1,x2 = self._imap.send( 'UID FETCH', set, bits, pipeline=True, mbox=self.path() )
        if x1 is not None:
            if x1.lower()!='ok':
                raise infotrope.base.connection.exception(x2)
        self._waiting += 1
        tag1.oncomplete( self.decr_waiters )
        if not highwater and 'FLAGS' in bits:
            tag1.fetched_set = set
            tag1.oncomplete( self.fetch_complete )
        return tag1

    def decr_waiters( self, *args ):
        self._waiting -= 1

    def fetch_complete( self, cmd, *args ):
        for u in self._imap.decompose_set(cmd.fetched_set):
            self.cache[(u, self._last_modseq_key)] = self._highest_modseq

    def fetch_wait( self, tags, mutables ):
        if len(tags) != 0:
            t,r,s = self._imap.wait( tags )
            if r.lower()!='ok':
                raise infotrope.base.connection.exception(s)

    def _make_msg_set( self, uids, nocheck=False ):
        uids.sort()
        seqs = []
        sseq = None
        eseq = None
        for u in uids:
            if sseq is None:
                if self.uid( u, nocheck=nocheck ) is None:
                    continue
                sseq = u
                eseq = u
            elif eseq==(u-1):
                eseq = u
            else:
                seqs.append( (sseq,eseq) )
                if self.uid( u, nocheck=nocheck ) is None:
                    sseq = None
                    eseq = None
                else:
                    sseq = u
                    eseq = u
        if sseq is not None:
            seqs.append( (sseq,eseq) )
        seqs2 = []
        # Phase 2: Can we reduce the byte-count by adding in non-existent UIDs?
        if nocheck:
            seqs2 = seqs
        else:
            for x in seqs:
                if len(seqs2)!=0:
                    hit = True
                    for u in range( seqs2[-1][1]+1, x[0] ):
                        if self.uid( u, nocheck=nocheck ) is not None:
                            hit = False
                            break
                    if hit:
                        nseq = (seqs2[-1][0],x[1])
                        seqs2 = seqs2[0:-1] + [nseq]
                        continue
                seqs2.append( x )
        seqs = None
        # Phase 3: Stringify.
        seqs3 = []
        for x in seqs2:
            if x[0]==x[1]:
                seqs3.append( str(x[0]) )
            else:
                seqs3.append( '%s:%s' % x )
        return seqs3

    def freeze( self ):
        class freezer:
            def __init__( self, mbx ):
                self.mbx = mbx
            def __del__( self ):
                self.mbx.thaw()
        self._freeze = True
        return freezer( self )

    def thaw( self ):
        self._freeze = False
        self.do_pending()

    def do_pending(self):
        tags = []
        if len(self._pending)>0:
            self.uidvalidity()
        for (what,uids) in self._pending.items():
            x = self._pending_codes[what]
            set = self._make_msg_set( uids )
            if len(set)>0:
                t,r,s = self._imap.send( ( 'UID STORE', ','.join(set), x[0], x[1] ), pipeline=True, mbox=self.path() )
                if r is None:
                    t.store_uids = uids
                    t.store_item = x[0]
                    t.store_thing = x[1]
                    tags.append( t )
        self._pending = {}
        if len( tags ) > 0:
            try:
                self._waiting += 1
                tx,r,s = self._imap.wait( tags )
                if r.lower()=='ok':
                    for t in tags:
                        for x in t.store_uids:
                            self._imap.log( ["Signalling",`x`] )
                            seqno = self.uid( x )
                            if seqno is not None: # Assuming the UID exists, anyway.
                                self._imap.log( "UID exists, good." )
                                if t.store_item=='+FLAGS.SILENT':
                                    flags = self.cache.get((x,'FLAGS'),None)
                                    if flags is None:
                                        self._imap.log( "Don't have FLAGS cached, no notification needed." )
                                        continue
                                    for f in t.store_thing:
                                        if f not in flags:
                                            flags.append(f)
                                        if f.lower() not in self._perm_flags:
                                            self._perm_flags.append( f.lower() )
                                    self._imap.log( ["Pushing notification for",`x`,`flags`] )
                                    self.rx_fetch( '', '', {'seqno': seqno,'FLAGS': flags} )
                                elif t.store_item=='-FLAGS.SILENT':
                                    flags = self.cache.get((x,'FLAGS'),None)
                                    if flags is None:
                                        continue
                                    flags = [ f for f in flags if f not in t.store_thing ]
                                    self.rx_fetch( '', '', {'seqno': seqno, 'FLAGS': flags} )
                                elif t.store_item=='ANNOTATION':
                                    self.rx_fetch( '', '', {'seqno': seqno, 'ANNOTATION': t.store_thing } )
            finally:
                self._waiting -= 1
                self._imap.log( ["Now have waiting:", `self._waiting`, `self._mods`, "ready to notify."] )
                self.notify()
        
    def store( self, msg, item, thing ):
        what = `(item, thing)`
        if what not in self._pending_codes:
            self._pending_codes[what] = (item,thing)
        if what not in self._pending:
            self._pending[ what ] = []
        self._pending[ what ].append( int(msg._uid) )
        if not self._freeze:
            self.thaw()

    def find_message_id( self, s ):
        try:
            if self.mid_cache.has_key( s ):
                return self.mid_cache[s]
            angle = s.find('<')
            if angle != -1:
                s = s[angle:]
                end = s.find('>')
                if end >= 0:
                    s = s[:end+1]
                    if self.mid_cache.has_key( s ):
                        return self.mid_cache[s]
            return None
        except:
            self.mid_cache_start( True )
            return None

    def __repr__(self):
        return '<infotrope.imap.mailbox for %s>' % (`self.uri()`)

    def __del__( self ):
        self.thaw()
        self._imap.unselect( self._path )
        self._messages = None
        self.sync()
        if self.cache_persist:
            self.cache.close()
            self.cache = None
        if self.seqno_cache_persist:
            self.seqno_cache.close()
            self.seqno_cache = None
        if self.detail_cache_persist:
            self.detail_cache.close()
            self.detail_cache = None
        if self.mid_cache_persist:
            self.mid_cache.close()
            self.mid_cache = None

class criteria:
    def __init__( self, plusflag=None, minusflag=None, unseen=False ):
        self.plusflag = plusflag
        self.minusflag = minusflag
        self.metadata = self.plusflag is not None or self.minusflag is not None
        self.unseen = True

    def asToks( self ):
        raise "Abstract method asToks called."

    def name( self ):
        raise "Abstract method name called."

    def still_matches( self, msg ):
        if self.plusflag and self.minusflag:
            return msg.flagged( self.plusflag ) and not msg.flagged( self.minusflag )
        elif self.plusflag is not None:
            return msg.flagged( self.plusflag )
        elif self.minusflag is not None:
            return not msg.flagged( self.minusflag )
        else:
            return True

    def check_match( self, msg ):
        """
        Returns one of:
        True - Message definitely matches
        False - Message definitely doesn't match.
        None - Don't know. Either don't yet have summary, or don't have data.
        """
        if msg.flags( nofetch=True ) is None:
            return None
        return self.local_match( msg )

    def local_match( self, msg ):
        return None

class crit_within(criteria):
    def __init__(self, comp, younger):
        criteria.__init__(self)
        self._comp = comp
        self._younger = younger

    def asToks(self):
        if self._younger:
            return ['YOUNGER', self._comp]
        return ['OLDER', self._comp]

    def name(self):
        if self._younger:
            return 'younger than %d seconds' % self._comp
        else:
            return 'older then %d seconds' % self._comp

    def __repr__(self):
        return '<infotrope.imap.crit_within younger=%s comp=%s>' % (`self._younger`,`self._comp`)

    def local_match(self,msg):
        date = msg.internaldate(nofetch=True)
        if date is None:
            return None
        else:
            import time
            t0 = time.time()
            t0 -= self._comp
            return date >= t0 and self._younger

class crit_stringmatch(criteria):
    def __init__( self, comp, s ):
        criteria.__init__( self )
        self._comp = comp.upper()
        self._str = s

    def asToks( self ):
        return [self._comp, astring( self._str.encode('utf-8') )]

    def name( self ):
        return self._comp.lower() + ' includes ' + self._str

    def __repr__( self ):
        return '<infotrope.imap.crit_stringmatch for %s %s>' % ( self._comp, `self._str` )

    def local_match( self, msg ):
        if self._comp in ['TO','CC','FROM','BCC','SUBJECT']:
            if msg.envelope(nofetch=True) is None:
                return None
        if self._comp == 'TO':
            return self._str in msg.envelope().To
        elif self._comp == 'FROM':
            return self._str in msg.envelope().From
        elif self._comp == 'CC':
            return self._str in msg.envelope().CC
        elif self._comp == 'BCC':
            return self._str in msg.envelope().BCC
        elif self._comp == 'SUBJECT':
            return msg.envelope().Subject is not None and self._str in msg.envelope().Subject
        return None

class crit_seqrange(criteria):
    def __init__(self, start, end):
        criteria.__init__(self)
        self._start = start or 1
        self._end = end or '*'

    def asToks(self):
        return [ '%s:%s' % (self._start, self._end) ]

    def name(self):
        return "lies between %s and %s" % (self._start. self._end)

class crit_headermatch(criteria):
    def __init__( self, header, s ):
        criteria.__init__( self )
        self._header = header
        self._str = s

    def asToks( self ):
        return [ 'HEADER', astring(self._header), astring(self._str) ]

    def name( self ):
        return "Header \"%s\" includes %s" % ( self._header, self._str )

class crit_genflag(criteria):
    def __init__( self, plusflag=None, minusflag=None ):
        if plusflag == '\\seen' or minusflag == '\\seen':
            unseen = True
        else:
            unseen = False
        if plusflag and minusflag:
            if minusflag!='\\seen' and plusflag!='\\recent':
                raise "Nope!"
        criteria.__init__( self, plusflag, minusflag, unseen )

    def asToks( self ):
        if self.plusflag and self.minusflag:
            return ['NEW']
        if self.plusflag is not None:
            if self.plusflag[0] == '\\':
                return [self.plusflag[1:].upper()]
            else:
                return ['KEYWORD', self.plusflag]
        else:
            if self.minusflag == '\\recent':
                return ['OLD']
            elif self.minusflag[0] == '\\':
                return ['UN' + self.minusflag[1:].upper()]
            else:
                return ['UNKEYWORD', self.minusflag]

    def name( self ):
        if self.plusflag:
            return 'flagged as ' + self.plusflag
        else:
            return 'not flagged as ' + self.minusflag

    def local_match( self, msg ):
        return self.still_matches( msg )

class crit_from(crit_stringmatch):
    def __init__( self, fr ):
        crit_stringmatch.__init__( self, 'FROM', fr )

class crit_subject(crit_stringmatch):
    def __init__( self, fr ):
        crit_stringmatch.__init__( self, 'SUBJECT', fr )

class crit_undeleted(crit_genflag):
    def __init__( self ):
        crit_genflag.__init__( self, minusflag='\\Deleted' )

class crit_unseen(crit_genflag):
    def __init__( self ):
        crit_genflag.__init__( self, minusflag='\\seen' )

class crit_and(criteria):
    def __init__( self ):
        criteria.__init__( self )
        self.stuff = []

    def asToks( self ):
        t = []
        for x in self.stuff:
            t += x.asToks()
        return [t]

    def add( self, criteria ):
        if isinstance( criteria, crit_and ):
            for x in criteria.stuff:
                self.add( x )
            return
        self.stuff.append( criteria )
        self.metadata = self.metadata or criteria.metadata
        self.unseen = self.unseen or criteria.unseen
        
    def name( self ):
        s = ''
        for x in self.stuff:
            if s != '':
                s += ', and '
            s += x.name()
        return s

    def still_matches( self, msg ):
        for x in self.stuff:
            if not x.still_matches( msg ):
                return False
        return True

    def local_match( self, msg ):
        for x in self.stuff:
            r = x.check_match( msg )
            if r is None:
                return None
            elif not r:
                return False
        return True

class crit_not(criteria):
    def __init__( self, crit ):
        criteria.__init__( self )
        self.crit = crit
        if crit.plusflag and crit.minusflag:
            self.crit = crit_and()
            self.crit.add( crit_genflag( plusflag=crit.plusflag ) )
            self.crit.add( crit_not( minusflag=crit.minusflag ) )
        if isinstance( self.crit, crit_and ):
            c = crit_or()
            for x in self.crit.stuff:
                c.add( crit_not( x ) )
            self.crit = c
        self.metadata = crit.metadata
        self.unseen = crit.unseen

    def asToks( self ):
        t = self.crit.asToks()
        if t[0] == 'OLD':
            t[0] = 'RECENT'
        elif t[0] == 'RECENT':
            t[0] = 'OLD'
        elif t[0] in ['ANSWERED','DELETED','DRAFT','FLAGGED','KEYWORD','SEEN']:
            t[0] = 'UN'+t[0]
        elif t[0] in ['UNANSWERED','UNDELETED','UNDRAFT','UNFLAGGED','UNKEYWORD','UNSEEN']:
            t[0] = t[0][2:]
        elif t[0] == 'NOT':
            return t[1:]
        return t
        
    def name( self ):
        s = 'not ' + x.name()
        return s

    def still_matches( self, msg ):
        return not self.crit.still_matches( msg )

    def local_match( self, msg ):
        r = self.crit.check_match( msg )
        if r:
            return False
        if r is None:
            return None
        return True

class crit_or(criteria):
    def __init__( self ):
        criteria.__init__( self )
        self.stuff = []

    def asToks( self ):
        t = [ 'OR' for x in self.stuff ][1:]
        for x in self.stuff:
            t += x.asToks()
        return t

    def add( self, criteria ):
        if isinstance( criteria, crit_or ):
            for x in criteria.stuff:
                self.add( x )
            return
        self.stuff.append( criteria )
        self.metadata = self.metadata or criteria.metadata
        self.unseen = self.unseen or criteria.unseen
        
    def name( self ):
        s = ''
        for x in self.stuff:
            if s != '':
                s += ', or '
            s += x.name()
        return s

    def still_matches( self, msg ):
        for x in self.stuff:
            if x.still_matches( msg ):
                return True
        return False

    def local_match( self, msg ):
        m = False
        for x in self.stuff:
            r = x.check_match( msg )
            if r:
                return True
            if r is None:
                m = None
        return m

def extract_criteria( what, charset = None ):
    if not len(what):
        return crit_all()
    key = what.pop()
    if isinstance(key,list):
        subcrit = []
        while len(key):
            subcrit += extract_criteria(key, charset=charset)
        if len(subcrit) == 1:
            return subcrit[0]
        else:
            critx = crit_and()
            for i in subcrit:
                critx.add(i)
            return critx
    if key.upper().find('UN')==0:
        key = key[2:]
        what.append( key )
        key = 'NOT'
    if key.lower() == 'not':
        return crit_not( extract_criteria( what, charset ) )
    if key.lower() == 'all':
        return crit_all()
    if key.lower() in ['answered','deleted','draft','flagged','recent','seen']:
        return crit_genflag( plusflag='\\' + key.lower() )
    if key.lower() == 'keyword':
        fl = what.pop()
        return crit_genflag( plusflag=fl )
    if key.lower() == 'new':
        return crit_genflag(plusflag='\\recent',minusflag='\\seen')
    if key.lower() == 'old':
        return crit_not( crit_recent() )
    if key.lower() in ['bcc','body','cc','subject','from','to']:
        s = what.pop()
        if charset:
            s = s.decode( charset )
        return crit_stringmatch( key.upper(), s )
    if key.lower() == 'header':
        h = what.pop()
        s = what.pop()
        if charset:
            s = s.decode( charset )
        return crit_headermatch( h, s )
    if key.lower() == 'younger':
        comp = int(what.pop())
        return crit_within(comp,True)
    if key.lower() == 'older':
        comp = int(what.pop())
        return crit_within(comp,False)
    if key.lower() == 'or':
        c = crit_or()
        c.add( extract_criteria( what, charset ) )
        c.add( extract_criteria( what, charset ) )
        return c
    if key[0].isdigit():
        t = key.split(':')
        if len(t) == 2 and t[0].isdigit() and (t[1].isdigit() or t[1] == '*'):
            return crit_seqrange(t[0], t[1])
    raise KeyError, "Unknown criteria '%s'" % key

def parse_criteria( tok, server ):
    charset = None
    if isinstance( tok, unicode ):
        tok = tok.encode('utf-8')
        charset = 'utf-8'
    if isinstance( tok, str ):
        s,i,tok = server.nparser( tok, genex=False )
    tok.reverse()
    if len(tok) and isinstance(tok[-1],str) and tok[-1].lower()=='charset':
        tok.pop()
        charset = tok.pop().lower()
    crit = []
    while len(tok):
        crit.append( extract_criteria( tok, charset ) )
    if len(crit)==0:
        return None
    if len(crit)==1:
        return crit[0]
    critx = crit_and()
    for c in crit:
        critx.add( c )
    return critx

def mailbox_filter(master, crit, noremove=False, sync=False):
    s = master.server()
    if s.have_capability('ESEARCH'):
        if s.have_capability('CONTEXT') and 'SEARCH' in s.get_capability('CONTEXT'):
            return mailbox_filter_context(master,crit,noremove)
        return mailbox_filter_basic(master,crit,noremove)
    elif sync:
        return mailbox_filter_simple(master,crit,noremove)
    return mailbox_filter_basic(master,crit,noremove)

class mailbox_filter_core:
    def __init__( self, master, crit, noremove=False ):
        self.master = master
        if not isinstance( crit, criteria ):
            crit = parse_criteria( crit, self.master.server() )
        self.criteria = crit
        self.noremove = noremove
        self._notifies = []
        self._mods = []

    def master_uri(self):
        return self.master.uri()

    def uri(self):
        return infotrope.url.URL( str(self.master.uri()) + '?' + crit.asString().encode('urlencode') )

    def server( self ):
        return self.master.server()

    def register_notify( self, who ):
        self._notifies.append( weakref.ref( who ) )

    def delete_notify( self, who ):
        tmp = self._notifies
        self._notifies = []
        for x in tmp:
            xx = x()
            if xx is not None:
                if xx is not who:
                    self._notifies.append( x )
        
    def notify( self ):
        for x in self._notifies:
            xx = x()
            if xx is not None:
                xx.notify_change( self, self._mods )
        self._mods = []

    def have_rights( self, which ):
        return self.master.have_rights( which )

    def freeze( self ):
        return self.master.freeze()

    def __len__( self ):
        return None

    def convert_sequence_then( self, action, seqs, *args ):
        uids = [ self.seqno( s ) for s in seqs ]
        uids = [ u for u in uids if u is not None ]
        action( uids, *args )

    def seqno( self, seq ):
        """ Given a pseudo sequence number, find the corresponding UID. """
        return None

    def check_seqno( self, seq ):
        """ Given a pseudo sequence number, find the corresponding UID
        if already known. """
        return None        

    def uid( self, uid, closest=False ):
        self.master.server().log( "Cannot find UID %s at all, given up." % `uid` )
        return None

    def expunge( self ):
        return self.master.expunge()

    def __getitem__( self, uid ):
        """ Return the message for this UID. """
        return self.master[uid]

    def index( self, uid ):
        return self.uid( uid )

    def flag_available( self, f ):
        return self.master.flag_available( f )

    def permflags( self ):
        return self.master.permflags()

    def newflags( self ):
        return self.master.newflags()

    def prefetch( self, uids, then=None ):
        return self.master.prefetch( uids, then )

    def logical_start_position( self ):
        return 0

    def find_message_id( self, x ):
        return None

class mailbox_filter_basic(mailbox_filter_core):
    def __init__( self, master, crit, noremove=False ):
        mailbox_filter_core.__init__(self, master, crit, noremove)
        self._old_count = len(self.master)
        self.master.register_notify( self )
        self.blocks = {}
        self.block = None
        self.checking = None
        self._notifies = []
        self._mods = []
        self._real_len = None
        self._min = None
        self._max = None
        self._esearch = None
        self._block_size = None
        self.send_esearch()

    def block_size( self ):
        if self._block_size is None:
            self.esearch()
            if self._min is None:
                self._block_size = max_pull * 3
                if len(self.master) < 3000:
                    self._block_size = len(self.master)
            else:
                if len(self.master) < 3000:
                    self._block_size = len(self.master)
                else:
                    holes = len(self.master) - self._real_len
                    max_num = 2 * ( holes + 1 )
                    if max_num > self._real_len:
                        max_num = self._real_len
                    foo = ( len(self.master) * 3 * max_pull ) / max_num
                    self._block_size = ( foo / max_pull ) * max_pull
                self.master.server().log( "Filter using block size of %d" % self._block_size )
        return self._block_size

    def notify_change( self, mbx, which ):
        self.server().log( "Got change for " + `which` )
        if self.criteria.metadata:
            check = []
            nwhich = []
            for x in which:
                if x == 0:
                    self._mods.append( 0 )
                    continue
                f = False
                for b in self.blocks.values():
                    if x in b:
                        f = True
                        break
                if not f:
                    if self.master.uid(x) is not None:
                        tr = self.criteria.local_match( self.master[x] )
                        #print "Local match on",`x`,"gave result",`tr`
                        if tr is True:
                            #print "Adding"
                            self._addto(x)
                        elif tr is None:
                            nwhich.append(x)
                else:
                    self.server().log(`x` + " IN search")
                    check.append( x )
            for x in check:
                if self.master.uid( x ) is None:
                    self._remove( x, True )
                elif not self.criteria.still_matches( self[x] ):
                    self._remove( x )
                self._mods.append( x )
            msgset = ','.join(self.master._make_msg_set( nwhich ))
            if len(msgset)>0:
                self.checking = nwhich
                self.block = None
                cmd = ['UID SEARCH']
                if self.master.server().have_capability('ESEARCH'):
                    cmd += ['RETURN', ['ALL']]
                cmd += ['CHARSET','UTF-8']
                cmd += [ 'UID', msgset ] + self.criteria.asToks()
                t,r,s = self.master.server().send( tuple(cmd), mbox=self.master.path() )
                self.master.server().register( t, self )
                if r is None:
                    t,r,s = self.master.server().wait( t )
                self.checking = None
                if r.lower()!='ok':
                    raise infotrope.base.connection.exception( s )
        if len(mbx)!=self._old_count:
            ## TODO :: Don't delete old block, just update.
            w = ( self.block_size() * ( self._old_count / self.block_size() ) )
            self._old_count = len(mbx)
            if w in self.blocks:
                self._mods += self.blocks[w]
                del self.blocks[w]
            self._real_len = None
            self._max = None
            self.send_esearch()
        self._mods += which
        self.notify()

    def fetch_block( self, what ):
        what = ( self.block_size() * ( what / self.block_size() ) )
        if what in self.blocks:
            return self.blocks[what]
        self.esearch()
        if self._min is not None:
            if self._min > ( what + self.block_size() ):
                self.blocks[what] = []
                return self.blocks[what]
        if self._max is not None:
            if self._max < ( what + 1 ):
                self.blocks[what] = []
                return self.blocks[what]
        self.block = what
        if self.master.server().have_capability('ESEARCH'):
            cmd = [ 'SEARCH' ]
            cmd += ['RETURN', ['ALL']]        
        else:
            cmd = [ 'UID SEARCH' ]
        cmd += ['CHARSET','UTF-8']
        cmd += [ '%d:%d' % ( what + 1, what + self.block_size() ) ]
        cmd += self.criteria.asToks()
        self.master.uidvalidity()
        t,r,s = self.master.server().send( tuple(cmd), mbox=self.master.path() )
        self.master.server().register( t, self )
        if r is None:
            t,r,s = self.master.server().wait( t )
        self.block = None
        if r.lower()!='ok':
            raise infotrope.base.connection.exception( s )
        if what not in self.blocks:
            self.blocks[what] = []
        self._mods += self.blocks[what]
        self.notify()
        return self.blocks[what]

    def _handle_search( self, t, r, s ):
        if self.block is not None:
            self.blocks[self.block] = s
            self.blocks[self.block].sort()
        else:
            res = s
            res.sort()
            self.checking.sort()
            for x in self.checking:
                if x in res:
                    if self._real_len is not None:
                        self._real_len += 1
                    seq = self.master.uid( x )
                    bn = ( self.block_size() * ( seq / self.block_size() ) )
                    if bn in self.blocks:
                        b = self.blocks[bn]
                        if x not in self.blocks[bn]:
                            self.blocks[bn].append(x)
                            self.blocks[bn].sort()
                            self._mods.append( x )
                else:
                    self._remove( x )
        return t,r,s

    def _remove( self, x, really=False ):
        if not really:
            really = self.noremove
        for bl in self.blocks.values():
            if x in bl:
                if not really:
                    if self._real_len is not None:
                        self._real_len -= 1
                    bl.remove(x)
                self._mods.append( x )
                break

    def _addto( self, x ):
        seqno = self.master.uid(x)
        bn = (self.block_size() * (seqno / self.block_size()))
        #print "Adding to block",bn
        b = self.blocks.get(bn,[])
        #print "==>",b
        b.append(x)
        b.sort()
        #print "==>",b
        self.blocks[bn] = b
        if self._real_len is not None:
            self._real_len += 1
        self._mods.append(x)
        
    def _handle_esearch( self, t, r, s ):
        if 'ALL' in s:
            uids = [ self.master.seqno( x ) for x in s['ALL'] ]
            self._handle_search( t, r, uids )
        else:
            self._real_len = s['COUNT']
            if 'MIN' in s:
                self._min = s['MIN']
                self._max = s['MAX']
        return t,r,s

    def send_esearch( self ):
        if self.master.server().have_capability('ESEARCH'):
            if self._esearch is None:
                cmd = ['SEARCH', 'RETURN', ['COUNT', 'MIN', 'MAX'], 'CHARSET', 'UTF-8'] + self.criteria.asToks()
                self.master.uidvalidity()
                t,r,s = self.master.server().send( cmd, mbox=self.master.path() )
                self.master.server().register( t, self )
                if r is None:
                    self._esearch = t

    def esearch( self ):
        if self._esearch is not None:
            self.master.server().wait( self._esearch )
            self._esearch = None

    def __len__( self ):
        self.esearch()
        if self._real_len is not None:
            return self._real_len
        l = 0
        for ll in range( 0, len(self.master), self.block_size() ):
            if ll in self.blocks:
                l += len( self.blocks[ll] )
            elif ( ll + self.block_size() ) > len(self.master):
                l += len(self.master) - ll
            else:
                l += self.block_size()
        return l

    def seqno( self, seq ):
        """ Given a pseudo sequence number, find the corresponding UID. """
        if seq is None:
            return None
        seq = seq - 1
        for ll in range( 0, len( self.master ), self.block_size() ):
            b = self.fetch_block( ll )
            if len(b) > seq:
                return b[seq]
            seq -= len(b)
        return None

    def check_seqno( self, seq ):
        if seq is None:
            return None
        seq = seq - 1
        for ll in range( 0, len( self.master ), self.block_size() ):
            if ll not in self.blocks:
                return None
            b = self.fetch_block( ll )
            if len(b) > seq:
                return b[seq]
            seq -= len(b)
        return None        

    def uid( self, uid, closest=False ):
        rseq = self.master.uid( uid, closest )
        if rseq is not None:
            b = self.fetch_block( rseq )
            if not closest and uid not in b:
                return None
            pseq = 0
            for x in range( 0, len( self.master ), self.block_size() ):
                bb = self.fetch_block( rseq )
                if len(bb)>0:
                    if bb[-1] >= uid:
                        pseq += len([x for x in bb if x<=uid])
                        return pseq
                    else:
                        pseq += len(bb)
        self.master.server().log( "Cannot find UID %s at all, given up." % `uid` )
        return None

class mailbox_filter_simple(mailbox_filter_core):
    def __init__(self, master, crit, noremove=False):
        mailbox_filter_core.__init__(self, master, crit, noremove)
        cmd = ['UID SEARCH', 'CHARSET', 'UTF-8']
        cmd += self.criteria.asToks()
        self._search,r,s = self.server().send(cmd, mbox=self.master.path())
        if r is None:
            self.server().register(self._search,self)

    def __len__(self):
        self.wait()
        return len(self.__data)

    def seqno(self,s):
        self.wait()
        return self.__data[s-1]

    def check_seqno(self,s):
        return self.seqno(s)

    def uid(self,u):
        return self.__data.index(u)+1

    def _handle_search(self, t, r, s):
        import array
        self.__data = array.array(s)

    def wait(self):
        if self._search is not None:
            self.server().wait(self._search)
            self._search = None

class mailbox_filter_context(mailbox_filter_core):
    def __init__(self, master, crit, noremove=False):
        mailbox_filter_core.__init__(self, master, crit, noremove)
        cmd = ['UID SEARCH', 'RETURN', ['UPDATE', 'CONTEXT', 'COUNT'], 'CHARSET', 'UTF-8']
        cmd += self.criteria.asToks()
        self._count = None
        self._blocks = {}
        self._searches = {}
        self._keys = []
        self.server().log('Sending CUC search')
        self._update_search,r,s = self.server().send(cmd, mbox=self.master.path())
        if r is None:
            self.server().register(self._update_search,self)
        self.server().flush()

    def __del__(self):
        self.server().send(['CANCELUPDATE',infotrope.base.string(str(self._update_search))])

    def wait(self):
        self.server().log('Waiting for CUC search')
        if self._count is None:
            self.server().wait(self._update_search)

    def __len__(self):
        self.wait()
        return self._count

    def find_block(self,s):
        bkey = 0
        for x in self._keys:
            if x <= s:
                bkey = x
            else:
                return bkey,x
        return bkey,self._count+1

    def fetch_seqno(self,s,then=None):
        self.wait()
        if s > self._count:
            if then is not None:
                then()
            return
        block,end = self.find_block(s)
        data = self._blocks.get(block,[])
        if len(data) > (s - block):
            if then is not None:
                then()
            return
        # Now find a good place to get data.
        block_start = s / 500 * 500
        if block_start == 0:
            block_start = 1
        if block_start < (block + len(data)):
            block_start = s
        block_end = block_start + 499
        if block_end >= end:
            block_end = end - 1
        ret = ['PARTIAL', '%d:%d' % (block_start,block_end)]
        if block_start == 1 and block_end == self._count:
            ret = []
        search = self._searches.get(block_start,None)
        if search is None:
            if block_start == block_end and self._count != 1:
                raise "Start is end for %s %s" % (`s`,`self._count`)
            search,r,s = self.server().send(['UID SEARCH', 'RETURN', ret, 'CHARSET', 'UTF-8'] + self.criteria.asToks(), mbox=self.master.path())
            search.context_block = (block_start,block_end)
            search.oncomplete(self.drop_search)
            self._searches[block_start] = search
            self.server().register(search,self)
        if then is None:
            self.server().wait(search)
            return
        search.oncomplete(then)

    def drop_search(self, search, t,r,s):
        try:
            del self._searches[search.context_block[0]]
        except:
            pass

    def _handle_esearch(self, t, r, s):
        print "Context ESEARCH:",`s`
        dkey = None
        if 'COUNT' in s:
            self._count = s['COUNT']
        if 'CHANGE' in s:
            print "Was: ",`self._count`
            self.process_changes(s['CHANGE'])
            print "Now: ",`self._count`
        if 'PARTIAL' in s:
            dkey = 'PARTIAL'
        if 'ALL' in s:
            dkey = 'ALL'
        if dkey:
            st,end = self.find_block(t.context_block[0])
            data = self._blocks.get(st,[])
            if st + len(data) == t.context_block[0]:
                data += s[dkey]
                if st + len(data) == end:
                    data2 = self._blocks.get(end,None)
                    if data2 is not None:
                        data += data2
                        del self._blocks[end]
                        self._keys.remove(end)
                self._blocks[st] = data
                if st not in self._keys:
                    self._keys.append(st)
                    self._keys.sort()
            else:
                data = s[dkey]
                if t.context_block[0] + len(data) == end:
                    data2 = self._blocks.get(end,None)
                    if data2 is not None:
                        data += data2
                        del self._blocks[end]
                        self._keys.remove(end)
                self._blocks[t.context_block[0]] = data
                self._keys.append(t.context_block[0])
                self._keys.sort()
        return t,r,s

    def process_changes(self, change_list):
        for ctype, position, values in change_list:
            self._mods += values
            if ctype == 'REMOVEFROM':
                self._count -= len(values)
                counter = 0
                values.sort()
                values.reverse()
                uid = values.pop()
                old_keys = self._keys[:]
                self._keys = []
                for x in old_keys:
                    data = self._blocks[x]
                    while uid and uid < data[0]:
                        counter += 1
                        if values:
                            uid = values.pop()
                        else:
                            uid = None
                    if counter:
                        del self._blocks[x]
                        x -= counter
                    self._keys.append(x)
                    while uid and uid in data:
                        counter += 1
                        data.remove(uid)
                        if values:
                            uid = values.pop()
                        else:
                            uid = None
                    self._blocks[x] = data
            elif ctype == 'ADDTO':
                self._count += len(values)
                counter = 0
                values.sort()
                values.reverse()
                uid = values.pop()
                old_keys = self._keys[:]
                self._keys = []
                for x in old_keys:
                    data = self._blocks[x]
                    while uid and uid < data[0]:
                        counter += 1
                        if values:
                            uid = values.pop()
                        else:
                            uid = None
                    if counter:
                        del self._blocks[x]
                        x += counter
                    self._keys.append(x)
                    while uid and uid >= data[0] and uid <= data[-1]:
                        counter += 1
                        data.append(uid)
                        data.sort()
                        if values:
                            uid = values.pop()
                        else:
                            uid = None
                    self._blocks[x] = data

    def check_seqno(self,s):
        def nothing(*args):
            pass
        self.fetch_seqno(s, then=nothing)
        st,end = self.find_block(s)
        try:
            return self._blocks[st][s-st]
        except:
            return None

    def seqno(self,s):
        self.fetch_seqno(s)
        st,end = self.find_block(s)
        try:
            return self._blocks[st][s-st]
        except:
            return None        

    def uid(self,u,skip_searches=False, closest=False):
        for chk in self._keys:
            block = self._blocks.get(chk)
            if block is None:
                continue
            try:
                #self._imap.log("Looking for %s in block %s len %d - %s" % (`u`,`chk`,len(block),`block`))
                return chk + block.index(u)
            except ValueError, e:
                if block[0] < u and block[-1] > u:
                    #self._imap.log("Check is %d, Block range %d to %d includes %s but missing." % (chk, block[0], block[-1], `u`))
                    #self._imap.log("Block is %s" % ( `block` ))
                    #self._imap.log("Exception is %s" % (str(e)))
                    if closest:
                        break
                    return None
        if skip_searches:
            return None
        seqno0 = 1
        seqnon = self._count
        self.server().log("Searching for UID %s" % ( `u` ))
        while True:
            uid0 = self.seqno( seqno0 )
            if uid0 is None:
                self.server().log("Seqno %d does not exist, aborting" % (seqno0))
                return None
            uidn = self.seqno( seqnon )
            self.server().log("%s => %s, %s => %s" % (`seqno0`,`uid0`,`seqnon`,`uidn`))
            while uidn is None:
                uidn = self.seqno( self._count )
                self.server().log("Now got %s" % (`uidn`))
            if uid0 == u:
                return seqno0
            if uidn == u:
                return seqnon
            if uid0 == uidn:
                if closest:
                    return seqno0
                return None
            if u<uid0:
                if closest:
                    return seqno0
                return None
            if u>uidn:
                if closest:
                    return seqnon
                return None
            cseq = seqno0 + int( ( u - uid0 ) * ( 1.0 * ( seqnon - seqno0 ) ) / ( uidn - uid0 ) )
            cuid = self.seqno( cseq )
            if cuid==u:
                return cseq
            if cuid > u:
                seqnon = cseq - 1
            else:
                seqno0 = cseq + 1

