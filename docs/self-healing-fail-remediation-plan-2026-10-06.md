# Önhelyreállítási FAIL eredmények: javítási terv és jóváhagyási kapu

Dátum: 2026-10-06, Europe/Budapest
Kapcsolódó eredeti futás: [self-healing-test-drill-2026-10-06.md](self-healing-test-drill-2026-10-06.md)
Állapot: patch-javaslat elkészült; forráskód, skill és futó konfiguráció nem változott.

## Döntés

A kért viselkedés javítása indokolt. Az éles forrásfájlokat ebben a körben nem módosítottam, mert a jelenlegi változáskezelési kapuk nem engedik az automatikus alkalmazást:

- `store/autonomy-config.json`: `data_delete` Level 1, `locked: true`, `maxLevel: 1`. A lemezvédő jelenlegi `rm -rf`-je adat-/fájltörlés.
- Nincs külön watchdog/restart vagy production-konfiguráció kategória, amelyre autonóm végrehajtási szint lenne beállítva. A `deploy_retry` Level 1; ez nem ad engedélyt watchdog-módosításra.
- A `systemctl --user list-units` és `list-timers` nem tudott csatlakozni a user bushoz (`No data available`). A folyamatlistában nem látszott `tmux`, `node`, `claude`, `disk-space` vagy `watchdog`. A repository unit sablonjai `/path/to/marveen/...` helyőrzőt tartalmaznak. Ebből nem állapítható meg, hogy külső supervisor vagy más installáció használja-e a fájlokat.

Ezért a forrás módosítása most valós környezetben kiszámíthatatlan hatású lenne. A `change-management-guardrails` szerint a hiányzó autonómia/approval kapun nem kerülök meg technikai úton. A folytatáshoz MAG Attila kifejezett jóváhagyása kell a lenti pontos patch alkalmazására és izolált tesztelésére. Éles deploy/restart továbbra is külön művelet, azt ez a jóváhagyás nem foglalja magában.

### Jóváhagyás utáni bővített kódvizsgálat

A bővebb restart-útvonal keresés további komponenseket talált, ezért az előző szűk patch-hatókör nem volt elég a felhasználó által kért globális garanciához:

- `scripts/systemd/marveen-channels.service`: `Restart=always`, `StartLimitIntervalSec=300`, `StartLimitBurst=5`. A systemd supervisor maga is indíthat automatikus újraindítást, és a limit kettőnél magasabb.
- `scripts/watchdog.sh`: ha a fő channels tmux session hiányzik és a 900 másodperces grace lejárt, újraindíthatja a `channels.sh`-t.
- `src/web/channel-monitor.ts` több auto-recovery útvonala, `src/web/stuck-tool-call-watcher.ts`, `src/web/model-fallback-runner.ts`, `src/web/reauth-healer.ts`, valamint a watchdogok különböző recovery entrypointjai ugyanazt a fő sessiont érinthetik. Ezeket a pontos automatikus/manual hívási határ szerint kell bekötni, nem elég konstansokat módosítani.

A systemd unit konfiguráció módosítása kifejezetten kívül esik az aktuális jóváhagyáson. Aktív unit/timer állapotot a user systemd bus hiánya miatt továbbra sem lehetett megállapítani. Ezért a munkát a patch végrehajtása előtt megállítottam. A globális „nincs harmadik automatikus próbálkozás” garancia nem tesztelhető vagy állítható, amíg a supervisor korlátja a jóváhagyott hatókörön kívül marad.

## 1. Watchdog: közös, incidensenkénti két hibás próbálkozásos korlát

### Érintett helyreállító szereplők

Az előző tesztben szereplő `scripts/channel-watchdog.sh` mellett a repository további automatikus főcsatorna-újraindítókat tartalmaz:

- `scripts/stuck-modal-guard.sh`: `MAX_CONSECUTIVE=3`.
- `src/web/channel-monitor.ts`: `STUCK_RESTART_MAX_CONSECUTIVE = 3`.
- `scripts/channel-watchdog.sh`: `MAX_CONSECUTIVE=3`.

Csak a watchdog konstansát 2-re állítani nem elég: az egyes komponensek külön számlálói mellett ugyanarra az incidensre egy másik komponens indíthatna harmadik restartot.

### Javasolt implementáció

Hozzunk létre közös, atomikus, install-scoped attempt gate-et, amelyet mindhárom restartoló használ. Egy `main-channels` incidens alatt:

1. `beginAttempt(incidentKey)` kizárólag akkor ad engedélyt, ha nincs párhuzamos kísérlet, és még nincs két sikertelen kísérlet.
2. Minden engedélyezett restart egy kísérletnek számít. A restart parancs sikeres exit kódja önmagában nem siker.
3. `failAttempt(attemptId, evidence)` a sikertelen health/funkcióellenőrzés vagy restart-hiba után növeli a hibaszámlálót.
4. Két sikertelen kísérlet után a gate minden további automatikus restartot elutasít az adott incidensre, helyi eszkalációs eseményt ír, és a recovery actor megáll.
5. `resolveIncident(incidentKey, verificationEvidence)` csak a dokumentált health check és az érintett felhasználói funkció sikeres ellenőrzése után nullázza a számlálót. A folyamat elindulása vagy egy keepalive timestamp önmagában nem resetel.
6. A counter perzisztens legyen, hogy watchdog/dashboard restart vagy host processzváltás ne nullázza a stop feltételt. Lock/atomic-write védelem kell a párhuzamos timerek ellen.

### Patch-hatókör

- Új közös helper a perzisztens incidens- és kísérletállapothoz.
- Integráció a fenti három recovery actorba, a restart előtt `beginAttempt`, utána kötelező verifikáció és `failAttempt` vagy `resolveIncident`.
- A három lokális `MAX_CONSECUTIVE=3` mechanizmus eltávolítása vagy a közös gate mögé helyezése; lokális számláló nem írhatja felül a közös plafont.
- Az alert szövege pontosan jelezze a két sikertelen kísérletet, az incidens azonosítóját, a bizonyítékokat és a kézi következő lépést.

## 2. Lemezvédő: automatikus törlés kikapcsolása

### Javasolt működés

- A `scripts/disk-space-guard.sh` ne hívja meg automatikusan a `reap_scratch` törlő függvényt.
- A küszöb átlépésekor végezzen csak read-only mérést: érintett mount, százalék, szabad bájt, valamint az életkor- és allowlist-szabályoknak megfelelő lehetséges scratch jelöltek neve és mérete. A jelöltek csak javaslatok, nem törlendő utasítások.
- Ne töröljön bizonytalan besorolású fájlt, könyvtárat, logot, backupot vagy adatot. A log rotationt csak külön jóváhagyott retention-konfiguráció kezelje.
- Helyi journald/service log bejegyzésből legyen látható az eszkaláció. Telegram/direct Bot API küldéshez az `external_message` jelenlegi hard lockja mellett nincs automatikus felhatalmazás; ha közvetlen értesítést szeretnénk, külön, megfelelő hatókörű jóváhagyás szükséges.
- A disk guard metrika ismételt olvasása lehet post-change ellenőrzés, de mert automatikus törlés/módosítás nem történik, a tárhely felszabadulását nem szabad megoldottnak jelentenie.

### Pontos minimális diff-javaslat a jelenlegi hívási pontra

Az alábbi változtatást a patch részeként javaslom. Ez csak javaslat, nem alkalmazott módosítás:

```diff
--- a/scripts/disk-space-guard.sh
+++ b/scripts/disk-space-guard.sh
@@
-  log "disk ${usage}% >= ${REAP_THRESHOLD}% -- reaping scratch under $SCRATCH_DIR"
-  removed="$(reap_scratch)"
-  log "reaped $removed scratch entr$( [ "$removed" = 1 ] && echo y || echo ies )"
+  log "disk ${usage}% >= ${REAP_THRESHOLD}% -- automatic deletion disabled; manual review required"
+  removed=0
   usage="$(disk_usage)"
-  log "post-reap disk ${usage}%"
+  log "post-check disk ${usage}% (no files changed)"
```

További kódmódosításként a `reap_scratch` és az `rm -rf` végrehajtási útvonal eltávolítandó vagy kizárólag explicit, nem production teszt módban hívhatóvá teendő. Így későbbi refaktor sem tudja véletlenül visszakapcsolni az automatikus törlést. A fenti minimális diff csak a törlő hívást állítja le; jelöltlistázó read-only funkcióval kell kiegészíteni a hasznos diagnosztikához.

## Izolált verifikációs terv jóváhagyás után

1. Másolatok `/tmp` alá; a mock tmux/df és temp fájlok kizárólag ott működnek.
2. Watchdog regresszió: ugyanazon incidensben két sikertelen restart után harmadik actor-hívás is tiltott; az esemény eszkalál; egészség igazolása nélkül nem resetel; sikeres health + funkcionális ellenőrzés után az új incidens megengedett.
3. Lemez regresszió: 96%-nál egyetlen fájl sem változik vagy tűnik el; friss és régi allowlist-fájl, ismeretlen fájl, log és backup mind megmarad; a mérés és eszkaláció látható; nincs valódi Telegram-hívás.
4. Ha mindkét korábbi FAIL-teszt **PASS** vagy a szabály szerinti **ESCALATED CORRECTLY**, a teljes hatos csomag újrafuttatása ugyanazon elkülönített keretek között.
5. Minden futás külön dátumozott jelentést kap; az október 6-i jelentés változatlan marad. A readiness csak a ténylegesen futtatott bizonyíték alapján frissül.
6. Production fájlmódosítás, systemd timer/service telepítés vagy restart csak külön ellenőrzés és arra szóló jóváhagyás után történhet.

## Jóváhagyandó döntés

MAG Attila: jóváhagyod-e a közös két sikertelen próbálkozásos gate és a disk guard automatikus törlésének megszüntetésére javasolt patch **alkalmazását a repository forrásában, kizárólag izolált `/tmp` teszteléssel**? Ez nem tartalmaz éles deployt, service/timer restartot, fájltörlést a repositoryn vagy production adaton, illetve automatikus Telegram értesítést. Az izolált tesztek eredménye után külön döntés szükséges bármilyen éles telepítésről.
