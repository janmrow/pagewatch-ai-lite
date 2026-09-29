# PageWatch AI Lite

**Mały watcher stron i kilka refleksji o tym, jak budować rozwiązania wystarczające.**

`pagewatch-ai-lite` to program w Pythonie, który sprawdza kilka stron, wykrywa zmianę, a potem pyta model językowy, czy ta zmiana ma znaczenie w kontekście intencji użytkownika. Jeśli tak, wysyła mail. W zasadzie to tyle.

Działająca instancja monitoruje wybrane strony studiów podyplomowych na UE Katowice i działa kilka razy dziennie na [Mikrusie](https://mikr.us/).

Sam web monitoring nie jest jednak najciekawszą częścią tego projektu. To można dziś rozwiązać na wiele sposobów i nie trzeba niczego budować. Ten projekt powstał raczej jako case study: **jak zachować kontrolę nad złożonością, kiedy tworzenie kodu stało się bardzo łatwe**.

## Prosty pomysł, który stał się trudny

Pierwsza wersja tego projektu zaczęła się od prostego pomysłu.

Pobrać stronę. Porównać ją z poprzednią wersją. Jeśli coś się zmieniło, ocenić znaczenie zmiany z dowolnym LLM. Jeśli jest istotna, wysłać maila.

Ale w trakcie zaczęły dochodzić kolejne możliwości i decyzje architektoniczne. Pracując z modelami językowymi, łatwo wpaść w ten schemat. Bo skoro dodanie kolejnego elementu jest tak szybkie, to czemu go nie dodać? Agent dopisze kolejną abstrakcję, warstwę integracyjną czy konfigurację w kilka minut.

Gdzieś w połowie projektu zauważyłem, że problem, który chciałem rozwiązać, nadal był mały. Tylko rozwiązanie zaczęło się robić nieproporcjonalnie duże.

Zamiast dalej inwestować w istniejącą strukturę, zacząłem od nowa.

## Kod stał się tani, ale złożoność nadal kosztuje

Agenci kodujący zmienili koszt eksperymentowania z oprogramowaniem.

Spadł koszt wymaganego czasu i wysiłku. Rzecz, której wcześniej nie chciałoby mi się budować przez dwa dni, dziś można zbudować w 10 minut.

To usuwa też część naturalnego oporu, który kiedyś ograniczał rozrost projektu.

Łatwiej stworzyć więcej kodu, niż utrzymać prosty model całego systemu w głowie.

## Druga próba: Just Enough

Drugą wersję zacząłem z użyciem własnego skilla [Just Enough](https://github.com/janmrow/just-enough).

Nie jest to skill do programowania. Jego sens jest prostszy: pomaga pytać, **ile złożoności dany problem rzeczywiście uzasadnia**.

Jeżeli jakaś rzecz poprawia bezpieczeństwo, niezawodność, poprawność albo istotnie zwiększa czytelność, to ma powód, żeby istnieć.

Jeżeli istnieje głównie dlatego, że może kiedyś się przydać albo dlatego, że łatwo ją zbudować, to powód jest słabszy.

W praktyce oznaczało to między innymi:

| Pytanie                                    | Decyzja                                                |
| ------------------------------------------ | ------------------------------------------------------ |
| Czy potrzebuję osobnego schedulera?        | Nie. `cron` rozwiązuje ten problem.                    |
| Czy potrzebuję bazy danych?                | Nie. Kilka atomowo zapisywanych plików wystarcza.      |
| Czy model ma sam wykrywać zmiany?          | Nie. Zwykły kod robi diff, LLM ocenia tylko znaczenie. |
| Czy potrzebuję warstwy providerów dla LLM? | Nie. Jeden konkretny endpoint wystarcza.               |
| Czy awaria może przesunąć stan?            | Nie. Ostatni poprawny baseline jest inwariantem.       |
| Czy potrzebuję rozbudowanego deploymentu?  | Nie. `venv` i `cron` na małym VPS-ie wystarczają.      |

Celem nie było zrobienie najmniejszego programu.

Celem było zrobienie **najmniejszego rozwiązania, któremu nadal można ufać**.

## Co z tego wyszło

Przepływ całego systemu można objąć wzrokiem:

```text
cron
  ↓
fetch
  ↓
normalizacja + diff
  ↓
brak zmiany ─────────────→ stop
  ↓
zmiana + intencja użytkownika
  ↓
LLM
  ↓
IGNORE / REVIEW / NOTIFY
  ↓
email, jeśli potrzebny
  ↓
zapis nowego stanu
```

Pierwsze poprawne uruchomienie zapisuje baseline i niczego nie wysyła.

Jeśli strona się nie zmieniła, model nie jest w ogóle wywoływany.

Jeśli zmiana wystąpiła, model dostaje diff oraz intencję przypisaną do danego targetu. Jego zadanie jest wąskie: zaklasyfikować zmianę jako `IGNORE`, `REVIEW` albo `NOTIFY`.

Dzięki temu model nie wykonuje pracy, którą zwykły deterministyczny kod robi lepiej. Jest używany tylko tam, gdzie potrzebna jest ocena znaczenia tekstu.

## Prościej nie znaczy gorzej

Ważną granicą podczas upraszczania jest to, żeby nie pomylić prostoty z brakiem jakości.

Projekt nie ma bazy danych, Dockera, kolejki ani rozbudowanej warstwy observability. Ma za to rzeczy, których brak mógłby realnie zepsuć jego działanie:

* timeouty dla operacji zewnętrznych,
* walidację odpowiedzi modelu,
* traktowanie treści stron i outputu LLM jako niezaufanych danych,
* niezależne przetwarzanie targetów,
* atomowy zapis stanu,
* zasadę, że nieudany fetch, request do LLM albo wysyłka maila nie mogą nadpisać ostatniego poprawnego baseline'u,
* testy krytycznych zachowań, a nie procent coverage jako cel sam w sobie.

Czyli:

**upraszczać strukturę, ale nie inwarianty.**

Testy obejmują między innymi pierwszy baseline bez powiadomienia, brak wywołania LLM przy braku zmiany, wszystkie trzy decyzje modelu, awarie fetch/LLM/SMTP oraz sytuację, w której jeden target nie może zatrzymać pozostałych.

Poza testami automatycznymi sprawdziłem też realne granice systemu: prawdziwy request do API modelu, rzeczywistą wysyłkę SMTP oraz uruchomienie przez cron na docelowym serwerze.

## Praca z Codexem

Znaczną część implementacji pisał Codex.

`SPEC.md` definiował produkt i jego granice: co ma działać, jakie są inwarianty i kiedy można uznać wersję za skończoną.

`AGENTS.md` definiował sposób pracy: implementować jeden krok naraz, nie budować przyszłych wymagań, nie dodawać abstrakcji bez konkretnego powodu i zatrzymać się, kiedy bieżący problem jest rozwiązany.

Praca wyglądała mniej więcej tak:

```text
SPEC
  ↓
AGENTS
  ↓
jeden mały krok
  ↓
implementacja przez Codex
  ↓
testy i checki
  ↓
ręczne review diffu
  ↓
commit
  ↓
następny krok
```

Przy agentach kodujących bardzo łatwo zbudować dużo.

## Mikrus

Działająca wersja projektu stoi na [Mikrusie](https://mikr.us/).

Mogłem zatrzymać się na lokalnym skrypcie albo próbować opakować go w bardziej rozbudowaną platformę. Zamiast tego chciałem uruchomić go na zwykłym serwerze i zobaczyć cały przepływ od repozytorium do czegoś, co rzeczywiście działa bez mojego udziału.

Mikrus dobrze tutaj pasuje: dostaję normalnego Linuksa, SSH, `cron` i nawet więcej niż trzeba.

Przy okazji taki mały VPS okazał się dobrym środowiskiem do nauki rzeczy, których na większych platformach nie widać: środowiska wirtualnego, zmiennych środowiskowych, uprawnień plików, crona, stref czasowych, logów i zwykłego debugowania na serwerze.

Docelowy harmonogram projektu to:

```text
09:00
11:00
13:00
15:00
```

w strefie `Europe/Warsaw`.

Serwer działa w UTC, więc harmonogram uwzględnia czas warszawski również po zmianie czasu.

Log ostatnich uruchomień można sprawdzić na serwerze:

```bash
cd ~/pagewatch-ai-lite
tail -n 40 .state/cron.log
```

## Uruchomienie

Projekt wymaga minimum Pythona 3.11.

```bash
git clone https://github.com/janmrow/pagewatch-ai-lite.git
cd pagewatch-ai-lite

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Sekrety są przechowywane lokalnie w `.env` i nie trafiają do repozytorium. Aplikacja korzysta między innymi z:

```text
OPENCODE_MODEL
OPENCODE_API_KEY

SMTP_HOST
SMTP_PORT
SMTP_USERNAME
SMTP_PASSWORD
SMTP_FROM
SMTP_TO
```

Monitorowane strony i intencje znajdują się w `config.toml`.

Każdy target ma prosty model:

```toml
[[targets]]
id = "example"
url = "https://example.com"
intent = """
Notify me only about changes that matter for this use case.
"""
```

Pierwszy ręczny run:

```bash
python pagewatch.py
```

Pierwsze poprawne uruchomienie tworzy baseline. Kolejne reagują dopiero na zmianę.

Testy i lint:

```bash
pytest
ruff check .
```

## Deployment na Mikrusie

Na Mikrusie deployment nie wymaga osobnej infrastruktury:

```text
git clone
→ python3 -m venv .venv
→ pip install -r requirements.txt
→ lokalny .env
→ ręczny run
→ cron
```

Po pierwszym ręcznym uruchomieniu warto wykonać kontrolowany test pełnego przepływu z powiadomieniem.

Dopiero potem watcher trafia do crona.

To w praktyce cały deployment tej aplikacji.

## Status

**Obecna wersja działa na Mikrusie.**

Projekt robi to, po co powstał: monitoruje realne strony, ignoruje brak zmian, używa modelu tylko wtedy, kiedy jest potrzebny, wysyła powiadomienie.

Jeśli realne używanie pokaże brakujące wymaganie, można je dodać.

## Licencja

MIT
