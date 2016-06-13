====
Help
====


Frequently Asked Questions
==========================


What does it mean by "Wget-compatible"?
+++++++++++++++++++++++++++++++++++++++

It means that Wpull behaves similarly to Wget, but the internal machinery
that powers Wpull is completely different from Wget.


What advantages does Wpull offer over Wget?
+++++++++++++++++++++++++++++++++++++++++++

The motivation for the development of Wpull is to find a replacement
for Wget that does not store URLs in memory and is scriptable.

Wpull has support for using a on-disk database so memory requirements
remain constant. Wget only stores URLs in memory, Wget will eventually
run out of memory if you want to crawl millions of URLs at once.

Another motivation is to provide hooks that accept/reject URLs during
the crawl.


What advantages does Wget offer over Wpull?
+++++++++++++++++++++++++++++++++++++++++++

Wget is much more mature and stable. With many developers working on
Wget, bug fixes and features arrive faster.

Wget is also written in C which can handle text much faster. Wpull
is written in Python which was not designed for blazing fast
processing of data. This means that Wpull can be slow processing
large documents.


How can change things while it is running? / Is there a GUI or web interface to make things easier?
+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

Wpull does not offer a user-friendly interface to make changes as it
runs at this time. However, please check out
https://github.com/ludios/grab-site which is a web interface built on
of Wpull


Wpull is giving an error or not performing correctly.
+++++++++++++++++++++++++++++++++++++++++++++++++++++

Check that you have the options correct. In most cases, it is a misunderstanding of `Wget options <https://www.gnu.org/software/wget/manual/wget.html>`_.

Otherwise if Wpull is not doing what you want, please visit the `issue tracker
<https://github.com/chfoo/wpull/issues>`_ and see if your issue is there.
If not, please inform the developers by creating a new issue.

When you open a new issue, GitHub provides a link to the guidelines
document. Please read it to learn how to file a good bug report.


How can I help the development of Wpull? What are the development goals?
++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

Please visit the [GitHub repository](https://github.com/chfoo/wpull).
From there, you can take a look at:

* The Contributing file for specific instructions on how to help
* The issue tracker for current bugs and features
* The Wiki for the roadmap of the project such as goals and statuses
* And the code, of course


How can I chat or ask a question?
+++++++++++++++++++++++++++++++++

For chatting and quick questions, please visit the "unoffical" IRC
channel: `#archiveteam-bs <irc://irc.efnet.org/archiveteam-bs>`_ on
EFNet. (`Click here <http://chat.efnet.org:9090/?channels=%23archiveteam-bs>`_
if you do not have an IRC client.)

Alternatively if the discussion is lengthy, please use the issue
tracker as described above. As a courtesy, if your question is
answered on the issue tracker, please close the issue to mark
your question as solved.

We *highly* prefer that you use IRC or the issue tracker. But email is
also available: chris.foo@gmail.com
