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
import polymer.encode
import weakref

"""
Basic dialogs for handling add/remove/delete events for entries in datasets.

Used by the maildrop, imap, and personality treenodes.
"""

OK = 1
APPLY = 2
CANCEL = 3
YES = 4
NO = 5
button_order = [ OK, APPLY, CANCEL, YES, NO ]
if wx.Platform == '__WXGTK__':
    button_order.reverse()
icons = {
    wx.ICON_ASTERISK: wx.ART_INFORMATION,
    wx.ICON_ERROR: wx.ART_ERROR,
    wx.ICON_HAND: wx.ART_ERROR,
    wx.ICON_INFORMATION: wx.ART_INFORMATION,
    wx.ICON_QUESTION: wx.ART_QUESTION,
    wx.ICON_STOP: wx.ART_ERROR,
    wx.ICON_WARNING: wx.ART_WARNING
    }
save_dir = None

class UserCtrl( wx.TextCtrl ):
    def __init__( self, parent, id, initial, methctrl=None ):
        wx.TextCtrl.__init__( self, parent, id, initial )
        self.methctrl = methctrl
        self.saved = initial
        self.other_events = wx.EvtHandler()
        self.other_events.Bind( wx.EVT_SET_FOCUS, self.focus )

    def focus( self, event ):
        self.switch_on()
        if self.methctrl.GetStringSelection() == 'Anonymous':
            self.methctrl.SetStringSelection( 'Any' )
        event.Skip()

    def switch_on( self ):
        if self.IsEditable():
            return
        self.PopEventHandler()
        self.SetEditable(True)
        self.SetValue( self.saved )

    def switch_off( self ):
        if not self.IsEditable():
            return
        self.saved = self.GetValue()
        self.SetValue('')
        self.SetEditable(False)
        self.PushEventHandler( self.other_events )

class MailboxCtrlDropTarget( wx.PyDropTarget ):
    def __init__( self, ctrl ):
        import polymer.dragdrop
        wx.PyDropTarget.__init__( self )
        self.ctrl = weakref.ref( ctrl )
        self.data = polymer.dragdrop.URLDataObject()
        self.SetDataObject( self.data )

    def OnDragOver( self, x, y, d ):
        return wx.DragCopy

    def OnDrop( self, x, y ):
        return True

    def OnData( self, x, y, r ):
        try:
            import infotrope.url
            if not self.GetData():
                return wx.DragNone
            ut = self.data.GetURLs()
            if len(ut)!=1:
                return wx.DragNone
            u = infotrope.url.URL( ut[0] )
            if u.scheme not in ['imap','imaps']:
                return wx.DragNone
            self.ctrl().SetValue( u )
            return wx.DragCopy
        except:
            return wx.DragNone

class MailboxCtrl( wx.Panel ):
    def __init__( self, parent, wxid, value=None ):
        wx.Panel.__init__( self, parent, wxid, style=wx.SUNKEN_BORDER )
        self.value = value
        self.txt = wx.StaticText( self, -1, self.printable() )
        self.but = wx.Button( self, -1, "Clear" )
        self.sizer = wx.BoxSizer( wx.HORIZONTAL )
        self.sizer.Add( self.txt, 0, wx.ALIGN_CENTRE )
        self.sizer.Add( self.but, 0, wx.ALIGN_CENTRE|wx.ALL, border = 5 )
        self.SetSizer( self.sizer )
        self.sizer.Fit( self )
        self.SetAutoLayout( True )
        self.Bind( wx.EVT_BUTTON, self.click, self.but )
        self.drop = MailboxCtrlDropTarget( self )
        self.SetDropTarget( self.drop )

    def click( self, evt ):
        self.SetValue( None )

    def printable( self ):
        try:
            if self.value is not None and self.value.scheme=='imap':
                srv = wx.GetApp().connection( self.value )
                mi = srv.mbox_info( self.value.mailbox )
                return mi.displaypath[-1]
        except:
            return u'Unknown'
        return u'None'

    def SetValue( self, u ):
        self.value = u
        label = self.printable()
        self.txt.SetLabel( label )

    def GetValue( self ):
        return self.value

class ColourSelector( wx.Panel ):
    def __init__( self, parent, wxid, val ):
        wx.Panel.__init__( self, parent, wxid )
        self.sizer = wx.BoxSizer( wx.HORIZONTAL )
        self.check = wx.CheckBox( self, -1, "Use Colour" )
        self.sizer.Add( self.check, 0 )
        self.Bind( wx.EVT_CHECKBOX, self.click, self.check )
        self.SetValue( val )

    def click( self, evt ):
        if not self.check.GetValue():
            return
        dlg = wx.ColourDialog( self.GetParent(), wx.ColourData() )
        if wx.ID_OK!=dlg.ShowModal():
            return
        col = dlg.GetColourData().GetColour()
        if col.Ok():
            self.SetValue( (col.Red(),col.Green(),col.Blue()) )

    def SetValue( self, val ):
        self.check.SetValue( val is not None )
        if val is not None:
            self.SetBackgroundColour( wx.Colour( *val ) )

    def GetValue( self ):
        if self.check.GetValue():
            c = self.GetBackgroundColour()
            return (c.Red(),c.Green(),c.Blue())

class Base( wx.Dialog ):
    def __init__( self, parent, title, flags=wx.OK|wx.CANCEL ):
        wx.Dialog.__init__( self, parent, -1, title, style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER )
        self.buttons = {
            OK: ( "OK", self.Okay, wx.OK, wx.ID_OK ),
            CANCEL: ( "Cancel", self.Cancel, wx.CANCEL, wx.ID_CANCEL ),
            APPLY: ( "Apply", self.Apply, 0, -1 ),
            YES: ( "Yes", self.Yes, wx.YES_NO, wx.ID_YES ),
            NO: ( "No", self.No, wx.YES_NO, wx.ID_NO  )
            }
        self.flags = flags
        p = self
        self._sizer = wx.BoxSizer( wx.VERTICAL )
        self._fgsizer = None
        self.prompts = {}
        self.promptinfo = {}
        if (wx.ICON_MASK & self.flags) == 0:
            if ( wx.YES_NO & self.flags ) != 0:
                self.flags |= wx.ICON_QUESTION
        self._scrolling = None
        self.add_prompts( p )
        if self._scrolling is not None:
            self._scroll_inner.SetSizer( self._fgsizer )
            self._scroll_inner.SetAutoLayout( True )
            self._fgsizer.Fit( self._scroll_inner )
            self._fgsizer = self._scrolling
            self._scrolling.SetAutoLayout( True )
            self._scrolling.SetScrollRate( 20, 20 )
        self.added = False
        for x in [ wx.ICON_ASTERISK, wx.ICON_INFORMATION, wx.ICON_HAND, wx.ICON_STOP, wx.ICON_EXCLAMATION, wx.ICON_QUESTION, wx.ICON_WARNING ]:
            if ( x & self.flags ) != 0:
                b = wx.ArtProvider.GetBitmap( icons[x], wx.ART_MESSAGE_BOX )
                if b:
                    ns = wx.BoxSizer( wx.VERTICAL )
                    ss = wx.BoxSizer( wx.HORIZONTAL )
                    ss.Add( wx.StaticBitmap( p, -1, b ), 0, wx.ALL|wx.ALIGN_CENTER|wx.ALIGN_CENTER_VERTICAL, 5 )
                    ss.Add( self._sizer, 0, wx.EXPAND|wx.ALIGN_CENTER|wx.ALIGN_CENTER_VERTICAL )
                    if self._fgsizer is not None:
                        self._sizer.Add( self._fgsizer, 0, wx.EXPAND )
                    self.added = True
                    ns.Add( ss, 0, wx.EXPAND )
                    self._sizer = ns
                break
        if not self.added and self._fgsizer is not None:
            self._sizer.Add( self._fgsizer, 0, wx.EXPAND )
        self._sizer.Add( wx.StaticLine( self, -1 ), 0, wx.EXPAND )
        self.AddButtons( p )
        #self.AddOkayCancel( p, self.Okay, self.Cancel )
        p.SetSizer( self._sizer )
        p.SetAutoLayout( True )
        self._sizer.Fit( p )
        self.notify_complete = None

    def fgsizer( self ):
        if self._fgsizer is None:
            self._fgsizer = wx.FlexGridSizer( cols = 2, vgap = 0, hgap = 5 )
            self._fgsizer.AddGrowableCol( 1 )
        return self._fgsizer

    def AddButtons( self, p ):
        s = wx.BoxSizer( wx.HORIZONTAL )
        for y in button_order:
            x = self.buttons[y]
            if x[2] & self.flags:
                s.Add( wx.Button( p, x[3], x[0]) , 0, wx.ALL, 5 )
                wx.EVT_BUTTON( self, x[3], x[1] )
        if wx.Platform == '__WXGTK__':
            self._sizer.Add( s, 0, wx.ALIGN_RIGHT|wx.ALIGN_BOTTOM )
        elif wx.Platform == '__WXMSW__':
            self._sizer.Add( s, 0, wx.ALIGN_RIGHT|wx.ALIGN_BOTTOM )
        else:
            self._sizer.Add( s, 0, wx.ALIGN_CENTRE|wx.ALIGN_BOTTOM )

    def AddPreamble( self, p, text ):
        self._sizer.Add( wx.StaticText( p, -1, polymer.encode.encode_ui( text ) ), 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL, 5 )

    def AddGeneric( self, win, flags = 0, minsize = ( -1, -1 ), prop = None ):
        if prop is None:
            prop = 1
        self._sizer.Add( win, prop, wx.ALL|flags, 5 )
        self._sizer.SetItemMinSize( win, minsize[0], minsize[1] )

    def MakeScrollable( self, p ):
        w = wx.ScrolledWindow( p, -1 )
        s = wx.BoxSizer( wx.VERTICAL )
        np = wx.Panel( w, -1 )
        s.Add( np, 1, wx.EXPAND|wx.GROW|wx.ADJUST_MINSIZE )
        w.SetSizer( s )
        w.SetAutoLayout( True )
        s.FitInside( w )
        self._scrolling = w
        self._scroll_inner = np
        self._fgsizer = wx.FlexGridSizer( cols = 2, hgap = 0, vgap = 5 )
        self._fgsizer.AddGrowableCol( 1 )
        return np

    def AddPromptReal( self, p, text, attr = None, defvalue = None, password = False ):
        if defvalue is None:
            defvalue = ''
        defvalue = unicode(defvalue)
        self.fgsizer().Add( wx.StaticText( p, -1, polymer.encode.encode_ui( text ) ), 0, wx.ALIGN_RIGHT|wx.ALL|wx.ALIGN_CENTRE_VERTICAL, 5 )
        if password:
            self.prompts[attr] = wx.TextCtrl( p, -1, value=polymer.encode.encode_ui( defvalue ), style=wx.TE_PASSWORD )
        else:
            self.prompts[attr] = wx.TextCtrl( p, -1, value=polymer.encode.encode_ui( defvalue ) )
        self.fgsizer().Add( self.prompts[attr], 0, wx.EXPAND|wx.ALL|wx.ALIGN_CENTRE_VERTICAL, 5 )
        return self.prompts[attr]

    def AddColourPromptReal( self, p, text, attr = None, defvalue = None ):
        #print "Attr is",`attr`
        win = ColourSelector( p, -1, defvalue )
        self.AddGeneric2( p, text, win )
        self.prompts[attr] = win
        return win
    def AddColourPrompt( self, p, text, attr = None, defvalue = None ):
        return self.AddColourPromptReal( p, text, attr, defvalue )

    def AddCheckBoxReal( self, p, text, attr = None, defvalue = None ):
        if defvalue is None:
            defvalue = False
        self.prompts[attr] = wx.CheckBox( p, -1 )
        self.prompts[attr].SetValue(defvalue==True)
        self.fgsizer().Add( self.prompts[attr], 0, wx.ALIGN_RIGHT|wx.ALL|wx.ALIGN_CENTRE_VERTICAL, 5 )
        self.fgsizer().Add( wx.StaticText( p, -1, polymer.encode.encode_ui( text ) ), 0, wx.ALIGN_LEFT|wx.ALL|wx.ALIGN_CENTRE_VERTICAL, 5 )
        return self.prompts[attr]

    def AddCheckBox( self, p, text, attr = None, defvalue = None ):
        return self.AddCheckBoxReal( p, text, attr, defvalue )

    def AddMailboxPrompt( self, p, text, attr = None, defvalue = None ):
        self.prompts[attr] = MailboxCtrl( p, -1, defvalue )
        self.fgsizer().Add( wx.StaticText( p, -1, polymer.encode.encode_ui( text ) ), 0, wx.ALIGN_RIGHT|wx.ALL|wx.ALIGN_CENTRE_VERTICAL, 5 )
        self.fgsizer().Add( self.prompts[attr], 0, wx.EXPAND|wx.ALL|wx.ALIGN_CENTRE_VERTICAL, 5 )
        return self.prompts[attr]

    def AddGeneric2( self, p, text, win ):
        self.fgsizer().Add( wx.StaticText( p, -1, polymer.encode.encode_ui( text ) ), 0, wx.ALIGN_RIGHT|wx.ALL|wx.ALIGN_CENTRE_VERTICAL, 5 )
        self.fgsizer().Add( win, 0, wx.EXPAND|wx.ALL|wx.ALIGN_CENTRE_VERTICAL, 5 )

    def AddPrompt( self, p, text, attr = None, defvalue = None ):
        return self.AddPromptReal( p, text, attr, defvalue )

    def AddSecurityPrompt( self, p, methprompt, userprompt, attr, method=None, username=None, check=None ):
        if method is None:
            method = 'Anonymous'
        if username is None:
            username = ''
        s = wx.BoxSizer( wx.HORIZONTAL )
        cid = wx.NewId()
        self.fgsizer().Add( wx.StaticText( p, -1, methprompt ), 0, wx.ALIGN_RIGHT|wx.ALL|wx.ALIGN_CENTRE_VERTICAL, 5 )
        self.prompts[attr+'_method'] = wx.Choice( p, cid, choices=['Anonymous','Any','DIGEST-MD5','CRAM-MD5','Plain'] )
        self.prompts[attr+'_method'].SetStringSelection( method )
        self.promptinfo[cid] = attr
        s.Add( self.prompts[attr+'_method'], 0 )
        if check is not None:
            id = wx.NewId()
            s.Add( wx.Button( p, id, "Check Supported" ), 0, wx.LEFT, 5 )
            wx.EVT_BUTTON( self, id, check )
        self.fgsizer().Add( s, 0, wx.ALIGN_RIGHT|wx.ALL, 5 )
        self.fgsizer().Add( wx.StaticText( p, -1, userprompt ), 0, wx.ALIGN_RIGHT|wx.ALL|wx.ALIGN_CENTRE_VERTICAL, 5 )
        self.prompts[attr+'_username'] = UserCtrl( p, -1, username, self.prompts[attr+'_method'] )
        self.fgsizer().Add( self.prompts[attr+'_username'], 0, wx.EXPAND|wx.ALL, 5 )
        wx.EVT_CHOICE( self.prompts[attr+'_method'], -1, self.sasl_meth_change )
        self.sasl_meth_change( id=cid )

    def sasl_meth_change( self, event=None, id=None ):
        if event is not None:
            id = event.GetId()
        if self.prompts[self.promptinfo[id]+'_method'].GetStringSelection() == 'Anonymous':
            self.prompts[self.promptinfo[id]+'_method'].SetFocus()
            self.prompts[self.promptinfo[id]+'_username'].switch_off()
        else:
            self.prompts[self.promptinfo[id]+'_username'].switch_on()

    def decode_sasl_method( self, m ):
        m = m.upper()
        if m=='ANONYMOUS':
            return 'Anonymous'
        elif m=='*':
            return 'Any'
        return m

    def encode_sasl_method( self, m ):
        m = m.upper()
        if m=='ANY':
            return '*'
        return m
    
    def End( self, idx ):
        self.SetReturnCode( idx )
        if self.IsModal():
            self.EndModal( idx )
        else:
            self.Show( False )
        if self.notify_complete is not None:
            n = self.notify_complete
            self.notify_complete = None
            n()

    def Cancel( self, event ):
        self.End( wx.ID_CANCEL )

    def Okay( self, event ):
        self.End( wx.ID_OK )

    def Yes( self, event ):
        self.End( wx.ID_YES )

    def No( self, event ):
        self.End( wx.ID_NO )

    def Apply( self, event ):
        pass

class EntryDialog( Base ):
    def __init__( self, parent, entry=None, acap=None ):
        self.new = False
        self.entry = entry
        if entry is None:
            self.entry = self.new_entry()
            self.new = True
            title_pfx = "Create"
        else:
            title_pfx = "Edit"
        self.acap = acap
        if acap is None:
            self.acap = wx.GetApp().acap_home()
        Base.__init__( self, parent, "%s %s" % ( title_pfx, self.entry['entry'] ) )

    def AddPrompt( self, p, prompt, attr=None, defvalue=None ):
        if defvalue is None:
            if attr in self.entry:
                defvalue = self.entry[attr]
        return self.AddPromptReal( p, prompt, attr, defvalue )

    def AddCheckBox( self, p, prompt, attr=None, defvalue=None ):
        if defvalue is None:
            if attr in self.entry:
                defvalue = self.entry[attr]
        return self.AddCheckBoxReal( p, prompt, attr, defvalue )

    def AddColourPrompt( self, p, prompt, attr=None, defvalue=None ):
        if defvalue is None:
            if attr in self.entry:
                defvalue = self.entry[attr]
        return self.AddColourPromptReal( p, prompt, attr, defvalue )

class EntryDialogNew( Base ):
    def __init__( self, parent, deftitle=None, entry=None, dataset=None ):
        import infotrope.datasets.base
        self.new = False
        self.entry = entry
        if entry is None or isinstance( entry, str ):
            self.entry = dataset.new( entry )
            self.new = True
            title_pfx = deftitle or "Add New"
        else:
            title_pfx = "Edit %s" % self.entry['entry']
        self.dataset = dataset
        if dataset is None:
            self.dataset = infotrope.datasets.base.get_dataset( self.entry.cont_url )
        #print `self.entry`,`self.dataset`
        Base.__init__( self, parent, title_pfx )

    def AddPrompt( self, p, prompt, attr=None, defvalue=None, fallback=None ):
        if defvalue is None:
            if attr in self.entry:
                defvalue = self.entry[attr]
        if defvalue is None:
            defvalue = fallback
        return self.AddPromptReal( p, prompt, attr, defvalue )

    def AddCheckBox( self, p, prompt, attr=None, defvalue=None ):
        if defvalue is None:
            if attr in self.entry:
                defvalue = self.entry[attr]
        return self.AddCheckBoxReal( p, prompt, attr, defvalue )

    def AddColourPrompt( self, p, prompt, attr=None, defvalue=None ):
        if defvalue is None:
            if attr in self.entry:
                defvalue = self.entry[attr]
        return self.AddColourPromptReal( p, prompt, attr, defvalue )

    def Okay( self, event ):
        self.rename = None
        self.decode_ui()
        if not self.new and self.rename:
            del self.dataset[self.rename]
        self.entry.save()
        l = len( self.dataset )
        self.End( wx.ID_OK )

class MessageDialog( Base ):
    def __init__( self, parent, text, title, flags ):
        self.txt = text
        Base.__init__( self, parent, title, flags )

    def add_prompts( self, p ):
        self.AddPreamble( p, self.txt )
        
class TextEntryDialog( Base ):
    def __init__( self, parent, text, title, default=None ):
        self._prompt = text
        self._default = default
        if self._default is None:
            self._default = ''
        self._default = polymer.encode.encode_ui( self._default )
        Base.__init__( self, parent, title )

    def add_prompts( self, p ):
        self.AddPrompt( p, self._prompt, 'v', self._default )

    def GetValue( self ):
        return polymer.encode.decode_ui( self.prompts['v'].GetValue() )

class ErrorDialog( MessageDialog ):
    def __init__( self, parent, errtxt, title ):
        MessageDialog.__init__( self, parent, errtxt, title, wx.ICON_ERROR|wx.OK )

class PropsDialog( Base ):
    def __init__( self, parent, props, title, val_decoder = None ):
        self.props = props
        self.lc = None
        self.val_decoder = val_decoder or self.val_decoder_default
        Base.__init__( self, parent, title, wx.OK )

    def val_decoder_default( self, v ):
        return v
        
    def add_prompts( self, p ):
        l = wx.ListCtrl( self, -1, style=wx.LC_REPORT )
        x = 0
        l.InsertColumn( 0, "Item" )
        l.InsertColumn( 0, "Value" )
        for var,val in self.props.items():
            l.InsertStringItem( x, var )
            l.SetStringItem( x, 0, var )
            l.SetStringItem( x, 1, self.val_decoder( val ) )
            x += 1
        l.SetColumnWidth( 0, wx.LIST_AUTOSIZE )
        l.SetColumnWidth( 1, wx.LIST_AUTOSIZE )
        self.AddGeneric( l, wx.EXPAND )
           
class QueryDialog( Base ):
    def __init__( self, parent, preamble, title, options ):
        self.preamble = preamble
        self.options = options
        self.result = None
        Base.__init__( self, parent, title, wx.OK|wx.CANCEL|wx.ICON_QUESTION )

    def add_prompts( self, p ):
        self.AddPreamble( p, self.preamble )
        self.__choice = wx.Choice( self, -1, choices=[ x[0] for x in self.options ] )
        self.AddGeneric2( p, "Reply to:", self.__choice )

    def Okay( self, event ):
        r = [ x[1] for x in self.options if x[0] == self.__choice.GetStringSelection() ]
        if len(r):
            self.result = r[0]
        self.End( wx.ID_OK )
