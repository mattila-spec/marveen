# Önhelyreállítási tesztfuttatás: előteszt jelentés

Futtatás ideje: 2026-10-06, Europe/Budapest
Állapot: **NOT READY**

## Vezetői összefoglaló

A hat teljes önhelyreállítási forgatókönyv nem futott le, mert nem volt azonosítható külön teszt/staging szolgáltatás, adatbázis, deploy-cél és eldobható restore/rollback pont. A megadott korlát szerint production hibainjektálást nem végeztem. Mind a hat esetnél helyesen leálltam az előfeltétel-ellenőrzésnél; az esetek státusza **ESCALATED CORRECTLY (csak előteszt)**. Ez a minősítés a biztonságos leállást igazolja, magát a helyreállítási működést nem.

Izolált kódtesztek részleges bizonyítékot adnak: a lemezvédő teszt 22/22, a kiválasztott restart-, health-monitor- és update-előfeltétel tesztek 83/83 esetben zöldek. Ezek nem igazolják a hat teljes önhelyreállítási folyamatot. Az összesített readiness ezért **NOT READY**.

## Környezeti bizonyíték és végrehajtási korlát

- A `127.0.0.1:3420` dashboard elérhető és hitelesítést kér az API-kon. Ez a futó kezelőfelület, nem azonosított staging hibacél.
- A tesztfuttatási környezetben nem volt `docker`, `podman` vagy `nerdctl`; a felhasználói/mount/PID namespace létrehozási próba `unshare` hibával zárult.
- Készítettem egy tiszta, live-marker nélküli checkoutot `/home/marveen/marveen/.self-healing-staging` néven a munkakönyvtárban. Ebben nincs dashboard-token, runtime adatbázis vagy `.env`. Ez elkülönített **kódteszt-checkout**, de nincs benne indítható, izolált Marveen-szolgáltatás, teszt DB, helyreállítási fixture vagy saját backup/rollback target.
- A meglévő `self-healing-orchestrator` egy utasításokat összefogó skill, nem futtatható általános javító szolgáltatás/API. Több külön komponensnek van kódja és egységtesztje, de az itt kért hat útvonal nincs egy közös izolált end-to-end tesztharnessbe kötve.
- A workspace élő dashboard/API állapotához nem küldtem hibát, nem állítottam le folyamatot, nem terheltem meg az aktív fájlrendszert, nem szakítottam meg DB-kapcsolatot, nem deployoltam, és nem módosítottam vagy állítottam vissza backupot. A tesztek kizárólag saját, korlátozott temp-fixtúrákat írtak, majd töröltek.

## Lefuttatott részleges, izolált kódtesztek

1. `scripts/__tests__/disk-space-guard.test.sh`: **22/22 PASS**. `DISK_GUARD_USAGE_OVERRIDE`-ot, dedikált scratch/state mappákat és alert dry-run módot használ. Azt igazolja, hogy a whitelistelt, koros `health_*` scratch állományok korlátozottan takaríthatók, a frissek és nem engedélyezett fájlok megmaradnak, a magas küszöb riaszt, a cooldown működik, a hibás mérés no-op. Nem töltött meg valódi fájlrendszert.
2. Tiszta checkoutban öt Vitest fájl: **83/83 PASS**:
   - `auto-restart-main-mechanism.test.ts`
   - `auto-restart.test.ts`
   - `channel-health-monitor.test.ts`
   - `update-preflight.test.ts`
   - `update-unit-maintenance-order.test.ts`

   Ezek függvény-, mock- és temp-fixture szintű tesztek. Nem állítanak le vagy állítanak helyre futó Marveen-szolgáltatást, és nem tesztelnek DB-kiesést, deploy utáni runtime rollbacket vagy restore-t.

3. A `update-unit-maintenance-order.test.ts` futása közben a temp probe kimenetében megjelent két `command not found`: `install_keepalive_probe_timer` és `park_morning_timer`. A teljes Vitest parancs ettől még zöld lett, de a tesztfixture nem definiálja ezeket a helper-függvényeket; ezt a tesztminőség értékelésénél figyelembe kell venni.

4. A Vitest első, éles checkoutból indított próbája a beépített `assert-not-live-install` miatt nem alkalmas futtatási helynek, és a workspace-ben lévő sok régi worktree-másolatot is gyűjtötte. Megállítottam, majd a teszteket tiszta izolált checkoutból futtattam le. Éles szolgáltatást ez a próbálkozás sem módosított.

## A hat forgatókönyv előteszt-értékelése

A státusz mindegyik sornál a kötelező izolációs kapu helyes alkalmazását értékeli. A tünetet szándékosan nem injektáltam, ezért a hiba-felismerés és gyökérok tényleges viselkedése nem kapott dinamikus validációt.

Értékelési rövidítések: **N/A** = a hiba nem lett injektálva; **PASS-előteszt** = az előfeltétel/kockázat helyes kezelése; **MEM-kampány** = a közös előteszt-eredmény a cold memóriában rögzítve, rekordazonosító **142**. Esetenkénti incidensrekord nem készült, mert egyetlen valós vagy szimulált incidens sem történt.

### 1. Szolgáltatás leáll

- **Eredmény:** ESCALATED CORRECTLY (előteszt).
- **Hibafelismerés:** N/A, szolgáltatásleállást nem injektáltam.
- **Kiváltó ok:** N/A, nincs tüneti bizonyíték.
- **Kockázat:** PASS-előteszt, nincs azonosított izolált szolgáltatáscél.
- **Javítás:** PASS-előteszt, nem indítottam restartot.
- **Módosítás utáni ellenőrzés:** N/A, nem történt módosítás.
- **Rollback:** nem áll rendelkezésre igazolt, tesztpéldányhoz kötött rollback.
- **Eszkaláció:** PASS-előteszt, a productionhoz közeli élő dashboardot nem érintettem.
- **Két kísérlet utáni STOP:** N/A, nulla javítási kísérlet.
- **Incident Memory & Learning:** MEM-kampány; valós incidens nem történt.
- **Megoldottnak minősítés:** PASS, nem állítottam helyreállítást.

### 2. Megtelik a lemez

- **Eredmény:** ESCALATED CORRECTLY (előteszt).
- **Hibafelismerés:** N/A, tényleges lemezterhelést nem okoztam. A disk-guard komponens 22/22 tesztje zöld.
- **Kiváltó ok:** N/A, csak szimulált használati százalékot tesztelt a komponenssuite.
- **Kockázat:** PASS-előteszt, valós volume-terhelés és automatikus törlés helyett tesztfixture maradt.
- **Javítás:** PASS-előteszt, nem töröltem valós adatot vagy backupot.
- **Módosítás utáni ellenőrzés:** N/A a teljes forgatókönyvre; a komponenssuite a scratch fixture-eket ellenőrizte.
- **Rollback:** a teljes szolgáltatási szintű helyreállítás nincs igazolva.
- **Eszkaláció:** PASS-előteszt, nincs izolált, méretkorlátos teszt volume.
- **Két kísérlet utáni STOP:** N/A, nulla javítási kísérlet.
- **Incident Memory & Learning:** MEM-kampány; valós incidens nem történt.
- **Megoldottnak minősítés:** PASS, a teljes disk-full helyzetet nem jelöltem megoldottnak.

### 3. Hibás deploy

- **Eredmény:** ESCALATED CORRECTLY (előteszt).
- **Hibafelismerés:** N/A, hibás release-t nem telepítettem.
- **Kiváltó ok:** N/A, nincs deploy-hiba log vagy futási adat.
- **Kockázat:** PASS-előteszt, nem volt dedikált staging deploy-cél.
- **Javítás:** PASS-előteszt, nem deployoltam.
- **Módosítás utáni ellenőrzés:** N/A, nem volt változás.
- **Rollback:** update-preflight tesztek futottak, de deploy utáni rollback nem.
- **Eszkaláció:** PASS-előteszt, hiányzik az izolált release és az ismert-jó visszaállítási pont.
- **Két kísérlet utáni STOP:** N/A, nulla javítási kísérlet.
- **Incident Memory & Learning:** MEM-kampány; valós incidens nem történt.
- **Megoldottnak minősítés:** PASS, deploy állapotot nem minősítettem helyreállítottnak.

### 4. Adatbázis-kapcsolat megszakad

- **Eredmény:** ESCALATED CORRECTLY (előteszt).
- **Hibafelismerés:** N/A, DB-kapcsolatot nem szakítottam meg.
- **Kiváltó ok:** N/A, nincs staging DB-hiba vagy kapcsolatlog.
- **Kockázat:** PASS-előteszt, az egyetlen elérhető dashboard DB-jét nem érintettem.
- **Javítás:** PASS-előteszt, nem futtattam DB-módosítást vagy reconnect műveletet.
- **Módosítás utáni ellenőrzés:** N/A, nem volt változás.
- **Rollback:** DB-helyreállítási eljárás staging célra nem igazolt.
- **Eszkaláció:** PASS-előteszt, dedikált tesztadatbázis hiányzik.
- **Két kísérlet utáni STOP:** N/A, nulla javítási kísérlet.
- **Incident Memory & Learning:** MEM-kampány; valós incidens nem történt.
- **Megoldottnak minősítés:** PASS, DB-helyreállítást nem állítottam.

### 5. Rollback nem érhető el

- **Eredmény:** ESCALATED CORRECTLY (előteszt).
- **Hibafelismerés:** N/A, nem futott hibás deploy egy tesztpéldányon.
- **Kiváltó ok:** N/A, nem volt rollbacket igénylő futási hiba.
- **Kockázat:** PASS-előteszt, az ismert-jó staging release hiányzik.
- **Javítás:** PASS-előteszt, rollback nélküli javítási próbát nem indítottam.
- **Módosítás utáni ellenőrzés:** N/A, nem volt módosítás.
- **Rollback:** a hiányzó rollback biztonságos felismerése kód/skill-szinten nem lett dinamikusan tesztelve.
- **Eszkaláció:** PASS-előteszt, rollback út igazolása nélkül leálltam.
- **Két kísérlet utáni STOP:** N/A, nulla javítási kísérlet.
- **Incident Memory & Learning:** MEM-kampány; valós incidens nem történt.
- **Megoldottnak minősítés:** PASS, helyreállítást nem jelentettem.

### 6. Backup létezik, de a restore nem működik

- **Eredmény:** ESCALATED CORRECTLY (előteszt).
- **Hibafelismerés:** N/A, hibás restore-t nem próbáltam.
- **Kiváltó ok:** N/A, nincs restore log vagy izolált restore cél.
- **Kockázat:** PASS-előteszt, valós backupot nem módosítottam és nem írtam felül.
- **Javítás:** PASS-előteszt, nem futtattam restore-t.
- **Módosítás utáni ellenőrzés:** N/A, nem történt visszaállítás.
- **Rollback:** disposable restore target és bizonyított visszaállítási út hiányzik.
- **Eszkaláció:** PASS-előteszt, backup/restore tesztkörnyezet nélkül leálltam.
- **Két kísérlet utáni STOP:** N/A, nulla javítási kísérlet.
- **Incident Memory & Learning:** MEM-kampány; valós incidens nem történt.
- **Megoldottnak minősítés:** PASS, a backupot nem tekintettem igazoltan visszaállíthatónak.

## Javasolt pontosítások, javítás előtt

Ezek javaslatok, még nem módosítottam skillt vagy futó rendszert.

1. **`self-healing-orchestrator` skill:** kerüljön bele egy tesztmód-kapu, amely megköveteli a tesztkörnyezet explicit azonosítóját, tesztadat/fixture használatát és a valós production API-k elérhetetlenségének bizonyítékát; a skill a tesztkörnyezet igazolása nélkül ne indíthasson fault injectiont.
2. **`self-healing-audit-readiness` skill:** a tesztkészenléti állapotot külön értékelje, és kérjen bizonyított izolált service/DB/backup/rollback targetet. A futó dashboard elérhetősége ne számítson staging-készenlét bizonyítékának.
3. **`incident-memory-learning` skill:** a szimulált gyakorlatot `test drill` jelöléssel válassza el a valós incidensektől; ha egy teszt nem indult el, kampány-előteszt rekord készüljön, ne kitalált incidensbejegyzés.
4. **Futtatható harness hiánya:** az instrukciós skilleken túl szükséges egy izolált tesztfuttató kontrollált service-, DB-, deploy-, disk- és backup fixture-ekkel, log/állapotgyűjtéssel, önálló rollbackkel és takarítással. E nélkül a hat eset end-to-end futtatása nem bizonyítható.
5. **Tesztfixture hiányosság:** a `update-unit-maintenance-order.test.ts` ideiglenes shellprobe-jába be kellene emelni vagy mockolni a `install_keepalive_probe_timer` és `park_morning_timer` segédfüggvényeket, majd ellenőrizni a stderr-t is; jelenleg két figyelmen kívül maradó `command not found` jelenik meg zöld tesztfutás mellett.

Ezek jóváhagyásra váró módosítási javaslatok, nem alkalmazott javítások.

## Következő szükséges lépés

A teljes hat teszt újrafuttatásához MAG Attilának egy dedikált izolált/staging futtatási célt kell megadnia, vagy külön jóvá kell hagynia egy helyi, throwaway tesztharness kiépítését. A következő futás előtt szükséges: külön service és DB, tesztadatok, backup/restore próbacél, ismert-jó release, mérhető health/funkció-ellenőrzés és automatikus takarítás.
