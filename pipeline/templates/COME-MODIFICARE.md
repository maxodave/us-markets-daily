# Cambiare l'aspetto del sito

Doppio clic su **`Modifica sito.command`** (nella cartella sopra questa).
Si apre l'editor sui file di `templates/` e il browser sull'anteprima.

Poi: **modifica → Cmd+S → guardi**. La pagina si ricarica da sola in meno di un
secondo. Ripetibile venti volte in due minuti. Il sito online non viene toccato.

Quando hai finito: `Ctrl+C` nella finestra del Terminale.

---

## Dove si cambia cosa

| Vuoi cambiare | Apri | Nota |
|---|---|---|
| Colori, dimensioni, font, spazi, bordi | **`style.css`** | il file che aprirai il 90% delle volte |
| Titolo del sito, sottotitolo, disclaimer, footer | **`page.html`** | testi fissi, uguali ogni giorno |
| *Cosa* si vede (aggiungere un dato, cambiare l'ordine) | **`app.js`** | qui nasce il contenuto dai dati |

I colori stanno tutti in cima a `style.css`, nel blocco `:root`. Cambiare
`--accent` cambia l'accento di tutta la pagina, in una riga.

**Trovare la classe di un elemento**: nel browser, tasto destro sull'elemento →
*Ispeziona*. Nel pannello *Styles* di Chrome puoi anche provare i valori dal vivo
prima di scriverli nel file. I nomi principali: `.edition-headline` (il titolone),
`.stat-strip` (la striscia dei numeri), `.mover` (una riga migliori/peggiori),
`.mover-reason` (la notizia che spiega il movimento), `.feed-card` (una card del
feed), `.archive-item`.

**Da telefono**: la maggior parte dei lettori arriva da LinkedIn, quindi da
telefono. Nell'anteprima usa `Cmd+Alt+I` e l'icona del telefono, oppure apri
dall'iPhone l'indirizzo `http://<ip-del-mac>:8787` che il Terminale ti stampa
all'avvio (stessa Wi-Fi). Il blocco `@media (max-width: 600px)` in fondo a
`style.css` è quello che governa la resa su schermo piccolo.

---

## Come finisce online

**Non fai niente**: alle 23:00 il job del Mac propaga i template su GitHub, e la
pagina online li usa dalla notte successiva.

**Subito**: doppio clic su **`Pubblica sito.command`**. Online in un minuto o due.

In entrambi i casi la pagina viene **ricostruita da zero** da questi file. Per
questo non esiste "la pagina di oggi" da aggiornare: una modifica di stasera vale
per l'edizione di domani e per tutto l'archivio, senza altri gesti.

---

## Se rompi qualcosa

Lo vedi nell'anteprima, prima che vada online:

- **schermata rossa** con l'errore preciso → un segnaposto cancellato in
  `page.html`, o un errore di sintassi in `app.js` (con il numero di riga);
- **il CSS non dà errori**: un valore sbagliato viene ignorato in silenzio dal
  browser. Non succede niente, e non te lo dice nessuno. È il motivo per cui
  l'anteprima va guardata **sempre**, anche per la modifica più banale.

Se un template è rotto, il job delle 23:00 **non** lo propaga: il sito continua a
uscire con l'aspetto di ieri, e la mail del mattino ti arriva comunque.

L'unica cosa da non fare: modificare questi file dall'interfaccia web di
github.com. Salta tutti i controlli.

---

## Dati disponibili, se vuoi mostrare qualcosa di nuovo

In `app.js`, ogni edizione (`ed`) ha:

```
ed.edition_date_it      "6 agosto 2026"          (già mostrato)
ed.session_date_it      "5 agosto 2026"          (già mostrato)
ed.headline             titolo della giornata     (già mostrato)
ed.generated_at         data/ora di generazione   (già mostrato)
ed.auto_report.paragraphs      i 3 paragrafi      (già mostrati)
ed.auto_report.stats           n_up, n_down, n_flat, n_total, avg_pct  (già mostrati)
ed.auto_report.stats.best_sectors      <- MAI MOSTRATO come elenco
ed.auto_report.stats.worst_sectors     <- MAI MOSTRATO come elenco
ed.auto_report.gainers / .losers       le 8+8 società
ed.manual_commentary_html      commento discorsivo, quando c'è
ed.feed                        le 40 notizie con immagine
```

Ogni società in `gainers`/`losers`:

```
m.symbol        "CRL"                    (già mostrato)
m.name          "Charles River Labs"     (già mostrato)
m.pct_change    11.36                    (già mostrato)
m.reason        {title, source, link}    (già mostrato) — può essere null
m.sector        "Health Care"            <- MAI MOSTRATO
m.last_close    260.72                   <- MAI MOSTRATO
```

I settori migliori e peggiori sono già raccontati a parole nel secondo paragrafo,
ma nessuna riga li disegna come elenco o come barre: sono lì pronti.

**Attenzione a `m.reason`**: è `null` quando nessuna testata affidabile spiega il
movimento, e le edizioni più vecchie non hanno affatto quel campo. Se scrivi
`m.reason.title` senza controllare prima, la pagina va in errore sull'archivio.
Il controllo automatico vede solo gli errori di *sintassi*, non questo.

Il file `editions/*.json` contiene anche `m.news` e `m.news_historical` (le
notizie complete per società) e `manual_highlights`, che nella pagina **non**
vengono incorporati per non farla pesare: se un giorno vuoi mostrarli, va
allargata la lista `MOVER_FIELDS` in `build_public_page.py`.
