Steve Fink's collection of random tools

These are tools that I think might be useful to other people. So far, I've just
been uploading them to my people.mozilla.org account, but I realized that
hosting them in a DVCS makes it much easier for people to (1) check if there
are any updates, and (2) grab those updates. And maybe (3) recover old versions
when I break shit.

----------------------------------------------------------------------

json - Interactive navigation of a JSON file

Created to explore a problem with a large sessionstore.js file. It mimics a
UNIX shell prompt, allowing you to cd, ls, grep, and similar.

Requires the Perl module 'JSON'. Installable on Fedora with

  yum install perl-JSON

Here's the current help message:

Usage: json <filename.json> [initial-path]

    ls [PATH]              - show contents of structure
    cd PATH                - change current view to PATH
    cat [PATH]             - display the value at the given PATH
    delete SPEC            - delete the given key or range of keys (see below
                             for a description of SPEC)
    set KEY VALUE          - modify an existing value (VALUE may optionally
                           - be quoted)
    grep [-l] PATTERN PATH - search for PATTERN in given PATH
    write [-pretty] [FILENAME]
                           - write out the whole structure as JSON. Use '-' as
                             FILENAME to write to stdout.
    pretty                 - prettyprint current structure to stdout
    size PATH              - display how many bytes the JSON of the substructure
                             at PATH would take up
    load [FILENAME]        - load in the given JSON file (reload current file
                             if no filename given)
    help                   - show this message

Paths:

    PATHs are slash-separated sequences of key names, '.', '..', or '*'.

Delete Specifications:

    A delete SPEC can be a plain key name, or a range of the format 'M..N',
    where one of M and N may be optional. M defaults to zero. N defaults to the
    highest index available. Ranges are inclusive.

