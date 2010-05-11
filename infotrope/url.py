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
# Encodings URLs use:
# 1) IMAP's Modified UTF-7
import infotrope.modutf7
# 2) Standard URL encoding of unsafe characters.
import infotrope.urlencode
# 3) XMPP stringprep profiles.
try:
    from infotrope.resourceprep import resourceprep
    from infotrope.nodeprep import nodeprep
    from encodings.idna import nameprep as nameprep_idna
except:
    def nameprep_idna( s ): return s
    def nodeprep( s ): return s
    def resourceprep( s ): return s

def nameprep( s ):
    if isinstance( s, str ):
        s = s.decode('us-ascii')
    return nameprep_idna( s )

_uri_map = {}

class URL_base:
    """
    A good old URL.
    """
    def __init__( self, thing ):
        """
        Create a URL, either by copying an existing URL, or parsing one from a string.
        """
        self.scheme = None
        self.mechanism = None
        self.username = None
        self.server = None
        self.port = None
        self.path = None
        self.parameters = None
        self.query = None
        self.fragment = None
        self.default_port = None
        self.string_form = None
        if isinstance( thing, unicode ):
            thing = thing.encode('utf-8')
        if isinstance( thing, str ):
            self.parse_url_full( thing )
        elif isinstance( thing, URL_base ):
            self.scheme = thing.scheme
            self.username = thing.username
            self.mechanism = thing.mechanism
            self.server = thing.server
            self.port = thing.port
            self.path = thing.path
            self.parameters = thing.parameters
            self.query = thing.query
            self.fragment = thing.fragment

    def __setattr__( self, attr, val ):
        self.__dict__[attr] = val
        self.__dict__['string_form'] = None
        if attr == 'username':
            if val is None or val.lower()=='anonymous':
                self.__dict__['mechanism'] = 'ANONYMOUS'
            elif self.mechanism is None or self.mechanism == 'ANONYMOUS':
                self.__dict__['mechanism'] = '*'
            
    def parse_url_full( self, urltxt ):
        '''
        Parse an absolute URL.
        We specialize for http, imap, acap, smtp, and mailto.
        '''
        # First, find the scheme.
        #print 'Parsing:',`urltxt`
        brk = urltxt.index( ':' )
        self.scheme = urltxt[0:brk].lower()
        for x in self.scheme:
            if not x.isalpha() and x!='-':
                raise "Not a URI"
        urltxt = urltxt[brk+1:]
        if self.scheme in ['mailto','news']:
            brk = urltxt.find( '?' )
            if brk == -1:
                self.path = urltxt
                return
            self.path = urltxt[0:brk]
            self.query = urltxt[brk+1:]
            return
        # Now find the authority part
        if urltxt[0:2] == '//':
            urltxt = urltxt[2:]
        elif self.scheme == 'xmpp':
            self.scheme = 'jid'
        brk = urltxt.find( '/' )
        if brk == -1:
            self.server = urltxt
            urltxt = '/'
        else:
            self.server = urltxt[0:brk]
            urltxt = urltxt[brk:]
        # Now split up the authority part into authentication and netloc.
        brk = self.server.find( '@' )
        if brk != -1:
            self.username = self.server[0:brk]
            self.server = self.server[brk+1:]
            tmp = self.username.split( ';' )
            self.username = tmp[0].decode('urlencode')
            if tmp[0] == '':
                self.username = None
            if len(tmp)>1:
                authopts = tmp[1].split( '=' )
                if( authopts[0].lower()=='auth' ):
                    self.mechanism = authopts[1].decode('urlencode').upper()
        self.do_auth_stuff()
        # Do we have a port?
        brk = self.server.find(':')
        if brk != -1:
            self.port = int(self.server[brk+1:])
            self.server = self.server[0:brk]
        else:
            self.port = self.default_port
        # The rest of the URL is path, parameters, query and fragment. Work backwards.
        brk = urltxt.rfind( '#' )
        if brk != -1:
            self.fragment = urltxt[brk+1:]
            urltxt = urltxt[0:brk]
        brk = urltxt.rfind( '?' )
        if brk != -1:
            self.query = urltxt[brk+1:]
            urltxt = urltxt[0:brk]
        self.path = urltxt

    def do_auth_stuff( self ):
        if self.mechanism is None:
            if self.username is None:
                self.mechanism = 'ANONYMOUS'
            elif self.username.lower() == 'anonymous':
                self.username = None
                self.mechanism = 'ANONYMOUS'
            else:
                self.mechanism = '*'
        elif self.mechanism.upper() == 'ANONYMOUS':
            self.username = None
        
    def __repr__( self ):
        """
        Return a URL in Python code.
        """
        return 'infotrope.url.URL(' + `self.asString()` + ')'

    def __str__( self ):
        """
        Convert the URL to a string.
        """
        return self.asString()

    def asString( self ):
        if self.string_form is None:
            self.__dict__['string_form'] = self.asString_real()
        return self.string_form

    def asString_real( self ):
        """
        Formally convert the URL into a string.
        """
        if self.scheme == 'jid':
            url = 'xmpp:'
        else:
            url = self.scheme + ':'
        if self.scheme in ['mailto','news']:
            url += self.path
        else:
            if self.scheme not in ['smtp','jid']:
                url += '//'
            add_at = False
            self.do_auth_stuff()
            if self.username is not None and self.username.lower()!='anonymous':
                url += self.username.encode('urlencode')
                add_at = True
            if self.mechanism is not None:
                if self.mechanism == '*':
                    if self.username is None:
                        url += ';AUTH=*'
                        add_at = True
                elif self.mechanism.upper()!='ANONYMOUS':
                    url += ';AUTH=' + self.mechanism.upper().encode('urlencode')
                    add_at = True
            if add_at:
                url += '@'
            url += self.server
            if self.port is not None:
                if self.default_port:
                    if self.port!=self.default_port:
                        url += ':%d' % self.port
                else:
                    url += ':%d' % self.port
            if self.path:
                if self.path != '/' or self.scheme in ['http','imap','imaps']:
                    url += self.path
        if self.query:
            url += '?'
            url += self.query
        if self.fragment:
            url += '#'
            url += self.fragment
        return url

    def add_relative( self, what ):
        """
        Add a (potentially) relative URL to self,
        treating self as the base.
        """
        if isinstance( what, URL_base ):
            return what
        if 0 == len(what):
            return URL( self )
        if what[0] == '/':
            if 1 == len(what) or what[1] != '/':
                url = URL_base( self )
                url.path = what
                return URL( url.asString() )
            else:
                return URL( self.scheme + ':' + what )
        url = URL_base(self)
        spl1 = url.path.split('/')[1:]
        if len(spl1) and spl1[-1] == '':
            spl1 = spl1[:-1]
        spl2 = what.split('/')
        for pcomp in spl2:
            if pcomp == '.':
                pass
            elif pcomp == '..':
                spl1 = spl1[:-1]
            else:
                spl1.append( pcomp )
        url.path = '/' + '/'.join( spl1 )
        return URL( url.asString() )

    def root( self ):
        url = URL_base( self.root_user() )
        url.username = None
        url.mechanism = None
        return URL( url )

    def root_user( self ):
        url = URL_base( self )
        if url.scheme not in ['smtp','mailto']:
            url.path = '/'
        url.query = None
        url.fragment = None
        return URL( url )

class URL_imap(URL_base):
    """
    A specialized URL for IMAP.
    """
    def __init__( self, wha ):
        """
        Creation of an IMAP URL.
        """
        URL_base.__init__( self, wha )
        if self.scheme == 'imap':
            self.default_port = 143
        if isinstance( wha, self.__class__ ):
            self.mailbox = wha.mailbox
            self.uid = wha.uid
            self.uidvalidity = wha.uidvalidity
            self.type = wha.type
            self.section = wha.section
            self.urlauth = wha.urlauth
            self.expires = wha.expires
        else:
            pathx = [ pcomp.split(';') for pcomp in self.path[1:].split('/') ]
            self.mailbox = ''
            self.type = None
            dtype = 'LIST'
            self.uid = None
            self.uidvalidity = None
            self.section = None
            self.urlauth = None
            self.expires = None
            self.partial = None
            for pcomp in pathx:
                if pcomp[0] != '':
                    self.mailbox += '/' + pcomp[0].decode('urlencode').encode('mod-utf-7')
                for param in pcomp[1:]:
                    var, val = param.split('=')
                    var = var.upper()
                    if var == 'UIDVALIDITY':
                        self.uidvalidity = val
                        dtype = 'LIST'
                    elif var == 'UID':
                        self.uid = int(val)
                        dtype = 'MESSAGE'
                        self.section = ''
                    elif var == 'EXPIRES':
                        self.expires = val.upper()
                    elif var == 'URLAUTH':
                        self.urlauth = val.split(':')
                    elif var == 'TYPE':
                        self.type = val.upper()
                    elif var == 'SECTION':
                        if val:
                            dtype = 'SECTION'
                        self.section = val
                    elif var == 'PARTIAL':
                        self.partial = val
            self.mailbox = self.mailbox[1:]
            if self.type is None:
                self.type = dtype
_uri_map['imap'] = URL_imap
_uri_map['imaps'] = URL_imap

class URL_acap(URL_base):
    """
    An ACAP URL.
    """
    def __init__( self, wha ):
        """
        Creation of an ACAP URL.
        """
        URL_base.__init__( self, wha )
        self.default_port = 674
        if isinstance( wha, self.__class__ ):
            self.dataset_class = wha.dataset_class
            self.dataset = wha.dataset
        else:
            self.dataset = self.path.decode('urlencode')
            self.dataset_class = None # Unknown
            spl = self.dataset.split('/')[1:]
            if 0 < len(spl):
                if spl[0] == 'byowner':
                    if 2 < len(spl):
                        if spl[1] in ['site','~']:
                            self.dataset_class = spl[2]
                        elif 3 < len(spl):
                            self.dataset_class = spl[3]
                else:
                    self.dataset_class = spl[0]
_uri_map['acap'] = URL_acap

class URL_xmpp(URL_base):
    def __init__( self, wha ):
        URL_base.__init__( self, wha )
        self.default_port = 5222
        self.username = nodeprep( self.username )
        self.path = resourceprep( self.path )
        self.server = nameprep( self.server )
        self.resource = self.path[1:] or None

    def bare_jid( self ):
        if self.username:
            return self.username + '@' + self.server
        return self.server

    def full_jid( self ):
        p = self.resource or ''
        if p:
            p = '/' + p
        if self.username:
            return self.username + '@' + self.server + p
        return self.server + p
_uri_map['xmpp'] = URL_xmpp
_uri_map['jid'] = URL_xmpp

def URL( uri ):
    """
    Wrapper to create a URL.
    This does a first-cut parse to find the scheme,
    then recreates a scheme-specific URL object
    if one is available.
    """
    if isinstance( uri, URL_base ):
        tmp = uri
    else:
        tmp = URL_base( uri )
    if tmp.scheme in _uri_map:
        return _uri_map[tmp.scheme](tmp)
    else:
        return tmp
