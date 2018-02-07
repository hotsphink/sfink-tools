Steve Fink's collection of random tools

These are tools that I think might be useful to other people.

----------------------------------------------------------------------

Tools included:

 - json : Interactive navigation of a JSON file
 - debug : Start up a debugger within emacs on various types of files
 - em : Start up emacs on the files touched by a patch, on a relevant line number
 - traverse.py : Gecko-specific, sorta. Utility for traversing a callgraph.
 - wig : Patch harder

----------------------------------------------------------------------

Configuration files:

I also have a set of configuration files that I version-control here. They
might be a little harder to install and use, because strangely enough I change
the filename between the actual files and the ones here, and some of them refer
to each other. Sorry.

 - .gdbinit : gdb init file in gdb command syntax
 - .gdbinit.py : gdb python init file, loaded by .gdbinit
 - .gdbinit.pahole.py : pahole command, loaded by .gdbinit
 - .gdbinit.symbols.py : Ted Mielczarek's source server integration for gdb
 - .hgrc : Mercurial configuration

Note that the filenames in this repo are missing the leading periods. I symlink
the actual names into my sfink-tools checkout. So if you wanted to use these
unmodified, you could do something like

    cd $HOME
    ln -s mycheckouts/sfink-tools/conf/gdbinit .gdbinit
    ln -s mycheckouts/sfink-tools/conf/gdbinit.py .gdbinit.py
    ln -s mycheckouts/sfink-tools/conf/gdbinit.pahole.py .gdbinit.pahole.py
    ln -s mycheckouts/sfink-tools/conf/gdbinit.symbols.py .gdbinit.symbols.py

But more likely, you want to modify them. And even for me, it would be smarter
to have .gdbinit load it straight from my sfink-tools checkout. Maybe I'll do
that someday.

----------------------------------------------------------------------

json - Interactive navigation of a JSON file

Created to explore a problem with a large sessionstore.js file. It mimics a
UNIX shell prompt, allowing you to cd, ls, grep, and similar.

Requires the Perl module 'JSON'. Installable on Fedora with

    dnf install perl-JSON

Run json --help for a full help message. Here's an excerpt:

`Usage: json <filename.json> [initial-path]`

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

`debug --help` for usage.

Usual usage is to prepend whatever command you want to debug with 'debug'.

Examples:

 - `debug firefox -no-remote -P BugPictures`

   runs firefox within gdb within emacs, with the given arguments
   
 - `debug -i firefox -no-remote -P NakedBugPictures`

   same, but stops at the gdb prompt before running firefox

 - `debug somescript.pl x y z`

   runs somescript.pl within perldb within emacs, with the given arguments

 - `debug --record js testfile.js`

   records `js testfile.js` with rr, then replays the recording in gdb in emacs

The script goes to insane lengths to figure out what you really meant to run.
For example, if you alias ff in your shell to 'firefox -no-remote', you can
just do

    debug ff

It will discover that there's no command ff in $PATH and start up a subshell,
look for the alias 'ff', and use that command instead.

----------------------------------------------------------------------

em - Edit files relevant to a patch

1. `em foo.txt:33` will run `emacs +33 foo.txt`
   so will `em foo.txt:33`: (easier cut & paste of trailing colon for error messages)
   and foo.txt will be found anywhere in the current hg tree (if not in cwd)
2. `em` with no args will run emacs on the files changed in the cwd, or if none, then
   by the cwd's parent rev
3. `em 01faf51a0acc` will run emacs on the files changed by that rev.
4. `em foo.txt.rej` will run emacs on both foo.txt and foo.txt.rej, but at the lines
   containing the first patch hunk and the line number of the original that it
   applies to (ok, so this is probably where this script jumped the shark.)

If your $EDITOR is not set to emacs, you won't get the fancy line number stuff.

----------------------------------------------------------------------

traverse.py - various traversals over the known portion of a callgraph.

The callgraph is in the format generated by the rooting hazard analysis.

Commands:

    help
    resolve
    callers
    callees
    route - Find a route from SOURCE to DEST [avoiding FUNC]
    quit
    allcounts
    reachable
    rootpaths
    canreach
    manyroutes
    roots
    routes
    verbose
    callee
    caller
    edges
    output

Use `help <cmd>` to figure out what they do; I'm not going to spend time doing that right now.

----------------------------------------------------------------------

wig - Apply a patch loosely. Works if the surrounding code has changed.

My usual use is to do some VCS command that spits out .rej files, then do `wig
file1.rej` followed by `wig file2.rej` etc. That lets me see any failures one
at a time. But the tool also supports scanning for all reject files.
