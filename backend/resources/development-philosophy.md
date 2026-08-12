---
title: Development Philosophy
type: philosophy
tags: [development-philosophy, philosophy, professional-profile, theories, methodologies, preferences, solid, dry, kiss, yagni, oop, waterfall, iterative-development, code-quality, maintainability, readability, pragmatism, software-design]
summary: How Michael approaches writing software - SOLID as the baseline, with DRY, KISS and YAGNI applied pragmatically rather than dogmatically. He rejects the waterfall model and holds that OOP design should evolve organically, iteration by iteration, rather than being fixed up front. He is also candid about the limits of his own experience, and treats leaving a system simpler than he found it as part of the job.
---

## Principles
SOLID is broadly how I think about design, and I keep the other usual
principles in mind alongside it. Code should be simple (KISS) and easy to read,
because that is what makes it possible to change later.

## Against waterfall
I don't believe in the waterfall development model — it simply isn't viable for
me, and I doubt it is for anyone. It assumes the final design can be settled
before the work starts, and in my experience that is exactly the thing you
cannot know up front.

## Design evolves organically
I'm a proponent of OOP design that evolves organically: code gets better per
iteration, and each iteration reveals the next pragmatic move. That move often
isn't creating a polymorphic class or an abstraction for something you might
not need, just for the sake of the principle (YAGNI). I would rather let a
design earn its abstractions from real use than guess up front and get locked
into the wrong abstraction.

I have a version of the same problem with DRY taken to the extreme, especially
in the first iterations of the development phase — deduplicating hard at that
point doesn't make much sense to me, because the final design is still hard to
determine. Of course one should aim for DRY code, but pragmatism should take
precedence, so that the design can evolve. When removing duplication costs more
in indirection than the duplication itself does, the duplication is the better
trade.

## Be honest about limits
I would rather state the boundary of what I've actually done than let an
impression stand uncorrected. That runs through these CV records: where my
experience is partial, it says so — I haven't used C++ since about 2005, and my
Kubernetes work was through a cluster management UI rather than authoring raw
manifests or designing cluster architecture. The same applies to seniority (see
"Role Fit"): strong junior-to-mid with senior-level scope, not senior-level
years. However, sometimes I can be too hard on myself.

## Leave it simpler than you found it
Reducing what the next person has to maintain is part of the work, not a
nice-to-have.