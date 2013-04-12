Publishing via a Publisher
==========================

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
    
