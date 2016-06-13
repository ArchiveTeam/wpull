Contributing
============

Thank you for your interest in contributing!


Issues
------

Hopefully you are arriving from
[the documentation](https://wpull.readthedocs.io/). If not, please take
a moment to read it. Updated documentation is provided on "latest"
version.

When reporting a bug or asking a question, please search to see if your
bug report exists or your question has been already answered.

When opening an issue, include lots of details about your problem and
information that we can use to reproduce the problem. There are many
resources that describe how to file a good bug report such as
<https://developer.mozilla.org/en-US/docs/Mozilla/QA/Bug_writing_guidelines>.

Concisely, we need to know:

* What you want
* What you expect
* What happened
* Commands to reproduce the issue
* Program versions
* Your computer details
* Debugging output and sample files

When you file an issue, a template should appear for you to fill out.


Pull requests
-------------

If you are planning to fix a bug or add a feature, please take some
time to review this section.


### Code convention

Please follow the [PEP8](https://www.python.org/dev/peps/pep-0008/)
conventions whenever possible. 

If the current code does not follow it, please do not make
a pull request that formats all the code with a program automatically.
Instead, incrementally make the corrections that are affected in your
bug fixes or features. This will help make Git's blame feature easier
use.


### Commits and commit messages

Please don't PR a single huge commit or hundreds of commits. Do your
best to group changes logically.

Give your commit messages meaningful descriptions. Make the first line
a short title describing the changes and then add an optional paragraph
describing why you made those changes.


### Branch model

This project is still small but we intend to follow 
[nvie's git branching model]
(http://nvie.com/posts/a-successful-git-branching-model/) to structure
the Git repository in the future. This means:

* The stable code is located on the `master` branch which is the default.
* The current work of focus is located on the `develop` branch.
* There is currently no release branches.
* Changes flow into the `develop` branch, then the `master` branch.

Because of the branching model, there are two options of branching:

* From a stable point, that is the `master` branch
* From an active point, that is a the `develop` branch

If you are making a small bug fix and are new to this project, we
suggest branching off the `master` branch so we can integrate your
changes properly. Otherwise, branch off the `develop` branch.

If you are adding a feature, please branch from the `develop` branch. 
If you branch from `master`, your changes may not merge anymore on the
next release. If needed, file an issue to discuss the roadmap of the
feature to avoid any rejection and disappointment.

One branch per bug/feature. Don't stack PR on top of other PR branches!


### Testing

Testing can be done by using [Nose](http://nose.readthedocs.io/). 
As described in Nose documentation, run `nosetests3` in the top
level of the project directory.

Additionally, the project is [configured to use the free Travis CI]
(https://travis-ci.org/chfoo/wpull).


### Making the PR

When you file a pull request, a template will appear reminding you
of this document. It will also remind you to:

* Update or add unit tests if needed.
* Update or add documentation/comments if needed.
* Describe *what* you changed and *why* you changed them.
* Set GitHub merge options to merge into `develop` if you branch
  from `develop`.

GitHub will also run tests on the code. If there is an error,
please take a look at to see if it is related to your PR.
See Testing above. Sometimes the build is broken and may not be
your fault. If you need to make more changes, add your commits to
the submitted branch. If the issue can't be resolved easily,
close the PR and make a new one when ready.
