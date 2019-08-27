Intro
=====

I thought I'd write up one of those periodic posts describing my workflow. My workflow is not best for everyone. Nor is it the best possible one for me, since I'm a creature of habit and cling to comfortable tools. But it can be helpful to look at what others do, and see what you might be able to steal.

This is going to be more of a summary overview than an in-depth description or tutorial. I am happy to expand on bits you are curious about. Note that there are good docs already for the "normal" workflow at http://mozilla-version-control-tools.readthedocs.io/en/latest/hgmozilla/index.html

A number of things here use local crap that I've piled up over time. I've published a repository containing some of them. At the moment, I have it uploaded to two difference places. I don't know how long I'll keep them in sync before giving up on one:

* (mercurial) https://hg.sr.ht/~sfink/sfink-tools
* (git) https://github.com/hotsphink/sfink-tools

Code Management
===============

I use mercurial. I like mercurial. I used git first, for quite a while, but it just doesn't stick in my brain.

I formerly used mq, and when I'd finally had enough of it, I tried to make my vanilla hg workflow provide as many of the same benefits as possible. I also use evolve[1], though it's mostly just to make some things nicer. I'm currently torn between using bookmarks and topics, and use a little of each.

I use phases heavily to keep track of what's "mine". If you're pushing to any personal repositories, be sure to mark them non-publishing.

Pulling from upstream
---------------------

I use the mozilla-unified repository. I have this in my ~/.hgrc:

    [paths]
    unified = https://hg.mozilla.org/mozilla-unified

so I can pull with

    % hg pull unified

Read more on the unified repo at <http://mozilla-version-control-tools.readthedocs.io/en/latest/hgmozilla/unifiedrepo.html>. I will usually rebase on top of central. `./mach mercurial-setup` should set you up with firefoxtree, which will cause the above pull to advance some local tags that will conveniently give you the head of the various repositories. My usual next step is

    % hg rebase -d central

That assumes you are currently updated to the "patch stack" that you want to rebase, probably with a bookmark at its head (or the whole stack is on a topic.)

What's my state?
----------------

The biggest thing I missed from mq was an easy way to see my current "patch stack". My main tool for this is an alias `hg ls`:

```
    % hg ls
    418116|8b3ea20f546c   Bug 1333000 - Display some additional diagnostic information for ConstraintTypeSet corruption, r=jandem
    418149|44e7e11f4a71   No bug. Attempt to get error output to appear.
    418150|12723a4fa5eb   Bug 1349531 - Remove non-threadsafe static buffers
    418165|9b790021a607   Bug 1367900 - Record the values and thresholds for GC triggers
    418171|5e12353100f6   Bug 1167452 - Incrementalize weakmap marking weakmap.incremental
```

You can't see the colors, sorry. But the first line is orange, and is the public[2] revision that my current patch stack is based on. The remaining lines are the ancestry of my current checkout. Note the weird format: I have it display "<changeset>|<rev>" so I can double-click the hash and copy it. If I were smarter, I would teach my terminal to work with the normal ':' separator. Without breaking URL highlighting.

"weakmap.incremental" is green in my terminal. It's a bookmark name. Bookmarks are my way of keeping track of multiple things I'm working on. They're sort of feature branches, except I have a bad habit of piling up a bunch of unrelated things in my patch stack. If they start interfering with each other too much, I'll rebase them onto the tip of my mozilla-central checkout and give them their own bookmark names:

    % hg rebase -d central weakmap.incremental
    % hg book -r 9b790021a607 gc.triggers
    % hg rebase -d central gc.triggers

The implementation of `hg ls` in my ~/.hgrc is:

    [alias]
    # Will only show changesets that chain to the working copy.
    ls = ![[ -n "$1" ]] && r="$1" || r=.; $HG log -r "with_parents(not public() and ::$r)" --template list
    sl = ls

    [revsetalias]
    with_parents(s) = parents(s) or s

    [templates]
    list = "{label('changeset.{phase}', '{node|short}')} {label('tags.normal', ifeq(tags, '', '', ifeq(tags, 'tip', '', '{tags}\n    ')))}  {desc|firstline} {label('tags.normal', topic)} {label('tags.normal', bookmarks)}\n"

(Note that I mistype `hg ls` as `hg sl` about 40% of the time. You may not be so burdened.) There are better aliases for this. I think ./mach mercurial setup might give you `hg wip` or something now? But I like the terse output format of mine. (Just ignore that monstrosity of a template in the implementation.) You can grab all of this stuff from the same repository that contains this document.

That works for a single stack of patches underneath a root bookmark. To see all of my stacks, I do:

    % hg lsb
    work                           Force-disable JIT optimization tracking
    haz.specialize                 Implement a mechanism to specialize functions on the function pointers passed in
    sixgill.tc                     Try marking JSCompartment as a GCThing for the hazard analysis
    phase-self-time                phase diagnostics -- it really is what I said, with parallel tasks duration
    GCCellPtr.TraceEdge            Implement TraceEdge for GCCellPtr
    weakmap.incremental            Bug 1167452 - Incrementalize weakmap marking

'lsb' stands for 'ls bookmarks'. And the above output is truncated, because it's embarrassing how much outdated crap I have lying around. The implementation of lsb in my ~/.hgrc:

    [alias]
    lsb = log -r 'bookmark() and not public()' -T '{pad("{bookmarks}", 30)} {desc|firstline}\n'

Note that this displays only *non-public* changesets. (A plain `hg bookmarks` will dump out all of them... sorted alphabetically. Bleagh.) That means that when I land something, I don't need to do anything to remove it from my set of active features. If I land the whole stack, then it'll be public and so will disappear from `hg lsb`. If I land part of the stack, then the bookmarked head will still be visible. (But if I bookmarked portions of the stack, then the right ones will disappear. Phases are cool.)

Working on code
---------------

### Updating, bookmarking

When starting on something new, I'll update to 'central'. Then I'll create a bookmark for the feature/fix I'm working on:

    % hg pull unified
    % hg update -r central
    % hg book remove.xul

Notice the clunky name "remove.xul". I formerly used '-' to separate words in my bookmark names, but '-' is a revset operator. It'll still work for many things (and I think it'd work with everything if you did eg `hg log -r 'bookmark("remove-xul")'`, but that's too much typing). Using periods as separators, that's just `hg log -r remove.xul`.

### Making commits

I will start out just editing code. Once it's in a reasonable state, or I need to switch to something else, I'll commit normally:

    % hg commit -m 'make stuff gooder'

Then while I'm being a good boy and continuing to work on the feature named in the bookmark, I'll just keep amending that top commit:

    % hg amend

`hg amend` is a command from the evolve extension[1]. If you're not using it, you could substitute `hg commit --amend`, but it will annoyingly keep asking you to update the commit message. There's a fix, but this document is about my workflow, not yours.

Often, I will get distracted and begin working on a different feature. I *could* update to central and start again, but that tends to touch too many source files and slow down my rebuilds, and I have a lot of inertia, so usually I'll just start hacking within the same bookmarked/topiced patch stack. When done or ready to work on the original (or a new) feature, I'll make another commit.

When I want to go back to working on the original feature, I *still* won't bother to clean things up, because I'm a bad and lazy person. Instead, I'll just start making a bunch of micro-commits pertaining to various of the patches in my current stack (possibly one at a time with `hg commit`, or possibly picking apart my working directory changes with `hg commit -i`; see below). I use a naming convention in the patch descriptions of "M-<which feature I'm changing>". So after a little while, my patch stack might look like:

```shell
    418116|8b3ea20f546c   Bug 1333000 - Display some additional diagnostic information for ConstraintTypeSet corruption, r=jandem
    418149|44e7e11f4a71   No bug. Attempt to get error output to appear.
    418150|12723a4fa5eb   Bug 1349531 - Remove non-threadsafe static buffers
    418165|9b790021a607   Bug 1367900 - Record the values and thresholds for GC triggers
    418171|5e12353100f6   Bug 1167452 - Incrementalize weakmap marking
    418172|deadbeef4dad   M-triggers
    418173|deadbeef4dad   M-static
    418174|deadbeef4dad   M-triggers
    418175|deadbeef4dad   M-weakmap
    418176|deadbeef4dad   M-triggers
```

What a mess, huh? Now comes the fun part. I'm a huge fan of the curses interface to the 'histedit' command. I have an alias to make histedit use a reasonable default for which revisions to show, which I suspect is no longer needed now that histedit has changed to default to something good. But mine is:

    [alias]
    he = histedit -i -r 'not public() and ancestors(.)'

Now `hg he` will bring up a curses interface showing your patch stack. Use j/k to move the highlight around the list. Highlight one of the patches, say the first "M-triggers", and then use J/K (K in this case) to move it up or down in the list. Reshuffle the patches until you have your modification patches sitting directly underneath the main patch, eg

```shell
    pick  418116|8b3ea20f546c   Bug 1333000 - Display some additional diagnostic information for ConstraintTypeSet corruption, r=jandem
    pick  418149|44e7e11f4a71   No bug. Attempt to get error output to appear.
    pick  418150|12723a4fa5eb   Bug 1349531 - Remove non-threadsafe static buffers
    pick  418173|deadbeef4dad   M-static
    pick  418165|9b790021a607   Bug 1367900 - Record the values and thresholds for GC triggers
    pick  418174|deadbeef4dad   M-triggers
    pick  418172|deadbeef4dad   M-triggers
    pick  418176|deadbeef4dad   M-triggers
    pick  418171|5e12353100f6   Bug 1167452 - Incrementalize weakmap marking
    pick  418175|deadbeef4dad   M-weakmap
```

Now use 'r' to "roll" these patches into their parents. You should end up with something like:

```shell
    pick  418116|8b3ea20f546c   Bug 1333000 - Display some additional diagnostic information for ConstraintTypeSet corruption, r=jandem
    pick  418149|44e7e11f4a71   No bug. Attempt to get error output to appear.
    pick  418150|12723a4fa5eb   Bug 1349531 - Remove non-threadsafe static buffers
    roll^ 418173|deadbeef4dad
    pick  418165|9b790021a607   Bug 1367900 - Record the values and thresholds for GC triggers
    roll^ 418174|deadbeef4dad
    roll^ 418172|deadbeef4dad
    roll^ 418176|deadbeef4dad
    pick  418171|5e12353100f6   Bug 1167452 - Incrementalize weakmap marking
    roll^ 418175|deadbeef4dad
```

Notice the caret that shows the direction of the destination patch, and that the commit messages for the to-be-folded patches are gone. If you like giving your micro-commits good descriptions, you might want to use 'f' for "fold" instead, in which case all of your descriptions will be smushed together for your later editing pleasure.

Now press 'c' to commit the changes. Whee! Use `hg ls` to see that everything is nice and pretty.

There is an `hg absorb` command that will take your working directory changes and automatically roll them into the appropriate non-public patch. It is awesome. I actually reach for it first these days, so the above is a little bit of a lie -- I only fall back on the manual histediting when absorb fails me. (Which it will often, correctly, when you make changes that don't happen to overlap the previous changes for a given purpose. But it's safe to use to at least apply the portions that it *can* figure out.)

histedit has other nice tricks. Use 'v' to see the patch. j/k now go up and down a line at a time. Space goes down a page, page up/down work. J/K now switch between patches. Oops, I just noticed I didn't update the help to include that. 'v' to return back to the patch list. Now try 'm', which will bring up an editor after you 'c' commit the changes, allowing you to edit the commit message for each patch so marked.

From my above example, you might think I use one changeset per bug. That's very bug-dependent; many times I'll have a whole set of patches for one bug, and I'll have multiple bugs in my patch stack at one time. If you do that too, be sure to put the bug number in your commit message early to avoid getting confused[4].

### Splitting out changes for multiple patches

I'm not very disciplined about keeping my changes separate, and often end up in a situation where my working directory has changes that belong to multiple patches. Mercurial handles this well. If some of the changes should be applied to the topmost patch, use

    % hg amend -i

to bring up a curses interface that will allow you to select just the changes that you want to merge into that top patch. Or skip that step, and instead do a sequence of

    % hg commit -i -m 'M-foo'

runs to pick apart your changes into fragments that apply to the various changesets in your stack, then do the above.

Normally, I'll use `hg amend -i` to select the new stuff that pertains to the top patch, `hg commit -i` to pick apart stuff for one new feature, and a final `hg commit` to commit the rest of the stuff.

    % hg amend -i  # Choose the stuff that belongs to the top patch
    % hg commit -i -m 'Another feature'
    % hg commit -i -m 'Yet another feature'
    % hg commit -m 'One more feature using the remainder of the changes'

And if you accidentally get it wrong and amend a patch with stuff that doesn't belong to it, then do

    % hg uncommit -a
    % hg amend -i

That will empty out the top patch, leaving the changes in your working directory, then bring up the interface to allow you to re-select just the stuff that belongs in that top patch. The remnants will be in your working directory, so proceed as usual. Alternatively, `hg split` will allow interactively splitting up a patch into multiple parts.

### Navigating through your stack

When I want to work on a patch "deeper" in the stack, I use `hg update -r <rev>` or `hg prev` to update to it, then make my changes and `hg amend` to include them into the changeset. If I am not at the top changeset, this will invalidate all of the other patches. My preferred way to fix this up is to use `hg next --evolve` to rebase the old child on top of my update changeset and update to its new incarnation.

The usual evolve workflow you'll read elsewhere is to run `hg evolve -a` to automatically rebase everything that needs rebasing, but these days I almost always use `hg next --evolve` instead just so it does it one at a time and if a rebase runs into conflicts, it's more obvious to me which changeset is having the trouble. In fact, I made an alias

    [alias]
    advance = !while $HG next --evolve; do :; done

to advance as far as possible until the head changeset is reached, or a conflict occurs. YMMV.

### Resolving conflicts

Speaking of conflicts, all this revision control craziness doesn't come for free. Conflicts are a fact of live, and it's nice to have a good merge tool. I'm not 100% happy with it, but the merge tool I prefer is kdiff3:

    [ui]
    merge = kdiff3

    [merge-tools]
    kdiff3.executable = ~/bin/kdiff3-wrapper
    kdiff3.args = --auto $base $local $other -o $output -cs SyncMode=1
    kdiff3.gui = True
    kdiff3.premerge = True
    kdiff3.binary = False

I don't remember what all that crap is for. It was mostly an attempt to get it to label the different patches being merged correctly, but I did it in the mq days, and these days I ignore the titles anyway. I kind of wish I *did* know which was which. Don't use the kdiff3.executable setting, since you don't have kdiff3-wrapper[5]. The rest is probably fine.

### Uploading patches to bugs

I mostly use moz-phab now to submit bugs.

    % moz-phab submit --reviewer fitzgen --bug 1234567 . .

I usually won't have put the bug number in my commit message yet, but moz-phab will do it for me (at the cost of updating the patch and often erroring out if you have any patches on top of it, since it tries to use the old patch instead of the new. But it's harmless.)

If I don't already have a bug, I will create it via bzexport:

    % hg bzexport --new -r :fitzgen -e --title 'Crashes on Wednesdays'

Now, I must apologize, but that won't work for you. My version of bzexport has fancy schmancy logic to automatically pick the component based on the files touched, and it invokes moz-phab to do the upload. Sorry about that; I'd have to do a bunch of cleanup to make that landable. And these days it would be better to rely on the moz.build bug component info instead of crawling through history.

Other useful flags are `--blocks`, `--depends`, `--cc`, and `--feedback`. Though I'll often fill those in when the editor pops up.

Oh, by the way, if you're nervous about it automatically doing something stupid when you're first learning, run with `-i` aka `--interactive`. It will ask before doing each step. Nothing bad will happen if you ^C out in the middle of that (though it will have already done what you allowed it to do; it can't uncreate a bugzilla bug or whatever, so don't say yes until you mean it.)

If I need to upload multiple patches, I'll update to each in turn (often using `hg next` and `hg prev`, which come with evolve) and run `hg bzexport` for each. You don't have to; or at least, I *think* I landed the patches to bzexport so that it will properly upload arbitrary non-tip patches in your stack.

### Uploading again

I originally had a detailed description of how bzexport helps with this case, but these days you'll need to use moz-phab and suffer through its weirdnesses.

### Incorporating review comments

I've already covered this. Update to the appropriate patch, make your changes, `hg amend`, `hg advance` to clean up any conflicts right away, then probably `hg update -r <...>` to get back to where you were.

### Landing

I'll usually do a final try push. I `cd` to the top of my source checkout, then run:

    % ./mach try <try args>

If you don't know try syntax, use `mach try chooser` to construct one. I've trained my brain to know various ones useful to what I work on, but you can't go too far wrong with

    % ./mach try -b do -p all -u all[x64]

### Forking your stack

If you commit a changeset on top of a non-top patch, you will fork your stack. The usual reason is that you've updated to some changeset, made a change, and run `hg commit`. You now have multiple heads. hg will tell you "created new head". Which is ok, except it's not, because it's much more confusing than having a simple linear patch stack. (Or rather, a bunch of linear patch stacks, each with a bookmark at its head.)

I usually look up through my terminal output history to find the revision of the older head, then rebase it on top of the new head. But if you don't have that in your history, you can find it with the appropriate `hg log` command. Something like

    % hg log -r 'children(.^) and not .'
    changeset:   418174:b7f1d672f3cd

will give it to you directly (see also `hg help revsets`), assuming you haven't done anything else and made a mess. Now rebase the old child on top of your new head:

    % hg rebase -b b7f1d672f3cd -d .

It will leave you updated to your new head, or rather the changeset that was formerly a head, but the other changesets will now be your descendants. `hg next` a bunch of times to advance through them, or use my `hg advance` alias to go all the way, or do it directly:

    % hg update -r 'heads(.::)'

(if you're not used to the crazy revset abbreviations, you may prefer to write that as `hg update -r 'heads(descendants(.))'`. I'm trying not to use too many abbreviations in this doc, but typing out "descendants" makes my fingers tired.)

Workspace management
====================

So being able to jump all over your various feature bookmarks and things is cool, but I'm working with C++ here, and I hate touching files unnecessarily because it means a slow and painful rebuild. Personally, I keep two checkouts, ~/src/mozilla and ~/src/mozilla2. If I were more disciplined about disk space, I'd probably have a few more. Most people have several more. I used to have clever schemes of updating a master repository and then having all the others pull from it, but newer hg (and my network) is fast enough that I now just `hg pull unified` manually whenever I need to. I use the default objdir, located in the top directory of my source checkout, because I like to be able to run hg commands from within the objdir. But I suspect it messes me up because hg and watchman have to deal with a whole bunch of files within the checkout area that they don't care about.

watchman
--------

Oh yeah, watchman. It makes many operations way, way faster. Though everything is still slow.

I can't remember how to set up watchman, sorry. It looks like I built it from source? Hm, maybe I should update, then. You need two pieces: the watchman daemon that monitors the filesystem, and the python mercurial extension that talks to the daemon to accelerate hg operations. The latter part can be enabled with

    [extensions]
    fsmonitor =

Maybe ./mach bootstrap sets up watchman for you these days? And ./mach mercurial-setup sets up fsmonitor? I don't know.

Debugging
=========

debug
-----

I have this crazy Perl script that I've hacked in various horrible ways over the years. It's awful, and awfully useful. If I'm running the JS shell, I do

    % debug ./obj-js-debug/dist/bin/js somefile.js

to start up Emacs with gdb running inside it in gud mode. Or

    % debug --record ./obj-js-debug/dist/bin/js somefile.js

to make an rr recording of the JS shell, then bring up Emacs with rr replay running inside it. Or

    % debug --record ./jstests.py /obj-js-debug/dist/bin/js sometest.js

to make an rr recording of a whole process tree, then find a process that crashed and bring up Emacs with rr replay on that process running inside it. Or

    % debug

to bring up Emacs with rr replay running on the last rr recording I've made, again automatically picking a crashing process. If it gets it wrong, I can always do

    % rr ps
    # identify the process of interest
    % debug --rrpid 1234

to tell it which one. Or

    % ./mach mochitest --debugger=debug some/test/file

to run the given test with hopefully the appropriate binary running under gdb inside Emacs inside the woman who swallowed a fly I don't know why. Or if you're truly crazy,

    % debug --js ./obj-js-debug/dist/bin/js somefile.js

brings up Emacs running jorendb[7].

rr
--

I love me my rr. I have a .gdbinit.py startup file that creates a handy command for displaying the event number and tick count to keep me oriented chronologically:

    (rr) now
    2592/100438197

Or I can make rr display that output on every prompt:

    (rr) set rrprompt on
    rr-aware prompt enabled
    (rr 538/267592) fin
    Run till exit from #0 blah blah
    (rr 545/267619)

I have a .gdbinit file with some funky commands to set hardware watchpoints on GC mark bits so I can 'continue' and 'reverse-continue' through an execution to find where the mark bits are set. And strangely dear to my heart is the 'rfin' command, which is just an easier to type alias for 'reverse-finish'. Other gdb commands:

    (rr) log $thread sees the bad value  # $thread is replaced by eg T1
    (rr) log also, obj is now $1         # gdb convenience vars ok
    (rr) rfin
    (rr) log {$2+4} bytes are required   # {any gdb expr}
    (rr) n
    (rr) log
       346/945 7 bytes are required
    => 562/8443 T2 sees the bad value
       562/8443 also, obj is now 0x7ff687749c00
    (rr) log/e                           # brings up $EDITOR on your full log file

The idea is to be able to move around in time, logging various things, and then use `log` to display the log messages *in chronological order according to the execution*. (Note that when you do this, the next point in time coming up will be labeled with "=>" to show you when you are.) You might consider using this in conjunction with `command` as a simple way of automatically tracing the evolution of some value:

    (rr) b HashTable::put
    Breakpoint 1 set at HashTable::put(Entry)
    (rr) comm 1
    > log [$thread] in put(), table size is now {mEntries}
    > cont
    > end
    (rr) c

Boom! You now have the value of mEntries every time put() is called. Or consider doing that with a hardware watchpoint. (But watch out for log messages in breakpoints; it will execute the log command every time you encounter the breakpoint, so if you go forwards and backwards across the breakpoint several times, you'll end up with a bunch of duplicate entries in your log. `log/e` is useful for manually cleaning those up.)

Note that the default log filename is based on the process ID, and the logging will append entries across multiple `rr replay` runs. So if you run muliple sessions of `rr replay` on the same process recording, all of your log messages will be collected together. Use `set logfile <filename>` to switch to a different file.

Finally, there's a simple `pp` command, where `pp foo` is equivalent to `python print(foo)`.

----

[1] https://www.mercurial-scm.org/wiki/EvolveExtension - install evolve with `pip install --user hg-evolve`, or manually by cloning `hg clone https://www.mercurial-scm.org/repo/evolve/` somewhere, then adding it into your ~/.hgrc:

    [extensions]
    evolve = ~/lib/hg/evolve/hgext3rd/evolve

[2] "public" is the name of a mercurial phase. It means a changeset that has been pushed to mozilla-central or similar. Stuff you're working on will ordinarily be in the "draft" phase until you push it. [↩](#a1)

[3] There is no [3] anymore. But it was: `hg clone https://bitbucket.org/facebook/hg-experimental` somewhere, then activate it with

    [extensions]
    chistedit = ~/lib/hg/hg-experimental/hgext3rd/chistedit.py

[4] When I have one patch per bug, I'll usually use `hg bzexport --update` to fill in the bug numbers. Especially since I normally file the bug in the first place with `hg bzexport --new`, so I don't even have a bug number until I do that.

[5] kdiff3-wrapper was pretty useful back in the day; kdiff3 has a bad habit of clearing the execute (chmod +x) bit when merging, so kdiff3-wrapper is a shell script that runs kdiff3 and then fixes up the bits afterwards. I don't know if it still has that issue?

[6] There is no footnote 6. It formerly referred to a not-yet-landed patch to bzexport, which I have now landed.

[7] jorendb is a relatively simple JS debugger that jorendorff wrote, I think to test the Debugger API. I suspect he's amused that I attempt to use it for anything practical. I'm sure the number of people for whom it is relevant is vanishingly small, but I love having it when I need it. (It's for the JS shell only. Nobody uses the JS shell for any serious scripting; why would you, when you have a full web browser, and Node if you don't want that?) (I'm Nobody.)
