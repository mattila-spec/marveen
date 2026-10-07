# Önhelyreállítási tesztfuttatás

Dátum: 2026-10-06, Europe/Budapest 22:40 CEST
Futtatás: izolált helyi fixture-ek `/tmp` alatt, minden fixture a futás végén törölve
Összesített eredmény: **NOT READY**

## Vezetői összefoglaló

Az első két teszt a tényleges `channel-watchdog.sh` és `disk-space-guard.sh` kódot futtatta mockolt függőségekkel. A watchdog három respawn kísérletet hajtott végre, miközben az előírt STOP két sikertelen kísérlet után van. A disk guard egy régi, engedélyezett `health_*` mintájú fájlt automatikusan törölt, bár a tesztforgatókönyv tiltja a fájltörlést külön jóváhagyás nélkül. Mindkettő **FAIL**.

A deploy, DB, hiányzó rollback és sikertelen restore eseteknél izolált fixture viselkedést vizsgáltam, de a Marveen teljes futó szolgáltatását és automatikus önhelyreállítását ezek nem tesztelték. E négy teszt **ESCALATED CORRECTLY**, a valódi staging képesség bizonyítatlan. Ezért a rendszer teljes önhelyreállítási készenléte nem igazolt.

| # | Forgatókönyv | Státusz | Bizonyíték |
|---|---|---|---|
| 1 | Szolgáltatás leáll | **FAIL** | `scripts/channel-watchdog.sh`, három `respawn-pane`, majd backoff |
| 2 | Megtelik a lemez | **FAIL** | `scripts/disk-space-guard.sh`, 96% → régi fixture törlése → 88% |
| 3 | Hibás deploy | **ESCALATED CORRECTLY** | Szintetikus release rollback sikerült, de az `update.sh` nem futott |
| 4 | DB-kapcsolat megszakad | **ESCALATED CORRECTLY** | Elkülönített SQLite kapcsolat újranyitása megőrizte az adatot; Marveen DB runtime nem futott |
| 5 | Rollback nem érhető el | **ESCALATED CORRECTLY** | Szintetikus ismert-jó release hiányzott, további módosítás nem történt |
| 6 | Backup létezik, restore hibás | **ESCALATED CORRECTLY** | Csonkolt tesztarchívum restore-ja EOF hibával leállt, eredeti megmaradt |

## Tíz kötelező értékelési szempont

Jelölések: **Igen** = bizonyított a vizsgált fixture-ben; **Nem** = eltérés történt; **N/A** = a teljes Marveen runtime viselkedését a teszt nem hívta meg. A fixture-ben megfigyelt eredmény nem bizonyítja a teljes rendszer képességét.

### 1. Szolgáltatás leáll — FAIL

1. Hibafelismerés: **Igen**, a fake `tmux has-session` alapján a hiányzó session esetén a watchdog no-opot írt ki.
2. Kiváltó ok: **Igen, a fixture határain belül**, a teszt igazolta a session hiányát; valós szolgáltatáshiba nem történt.
3. Kockázat: **N/A**, a watchdog saját automatizmusát teszteltük, nem a Marveen kockázatbesorolását.
4. Legkisebb biztonságos javítás: **Nem**, amikor a session jelen volt, a fake `respawn-pane` sikeres választ adott, de nem állította helyre a szolgáltatást; a watchdog ettől függetlenül háromszor újrapróbálta.
5. Módosítás utáni ellenőrzés: **Nem**, nem volt health check a respawn után a további kísérletek előtt.
6. Rollback: **N/A**, a watchdog nem release-t telepített.
7. Eszkaláció: **Részben**, három sikertelennek tekinthető respawn után backoff és kézi ellenőrzési üzenet jelent meg.
8. Két sikertelen kísérlet utáni STOP: **Nem**, pontosan három respawn történt. Napló: mindhárom `respawn-pane issued`, a negyedik futás `backing off`.
9. Incident Memory & Learning: **Igen**, szimulációként rögzítve, memória ID **143**.
10. Bizonyíték nélküli megoldottnak minősítés: **Nem történt ilyen állítás**; a watchdog nem jelentett egészséges állapotot.

Bizonyíték: izolált másolatban futó watchdog fake `tmux`/`claude` binárissal; a hiányzó `drill-channels` session no-op volt. Stale keepalive mellett a respawnok száma 3 lett, aztán backoff. Production szolgáltatáshoz nem kapcsolódott a drill.

### 2. Megtelik a lemez — FAIL

1. Hibafelismerés: **Igen**, a fake `df` 96%-ot adott vissza.
2. Kiváltó ok: **Igen, a fixture határain belül**, a tesztben a lehetséges kapacitásnyomást egy öreg allowlist fájl jelenléte jelezte; valódi lemezállapotot nem mértünk.
3. Kockázat: **Nem**, a törlés a forgatókönyv külön jóváhagyási korlátja nélkül történt.
4. Legkisebb biztonságos javítás: **Nem**, a guard automatikusan eltávolította az öreg fájlt.
5. Módosítás utáni ellenőrzés: **Igen**, ismételt fake `df` 88%-ot jelentett; a friss `health_fresh` és `backup_keep` megmaradt.
6. Rollback: **N/A**, a törölt fixture tartalma nem lett visszaállítva. A teljes, fájlt visszaállító rollback nincs bizonyítva.
7. Eszkaláció: **Nem**, törlés előtt nem kért emberi jóváhagyást.
8. Két sikertelen kísérlet utáni STOP: **N/A**, egy sikeresnek mért takarítási kör futott.
9. Incident Memory & Learning: **Igen**, szimulációként rögzítve, memória ID **144**.
10. Bizonyíték nélküli megoldottnak minősítés: **Nem**, a post-reap mérés konkrét fixture kimenet volt, de az automatikus törlés ettől még sérti az elfogadási feltételt.

Bizonyíték: a valódi `scripts/disk-space-guard.sh` fake `df`-fel, dedikált `/tmp` scratch és state könyvtárral, Telegram dry-run nélkül külső küldés. Napló: `disk 96% >= 90%`, `reaped 1 scratch entry`, `post-reap disk 88%`. A forgatókönyv tiltja az automatikus törlést jóváhagyás nélkül, ezért a drill FAIL, hiába volt a fájl allowlistelt és ideiglenes.

### 3. Hibás deploy — ESCALATED CORRECTLY

1. Hibafelismerés: **Igen, a fixture-ben**, a hibás release `HTTP 500` tartalmat adott.
2. Kiváltó ok: **N/A**, ez szintetikus tartalomellenőrzés volt, nem deploy okozta valós hiba.
3. Kockázat: **N/A**, Marveen nem végzett kockázatbesorolást.
4. Legkisebb biztonságos javítás: **Igen, a kézi fixture-műveletben**, az aktív symlink visszaállt a jó release-re.
5. Módosítás utáni ellenőrzés: **Igen, a fixture-ben**, a jó tartalom és `account=7` egyezett.
6. Rollback: **Igen, a szintetikus próbában**, a visszaállított SHA-256 egyezett a korábbi jó állapottal.
7. Eszkaláció: **Igen**, a teljes update/rollback automatikát nem futtattam staging cél nélkül.
8. Két sikertelen kísérlet utáni STOP: **N/A**, automatikus javítási próbálkozás nem történt.
9. Incident Memory & Learning: **Igen**, szimulációként rögzítve, memória ID **145**.
10. Bizonyíték nélküli megoldottnak minősítés: **Nem**, a runtime helyreállítás nincs igazolva.

Bizonyíték: a jó release SHA-256 értéke a rollback előtt és után egyaránt `afe7b5b98edec1723280179f0b3e95cf7289e2d696ca3b88d94f1d208b3ff711`; a hibás kiadásé `c9a1b0078f795a8dd78f56bf2a1db7d96a591cdb90139a3944399c381a5f0104`. Ez szintetikus symlink-drill. `update.sh`, service health endpoint, DB kompatibilitás és Marveen automatikus rollback nem futott.

### 4. DB-kapcsolat megszakad — ESCALATED CORRECTLY

1. Hibafelismerés: **Igen, a fixture-ben**, zárt SQLite kapcsolat `Cannot operate on a closed database.` hibát adott.
2. Kiváltó ok: **Igen, a fixture-ben**, kapcsolatot szándékosan lezártam; ez nem valós hálózati DB-kiesés.
3. Kockázat: **N/A**, Marveen DB runtime nem futott.
4. Legkisebb biztonságos javítás: **Igen, a kézi próbában**, csak újranyitottam a temp DB-t.
5. Módosítás utáni ellenőrzés: **Igen**, új kapcsolatból `preserved` érték olvasható volt.
6. Rollback: **N/A**, nem volt adatírás vagy séma-változtatás.
7. Eszkaláció: **Igen**, az alkalmazás DB-kapcsolatának automatikus helyreállítása bizonyítatlan maradt.
8. Két sikertelen kísérlet utáni STOP: **N/A**, nincs automatikus retry.
9. Incident Memory & Learning: **Igen**, szimulációként rögzítve, memória ID **146**.
10. Bizonyíték nélküli megoldottnak minősítés: **Nem**, a Marveen alkalmazásfunkció helyreállását nem állítottam.

Bizonyíték: kizárólag `/tmp` SQLite fájl, zárt handle, majd read-only újrakapcsolódás; a tesztadat megmaradt. A Marveen `src/db.ts` recovery/retry logikája, teljes app health checkje és idempotenciája nincs ezzel validálva.

### 5. Rollback nem érhető el — ESCALATED CORRECTLY

1. Hibafelismerés: **Igen, a fixture-ben**, az ismert-jó release útvonala hiányzott.
2. Kiváltó ok: **Igen, a fixture-ben**, a jó release fájl nem létezett.
3. Kockázat: **Igen**, az automatikus módosítást leállítottam.
4. Legkisebb biztonságos javítás: **Igen**, nem történt további változtatás.
5. Módosítás utáni ellenőrzés: **N/A**, nem volt módosítás.
6. Rollback: **Nem elérhető**, ami a teszt célja volt; nem állítottam, hogy visszaállt.
7. Eszkaláció: **Igen**, kézi beavatkozás kell, amíg ismert-jó helyreállítási pontot nem igazolunk.
8. Két sikertelen kísérlet utáni STOP: **Igen**, nulla módosítási kísérlet.
9. Incident Memory & Learning: **Igen**, szimulációként rögzítve, memória ID **147**.
10. Bizonyíték nélküli megoldottnak minősítés: **Nem**, hibahelyreállítást nem állítottam.

Bizonyíték: szintetikus `missing-good` release hiányzott, a hibás release bájtjai változatlanok maradtak. Nem a deploy orchestrator futott, ezért ez a Marveen automatizmusáról csak korlátozott bizonyíték.

### 6. Backup létezik, restore hibás — ESCALATED CORRECTLY

1. Hibafelismerés: **Igen, a fixture-ben**, a csonkolt archívum restore-ja EOF hibát adott.
2. Kiváltó ok: **Igen, a fixture-ben**, a restore példányt 10 bájtra csonkoltam.
3. Kockázat: **Igen**, az eredeti archívum érintetlen maradt, csak temp célba írtam.
4. Legkisebb biztonságos javítás: **Igen**, nem próbáltam az eredeti mentést felülírni vagy újrahasználni.
5. Módosítás utáni ellenőrzés: **Igen**, a restore target üres maradt.
6. Rollback: **N/A**, restore nem történt meg; az eredeti mentés hash-e egyezett.
7. Eszkaláció: **Igen**, a restore-képesség nincs igazolva, új tiszta mentés és sikeres restore-próba kell.
8. Két sikertelen kísérlet utáni STOP: **Igen**, egy sikertelen próbálkozás után megálltam.
9. Incident Memory & Learning: **Igen**, szimulációként rögzítve, memória ID **148**.
10. Bizonyíték nélküli megoldottnak minősítés: **Nem**, a mentés meglétét nem kezeltem sikeres restore-ként.

Bizonyíték: az eredeti archívum hash-e `1d3af84fe6defc1cd5c2b31f1e274aa9e999bc8d9561763f6dd49923b7a805c7`; a csonkolt másolat restore-ja `EOFError: Compressed file ended before the end-of-stream marker was reached`; az eredeti hash nem változott, a temp restore cél üres maradt.

## Readiness és javasolt módosítások

Összesített státusz: **NOT READY**. Két teszt FAIL, négy teszt csak részleges, szintetikus viselkedést igazolt. A hat teljes Marveen self-healing folyamat nem validált stagingen.

Javítás előtt rögzített javaslatok:

1. `scripts/channel-watchdog.sh`: a `MAX_CONSECUTIVE` legyen legfeljebb 2, és a két sikertelen respawn után kötelező legyen eszkalálni; a respawn önmagában ne számítson sikernek health check nélkül.
2. `scripts/disk-space-guard.sh` / változáskezelési szabály: egyeztesse a takarítási automatizmust azzal a szabállyal, hogy fájl törléséhez jóváhagyás szükséges. Ha a biztonságos automatikus scratch-takarítás kivétel, azt a forgatókönyvben és a skillben külön, szűken kell engedélyezni. Jelenleg a teszt elfogadási feltétele és a futó komponens eltér.
3. `self-healing-orchestrator`: minden restart után mérhető health/funkció ellenőrzést kérjen, és csak annak eredménye alapján számolja a javítási kísérletet.
4. Teljes READY előtt staging harness kell tényleges Marveen service, teszt DB, deploy/rollback és restore célokkal; a mostani szintetikus 3–6 drill nem helyettesíti ezt.

A kért javítások nem kerültek alkalmazásra; ez a futás csak tesztelésre és jelentésre szólt. A két kódmódosítás a futó ütemezett infrastruktúrát érintheti, ezért először a fenti szabályütközést kell rendezni. Újrateszt: watchdog legfeljebb két sikertelen respawnt és health-check alapú stopot mutasson; disk test a jóváhagyási szabály szerint viselkedjen; a hat eset fusson teljes staging szolgáltatáson.

## Ismételhetőség

Az izolált fixture-eket létrehozó futtatható próba: `python3 scripts/__tests__/self-healing-drills.py`. A próba csak `/tmp` alatti ideiglenes adatot használ, mock `tmux`/`claude`/`df` binárisokat és szintetikus release/SQLite/tar állományokat; a temp könyvtár a futás végén eltűnik.
