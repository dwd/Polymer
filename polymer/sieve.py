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
import infotrope.managesieve
import polymer.encode
import polymer.dialogs
import wx

"""Classes for handling and editing SIEVE scripts."""

class sieve_open(polymer.dialogs.Base):
    def __init__( self, parent, sieve ):
        self._sieve = sieve
        self.script = None
        polymer.dialogs.Base.__init__( self, parent, "Open SIEVE Script" )

    def add_prompts( self, p ):
        self.AddPreamble( p, "Select a SIEVE script to open" )
        self.listing = wx.ListCtrl( p, -1, style=wx.LC_REPORT )
        count = 0
        self.listing.InsertColumn( 0, "Script Name" )
        for sc in self._sieve.scripts():
            self.listing.InsertStringItem( count, sc )
            if sc == self._sieve.active_script():
                self.listing.SetItemTextColour( count, wx.RED )
            count = count + 1
        self.AddGeneric( self.listing, flags=wx.EXPAND, minsize=(-1,50) )
        wx.EVT_LIST_ITEM_SELECTED( self, -1, self.selected )
        self.AddPrompt( p, "Script", attr='script', defvalue='' )
        #self.AddOkayCancel( p, self.Okay, self.Cancel )

    def selected( self, event ):
        id = event.GetIndex()
        txt = event.GetText()
        self.prompts['script'].SetValue( txt )

    def Okay( self, event ):
        self.script = polymer.encode.decode_ui( self.prompts['script'].GetValue() )
        self.SetReturnCode( wx.ID_OK )
        self.EndModal( wx.ID_OK )

ID_DISCARD = wx.NewId()
ID_SAVE = wx.NewId()
ID_SAVE_ACTIVE = wx.NewId()
ID_SAVE_AS = wx.NewId()

class Editor( wx.Frame ):
    def __init__( self, parent, sieve, script=None ):
        self.script_name = script
        if self.script_name is None:
            self.script_name = 'New Script'
        wx.Frame.__init__( self, parent, -1, "Edit script %s - Infotrope Polymer" % self.script_name, name='polymer' )
        self.CreateStatusBar()
        m = wx.Menu()
        m.Append( ID_SAVE, "&Save", "Save script to server" )
        m.Append( ID_SAVE_ACTIVE, "Save and Acti&vate", "Save script and activate" )
        m.Append( ID_SAVE_AS, "Save &As...", "Save to server with new name" )
        m.Append( ID_DISCARD, "&Quit", "Quit without saving" )

        mb = wx.MenuBar()
        mb.Append( m, "&Script" )

        self.SetMenuBar( mb )

        self.book = wx.Notebook( self, -1 )
        self.editor = wx.stc.StyledTextCtrl( self.book, -1 )
        self.book.AddPage( self.editor, "Source" )

        wx.EVT_MENU( self, ID_DISCARD, self.discard )
        wx.EVT_MENU( self, ID_SAVE, self.save )
        wx.EVT_MENU( self, ID_SAVE_ACTIVE, self.save_active )
        wx.EVT_MENU( self, ID_SAVE_AS, self.save_as )

        wx.EVT_CLOSE( self, self.close )

        if script is not None:
            try:
                self.editor.SetText( sieve.getscript( self.script_name ) )
                self.editor.SetSavePoint()
            except:
                pass
        
        self.sieve = sieve

    def save( self, event ):
        self.real_save()

    def save_as( self, event ):
        ds = sieve_open( self, self.sieve )
        if ds.ShowModal() == wx.ID_OK:
            self.real_save( ds.script )

    def real_save( self, script_name=None ):
        try:
            if script_name is not None:
                if not self.editor.GetModify():
                    return
            else:
                script_name = self.script_name
            self.sieve.putscript( script_name, self.editor.GetText() )
            self.script_name = script_name
            self.SetTitle( script_name )
            self.editor.SetSavePoint()
            return True
        except infotrope.base.connection.exception, e:
            dlg = polymer.dialogs.MessageDialog( self, "Error while saving: %s" % ( str(e) ), "SIEVE Script Error", wx.ICON_ERROR|wx.OK )
            dlg.ShowModal()
        return False

    def save_active( self, event ):
        if self.real_save():
            self.sieve.setactive( self.script_name )

    def discard( self, event ):
        if self.discard_check():
            self.Close( True )

    def close( self, event ):
        if self.discard_check():
            event.Skip()

    def discard_check( self ):
        if not self.editor.GetModify():
            return True
        if wx.ID_YES == wx.MessageDialog( self, "Script unsaved, really quit?", "Infotrope Polymer", wx.ICON_INFORMATION|wx.YES_NO ).ShowModal():
            self.editor.SetSavePoint()
            return True
        return False

