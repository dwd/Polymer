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
import infotrope.url
import polymer.treenav
import sys

import infotrope.datasets.bookmarks
import infotrope.datasets.base

ID_CREATE_SUBFOLDER = wx.NewId()
ID_ADD_NEW = wx.NewId()
ID_ADD = wx.NewId()
ID_DELETE = wx.NewId()
ID_EDIT = wx.NewId()
ID_SHARED = wx.NewId()

class BookmarkDialog( polymer.dialogs.EntryDialogNew ):
    def __init__( self, parent, deftitle=None, entry=None, dataset=None ):
        if dataset is None:
            dataset = wx.GetApp().bookmarks()
        polymer.dialogs.EntryDialogNew.__init__( self, parent, deftitle, entry, dataset )

    def add_prompts( self, p ):
        ( curl, name ) = wx.GetApp().frame.get_current_url()
        self._name = self.AddPrompt( p, "Name", "bookmarks.Name", fallback=name )
        if isinstance( self.entry, infotrope.datasets.bookmarks.link ):
            self._url = self.AddPrompt( p, "URL", "bookmarks.URL", fallback=curl )
        self._desc = self.AddPrompt( p, "Description", "bookmarks.Description" )

    def decode_ui( self ):
        if isinstance( self.entry, infotrope.datasets.bookmarks.link ):
            self.entry['bookmarks.URL'] = infotrope.url.URL( self._url.GetValue() )
        self.entry['bookmarks.Name'] = polymer.encode.decode_ui( self._name.GetValue() )
        self.entry['bookmarks.Description'] = polymer.encode.decode_ui( self._desc.GetValue() )

class TreeNodeBookmarks( polymer.treenav.TreeNode ):
    def __init__( self, tree, pid, entry = None, bm_entry = None ):
        self.bm = None
        if bm_entry is None and entry is None:
            self.bm = wx.GetApp().bookmarks()
        name = 'Bookmarks'
        self.bm_entry = bm_entry
        self.entry = entry
        if entry is not None:
            name = entry['bookmarks.Name']
            if name is None:
                name = entry['entry']
        kids = ( self.bm is not None or self.bm_entry is not None )
        icon = 'bookmarks.png'
        if kids:
            icon = 'subfolder.png'
        polymer.treenav.TreeNode.__init__( self, tree, pid, name, kids, images={wx.TreeItemIcon_Normal:'icons/tree/'+icon} )
        self.nodes = {}
        if self.bm is not None:
            self.bm.add_notify( self )

    def get_bm( self ):
        if self.bm is None and self.bm_entry is not None:
            self.bm = self.bm_entry.subdataset()
            self.bm.add_notify( self )

    def try_expand( self, event ):
        self.get_bm()
        if self.bm is not None:
            return len(self.bm) > 1
        return False

    def notify_addto( self, entryname ):
        if entryname == '':
            return
        e = self.bm[entryname]
        if e['bookmarks.Type'] is None:
            if e['subdataset'] is not None:
                e['bookmarks.Type'] = 'folder'
            else:
                e['bookmarks.Type'] = 'link'
        if e['bookmarks.Type'] == 'folder' and 'subdataset' in e:
            self.nodes[entryname] = TreeNodeBookmarks( self.tree(), self._id, e, e )
        else:
            self.nodes[entryname] = TreeNodeBookmarks( self.tree(), self._id, e )
        self.tree().Refresh()

    def notify_removefrom( self, entryname ):
        if entryname == '':
            return
        if entryname in self.nodes:
            self.nodes[entryname].Delete()
            del self.nodes[entryname]

    def notify_change( self, entryname ):
        if entryname == '':
            return
        self.notify_removefrom( entryname )
        self.notify_addto( entryname )

    def notify_complete( self, st ):
        pass

    def select( self, event ):
        if self.entry is not None:
            if self.entry['bookmarks.Type'] is None:
                if self.entry['bookmarks.URL'] is not None:
                    wx.GetApp().process_url( self.entry['bookmarks.URL'] )
            elif self.entry['bookmarks.Type'] == 'link':
                wx.GetApp().process_url( self.entry['bookmarks.URL'] )

    def begin_drag( self, event ):
        if self.entry is None:
            return
        self.get_bm()
        if self.bm is not None:
            dobj = polymer.dragdrop.URLDataObject( self.bm.url, self.entry['bookmarks.Name'], self )
            ds = wx.DropSource( self.tree() )
            ds.SetData( dobj )
            res = ds.DoDragDrop( wx.Drag_DefaultMove )
            return
        if self.entry['bookmarks.URL'] is None:
            event.Veto()
            return
        url = self.entry['bookmarks.URL']
        title = self.entry['bookmarks.Name']
        dobj = polymer.dragdrop.URLDataObject( url, title, self )
        ds = wx.DropSource( self.tree() )
        ds.SetData( dobj )
        res = ds.DoDragDrop( wx.Drag_DefaultMove )

    def drag_over( self, res ):
        return wx.DragCopy

    def drop( self ):
        return True

    def newentry( self ):
        import time
        import socket
        return str(time.time())+'@'+socket.gethostname()

    def menu_create_subfolder( self, event ):
        d = polymer.dialogs.TextEntryDialog( self.tree(), "New subfolder name", "Infotrope Polymer" )
        if wx.ID_OK!=d.ShowModal():
            return
        title = d.GetValue()
        self.get_bm()
        if self.bm is not None:
            st_url = self.bm.url
        if st_url is None:
            if self.entry is not None:
                st_url = self.entry.cont_url
        if st_url.path[-1] != '/':
            st_url.path += '/'
        wx.GetApp().connection( st_url ).store( st_url.path + self.newentry(), {'bookmarks.Type':'folder', 'bookmarks.Name':title.encode('utf-8'), 'subdataset':['.'] } )

    def menu_new( self, event ):
        dset = None
        if self.bm is not None:
            dset = self.bm
        if dset is None:
            if self.entry is not None:
                dset = infotrope.datasets.base.get_dataset( self.entry.cont_url )
        d = BookmarkDialog( self.tree(), dataset=dset )
        d.Show()

    def menu_add( self, event ):
        st_url = None
        if self.bm is not None:
            st_url = self.bm.url
        if st_url is None:
            if self.entry is not None:
                st_url = self.entry.cont_url        
        wx.GetApp().frame.new_bookmark( tgt_u=st_url )

    def menu_delete( self, event ):
        del_url = None
        if self.bm is not None:
            del_url = self.bm.url
        if self.entry is not None:
            del_url = self.entry.entry_url()
        if self.entry is None or self.entry['bookmarks.Type'] == 'folder':
            d = polymer.dialogs.MessageDialog( self.tree(), "Do you really want to delete a folder?\nAll bookmarks and subfolders inside will be deleted, too.", "Infotrope Polymer", wx.YES_NO|wx.ICON_EXCLAMATION )
            if wx.ID_YES!=d.ShowModal():
                return
        dset = infotrope.datasets.base.get_dataset( del_url.add_relative( '..' ) )
        dset[ del_url.path.split('/')[-1] ] = None
        #wx.GetApp().connection( del_url ).store( del_url.path, {'entry':None} )

    def menu_edit( self, event ):
        #d = polymer.dialogs.TextEntryDialog( self.tree(), "New name", "Infotrope Polymer" )
        #if wx.ID_OK!=d.ShowModal():
        #    return
        del_url = None
        if self.bm is not None:
            del_url = self.bm.url
        if del_url is None:
            del_url = self.entry.entry_url()
        dset = infotrope.datasets.base.get_dataset( del_url.add_relative( '..' ) )
        d = BookmarkDialog( self.tree(), entry=self.entry, dataset=dset )
        d.Show()
        #wx.GetApp().connection( del_url ).store( del_url.path, {'bookmarks.Name':d.GetValue().encode('utf-8')} )

    def menu_shared( self, event ):
        rights = self.bm['']['dataset.acl']
        if self.bm.url.path[-1]!='/':
            self.bm.url.path += '/'
        if 'anyone' in rights:
            wx.GetApp().connection( self.bm.url ).store( self.bm.url.path, {'dataset.acl': [ '\t'.join( x ) for x in rights.items() if x[0]!='anyone' ] } )
        else:
            wx.GetApp().connection( self.bm.url ).store( self.bm.url.path, {'dataset.acl': [ 'anyone\trx'] + ['\t'.join( x ) for x in rights.items() ] } )

    def context_menu( self, event, frame ):
        if self._menu is None:
            self._menu = wx.Menu()
            self._menu.Append( ID_CREATE_SUBFOLDER, "New subfolder", "Create a new bookmarks folder" )
            wx.EVT_MENU( self._menu, ID_CREATE_SUBFOLDER, self.menu_create_subfolder )
            self._menu.Append( ID_ADD_NEW, "New bookmark", "Create a new bookmark" )
            wx.EVT_MENU( self._menu, ID_ADD_NEW, self.menu_new )
            self._menu.Append( ID_ADD, "Add bookmark", "Add bookmark to here" )
            wx.EVT_MENU( self._menu, ID_ADD, self.menu_add )
            self._menu.Append( ID_DELETE, "Delete", "Delete this node" )
            wx.EVT_MENU( self._menu, ID_DELETE, self.menu_delete )
            self._menu.Append( ID_EDIT, "Edit", "Edit this node" )
            wx.EVT_MENU( self._menu, ID_EDIT, self.menu_edit )
            self.get_bm()
            if self.bm is not None and self.bm.url.server != '__DUMMY__':
                self._menu_shared = self._menu.Append( ID_SHARED, "Share", "Share this folder", wx.ITEM_CHECK )
                wx.EVT_MENU( self._menu, ID_SHARED, self.menu_shared )
        if self.bm is not None and self.bm.url.server != '__DUMMY__':
            len(self.bm)
            self._menu_shared.Check( 'anyone' in self.bm['']['dataset.acl'] )
        self.tree().PopupMenu( self._menu, event.GetPoint() )

    def data( self, data, how ):
        try:
            st_url = None
            if self.bm is not None:
                st_url = self.bm.url
            if st_url is None:
                if self.entry is not None:
                    if self.entry['bookmarks.Type'] == 'folder':
                        st_url = self.entry.entry_url()
                    else:
                        st_url = self.entry.cont_url
            st_url = infotrope.url.URL(st_url)
            if st_url.path[-1:] != '/':
                st_url.path += '/'
            node = data.GetNode()
            if node is not None:
                if not isinstance( node, TreeNodeBookmarks ):
                    node = None
            if node is None:
                urls = [infotrope.url.URL(x) for x in data.GetURLs()]
                if not urls:
                    return wx.DragNone
                for u in urls:
                    title = data.GetTitle()
                    if title == '' or len(urls)>1:
                        title = None
                    if title is None:
                        title = u.asString()
                    wx.GetApp().connection( st_url ).store( st_url.path + self.newentry(), {'bookmarks.Type':'link', 'bookmarks.Name':title.encode('utf-8'), 'bookmarks.URL':u.asString() }, async=True )
                wx.GetApp().connection( st_url ).store_flush()
                return wx.DragCopy
            else:
                if isinstance( node, TreeNodeBookmarks ):
                    if node.entry['bookmarks.Type'] is None:
                        if node.entry['subdataset'] is not None:
                            return wx.DragNone
                    elif node.entry['bookmarks.Type'] == 'link':
                        wx.GetApp().connection( st_url ).store( st_url.path + node.entry['entry'].encode('utf-8'), {'bookmarks.Type':'link', 'bookmarks.Name':node.entry['bookmarks.Name'].encode('utf-8'), 'bookmarks.URL':node.entry['bookmarks.URL'].asString()} )
                        return wx.DragCopy
                    elif node.entry['bookmarks.Type'] == 'folder':
                        tgturl = infotrope.url.URL( node.entry.subdataset_url() )
                        node.get_bm()
                        if 'anyone' in node.bm['']['dataset.acl']:
                            print "Folder is shared."
                            if '/~/' in tgturl.path:
                                tgturl.path = tgturl.path.replace( '/~/', '/user/' + ( tgturl.username or 'anonymous' ) + '/' )
                            tgturl.username = None
                            if tgturl.mechanism is not None:
                                tgturl.mechanism = '*'
                        else:
                            print "Node not shared."
                        if st_url.username is None:
                            print "Target is anonymous"
                            if tgturl.username is not None:
                                print "Can't store non-anonymous in anonymous, would be mean."
                                return wx.DragNone
                            tgturl.mechanism = None
                        wx.GetApp().connection( st_url ).store( st_url.path + node.entry['entry'].encode('utf-8'), {'bookmarks.Type': 'folder', 'bookmarks.Name':node.entry['bookmarks.Name'].encode('utf-8'), 'subdataset': [tgturl.asString()] } )
            return wx.DragNone
        except:
            return wx.DragNone
