import sys
from sqlalchemy import __version__ as sa_version

if sys.version_info < (2, 6):
    raise NotImplementedError("Python 2.6 or greater is required.")

py2k = sys.version_info < (3, 0)
py3k = sys.version_info >= (3, 0)
py33 = sys.version_info >= (3, 3)

if py3k:
    import builtins as compat_builtins
    string_types = str,
    binary_type = bytes
    text_type = str
    def callable(fn):
        return hasattr(fn, '__call__')

    def u(s):
        return s

else:
    import __builtin__ as compat_builtins
    string_types = basestring,
    binary_type = str
    text_type = unicode
    callable = callable

    def u(s):
        return unicode(s, "utf-8")

if py3k:
    from configparser import ConfigParser as SafeConfigParser
    import configparser
else:
    from ConfigParser import SafeConfigParser
    import ConfigParser as configparser

if py2k:
    from mako.util import parse_encoding

if py33:
    from importlib import machinery
    def load_module(module_id, path):
        return machinery.SourceFileLoader(module_id, path).load_module()
else:
    import imp
    def load_module(module_id, path):
        fp = open(path, 'rb')
        try:
            mod = imp.load_source(module_id, path, fp)
            if py2k:
                source_encoding = parse_encoding(fp)
                if source_encoding:
                    mod._alembic_source_encoding = source_encoding
            return mod
        finally:
            fp.close()

try:
    exec_ = getattr(compat_builtins, 'exec')
except AttributeError:
    # Python 2
    def exec_(func_text, globals_, lcl):
        exec('exec func_text in globals_, lcl')

if sa_version >= '0.8.0':
    def get_index_column_names(idx):
        return [exp.name for exp in idx.expressions]
else:
    def get_index_column_names(idx):
        return [col.name for col in idx.columns]

################################################
# cross-compatible metaclass implementation
# Copyright (c) 2010-2012 Benjamin Peterson
def with_metaclass(meta, base=object):
    """Create a base class with a metaclass."""
    return meta("%sBase" % meta.__name__, (base,), {})
################################################
