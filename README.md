# Kotilaitteet – Kodin automaatiojärjestelmä

Kotilaitteet on selainpohjainen kotiautomaatiotyökalu, jonka avulla voit ohjata kodin laitteita ja hyödyntää sähkön spot-hintoja laitteiden automaattisessa ohjauksessa.

## Ominaisuudet

- **Laitteiden ohjaus** – Käynnistä/sammuta lämmitys, valaistus, ilmastointi, sähköauton laturi, poreallas ja muut laitteet yhdestä näkymästä
- **Sähkön hinnat** – Hakee automaattisesti Suomen sähkön spot-hinnat (NordPool, ALV sisältäen) [spot-hinta.fi](https://spot-hinta.fi) -palvelusta tänään ja huomenna
- **Halvimpien tuntien tunnistus** – Korostaa päivän halvimmat tunnit sekä koontinäytöllä että hintanäkymässä
- **Automaattinen ohjaus** – Laite käynnistyy automaattisesti kun spot-hinta on alle asetetun kynnysarvon (snt/kWh)
- **Ajastukset** – Lisää tuntikohtaisia käynnistys- ja sammutusajastuksia laitteille
- **REST-rajapinta** – Kaikki toiminnot saatavilla myös JSON-rajapinnan kautta
- **Tumma teema** – Tyylikäs responsiivinen käyttöliittymä

## Asennus ja käynnistys

### Vaatimukset

- Python 3.10+

### Asennus

```bash
git clone https://github.com/Timo1234-ai/Kotilaitteet.git
cd Kotilaitteet
pip install -r requirements.txt
```

### Käynnistys

```bash
python app.py
```

Avaa selaimessa: **http://localhost:5000**

## Näkymät

| Sivu | Osoite | Kuvaus |
|---|---|---|
| Koontinäyttö | `/` | Laitteiden pika-ohjaus + nykyinen sähköhinta |
| Laitteet | `/devices` | Laitetaulukko, automaattiohjauksen asetus |
| Sähkön hinta | `/electricity` | Tuntihinnat + kaavio tänään ja huomenna |
| Ajastukset | `/schedule` | Lisää/poista ajastuksia |

## REST-rajapinta

### Laitteet

| Metodi | Osoite | Kuvaus |
|---|---|---|
| `GET` | `/api/devices` | Hae kaikki laitteet |
| `POST` | `/api/devices` | Lisää laite (`name`, `type`, `icon`) |
| `PATCH` | `/api/devices/<id>` | Päivitä laite (`state`, `auto`, `max_price`, `name`) |
| `DELETE` | `/api/devices/<id>` | Poista laite |
| `POST` | `/api/devices/<id>/toggle` | Vaihda tila päällä/pois |

### Sähköhinnat

| Metodi | Osoite | Kuvaus |
|---|---|---|
| `GET` | `/api/electricity/prices` | Tuntihinnat (optio: `?date=2024-01-15`) |
| `GET` | `/api/electricity/cheapest` | Halvimmat tunnit (`?date=...&n=8`) |
| `POST` | `/api/electricity/refresh` | Pakota hintojen päivitys |

### Ajastukset

| Metodi | Osoite | Kuvaus |
|---|---|---|
| `GET` | `/api/schedules` | Hae kaikki ajastukset |
| `POST` | `/api/schedules` | Lisää ajastus (`device_id`, `hour`, `action`) |
| `DELETE` | `/api/schedules/<id>` | Poista ajastus |

### Automaattinen ohjaus

```
POST /api/auto/tick
```

Tarkistaa nykyisen spot-hinnan ja käynnistää/sammuttaa automaattiohjauksessa (`auto: true`) olevat laitteet `max_price`-kynnysarvon mukaan. Lisää cron-tehtävä, joka kutsuu tätä kerran tunnissa:

```bash
0 * * * * curl -X POST http://localhost:5000/api/auto/tick
```

## Testit

```bash
pytest test_app.py -v
```

## Tiedostorakenne

```
app.py           – Flask-sovellus ja API-reitit
models.py        – Laite- ja ajastusmallit (JSON-tiedostoon tallennus)
electricity.py   – Sähköhintojen haku ja halvimpien tuntien laskenta
templates/       – HTML-sivupohjat (Jinja2)
static/css/      – Tyylitiedostot
static/js/       – JavaScript (laiteohjaus + hintataulukko)
data.json        – Laite- ja aikataulutiedot (luodaan automaattisesti)
requirements.txt – Python-riippuvuudet
test_app.py      – Yksikkö- ja integraatiotestit
```

## Laitetyypit

| Tyyppi | Kuvaus |
|---|---|
| `heating` | Lämmitys (lattia, patterit, …) |
| `lighting` | Valaistus (sisä, ulko) |
| `ac` | Ilmastointi / lämpöpumppu |
| `ev_charger` | Sähköauton latauspiste |
| `jacuzzi` | Poreallas |
| `other` | Muu laite |
