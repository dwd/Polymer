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

import infotrope.url
import infotrope.encoding
import infotrope.flowed
import StringIO

class MailAddress:
    def __init__( self, addr, hname=None, mime=None ):
        self.hname = hname
        self.addr = addr
        self.mime = mime
        if self.mime and not self.hname:
            self.hname = infotrope.encoding.decode_header( self.mime )

    def __str__( self ):
        if self.hname or self.mime:
            return '%s <%s>' % ( self.get_mime(), self.addr )
        return self.addr

    def get_mime( self ):
        if self.mime:
            return self.mime
        self.mime = infotrope.encoding.encode_header( self.hname )
        return self.mime

class TrType__inst:
    def __init__( self, name ):
        self.name = name

    def __repr__( self ):
        return '<' + self.name + '>'

class TrType:
    TEXT = TrType__inst( 'Text' )
    URI = TrType__inst( 'URI' )
    BINARY = TrType__inst( 'Binary' )
    EIGHTBIT = TrType__inst( '8Bit' )

class TrProps:
    def __init__( self, encodings=None, maxline=None, nullok=None, schemes=None, trusted=None, uriratifier=None, chunked=None, lengthonly=None ):
        self.encodings = encodings or ['base64','7bit','quoted-printable']
        self.maxline = maxline
        self.nullok = nullok or False
        self.schemes = schemes or []
        self.trusted = trusted or []
        self.uriratifier = uriratifier
        self.chunked = chunked or False
        self.lengthonly = lengthonly or False

    def __repr__( self ):
        return `self.__dict__`

class BasePart:
    def __init__( self ):
        self.subparts = []
        self.headers = []
        self.raw_data = None
        self.uri = []
        self.mtype = None
        self.msubtype = None
        self.mparams = {}
        self.dtype = None
        self.dparams = {}
        self.msg_description = None
        self.encoding = None
        self.encoded_body = None
        self.msg_flags = None
        self.msg_timestamp = None
        self.content_id = None

    def send_completed(self):
        pass

    def description( self ):
        return self.msg_description or self.get_msg_description()

    def get_msg_description( self ):
        pass

    def flags( self ):
        return self.msg_flags or self.get_msg_flags() or ['$MDNSent','\\Seen']

    def get_msg_flags( self ):
        pass

    def internaldate( self ):
        return self.msg_timestamp or self.get_msg_timestamp()

    def get_msg_timestamp( self ):
        pass

    def __getitem__( self, h ):
        for x in self.headers:
            if x[0].lower() == h.lower():
                return x[1]
        return None

    def saved_as( self, u ):
        #print "Saving",`self`
        url = infotrope.url.URL( u )
        found = False
        for x in self.uri:
            if str(url) == str(x):
                found = True
                break
        if not found:
            self.uri.append( url )
        if url.scheme in ['imap','imaps']:
            us = str(url)
            if url.type == 'MESSAGE':
                us += '/;SECTION='
            else:
                us += '.'
            for n in range( len( self.subparts ) ):
                self.subparts[n].saved_as( us + '%d' % ( n + 1 ) )

    def unsaved( self ):
        self.uri = []
        
    def __setitem__( self, h, txt ):
        self.add_gen_header( h, txt )

    def add_gen_header( self, h, atxt, params=None ):
        txt = None
        if isinstance(atxt,str):
            txt = atxt
        elif isinstance(atxt,unicode):
            txt = atxt
        else:
            txt = str(txt)
        if params:
            for var,val in params.items():
                txt += '; '
                txt += var
                txt += '='
                txt += '"%s"' % ( str(val).replace( '"', '\\"' ) )
        self.headers.append( ( h, infotrope.encoding.encode_header( txt, h ).replace('\n','\r\n') + '\r\n' ) )

    def set_encoding( self, avail=None ):
        avail = avail or ['7bit','quoted-printable','base64']
    
    def dump_headers( self, terminator=True ):
        htxt = ''
        for x in self.headers:
            htxt += x[1]
        if terminator:
            htxt += '\r\n'
        return htxt

    def has_headers( self ):
        return True

    def send_trlist( self, props, where ):
        where( self.transmission_list( props ) )

    def transmission_list( self, props = None, parent = None ):
        import time
        if props is None:
            props = TrProps( maxline=998 )
        save_headers = self.headers[:]
        save_subparts = self.subparts[:]
        try:
            trlist = []
            self.prep()
            self.check_mime_type()
            if self.mtype == 'x-null':
                raise "No URI, no data, no subparts."
            use_uri = None
            if ( not parent or props.chunked ) and self.uri:
                for uri in self.uri:
                    root = uri.root().asString()
                    for u in props.trusted:
                        if root==u.asString():
                            use_uri = uri.asString()
                            break
                    if use_uri:
                        break
                if not use_uri:
                    for uri in self.uri:
                        if uri.scheme in props.schemes:
                            if props.uriratifier is not None:
                                nuri = props.uriratifier( uri )
                                if nuri is not None:
                                    use_uri = nuri
                                    break
            self.prep_second( use_uri )
            subsume = self.mtype.lower() == 'multipart' and len(self.subparts)==1            
            if not subsume:
                enc = self.select_encoding( props, use_uri )
                if self.mtype.lower()=='message':
                    if self.msubtype.lower()=='rfc822-header' and ( parent is None or (parent.mtype == 'message' and parent.msubtype == 'rfc822') ):
                            subsume = True
                    if self.msubtype.lower()=='rfc822' and parent is None:
                        subsume = True
            if ( use_uri is None or parent is not None ) and self.has_headers():
                self.add_required_headers()
                if not subsume:
                    self.add_gen_header( 'Content-Type', self.mtype+'/'+self.msubtype, self.mparams )
                    if enc:
                        self.add_gen_header( 'Content-Transfer-Encoding', enc )
                    if self.dtype:
                        self.add_gen_header( 'Content-Disposition', self.dtype, self.dparams )
                    if self.description():
                        self.add_gen_header( 'Content-Description', self.description() )
                    md5 = self.gen_content_md5()
                    if md5:
                        self.add_gen_header( 'Content-MD5', md5 )
                    if self.content_id:
                        self.add_gen_header( 'Content-Id', self.content_id )
                if props.lengthonly:
                    trlist.append( ( TrType.TEXT, len(self.dump_headers( not subsume )) ) )
                else:
                    trlist.append( ( TrType.TEXT, self.dump_headers( not subsume ) ) )
            if use_uri:
                if props.lengthonly:
                    trlist.append( ( TrType.URI, len(use_uri) ) )
                else:
                    trlist.append( ( TrType.URI, use_uri ) )
                return trlist
            if len(self.subparts):
                for x in self.subparts:
                    if not subsume and self.mtype.lower()=='multipart': # Only multipart has a boundary, and only when we're not subsuming it into its parent.
                        if props.lengthonly:
                            trlist.append( ( TrType.TEXT, len('\r\n--' + self.mparams['boundary'] + '\r\n') ) )
                        else:
                            trlist.append( ( TrType.TEXT, '\r\n--' + self.mparams['boundary'] + '\r\n' ) )
                    trlist += x.transmission_list( props, parent=self )
                if not subsume and self.mtype.lower()=='multipart':
                    if props.lengthonly:
                        trlist.append( ( TrType.TEXT, len('\r\n--' + self.mparams['boundary'] + '--\r\n') ) )
                    else:
                        trlist.append( ( TrType.TEXT, '\r\n--' + self.mparams['boundary'] + '--\r\n' ) )
            else:
                self.prep_encoded_body( props )
                if not self.encoding:
                    trlist.append( ( TrType.TEXT, self.encoded_body ) )
                elif self.encoding.lower()=='binary':
                    trlist.append( ( TrType.BINARY, self.encoded_body ) )
                elif self.encoding.lower()=='8bit':
                    trlist.append( ( TrType.EIGHTBIT, self.encoded_body ) )
                else:
                    trlist.append( ( TrType.TEXT, self.encoded_body ) )
            trlist = collapse_trlist( trlist, props.chunked )
            return trlist
        finally:
            self.headers = save_headers
            self.subparts = save_subparts
            self.encoding = None
            self.encoded_body = None

    def check_mime_type( self ):
        import time
        if self.mtype is not None:
            return
        if self.uri:
            self.get_mime_type_from_uri()
            return
        if self.raw_data is None:
            if len(self.subparts)==0:
                self.mtype = 'x-null'
                return
            else:
                self.mtype = 'multipart'
                self.msubtype = 'mixed'
                self.mparams['boundary'] = gen_mime_id()
        elif isinstance(self.raw_data,unicode):
            self.mtype = 'text'
            self.msubtype = 'plain'
        else:
            raise "Can't autodetect MIME type."

    def get_mime_type_from_uri( self ):
        for u in self.uri:
            if u.scheme in ['imap','imaps']:
                if u.type=='MESSAGE':
                    self.mtype = 'message'
                    self.msubtype = 'rfc822'
        raise "Can't detect MIME type from URI yet."

    def select_encoding( self, props, nuri ):
        if self.encoding is not None:
            return self.encoding
        if self.mtype.lower() == 'text' or self.msubtype.lower()[-4:]=='+xml': # Note that any MIME type ending in +xml is XML, and thus textual in nature, albeit not always human readable.
            wchr,charset = infotrope.encoding.encode_min( self.raw_data )
            self.mparams['charset'] = charset
            self.encode_text( wchr, props )
        elif self.mtype.lower() in ['multipart','message']:
            self.encoding = False
        elif 'binary' in props.encodings:
            self.encoding = 'Binary'
        else:
            self.encoding = 'Base64'
        return self.encoding

    def encode_text( self, wchr, props ):
        try:
            longlines = False
            if '\r\n' not in wchr:
                wchr = wchr.replace('\n','\r\n')
            if props.maxline is not None:
                for x in wchr.split('\n'):
                    if (len(x)-1)>props.maxline:
                        longlines = True
                        break
            highbytes = False
            nullchar = False
            for x in wchr:
                if ord(x)>127:
                    highbytes = True
                    if not props.nullok or nullchar:
                        break
                if ord(x)==0 and not props.nullok:
                    nullchar = True
            force = False
            if longlines:
                if 'binary' in props.encodings:
                    self.encoded_body,self.encoding = (wchr,'Binary')
                    return self.encoding
                else:
                    force = True
            if not force and not nullchar and highbytes and '8bit' in props.encodings:
                self.encoded_body,self.encoding = (wchr,'8Bit')
                return self.encoding
            self.encoded_body,self.encoding = infotrope.encoding.xfer_encode_min( wchr, force )
            if self.encoding == '7bit':
                self.encoding = None
            return self.encoding
        finally:
            if props.lengthonly and isinstance(self.encoded_body,str):
                self.encoded_body = len(self.encoded_body)
    
    def prep_encoded_body( self, props ):
        if self.encoded_body is None:
            if self.raw_data is not None:
                if self.encoding and self.encoding.lower() in ['base64','quoted-printable']:
                    self.encoded_body = '\r\n'.join( self.raw_data.encode( self.encoding.lower() ).split('\n') )
                else:
                    self.encoded_body = self.raw_data
        if self.encoded_body is None:
            raise "Cannot provide encoded body"
        elif props.lengthonly and not isinstance( self.encoded_body, int ):
            self.encoded_body = len( self.encoded_body )

    def add_required_headers( self ):
        pass

    def prep( self ):
        pass

    def prep_second( self, nuri ):
        pass

    def gen_content_md5( self ):
        return None

class FlowedTextPart(BasePart):
    def __init__( self, text=None ):
        BasePart.__init__( self )
        self.raw_data = text or u''
        self.paras = None

    def set_paras(self, paras):
        self.unsaved()
        self.paras = paras
        self.raw_data = ''
        for p in paras:
            pfx = u''
            pfx = (u'>' * p.quote_depth) + u' '
            self.raw_data += pfx + p.txt + u'\n'

    def get_paras(self):
        return self.paras or infotrope.flowed.parse(self.raw_data, True)
        
    def check_mime_type( self ):
        self.mtype = 'text'
        self.msubtype = 'plain'
        self.mparams['format'] = 'flowed'
        self.mparams['delsp'] = 'yes'

    def encode_text( self, wchr, props ):
        paras = infotrope.flowed.parse( wchr, True )
        o = StringIO.StringIO()
        for p in paras:
            pfx = ''
            if p.quote_depth:
                pfx = ('>' * p.quote_depth) + ' '
            l = 70 - len(pfx)
            ptxt = p.txt
            if 0==len(pfx):
                if len(ptxt):
                    if ptxt[0] == ' ' or ptxt[0] == '>' or ptxt[0:5] == 'From ':
                        ptxt = ' ' + ptxt
            #print `l`,`len(ptxt)`,`ptxt`
            if l < len(ptxt):
                ll = 70 - len(pfx)
                while ll < len(ptxt):
                    br = ' '
                    b = ptxt.rfind( ' ', 0, ll )
                    if b==-1:
                        br = ''
                        b = ptxt.find( ' ' )
                        if b==-1:
                            break
                    o.write( pfx + ptxt[0:b] + br + ' \n' )
                    ptxt = ptxt[b+1:]
                    if 0==len(pfx):
                        if ptxt[0] == ' ' or ptxt[0] == '>' or ptxt[0:5]=='From ':
                            ptxt = ' ' + ptxt
            o.write( pfx + ptxt + '\n' )
        txt = o.getvalue()
        #print "TEXT:::",`txt`
        return BasePart.encode_text( self, txt, props )

class MessagePart(BasePart):
    def __init__( self, msg, part=None ):
        BasePart.__init__( self )
        self.part = part or msg.parts()
        if part is None or not part.part_id:
            self.uri = [infotrope.url.URL( msg.uri().asString() )]
        else:
            self.uri = [infotrope.url.URL( msg.uri().asString() + '/;section=' + self.part.part_id.encode('urlencode') )]
        self.msg = msg
        self.raw_data = None
        self.mtype = self.part.type.lower()
        self.msubtype = self.part.subtype.lower()
        self.dtype = self.part.disposition.lower()
        self.mparams = {}
        for k,v in self.part.params.items():
            self.mparams[k.lower()] = v
        self.dparams = self.part.disposition_params

    def get_msg_description( self ):
        if self.part.part_id == '':
            self.msg_description = self.msg.envelope().Subject
        else:
            self.msg_description = self.part.description
        return self.msg_description

    def get_msg_flags( self ):
        if self.part.part_id == '':
            self.msg_flags = msg.flags()
            if '$mdnsent' not in self.msg_flags:
                self.msg_flags.append( '$MDNSent' )
        return self.msg_flags
        
    def get_msg_timestamp( self ):
        self.msg_timestamp = self.msg.internaldate()
        return self.msg_timestamp

    def __repr__( self ):
        return '<MessagePart for ' + `self.uri` + '>'

    def has_headers( self ):
        #if self.part.part_id.find('HEADER') is not None:
        #    return False;
        return True

    def prep_second( self, nuri ):
        if nuri is None:
            if len(self.part.children):
                for c in self.part.children:
                    self.subparts.append( MessagePart( self.msg, c ) )

    def select_encoding( self, props, nuri ):
        if self.encoding is not None:
            return self.encoding
        if nuri is None and 'HEADER' not in self.part.part_id: # Resign ourselves to recoding it.
            if len(self.part.children): # If we have children, let's add them in.
                return False
            if self.mtype.lower()=='text' or self.msubtype.lower()[-4:]=='+xml':
                self.encode_text( self.msg.body_decode( self.part ), props )
            elif len(self.subparts):
                self.encoding = False # No encoding, just spool children
            elif 'binary' in props.encodings:
                self.encoding = 'binary'
                if props.lengthonly:
                    if self.part.encoding.lower() == 'base64':
                        self.encoded_body = ( self.part.size * 3 ) / 4
                    elif self.part.encoding.lower() in ['7bit','8bit','binary']: # Identity encodings. None of these should appear.
                        self.encoded_body = self.part.size
                    else: # QP or something. Shouldn't really be used.
                        self.encoded_body = len( self.msg.body_decode( self.path ) )
                else:
                    self.encoded_body = self.msg.body_decode( self.part )
            else:
                self.encoding = self.part.encoding
                if self.encoding is None:
                    self.encoding = False
                else:
                    self.encoding = self.encoding.lower()
                if props.lengthonly:
                    try:
                        self.encoded_body = self.part.size
                    except:
                        print "Ack!",`self.part`
                        raise
                else:
                    self.encoded_body = self.msg.body_raw( self.part )
        else:
            self.encoding = self.part.encoding
            if self.encoding is not None:
                self.encoding = self.encoding.lower()
        if self.encoding is None or self.encoding == '7bit':
            self.encoding = False
        if self.part.part_id.find( 'HEADER' ) != -1:
            import infotrope.parser
            tmp = infotrope.parser.rfc822( self.msg.body_decode( self.part ) )
            if 'MIME-Version' not in tmp:
                tmp.add_header( 'MIME-Version', '1.0' );
            tmp.remove_content_headers()
            self.encoded_body = tmp.as_string()[:-1].replace('\n','\r\n') # Trim off CRLF at end.
            if props.lengthonly:
                self.encoded_body = len(self.encoded_body)
        return self.encoding

    def prep_encoded_body( self, props ):
        if self.encoded_body is None:
            print `self`,":",`self.__dict__`
            raise "Erk, should have encoded body by now."

class MessageCopy( MessagePart ):
    def __init__( self, msg ):
        MessagePart.__init__( self, msg )

    def has_headers( self ):
        return False

def gen_mime_id():
    import time
    import os
    import socket
    hn = socket.gethostname()
    return '%d.%f@%s' % ( os.getpid(), time.time(), hn )

class MessageId:
    def __init__( self ):
        self.mid = None

    def __str__( self ):
        if not self.mid:
            self.mid = self.gen()
        return '<' + self.mid + '>'
    
    def gen( self ):
        return gen_mime_id()

class Message(BasePart):
    def __init__( self ):
        BasePart.__init__( self )
        self.froms = []
        self.sender = None
        self.to = []
        self.cc = []
        self.bcc = []
        self.newsgroups = []
        self.subject = None

    def add_required_headers( self ):
        import time
        self.add_gen_header( 'MIME-Version', '1.0' )
        self.add_gen_header( 'Message-Id', str(MessageId()) )
        self.add_gen_header( 'Date', time.strftime("%a, %d %b %Y %H:%M:%S %z"))
        if len(self.froms)==0:
            raise "No from"
        if len(self.froms)>1 and not self.sender:
            raise "Multiple froms, no sender"
        self.add_pers_header( 'From', self.froms )
        if self.sender:
            self.add_pers_header( 'Sender', self.sender.address )
        if self.to:
            self.add_pers_header( 'To', self.to )
        if self.cc:
            self.add_pers_header( 'Cc', self.cc )
        if self.newsgroups:
            self.headers.append( ('Newsgroups', ','.join(self.newsgroups)) )
        if self.subject:
            self.add_gen_header('Subject', self.subject)
            
    def add_pers_header( self, what, foo ):
        htxt = what + ': ' + ',\r\n '.join( [ str(x) for x in foo ] ) + '\r\n'
        self.headers.append( ( what, htxt ) )

class Address:
    def __init__( self, addr, hname=None, mname=None, header=None ):
        self.address = addr
        self.hname = hname
        self.mname = mname
        if hname and not mname:
            self.mname = infotrope.encoding.encode_header( hname )
        elif not hname and mname:
            self.hname = infotrope.encoding.decode_header( mname )
        self.header = header
        if self.header:
            if isinstance( self.header, list ):
                self.header = '\r\n '.join( self.header )

    def __str__( self ):
        if self.header:
            return self.header
        elif self.mname:
            return '%s <%s>' % ( self.mname, self.address )
        else:
            return '<%s>' % ( self.address )

class collapse_exception:
    def __init__( self, reason ):
        self.reason = reason

    def __str__( self ):
        return "Cannot collapse TrList: " + self.reason

class dechunk_exception:
    def __init__( self, lhs, rhs, reason ):
        self.lhs = lhs
        self.rhs = rhs
        self.reason = reason

    def __str__( self ):
        return "Cannot dechunk: LHS is "+`self.lhs.__class__.__name__`+", RHS is "+`self.rhs.__class__.__name__`+": "+self.reason

def collapse_trlist( trlist, chunks_okay ):
    """
    Collapse a trlist into a single tuple.
    """
    output = []
    wtr = trlist[:]
    wtr.reverse()
    ntr = None
    while len(wtr):
        if ntr is None or ntr[0] is TrType.URI:
            if ntr is not None:
                output.append( tuple(ntr) )
            ntr = list(wtr.pop())
            continue
        xntr = list(wtr.pop())
        if isinstance(ntr[1],str):
            if not isinstance(xntr[1],str):
                raise dechunk_exception( ntr, xntr, "Not both strings" )
        elif not isinstance(ntr[1],int):
            raise dechunk_exception( ntr, xntr, "LHS is neither int nor string" )
        elif isinstance(xntr[1],str):
            if not isinstance(ntr[1],str):
                raise dechunk_exception( ntr, xntr, "Not both strings" )
        elif not isinstance(xntr[1],int):
            raise dechunk_exception( ntr, xntr, "RHS is neither int nor string" )
        if xntr[0] is TrType.URI:
            if ntr is not None:
                output.append( tuple(ntr) )
            output.append( tuple(xntr) )
            ntr = None
            continue
        if ntr[0] is TrType.BINARY and xntr[0] is not TrType.BINARY:
            xntr[0] = ntr[0]
        elif ntr[0] is not TrType.BINARY and xntr[0] is TrType.BINARY:
            ntr[0] = xntr[0]
        elif ntr[0] is TrType.TEXT:
            ntr[0] = xntr[0]
        ntr[1] += xntr[1]
    if ntr is not None:
        output.append( tuple(ntr) )
    if not chunks_okay and len(output)>1:
        raise collapse_exception( "Chunks not supported by TrProps and length greater than one." )
    return output

def run_test():
    draft = Message()
    draft.raw_data = u'Well, this is an entirely exciting thing.'
    draft.froms.append( Address( 'dave@cridland.net', 'Dave Cridland' ) )
    draft.to.append( Address( 'dwd@invsys.co.uk', 'Dave Cridland' ) )
    print `draft.transmission_list()`
    draft2 = Message()
    draft2.froms.append( Address( 'dave@cridland.net', 'Dave Cridland' ) )
    draft2.to.append( Address( 'dwd@invsys.co.uk', 'Dave Cridland' ) )
    draft2.to.append( Address( 'alexey.melnikov@isode.com', 'Alexey Melnikov' ) )
    text_part = BasePart()
    text_part.raw_data = u'A textual part with extraordinarily long lines in it, possibly arising from an inadvertantly verbose string enetered within the controlling application causing a maxline problem that will force either a quoted-printable encoding, or a binary transmission path - entirely dependent on the properties of the transmission path itself, of course. Traditional line length is 998 - this accounts for the terminating carriage return and line feed, which raises the maximal line length to 1000 octets - this is the maximal line length for the ESMTP protocol itself as defined in RFC 821, and udpated in RFC 2821. Some internet applications do generate line lengths in excess of this, and compensate solely using quoted printable encoding. Polymer does not generate these for message text, as it uses format=flowed to control wrapping at a much earlier stage, limiting line lengths to 72 characters under normal conditions, however an especially long URI or other unbreakable line can cause this to overflow laterally, but it would be exceedingly rare for this to cause the 998 limit to be broken. However, this is still possible, and therefore Polymer deploys the Infotrope Python Library, and in particular its message assembly library, to reduce line length via encoding in those circumstances, or allow transmission using binary mime, which has no line length concerns.'
    flowed_part = FlowedTextPart( u'Although somewhat unusual, you can pass a very long unicode string into the FlowedTextPart constructor, thus enabling demonstration of format=flowed wrapping.' )
    draft2.subparts.append( text_part )
    draft2.subparts.append( flowed_part )
    image_part = BasePart()
    image_part.raw_data = file( 'polymer/invsys16.bmp', 'rb' ).read()
    image_part.mtype = 'image'
    image_part.msubtype = 'bitmap'
    draft2.subparts.append( image_part )
    bin_props = TrProps( encodings=['7bit','8bit','base64','quoted-printable','binary'], maxline=998 )
    print `draft2.transmission_list( bin_props )`
    bin_props.lengthonly = True
    print `draft2.transmission_list( bin_props )`    
    draft3 = Message()
    draft3.froms.append( Address( 'dave@cridland.net', 'Dave Cridland' ) )
    draft3.to.append( Address( 'dwd@invsys.co.uk', 'Dave Cridland' ) )
    draft3.to.append( Address( 'alexey.melnikov@isode.com', 'Alexey Melnikov' ) )
    draft3.subparts.append( text_part )
    trl = draft3.transmission_list()
    print `trl`
