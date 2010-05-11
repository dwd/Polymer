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

"""
RFC822 parsing, primarily for headers only at this point in time.
"""

class rfc822:
    """
    Simple header-only RFC822 parser.
    """
    def __init__( self, fp ):
        if isinstance( fp, str ):
            import StringIO
            fp = StringIO.StringIO( fp )
        self.lines = fp.readlines()
        self.headers = []
        self.parse_headers()
        self.lines = None

    def parse_headers( self ):
        first = True
        for x in self.lines:
            if first:
                first = False
                if x[0:5] == 'From ':
                    continue
            x = x.strip( '\r\n' )
            if len(x)==0:
                break
            if x[0] in ' \t':
                hdr,val = self.headers.pop()
                val += '\n' + x
            else:
                hdr = x[:x.index(':')].strip( ' \t' )
                val = x[x.index(':')+1:].lstrip( ' \t' )
            self.headers.append( (hdr,val) )

    def __getitem__( self, x ):
        vals = []
        for hdr,val in self.headers:
            if hdr.lower() == x.lower():
                vals.append(val)
        if len(vals)==0:
            return None
        if len(vals)==1:
            return vals[0]
        return vals

    def items( self ):
        return self.headers

    def __contains__( self, x ):
        return self[x] is not None

    def add_header( self, hdr, val ):
        self.headers.append( ( hdr, val ) )

    def remove_content_headers( self ):
        old = self.headers
        self.headers = []
        for hdr, val in old:
            if hdr.lower().find('content-')!=0:
                self.headers.append( (hdr,val) )

    def as_string( self ):
        s = ''
        for hdr,val in self.headers:
            s += hdr
            s += ': '
            s += val
            s += '\n'
        s += '\n'
        return s

_days = ['mon','tue','wed','thu','fri','sat','sun']
_months = ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec']
def parse_date( hdrval ):
    """
    Parse a date field, return a time.time.
    """
    import time
    paren = 0
    s = ''
    for x in hdrval:
        if x=='(':
            s += ' '
            paren += 1
            continue
        if x==')':
            paren -= 1
            continue
        if paren==0:
            s += x
    words = s.split(' ')
    words = [ x.strip(' \t\r\n,').lower() for x in words if len(x) ]
    day = None
    month = None
    date = None
    year = None
    hour = None
    minute = None
    sec = None
    tz = None
    for x in words:
        if day is None:
            if x[:3] in _days:
                day = _days.index(x[:3])
                continue
        if month is None:
            if x[:3] in _months:
                month = _months.index(x[:3])
                continue
        try:
            i = int(x)
            if x[0] in '-+':
                if len(x)==5:
                    tz = x
                continue
            if date is None:
                if i > 31 and year is None:
                    year = i
                    if year < 1900:
                        year += 1900
                    continue
                date = i
                continue
            if year is None:
                year = i
                if year < 1900:
                    year += 1900
                continue
        except:
            pass
        try:
            colons = [int(z) for z in x.split(':')]
            if len(colons)>1:
                colons.reverse()
                hour = colons.pop()
                if colons:
                    minute = colons.pop()
                else:
                    minute = 0
                if colons:
                    sec = colons.pop()
                else:
                    sec = 0
        except:
            pass
    if tz is None:
        tz = '+0000'
    if day is None:
        day = 0
    if hour is None:
        ( hour, minute, sec ) = ( 0, 0, 0 )
    if month is None:
        month = 0
    if year is None:
        year = 2005
    if date is None:
        date = 1
    tzm = ( int( tz[:3] ) * 60 + int( tz[3:] ) ) * 60
    offset = 0
    now = time.localtime()
    if time.daylight and now[-1]:
        offset = time.altzone
    else:
        offset = time.timezone
    tzm += offset
    try:
        t = time.mktime( ( year, month+1, date, hour, minute, sec, day, 1, -1 ) )
        return t - tzm
    except:
        return time.time()

def test_run():
    s = """From stuff
Received: yadayaya
From :Dave Cridland <dave@cridland.net>
Content-Type: text/plain

"""
    print s
    t = rfc822( s )
    print "* From header:"
    print t['From']
    print "* Dump:"
    print t.as_string()
    t.remove_content_headers()
    print "* Dump:"
    print t.as_string()

if __name__ == '__main__':
    test_run()
