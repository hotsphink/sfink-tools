Steve Fink's collection of random tools

These are tools that I think might be useful to other people. So far, I've just
been uploading them to my people.mozilla.org account, but I realized that
hosting them in a DVCS makes it much easier for people to (1) check if there
are any updates, and (2) grab those updates. And maybe (3) recover old versions
when I break shit.

----------------------------------------------------------------------

Tools included:

json - Interactive navigation of a JSON file
debug - Start up a debugger within emacs on various types of files

----------------------------------------------------------------------

json - Interactive navigation of a JSON file

Created to explore a problem with a large sessionstore.js file. It mimics a
UNIX shell prompt, allowing you to cd, ls, grep, and similar.

Requires the Perl module 'JSON'. Installable on Fedora with

  yum install perl-JSON

Run json --help for a full help message. Here's an excerpt:

Usage: json <filename.json> [initial-path]

    ls [PATH]              - show contents of structure
    cd PATH                - change current view to PATH
    cat [PATH]             - display the value at the given PATH
    delete SPEC            - delete the given key or range of keys (see below
                             for a description of SPEC)
    set KEY VALUE          - modify an existing value (VALUE may optionally
                           - be quoted)
    mv PATH PATH           - move a subtree
    grep [-l] PATTERN PATH - search for PATTERN in given PATH
    write [-pretty] [FILENAME]
                           - write out the whole structure as JSON. Use '-' as
                             FILENAME to write to stdout.
    pretty                 - prettyprint current structure to stdout
    size PATH              - display how many bytes the JSON of the substructure
                             at PATH would take up
    load [FILENAME]        - load in the given JSON file (reload current file
                             if no filename given)

----------------------------------------------------------------------

debug - Start up a debugger within emacs on various types of files

debug --help for usage.

Usual usage is to prepend whatever command you want to debug with 'debug'.

Examples:

debug firefox -no-remote -P BugPictures
 - runs firefox within gdb within emacs, with the given arguments
debug -i firefox -no-remote -P NakedBugPictures
 - same, but stops at the gdb prompt before running firefox
debug somescript.pl x y z
 - runs somescript.pl within perldb within emacs, with the given arguments

The script goes to insane lengths to figure out what you really meant to run.
For example, if you alias ff in your shell to 'firefox -no-remote', you can
just do

  debug ff

It will discover that there's no command ff in $PATH and start up a subshell,
look for the alias 'ff', and use that command instead.
