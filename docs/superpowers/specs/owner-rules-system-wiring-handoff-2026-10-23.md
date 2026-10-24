# Codex felügyeleti átadás: az AGENTS.md szabályok rendszer-szintű betöltése

Dátum: 2026-10-23
Tulajdonos és döntéshozó: MAG Attila
Végrehajtás: a felügyeleti rendszer Codex operátora
Határidő: nincs megadva
Állapot: forrásmódosítások helyben elkészültek; végleges ág, commit, telepítés és főcsatorna-ellenőrzés függőben.

## Cél és elfogadási feltétel

Az `AGENTS.md` legyen az 1–3. jóváhagyott működési szabály egyetlen verziózott forrása, és automatikusan töltődjön be minden releváns agent belépési pontján, új és már létező agenteknél is. A feladat csak akkor kész, ha a módosítás a ténylegesen használt Codex-integrációt tartalmazó kiadási ágba került, a szabályblokk minden futó agent promptjába bejutott, és ezt tesztek, API-állapotok, valamint prompt-ellenőrzések bizonyítják.

Ne módosítsd a szabályok tartalmát MAG Attila jóváhagyása nélkül. Ne indítsd újra az éles szolgáltatásokat a sikeres build és telepítési előellenőrzések előtt. Ne kerüld meg a commit hookot, a hozzáférési korlátot vagy a release-folyamatot.

## Jóváhagyott szabályforrás

Az `AGENTS.md` tartalmazza a jóváhagyott három szabályt és a szabálykarbantartási elvet. A fájl jelenleg uncommitted, a futó repo `main` checkoutjában van. A szabályszöveg módosítása nem része ennek a feladatnak.

## Elvégzett, helyi módosítások

Ezek a módosítások a telepített repó forrásfájljain és a promptokon jelenleg megtalálhatók:

- `scripts/codex-channels.mjs`: az `AGENTS.md` kötelezővé vált; a Codex főcsatorna a `CLAUDE.md` és `SOUL.md` előtt betölti.
- `scripts/codex-worker.mjs`: az `AGENTS.md` kötelező, a worker fejlesztői utasításaihoz hozzáfűződik.
- `src/web/agent-scaffold.ts`: `ensureOwnerOperatingRulesSection()` idempotensen szinkronizálja az `AGENTS.md` tartalmát a kezelt markerblokkba.
- `src/web.ts`: nem `webOnly` dashboard induláskor meghívja a szinkronizálót a fő agentre.
- `src/web/agent-process.ts`: minden Claude agent indítása előtt meghívja a szinkronizálót.
- A fő `CLAUDE.md`, `agents/gazdasagi-vezeto/CLAUDE.md` és `agents/procurement-logistics-lead/CLAUDE.md` fájlokban egy-egy, az `AGENTS.md`-vel pontosan egyező blokk van.

Ellenőrzött eddigi eredmény: `npm run typecheck -- --pretty false` sikeres; `node --check scripts/codex-channels.mjs`, `node --check scripts/codex-worker.mjs` és `git diff --check` sikeres. Mágia György és Bori dashboard API-n keresztüli újraindítása 200-at adott, és mindkettő `running=true` állapotú volt az ellenőrzéskor. Ez a szolgáltatásoldali szinkronizáló új buildből való futását önmagában nem bizonyítja.

## Release-út és jelenlegi akadály

- A repo CONTRIBUTING útmutatója PR-t ír elő `develop` ágra.
- A futó `/home/marveen/marveen` checkout `main` ága helyi állapot szerint 9 committal előrébb van a korábban ismert `origin/main`-nél; a checkoutban más, feladattól független módosítások is vannak. Ezeket tilos eldobni, stash-elni vagy a feladat commitjába venni.
- A repo commit hook a futó `main` checkoutban blokkolja a commitot, és külön worktree használatát javasolja. A `MARVEEN_PROD_COMMIT_OK=1` felülbírálást az automatikus jóváhagyási felülvizsgálat kifejezetten elutasította. Ne próbáld újra és ne kerüld meg.
- A szabályos kísérlet során `/tmp/marveen-owner-rules` worktree készült `origin/develop` alapon. A helyi Codex-integrációs patch nem alkalmazható erre az ágra: onnan hiányzik a `scripts/codex-channels.mjs` és `scripts/codex-worker.mjs`, a `src/web.ts` és `src/web/agent-process.ts` kontextusai is eltérnek. A worktree nem tartalmazza a változtatást.
- Nincs telepített `gh` CLI vagy GitHub PR connector ebben a Codex-környezetben.

**Kötelező döntési kapu:** először határozd meg, melyik központi ág tartalmazza a telepített Codex-runtime integrációt, és hogyan kerül ez a szabálymódosítással együtt a release-be. Ha a megfelelő ág nem a `develop`, kérj repó-karbantartói döntést a célágról. Ne készíts PR-t olyan célágra, amelyből a Codex entrypointok hiányoznak, és ne vigyél be automatikusan kilenc, külön nem felülvizsgált commitot.

## Végrehajtási lépések

1. **Állapotmentés és diff-ellenőrzés**
   - Futtasd a `git status -sb`, `git diff --cached --stat`, `git diff --stat` parancsokat.
   - Azonosítsd az e feladathoz tartozó hat fájlt: `AGENTS.md`, a két `scripts/codex-*.mjs` fájl, `src/web.ts`, `src/web/agent-process.ts`, `src/web/agent-scaffold.ts`.
   - Minden más változtatás maradjon érintetlen.
   - A staged változtatás jelenleg ezt a hat fájlt tartalmazza. Ellenőrizd a staged diff teljes tartalmát commit előtt.

2. **Célág tisztázása és izolált munka**
   - Válaszd ki a tényleges Codex-integrációt tartalmazó, jóváhagyott PR-célágat.
   - Készíts külön worktree-t és témabranch-et a repo által előírt módon.
   - A változtatást tisztán, a célág aktuális fájlszerkezetéhez igazítva vidd át. Ne alkalmazd vakon a korábban sikertelen patch-et.
   - Ha a célág nem tartalmaz Codex runtime-ot, állj meg, és kérj döntést. Ne rebase-eld automatikusan a helyi kilenc commitot.

3. **Tesztregressziók hozzáadása**
   Hozz létre célzott teszteket, amelyek legalább az alábbiakat bizonyítják:
   - Codex főcsatorna promptja az `AGENTS.md` teljes tartalmát tartalmazza, és hiányzó fájlnál hibával leáll.
   - Codex worker promptja ugyanezt teszi a megadott `cwd` alapján.
   - `ensureOwnerOperatingRulesSection()` új agentnél pontosan egy managed blokkot illeszt be.
   - Ismételt futás idempotens: nem dupláz blokkot.
   - Megváltozott kanonikus forrás esetén a korábbi managed blokkot frissíti.
   - Hiányzó `AGENTS.md` vagy agent prompt esetén fail-closed módon hibát ad.
   - Fő agent, meglévő subagent és frissen scaffoldolt agent útvonalai mind lefedettek.
   - A `webOnly` indulás ne írja át a fő promptfájlt; a normál dashboard indulás szinkronizálja.

   A tesztek ne használjanak valódi külső API-t, és ne indítsák újra az éles szolgáltatást. Fájlrendszer-teszteknél használj izolált temp projektet vagy injektálható útvonalakat.

4. **CI és lokális ellenőrzés**
   - `npm run typecheck -- --pretty false`
   - `node --check scripts/codex-channels.mjs`
   - `node --check scripts/codex-worker.mjs`
   - `git diff --check`
   - Futtasd a létrehozott fókuszált teszteket, majd a projekt által előírt teljes CI-tesztcsomagot.
   - Írd a PR-leírásba a parancsokat és azok tényleges kimenetelét. Ne állíts sikert olyan tesztről, amely nem futott le.

5. **PR, review, commit**
   - Nyiss PR-t a jóváhagyott célágra a `.github/pull_request_template.md` teljes kitöltésével.
   - Hivatkozz erre az átadási dokumentumra és írd le az elfogadási kritériumokat.
   - Várd meg és kövesd a repo által előírt review-folyamatot. Csak a jóváhagyott branchben commitolj.
   - Ne használj `MARVEEN_PROD_COMMIT_OK=1`-et a futó `main` checkout commitvédelmének megkerülésére.

6. **Telepítés és újraindítás**
   - Telepítés előtt ellenőrizd az előző build/revíziót, szolgáltatásállapotot, konfigurációt, visszaállítási lehetőséget és a változtatás pontos diffjét.
   - A jóváhagyott commit merge után a projekt `./update.sh` eljárását használd. Ne futtass közvetlen `git reset --hard`, kézi production buildet vagy párhuzamos szolgáltatásindítást.
   - A `./update.sh` maga kezeli a buildet, restartot, health checket és rollbacket. Ne indíts systemd daemon-reloadot vagy külön service restartot az updater mellett.
   - Ha update preflight dirty tracked tree-t jelez, állj meg. Ne használd az `AUTO_STASH=1` opciót, mert az ebben a checkoutban más, idegen módosításokat is stash-elhet.

7. **Telepítés utáni validáció**
   - Ellenőrizd az `update.last-result`, a dashboard `GET /` health-válaszát és a szolgáltatás revízióját/build markerét.
   - Ellenőrizd a `GET /api/agents` listát és a fő, Mágia, Bori, valamint az összes további agent státuszát.
   - Újraolvasással hasonlítsd össze a markerblokkok közötti szöveget az `AGENTS.md` teljes tartalmával. Agentenként pontosan egy blokk legyen.
   - Indítsd újra a főcsatornát a támogatott dashboard API-n keresztül, majd a fő csatorna következő promptját teszteld úgy, hogy vissza tudja idézni az 1–3. szabály lényegét. Ne küldj tesztüzenetet külső címzettre.
   - Legalább egy alügynöknél ellenőrizd, hogy indításkor a prompt szinkronizál, majd ugyanezt új scaffoldolt tesztagenttel is igazold staging/izolált környezetben.
   - Hibánál azonnal állítsd le a további rolloutot, őrizd meg a logot, és használd az updater dokumentált rollbackjét.

## Végső elfogadás

Csak akkor jelentsd késznek, ha mind teljesül:

- a jóváhagyott commit/release tartalmazza az `AGENTS.md`-t és az összes runtime bekötést;
- a cél release-ág valóban tartalmazza a használt Codex entrypointokat;
- regressziós tesztek és CI zöldek;
- telepített szolgáltatás az új revízióval fut;
- fő- és alügynök promptok betöltési ellenőrzése sikeres;
- az 1–3. szabályra adott izolált smoke-check helyes;
- a commit és telepítés az audit trailben visszakereshető.

## Operátori zárójelentés MAG Attilának

Röviden közöld: commit SHA és célág; PR/review állapot; telepített build/revízió; újraindítás eredménye; tesztparancsok és státuszuk; mely agentek betöltését ellenőrizted; rollback lehetőség; fennmaradó kockázat. Válaszd külön a forrásba került módosítást, a telepített módosítást és a ténylegesen runtime-ban ellenőrzött működést.
