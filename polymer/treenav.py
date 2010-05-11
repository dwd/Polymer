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
import polymer.dragdrop

import weakref

"""
This is a more useful (to me) interface to wx.TreeCtrl and friends.

Essentially, it wraps everything in Python classes.
"""

class NavigatorDropTarget( wx.PyDropTarget ):
    def __init__( self, tree ):
        wx.PyDropTarget.__init__( self )
        self.tree = weakref.ref( tree )
        self.data = polymer.dragdrop.URLDataObject()
        self.SetDataObject( self.data )
        
    def OnDragOver( self, x, y, d ):
        d = self.tree().drag_over( x, y, d )
        return d

    def OnDrop( self, x, y ):
        t = self.tree().on_drop( x, y )
        return t

    def OnData( self, x, y, r ):
        if self.GetData():
            return self.tree().on_data( x, y, self.data, r )
        else:
            r = wx.DragNone
            return r

    def set_data( self, d ):
        return
        if d is not None:
            self.data = d
            self.SetDataObject( self.data )

class Navigator( wx.TreeCtrl ):
    def __init__( self, parent, frame, nb ):
        if '__WXMSW__' in wx.PlatformInfo:
            style = wx.TR_HAS_BUTTONS
            self.root_shown = True
        else:
            style = wx.TR_HAS_BUTTONS|wx.TR_HIDE_ROOT
            self.root_shown = False
        wx.TreeCtrl.__init__( self, parent, -1, style=style )
        self.images = []
        self.imlist = None
        self.root = TreeNode( self, None, "Polymer", True )
        self._shutdown = False
        self._parent = parent
        self._frame = frame
        wx.EVT_TREE_ITEM_EXPANDING( self, self.GetId(), self.try_expand )
        wx.EVT_TREE_ITEM_COLLAPSED( self, self.GetId(), self.collapsed )
        wx.EVT_TREE_SEL_CHANGED( self, self.GetId(), self.select )
        wx.EVT_TREE_ITEM_RIGHT_CLICK( self, self.GetId(), self.context_menu )
        wx.EVT_TREE_BEGIN_DRAG( self, self.GetId(), self.begin_drag )
        wx.EVT_TREE_ITEM_ACTIVATED( self, self.GetId(), self.activated )
        self._nb = nb
        self.context_active = None
        self._timer = wx.GetApp().timer( self.ticktock )
        self._timer.Start( 1000 )
        self.drop_target = NavigatorDropTarget( self )
        self.SetDropTarget( self.drop_target )

    def add_icon_file( self, fname ):
        path = wx.GetApp().find_image( fname )
        if path in self.images:
            return self.images.index( path )
        self.images.append( path )
        i = wx.Image( self.images[0], wx.BITMAP_TYPE_ANY )
        il = wx.ImageList( i.GetWidth(), i.GetHeight() )
        il.Add( wx.BitmapFromImage( i ) )
        for x in self.images[1:]:
            il.Add( wx.Bitmap( x, wx.BITMAP_TYPE_ANY ) )
        self.SetImageList( il )
        self.imlist = il
        return len(self.images)-1
        
    def ticktock( self ):
        if self.root_shown:
            self.root.Expand()
        self.root.update()
        page = self._nb.GetSelection()
        if page >= 0:
            p = self._nb.GetPage( page )
            if p is not None:
                p.update()

    def add_main( self, type ):
        return type( self, self.root )

    def expand_at( self, x, y ):
        item,flags = self.HitTest( (x,y) )
        if item is not None and item.Ok():
            d = self.GetPyData( item )
            if d is not None:
                d.Expand()

    def drag_over( self, x, y, d ):
        item,flags = self.HitTest( (x,y) )
        if item is not None and item.Ok():
            if y < 10.0:
                item2 = self.GetPrevSibling( item )
                if item2 is None or not item2.Ok():
                    item2 = self.GetItemParent( item )
                if item2 is not None and item2.Ok():
                    self.ScrollTo( item2 )
                    return wx.DragNone
            if y > ( self.GetClientSize()[1] - 10.0 ):
                item2 = self.GetNextSibling( item )
                if item2 is None or not item2.Ok():
                    item2 = self.GetItemParent( item )
                    if item2 is not None and item2.Ok():
                        item2 = self.GetNextSibling( item2 )
                if item2 is not None and item2.Ok():
                    self.ScrollTo( item2 )
                    return wx.DragNone
            o = self.GetPyData( item )
            if o is not None:
                d = o.drag_over( d )
                return d
        d = wx.DragNone
        return d

    def on_drop( self, x, y):
        item,flags = self.HitTest( (x,y) )
        if item is not None and item.Ok():
            d = self.GetPyData( item )
            if d is not None:
                return d.drop()
        return False

    def on_data( self, x, y, what, r ):
        item,flags = self.HitTest( (x,y) )
        if item is not None and item.Ok():
            d = self.GetPyData( item )
            if d is not None:
                return d.data( what, r )
    
    def try_expand( self, event ):
        if self._shutdown:
            event.Veto()
            return
        d = self.GetPyData( event.GetItem() )
        if d is None:
            event.Skip()
        if d.try_expand( event ):
            event.Skip()
        else:
            event.Veto()

    def collapsed( self, event ):
        if self._shutdown:
            event.Veto()
            return
        d = self.GetPyData( event.GetItem() )
        if d is not None:
            d.collapsed( event )

    def select( self, event ):
        if self._shutdown:
            event.Veto()
            return
        item = event.GetItem()
        if not item.Ok():
            event.Veto()
            return
        d = self.GetPyData( item )
        if d is not None:
            d.select( event )

    def activated( self, event ):
        if self._shutdown:
            event.Veto()
            return
        item = event.GetItem()
        if not item.Ok():
            event.Veto()
            return
        d = self.GetPyData( item )
        if d is not None:
            d.Activated( event )

    def context_menu( self, event ):
        if self._shutdown:
            event.Veto()
            return
        item = event.GetItem()
        if not item.Ok():
            event.Veto()
            return
        d = self.GetPyData( item )
        if d is not None:
            self.context_active = d
            d.context_menu( event, self._frame )

    def notebook( self ):
        return self._nb
    
    def shutdown( self ):
        self._shutdown = True

    def update( self ):
        if self._shutdown:
            return
        #self._nb.Refresh()
        self.Refresh()
        self._frame.update()

    def begin_drag( self, event ):
        d = self.GetPyData( event.GetItem() )
        if d is not None:
            d.begin_drag( event )

class TreeNode:
    def __init__( self, tree, pid, name, kids=False, images=None ):
        self.panel = None
        self._name = name or '<unnamed>'
        if pid is not None:
            pos = None
            if isinstance(pid,tuple):
                pid,pos = pid
            if isinstance(pid,TreeNode):
                pid = pid._id
            if pos is None:
                self._id = tree.AppendItem( pid, polymer.encode.encode_ui(self._name), data = wx.TreeItemData( self ) )
            else:
                self._id = tree.InsertItemBefore( pid, pos, polymer.encode.encode_ui( self._name ), data = wx.TreeItemData( self ) )
        else:
            self._id = tree.AddRoot( polymer.encode.encode_ui(self._name), data = wx.TreeItemData( self ) )
        self._tree_ref = weakref.ref( tree )
        self._pid = pid
        self._havechildren = kids
        self._menu = None
        if self._pid is not None:
            tree.SetItemHasChildren( self._pid )
            o = tree.GetPyData( self._pid )
            if o is not None:
                o._havechildren = True
        if self._havechildren:
            tree.SetItemHasChildren( self._id )
        self.set_images( images )
        self.update_every = -1
        self._update_counter = 0

    def GetParent( self ):
        if self._pid is not None:
            return self.tree().GetPyData( self._pid )

    def set_images( self, images=None ):
        tree = self._tree_ref()
        if tree is None:
            return
        self._images = images or {}
        for which,fname in self._images.items():
            n = tree.add_icon_file( fname )
            tree.SetItemImage( self._id, n, which )

    def name( self ):
        return self._name

    def id( self ):
        return self._id

    def __repr__( self ):
        return "<TreeNode type %s with name %s, and children: %s>" % ( self.__class__.__name__, self._name, self._havechildren )

    def Expand( self ):
        if self._havechildren:
            self.tree().Expand( self._id )

    def Delete( self ):
        tree = self._tree_ref()
        if tree is None:
            return
        id,cookie = tree.GetFirstChild( self._id )
        while id.IsOk():
            o = tree.GetPyData( id )
            o.Delete()
            id,cookie = tree.GetNextChild( self._id, cookie )
        self.local_delete()
        tree.Delete( self._id )

    def IsVisible( self ):
        return self.tree().IsVisible( self._id )

    def find( self, name ):
        tree = self._tree_ref()
        if tree is None:
            return None
        id,cookie = tree.GetFirstChild( self._id )
        while id.IsOk():
            o = tree.GetPyData( id )
            if o.name() == name:
                return o
            id,cookie = tree.GetNextChild( self._id, cookie )
        return None

    def child_nodes( self ):
        tree = self._tree_ref()
        if tree is None:
            return {}
        kinder = {}
        id,cookie = tree.GetFirstChild( self._id )
        while id.IsOk():
            o = tree.GetPyData( id )
            kinder[o.name()] = o
            id,cookie = tree.GetNextChild( self._id, cookie )
        return kinder

    def local_delete( self ):
        pass

    def tree( self ):
        return self._tree_ref()

    def try_expand( self, event ):
        return True

    def get_panel( self ):
        return None
    
    def select( self, event ):
        if self.panel is None:
            self.panel = self.get_panel()
            self.tree().update()
        elif self.panel is not None:
            self.panel.foreground()

    def Activated( self, event ):
        pass

    def collapsed( self, event ):
        pass

    def context_menu( self, event, frame ):
        pass

    def local_update( self, force=False ):
        pass

    def update( self, force=False ):
        tree = self._tree_ref()
        if tree is None:
            return
        id,cookie = tree.GetFirstChild( self._id )
        while id.IsOk():
            o = tree.GetPyData( id )
            o.update( force )
            id,cookie = tree.GetNextChild( self._id, cookie )
        if not force:
            if self.update_every < 0:
                return
            else:
                self._update_counter += 1
                if self._update_counter < self.update_every:
                    return
        self._update_counter = 0
        self.local_update( force )

    def begin_drag( self, event ):
        event.Veto()

    def drag_over( self, type ):
        self.Expand()
        return wx.DragNone

    def drop( self ):
        return False

    def data( self, what, how ):
        how = wx.DragNone
        return how

    def have_children( self ):
        tree = self._tree_ref()
        if tree is None:
            return False
        id,cookie = tree.GetFirstChild( self._id )
        if not id.IsOk():
            return False
        return self._havechildren

class NavPanel:
    def __init__( self, notebook, name, init_func, node ):
        self.node = node
        self._menu = None
        #notebook.Show( False )
        init_func( self, notebook, -1 )
        notebook.AddPage( self, name, select=True )
        #notebook.Show( True )

    def foreground( self ):
        for i in range( self.GetParent().GetPageCount() ):
            if self is self.GetParent().GetPage( i ):
                self.GetParent().SetSelection( i )
                #self.GetParent().AdvanceSelection()
                #self.GetParent().AdvanceSelection( False )
                break

    def delete( self, evt=None ):
        self.node.panel = None
        if self is self.GetParent().GetPage( self.GetParent().GetSelection() ):
            self.GetParent().AdvanceSelection()
        for i in range( self.GetParent().GetPageCount() ):
            if self is self.GetParent().GetPage( i ):
                self.GetParent().RemovePage( i )
                break

    def delete_others( self, evt=None ):
        self.foreground()
        me = self.GetParent().GetSelection()
        i = 0
        while i < self.GetParent().GetPageCount():
            if i==me:
                i += 1
            else:
                self.GetParent().GetPage( i ).delete()
                if i < me:
                    me -= 1

    def update( self, full=False ):
        pass

    def PanelMenu( self ):
        if self._menu is None:
            self._menu = wx.Menu()
            mi = self._menu.Append( -1, "Close", "Close this tab" )
            self.GetParent().Bind( wx.EVT_MENU, self.delete, mi )
            mi = self._menu.Append( -1, "Close other tabs", "Close all other tabs" )
            self.GetParent().Bind( wx.EVT_MENU, self.delete_others, mi )
        return self._menu

    def ShowPopupMenu( self, pos ):
        m = self.PanelMenu()
        if m is not None:
            self.GetParent().PopupMenu( m, pos )
