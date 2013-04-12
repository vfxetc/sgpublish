.. _index:

sgpublish
=========

.. image:: https://secure.travis-ci.org/westernx/sgpublish.png
    :alt: Test Status
    :target: http://travis-ci.org/westernx/sgpublish

Overview
--------

This package is a toolkit for creating work exporters, or "publishers", which report the work to Shotgun, and ease the flow of work products (e.g. caches, cameras, renders, etc.) from one department to the next.

The basic idea is for the artist's tools to know where the products are so that the artist doesn't have to dig through the file system looking for caches they need, and for the artist to be automatically warned whenever something they are using in the scene/script becomes out of date.

To streamline the process for artists, the tools may also create a Shotgun ``Version`` of the current shot for review, create QuickTimes for editorial, and log their time worked.


Streams
-------

Publishes are grouped into streams, consisting of Shotgun ``PublishEvent`` entities sharing the same Shotgun task, type (e.g. ``"maya_geocache"``) and name. Any publish attached to the same task, of the same type, and with the same name are considered incremental versions of the same thing.

While publishes have version numbers, and these version numbers can be automatically generated to be increasing, there is no meaning behind the version numbers except what the users/artists put upon them.

.. note::
    
    Even if they are on the same shot, a "rigging" stream is seperate from a "animation" stream is seperate from a "lighting" stream, and so the version numbers do not line up across departments.

    For example, imagine that we are working on lighting a shot. We have version 1 of the lighting, which is using version 3 of the animation, which is using version 5 of the rig. If an animation revision is required, it will bump up to version 4. Lighting will then upgrade to using the newer animation publish, and will bump to version 2.


Example Publishers
------------------

The following publisher/importer pairs exist within the WesternX pipeline (and most of which are either availible in this package or in the mayatools_):

.. _mayatools: https://github.com/westernx/mayatools

    * generic Maya scenes;
    * Maya geocaches;
    * Maya cameras (also to Nuke);
    * Maya reference edits;
    * Maya transformations (as locators);
    * Maya render layers.


Contents
--------

.. toctree::
    :maxdepth: 2
    
    publisher
    io
    utils





Indices and tables
==================
* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

