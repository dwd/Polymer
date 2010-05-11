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
from StringIO import StringIO

class para:
    def __init__( self, qd, txt, delsp=False ):
        self.txt = txt
        self.quote_depth = qd
        self.soft = False
        self.crlf = False
        self.flowed = True
        self.multiline = False
        if self.txt[-1:]==' ':
            self.soft = True
            if delsp: # Trim off SP.
                self.txt = self.txt[:-1]
        if self.txt == '' or self.txt == ' ':
            self.crlf = True

    def append( self, para ):
        if not self.soft:
            raise "Attempt to append to non-soft FF para"
        if self.quote_depth!=para.quote_depth:
            raise "Attempt to append different quote depths."
        self.multiline = True
        self.txt += para.txt
        self.soft = para.soft
        self.crlf = para.crlf

    def asText( self ):
        txt = self.txt
        if self.quote_depth!=0:
            txt = '>' * self.quote_depth + ' ' + txt
        txt += '\n'
        return txt

def parse( txt, composer=False, part=None ):
    paras = []
    f = StringIO( txt )
    sigmode = False
    delsp = False
    if part is not None:
        if 'DELSP' in part.params:
            if part.params['DELSP'].lower() == 'yes':
                delsp = True
    for l in f:
        qd = 0
        l = l.rstrip( '\r\n' )
        #print "1:",`l`
        if l=='-- ':
            sigmode = True
        if len(l)>0 and l=='_'*len(l):
            sigmode = True
        if not sigmode:
            while l[0:1]=='>':
                qd+=1
                l = l[1:]
            if l[0:1]==' ':
                l = l[1:]
            if composer:
                l.rstrip( ' ' )
            #print "2:",qd,`l`
            if len(paras):
                top = paras[-1]
                if composer and len(l)==0 and top.crlf:
                    top.soft = True
                    qd = top.quote_depth
                    top.append( para( qd, l, delsp=delsp ) )
                if top.quote_depth==qd and top.soft:
                    #print "Appending."
                    top.append( para( qd, l, delsp=delsp ) )
                else:
                    #print "Adding, qd/soft differ"
                    paras.append( para( qd, l, delsp=delsp ) )
            else:
                #print "Adding, first para"
                paras.append( para( qd, l, delsp=delsp ) )
        else:
            #print "Adding, sigmode."
            p = para( 0, l )
            p.flowed = False
            paras.append( p )
    return paras
