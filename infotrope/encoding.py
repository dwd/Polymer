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

import re
import usascii

ENCODED_WORD = re.compile('^=\\?(?P<charset>[^?* \t]+)(?:\\*(?P<lang>[^? \t]+))?\\?(?P<encoding>[A-Za-z])\\?(?P<text>[^? \t]*)\\?=$')
FUZZY_ENCODED_WORD = re.compile( '^=\\?.*\\?=$' )

def encode_min( s ):
    'Used for translating a unicode into whatever minimal encoding we can get away with for transmission. Returns a tuple of string, charset'
    #print "Encode MIN, encoding %s %s" % ( s.__class__, s )
    for ch in ['us-ascii','iso-8859-1','utf-8']:
        try:
            #print "Trying",ch
            return s.encode(ch), ch
        except UnicodeEncodeError, e:
            #print e
            pass
    #print "Giving up and using UTF-8"
    return s.encode('utf-8'), 'utf-8'

def xfer_encode_min( txt, force=False ):
    '''
    Used for minimally encoding a byte string into whatever is shortest.
    '''
    high_count = len([ x for x in txt if ord(x) > 127])
    if not force:
        if high_count == 0:
            return txt,'7bit'
    base64_count = (len(txt)*4)/3
    if base64_count % 4:
        base64_count += 4 - ( base64_count % 4 )
    qp_count = len(txt) + high_count * 2
    #print 'Base64:',base64_count,'QP:',qp_count,'H:',high_count,'L:',len(txt)
    if base64_count < qp_count:
        return txt.encode('base64'),'Base64'
    # Python encodes spaces wrong.
    enc = '*'
    if '*' in txt:
        if '^' not in txt:
            enc = '^'
        elif '~' not in txt:
            enc = '~'
        else:
            enc = None
    if enc:
        txt = txt.replace(' ',enc)
        txt = txt.encode('quoted-printable')
        txt = txt.replace(enc,' ')
        return txt, 'Quoted-Printable'
    return txt.encode('quoted-printable').replace('=20',' '),'Quoted-Printable'

def encode_header_word( wbuffer, force=False ):
    wchr, charset = encode_min( wbuffer )
    force = force or FUZZY_ENCODED_WORD.match( wchr )
    if charset == 'us-ascii' and not force:
        return wchr,False
    else:
        wenc, enc = xfer_encode_min( wchr, force=force )
        if enc == '7bit':
            return wenc,False
        else:
            menc = 'X'
            if enc == 'Base64':
                menc = 'B'
                wenc = ''.join( wenc.split( '\n' ) )
            elif enc == 'Quoted-Printable':
                menc = 'Q'
                wenc = ''.join( wenc.split( '=\n' ) )
                wenc = wenc.replace( ' ', '_' )
                wenc = wenc.replace( '?', '=%X' % ord( '?' ) )
            return '=?%s?%s?%s?=' % ( charset.upper(), menc, wenc ), True

def canonicalize_whitespace( txt ):
    txt = txt.replace( '\t', ' ' )
    txt = txt.replace( '\n ', ' ' )
    txt = txt.replace( '\r', '' )
    txt = txt.replace( '\n', '' )
    l = len(txt)
    while True:
        txt = txt.replace( '  ', ' ' )
        if l==len(txt):
            break
        l = len(txt)
    return txt

class encode_header_engine:
    def __init__( self, txt, hdr=None, phrase=False ):
        self.wbuf = u''
        self.obuf = ''
        if hdr:
            self.obuf = hdr + ':'
        self.output = []
        self.txt = canonicalize_whitespace( txt )
        self.phrase = False

    def execute( self ):
        for word in self.txt.split( ' ' ):
            self.add_word( word )
        self.clear_word_buffer()
        if( self.obuf ):
            self.output.append( self.obuf )
        return '\n '.join( self.output ).replace( ' \n','\n' )

    def add_word( self, word ):
        word_enc, used_enc = encode_header_word( word )
        if used_enc:
            if self.wbuf:
                self.wbuf += ' '
            self.wbuf += word
        elif len( word_enc) > 75:
            if self.wbuf:
                self.wbuf += ' '
            self.wbuf += word
        else:
            self.clear_word_buffer()
            if self.obuf:
                self.obuf += ' '
            if len( self.obuf ) + len( word_enc ) > 75:
                self.output.append( self.obuf )
                self.obuf = ''
            if self.phrase:
                safe = True
                for x in word_enc:
                    if not x.isalnum() and x not in "!#$%&'*+-/=?^_`{|}~":
                        safe = False
                        break
                if not safe:
                    word_enc = '"' + word_enc.replace( '\\', '\\\\' ).replace( '"', '\"' ) + '"'
            self.obuf += word_enc

    def clear_word_buffer( self ):
        while self.wbuf:
            frame = self.wbuf[0:(45-len(self.obuf))] # 45 => 60 characters encoded, plus around 20 for charset etc.
            if frame:
                self.wbuf = self.wbuf[(45-len(self.obuf))+1:]
            else:
                self.output.append( self.obuf )
                self.obuf = ''
                frame = self.wbuf
                self.wbuf = u''
            frame_enc, frame_used = encode_header_word( frame, True )
            if self.obuf:
                self.obuf += ' '
            self.obuf += frame_enc
            if self.wbuf:
                self.output.append( self.obuf )
                self.obuf = ''

def encode_header( txt, hdr=None, phrase=False ):
    """
    Encode a unicode string as an RFC2047 header.
    The optional hdr argument is the header field name.
    """
    c = encode_header_engine( txt, hdr, phrase )
    return c.execute()

def decode_header( txt ):
    """
    Decode a header encoded with RFC2047.
    In addition, it will cope with RFC2231's language specifier, although it's discarded.
    """
    if isinstance( txt, unicode ):
        try:
            txt = txt.encode('usascii')
        except:
            import sys
            print "Unicode already?",sys.exc_type,sys.exc_info()[1]
            return txt
    txt = canonicalize_whitespace( txt )
    obuf = u''
    last_enc = False
    for word in txt.split(' '):
        encw = ENCODED_WORD.match( word )
        if encw:
            if not last_enc:
                if len(obuf):
                    obuf += ' '
            encw = encw.groupdict()
            try:
                if encw['encoding'].upper() == 'B':
                    obuf += encw['text'].decode( 'base64' ).decode( encw['charset'] )
                elif encw['encoding'].upper() == 'Q':
                    obuf += encw['text'].replace('_','=20').decode( 'quoted-printable' ).decode( encw['charset'] )
                else:
                    raise "Unknown RFC2047 encoding."
                last_enc = True
                continue
            except:
                import sys
                print " *** *** RFC2047 failure:",sys.exc_type,sys.exc_info()[1]
                pass
        if len(obuf):
            obuf += ' '
        obuf += word.decode('us-ascii','ignore')
        last_enc = False
    return obuf

try:
    import quopri
except ImportError:
    import iquopri
