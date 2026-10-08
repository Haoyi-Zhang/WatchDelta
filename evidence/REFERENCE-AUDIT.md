# Reference integrity audit

Each bibliography entry is paired with a DOI landing record, archival proceedings page, or official versioned project source/report used during metadata checking. The paper source is additionally checked so every key is cited and no cited key is missing. This ledger supports traceability; it does not guarantee that every external URL will remain reachable indefinitely.

| # | Key | Source class | Persistent verification | Intended use |
|---:|---|---|---|---|
| 1 | `buildfuzz` | peer-reviewed | https://doi.org/10.1109/ICSE.2019.00125 | incremental-build correctness and clean-build comparison |
| 2 | `riker` | peer-reviewed | https://www.usenix.org/conference/atc22/presentation/curtsinger | correct incremental execution |
| 3 | `echecker` | peer-reviewed | https://doi.org/10.1145/3650212.3652105 | incremental-build dependency errors |
| 4 | `buildcarte` | peer-reviewed | https://doi.org/10.1145/3236774 | build-system design dimensions |
| 5 | `shake` | peer-reviewed | https://doi.org/10.1145/2364527.2364538 | dynamic dependencies and incremental builds |
| 6 | `pluto` | peer-reviewed | https://doi.org/10.1145/2814270.2814316 | soundness and optimality in incremental builds |
| 7 | `pie` | peer-reviewed | https://doi.org/10.22152/programming-journal.org/2018/2/9 | interactive development pipelines |
| 8 | `nix` | peer-reviewed | https://www.usenix.org/conference/lisa-04/nix-safe-and-policy-free-system-software-deployment | reproducible dependency-based deployment |
| 9 | `builderrors` | peer-reviewed | https://doi.org/10.1145/2568225.2568255 | practical build failures |
| 10 | `buildmaint` | peer-reviewed | https://doi.org/10.1145/1985793.1985813 | build maintenance in practice |
| 11 | `antevolution` | peer-reviewed | https://doi.org/10.1109/MSR.2010.5463341 | evolution of build specifications |
| 12 | `weyuker` | peer-reviewed | https://doi.org/10.1093/comjnl/25.4.465 | oracle problem |
| 13 | `oraclesurvey` | peer-reviewed | https://doi.org/10.1109/TSE.2014.2372785 | test-oracle taxonomy |
| 14 | `difftest` | peer-reviewed | https://vmssoftware.com/docs/dtj-v10-01-1998.pdf | differential oracle |
| 15 | `metareview` | peer-reviewed | https://doi.org/10.1145/3143561 | metamorphic testing review |
| 16 | `metasurvey` | peer-reviewed | https://doi.org/10.1109/TSE.2016.2532875 | metamorphic testing survey |
| 17 | `hamming1950` | peer-reviewed | https://doi.org/10.1002/j.1538-7305.1950.tb00463.x | distance-based error correction for diagnostic transcripts |
| 18 | `scipy2020` | peer-reviewed | https://doi.org/10.1038/s41592-019-0686-2 | MILP implementation and reproducible numerical software |
| 19 | `oraclemutation` | peer-reviewed | https://doi.org/10.1109/ICSE.2012.6227132 | mutation-based oracle selection |
| 20 | `metarel` | peer-reviewed | https://doi.org/10.1109/COMPSAC.2006.24 | metamorphic-relation quality |
| 21 | `metasimple` | peer-reviewed | https://doi.org/10.1109/AST.2015.18 | metamorphic testing overview |
| 22 | `flakyemp` | peer-reviewed | https://doi.org/10.1145/2635868.2635920 | causes of flaky behavior |
| 23 | `deflaker` | peer-reviewed | https://doi.org/10.1145/3180155.3180164 | flaky-test detection |
| 24 | `idflakies` | peer-reviewed | https://doi.org/10.1109/ICST.2019.00038 | repeatable flaky-test classification |
| 25 | `reiter1987` | peer-reviewed | https://doi.org/10.1016/0004-3702(87)90062-2 | foundational model-based diagnosis and candidate consistency |
| 26 | `dekleer1987` | peer-reviewed | https://doi.org/10.1016/0004-3702(87)90063-4 | multiple-fault diagnosis over candidate sets |
| 27 | `flakysurvey` | peer-reviewed | https://doi.org/10.1145/3476105 | flaky-test research synthesis |
| 28 | `flakypython` | peer-reviewed | https://doi.org/10.1109/ICST49551.2021.00026 | Python-specific flakiness and rerun needs |
| 29 | `rodler2023` | peer-reviewed | https://doi.org/10.1016/j.artint.2023.103988 | sequential selection of diagnostic tests |
| 30 | `configerrors` | peer-reviewed | https://doi.org/10.1145/2043556.2043572 | configuration failures |
| 31 | `configextract` | peer-reviewed | https://doi.org/10.1145/1985793.1985812 | configuration-option identification |
| 32 | `toomanyknobs` | peer-reviewed | https://doi.org/10.1145/2786805.2786852 | configuration complexity |
| 33 | `confaid` | peer-reviewed | https://www.usenix.org/conference/osdi10/automating-configuration-troubleshooting-dynamic-information-flow-analysis | configuration diagnosis |
| 34 | `confdiagnoser` | peer-reviewed | https://doi.org/10.1109/ICSE.2013.6606577 | configuration-error diagnosis |
| 35 | `measurementbias` | peer-reviewed | https://doi.org/10.1145/1508244.1508275 | measurement bias |
| 36 | `javabench` | peer-reviewed | https://doi.org/10.1145/1297027.1297033 | performance experiment methodology |
| 37 | `rigorousbench` | peer-reviewed | https://doi.org/10.1145/2464157.2464160 | replication and uncertainty in benchmarking |
| 38 | `stabilizer` | peer-reviewed | https://doi.org/10.1145/2451116.2451141 | layout and measurement randomization |
| 39 | `scientificbench` | peer-reviewed | https://doi.org/10.1145/2807591.2807644 | transparent performance reporting |
| 40 | `benchstats` | peer-reviewed | https://doi.org/10.1145/5666.5673 | summary statistics for benchmarks |
| 41 | `mk2061` | official issue | https://github.com/mkdocs/mkdocs/issues/2061 | MkDocs repeated-rebuild report and reproduction |
| 42 | `mk2519` | official issue | https://github.com/mkdocs/mkdocs/issues/2519 | MkDocs hidden/temporary-file report |
| 43 | `mk2385` | official merged change | https://github.com/mkdocs/mkdocs/pull/2385 | MkDocs batching mechanism and fix |
| 44 | `mk12rel` | official release notes | https://www.mkdocs.org/about/release-notes/#version-12-2021-06-04 | MkDocs release claim for batching |
| 45 | `mk122rel` | official release notes | https://www.mkdocs.org/about/release-notes/#version-122-2021-07-18 | watcher fallback history |
| 46 | `vite16248` | official issue | https://github.com/vitejs/vite/issues/16248 | Vite output-directory filter regression |
| 47 | `vitefix` | official merged change | https://github.com/vitejs/vite/pull/16453 | Vite regression fix |
| 48 | `vite524` | official versioned source | https://github.com/vitejs/vite/blob/v5.2.4/packages/vite/src/node/watch.ts | pre-fix Vite decision logic |
| 49 | `vite5210` | official versioned source | https://github.com/vitejs/vite/blob/v5.2.10/packages/vite/src/node/watch.ts | fixed Vite decision logic |
| 50 | `vite5210rel` | official release notes | https://github.com/vitejs/vite/blob/v5.2.10/packages/vite/CHANGELOG.md | release association for Vite fix |
| 51 | `ch1471` | official issue | https://github.com/paulmillr/chokidar/issues/1471 | discovery/registration race report |
| 52 | `bun36328` | official issue | https://github.com/oven-sh/bun/issues/36328 | atomic-save report |
| 53 | `tswatch` | official documentation | https://www.typescriptlang.org/docs/handbook/configuring-watch.html | TypeScript watcher options |
| 54 | `tssource` | official versioned source | https://github.com/microsoft/TypeScript/blob/v5.8.3/src/compiler/sys.ts | TypeScript watch implementation |
| 55 | `chokidar` | official versioned documentation | https://github.com/paulmillr/chokidar/blob/3.6.0/README.md | watch options and event normalization |
| 56 | `watchfiles` | official versioned source | https://github.com/samuelcolvin/watchfiles/blob/v1.2.0/watchfiles/main.py | watchfiles behavior and options |
| 57 | `wfrust` | official versioned source | https://github.com/samuelcolvin/watchfiles/blob/v1.2.0/src/lib.rs | event classification in watchfiles |
| 58 | `notifyconfig` | official versioned source | https://github.com/notify-rs/notify/blob/notify-8.0.0/notify/src/config.rs | poll interval and content comparison options |
| 59 | `notifypoll` | official versioned source | https://github.com/notify-rs/notify/blob/notify-8.0.0/notify/src/poll.rs | polling state predicate |
| 60 | `markdown` | official package metadata | https://pypi.org/project/markdown-it-py/4.2.0/ | documentation renderer version |
| 61 | `uvicorn` | official versioned source | https://github.com/Kludex/uvicorn/blob/0.48.0/uvicorn/supervisors/watchfilesreload.py | Uvicorn reload selection |
| 62 | `hypercorn` | official versioned source | https://github.com/pgjones/hypercorn/tree/0.18.0/src/hypercorn | Hypercorn reload implementation |
| 63 | `pep552` | official language specification | https://peps.python.org/pep-0552/ | timestamp- and hash-based bytecode invalidation |
| 64 | `nodefswatch` | official documentation | https://nodejs.org/docs/latest-v22.x/api/fs.html#fswatchfilename-options-listener | platform caveats for filesystem watching |
| 65 | `pep3147` | official language specification | https://peps.python.org/pep-3147/ | bytecode cache layout and reuse |
| 66 | `inotify` | official manual | https://man7.org/linux/man-pages/man7/inotify.7.html | Linux filesystem event semantics |
| 67 | `tangbug` | peer-reviewed | https://doi.org/10.1007/s10664-024-10489-x | methodological connection from public reports to validated cases |
