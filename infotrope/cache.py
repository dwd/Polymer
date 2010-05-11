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
#!/usr/bin/env python

"""
Provides shelve-like functionality.
Typically, uses shelve, but can also use e32dbm/marshal
"""

class dummy:
    def __init__( self, d=None ):
        self.contents = d or {}

    def __getitem__( self, w ):
        return self.contents[w]

    def __setitem__( self, w, s ):
        self.contents[w] = s

    def __delitem__( self, w ):
        del self.contents[w]

    def __len__(self):
        return len(self.contents)

    def items( self ):
        return self.contents.items()

    def sync( self ):
        try:
            self.contents.sync()
        except:
            pass

    def close( self ):
        try:
            self.contents.close()
        except:
            pass

    def __contains__( self, w ):
        return w in self.contents

    def has_key( self, w ):
        return self.contents.has_key( w )

    def get( self, k, default=None ):
        return self.contents.get( k, default )

class dummy_double(dummy):
    def __init__(self,d=None):
        dummy.__init__(self,d)

    def __getitem__(self, s):
        k1, k2 = s
        self.contents[k1].get(k2,{})
        return self.contents[k1][k2]

    def __len__(self):
        return len(self.contents)

    def __setitem__(self, s, v):
        k1, k2 = s
        d = self.contents.get(k1,{})
        d[k2] = v
        self.contents[k1] = d

    def __delitem__(self, s):
        try:
            k1, k2 = s
            d = self.contents.get(k1,{})
            del d[k2]
            self.contents = d
        except:
            del self.contents[s]

    def __contains__(self, s):
        try:
            k1, k2 = s
            return k2 in self.contents.get(k1,{})
        except:
            return s in self.contents

    def has_key(self, s):
        return s in self

    def items(self,kx=None):
        if kx is None:
            for k1,d in self.contents.items():
                for k2,v in d.items():
                    yield (k1,k2,v)
        else:
            dx = self.contents.get(kx,{})
            for k2,v in dx.items():
                yield (kx,k2,v)

    def get(self, k, default=None):
        try:
            k1,k2 = k
            return self.contents.get(k1,{}).get(k2,default)
        except:
            return self.contents.get(k,default)

__ok = False

if not __ok:
    try:
        try:
            from pysqlite2 import dbapi2 as sqlite
            sql_get = 'select stuff,enc from %s where name=?'
            sql_get_sgl = 'select stuff,enc from %s where uid=?'
            sql_set = 'insert or replace into %s(name,stuff,enc) values(?,?,?)'
            sql_del = 'delete from %s where name=?'
            sql_get_dbl = 'select stuff,enc from %s where uid=? and name=?'
            sql_set_dbl = 'insert or replace into %s(uid,name,stuff,enc) values(?,?,?,?)'
            sql_del_dbl = 'delete from %s where uid=? and name=?'
            sql_del_sgl = 'delete from %s where uid=?'
            sql_items_match = 'select name,stuff,enc from %s where uid=?'
            encode = buffer
        except ImportError:
            import sqlite
            sql_get = 'select stuff,enc from %s where name=%%s'
            sql_get_sgl = 'select stuff,enc from %s where uid=%%d'
            sql_set = 'insert or replace into %s(name,stuff,enc) values(%%s,%%s,%%d)'
            sql_del = 'delete from %s where name=%%s'
            sql_get_dbl = 'select stuff,enc from %s where uid=%%d and name=%%s'
            sql_set_dbl = 'insert or replace into %s(uid,name,stuff,enc) values(%%d,%%s,%%s,%%d)'
            sql_items_match = 'select name,stuff,enc from %s where uid=%%d'
            sql_del_dbl = 'delete from %s where uid=%%d and name=%%s'
            encode = sqlite.encode
        import marshal
        from infotrope.weak import weakref

        sql_enc_nlist = 0
        sql_enc_marshal = 1
        sql_enc_str = 2
        sql_enc_utf8 = 3
        
        __sqldb = weakref.WeakValueDictionary()

                
        class sqlite_master:
            def __init__( self, filename ):
                self.filename = filename
                self.db = sqlite.connect( filename, check_same_thread=False )
                self.tables = weakref.WeakValueDictionary()
                self.dirty = False

            def open_cache( self, table):
                try:
                    return self.tables[table]
                except:
                    pass
                tb = sqlite_cache( self, table)
                self.tables[table] = tb
                return tb

            def open_double_cache( self, table, ktype ):
                try:
                    return self.tables[table]
                except:
                    pass
                tb = sqlite_double_cache( self, table, ktype )
                self.tables[table] = tb
                return tb

            def commit( self ):
                if self.db and self.dirty:
                    for k,v in self.tables.items():
                        v.pre_sync()
                    self.db.commit()
                    self.dirty = False
                    for k,v in self.tables.items():
                        v.reader = self.cursor()

            def close( self ):
                if self.db:
                    self.commit()
                    self.db.close()
                    self.db = None

            def __del__( self ):
                self.close()

            def cursor( self ):
                #return sqlite_cursor_wrap(self.db.cursor())
                return self.db.cursor()

        class sqlite_cursor_wrap:
            def __init__(self, real):
                self.real = real

            def execute(self,sql,*args):
                #print "\n\nEXEC:",sql,args,"\n"
                return self.real.execute(sql,*args)

            def fetchall(self):
                return self.real.fetchall()
                
        class sqlite_cache:
            def __init__( self, db, table):
                self.db = db
                self.last_name = None
                self.last_stuff = None
                self.reader = self.db.cursor()
                self.sql_get = sql_get % table
                self.sql_set = sql_set % table
                self.sql_del = sql_del % table
                self.sql_count = 'select count(*) from %s' % table
                self.sql_create = 'create table %s ( name varchar(255) primary key, stuff blob, enc int )' % table
                self.sql_items = 'select name,stuff,enc from %s' % table

            def __len__(self):
                try:
                    self.reader.execute(self.sql_count)
                    d = self.reader.fetchall()
                    return d[0][0]
                except:
                    return 0
                
            def floxicate( self, obj ):
                import array
                if isinstance(obj,array.array):
                    return sql_enc_nlist,obj.tostring()
                if isinstance(obj,str):
                    return sql_enc_str,obj
                if isinstance(obj,unicode):
                    return sql_enc_utf8,obj.encode('utf-8')
                return sql_enc_marshal,encode(marshal.dumps( obj ))

            def defloxicate( self, s, enc ):
                if enc == sql_enc_nlist:
                    import array
                    return array.array('L',s)
                if enc == sql_enc_str:
                    return s
                if enc == sql_enc_utf8:
                    return s.decode('utf-8')
                if enc == sql_enc_marshal:
                    return marshal.loads( s )
                raise "Unknown encoding"

            def _get( self, s, failokay=True ):
                #print "CACHE: <<",`s`
                if self.last_name == s:
                    return self.last_stuff
                try:
                    self.reader.execute( self.sql_get, (s,) )
                    d = self.reader.fetchall()
                except:
                    self.reader.execute( self.sql_create )
                    self.db.dirty = True
                    if failokay:
                        return None
                    else:
                        raise KeyError, s
                if not d:
                    if failokay:
                        return None
                    else:
                        raise KeyError, s
                self.last_name = s
                self.last_stuff = self.defloxicate( str(d[0][0]), d[0][1] )
                return self.last_stuff

            def get(self, s, default=None):
                v = self._get(s)
                if v is None:
                    return default
                return v

            def __getitem__( self, s ):
                return self._get( s, False )

            def __setitem__( self, s, obj ):
                gloop = self.floxicate(obj)
                try:
                    self.reader.execute( self.sql_set, ( s, buffer(gloop[1]), gloop[0] ) )
                except:
                    self.reader.execute( self.sql_create )
                    self.db.dirty = True
                    self.__setitem__( s, obj )
                self.db.dirty = True
                if self.last_name == s:
                    self.last_stuff = obj

            def __delitem__( self, s ):
                try:
                    self.reader.execute( self.sql_del, (s,) )
                except:
                    self.reader.execute( self.sql_create )
                    self.db.dirty = True
                    self.__delitem__( s )                
                self.db.dirty = True
                if self.last_name == s:
                    self.last_stuff,self.last_name = (None,None)

            def sync( self ):
                self.db.commit()

            def pre_sync(self):
                pass

            def close( self ):
                self.sync()
                
            def __del__( self ):
                self.sync()
                self.db = None # Ensure.

            def items( self ):
                cursor = self.db.cursor()
                cursor.execute( self.sql_items )
                for k,v,e in cursor:
                    yield ( k,self.defloxicate(v,e) )

            def __contains__( self, s ):
                return self.has_key( s )

            def has_key( self, s ):
                try:
                    self[s]
                    return True
                except KeyError:
                    return False

        class sqlite_double_cache:
            def __init__( self, db, table, ktype ):
                self.db = db
                self.last_name = None
                self.last_stuff = None
                self.write_dirty = False
                self.write_name = None
                self.write_data = None
                self.reader = self.db.cursor()
                self.sql_get = sql_get_sgl % table
                self.sql_del = sql_del_sgl % table
                self.sql_set_dbl = sql_set_dbl % table
                self.sql_get_dbl = sql_get_dbl % table
                self.sql_del_dbl = sql_del_dbl % table
                if ktype is str:
                    self.sql_create = 'create table %s ( uid varchar(255), name varchar(255), stuff blob, enc int, primary key(uid,name) )' % table
                else:
                    self.sql_create = 'create table %s ( uid int, name varchar(255), stuff blob, enc int, primary key(uid,name) )' % table
                self.sql_create_index = 'create index idx%s on %s(uid)' % ( table, table )
                self.sql_items = 'select uid,name,stuff,enc from %s' % table
                self.sql_items_match = sql_items_match % table
                self.sql_count = 'select count(*) from %s' % table
                
            def __len__(self):
                try:
                    self.reader.execute(self.sql_count)
                    d = self.reader.fetchall()
                    return d[0][0]
                except:
                    return 0
                
            def floxicate( self, obj ):
                import array
                if isinstance(obj,array.array):
                    return sql_enc_nlist,obj.tostring()
                if isinstance(obj,str):
                    return sql_enc_str,obj
                if isinstance(obj,unicode):
                    return sql_enc_utf8,obj.encode('utf-8')
                return sql_enc_marshal,encode(marshal.dumps( obj ))

            def defloxicate( self, s, enc ):
                if enc == sql_enc_nlist:
                    import array
                    return array.array('L',s)
                if enc == sql_enc_str:
                    return s
                if enc == sql_enc_utf8:
                    return s.decode('utf-8')
                if enc == sql_enc_marshal:
                    return marshal.loads( s )
                raise "Unknown encoding"

            def _get( self, s, failokay=True ):
                if self.last_name == s:
                    return self.last_stuff
                if self.write_name == s:
                    return self.write_data
                #print "DCACHE: <<",`s`
                try:
                    t = s
                    sql = self.sql_get_dbl
                    if not isinstance(t,tuple):
                        t = (s,)
                        sql = self.sql_get_dbl
                    self.reader.execute( sql, t )
                    d = self.reader.fetchall()
                except:
                    self.reader.execute( self.sql_create )
                    self.reader.execute(self.sql_create_index)
                    self.db.dirty = True
                    if failokay:
                        return None
                    else:
                        raise KeyError, s
                if not d:
                    if failokay:
                        return None
                    else:
                        raise KeyError, s
                self.last_name = s
                self.last_stuff = self.defloxicate( str(d[0][0]), d[0][1] )
                return self.last_stuff

            def get(self, s, default=None):
                v = self._get(s)
                if v is None:
                    return default
                return v

            def __getitem__( self, s ):
                return self._get( s, False )

            def __setitem__( self, s, obj ):
                if self.write_name is not None:
                    if self.write_name != s:
                        self.real_write(self.write_name,self.write_data)
                self.write_name = s
                self.write_data = obj
                self.write_dirty = True
                self.db.dirty = True
                if self.last_name == s:
                    self.last_stuff = obj

            def real_write(self, s, obj):
                #print "DCACHE: >>",`s`
                try:
                    gloop = self.floxicate(obj)
                    self.reader.execute( self.sql_set_dbl, ( s[0], s[1], buffer(gloop[1]), gloop[0] ) )
                except:
                    self.reader.execute( self.sql_create )
                    self.reader.execute(self.sql_create_index)
                    self.db.dirty = True
                    self.__setitem__( s, obj )

            def __delitem__( self, s ):
                try:
                    sql = self.sql_del_dbl
                    if not isinstance(s,tuple):
                        s = (s,)
                        sql = self.sql_del
                    self.reader.execute( sql, s )
                except:
                    self.reader.execute( self.sql_create )
                    self.reader.execute(self.sql_create_index)
                    self.db.dirty = True
                    self.__delitem__( s )                
                self.db.dirty = True
                if self.last_name == s:
                    self.last_stuff,self.last_name = (None,None)

            def sync( self ):
                self.db.commit()

            def pre_sync(self):
                if self.write_dirty:
                    self.real_write(self.write_name,self.write_data)

            def close( self ):
                self.sync()
                
            def __del__( self ):
                self.sync()
                self.db = None # Ensure.

            def items( self, uid=None ):
                if uid is None:
                    cursor = self.db.cursor()
                    cursor.execute( self.sql_items )
                    for k,v,e in cursor:
                        yield ( k,self.defloxicate(v,e) )
                else:
                    cursor = self.db.cursor()
                    cursor.execute(self.sql_items_match, (uid,))
                    for k,v,e in cursor:
                        yield (uid,k,self.defloxicate(v,e))

            def __contains__( self, s ):
                return self.has_key( s )

            def has_key( self, s ):
                try:
                    self[s]
                    return True
                except KeyError:
                    return False

        def open( filename ):
            import os.path
            path, table = os.path.split( filename )
            dbfile = os.path.join( path, 'sqlite.db' )
            try:
                sql = __sqldb[dbfile]
            except KeyError:
                sql = sqlite_master( dbfile )
                __sqldb[dbfile] = sql
            return sql.open_cache( table )
        
        def open_double( filename, ktype ):
            import os.path
            path, table = os.path.split( filename )
            dbfile = os.path.join( path, 'sqlite.db' )
            try:
                sql = __sqldb[dbfile]
            except KeyError:
                sql = sqlite_master( dbfile )
                __sqldb[dbfile] = sql
            return sql.open_double_cache( table, ktype )

        __ok = True
    except ImportError:
        pass

if not __ok:
    try:
        import shelve
        
        def open( filename ):
            sh = shelve.open( filename )
            return sh

        def open_double(filename, ktype):
            sh = shelve.open(filename)
            d = dummy_double(sh)
            return d
        
        __ok = True
    except ImportError:
        pass

if not __ok:
    try:
        import e32dbm
        import marshal
        import base64
        
        class cache:
            def __init__( self, fname ):
                self.e32dbm = e32dbm.open( fname, 'cf' )
                self.sync()

            def floxicate( self, o ):
                return base64.encodestring( marshal.dumps( o ) )
            
            def defloxicate( self, d ):
                return marshal.loads( base64.decodestring( d ) )
            
            def __getitem__( self, k ):
                return self.defloxicate( self.e32dbm[ k ] )

            def __setitem__( self, k, w ):
                self.e32dbm[ k ] = self.floxicate( w )
            
            def __delitem__( self, k ):
                del self.e32dbm[ k ]
            
            def sync( self ):
                self.e32dbm.sync()
                self.e32dbm.reorganize()
            
            def close( self ):
                self.e32dbm.close()
            
            def __contains__( self, k ):
                return k in self.e32dbm

            def has_key( self, k ):
                return k in self.e32dbm

            def __len__( self ):
                return len( self.e32dbm )

        def open( fname ):
            return cache( fname )

        __ok = True
        
    except ImportError:
        pass
