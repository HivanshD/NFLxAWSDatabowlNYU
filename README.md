# The Chip Tax: one route pays for one rusher

We built the **Chip Tax**, a new tracking metric for how much route depth a tight end or running back gives up when he chips an edge rusher, compared with his own non-chip routes (1,361 chips, 2021 Weeks 1–8). A chip costs him **3.1 yards of depth at 2 seconds** (about 5 for a TE, 2 for a RB), gets him into his route **0.8 s later**, and drops his target rate from **18% to 13%**. When he does get the ball he is typically 8 yards open but only 1 yard past the line. In return, the rusher he chips gets pressure **half as often (13% → 6%)**, and chip plays show **fewer sacks (−1.9 pts) and more 15+ yard targets (+4.8 pts, +1.3 yds/play)** than plays with the same protection and hold time. Offensive coordinators can use the per-player tax to decide *who* chips: Knox and Henry lose about 5.5 yards per chip, while Kelce, Higbee and Cook lose about 4, and among backs Mike Davis loses under 1 while Hines loses about 3. These are observational estimates from 8 weeks of PFF-labeled data, so the play-level gains are associations and only the clearly flagged player differences are reliable.

**Format:** Metric/Score (the Chip Tax), with a player comparison chart. **Audience:** OCs and pass-game coordinators (who chips, when it's worth it), scouts (what a TE's chip snaps cost his receiving value), broadcasters (why the chipper is wide open in the flat).

| | |
|---|---|
| ![Anatomy of a chip](outputs/figs/0_chip_play_field.png) | **One real chip.** Kelce chips the edge rusher for 0.8 s, so the rusher is still 5.8 yds from Mahomes at the throw. But Kelce is only 0.4 yds past the line while Hill and Robinson are about 15 yds downfield, and Mahomes hits Hill deep for 19. |
| ![The receipt](outputs/figs/2_the_receipt.png) | **The receipt.** What the chipper pays and what the offense gets. Every line is a controlled comparison with a 95% CI. |
| ![What a chip moves](outputs/figs/2b_what_a_chip_moves.png) | **Before and after.** Target rate, rusher pressure, sacks and deep targets, with and without a chip. |
| ![Two sides of a chip](outputs/figs/1_two_sides_of_a_chip.png) | **The two sides over time** (raw averages). The chipper's route stalls while the chipped rusher stays about 1 yd farther from the QB. |
| ![Open because shallow](outputs/figs/4_open_but_harmless.png) | **Open because he's shallow.** Chippers who are targeted are 8 yds from the nearest defender but 1 yd downfield. |
| ![Chip Tax by player](outputs/figs/3_chip_tax_by_player.png) | **The Chip Tax by player** (shrunk toward position average, 80% intervals). Trust the flagged ends, not the middle. |

## Method
- **Data:** NGS tracking (10 Hz) plus PFF scouting from the NYU Big Data Bowl set. A chip = a route runner with `pff_blockType == "CH"`; the chipped rusher is `pff_nflIdBlockedPlayer`. Coordinates are normalized so the offense always moves left to right. The play window runs from `ball_snap` to the first of {pass_forward, autoevent_passforward, qb_sack, qb_strip_sack, run}.
- **Cost (`src/chip_analysis.py`):** OLS with **player fixed effects** (chip routes vs the same player's non-chip routes). Controls: down, distance, play action, dropback type, coverage, alignment and hold time. SEs are clustered by game. Outcomes come from tracking: route depth at 1.5/2.0/2.5 s and at the throw, time to cross the line, distance to the nearest coverage defender at the throw, and targeted (parsed from `playDescription`).
- **Benefit:** OLS with **rusher fixed effects**, plus alignment, pre-snap distance to the QB, hold time and protection size. Pressure = PFF hurry/hit/sack.
- **Play level:** chip-eligible plays (a TE/RB running a route) with offense and defense fixed effects, matched exactly on protection structure (# blockers × # route runners), plus hold time.
- **Chip Tax per player:** mean depth at 2.0 s on chip routes minus the same player's non-chip routes (min. 12 chips, 30 non-chip routes), with empirical-Bayes shrinkage toward the position average. Players differ beyond noise (heterogeneity p < 0.001 for TEs and RBs), and for TEs it isn't explained by normal route depth (r = −0.24). Flags use an 80% interval, so about 4 of 37 could be flagged by chance.

## Robustness, placebo checks, and what we dropped
| Check | Result |
|---|---|
| Placebo: do chipped rushers already line up differently? | Slightly wider (+0.25 yds from the QB pre-snap). Controlled for; the pressure effect holds (−6.8 pts, se 0.9) |
| "Pressure just moves to the other rushers"? | +4.3 pts raw, only +1.3 (se 0.7) after accounting for longer chip plays. **Not claimed** |
| "Chip plays are just max-protect shot plays"? | 82% of chip plays still send 5 receivers out. Matched on exact protection structure, the gains remain |
| "Only chip elite rushers"? | Teams already do (6.5% vs 2.1% chip rate), and the evidence is thin. **Not claimed** |
| 19 other idea candidates | Screened for signal, split-half stability and face validity in `explore/` before choosing this one |

## Assumptions and limitations
- **Observational.** Coaches choose when to chip. Conditioning on hold time compares like with like, but chips themselves lengthen hold time (3.5 vs 3.0 s), so the play-level gains are associations, not proof that the chip caused them.
- **Labels and openness.** Chip and pressure labels are PFF's human charting. "Open" = distance to the nearest coverage defender only. We don't observe *why* defenders leave the chipper, only that he is shallow and uncovered.
- **Small samples.** 8 weeks of data; 12–42 chips per player.
- **No YAC.** Tracking ends at the throw, so yards after the catch can't be measured.
- **Prior work.** Next Gen Stats has reported that chipped edge rushers take ~0.6 s longer to pressure and that chip routes catch ~80% of targets. Our raw medians agree (3.4 vs 2.8 s to reach the QB). What's new here is the chipper's route cost, controlled, and the per-player Chip Tax.

## Run it
```bash
pip install -r requirements.txt
# data: copy the data/ folder from https://github.com/ThompsonJamesBliss/nfl-big-data-bowl-regional-event-data into ./data
./run_all.sh   # ~2 min: routes + targets -> chip features -> controlled effects -> figures
```
Outputs: `outputs/chip_results.json` (every effect with SE and n), `outputs/chip_tax_by_player.csv`, `outputs/figs/`.
Repo map: `src/` = submission pipeline · `explore/` = idea screening, robustness scripts and story draft · `archive/` = an earlier idea (Beat the Rush) dropped after failing stability tests.
