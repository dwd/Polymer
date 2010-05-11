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

EVT_STATUS_UPDATE_ID = wx.NewId()

class EventStatusUpdate( wx.PyEvent ):
    def __init__( self, msg ):
        wx.PyEvent.__init__( self )
        self.SetEventType( EVT_STATUS_UPDATE_ID )
        self._message = msg

    def GetMessage( self ):
        return self._message

def EVT_STATUS_UPDATE( win, func ):
    win.Connect( -1, -1, EVT_STATUS_UPDATE_ID, func )
