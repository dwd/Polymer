#
# Copyright 2004,2005 Dave Cridland <dave@cridland.net>
#
# This file forms part of Infotrope Polymer.
#
# Infotrope Polymer is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# Infotrope Polymer is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with Infotrope Polymer; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
import wx
import infotrope.url
import os.path
import sys
import weakref

class PyURLDataObject(wx.CustomDataObject):
    def __init__( self, u=None ):
        df = wx.DataFormat( wx.DF_FILENAME )
        wx.CustomDataObject.__init__( self, df )
        if u is not None:
            if isinstance(u,list):
                self.data = u
            else:
                self.data = [u]
        else:
            self.data = []
        self._reset_data()

    def _reset_data( self ):
        self.xmit = None
        self.SetData( self._xmit() )

    def AddFile( self, fname ):
        self.data.append( 'file://' + socket.getfqdn() + fname )
        self._reset_data()

    def AddURL( self, url ):
        self.data.append( url )
        self._reset_data()

    def SetURL( self, url ):
        self.data = [url]
        self._reset_data()

    def GetURL( self ):
        self._unpack_data()
        return self.data[0]

    def GetURLs(self):
        self._unpack_data()
        return self.data

    def GetTitle( self ):
        return ''

    def _xmit( self ):
        if self.xmit is None:
            self.xmit = ''
            for x in self.data:
                self.xmit += str(x)
                self.xmit += '\r\n'
        return self.xmit

    def _unpack_data( self ):
        s = self.GetData()
        self.data = []
        self.data = [ x.strip() for x in s.split('\n') if len(x) and x[0]!='#' ]
        return True

_node_key = 0
_node_list = weakref.WeakValueDictionary()

class PyMozURLDataObject( wx.CustomDataObject ):
    def __init__( self, u = None, t = None, format = None, delim = None, charset = None, node = None ):
        if format is None:
            f = wx.CustomDataFormat( 'text/x-moz-url' )
        else:
            f = wx.CustomDataFormat( format )
        if delim is None:
            self.delim = ' '
        else:
            self.delim = delim
        if charset is None:
            self.charset = 'ucs2'
        else:
            self.charset = charset
        wx.CustomDataObject.__init__( self, f )
        self.url = u
        self.title = t
        self.node = None
        if self.url is None:
            self.url = ''
        if self.title is None:
            self.title = ''
        if self.delim == '':
            self.title = ''
        elif node is not None:
            self.node = _node_holder( node )
        self._pack_data()

    def _pack_data( self ):
        if self.url == '':
            t = ''
        else:
            tx = u''
            if self.node is not None:
                global _node_key
                global _node_list
                tx = _node_key
                _node_key += 1
                _node_list[ tx ] = self.node
                tx = self.delim + u'%d' % tx
            t = ( unicode( str(self.url) + self.delim ) + self.title + tx ).encode( self.charset )
        self.SetData( t )

    def _unpack_data( self ):
        self.url = None
        self.title = None
        self.node = None
        tmp = self.GetData()
        u = tmp.decode( self.charset )
        t = u''
        if self.delim!='':
            us = u.split( self.delim )
            u = us[0]
            us = us[1:]
            if len(us):
                try:
                    if int(us[-1]) in _node_list:
                        self.node = _node_list[int(us[-1])]
                        us = us[0:-1]
                except:
                    pass
                t = self.delim.join(us)
        self.url = u.encode( 'utf-8' )
        self.title = t

    def GetURL( self ):
        self._unpack_data()
        return self.url

    def GetTitle( self ):
        self._unpack_data()
        return self.title

    def GetNode( self ):
        self._unpack_data()
        if self.node is not None:
            return self.node.node

class _node_holder:
    def __init__( self, node ):
        self.node = node

class _URLDataObject( wx.DataObjectComposite ):
    def __init__( self, u = None, t = None, node = None ):
        wx.DataObjectComposite.__init__( self )
        self.formats = []
        multi = False
        if u is not None:
            if isinstance(u,list):
                multi = True
        if not multi:
            self.AddLocal( PyMozURLDataObject( u, t, format = '_NETSCAPE_URL', delim='\n', charset='utf-8', node=node ) )
            self.AddLocal( PyMozURLDataObject( u, t, delim='\n', charset='utf_16_le' ) )
        self.AddLocal( PyURLDataObject( u ) )
        if multi:
            uu = '\n'.join([str(i) for i in u])
        else:
            uu = str(u)
        self.AddLocal( PyMozURLDataObject( uu, format = 'UTF8_STRING', delim = '', charset = 'utf-8' ) )
        self.AddLocal( wx.TextDataObject( uu ) )

    def AddLocal( self, t ):
        self.formats.append( t )
        self.Add( t )

    def _supported_format( self, do, f ):
        try:
            return self.IsSupported( f )
        except:
            return self.IsSupportedFormat( f )

    def GetNode( self ):
        t = self.formats[0]
        x = t.GetFormat()
        if self._supported_format( t, x ):
            if t.GetDataSize():
                try:
                    return t.GetNode()
                except:
                    return None

    def GetURLs( self ):
        for t in self.formats:
            x = t.GetFormat()
            if self._supported_format( t, x ):
                if t.GetDataSize():
                    try:
                        u = t.GetURLs()
                        return u
                    except:
                        try:
                            u = [t.GetURL()]
                            return u
                        except:
                            u = t.GetText().split('\n')
                            return u
                    
    def GetTitle( self ):
        for t in self.formats:
            x = t.GetFormat()
            if self._supported_format( t, x ):
                if t.GetDataSize():
                    try:
                        u = t.GetTitle()
                        if len(u)!=0:
                            return u
                    except:
                        pass

def URLDataObject( u = None, t = None, node = None ):
    multi = False
    if u is not None:
        if isinstance(u,list):
            if len(u) == 0:
                u = None
            elif len(u) == 1:
                u = u[0]
            else:
                multi = True
    if multi:
        return _URLDataObject( u, t, node )
    if wx.Platform=='__WXGTK__':
        return _URLDataObject( u, t, node )
    else:
        tmp = wx.URLDataObject()
        if u is not None:
            tmp.SetURL( str(u) )
    return tmp
    
