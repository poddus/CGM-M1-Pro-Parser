# CGM-M1-Pro-Parser
CGM M1 Pro has the option to export various record lists to files. Unfortunately (like most things in the software),
this functionality hasn't been updated for about 2 decades. The lists don't share a common format, they don't even
share the same line width. This makes working with lists outside of CGM M1 Pro basically impossible (perhaps this
by design).

This parser attempts to bring the export functionality into the current century. The lowest bar for success is the
ability to extract patient IDs from the various lists in order to perform set operations that would not be possible
within the program. At best this parser should be able to transform the export lists into various other modern
data interchange formats.
