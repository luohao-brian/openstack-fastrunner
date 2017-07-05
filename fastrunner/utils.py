from oslo_utils import importutils
import six
import functools


import eventlet
from oslo_context import context as common_context


def spawn(func, *args, **kwargs):
    """Passthrough method for eventlet.spawn.

    This utility exists so that it can be stubbed for testing without
    interfering with the service spawns.

    It will also grab the context from the threadlocal store and add it to
    the store on the new thread.  This allows for continuity in logging the
    context when using this method to spawn a new thread.
    """
    _context = common_context.get_current()

    @functools.wraps(func)
    def context_wrapper(*args, **kwargs):
        # NOTE: If update_store is not called after spawn it won't be
        # available for the logger to pull from threadlocal storage.
        if _context is not None:
            _context.update_store()
        return func(*args, **kwargs)

    return eventlet.spawn(context_wrapper, *args, **kwargs)

def strtime(at):
    return at.strftime("%Y-%m-%dT%H:%M:%S.%f")

def utf8(value):
    """Try to turn a string into utf-8 if possible.

    The original code was copied from the utf8 function in
    http://github.com/facebook/tornado/blob/master/tornado/escape.py

    """
    if value is None or isinstance(value, six.binary_type):
        return value

    if not isinstance(value, six.text_type):
        value = six.text_type(value)

    return value.encode('utf-8')


def walk_class_hierarchy(clazz, encountered=None):
    """Walk class hierarchy, yielding most derived classes first."""
    if not encountered:
        encountered = []
    for subclass in clazz.__subclasses__():
        if subclass not in encountered:
            encountered.append(subclass)
            # drill down to leaves first
            for subsubclass in walk_class_hierarchy(subclass, encountered):
                yield subsubclass
            yield subclass
