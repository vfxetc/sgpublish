Publishing via a Publisher
==========================

Streams
-------

Publishes are grouped into logical streams, consisting of Shotgun ``PublishEvent``
entities sharing the same ``sg_link``, ``sg_type``, and ``code``. Any publish
attached to the same link, of the same type, and with the same code should be
considered incremental versions of the same thing.

While publishes have version numbers, and these version numbers can be
automatically generated to be monotonically increasing, there is no meaning
behind the version numbers except what the users/artists put upon them.


Creating a Publish
------------------

Publishing is assisted via a :class:`.Publisher` instance, which manages the
creation of the folder for the publish (via :ref:`SGFS templates <sgfs:templates>`),
copying of files into that folder, permissions, and creating the final entity
on Shotgun itself.

The added complication is so that we can always be sure that if a publish is on
Shotgun with a non-zero version number, we know that the export finished and the
data is in a valid state.

We use the publisher as a context manager around our export code::
    
    >>> task = sg.find('Task', filters_to_get_a_task)
    >>> with Publisher(link=task, type="your_publish_type", code="Demo") as pub:
    ...     # Export into pub.directory


API Reference
-------------

.. automodule:: sgpublish.publisher

    .. autoclass:: Publisher
        :members:
    
