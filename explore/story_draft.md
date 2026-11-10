# Story draft: The Chip Tax

## 1. Headlines
1. **The Chip Tax: one route pays for one rusher**
2. Open, and Harmless
3. Every chip costs your tight end 3 yards

**Pick: #1.** Names the metric and the trade.

## 2. README summary (replace-ready)
We built the Chip Tax, a tracking measure of how much route depth a tight end or running back gives up when he chips an edge rusher, compared with his own non-chip routes (1,361 chips, 2021 Weeks 1-8). A chip costs him 3.1 yards of depth at 2 seconds (about 5 for a TE, 2 for a RB) and drops his target rate from 18% to 13%; when he does get the ball he is usually 8 yards open but only 1 yard past the line. In return, the rusher he chips gets pressure half as often (13% to 6%), and chip plays show fewer sacks (-1.9 pts) and more 15+ yard targets (+4.8 pts) than plays with the same protection and hold time. Offensive coordinators can use the per-player tax to decide who chips: at the extremes, Knox and Henry lose about 6 yards while Mike Davis and Singletary lose under 1. These are observational estimates from 8 weeks of PFF-labeled data, so the play-level gains are associations and only the extreme player rankings are reliable.

## 3. Story arc
| Beat | Message | Figure |
|-|-|-|
| Hook | One real chip: TE still ~1 yd deep while WRs run deep. | 0_chip_play_field.png |
| The price | Same player: +0.8 s release, -3.1 yds at 2 s, targeted 18% to 13%. | 2_the_receipt.png (left), 1_two_sides_of_a_chip.png (left) |
| What it buys | Rusher pressure 13% to 6%; sacks -1.9, deep targets +4.8, +1.3 yds/play. The "80% catch rate" is hollow: 8 open, 1 deep. | 1_two_sides (right), 2_the_receipt (right), 4_open_but_harmless.png |
| Who pays / so what | TE ~5, RB ~2; Knox/Henry/Fant most, Mike Davis/Swift/Singletary least. Chip with the spare route. | 3_chip_tax_by_player.png |

## 4. Captions
- **0:** One chip, one frozen route: the TE is barely past the line while the receivers stretch the field.
- **2:** The receipt: the chipper pays in depth and targets; the offense gets less pressure and more deep shots.
- **1:** A chip stalls the TE ~5 yds and the RB ~2; the chipped rusher stays ~1 yd farther from the QB (raw averages).
- **4:** Open because harmless: chippers who get the ball are 8 yds open but 1 yd downfield.
- **3:** Depth each chipper gives up at 2 s vs his own non-chip routes; trust the ends, not the middle.

## 5. So what
- **OC:** Chip with the back or the TE you can spare; a Knox chip costs a 6-yard route every rep.
- **DC:** A chipping TE is late and short; rally underneath and spend coverage elsewhere (untested).
- **Broadcaster:** "He chipped, so he's wide open in the flat, and that's exactly why they let him be."

## 6. README claims that overstate the evidence
- **Too long:** ~8 sentences; brief asks for 3-5.
- **"In return... QBs throw 15+ yd targets more often (+1.3 yds/play)"** reads causal. Observational, and conditioning on hold time (which chips lengthen, 3.5 vs 3.0 s) can bias it. Say "chip plays show".
- **"Mirage... because defenses stop covering him":** we never measured catch rate, have no YAC, and did not observe defenders' intent. Say "open because he is shallow".
- **"Kelce, Higbee and Cook pay ~3.7":** mid-pack, SE ~0.4, not separable from neighbors. Our team note says Kelce/Ertz/Kroft; the CSV says Kroft 3.1, Higbee 3.7, Cook 3.7, Ertz 3.8, Kelce 3.8. Name only extremes.
- **"Chipper can be left alone":** untested.
- **"Independently reproduce the 0.6 s":** raw median gap, not controlled.
