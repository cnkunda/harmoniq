# W4 tablature assignment — amt-eval-v1

Evaluation: symbolic MIDI→tab assignment on reference pitches. Tuning/capo variants are augmented, not recorded audio.

Tracks: 62
Notes: 9550 · Skipped: 0

## Gate (base variant)

| Metric | allCellsForMidi | DP | Delta |
| --- | ---: | ---: | ---: |
| Pitch accuracy | 1.0 | 1.0 | 0.0 |
| Tab accuracy | 0.503141 | 0.589319 | 0.086178 |
| Difficulty (lower is better) | 2.452866 | 2.60921 | +0.156344 |
| Group validity | 0.507634 | 1.0 | 0.492366 |

**Gate: PASS (passed on tab_accuracy)**

## Variants

| Variant | Mode | Tracks | Notes | Pitch acc | Tab acc | Difficulty | Group validity |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| base | baseline | 62 | 9550 | 1.0 | 0.503141 | 2.452866 | 0.507634 |
| base | dp | 62 | 9550 | 1.0 | 0.589319 | 2.60921 | 1.0 |
| capo_1 | baseline | 62 | 9550 | 1.0 | 0.503141 | 2.452866 | 0.507634 |
| capo_1 | dp | 62 | 9550 | 1.0 | 0.589319 | 2.60921 | 1.0 |
| capo_2 | baseline | 62 | 9550 | 1.0 | 0.503141 | 2.452866 | 0.507634 |
| capo_2 | dp | 62 | 9550 | 1.0 | 0.589319 | 2.60921 | 1.0 |
| capo_3 | baseline | 62 | 9550 | 1.0 | 0.503141 | 2.452866 | 0.507634 |
| capo_3 | dp | 62 | 9550 | 1.0 | 0.589319 | 2.60921 | 1.0 |
| capo_4 | baseline | 62 | 9550 | 1.0 | 0.503141 | 2.452866 | 0.507634 |
| capo_4 | dp | 62 | 9550 | 1.0 | 0.589319 | 2.60921 | 1.0 |
| capo_5 | baseline | 62 | 9550 | 1.0 | 0.503141 | 2.452866 | 0.507634 |
| capo_5 | dp | 62 | 9550 | 1.0 | 0.589319 | 2.60921 | 1.0 |
| capo_6 | baseline | 62 | 9550 | 1.0 | 0.503141 | 2.452866 | 0.507634 |
| capo_6 | dp | 62 | 9550 | 1.0 | 0.589319 | 2.60921 | 1.0 |
| capo_7 | baseline | 62 | 9550 | 1.0 | 0.503141 | 2.452866 | 0.507634 |
| capo_7 | dp | 62 | 9550 | 1.0 | 0.589319 | 2.60921 | 1.0 |
| tuning_drop_d | baseline | 62 | 9550 | 1.0 | 0.510576 | 2.495472 | 0.507634 |
| tuning_drop_d | dp | 62 | 9550 | 1.0 | 0.605026 | 2.650722 | 1.0 |
| tuning_full_step_down | baseline | 62 | 9550 | 1.0 | 0.503141 | 2.452866 | 0.507634 |
| tuning_full_step_down | dp | 62 | 9550 | 1.0 | 0.589319 | 2.60921 | 1.0 |
| tuning_half_step_down | baseline | 62 | 9550 | 1.0 | 0.503141 | 2.452866 | 0.507634 |
| tuning_half_step_down | dp | 62 | 9550 | 1.0 | 0.589319 | 2.60921 | 1.0 |

## Per-track (base variant)

| Track | Source | Split | Notes | Base tab | DP tab | Base diff | DP diff |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| egset12:09 | egset12 | test | 89 | 0.280899 | 0.191011 | 3.475962 | 3.8125 |
| egset12:11 | egset12 | test | 103 | 0.359223 | 0.398058 | 2.342697 | 2.63764 |
| guitarset:03_BN1-129-Eb_comp | guitarset | test | 157 | 0.127389 | 0.324841 | 2.210938 | 2.074219 |
| guitarset:03_BN1-129-Eb_solo | guitarset | test | 58 | 0.396552 | 0.396552 | 3.25 | 3.25 |
| guitarset:03_BN1-147-Gb_comp | guitarset | test | 155 | 0.980645 | 0.967742 | 1.851562 | 1.808594 |
| guitarset:03_BN1-147-Gb_solo | guitarset | test | 64 | 0.828125 | 0.859375 | 2.440476 | 2.384921 |
| guitarset:03_BN2-131-B_comp | guitarset | test | 230 | 0.543478 | 0.617391 | 1.387363 | 1.447802 |
| guitarset:03_BN2-131-B_solo | guitarset | test | 72 | 0.361111 | 0.388889 | 3.172535 | 3.130282 |
| guitarset:03_BN2-166-Ab_comp | guitarset | test | 200 | 0.245 | 0.36 | 1.834416 | 1.957792 |
| guitarset:03_BN2-166-Ab_solo | guitarset | test | 76 | 0.328947 | 0.342105 | 3.02027 | 3.013514 |
| guitarset:03_BN3-119-G_comp | guitarset | test | 199 | 0.326633 | 0.512563 | 1.431818 | 1.603896 |
| guitarset:03_BN3-119-G_solo | guitarset | test | 79 | 0.303797 | 0.316456 | 3.676282 | 3.666667 |
| guitarset:03_BN3-154-E_comp | guitarset | test | 181 | 0.132597 | 0.187845 | 1.746429 | 1.728571 |
| guitarset:03_BN3-154-E_solo | guitarset | test | 66 | 0.257576 | 0.287879 | 2.464286 | 2.428571 |
| guitarset:03_Funk1-114-Ab_comp | guitarset | test | 174 | 0.390805 | 0.666667 | 3.027778 | 3.515432 |
| guitarset:03_Funk1-114-Ab_solo | guitarset | test | 96 | 0.239583 | 0.25 | 2.123684 | 2.121053 |
| guitarset:03_Funk1-97-C_comp | guitarset | test | 259 | 0.737452 | 0.741313 | 2.08547 | 2.239316 |
| guitarset:03_Funk1-97-C_solo | guitarset | test | 105 | 0.247619 | 0.257143 | 3.757653 | 3.793367 |
| guitarset:03_Funk2-108-Eb_comp | guitarset | test | 299 | 0.545151 | 0.782609 | 2.266791 | 2.794776 |
| guitarset:03_Funk2-108-Eb_solo | guitarset | test | 127 | 0.598425 | 0.590551 | 2.627083 | 2.604167 |
| guitarset:03_Funk2-119-G_comp | guitarset | test | 234 | 0.444444 | 0.641026 | 2.275 | 3.091667 |
| guitarset:03_Funk2-119-G_solo | guitarset | test | 106 | 0.54717 | 0.556604 | 2.5875 | 2.545 |
| guitarset:03_Funk3-112-C#_comp | guitarset | test | 203 | 0.482759 | 0.70936 | 1.898585 | 2.441038 |
| guitarset:03_Funk3-112-C#_solo | guitarset | test | 121 | 0.330579 | 0.355372 | 2.525641 | 2.5 |
| guitarset:03_Funk3-98-A_comp | guitarset | test | 395 | 0.21519 | 0.617722 | 2.633152 | 3.315217 |
| guitarset:03_Funk3-98-A_solo | guitarset | test | 135 | 0.266667 | 0.288889 | 3.257634 | 3.257634 |
| guitarset:03_Jazz1-130-D_comp | guitarset | test | 90 | 0.333333 | 0.6 | 1.210938 | 2.148438 |
| guitarset:03_Jazz1-130-D_solo | guitarset | test | 70 | 0.385714 | 0.4 | 2.721014 | 2.706522 |
| guitarset:03_Jazz1-200-B_comp | guitarset | test | 82 | 0.134146 | 0.597561 | 2.196429 | 3.0 |
| guitarset:03_Jazz1-200-B_solo | guitarset | test | 43 | 0.232558 | 0.232558 | 3.35119 | 3.309524 |
| guitarset:03_Jazz2-110-Bb_comp | guitarset | test | 132 | 0.0 | 0.075758 | 1.5 | 2.209302 |
| guitarset:03_Jazz2-110-Bb_solo | guitarset | test | 99 | 0.272727 | 0.30303 | 3.315104 | 3.286458 |
| guitarset:03_Jazz2-187-F#_comp | guitarset | test | 102 | 0.470588 | 0.578431 | 1.314286 | 1.5 |
| guitarset:03_Jazz2-187-F#_solo | guitarset | test | 72 | 0.402778 | 0.402778 | 2.598592 | 2.591549 |
| guitarset:03_Jazz3-137-Eb_comp | guitarset | test | 107 | 0.420561 | 0.485981 | 1.78125 | 1.776042 |
| guitarset:03_Jazz3-137-Eb_solo | guitarset | test | 97 | 0.463918 | 0.474227 | 2.568421 | 2.568421 |
| guitarset:03_Jazz3-150-C_comp | guitarset | test | 101 | 0.257426 | 0.405941 | 1.217949 | 1.916667 |
| guitarset:03_Jazz3-150-C_solo | guitarset | test | 77 | 0.415584 | 0.428571 | 3.532895 | 3.526316 |
| guitarset:03_Rock1-130-A_comp | guitarset | test | 212 | 0.938679 | 0.915094 | 1.237037 | 1.268519 |
| guitarset:03_Rock1-130-A_solo | guitarset | test | 58 | 0.172414 | 0.172414 | 2.328947 | 2.307018 |
| guitarset:03_Rock1-90-C#_comp | guitarset | test | 204 | 0.568627 | 0.617647 | 1.881148 | 1.875 |
| guitarset:03_Rock1-90-C#_solo | guitarset | test | 75 | 0.106667 | 0.106667 | 3.408451 | 3.40493 |
| guitarset:03_Rock2-142-D_comp | guitarset | test | 259 | 0.409266 | 0.57529 | 1.75 | 1.917832 |
| guitarset:03_Rock2-142-D_solo | guitarset | test | 88 | 0.363636 | 0.409091 | 3.360465 | 3.290698 |
| guitarset:03_Rock2-85-F_comp | guitarset | test | 260 | 0.546154 | 0.696154 | 1.753571 | 2.342857 |
| guitarset:03_Rock2-85-F_solo | guitarset | test | 97 | 0.670103 | 0.670103 | 2.43617 | 2.43617 |
| guitarset:03_Rock3-117-Bb_comp | guitarset | test | 241 | 0.809129 | 0.825726 | 1.572266 | 1.730469 |
| guitarset:03_Rock3-117-Bb_solo | guitarset | test | 94 | 0.297872 | 0.319149 | 3.383333 | 3.305556 |
| guitarset:03_Rock3-148-C_comp | guitarset | test | 293 | 1.0 | 0.959044 | 1.302365 | 1.236486 |
| guitarset:03_Rock3-148-C_solo | guitarset | test | 66 | 0.333333 | 0.454545 | 5.441406 | 5.394531 |
| guitarset:03_SS1-100-C#_comp | guitarset | test | 368 | 0.467391 | 0.521739 | 1.619512 | 1.714634 |
| guitarset:03_SS1-100-C#_solo | guitarset | test | 111 | 0.432432 | 0.459459 | 2.823077 | 4.319231 |
| guitarset:03_SS1-68-E_comp | guitarset | test | 256 | 1.0 | 0.988281 | 0.935294 | 0.925 |
| guitarset:03_SS1-68-E_solo | guitarset | test | 92 | 0.26087 | 0.271739 | 3.114943 | 3.100575 |
| guitarset:03_SS2-107-Ab_comp | guitarset | test | 395 | 0.56962 | 0.724051 | 1.715802 | 1.992925 |
| guitarset:03_SS2-107-Ab_solo | guitarset | test | 101 | 0.326733 | 0.326733 | 3.315 | 3.315 |
| guitarset:03_SS2-88-F_comp | guitarset | test | 340 | 0.502941 | 0.647059 | 1.810484 | 2.18414 |
| guitarset:03_SS2-88-F_solo | guitarset | test | 98 | 0.479592 | 0.489796 | 2.857895 | 2.852632 |
| guitarset:03_SS3-84-Bb_comp | guitarset | test | 186 | 0.849462 | 0.887097 | 1.862179 | 1.921474 |
| guitarset:03_SS3-84-Bb_solo | guitarset | test | 82 | 0.426829 | 0.463415 | 4.224359 | 4.160256 |
| guitarset:03_SS3-98-C_comp | guitarset | test | 408 | 1.0 | 0.933824 | 1.305814 | 1.226744 |
| guitarset:03_SS3-98-C_solo | guitarset | test | 111 | 0.441441 | 0.486486 | 3.959091 | 3.845455 |

## Techniques (prototype)

Heuristic labels, not scored: bend=212, hammer_on=303, pull_off=222, slide=466, vibrato=76

## Notes

- DadaGP was not staged (research access on request); the gate uses GuitarSet (primary) and EGSet12 (secondary).
- Tuning/capo variants are augmented by transposing the reference performance; they are not recorded tuning/capo performances.
- The DP receives reference pitches, so pitch accuracy is 1.0 for every assignable note; unassignable notes are counted as misses.
- The DP minimises playability cost subject to distinct strings for simultaneous notes. The per-note baseline can report a lower difficulty only by placing colliding notes on the same string; group validity shows that difference directly.
- Tab accuracy and group validity are the primary gains here; playability may trade off against physical validity.
- Technique labels are a heuristic prototype and are not scored.
- The audio string-activity auxiliary head is deferred; target construction is implemented in app.fretting.string_activity.
