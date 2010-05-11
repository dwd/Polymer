#
# Copyright 2004,2005 Dave Cridland <dave@cridland.net>
#
# This file forms part of Infotrope Polymer
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
# along with the Infotrope Python Library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
import infotrope.datasets.base
import infotrope.serverman
import infotrope.url
import infotrope.imap
import polymer.encode

class filters(infotrope.datasets.base.dataset_class):
    def __init__( self, url ):
        infotrope.datasets.base.dataset_class.__init__( self, url )

    def get_search_return( self ):
        return '*'

    def get_search_criteria( self ):
        return 'NOT EQUAL "entry" "i;octet" ""'

    def get_search_sort( self ):
        return ['vendor.infotrope.filter.priority', 'i;ascii-casemap']

    def factory( self, e ):
        if 'vendor.infotrope.filter.type' in e:
            if e['vendor.infotrope.filter.type']['value'] == 'single':
                return single
        return base

    def new( self, t=None, entryname=None ):
        if t is None:
            t = 'single'
        if entryname is None:
            import time
            import socket
            entryname = str(time.time()) + '@' + socket.gethostname()
        raw = {'entry':{'value':entryname}}
        return single( raw, self.url )

class base(infotrope.datasets.base.entry):
    def __init__( self, e, url ):
        infotrope.datasets.base.entry.__init__( self, e, url )

    def decode( self, attr, raw ):
        if attr in ['vendor.infotrope.filter.colour.foreground','vendor.infotrope.filter.colour.background']:
            return tuple(map(int,raw.split(',')))
        elif attr == 'vendor.infotrope.filter.name':
            return raw.decode('utf-8')
        elif attr in ['vendor.infotrope.filter.bold','vendor.infotrope.filter.italic','vendor.infotrope.filter.scanonly']:
            return raw == "1"
        elif attr == 'vendor.infotrope.filter.program':
            return raw.decode('utf-8')
        elif attr == 'vendor.infotrope.filter.subfilters':
            return [ self.referral( x ) for x in raw ]
        elif attr == 'vendor.infotrope.filter.description':
            return raw.decode('utf-8')
        return raw

    def encode( self, attr, polish ):
        raw = polish
        if attr in ['vendor.infotrope.filter.colour.foreground','vendor.infotrope.filter.colour.background']:
            raw = ','.join( [ str(x) for x in polish ] )
        elif attr in ['vendor.infotrope.filter.bold','vendor.infotrope.filter.italic','vendor.infotrope.filter.scanonly']:
            raw = None
            if polish:
                raw = "1"
        return raw

class single(base):
    def __init__( self, e, url ):
        base.__init__( self, e, url )
        
    def check_match( self, msg ):
        return True

infotrope.datasets.base.register_dataset_type( 'vendor.infotrope.filter', filters )

import polymer.dialogs
import wx

class FilterList( polymer.dialogs.Base ):
    def __init__( self, parent ):
        self._filters = wx.GetApp().filters()
        polymer.dialogs.Base.__init__( self, parent, "Edit View" )
        self.selected = None

    def add_prompts( self, p ):
        self.AddPreamble( p, "Select view to edit" )
        self.listing = wx.ListCtrl( p, -1, style=wx.LC_REPORT )
        count = 0
        self.listing.InsertColumn( 0, "View Name" )
        filters = self._filters
        for f in filters.entries():
            e = filters[f]
            item = wx.ListItem()
            item.SetText( e['vendor.infotrope.filter.name'] )
            item.SetId( count )
            if e['vendor.infotrope.filter.colour.foreground']:
                item.SetTextColour( e['vendor.infotrope.filter.colour.foreground'] )
            if e['vendor.infotrope.filter.colour.background']:
                item.SetBackgroundColour( e['vendor.infotrope.filter.colour.background'] )
            if e['vendor.infotrope.filter.bold'] or e['vendor.infotrope.filter.italic']:
                font = wx.SystemSettings.GetFont( wx.SYS_DEFAULT_GUI_FONT )
                if e['vendor.infotrope.filter.bold']:
                    font.SetWeight( wx.BOLD )
                if e['vendor.infotrope.filter.italic']:
                    font.SetStyle( wx.ITALIC )
                item.SetFont( font )
            self.listing.InsertItem( item )
            count += 1
        self.AddGeneric( self.listing, flags=wx.EXPAND, minsize=(-1,50) )
        self.Bind( wx.EVT_LIST_ITEM_SELECTED, self.selected, self.listing )
        self.descr = wx.StaticText( p, -1, "" )
        self.AddGeneric( self.descr, flags=wx.EXPAND, prop=0 )
        te = self.AddPrompt( p, "View Name", attr='filter', defvalue='' )
        self.Bind( wx.EVT_TEXT_ENTER, self.Okay, te )
        self.Bind( wx.EVT_TEXT, self.text_changed, te )
        self.listing.SetColumnWidth( 0, wx.LIST_AUTOSIZE )

    def unselect_all( self ):
        idx = self.listing.GetFirstSelected()
        while idx > -1:
            self.listing.SetItemState( idx, 0, wx.LIST_STATE_SELECTED|wx.LIST_STATE_FOCUSED )
            idx = self.listing.GetNextSelected( idx )

    def selected( self, evt ):
        self.selected = wx.GetApp().filters()[evt.GetIndex()]
        self.prompts['filter'].SetValue( evt.GetText() )
        self.descr.SetLabel( self._filters[evt.GetIndex()]['vendor.infotrope.filter.description'] )

    def text_changed( self, evt ):
        evt.Skip()
        if self.selected is not None and evt.GetString():
            if self.selected['vendor.infotrope.filter.name'] != polymer.encode.decode_ui( self.prompts['filter'].GetValue() ):
                self.unselect_all()
                self.descr.SetLabel( 'New' )
                self.selected = None

    def Okay( self, evt ):
        self.End( wx.ID_OK )
        

class EditFilter( polymer.dialogs.EntryDialogNew ):
    def __init__( self, parent, filt=None, name=None, dataset=None ):
        self.name = name
        if dataset is None:
            dataset = wx.GetApp().filters()
        polymer.dialogs.EntryDialogNew.__init__( self, parent, name or "New View", filt, dataset )

    def add_prompts( self, p ):
        self.AddPrompt( p, "Name", 'vendor.infotrope.filter.name', self.name )
        self.AddPrompt( p, "Description", 'vendor.infotrope.filter.description' )
        self.AddColourPrompt( p, "Foreground", 'vendor.infotrope.filter.colour.foreground' )
        self.AddColourPrompt( p, "Background", 'vendor.infotrope.filter.colour.background' )
        self.AddCheckBox( p, "Italic", 'vendor.infotrope.filter.italic' )
        self.AddCheckBox( p, "Bold", 'vendor.infotrope.filter.bold' )
        self.AddPrompt( p, "IMAP Search", 'vendor.infotrope.filter.program' )
        self.AddCheckBox( p, "Don't list", 'vendor.infotrope.filter.scanonly' )
        self.AddPrompt( p, "Priority", 'vendor.infotrope.filter.priority' )

    def decode_ui( self ):
        d = self.entry
        d['vendor.infotrope.filter.name'] = polymer.encode.decode_ui( self.prompts['vendor.infotrope.filter.name'].GetValue() )
        d['vendor.infotrope.filter.description'] = polymer.encode.decode_ui( self.prompts['vendor.infotrope.filter.description'].GetValue() )
        d['vendor.infotrope.filter.colour.foreground'] = self.prompts['vendor.infotrope.filter.colour.foreground'].GetValue()
        #if d['vendor.infotrope.filter.colour.foreground'] is not None:
        #    d['vendor.infotrope.filter.colour.foreground'] = ','.join( map(str,d['vendor.infotrope.filter.colour.foreground']) )
        d['vendor.infotrope.filter.colour.background'] = self.prompts['vendor.infotrope.filter.colour.background'].GetValue()
        #if d['vendor.infotrope.filter.colour.background'] is not None:
        #    d['vendor.infotrope.filter.colour.background'] = ','.join( map(str,d['vendor.infotrope.filter.colour.background']) )
        d['vendor.infotrope.filter.program'] = polymer.encode.decode_ui( self.prompts['vendor.infotrope.filter.program'].GetValue() )
        d['vendor.infotrope.filter.prority'] = self.prompts['vendor.infotrope.filter.priority'].GetValue()
        d['vendor.infotrope.filter.type'] = 'single'
        d['vendor.infotrope.filter.italic'] = int(self.prompts['vendor.infotrope.filter.italic'].GetValue())
        d['vendor.infotrope.filter.bold'] = int(self.prompts['vendor.infotrope.filter.bold'].GetValue())
        d['vendor.infotrope.filter.scanonly'] = int(self.prompts['vendor.infotrope.filter.scanonly'].GetValue())
