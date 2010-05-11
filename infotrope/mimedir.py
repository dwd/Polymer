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
'''
MIME text/directory parser, according to RFC2425.

Given a series of lines in this format, it should return a sequence of objects which have a name, a value, and optionally some parameters.

The parameters are unordered.
'''

class Line:
    def __init__( self, name, value, params=None ):
        self.name = name
        self.value = value
        self.params = {}
        if params is not None:
            self.params = params

    def __getitem__( self, what ):
        if self.params is None:
            return None
        if what not in self.params:
            return None
        return self.params[what]

    def __str__( self ):
        return self.value

    def asString( self ):
        s = ''+self.name
        if self.params is not None and len(self.params):
            s += ';'
            first = True
            for p,v in self.params.items():
                if first:
                    first=False
                else:
                    s += ';'
                s += p + '='
                first = True
                for x in v:
                    if first:
                        first = False
                    else:
                        s += ','
                    written = False
                    for c in ';:,':
                        if c in x:
                            s += '"'+x+'"'
                            written = True
                            break
                    if not written:
                        s += x
        s += ':' + self.value + '\r\n'
        return s

class MimeDirectory:
    def __init__( self ):
        self.contents = []
        self.contentsByName = {}

    def parse( self, src ):
        ''' Extract and unfold one line at a time, passing onto the parse_line method. '''
        b = ''
        for x in src:
            #print "Source line: %s" % `x`
            x = x.strip( '\r\n' )
            # Hack to cope with VCARD 2.1
            if -1!=b.lower().find( 'encoding=quoted-printable' ):
                #print 'Found possible QP.'
                if b[-1:]=='=':
                    #print 'Last char is =, likely continue.'
                    b += '\n'
                    b += x
                else:
                    self.parse_line( b )
                    b = x
            elif x[0]==' ' or x[0]=='\t':
                b += x[1:]
            else:
                if b!='':
                    self.parse_line( b )
                b = x
        if b!='':
            self.parse_line( b )

    def parse_line( self, line ):
        ''' Parse one unfolded line. '''
        #print "Unfolded line: %s" % `line`
        br = line.index( ':' )
        Name = ''
        Value = ''
        Params = {}
        state = 'n'
        pn = ''
        pvc = ''
        pv = []
        for x in line:
            if state=='pn':
                if x=='=':
                    state = 'pvs'
                elif x==';':
                    pv = [pn]
                    pn = 'TYPE'
                    if pn not in Params:
                        Params[pn] = []
                    Params[pn] += pv
                    pn, pvc, pv = '','',[]
                    state = 'pn'
                elif x==':':
                    pv = [pn]
                    pn = 'TYPE'
                    if pn not in Params:
                        Params[pn] = []
                    Params[pn] += pv
                    pn, pvc, pv = '','',[]
                    state = 'v'
                else:
                    pn += x
            elif state=='pvs':
                if x=='"':
                    state = 'pvq'
                else:
                    state = 'pvr'
                    pvc = x
            elif state=='pvr':
                if x==',':
                    pv.append( pvc )
                    pvc = ''
                    state = 'pvs'
                elif x==';':
                    pv.append( pvc )
                    if pn not in Params:
                        Params[pn] = []
                    Params[pn] += pv
                    pn, pvc, pv = '','',[]
                    state = 'pn'
                elif x==':':
                    pv.append( pvc )
                    if pn not in Params:
                        Params[pn] = []
                    Params[pn] += pv
                    pn, pvc, pv = '','',[]
                    state = 'v'
                else:
                    pvc += x
            elif state=='pvq':
                if x=='"':
                    state = 'pvqt'
                    pv.append(pvc)
                    pvc = ''
                elif x=='\\':
                    state = 'pvqe'
                else:
                    pvc += x
            elif state=='pvqe':
                pvc += x
                state = 'pvq'
            elif state=='pvqt':
                if x==',':
                    state = 'pvs'
                elif x==';':
                    if pn not in Params:
                        Params[pn] = []
                    Params[pn] += pv
                    pn, pvc, pv = '','',[]
                    state = 'pn'
                elif x==':':
                    state = 'v'
                else:
                    raise "Unexpected character %s" % `x`
            elif state=='v':
                Value += x
            elif state=='n':
                if x==';':
                    state = 'pn'
                elif x==':':
                    state = 'v'
                else:
                    Name += x
            else:
                raise "Unknown state %s while parsing line." % `state`
        if pn!='':
            raise "Unexpectedly have unassigned parameter name %s, state is %s." % ( `pn`, state )
        if pvc!='':
            raise "Unexpectedly have unassigned parameter value %s, state is %s." % ( `pn`, state )
        if state!='v':
            raise "State not value: %s" % v
        #print 'LINE: %s %s %s' % ( `Name`, `Value`, `Params` )
        t = len( self.contents )
        self.contents.append( Line( Name, Value, Params ) )
        if Name not in self.contentsByName:
            self.contentsByName[Name] = []
        self.contentsByName[Name].append( t )
        return self.contents[t]

    def write( self ):
        import sys
        for x in self.contents:
            sys.stdout.write( x.asString() )

    def asComponents( self, pos=None ):
        if pos is None:
            pos = 0
        c = None
        if self.contents[pos].name=='BEGIN':
            c = Component( self.contents[pos].value.upper() )
            pos += 1
        else:
            cn = ''
            if 'PROFILE' in t:
                t = self.contentsByName['PROFILE']
                if len(t):
                    cn = t[0]
            c = Component( cn )
        while pos<len(self.contents):
            if self.contents[pos].name=='END':
                return c,pos
            if self.contents[pos].name=='BEGIN':
                sc,pos = self.asComponents( pos )
                c.append( sc )
            else:
                c.append( self.contents[pos] )
            pos += 1
        return c,pos
            

class Component:
    def __init__( self, name ):
        self.contents = []
        self.contentsByName = {}
        self.componentsByName = {}
        self.name = name

    def append( self, x ):
        t = len(self.contents)
        self.contents.append( x )
        if isinstance( x, Line ):
            if x.name not in self.contentsByName:
                self.contentsByName[x.name] = []
            self.contentsByName[x.name].append( t )
        else:
            if x.name not in self.componentsByName:
                self.componentsByName[x.name] = []
            self.componentsByName[x.name].append( t )

    def dump(self,pfx=None):
        if pfx is None:
            pfx = ''
            print ":: Root Component ::"
        print "%s::Component Start, type %s" % ( pfx, `self.name` )
        for x in self.contents:
            if isinstance( x, Line ):
                print "%s:: Line, name %s, params %s, value %s." % ( pfx, `x.name`, `x.params`, `x.value` )
            else:
                x.dump( pfx+' ' )
        print "%s::Component End, type %s" % ( pfx, `self.name` )

if __name__=='__main__':
    #f = open( '/home/dwd/Kellie-Ann_Cridland.vcf' )
    f = open( '/home/dwd/UK32Holidays.ics' )
    p = MimeDirectory()
    p.parse( f )
    p.write()
    c,pos = p.asComponents()
    c.dump()
