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
from infotrope.weak import weakref

import infotrope.acap

class resync_search( infotrope.acap.search ):
    def __init__( self, **kw ):
        infotrope.acap.search.__init__( self, **kw )

class index_search( infotrope.acap.search ):
    def __init__( self, **kw ):
        infotrope.acap.search.__init__( self, **kw )

class first_search( infotrope.acap.search ):
    def __init__( self, **kw ):
        infotrope.acap.search.__init__( self, **kw )

class fallback_resync_search( infotrope.acap.search ):
    def __init__( self, **kw ):
        infotrope.acap.search.__init__( self, **kw )

class modsince_search( infotrope.acap.search ):
    def __init__( self, **kw ):
        infotrope.acap.search.__init__( self, **kw )

class dataset_class:
    def __init__( self, url, depth=False ):
        self._search = None
        self._cache = None
        import infotrope.serverman
        import infotrope.url
        import infotrope.cache
        self.url = infotrope.url.URL( url )
        if self.url.path[-1] != '/':
            self.url.path += '/'
        self._search = None
        self._resync_search = None
        self._waited = False
        self._sync_active = False
        self._subnotify = []
        c = infotrope.serverman.get_serverman().get( self.url ) # Async.
        self._cache_name = c.cache_root()
        self._cache = None
        self._delta_cache = infotrope.cache.dummy()
        self._delta_index = []
        self._index = None
        self._modtime = None
        if self._cache_name and not depth:
            import os
            for x in url.path.split('/'):
                if len(x):
                    if x == '~':
                        x = '%'
                    self._cache_name = os.path.join( self._cache_name, x )
            if not os.path.exists( self._cache_name ):
                os.makedirs( self._cache_name )
            self._cache_name = os.path.join( self._cache_name, self.__class__.__name__ )
            self._cache = infotrope.cache.open( self._cache_name )
            self._delta_cache = infotrope.cache.open( self._cache_name + '_delta' )
            if self._delta_cache.has_key('INDEX'):
                self._delta_index = self._delta_cache['INDEX']
            if self._cache.has_key('INDEX'):
                self._index = self._cache['INDEX']
                self._modtime = self._cache['MODTIME']
        if self.url.server == '__DUMMY__':
            if self._cache is None:
                self._cache = infotrope.cache.dummy()
            if not self._cache.has_key('INDEX'):
                self._index = []
                self._cache['INDEX'] = []
                self._modtime = 'whenever'
                self._cache['MODTIME'] = 'whenever'
            self._cache.sync()
            self._delta_cache.sync()
            self._waited = True
            self._sync_active = True
        c.notify_ready( self.connected )

    def sync( self ):
        if self._sync_active:
            if self._cache is not None:
                self._cache.sync()
            if self._delta_cache is not None:
                self._delta_cache.sync()

    def log( self, what ):
        import infotrope.serverman
        infotrope.serverman.get_serverman().log( self.url.asString(), '==', what )

    def connected( self, c ):
        if not c.ready:
            return
        c.add_resync( self.reconnect )
        self.do_search( c )

    def reconnect( self, c ):
        self._search = None
        c.notify_ready( self.connected )
        
    def real_getitem( self, what ):
        if self._cache:
            return self._cache['E::'+what]
        if self.url.server == '__DUMMY__':
            raise KeyError,what
        self.do_search()
        if what not in self._search:
            if not self._waited:
                self.log( "Waiting []..." )
                self._search.wait()
        return self._search[what]

    def raw_getitem( self, what ):
        d = {}
        try:
            q = self.real_getitem( what )
            if q is not None:
                d.update( q )
        except TypeError:
            pass
        except KeyError:
            pass
        if what in self._delta_index:
            o = self._delta_cache['E::'+what]
            if o is None:
                raise KeyError, "Entry %s has been deleted locally" % `what`
            for k,a in o.items():
                if a is None:
                    if k in d:
                        del d[k]
                else:
                    if k in d:
                        d[k]['value'] = a
                    else:
                        d[k] = {'value':a}
        return d

    def __getitem__( self, what ):
        if isinstance(what,int):
            index = self.get_index()
            what = index[what]
            entry = self.raw_getitem( what )
            return self.base_factory( entry )
        return self.base_factory( self.raw_getitem( what ) )

    def __delitem__( self, what ):
        self[what] = None
        
    def __setitem__( self, what, s ):
        if isinstance(what,unicode):
            what = what.encode('utf-8')
        oldhere = what in self
        key = 'E::' + what
        if s is not None:
            if key in self._delta_cache:
                d = self._delta_cache[key]
            else:
                d = None
            if d is None:
                d = {}
            d.update( s )
        else:
            d = None
        if what not in self._delta_index:
            self._delta_index.append( what )
        self._delta_cache[key] = d
        self._delta_cache['INDEX'] = self._delta_index
        self.sync()
        sm = infotrope.serverman.get_serverman()
        c = sm.get( self.url )
        if c.ready:
            self.do_pending_stores( c )
            self.do_search( c )
        else:
            newhere = what in self
            if oldhere:
                if newhere:
                    self.send_notify_change( what )
                else:
                    self.send_notify_removefrom( what )
            else:
                self.send_notify_addto( what )
        
    def __contains__( self, what ):
        if what in self._delta_index:
            if self._delta_cache['E::'+what] is None:
                return False
            else:
                return True
        try:
            self.index( what )
            return True
        except ValueError:
            return False

    def get_index( self ):
        if self._index is not None:
            if not self._delta_index:
                return self._index
            index = self._index[:]
            for x in self._delta_index:
                if x in index:
                    if self._delta_cache['E::'+x] is None:
                        index.remove(x)
                else:
                    if self._delta_cache['E::'+x] is not None:
                        index.append(x)
            return index
        self.do_search()
        if self._search is None:
            return []
        if not self._waited:
            self._search.wait()
        return self._search.entries()

    def index( self, what ):
        if self._cache:
            return self.get_index().index(what)
        self.do_search()
        if not self._search:
            raise ValueError, "No search"
        if what not in self._search.entries():
            if not self._waited:
                self._search.wait()
        return self._search.entries().index(what)
    
    def entries( self ):
        if self._cache:
            self.log( "Producing cache index." )
            return self.get_index()
        self.do_search()
        if self._search is None:
            return []
        if not self._waited:
            self.log( "Waiting for entries" )
            self._search.wait()
        self.log( "Using search entries" )
        return self._search.entries()

    def __len__( self ):
        self.log( "len() requested" )
        if self._cache:
            self.log( "Using cache length" )
            return len(self.get_index())
        self.log( "Using search length" )
        self.do_search()
        if not self._waited:
            self.log( "Waiting len()" )
            self._search.wait()
        if self._search is None:
            self.log( "Search dead, zero length" )
            return 0
        return len(self._search)

    def empty( self ):
        return len(self)==0

    def do_search( self, conn=None ):
        import infotrope.acap
        if self._search is not None:
            self.do_pending_stores( conn )
            return
        if conn is None:
            import infotrope.serverman
            conn = infotrope.serverman.get_serverman()[self.url]
            return
        limit = None
        self._search_mode = 'FIRST'
        self._modtime_resync = self._modtime
        if self._cache and self._modtime: # We have a cache with a modtime, so we need a resync.
            limit = 0
            self._search_mode = 'RESYNC'
            self.log( "Using resync search" )
        sort = self.get_search_sort()
        self._search = first_search( connection=conn, context=self.__class__.__name__ + self.url.path, base=self.url.path, criteria=self.get_search_criteria(), ret=self.get_search_return(), sort=sort, notify=self, enum=sort is not None, limit=limit, notify_complete=self.recreate_context_complete )
        self._search.send()

    def recreate_context_complete( self, search, result ):
        self._waited = True
        if result.lower()!='ok':
            self._search = None
            self._index = []
            self.do_pending_stores()
            self.send_notify_complete()
            return
        if self._search_mode == 'RESYNC':
            self.log( "Sending modsince search" )
            self._modsearch = modsince_search( connection=self._search.connection(), base=self.__class__.__name__ + self.url.path, ret=self.get_search_return(), notify_complete=self.modsince_search_complete, criteria='COMPARESTRICT "modtime" "i;octet" "%s"' % self._modtime_resync )
            self._modsearch.send()
        else:
            self._index = self._search.entries()
            self.update_cache()
            self.do_pending_stores()
            self.send_notify_complete()

    def modsince_search_complete( self, *args ):
        ls = len(self._search)
        li = len(self._index)
        lm = len(self._modsearch)
        if self.get_search_sort() is not None:
            self.log( "Sorted search" )
            if ls==li and lm==0:
                self.log( "Length unchanged and no modifications." )
                self._modsearch = None
                self.sync_complete()
                return # No modifications, context same size => no deletions.
            self.log( "Merging modifications" )
            for x in self._modsearch.entries():
                if x in self._index:
                    self.notify_change( x, 0, 0, self._modsearch[x] )
                else:
                    self.notify_addto( x, 0, self._modsearch[x] )
            self.send_index_search()
        else:
            self.log( "Unsorted search, merging modifications." )
            adds = 0
            for x in self._modsearch.entries():
                if x in self._index:
                    self.notify_change( x, 0, 0, self._modsearch[x] )
                else:
                    adds += 1
                    self.notify_addto( x, 0, self._modsearch[x] )
            if ls-li == adds:
                self.log( "Difference in length equal to adds, no deletions." )
                self._modsearch = None
                self.sync_complete()
                return # No modifications, context same size => no deletions.
            self.log( "Finding deletions via DELETEDSINCE." )
            conn = self._search.connection()
            t,r,s = conn.send( 'DELETEDSINCE', infotrope.acap.string( self.url.path ), infotrope.acap.string( self._modtime_resync ) )
            conn.register( t, self )
            t.notifier = self.deletedsince
            self._resync_command = t

    def send_index_search( self ):
        self.log( "Sending index search" )
        self._modsearch = None # Done with this now.
        self._indexsearch = index_search( connection=self._search.connection(), base=self.__class__.__name__ + self.url.path, ret=['modtime'], sort=self.get_search_sort(), notify_complete=self.index_search_complete )
        self._indexsearch.send()
        
    def index_search_complete( self, *args ):
        self.log( "Index search complete, removing non-existent entries" )
        for x in self._index:
            if x not in self._indexsearch:
                self.notify_removefrom( x, 0 )
        self.log( "Copying index" )
        self._index = self._indexsearch.entries()
        self._modtime = self._indexsearch.modtime()
        self.update_cache( False )
        self._indexsearch = None
        self.sync_complete()

    def _handle_deleted( self, t, r, s ):
        self.log( "Removing deleted entry" )
        self.notify_removefrom( s, 0 )

    def get_search_sort( self ):
        return None

    def deletedsince( self, cmd, t, r, s ):
        self._resync_command.notifier = None # Break loop.
        self._resync_command = None
        if r.lower()!='ok': # In theory, this is rare. In practise, it's actually normal.
            self.log( "DELETEDSINCE failed, using fallback resync search" )
            conn = infotrope.serverman.get_serverman()[self.url]
            criteria = self.get_search_criteria()
            criteria = 'AND COMPARE "modtime" "-i;octet" "%s" %s' % ( self._modtime_resync, criteria )
            self._resync_search = fallback_resync_search( connection=conn, base=self.__class__.__name__ + self.url.path, criteria=criteria, ret=['entry'], notify_complete=self.resync_search_complete )
            self._resync_search.send()
        else:
            self.log( "DELETEDSINCE success!" )
            if len(self._search) == len(self._index):
                self.log( "Found all removals." )
                self._modsearch = None
                self.sync_complete()
            else:
                self.log( "Some removals are modifications, annoying." )
                self.send_index_search()

    def base_factory( self, entry ):
        if 'entry' in entry and 'value' in entry['entry']:
            if entry['entry']['value'] == '':
                return empty_entry( entry, self.url )
        return self.factory( entry )( entry, self.url )

    def new( self, t=None ):
        raise TypeError, "Abstract method called."

    def update_cache( self, normal=True ):
        if self._index is None:
            self._index = []
        if normal:
            if self._modtime == self._search.modtime():
                return
            self._modtime = self._search.modtime()
        if self._cache is not None:
            self._cache['MODTIME'] = self._modtime
            self._cache['INDEX'] = self._index
            self.sync()

    def send_notify_addto( self, entry ):
        for x in self._subnotify:
            z = x()
            if z is not None:
                z.notify_addto( entry )
    
    def send_notify_change( self, entry ):
        for x in self._subnotify:
            z = x()
            if z is not None:
                z.notify_change( entry )
    
    def send_notify_removefrom( self, entry ):
        for x in self._subnotify:
            z = x()
            if z is not None:
                z.notify_removefrom( entry )
    
    def send_notify_complete( self ):
        for x in self._subnotify:
            z = x()
            if z is not None:
                z.notify_complete( 'ok' )
    
    def notify_addto( self, entry, pos, e=None ):
        self.log( "Add: " + entry )
        if self._cache is not None:
            incache = 'E::'+entry in self._cache
            self._cache['E::'+entry] = e or self._search[entry]
            if self._index is not None:
                if entry not in self._index:
                    self._index.insert( pos, entry )
            else:
                self._index = [ entry ]
            self.log( "Post index insert: " + `self._index` + " incache: " + `incache` )
            self.update_cache()
            if incache:
                self.send_notify_change( entry )
                return
        self.send_notify_addto( entry )
        
    def notify_removefrom( self, entry, pos ):
        self.log( "Remove: " + entry )
        if self._cache is not None:
            incache = 'E::'+entry in self._cache
            del self._cache['E::'+entry]
            self._index.remove( entry )
            self.log( "Post index removal: " + `self._index` )
            self.update_cache()
            if not incache:
                return
        self.send_notify_removefrom( entry )
        
    def notify_change( self, entry, oldpos, newpos, e=None ):
        self.log( "Change: " + entry )
        if self._cache is not None:
            self._cache['E::'+entry] = e or self._search[entry]
            self.log( "Pre index removal: " + `self._index` )
            self._index.remove( entry )
            self.log( "Post index removal: " + `self._index` )
            self._index.insert( newpos, entry )
            self.log( "Post index insert: " + `self._index` )
            self.update_cache()
        self.send_notify_change( entry )
        
    def sync_complete( self ):
        self.log( "Sync complete, setting index." )
        self._search.set_index( self._index )
        self.update_cache()
        self.log( "Fully resynchronized" )
        self.do_pending_stores()
        self.send_notify_complete()

    def do_pending_stores( self, conn=None ):
        if self._delta_index:
            if conn is None:
                conn = infotrope.serverman.get_serverman()[ self.url ]
            dl = []
            for k,d in self._delta_cache.items():
                if k=='INDEX':
                    continue
                if d is None:
                    d = {'entry':None}
                conn.store( self.url.path + k[3:], d, True )
                dl.append( k )
            for k in dl:
                del self._delta_cache[k]
            self._delta_index = []
            self._delta_cache['INDEX'] = self._delta_index
            conn.store_flush()
            self.sync()
            if self._search:
                self._search.updatecontext()
            else:
                self._waited = False
                self.do_search()
        self._sync_active = True
        self.sync()

    def resync_search_complete( self, srch, r ):
        self.test_both_done()
    
    def notify_complete( self, state ):
        if state.lower()!='ok':
            self._search = None
            self._waited = False
        else:
            self._waited = True
            if self._cache is not None:
                if self._search_mode == 'FIRST':
                    if self._index is None:
                        self._index = []
                    for e in self._index:
                        self._cache['E::' + e] = self._search[e]
                    self.update_cache()
        self.test_both_done()
        for x in self._subnotify:
            z = x()
            if z is not None:
                z.notify_complete( state.lower() )

    def test_both_done( self ):
        # Update cache after completed fallback search for failed DELETEDSINCE.
        if self._search_mode == 'DELETEDSINCE':
            if self._resync_search is None:
                return
            if self._resync_search.complete() and self._search.complete():
                for x in self._cache.keys():
                    if x.find('E::'):
                        entry = x[3:]
                        if entry not in self._resync_search and entry not in self._search:
                            self.notify_removefrom( entry )
            self.update_cache()
            self._resync_search = None

    def add_notify( self, what ):
        self._subnotify.append( weakref.ref(what) )
        if self._cache and self._cache.has_key('INDEX'):
            for entry in self.get_index():
                what.notify_addto( entry )
        elif self._search is not None:
            for entry in self._search.entries():
                what.notify_addto( entry )
        if self._waited:
            what.notify_complete( 'ok' )

    def shutdown(self):
        if self._search is not None:
            #print "freecontext"
            self._search.freecontext(self.post_shutdown)

    def post_shutdown(self,*args):
        #print "post shutdown"
        self.update_cache()

    def __del__( self ):
        #print "(base dataset del)"
        if self._cache is not None:
            self._cache.close()

class entry:
    def __init__( self, entry, url ):
        self._raw = entry
        self.cont_url = url
        self._setting = {}

    def __getitem__( self, attra ):
        attr = ''
        if isinstance( attra, str ):
            attr = attra
        else:
            attr = attra.encode('utf-8')
        raw = None
        if attr in self._setting:
            raw = self._setting[attr]
        if raw is None:
            if attr in self._raw:
                if 'value' in self._raw[attr]:
                    raw = self._raw[attr]['value']
        if raw is None:
            return None
        if attr=='entry':
            return raw.decode( 'utf-8' )
        elif attr=='subdataset':
            return raw
        else:
            try:
                t = self.decode( attr, raw )
            except:
                return None # Attributes which fail to get decoded right are treated as if they don't exist.
            if t is not None:
                return t
            return raw

    def __setitem__( self, attr, polish ):
        if polish is None:
            if self[attr] is not None:
                self._setting[attr] = None
            return
        raw = self.encode( attr, polish )
        if raw is None:
            raw = polish
        if isinstance(raw,unicode):
            raw = raw.encode('utf-8')
        elif isinstance(raw,tuple) or isinstance(raw,list):
                nraw = []
                for x in raw:
                    if isinstance(x,unicode):
                        nraw.append(x.encode('utf-8'))
                    elif isinstance(x,str):
                        nraw.append(x)
                    else:
                        nraw.append(str(x))
                raw = nraw
        elif not isinstance(raw,str):
            raw = str(raw)
        if attr in self._raw:
            if 'value' in self._raw[attr]:
                if raw==self._raw[attr]['value']:
                    return
        self._setting[attr] = raw

    def entry_url( self ):
        u = self.cont_url.add_relative( self['entry'] )
        return u

    def save( self, force=False ):
        if force:
            for name,attr in self._raw.items():
                if name not in self._setting:
                    if attr['value'] is not None:
                        self._setting[name] = attr['value']
        if 0==len(self._setting):
            return
        u = self.entry_url()
        d = get_dataset( self.cont_url )
        en = u.path
        if '/' in en:
            en = en[en.rfind('/')+1:]
        d[en] = self._setting
        #infotrope.serverman.get_serverman()[ u ].store( u.path, self._setting )

    def subdataset_url( self ):
        sd = self['subdataset']
        if sd is None:
            return None
        if '.' in sd:
            return self.entry_url() # Shortcut, prefer immediate.
        # Scan through twice - once for local, once for remote.
        for s in sd:
            if s[0:5]=='acap:' or s[0:2]=='//':
                # Remote.
                pass
            else:
                return self.entry_url().add_relative( s )
        if sd[0][0:5]=='acap:':
            return infotrope.url.URL( sd[0] )
        return infotrope.url.URL( 'acap:'+sd[0] )

    def subdataset( self ):
        u = self.subdataset_url()
        if u is not None:
            return get_dataset( u )
        return None

    def __contains__( self, what ):
        return what in self._raw

class empty_entry(entry):
    def __init__( self, e, url ):
        entry.__init__( self, e, url )

    def decode( self, attr, raw ):
        if attr.find( 'dataset.acl' ) == 0:
            return dict([ x.split('\t') for x in raw ])
        else:
            return raw
            

dataset_types = {}
datasets = weakref.WeakValueDictionary()
def register_dataset_type( dataset, c ):
    global dataset_types
    dataset_types[dataset] = c

def get_dataset_type( url ):
    import infotrope.url
    global dataset_types
    u = infotrope.url.URL( url )
    if u.scheme!='acap':
        raise "Cannot handle non-ACAP URLs"
    if u.dataset_class is None:
        raise "Erm. Dunno."
    if u.dataset_class not in dataset_types:
        raise "Erm, still dunno about %s from %s" % ( `u.dataset_class`, `u` )
    return dataset_types[u.dataset_class]( u )

def get_dataset( url ):
    import infotrope.url
    global datasets
    u = infotrope.url.URL( str(url) )
    us = u.asString()
    srv = None
    if us not in datasets:
        srv = get_dataset_type( u )
        datasets[us] = srv
    else:
        srv = datasets[us]
    return srv

def cleanup():
    global datasets
    datasets = weakref.WeakValueDictionary()
