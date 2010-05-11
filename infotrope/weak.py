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
weakref by reference counting implementation.

Contains just weakref.Ref and WeakValueDictionary.
This is to work around limitations in the Nokia Series 60
port of Python.
"""

try:
    import weakref
except ImportError:
    _weakdict = {}
    def _checkweakrefs():
        try:
            import sys
        except ImportError:
            return
        global _weakdict
        old = _weakdict
        _weakdict = {}
        for k,v in old.items():
            #print "Checking %s, refcount %d" % ( `k`, sys.getrefcount(v) )
            if sys.getrefcount(v)>4:
                _weakdict[k] = v

    class weakref:
        class ref:
            def __init__( self, o ):
                self.id = id( o )
                _weakdict[ id(o) ] = o
                self.checker = _checkweakrefs

            def __call__( self ):
                self.checker()
                return _weakdict.get( self.id, None )

            def __del__( self ):
                self.checker()

        class WeakValueDictionary:
            def __init__( self ):
                self.d = {}

            def __getitem__( self, k ):
                o = self.d.get(k,None)
                if o is None:
                    raise KeyError,k
                else:
                    o = o()
                    if o is None:
                        del self.d[k]
                        raise KeyError,k
                return o

            def __contains__( self, k ):
                try:
                    return self[k] is not None
                except KeyError:
                    return None

            def __setitem__( self, k, v ):
                self.d[k] = weakref.ref(v)

            def __delitem__( self, k ):
                del self.d[k]

            def _check( self ):
                old = self.d
                self.d = {}
                for k,v in old.items():
                    if v() is not None:
                        self.d[k] = v

            def items( self ):
                self._check()
                return self.d.items()
            
            def values( self ):
                self._check()
                return [ x() for x in self.d.values() ]

            def keys( self ):
                self._check()
                return self.d.keys()

            def __del__( self ):
                _checkweakrefs()
