Steve Fink's collection of random tools

These are tools that I think might be useful to other people.

----------------------------------------------------------------------

Tools included:

 - artifetch : Retrieve artifacts from pushes, according to a flexible query spec. Example: give me the performance score from all runs (replicates) of the "id-getter-5.html" Talos subtest from a fzf-selected set of pushes.
 - landed : Prune changesets that have landed, setting their successors to the landed
   revisions.
 - run-taskcluster-job : Run taskcluster jobs in a local Docker container.
 - get-taskcluster-logs : Retrieve groups of log files from a push by scraping taskcluster
 - em / vs : Open emacs or VSCode on the files touched by a patch, on a relevant
   line number
 - viewsetup : Construct a virtual disk that exposes selected portions of a local disk,
   to allow running a Windows install either physically or virtually
 - json : Interactive navigation of a JSON file
 - debug : Start up a debugger within emacs on various types of files
 - rr-exits : List out all rr recordings with their worst exit codes
 - traverse.py : Gecko-specific, sorta. Utility for traversing a callgraph.
 - wig : Patch harder

----------------------------------------------------------------------

Configuration files:

I also have a set of gdb initialization files that I version-control here.

 - gdbstart.py : gdb init file that loads all of the below gdb startup files (except for gdbinit.sfink)
 - gdbinit : basic gdb configuration
 - gdbinit.py : gdb python init file, defines some miscellany
 - gdbinit.symbols.py : Ted Mielczarek's source server integration for gdb
 - gdbinit.pahole.py : pahole and overlap commands, loaded by gdbstart.py
 - gdbinit.gecko.py : configuration to assist with debugging Gecko and SpiderMonkey
 - gdbinit.misc : some miscellaneous gdb helper commands
 - gdbinit.rr.py : gdb helper commands for running under rr (lots here!)
 - gdbinit.sfink : a couple of things that depend on my personal file layout

The easiest way to use these is to create a `~/.gdbinit` file with something
like the following, with the appropriate path to your sfink-tools checkout:

    source ~/checkouts/sfink-tools/conf/gdbstart.py

That will load all of the above except for `gdbinit.sfink`. Alternatively, you
could just source the individual files you want to use from the above list.

Other configuration files:

 - hgrc : Mercurial configuration

I use this via a symlink from ~/.hgrc.

----------------------------------------------------------------------

landed - Prune patches that have landed, setting their successors to the landed
revisions.

Typical usage:

    hg pull
    landed

That will look at the non-public (aka draft, probably) ancestors of your
checked out revision, and scan for matching phabricator revisions (or commit
messages, if phabricator revisions are not present) within the landed tree.
You'll want to download the latest set of landed changes first, so they exist
locally.

You can also do this in a more targeted way:

    landed -r 30deabdff172

(or a revspec matching multiple patches).

Note that this will not rebase any orphaned patches for you, so if you are
pruning landed patches with descendants that have not yet been landed, you will
need to rebase them (eg by running `hg evolve` or `hg evolve -a` or whatever.)

----------------------------------------------------------------------

run-taskcluster-job : Run taskcluster jobs in a local Docker container.

    run-taskcluster-job --log-task-id a5gT2XbUSGuBd-IMAjjTUw

to replicate task a5gT2XbUSGuBd-IMAjjTUw locally. The above command will

 - download the log file for that task
 - find the line that says the task ID of the toolchain task that generated the
   image that it is running
 - use `mach taskcluster-load-image` to pull down that image
 - once you have the image, use `--task-id` in later runs to avoid re-downloading things
 - download the task description from taskcluster to extract out the command that
   is to be executed and the environment variables
 - execute the image (run `$COMMAND` from within the image to run the default command,
   or `echo $COMMAND` to inspect and modify it.)

Note that $COMMAND will probably execute `run-task` with a gecko revision,
which will start out by pulling down the whole tree. This is large and will
take a while. (Avoiding this requires hacking the script a bit;
https://bugzilla.mozilla.org/show_bug.cgi?id=1605232 was an early attempt at
that.)

----------------------------------------------------------------------

em / vs - Edit files relevant to a patch

Run your $EDITOR (defaulting to emacs) on the given files, or on the files
touched by the changes described by the given revision.

If $EDITOR is unset, then `em` will default to `emacs` and `vs` will default to
`vscode` (you will need to create a symlink from `vs` -> `em`).

If you are using vscode remote editing, you will want to install this on the
remote machine and run it from within a terminal there.

1. `em foo.txt:33` will run `emacs +33 foo.txt`
   so will `em foo.txt:33:` (easier cut & paste of trailing colon for error messages)
   and foo.txt will be found anywhere in the current hg tree (if not in cwd)
2. `em` with no args will run emacs on the files changed in the cwd, or if none, then
   by the cwd's parent hg rev
3. `em 01faf51a0acc` will run emacs on the files changed by that hg rev.
4. `em foo.txt.rej` will run emacs on both foo.txt and foo.txt.rej, but at the lines
   containing the first patch hunk and the line number of the original that it
   applies to (ok, so this is probably where this script jumped the shark.)

The fancy line number stuff does not apply to all possible editors. emacs and
vscode are fully supported, though vscode's behavior is a little erratic. vi
will only set the position for the first file.

Sorry, no git support.

----------------------------------------------------------------------

get-taskcluster-logs - Retrieve groups of log files from a push by scraping taskcluster

Typical example: copy link location to a taskcluster push (what you get from
clicking on the date for a push), and run

    get-taskcluster-logs '<url>'

Alternatively, use the topmost revision of a push with the -r flag:

    get-taskcluster-logs -r <rev>

By default, this downloads all logs for all Talos jobs in that push, and stores
them in individual text files under a new directory.

See --help for additional options and usage.

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
hi dad
