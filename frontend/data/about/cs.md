<!--
  O nástroji: zobrazí se po kliknutí na tlačítko (i) vedle
  „Vaše město, váš plán, vaše priority“.
  Text měňte přímo v tomto souboru, kód není třeba upravovat.
  Anglická verze: en.md (stejná struktura).
  Podporovaný zápis je popsán na začátku en.md.
-->

# More Green, Moravia

**Kde v Olomouci by zeleň nejvíce snížila tepelný stres u lidí, kteří jsou mu nejvíce vystaveni?**

More Green, Moravia je interaktivní mapa pro obyvatele, plánovače a město. Hodnotí každou část Olomouce (šestiúhelníky H3 o velikosti asi 75 m) podle tří faktorů: jak velké je tam horko a kolik lidí tam je, kolik zranitelných lidí tam žije a jak málo je tam zeleně. Sami určíte, jak moc má který faktor vážit, a mapa, pořadí i detail oblasti se hned přepočítají.

Přihlášeno do [UPOL Hackathonu 2026](https://hackathon.upol.cz/en/) k tématu **Smart City in Data: Assessing Quality of Life in Olomouc's Micro-zones Using Sensor Data** (hodnocení kvality života v mikrozónách Olomouce pomocí senzorových dat).

> **Předběžné výsledky.** Skóre kombinuje teplotu povrchu ze satelitu (Landsat, léto 2026), teploty během vln veder (v noci i ve dne), počet obyvatel, zranitelné skupiny, zelenou vegetaci (Sentinel-2, léto 2026), pokryvnost stromů, zpevněný povrch, pěší vzdálenost k parkům a dostupné plochy v síti šestiúhelníků o velikosti 75 m (H3); obyvatele a zranitelné skupiny po čtvrtích o velikosti ~200 m. Ověřeno na 2 091 místech, která obyvatelé označili jako příjemná nebo nepříjemná v horkých dnech. Tato verze se zaměřuje na tepelný stres. Berte je jako vodítko, ne jako konečné rozhodnutí.

---

## Jak to funguje

![Jak produkt funguje: data, index INFORM, portál](assets/img/how-it-works.png)

1. **Data.** Pro Olomouc se shromáždí data o horku, obyvatelích, zeleni a využití území (viz *Zdroje dat* níže).
2. **Notebook GI indexu.** Všechna data se převedou na stejnou síť šestiúhelníků H3, přepočtou na skóre 0–1 a spojí vzorcem INFORM.
3. **Zveřejnění.** Výstup notebooku se zkopíruje na web i do služby Zeptat se AI, takže obě ukazují stejná čísla.
4. **Portál.** Web přepočítává skóre přímo ve vašem prohlížeči při každém posunu posuvníku. Zeptat se AI odpovídá jen z týchž dat.

---

## Metodika: přístup INFORM

Skóre vychází z metody [INFORM Risk Index](https://drmkc.jrc.ec.europa.eu/inform-index/INFORM-Risk/Methodology), kterou vyvinulo Společné výzkumné středisko Evropské komise (JRC). INFORM měří riziko jako kombinaci **ohrožení a expozice**, **zranitelnosti** a **nedostatečné schopnosti se vyrovnat**. Každá dimenze se skládá z kategorií a složek a dimenze se spojují geometrickým průměrem.

![Rámec INFORM: dimenze, kategorie a složky](assets/img/inform-framework.png)

*Obrázek: rámec INFORM. Zdroj: Evropská komise, Společné výzkumné středisko, [metodika INFORM Risk](https://drmkc.jrc.ec.europa.eu/inform-index/INFORM-Risk/Methodology).*

Stejnou strukturu používáme v měřítku města, pro horko:

| Dimenze INFORM | V tomto nástroji | Co měří |
|---|---|---|
| Ohrožení a expozice | **Horko a zasažení lidé** | Jak se místo zahřívá a kolik lidí tam bydlí nebo tráví den |
| Zranitelnost | **Zranitelné skupiny** | Starší obyvatelé, malé děti, školy, mateřské školy a lékaři |
| Nedostatečná schopnost se vyrovnat | **Nedostatek zeleně** | Málo vegetace a stromů, hodně zpevněných ploch, daleko do parku |

### Krok 1: z dat na skóre 0–1

Každý ukazatel se převede na hodnotu mezi 0 a 1 (*fuzzy příslušnost*): 0 znamená žádnou potřebu, 1 nejvyšší potřebu. Hodnoty pod dolní mezí dostanou 0, nad horní mezí 1 a mezi nimi hodnota roste lineárně. U horka jsou mezemi medián města a 95. percentil, takže skóre ukazuje místa teplejší, než je v Olomouci obvyklé. Hustota obyvatel a počty zařízení se nejprve logaritmují. U zeleně se používají pevné plánovací meze (např. do 300 m pěšky k zeleni je dobré, 800 m a více špatné).

### Krok 2: spojení ukazatelů do dimenzí

**Horko a lidé (HE).** Horko se skládá z:

| Ukazatel horka | Váha |
|---|---|
| Teplota povrchu ze satelitu (Landsat, léto 2026, 30 m) | 45 % |
| Noční minimální teplota během vln veder | 30 % |
| Teplota povrchu ve čtvrti (průměr mikrozóny) | 15 % |
| Denní maximální teplota během vln veder | 10 % |

Expozice je počet lidí, kteří v oblasti bydlí (noc) a tráví den (den), v poměru 50/50. Horko a expozice se spojí jako `HE = horko^0,5 × expozice^0,5`, takže horké místo, kde nikdo nežije, se na vrchol nedostane.

**Zranitelné skupiny (V):** podíl obyvatel 65+ (35 %), 75+ (20 %), dětí 0–4 let (20 %) a školy, mateřské školy a lékaři (25 %).

**Nedostatek zeleně (GD):** nabídka a dostupnost zeleně, 50/50. Nabídka zahrnuje vegetaci ze Sentinel-2 NDVI (30 %), podíl dostupné zeleně (20 %), zpevněný povrch (20 %), pokryvnost stromů (15 %) a zeleň na obyvatele (15 %). Dostupnost je pěší vzdálenost po ulicích k nejbližšímu parku nebo lesu.

### Krok 3: skóre potřeby zeleně (naše vážení)

Stejně jako v INFORM se tři dimenze spojují **váženým geometrickým průměrem**:

`Potřeba GI = HE^wHE × V^wV × GD^wGD`  (součet vah je 1)

Při předvolbě **Vyvážené** má každá váha 1/3. Díky geometrickému průměru musí místo vycházet vysoko ve všech třech dimenzích: velmi horké místo bez zranitelných obyvatel se na první místo nedostane. Chybějící nebo nulové hodnoty se nastaví na 0,01, aby jedna mezera skóre nevynulovala.

Předvolby a posuvníky mění jen váhy:

| Předvolba | Horko a zasažení lidé | Zranitelné skupiny | Nedostatek zeleně |
|---|---|---|---|
| Vyvážené | 33 % | 33 % | 33 % |
| Chladnější ulice | 50 % | 20 % | 30 % |
| Ochrana zranitelných | 30 % | 50 % | 20 % |
| Kapesní parky | 20 % | 40 % | 40 % |
| Rychlá řešení | 33 % | 33 % | 33 % + jen místa, kde lze stavět |

Skóre se přepočítá ve vašem prohlížeči pro každou oblast při každém pohybu posuvníku. Při spuštění se web sám kontroluje: s váhami Vyvážené musí každá oblast odpovídat skóre spočtenému v notebooku.

### Krok 4: zobrazit jen místa, kde lze stavět

Volba „Zobrazit jen místa, kde lze stavět“ násobí potřebu skóre **proveditelnosti** (0–1): `Priorita = potřeba GI × proveditelnost`. Proveditelnost je vysoká tam, kde je pro zeleň místo: brownfieldy, volné plochy, parkoviště a veřejné budovy (zelené střechy) a také cyklostezky a ulice, které se mohou stát zelenými koridory. Železnice, vodní plochy a rychlostní silnice se vyřazují, protože tam nelze sázet.

---

## Ověření

Index byl ověřen dvěma nezávislými způsoby. Ani jeden do skóre nevstupuje.

**1. Letní tepelná mapa obyvatel** (2 091 míst označených jako příjemná nebo nepříjemná, 2020):

- Ve 114 oblastech s alespoň 3 značkami potřeba GI koreluje s podílem „nepříjemných“ značek (Spearmanovo r = 0,73, významné).
- Pokryvnost stromů (r = −0,81), vegetace (r = −0,74) i zpevněný povrch (r = 0,70) mají očekávaný směr.
- 56 % „nepříjemných“ značek leží v 20 % oblastí s nejvyšší potřebou GI, oproti 7 % „příjemných“.

**2. Ortofoto Olomouce** ([ČÚZK](https://geoportal.cuzk.cz/Default.aspx?mode=TextMeta&metadataID=CZ-CUZK-ORTOCIR-R&metadataXSL=full&side=ortofoto)): výsledky jsme přímo v této aplikaci překryli přes ortofoto, hlavně abychom prověřili plochy s vegetací. Ověřili jsme, že parky, lesy, zahrady a ulice se stromořadím mají nízký nedostatek zeleně a že oblasti s vysokým skóre jsou opravdu zastavěné a zpevněné s málo vegetací. Kontrolu můžete zopakovat: přepněte podkladovou mapu na ortofoto tlačítkem na mapě a v Mapových vrstvách snižte neprůhlednost.

---

## Zdroje dat

| Téma | Data |
|---|---|
| Horko | Teplota povrchu Landsat (léto 2026, 30 m) · denní a noční teploty během vln veder Citiq (2026) · tepelný průměr mikrozón |
| Lidé | Mikrozóny Olomouce: obyvatelé, věk 65+, 75+, 0–4 · školy, mateřské školy, lékaři |
| Zeleň | Sentinel-2 NDVI (léto 2026) · Copernicus Tree Cover Density (10 m) · Copernicus Imperviousness (10 m, 2024) · Copernicus Urban Atlas 2021 · ulice OpenStreetMap pro pěší vzdálenosti |
| Místo pro stavbu | Brownfieldy · volné plochy · parkoviště · veřejné budovy · cyklostezky |
| Ověření | Letní tepelná mapa obyvatel (2 091 míst, 2020) · [ortofoto ČÚZK](https://geoportal.cuzk.cz/Default.aspx?mode=TextMeta&metadataID=CZ-CUZK-ORTOCIR-R&metadataXSL=full&side=ortofoto) |
| Mapa | OpenFreeMap · ortofoto ČÚZK · vyhledávání Mapy.com |

**Omezení.** Obyvatelé a zranitelné skupiny se počítají po mikrozónách (asi 200 m), takže sousední 75m oblasti mají stejné hodnoty. Skóre ukazuje, kde by zeleň pomohla nejvíc; není to návrh ani rozpočet. Náklady na zelené střechy jsou hrubé odhady z publikovaných cenových rozpětí.

---

## Tým

Vytvořil **tým deCoDE**: **Victor**, **Pamela** a **Redoy** pro [UPOL Hackathon 2026](https://hackathon.upol.cz/en/).
