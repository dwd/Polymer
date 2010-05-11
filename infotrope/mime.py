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

import infotrope.message

class parser:
    def __init__( self ):
        self.msg_out = infotrope.message.BasePart()
        self.hdr_buf = ''
        self.encoding = None

    def parse( self, s ):
        s = self.parse_headers( s )
        if self.msg_out.mtype is None:
            self.msg_out.mtype = 'text'
            self.msg_out.msubtype = 'plain'
            self.msg_out.mparams = {'charset':'us-ascii'} # We'll decode with this to be sure.
        self.parse_body( s )
        return self.msg_out

    def parse_headers( self, s ):
        self.hdr_buf = ''
        while True:
            eol = s.index( '\r\n' )
            l = s[0:eol]
            s = s[eol+2:]
            if len(l)==0:
                self.push_header()
                return s
            if l[0].isspace():
                self.hdr_buf += '\r\n' + l
            else:
                self.push_header()
                self.hdr_buf = l

    def parse_mime_header( self, v ):
        mode = 'header'
        header = ''
        param = ''
        val = ''
        params = {}
        for c in v:
            if mode=='header':
                if c==';':
                    mode = 'param'
                elif not c.isspace():
                    header += c
            elif mode=='param':
                if c=='=':
                    mode = 'val'
                elif not c.isspace():
                    param += c
            elif mode=='val':
                if c=='"':
                    mode='qval'
                elif c==';':
                    params[param.lower()] = val
                    mode='param'
                    param, val = '', ''
                elif not c.isspace():
                    val += c
            elif mode=='qval':
                if c=='\\':
                    mode = 'qval_quote'
                if c=='"':
                    mode = 'val'
                else:
                    val += c
            elif mode=='qval_quote':
                val += c
                mode = 'qval'
        if param or val:
            params[param.lower()] = val
        return header.lower(),params
    
    def push_header( self ):
        if 0==len( self.hdr_buf ):
            return
        q = self.hdr_buf.index(':')
        n = self.hdr_buf[0:q].strip()
        v = self.hdr_buf[q+1:].strip()
        if n.lower()=='content-type':
            header,params = self.parse_mime_header( v )
            self.msg_out.mtype = header[:header.find('/')]
            self.msg_out.msubtype = header[header.find('/')+1:]
            self.msg_out.mparams = params
        elif n.lower()=='content-description':
            self.msg_out.msg_description=v
        elif n.lower()=='content-disposition':
            header,params = self.parse_mime_header( v )
            self.msg_out.dtype = header
            self.msg_out.dparams = params
        elif n.lower()=='content-transfer-encoding':
            self.encoding = v
        else:
            self.msg_out.headers.append( (n,self.hdr_buf) )
            self.hdr_buf = ''
        
    def parse_body( self, s ):
        if self.msg_out.mtype.lower()=='multipart':
            boundary = self.msg_out.mparams['boundary']
            first = s.find( '\r\n--' + boundary + '\r\n' )
            s = s[first+6+len(boundary):]
            while True:
                final = False
                next = s.find( '\r\n--' + boundary + '\r\n' )
                if next == -1:
                    next = s.find( '\r\n--' + boundary + '--\r\n' )
                    final = True
                pp = parser()
                self.msg_out.subparts.append( pp.parse( s[:next] ) )
                if final:
                    return
                else:
                    s = s[next+6+len(boundary):]
        else: ## Simple part
            if self.encoding is None:
                self.encoding = '7bit'
            if self.encoding.lower() in ['8bit','7bit','binary']:
                self.msg_out.raw_data = s
            else:
                self.msg_out.raw_data = s.decode(self.encoding)
        if self.msg_out.mtype.lower()=='text':
            chrset = 'us-ascii'
            if 'charset' in self.msg_out.mparams:
                chrset = self.msg_out.mparams['charset']
            self.msg_out.raw_data = self.msg_out.raw_data.replace('\r\n','\n')
            self.msg_out.raw_data = self.msg_out.raw_data.decode(chrset)

def main():
    bin_props = infotrope.message.TrProps( encodings=['7bit','8bit','base64','quoted-printable','binary'], maxline=998 )
    bin_props = infotrope.message.TrProps()
    
    draft2 = infotrope.message.Message()
    draft2.froms.append( infotrope.message.Address( 'dave@cridland.net', 'Dave Cridland' ) )
    draft2.to.append( infotrope.message.Address( 'dwd@invsys.co.uk', 'Dave Cridland' ) )
    draft2.to.append( infotrope.message.Address( 'alexey.melnikov@isode.com', 'Alexey Melnikov' ) )
    text_part = infotrope.message.BasePart()
    text_part.raw_data = u'A textual part with extraordinarily long lines in it, possibly arising from an inadvertantly verbose string enetered within the controlling application causing a maxline problem that will force either a quoted-printable encoding, or a binary transmission path - entirely dependent on the properties of the transmission path itself, of course. Traditional line length is 998 - this accounts for the terminating carriage return and line feed, which raises the maximal line length to 1000 octets - this is the maximal line length for the ESMTP protocol itself as defined in RFC 821, and udpated in RFC 2821. Some internet applications do generate line lengths in excess of this, and compensate solely using quoted printable encoding. Polymer does not generate these for message text, as it uses format=flowed to control wrapping at a much earlier stage, limiting line lengths to 72 characters under normal conditions, however an especially long URI or other unbreakable line can cause this to overflow laterally, but it would be exceedingly rare for this to cause the 998 limit to be broken. However, this is still possible, and therefore Polymer deploys the Infotrope Python Library, and in particular its message assembly library, to reduce line length via encoding in those circumstances, or allow transmission using binary mime, which has no line length concerns.'
    flowed_part = infotrope.message.FlowedTextPart( u'Although somewhat unusual, you can pass a very long unicode string into the FlowedTextPart constructor, thus enabling demonstration of format=flowed wrapping.' )
    draft2.subparts.append( text_part )
    draft2.subparts.append( flowed_part )
    image_part = infotrope.message.BasePart()
    image_part.raw_data = file( 'polymer/invsys16.bmp', 'rb' ).read()
    image_part.mtype = 'image'
    image_part.msubtype = 'bitmap'
    draft2.subparts.append( image_part )
    
    trl = draft2.transmission_list( bin_props )
    
    s = trl[0][1]

    s = 'X-Tra-Header: This should appear first.\r\n' + s
        
    pp = parser()
    
    m = pp.parse(s)
    
    trl2 = m.transmission_list(bin_props)
    s2 = trl2[0][1]
    
    print s==s2
    st = 0
    for x in range(50,len(s),50):
        if s[st:x]!=s2[st:x]:
            print st
            print `s[st:x]`
            print `s2[st:x]`
            break
        st = x

if __name__=='__main__':
    main()
