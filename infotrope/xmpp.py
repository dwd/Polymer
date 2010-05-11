import infotrope.core
import xml.dom.minidom
import socket
from infotrope.weak import weakref

class exception(infotrope.core.exception):
    def __init__( self, resp ):
        infotrope.core.exception.__init__( self, resp )

STREAM = u'http://etherx.jabber.org/streams'
JABBER = u'jabber:client'
TLS = u'urn:ietf:params:xml:ns:xmpp-tls'
SASL = u'urn:ietf:params:xml:ns:xmpp-sasl'
BIND = u'urn:ietf:params:xml:ns:xmpp-bind'
SESSION = u'urn:ietf:params:xml:ns:xmpp-session'
DISCO_INFO = u'http://jabber.org/protocol/disco#info'
DISCO_ITEMS = u'http://jabber.org/protocol/disco#items'
COMPRESS = u'http://jabber.org/protocol/compress'
ROSTER = u'jabber:iq:roster'

_ns = {
    STREAM: 'stream',
    JABBER: 'jabber',
    TLS: 'tls',
    SASL: 'sasl',
    BIND: 'bind',
    SESSION: 'session',
    COMPRESS: 'compress',
}

class iq(infotrope.core.command):
    def __init__( self, env, xid, type, xml, to=None ):
        infotrope.core.command.__init__( self, env, xid )
        xml2 = '<iq type="%s" id="%s"' % ( type, xid )
        if to:
            xml2 += ' to="%s"' % to
        xml2 += '>' + xml + '</iq>'
        self._xml = xml2

    def xml( self ):
        return self._xml

    def complete( self, stanza ):
        self.notify_complete( stanza )

class roster:
    def __init__( self, conn ):
        self.groups = {}
        self.all = {}
        self.server = weakref.ref( conn )

    def __getitem__( self, group ):
        if group not in self.groups:
            self.groups[group] = []
        return self.groups[group]

    def updateRosterItem( self, xml ):
        jid = xml.getAttribute('jid')
        u = infotrope.url.URL( 'xmpp:' + jid ).root_user()
        jid = u.bare_jid()
        change = True
        if u.asString() not in self.all:
            change = False
            self.all[u.asString()] = roster_entry()
            delete = self.all[u.asString()].fromRosterItemXml( xml, self )
        else:
            delete = self.all[u.asString()].fromRosterItemXml( xml, self )
        if delete:
            del self.all[u.asString()]
            if not change:
                jid = None
            return jid, False, True
        return jid, change, False

    def updatePresence( self, xml ):
        jid = xml.getAttribute('from')
        u = infotrope.url.URL( 'xmpp:' + jid ).root_user()
        jid = u.bare_jid()
        change = True
        online = False
        if u.asString() not in self.all:
            change = False
            self.all[u.asString()] = roster_entry()
        else:
            online = self.all[u.asString()].available()
        self.all[u.asString()].fromPresenceXml( xml, self )
        if self.all[u.asString()].available():
            if not online:
                self.server().env.status( self.all[u.asString()].hname() + " is now online" )
        elif online:
            self.server().env.status( self.all[u.asString()].hname() + " is now offline" )
        return jid,change,False

SHOW_TYPES = ['chat',None,'away','xa','dnd']

class roster_entry:
    def __init__( self ):
        self.name = None
        self.jid = None
        self.sub_to = None
        self.sub_from = None
        self.groups = []
        self.presence = {}

    def available( self ):
        return len(self.presence)!=0

    def best_avail(self):
        if len(self.presence)==0:
            return None
        x = None
        for r,p in self.presence.items():
            i = SHOW_TYPES.index(p.show)
            if i == 0:
                return SHOW_TYPES[0] or 'available'
            elif i > x:
                x = i
        return SHOW_TYPES[x] or 'available'

    def hname( self ):
        return self.name or self.jid

    def fromRosterItemXml( self, xml, r ):
        self.name = xml.getAttribute('name')
        self.jid = infotrope.url.URL( 'xmpp:' + xml.getAttribute('jid') ).bare_jid()
        sub = xml.getAttribute('subscription')
        if sub in ['from','both']:
            self.sub_from = True
        else:
            self.sub_from = False
        if sub in ['to','both']:
            self.sub_to = True
        else:
            self.sub_to = False
        self.groups = []
        for x in xml.childNodes:
            if x.nodeType == x.ELEMENT_NODE and x.localName == 'group':
                self.groups.append( x.childNodes[0].nodeValue )
                r[x.childNodes[0].nodeValue].append( weakref.ref(self) )
        return sub == 'remove'

    def fromPresenceXml( self, xml, r ):
        u = infotrope.url.URL( 'xmpp:' + xml.getAttribute('from') )
        if not self.jid:
            self.jid = u.bare_jid()
        pres = presence_entry( xml )
        if pres.type == 'available':
            self.presence[u.resource] = pres
        elif pres.type == 'unavailable':
            if u.resource in self.presence:
                del self.presence[u.resource]
        elif pres.type == 'subscribed':
            self.sub_to = True
        elif pres.type == 'unsubscribed':
            self.sub_to = False
        else:
            r.server().log( "Unknown presence type: " + `pres.type` )

class presence_entry:
    def __init__( self, xml ):
        self.type = 'available'
        try:
            self.type = xml.getAttribute('type') or 'available'
        except:
            pass
        self.show = None
        self.status = None
        self.priority = None
        self.resource = None
        for x in xml.childNodes:
            if x.localName == 'show':
                self.show = x.childNodes[0].nodeValue
            elif x.localName == 'status' and x.childNodes:
                self.status = x.childNodes[0].nodeValue
            elif x.localName == 'priority':
                self.priority = int(x.childNodes[0].nodeValue)

class bind(iq):
    def __init__( self, conn ):
        xid = conn.get_xid()
        x = '<bind xmlns="urn:ietf:params:xml:ns:xmpp-bind"'
        if conn.uri.path[1:]:
            x += '><resource>'
            x += conn.uri.path[1:]
            x += '</resource></bind>'
        else:
            x += '/>'
        iq.__init__( self, conn.env, xid, 'set', x )

class connection(infotrope.core.connection):
    def __init__( self, uri, env ):
        global __stream_id
        infotrope.core.connection.__init__( self, uri, [('xmpp-client','tcp'),uri.default_port], env, True, False )
        self.buffer = ''
        self.stream_open = None
        self.stream_close = None
        self.state = 'stream-startup'
        self.local_id = None
        self.local_resource = None
        self.message_listeners = []
        self._capabilities = {}
        self._taghit = 0
        self._roster = roster( self )
        self.roster_listeners = []
        self.do_connect()

    def add_notify( self, me ):
        self.roster_listeners.append( weakref.ref(me) )

    def listen( self, me ):
        self.message_listeners.append( me )

    def secret_sauce( self ):
        self.env.status( "Connected to " + str(self.uri) )
        self._capabilities = {}
        self.stream_init()

    def send_raw( self, xml ):
        if isinstance(xml, unicode):
            xml = xml.encode('utf8')
        self.proto_log(xml)
        self.s.write(xml)

    def stream_init( self ):
        self.send_raw( '<?xml version="1.0"?>' )
        self.proto_log_crlf()
        #self.send_raw( '<stream:stream xmlns="%s" xmlns:stream="%s" to="%s" version="1.0">' % ( JABBER, STREAM, self.uri.server ) )
        self.send_raw( '<stream:stream xmlns="%s" xmlns:stream="%s" version="1.0">' % ( JABBER, STREAM ) )
        self.proto_log_done()
        self.state = 'stream-startup'
        self.flush()

    def prod( self ):
        if not self.s:
            return False
        if self.s.dead():
            return False
        if not self.s.prod():
            return False
        anything = False
        try:
            while self.fetch( True ):
                anything = True
        except socket.error:
            pass
        return anything

    def logout( self, phase2=False ):
        if self.s and not self.s.dead():
            self.send_raw( '<presence type="unavailable"/>' )
            self.proto_log_crlf()
            self.send_raw( '</stream:stream>' )
            self.proto_log_done()
            self.flush()
        self.s.close()

    def logout_phase2(self):
        pass

    def fetch( self, genexcept=False ):
        stanza = None
        if self.state == 'stream-startup':
            self.stream_open = self.s.readuntil( genexcept=genexcept, charseq='>' )
            self.stream_close = '</' + self.stream_open[1:self.stream_open.index(' ')] + '>'
            try:
                stanza = xml.dom.minidom.parseString( self.stream_open + self.stream_close )
            except:
                return True
            self.state = 'stream-running'
        else:
            self.buffer += self.s.readuntil( genexcept=genexcept, charseq='>' )
            try:
                stanza = xml.dom.minidom.parseString( self.stream_open + self.buffer + self.stream_close )
                self.proto_log_commit( "<<< " + self.buffer )
                self.buffer = ''
            except:
                return True
        if stanza:
            stanza = stanza.getElementsByTagNameNS( STREAM, 'stream' )
            stanza = stanza[0]
        if stanza.childNodes:
            for s in stanza.childNodes:
                if s.nodeType != s.ELEMENT_NODE:
                    continue
                ns = ''
                tag = s.localName
                if s.namespaceURI in _ns:
                    ns = _ns[s.namespaceURI]
                method = 'handle_%s_%s' % (ns,tag)
                if method in dir(self):
                    getattr(self,method)(s)
        else:
            stanza = None
        return True

    def handle_jabber_message( self, stanza ):
        for y in self.message_listeners:
            y( self, stanza )

    def handle_stream_features( self, stanza ):
        for x in stanza.childNodes:
            if x.nodeType == x.ELEMENT_NODE:
                ns = ''
                if x.namespaceURI in _ns:
                    ns = _ns[x.namespaceURI]
                if ns == 'tls' and x.localName == 'starttls':
                    self._capabilities['starttls'] = []
                elif ns == 'sasl' and x.localName == 'mechanisms':
                    self._capabilities['sasl'] = []
                    for m in x.childNodes:
                        if m.nodeType == m.ELEMENT_NODE and m.localName == 'mechanism':
                            for z in m.childNodes:
                                self._capabilities['sasl'].append( z.nodeValue.upper() )
                elif ns == 'bind' and x.localName == 'bind':
                    self._capabilities['bind'] = []
                elif ns == 'session' and x.localName == 'session':
                    self._capabilities['session'] = []
        if 'starttls' in self._capabilities and infotrope.core.platform_tls() and not self.tls_active():
            return self.starttls()
        if 'sasl' in self._capabilities and not self.local_id:
            return self.authenticate()
        if 'bind' in self._capabilities and not self.local_resource:
            return self.bind()
        if self.local_id:
            return self.now_ready()

    def get_xid( self ):
        self._taghit += 1
        return 'a%d' % self._taghit

    def send_iq( self, iqtype, xml=None, to=None ):
        if not isinstance(iqtype,iq):
            xid = self.get_xid()
            qiq = iq( self.env, xid, iqtype, xml, to )
        else:
            qiq = iqtype
        self.send_raw( qiq.xml() )
        self.proto_log_done()
        self.inprog[str(qiq)] = qiq
        return qiq

    def bind( self ):
        iq = self.send_iq( bind( self ) )
        iq.oncomplete( self.bind_complete )
        self.flush()

    def bind_complete( self, iqbind, stanza ):
        if stanza.getAttribute( 'type' )=='result':
            jid = stanza.childNodes[0].childNodes[0].childNodes[0].nodeValue
            sl = jid.find('/')
            if sl != -1:
                self.local_resource = jid[sl+1:]
            self.local_id = jid
            if 'session' in self._capabilities:
                self.setup_session()
            else:
                self.request_roster()
                self.now_ready( jid )
        
    def handle_jabber_iq( self, stanza ):
        xid = str(stanza.getAttribute( 'id' ))
        if xid in self.inprog:
            self.inprog[xid].complete( stanza )
            del self.inprog[xid]
        t = stanza.getAttribute('type')
        handle = 'error'
        xml = None
        if t == 'set' or t == 'get':
            for x in stanza.childNodes:
                if x.nodeType == x.ELEMENT_NODE and x.namespaceURI == ROSTER and x.localName == 'query':
                    for c in x.childNodes:
                        self.process_roster_item( c )
                    handle = 'result'
                elif x.nodeType == x.ELEMENT_NODE and x.namespaceURI == DISCO_INFO and x.localName == 'query':
                    if x.getAttribute('node'):
                        xml = '<query xmlns="%s">' % ( DISCO_INFO )
                        xml += '<identity category="client" type="pc" name="IPL"/>'
                        for ns in [DISCO_INFO]:
                            xml += '<feature var="%s"/>' % ( ns )
                            xml += '</query>'
                        handle = 'result'
            if handle == 'error':
                if not xml:
                    xml = stanza.childNodes[0].toxml()
                    xml += "<error type='cancel'><service-unavailable xmlns='urn:ietf:params:xml:ns:xmpp-stanzas'/></error>"
            if xid:
                self.send_raw( '<iq type="%s" from="%s" id="%s"' % ( handle, self.local_id, xid ) )
            else:
                self.send_raw( '<iq type="%s" from="%s"' % ( handle, self.local_id ) )
            if xml:
                self.send_raw( '>' )
                self.send_raw( xml )
                self.send_raw( '</iq>' )
            else:
                self.send_raw( '/>' )
            self.proto_log_done()
            self.flush()

    def setup_session( self ):
        siq = self.send_iq( 'set', '<session xmlns="urn:ietf:params:xml:ns:xmpp-session"/>', self.uri.server )
        siq.oncomplete( self.session_complete )
        self.flush()

    def roster_complete( self, riq, stanza ):
        for x in stanza.childNodes[0].childNodes:
            if x.nodeType == x.ELEMENT_NODE and x.localName == 'item':
                self.process_roster_item( x )
        for rn in self.roster_listeners:
            n = rn()
            if n:
                n.notify_complete( self )
        self.send_raw( '<presence/>' )
        self.proto_log_done()
        self.flush()

    def process_roster_item( self, x ):
        jid,change,delete = self._roster.updateRosterItem( x )
        if not jid:
            return
        for rn in self.roster_listeners:
            n = rn()
            if n:
                if change:
                    n.notify_change( self, jid )
                elif delete:
                    n.notify_removefrom( self, jid )
                else:
                    n.notify_addto( self, jid )

    def handle_jabber_presence( self, x ):
        jid,change,delete = self._roster.updatePresence( x )
        if not jid:
            return
        for rn in self.roster_listeners:
            n = rn()
            if n:
                if change:
                    n.notify_change( self, jid )
                elif delete:
                    n.notify_removefrom( self, jid )
                else:
                    n.notify_addto( self, jid )        
        
    def roster_change( self, jid, name=None, groups=None, subscription=None ):
        xml = '<query xmlns="%s"><item jid="%s"' % ( ROSTER, jid )
        if name:
            xml += ' name="%s"' % name
        if subscription:
            xml += ' subscription="%s"' % subscription
        if groups:
            xml += ''.join( '><group>%s</group' % group )
            xml += '></item>'
        else:
            xml += '/>'
        riq = self.send_iq( 'set', xml )
        riq.roster_data = ( jid, name, groups, subscription )
        riw.oncomplete( self.roster_change_complete )

    def roster_add( self, jid, name, groups=None ):
        self.roster_change( self, jid, name, groups )

    def roster_del( self, jid ):
        self.roster_change( self, jid, subscription='remove' )

    def roster_change_complete( self, riq, stanza ):
        if stanza.getAttribute('type')=='result':
            jid,change,delete = self._roster.updateFromData( *riq.roster_data )
            if not jid:
                return
            for rn in self.roster_listeners:
                n = rn()
                if n:
                    if change:
                        n.notify_change( self, jid )
                    elif delete:
                        n.notify_removefrom( self, jid )
                    else:
                        n.notify_addto( self, jid )

    def roster( self ):
        return self._roster

    def request_roster(self):
        riq = self.send_iq( 'get', '<query xmlns="%s"/>' % ( ROSTER ) )
        riq.oncomplete( self.roster_complete )
        self.flush()

    def session_complete( self, iqsess, stanza ):
        self.request_roster()
        self.now_ready()
        
    def starttls( self ):
        self.send_raw( '<starttls xmlns="urn:ietf:params:xml:ns:xmpp-tls"/>' )
        self.proto_log_done()
        self.flush()

    def handle_tls_proceed( self, stanza ):
        self.s.starttls()
        self.stream_init()

    def authenticate( self ):
        self.mech = self.sasl.mechlist( self._capabilities['sasl'] )
        d = self.mech.process( None )
        self.send_raw( '<auth xmlns="urn:ietf:params:xml:ns:xmpp-sasl" mechanism="%s"' % self.mech.name() )
        if d:
            self.send_raw( ">%s</auth>" % ''.join(d.encode('base64').split('\n')) )
        else:
            self.send_raw( "/>" )
        self.proto_log_done()
        self.flush()

    def handle_sasl_challenge( self, stanza ):
        r = stanza.childNodes[0].nodeValue.decode('base64')
        d = self.mech.process( r )
        self.send_raw( '<response xmlns="urn:ietf:params:xml:ns:xmpp-sasl"' )
        if d:
            self.send_raw( '>%s</response>' % ''.join(d.encode('base64').split('\n')) )
        else:
            self.send_raw( '/>' )
        self.proto_log_done()
        self.flush()

    def handle_sasl_success( self, stanza ):
        try:
            r = stanza.childNodes[0].nodeValue.decode('base64')
            d = self.mech.process( r )
        except:
            pass
        if self.mech.okay():
            self.local_id = self.mech.getuser()
            self.sasl.success( self.mech )
            self.auth_complete( self.mech )
            self.mech = None
            self.stream_init()
        else:
            raise "Bogus server?"
        
    def login( self, user=None, password=None ):
        "Perform SASL based login sequence."
        import infotrope.base
        import infotrope.sasl
        if user is None:
            user = self.uri.username
        user += '@' + self.uri.server
        print `self.env`,`infotrope.base`
        callback=infotrope.base.callback( self.env.callback, user, password )
        self.sasl = infotrope.sasl.sasl( self.uri, callback=callback, service='xmpp', secquery=self.env.secquery, tls_active=self.tls_active )

    def message( self, to, body, subject=None ):
        msg = '<message from="foo" to="%s"><body>%s</body></message>' % ( to, body )
        self.send_raw( msg )
        self.proto_log_done()
        self.flush()
