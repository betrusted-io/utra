# Unambiguous Thin Register Abstraction (UTRA)

## Motivation

UTRA is a register abstraction for accessing hardware resources. It tries to be:

* Unambiguous -- the access rules should be concise and unambiguous to a systems programmer with a C background
* Thin -- it should hide constants, but not bury them so they become difficult to verify

Here is an example of an ambiguous style of register access, from the PAC crate:

```
    // this seems clear -- as long as all the bit fields are specified
    // (they actually aren't, so some non-obvious things are happening)
    p.POWER.power.write(|w| 
       w.discharge().bit(true)
        .soc_on().bit(false)
        .kbddrive().bit(true)
        .kbdscan().bits(3)
      );

    // what should this do?
    // 1. just set the discharge bit to true and everything else to zero?
    // 2. read the register first, change only the discharge bit to true, leaving the rest unchanged?
    p.POWER.power.write(|w| 
       w.discharge().bit(true)
      );
      
    // answer: it does (1). You need to use the `modify()` function to have (2) happen.

```

While the closure-chaining is clever syntax, it's also ambiguous.
First, does the chaining imply an order of writes happening in
sequence, or do they all happen at once? The answer depends on Rust's
optimizer, which is very good and one can expect the behavior to be
the latter, but it is still write-ordering behavior that depends upon
the outcome of an optimizer and not a linguistic guarantee. Second,
the term `write` itself is ambiguous when it comes to bitfields: do we
write just the bitfield, or do we write the entire register, assuming
the rest of the contents are zero? These types of ambiguity make it
hard to audit code, especially for experts in systems programming
who are not also experts in Rust.

The primary trade-off for achieving unambiguity and thinness is less
type checking and type hardening, because we are not fully taking
advantage of the advanced syntax features of Rust. 

That being said, a certain degree of deliberate malleability in the
register abstraction is desired to assist with security-oriented
audits: for a security audit, it is often just as important to ask
what the undefined bits do, as it is to check the settings of the
defined bits. Malleabilty allows an auditor to quickly create targeted
tests that exercise undefined bits. Existing Rust-based access crates
create strict types that eliminate the class of errors where constants
defined for one register are used in an incorrect type of register,
but they also make it very hard to modify in an ad-hoc manner.

