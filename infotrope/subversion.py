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
import svn.fs
import svn.repos
import svn.core
import svn.client

class fooness:
    def __init__( self ):
        self._mod = svn.core
        svn.core.apr_initialize()

    def __del__( self ):
        if self._mod is not None:
            if self._mod.apr_terminate is not None:
                self._mod.apr_terminate()
        self._mod = None

foo = fooness()

class pool:
    def __init__( self, parent=None ):
        self._pool = None
        self._parent = parent

    def __del__( self ):
        if self._pool is not None:
            svn.core.svn_pool_destroy( self._pool )
    
    def pool( self ):
        if self._pool is None:
            self._pool = svn.core.svn_pool_create( self._parent )
        return self._pool

class fileish:
    def __init__( self, stream ):
        self._stream = svn.core.Stream( stream )
        self._buffer = ''
        self._eof = False

    def readline( self ):
        while not self._eof:
            if '\n' in self._buffer:
                s = self._buffer[0:self._buffer.index('\n')+1]
                self._buffer = self._buffer[len(s):]
                return s
            r = self._stream.read( 1024 )
            if r == '':
                self._eof = True
            self._buffer += r
        return None

    def read( self, l=None ):
        if l is None:
            l = len(self._buffer)
        if len(self._buffer) < l:
            x = self._stream.read( l - len( self._buffer ) )
            self._buffer += x
        r = self._buffer[0:l]
        self._buffer = self._buffer[l:]
        if len(r)==0:
            self._eof = True
            return None
        return r

    def write( self, txt ):
        self._stream.write( txt )
    
    def __iter__( self ):
        return self

    def next( self ):
        l = self.readline()
        if l is None:
            raise StopIteration()
        return l

    def close( self ):
        #self._stream.close()
        svn.core.svn_stream_close( self._stream._stream )
        self._stream = None

    def __del__( self ):
        if self._stream is not None:
            self.close()


class repos:
    def __init__( self, path, p=None ):
        self._pool = p
        if self._pool is None:
            self._pool = pool()
        self._repos = None
        self._path = path
        self._fs = None
        self._roots = {}
        self._latest = None

    def repos( self ):
        if self._repos is None:
            self._repos = svn.repos.svn_repos_open( self._path, self._pool.pool() )
        return self._repos

    def fs( self ):
        if self._fs is None:
            self._fs = svn.repos.svn_repos_fs( self.repos() )
        return self._fs

    def latest_revision( self ):
        if self._latest is None:
            self._latest = svn.fs.youngest_rev( self.fs(), self._pool.pool() )
        return self._latest

    def root( self, rev ):
        if rev is None:
            rev = self.latest_revision()
        if rev not in self._roots:
            self._roots[rev] = svn.fs.revision_root( self.fs(), rev, self._pool.pool() )
        return self._roots[rev]

    def open( self, vpath, rev=None ):
        return fileish( svn.fs.file_contents( self.root( rev ), vpath, self._pool.pool() ) )

    def transaction( self, username, logmessage ):
        return transaction( self, username, logmessage )

    def is_dir( self, vpath, rev=None ):
        if rev is None:
            rev = self.latest_revision()
        return svn.fs.is_dir( self.root( rev ), vpath, self._pool.pool() )==1

    def is_file( self, vpath, rev=None ):
        if rev is None:
            rev = self.latest_revision()
        return svn.fs.is_file( self.root( rev ), vpath, self._pool.pool() )==1

    def exists( self, vpath, rev=None ):
        try:
            self.is_file( vpath, rev )
            return True
        except svn.core.SubversionException:
            return False

    def last_modified( self, vpath, rev=None ):
        if rev is None:
            rev = self.latest_revision()
        r = svn.fs.node_created_rev( self.root( rev ), vpath, self._pool.pool() )
        return svn.fs.revision_prop( self.fs(), r, svn.core.SVN_PROP_REVISION_DATE, self._pool.pool() )
    
    def get_log( self, vpath, handler ):
        def main_handler( paths, rev, author, date, log, pool ):
            handler( paths=paths, rev=rev, author=author, date=date, log=log )
        svn.repos.svn_repos_get_logs( self.repos(), (vpath,), 0, self.latest_revision(), 0, 0, main_handler, self._pool.pool() )
        
    def set_file( self, f, vpath, username, logmessage ):
        make = True
        if self.exists( vpath ):
            make = False
        t = svn.repos.svn_repos_fs_begin_txn_for_commit( self.repos(), self.latest_revision(), username, logmessage, self._pool.pool() )
        root = svn.fs.txn_root( t, self._pool.pool() )
        if False:
            svn.fs.make_file( root, vpath, self._pool.pool() )
        f1 = fileish( svn.fs.apply_text( root, vpath, None, self._pool.pool() ) )
        f1.write( f )
        f1.close()
        svn.repos.svn_repos_fs_commit_txn( self.repos(), t, self._pool.pool() )
        self._latest = None
        self._roots = {}

class repos_remote:
    def __init__( self, url, p=None ):
        print "INIT"
        self.pool = pool( p )
        print "POOL"
        self.url = url
        print "CTX"
        self.ctx = svn.client.svn_client_create_context( self.pool.pool() )
        print "CTX/CONFIG"
        self.ctx.config = svn.core.svn_config_get_config( None, self.pool.pool() )
        print "DONE"

    def ls( self, rev=None, p=None ):
        if rev is None:
            rev = svn.core.svn_opt_revision_t()
            rev.kind = svn.core.svn_opt_revision_head
        if p is None:
            p = self.pool
        return svn.client.svn_client_ls( 'http://gw2/svn/', rev, 0, self.ctx, p.pool() )
